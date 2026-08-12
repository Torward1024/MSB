# base/serializable.py
from abc import ABC, ABCMeta
from collections.abc import Callable as AbcCallable, Mapping as AbcMapping
from types import UnionType
from typing import (Dict,
                    Union,
                    List,
                    Any,
                    Literal,
                    Optional,
                    Set,
                    get_origin,
                    get_args)
import weakref
from contextvars import ContextVar
from threading import RLock
from ..errors import (ResolutionError,
                      SerializationError,
                      TypeValidationError,
                      UnknownAttributeError)
from ..utils.logging_setup import logger
from ..utils.validation import Constraint

CYCLIC_REFERENCE = "<cyclic reference>"

# The key serialized data carries its model version under. Data written before this existed
# has no such key, which `from_dict` reads as version 1.
SCHEMA_FIELD = "schema_version"

# Sentinel for cache lookups: None is a legitimate cached value, so it cannot mark a miss.
_MISSING = object()

# Guards the class registry. Declaring a class and reading the registry can happen on
# different threads, and a WeakSet cannot be added to while it is being iterated.
_REGISTRY_LOCK = RLock()

# Identities already serialized during the current to_dict traversal. Kept here rather than
# in a parameter so that `to_dict()` keeps the signature subclasses override, and so that
# concurrent serializations do not share marks.
_TRAVERSAL: ContextVar = ContextVar("msb_arch_to_dict_seen", default=None)

# Every live object with caching enabled. Invalidation climbs the ownership graph on every
# write, and cannot know whether any ancestor caches without walking to it -- so with nothing
# caching anywhere the whole walk reaches nothing, which was 277 us of the 413 measured at 500
# owners. This makes that case one truthiness check.
#
# A stale read is harmless in both directions: a walk skipped for an object that has only just
# enabled caching cannot leave a stale mapping, because a new object has none yet, and an
# extra walk merely costs what it always cost.
#
# Keyed by identity rather than by the object, for the reason the ownership graph is: `__eq__`
# and `__hash__` are defined on class and name, so two entities sharing a name are one member
# of a set, and the death of either would stop tracking the other.
_CACHING_OBJECTS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()

class EntityMeta(ABCMeta):
    """Metaclass for Serializable to handle type annotations and enforce attribute validation.

    Automatically collects type annotations from the subclass and configures the entity to validate
    attributes against these types during initialization and updates.

    Attributes:
        _fields (Dict[str, type]): Dictionary of annotated attribute names and their expected types.
        _type_cache (Dict[Any, Any]): Per-class cache of resolved type hints.
        _entity_registry (Dict[str, WeakSet]): Every class built by this metaclass, grouped
            by class name, used to reconstruct nested entities from their serialized 'type'.

    Notes:
        - Every class gets its own `_type_cache`. A cache shared through the hierarchy would
          be keyed by names that are only unique within one module, so two modules each
          defining a class of the same name would resolve to whichever was seen first.
        - The registry deliberately groups by name rather than overwriting, so a name used in
          two modules is reported as ambiguous instead of silently resolving to one of them.
        - Classes are held weakly. A registry of strong references would keep every class
          ever declared alive for the lifetime of the process, which matters for code that
          builds classes dynamically. A class nothing else refers to cannot be a
          deserialization target anyway, so dropping it loses nothing.
    """

    _entity_registry: Dict[str, weakref.WeakSet] = {}

    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)
        annotations = {}
        for base in reversed(bases):
            if hasattr(base, '_fields'):
                annotations.update(base._fields)
            annotations.update(getattr(base, '__annotations__', {}))
        annotations.update(attrs.get('__annotations__', {}))
        new_class._fields = annotations
        new_class._type_cache = {}
        with _REGISTRY_LOCK:
            EntityMeta._entity_registry.setdefault(name, weakref.WeakSet()).add(new_class)
        return new_class

    @classmethod
    def registered_classes(mcs, type_name: str) -> List[type]:
        """Return the live classes declared under a given name.

        Args:
            type_name (str): The class name to look up.

        Returns:
            List[type]: Matching classes, ordered by module and name so that error messages
                and single-candidate resolution stay deterministic.
        """
        with _REGISTRY_LOCK:
            entry = mcs._entity_registry.get(type_name)
            if not entry:
                return []
            # Materialise inside the lock: another thread declaring a class would otherwise
            # mutate the set while it is being iterated.
            return sorted(entry, key=lambda c: (c.__module__ or "", c.__qualname__))

class Serializable(ABC, metaclass=EntityMeta):
    """Common base for everything MSB validates, serializes and caches.

    Holds the machinery shared by entities and containers: the annotated fields and their
    validation, the name and activation state, serialization to and from dictionaries, the
    cache and the ownership graph it is invalidated through.

    Attributes:
        name (str): An identifier, unique within the container that holds the object.
        isactive (bool): Whether the object is active.
        _fields (Dict[str, type]): Attribute names mapped to their expected types.

    Notes:
        - `BaseEntity` and `BaseContainer` both derive from this class and neither derives
          from the other. They mean different things by `get`, `set`, `clear` and the item
          access operators -- an entity addresses its attributes, a container its items --
          and while the container inherited from the entity, each of those names carried two
          incompatible meanings in one hierarchy.
        - Use this class in `isinstance` checks that should accept either. Checking against
          `BaseEntity` no longer matches a container.
        - Subclasses are expected to define `from_dict`, `clear`, `__eq__` and `__repr__`
          themselves, because those cannot mean the same thing for both.

    Thread safety:
        - State shared between objects is guarded: declaring classes, resolving type hints,
          generating a container class for a project and resolving a handler are all safe to
          do from several threads at once.
        - `to_dict` keeps its traversal marks in a context variable, so concurrent
          serializations never see each other's.
        - A single object is not guarded, exactly as a plain Python object is not. Two
          threads writing attributes of the same entity, or adding to the same container,
          have to be serialized by the caller; with caching enabled a write racing a read
          can leave a stale cached mapping.
    """
    name: str
    isactive: bool
    _type_cache: Dict[Any, Any] = {}
    _cached_to_dict: Dict[str, Any]
    _use_cache: bool

    # The version of *this class's* serialized shape, written into every mapping it produces.
    # Raise it in a subclass when a field is renamed, removed or given a new meaning, and
    # override `migrate` to bring older data forward. Data written before versioning existed
    # carries no version and is read as 1.
    # Deliberately unannotated: an annotation here would make it one of `_fields`, so every
    # entity would carry it as an attribute and serialize it as None.
    SCHEMA_VERSION = 1

    # Field name -> the key in incoming data that names the type to build for it. Only needed
    # for data MSB did not write: its own mappings carry `type`. Declare one where a field is
    # a Union whose members have the same shape, since nothing else can tell them apart.
    # Also unannotated, for the reason above.
    DISCRIMINATORS = {}

    def __init__(self, *, name: str, isactive: bool = True, use_cache: bool = False, **kwargs):
        """Initialize with a name, activation status, and optional typed attributes.

        Args:
            name (str): A required identifier for the entity.
            isactive (bool): Initial activation status of the entity. Defaults to True.
            **kwargs: Arbitrary keyword arguments to set initial attributes, validated against type annotations.

        Raises:
            TypeError: If an attribute value does not match its annotated type.
            ValueError: If an unknown attribute is provided.
        """
        
        self._validate_type('use_cache', use_cache, bool)
        super().__setattr__('_use_cache', use_cache)
        super().__setattr__('_cached_to_dict', None)
        super().__setattr__('_parents', None)
        super().__setattr__('_revision', 0)
        self._validate_type('name', name, str)
        super().__setattr__('name', name)
        self._validate_type('isactive', isactive, bool)
        super().__setattr__('isactive', isactive)
        
        for field in self._fields:
            if field in ('name', '_use_cache', '_cached_to_dict', '_type_cache', 'isactive') and field not in kwargs:
                continue
            value = kwargs.get(field, None)
            expected_type = self._resolve_type(self._fields[field])
            self._validate_type(field, value, expected_type)
            super().__setattr__(field, value)
            if isinstance(value, Serializable):
                value._adopt(self)

        unknown_attrs = set(kwargs.keys()) - set(self._fields.keys())
        if unknown_attrs:
            raise UnknownAttributeError(f"Unknown attributes provided for {self.__class__.__name__}: {unknown_attrs}")

        if self.__dict__.get('_use_cache'):
            # Registered so that invalidation can tell, without walking, whether any cache
            # exists to go stale. Weakly held, so this never keeps an object alive.
            #
            # Read from the attribute rather than from the `use_cache` argument: a container
            # enables caching by passing `_use_cache` through kwargs, which the loop above
            # applies, so the argument alone would miss every caching container.
            _CACHING_OBJECTS[id(self)] = self

        logger.debug("Initialized %s instance with name=%s, isactive=%s", self.__class__.__name__, name, isactive)
    def _adopt(self, owner: Optional['Serializable'] = None, _seen: Optional[Set[int]] = None) -> None:
        """Record ownership for this entity and for everything it holds.

        Args:
            owner (Optional[Serializable]): The entity or container taking ownership.
            _seen (Optional[Set[int]]): Internal. Identities already visited, so a cyclic
                structure is adopted once rather than endlessly.

        Notes:
            - Owners are held weakly, so an entity never keeps one alive.
            - The whole subtree is walked, not just this node: `deepcopy` treats a weak
              reference as atomic, so the copies made by `add` would otherwise keep pointing
              at the originals and invalidation would never reach the new owner.
            - An entity can have several owners. Storing only the latest was enough while
              `add` deep copied, but `copy_items=False` puts one object into two containers,
              and then every one of them has to be invalidated, not just the last.
            - Owners are keyed by identity rather than kept in a set: a set would hash and
              compare them, and comparing entities walks their fields, which never returns
              on a cyclic structure.
            - The mapping is created on first adoption, so an entity that belongs to nothing
              carries no extra state.
        """
        seen = set() if _seen is None else _seen
        if id(self) in seen:
            return
        seen.add(id(self))
        if owner is not None:
            owners = self.__dict__.get('_parents')
            if owners is None:
                owners = {}
                super().__setattr__('_parents', owners)
            owners[id(owner)] = weakref.ref(owner)
        for key in self._fields:
            if key.startswith('_'):
                continue
            value = getattr(self, key, None)
            if isinstance(value, Serializable):
                value._adopt(self, seen)
    @property
    def revision(self) -> int:
        """How many times this object has been written to.

        Returns:
            int: 0 for an object nobody has changed since it was built, and one more after each
                write.

        Notes:
            - **"Did this change" without keeping a copy of what it was.** Two reads of the same
              number mean nothing was written in between; two different numbers mean something
              was. That is the cheap half of knowing whether a result is still good, and it costs
              one increment on a path that was already there to invalidate the cache.
            - **About this object, not about what it holds.** A container's revision does not
              move when one of its items is written to, because making it move would mean walking
              up the ownership graph on every write whether anything cached or not. Ask the item.
            - Not serialised. A revision counts writes in one process's memory; a number restored
              from a file would claim to compare with something it never saw.
        """
        return self.__dict__.get('_revision', 0)

    def _invalidate_cache(self) -> None:
        """Drop the cached serialization of this entity and of everything that owns it, and
        record that this one was written to.

        Notes:
            - A container serializes its items, so a mutated item makes every ancestor
              stale. Invalidation therefore walks up the ownership graph rather than down
              into the children, which is both correct and cheap.
            - Every owner is visited, not just one: an item added with `copy_items=False`
              belongs to each container that holds it, and all of them go stale together.
            - The walk is guarded against a cycle in the ownership graph.
        """
        try:
            self.__dict__['_revision'] += 1
        except KeyError:                        # built by something that skipped __init__
            self.__dict__['_revision'] = 1

        if not _CACHING_OBJECTS:
            # Nothing anywhere caches, so there is no stale mapping for the walk to find.
            # Dead owners are still dropped, because pruning them is the walk's other job and
            # they would otherwise accumulate for the lifetime of the object. That costs one
            # pass over the direct owners rather than over the whole graph above them.
            owners = self.__dict__.get('_parents')
            if owners:
                for key, ref in list(owners.items()):
                    if ref() is None:
                        del owners[key]
            return

        if not self.__dict__.get('_parents'):
            # Nothing owns this entity, so there is no graph to walk and no reason to
            # allocate one.
            if self.__dict__.get('_use_cache') and '_cached_to_dict' in self.__dict__:
                super().__setattr__('_cached_to_dict', None)
            return

        pending = [self]
        visited = set()
        while pending:
            node = pending.pop()
            if id(node) in visited:
                continue
            visited.add(id(node))
            if getattr(node, '_use_cache', False) and hasattr(node, '_cached_to_dict'):
                super(Serializable, node).__setattr__('_cached_to_dict', None)
            owners = node.__dict__.get('_parents')
            if not owners:
                continue
            for key, ref in list(owners.items()):
                owner = ref()
                if owner is None:
                    del owners[key]          # the owner is gone; stop tracking it
                else:
                    pending.append(owner)
    #: What each numeric annotation also accepts, following PEP 484's numeric tower: a value
    #: annotated `float` may be an `int`, and one annotated `complex` may be either. This is
    #: what every type checker does, and what a caller writing `(0, 90)` for a pair of degrees
    #: expects. Nothing here widens `int` -- an annotation asking for a whole number means it.
    _NUMERIC_TOWER = {float: (float, int), complex: (complex, float, int)}

    @classmethod
    def _accepted_for(cls, resolved_type: Any) -> Any:
        """Return the types an annotation accepts, widening the numeric ones.

        Args:
            resolved_type (Any): A class, or a tuple of classes, to check against.

        Returns:
            Any: The same thing, with `float` and `complex` widened to what they also accept.

        Notes:
            - Before this, `frequency: float` rejected `1`, and `Tuple[float, float]` rejected
              `(0, 90)`. Both are ordinary Python, and the second is how anyone writes a range
              of degrees. The error named the tuple element, which made it look like a
              collection problem rather than the numeric rule it was.
        """
        if isinstance(resolved_type, tuple):
            widened = []
            for member in resolved_type:
                widened.extend(cls._NUMERIC_TOWER.get(member, (member,)))
            return tuple(dict.fromkeys(widened))
        return cls._NUMERIC_TOWER.get(resolved_type, resolved_type)

    def _validate_type(self, key: str, value: Any, expected_type: Any) -> None:
        """Validate that a value matches the expected type.

        Args:
            key (str): The attribute name being validated.
            value (Any): The value to check.
            expected_type (Any): The expected type from type annotations.

        Raises:
            TypeError: If the value does not match the expected type, or if 'name' is None.

        Notes:
            - `None` is accepted for every attribute except 'name', because unset annotated
              attributes are initialized to None by `__init__`. Requiring a value therefore
              cannot be expressed through the annotation alone; enforce it in the subclass.
            - 'name' is the only mandatory attribute: containers index their items by it.
            - The structural check is delegated to `_check_type`, which walks nested generics.
        """
        if key == 'name' and value is None:
            raise TypeValidationError(f"Attribute '{key}' cannot be None")
        if value is None:
            return

        checker = self.__class__._compiled_validator(expected_type)
        if checker is not None:
            if not checker(value):
                raise TypeValidationError(
                    f"Attribute '{key}' must be of type {self._resolve_type(expected_type)}, "
                    f"got {type(value)}")
            return

        self._check_type(key, value, expected_type, f"Attribute '{key}'")

    @classmethod
    def _compiled_validator(cls, hint: Any):
        """Return a one-call check for a hint, or None to use the structural walk.

        Args:
            hint (Any): The annotation to compile.

        Returns:
            Optional[Callable[[Any], bool]]: A predicate that is True for an acceptable
                value, or None when the hint needs `_check_type`.

        Notes:
            - Compiled once per class and kept in the class's own dictionary, so a subclass
              never reads a parent's table and resolution happens once rather than per
              instance. Profiling put 42 `isinstance` calls and ten `get_origin`/`get_args`
              calls into constructing a single entity, almost all of it re-deriving the same
              answer about the same annotation.
            - Only a plain class and `Any` compile. Everything parameterized keeps the
              structural walk, which is where the meaning lives and where a second
              implementation would eventually disagree with the first.
            - Keyed by the hint rather than by the field name, because a container validates
              its items under a key that carries the item's name, which would otherwise put
              one entry in the table per item.
        """
        table = cls.__dict__.get('_compiled_validators')
        if table is None:
            table = {}
            type.__setattr__(cls, '_compiled_validators', table)

        try:
            if hint in table:
                return table[hint]
        except TypeError:
            return None                       # an unhashable hint cannot be tabulated

        resolved = cls._resolve_type(hint)
        checker = None
        if not hasattr(resolved, '__metadata__'):
            if resolved is Any:
                checker = lambda value: True                              # noqa: E731
            elif get_origin(resolved) is None and isinstance(resolved, type):
                checker = lambda value, _type=cls._accepted_for(resolved): isinstance(value, _type)  # noqa: E731

        table[hint] = checker
        return checker
    @classmethod
    def _check_type(cls, key: str, value: Any, expected_type: Any, subject: str) -> None:
        """Recursively check a non-None value against a (possibly generic) type hint.

        Supports plain classes, `Any`, `Union`/`Optional` (both `Union[X, Y]` and `X | Y`),
        `Literal`, `Callable`, `Type[X]`, and the parameterized builtin collections
        `list`, `set`, `frozenset`, `tuple` and `dict`, nested to any depth.

        Args:
            key (str): The attribute name being validated, used in error messages.
            value (Any): The value to check. Must not be None.
            expected_type (Any): The type hint to check against.
            subject (str): Human readable description of what is being checked, used as the
                prefix of error messages (e.g. "Attribute 'tags'", "Item in list 'tags'").

        Raises:
            TypeError: If the value does not match the expected type.

        Notes:
            - `None` elements inside collections are skipped, mirroring the top-level rule.
            - Type hints whose origin is an abstract collection (e.g. `Sequence[int]`) are
              checked with `isinstance` against the origin only; their elements are left
              unchecked so that arbitrary iterables are never consumed during validation.
            - Unresolvable or non-class hints are accepted rather than raising, so that an
              exotic annotation never blocks a valid assignment.
        """
        resolved_type = cls._resolve_type(expected_type)

        # Unwrap Annotated[X, ...] down to X, keeping the constraints it carries. They are
        # applied after the type is known to hold, so a rule never sees a value it was not
        # written for.
        constraints = []
        while hasattr(resolved_type, '__metadata__'):
            constraints.extend(item for item in resolved_type.__metadata__
                               if isinstance(item, Constraint))
            resolved_type = cls._resolve_type(resolved_type.__origin__)

        if constraints:
            cls._check_type(key, value, resolved_type, subject)
            for constraint in constraints:
                constraint.check(value, subject)
            return

        if resolved_type is Any:
            return
        if resolved_type is None or resolved_type is type(None):
            raise TypeValidationError(f"{subject} must be None, got {type(value)}")

        origin = get_origin(resolved_type)
        type_args = get_args(resolved_type)

        if origin is None:
            if isinstance(resolved_type, (type, tuple)):
                if not isinstance(value, cls._accepted_for(resolved_type)):
                    raise TypeValidationError(f"{subject} must be of type {resolved_type}, got {type(value)}")
            else:
                logger.debug("Skipping unenforceable type hint %r for '%s'", resolved_type, key)
            return

        if origin is Union or origin is UnionType:
            for union_type in type_args:
                if cls._resolve_type(union_type) is type(None):
                    continue
                try:
                    cls._check_type(key, value, union_type, subject)
                    return
                except TypeError:
                    continue
            raise TypeValidationError(f"{subject} does not match any type in {resolved_type}, got {type(value)}")

        if origin is Literal:
            for literal_value in type_args:
                if type(value) is type(literal_value) and value == literal_value:
                    return
            raise TypeValidationError(f"{subject} must be one of {list(type_args)}, got {value!r}")

        if origin is type:
            if not isinstance(value, type):
                raise TypeValidationError(f"{subject} must be a class, got {type(value)}")
            if type_args:
                bound = cls._resolve_type(type_args[0])
                if isinstance(bound, type) and not issubclass(value, bound):
                    raise TypeValidationError(f"{subject} must be a subclass of {bound}, got {value}")
            return

        if origin is AbcCallable:
            if not callable(value):
                raise TypeValidationError(f"{subject} must be callable, got {type(value)}")
            return

        if origin is dict or (isinstance(origin, type) and issubclass(origin, AbcMapping)):
            if not isinstance(value, origin):
                raise TypeValidationError(f"{subject} must be a {origin.__name__}, got {type(value)}")
            if origin is dict and len(type_args) == 2:
                cls._check_mapping(key, value, type_args[0], type_args[1], subject)
            return

        if origin in (list, set, frozenset):
            if not isinstance(value, origin):
                raise TypeValidationError(f"{subject} must be a {origin.__name__}, got {type(value)}")
            if type_args:
                cls._check_elements(key, value, type_args[0], f"Item in {origin.__name__} '{key}'")
            return

        if origin is tuple:
            if not isinstance(value, tuple):
                raise TypeValidationError(f"{subject} must be a tuple, got {type(value)}")
            cls._check_tuple(key, value, type_args, subject)
            return

        # Any other generic alias (user generics, abstract collections): check the origin only.
        if isinstance(origin, type) and not isinstance(value, origin):
            raise TypeValidationError(f"{subject} must be of type {resolved_type}, got {type(value)}")
    @classmethod
    def _check_elements(cls, key: str, values: Any, item_type: Any, subject: str) -> None:
        """Check every element of a homogeneous collection against an item type.

        Args:
            key (str): The attribute name being validated, used in error messages.
            values (Any): The iterable whose elements are checked.
            item_type (Any): The expected type of each element.
            subject (str): Description of an element, used as the error message prefix.

        Raises:
            TypeError: If any element does not match `item_type`.
        """
        resolved_item_type = cls._resolve_type(item_type)
        if resolved_item_type is Any:
            return
        for item in values:
            if item is None:
                continue
            cls._check_type(key, item, resolved_item_type, subject)
    @classmethod
    def _check_mapping(cls, key: str, value: Dict[Any, Any], key_type: Any, value_type: Any,
                       subject: str) -> None:
        """Check the keys and values of a mapping against their declared types.

        Args:
            key (str): The attribute name being validated, used in error messages.
            value (Dict[Any, Any]): The mapping to check.
            key_type (Any): The expected type of every key.
            value_type (Any): The expected type of every value.
            subject (str): Description of the mapping, used for context in error messages.

        Raises:
            TypeError: If any key or value does not match its declared type.
        """
        resolved_key_type = cls._resolve_type(key_type)
        resolved_value_type = cls._resolve_type(value_type)
        check_keys = resolved_key_type is not Any
        check_values = resolved_value_type is not Any
        if not check_keys and not check_values:
            return
        for k, v in value.items():
            if check_keys:
                cls._check_type(key, k, resolved_key_type, f"Key in '{key}'")
            if check_values and v is not None:
                cls._check_type(key, v, resolved_value_type, f"Value in '{key}'")
    @classmethod
    def _check_tuple(cls, key: str, value: tuple, type_args: tuple, subject: str) -> None:
        """Check a tuple against either a variadic or a fixed-length type hint.

        Handles both `Tuple[X, ...]` (any number of X) and `Tuple[X, Y]` (exact arity).
        A bare `tuple` or `Tuple[()]` places no constraint on the elements.

        Args:
            key (str): The attribute name being validated, used in error messages.
            value (tuple): The tuple to check.
            type_args (tuple): The arguments of the tuple type hint.
            subject (str): Description of the tuple, used as the error message prefix.

        Raises:
            TypeError: If the arity or any element type does not match.
        """
        if not type_args or type_args == ((),):
            return
        if len(type_args) == 2 and type_args[1] is Ellipsis:
            cls._check_elements(key, value, type_args[0], f"Item in tuple '{key}'")
            return
        if len(value) != len(type_args):
            raise TypeValidationError(f"{subject} must have {len(type_args)} items, got {len(value)}")
        for index, (item, item_type) in enumerate(zip(value, type_args)):
            if item is None:
                continue
            cls._check_type(key, item, item_type, f"Item {index} in tuple '{key}'")
    def activate(self) -> None:
        """Activate the entity, setting its status to active.

        Notes:
            - Logs an info message indicating the entity has been activated.
        """
        self.isactive = True
        self._invalidate_cache()
        logger.debug("Activated %s instance", self.__class__.__name__)
    def deactivate(self) -> None:
        """Deactivate the entity, setting its status to inactive.

        Notes:
            - Logs an info message indicating the entity has been deactivated.
        """
        self.isactive = False
        self._invalidate_cache()
        logger.debug("Deactivated %s instance", self.__class__.__name__)
    def has_attribute(self, key: str) -> bool:
        """Check whether an annotated attribute exists and is set.

        Args:
            key (str): The name of the attribute to check.

        Returns:
            bool: True if the attribute is declared on the class and set on the instance.

        Notes:
            - Lives here rather than on `BaseEntity` because a container has annotated
              attributes too. Splitting the hierarchy moved it off containers by accident;
              its counterpart for items is `BaseContainer.has_item`.
        """
        return key in self._fields and hasattr(self, key)

    @classmethod
    def _apply_migration(cls, data: dict) -> dict:
        """Bring serialized data up to this class's schema version, if it is behind.

        Args:
            data (dict): A copy of the mapping being restored. Modified in place by `migrate`.

        Returns:
            dict: The data in the shape this version expects, with the version key removed.

        Notes:
            - Shared by everything that restores, because the class most worth versioning is
              usually the one saved to a file -- a project or a container -- and for a while
              only entities checked. Serialized data with no version reads as version 1.
        """
        written_under = data.pop(SCHEMA_FIELD, 1)
        if written_under != cls.SCHEMA_VERSION:
            data = cls.migrate(data, written_under)
            data.pop("type", None)
            data.pop(SCHEMA_FIELD, None)
        return data

    @classmethod
    def migrate(cls, data: dict, from_version: int) -> dict:
        """Bring serialized data written by an older version of this class up to date.

        Args:
            data (dict): The mapping as it was written, with its original field names.
            from_version (int): The `SCHEMA_VERSION` it was written under.

        Returns:
            dict: The same data in the shape the current version expects.

        Raises:
            SerializationError: By default, naming both versions. A class that raises its
                `SCHEMA_VERSION` without overriding this is declaring that older data cannot
                be read, and says so rather than failing later on a missing field.

        Notes:
            - Called by `from_dict` only when the version differs, so the common case costs
              nothing.
            - Migrate forward one step at a time when several versions have passed; each step
              is easier to reason about than one jump, and the intermediate shapes are the
              ones already tested.

        Example:
            ```python
            class Telescope(BaseEntity):
                SCHEMA_VERSION = 2
                diameter: float          # was 'size' in version 1

                @classmethod
                def migrate(cls, data, from_version):
                    if from_version == 1:
                        data["diameter"] = data.pop("size")
                    return data
            ```
        """
        raise SerializationError(
            f"{cls.__name__} cannot read data written under schema version {from_version}; "
            f"it is now version {cls.SCHEMA_VERSION}. Override `migrate` to bring it forward."
        )

    @classmethod
    def _deserialize_value(cls, value: Any, hint: Any, field_path: str = "",
                           discriminator: Optional[str] = None) -> Any:
        """Rebuild a value from plain data, guided by what the annotation declares.

        Args:
            value (Any): The data as it was read.
            hint (Any): The annotation the value belongs to.
            field_path (str, optional): Where it sits, for error messages. Defaults to "".
            discriminator (Optional[str], optional): A key in the data naming the type to
                build, for data that does not carry `type`. Defaults to None.

        Returns:
            Any: The value as the annotation declares it.

        Notes:
            - The annotation is the schema. JSON has no set, no tuple and no entity, so what
              comes back is a list or a mapping, and only the declared type says which of the
              three it was. This is why a `Tuple[float, float]` used to survive `json.dumps`
              and then be rejected by `from_dict` for being a list.
            - A mapping carrying a `type` field is an entity, and is restored through the
              class that field names, so a subclass stored in a field typed as its base comes
              back as the subclass. A `discriminator` names the key to read instead, for data
              MSB did not write.
            - **A `Union` without either is resolved by trying its members in order and
              keeping the first that accepts the data.** That is right whenever the members
              differ in shape, and a guess when they do not: declare a discriminator on such
              a field rather than relying on the order.
            - Anything the hint does not describe is returned unchanged, which keeps an exotic
              annotation from blocking a restore.
        """
        if value is None:
            return None

        origin = get_origin(hint)
        args = get_args(hint)

        if isinstance(value, dict):
            named = value.get(discriminator) if discriminator else value.get("type")
            if named is not None:
                entity_type = cls._resolve_entity_type(
                    named, hint if isinstance(hint, type) else None)
                if entity_type is not None:
                    payload = value
                    if discriminator and discriminator != "type":
                        # The key belongs to the wire format, not to the model, so the class
                        # being built would reject it as an attribute it never declared.
                        payload = {k: v for k, v in value.items() if k != discriminator}
                    return entity_type.from_dict(payload)

        if origin is Union:
            for member in args:
                if member is type(None):
                    continue
                try:
                    return cls._deserialize_value(value, member, field_path, discriminator)
                except (TypeError, ValueError, AttributeError):
                    continue
            return value

        if origin in (list, List):
            member = args[0] if args else Any
            return [cls._deserialize_value(item, member, field_path, discriminator)
                    for item in value]
        if origin in (set, frozenset):
            member = args[0] if args else Any
            rebuilt = (cls._deserialize_value(item, member, field_path, discriminator)
                       for item in value)
            return origin(rebuilt)
        if origin is tuple:
            if len(args) == 2 and args[1] is Ellipsis:
                return tuple(cls._deserialize_value(item, args[0], field_path, discriminator)
                             for item in value)
            if args:
                return tuple(cls._deserialize_value(item, member, field_path, discriminator)
                             for item, member in zip(value, args))
            return tuple(value)
        if origin is dict and isinstance(value, dict):
            key_hint = args[0] if len(args) == 2 else Any
            member = args[1] if len(args) == 2 else Any
            return {cls._restore_key(key, key_hint): cls._deserialize_value(item, member,
                                                                            field_path,
                                                                            discriminator)
                    for key, item in value.items()}

        if isinstance(hint, type) and issubclass(hint, Serializable) and isinstance(value, dict):
            return hint.from_dict(value)

        return value

    @classmethod
    def _restore_key(cls, key: Any, hint: Any) -> Any:
        """Return a mapping key as its annotation declares it.

        Args:
            key (Any): The key as it was read.
            hint (Any): The key type the annotation declares.

        Returns:
            Any: The key, converted when the declared type is a scalar JSON cannot express.

        Notes:
            - **JSON has only string keys.** A `Dict[float, float]` therefore comes back with
              `"1420.0"` where it was written with `1420.0`, and validation rejects it -- so a
              mapping keyed by anything but `str` could not round-trip at all. Values were
              already restored from the annotation; keys were not, which was an oversight
              rather than a decision.
            - Only `int`, `float` and `bool` are converted, and only from a string. Those are
              what JSON flattens; anything else is returned untouched, so an exotic key type
              is no worse off than before.
            - A conversion that fails leaves the key alone, so the type error names the field
              rather than coming from here.
        """
        if not isinstance(key, str) or hint in (Any, str):
            return key
        if hint is bool:
            return {"true": True, "false": False}.get(key.lower(), key)
        if hint in (int, float):
            try:
                return hint(key)
            except ValueError:
                return key
        return key

    @classmethod
    def _serialize_value(cls, value: Any, seen: Set[int]) -> Any:
        """Reduce a value to data that survives JSON, descending through collections.

        Args:
            value (Any): The value held by an attribute.
            seen (Set[int]): Identities already serialized in this traversal.

        Returns:
            Any: The value as plain data.

        Notes:
            - Descent used to stop at the attribute: an entity held *directly* was serialized
              and one held inside a list or a dict was not, so the mapping carried live
              objects, `json.dumps` refused it and `from_dict` could not restore it.
            - `set` and `frozenset` become lists, and `tuple` becomes a list, because JSON has
              none of the three. The declared type is what restores them, in
              `_deserialize_value`.
            - A set is ordered before it is written. Its iteration order is arbitrary, so
              without this the same object serializes differently on each run, and any later
              comparison, hash or diff of the output is meaningless. Natural order is used
              where the elements allow it and `repr` order otherwise, which is total.
        """
        if isinstance(value, Serializable):
            return CYCLIC_REFERENCE if id(value) in seen else value.to_dict()
        if isinstance(value, dict):
            return {key: cls._serialize_value(item, seen) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._serialize_value(item, seen) for item in value]
        if isinstance(value, (set, frozenset)):
            items = [cls._serialize_value(item, seen) for item in value]
            try:
                return sorted(items)
            except TypeError:
                return sorted(items, key=repr)
        return value

    def fingerprint(self) -> str:
        """Return a hash of everything this object holds, itself and below.

        Returns:
            str: 16 hexadecimal characters. Two objects with the same contents give the same
                string, whatever order their fields were written in and whether or not they are
                the same object.

        Notes:
            - The other half of `revision`, and the half that answers across processes and
              across time. `revision` says "was this written to" and costs nothing; this says
              "is this the same content as before" and costs one serialisation.
            - Computed over `to_dict` with the keys sorted, so it depends on what the object
              *is* rather than on the order anything was assigned. `name` is part of the
              content, since two differently named objects are not the same input.
            - Truncated to 64 bits. This identifies content, it does not authenticate it: a
                collision means a wrong cache hit, not a forged one, and 64 bits is 1 in 2**32
                after four billion distinct objects.
            - Reflects the cached mapping when caching is on, so it is invalidated with it.

        Examples:
            >>> a, b = Item(name="i", value=1), Item(name="i", value=1)
            >>> a.fingerprint() == b.fingerprint()
            True
        """
        import hashlib
        import json

        content = json.dumps(self.to_dict(), sort_keys=True, default=repr, ensure_ascii=False)
        return hashlib.blake2b(content.encode("utf-8"), digest_size=8).hexdigest()

    def to_dict(self) -> dict:
        """Convert the entity to a dictionary for serialization.

        Automatically serializes the entity's state, including all annotated attributes,
        with nested entities recursively serialized. Always includes a 'type' field with the class name.

        Returns:
            dict: A dictionary containing the entity's serialized data.

        Notes:
            - A reference to an entity already serialized in this traversal is replaced with
              `CYCLIC_REFERENCE`, which makes genuine cycles terminate rather than exhaust
              the stack.
            - The traversal state lives in a context variable rather than in a parameter, so
              this signature stays the one a subclass overrides. Passing it as an argument
              broke every override written as `def to_dict(self)`, which is how subclasses
              are meant to write it.
            - Because the state is contextual it is also per thread and per task, so two
                concurrent serializations never see each other's marks.
            - When caching is enabled the very same mapping is returned on every call. Treat
              it as read only: mutating it corrupts the cache. Copy it before changing it.
            - The cache is only written at the root of a traversal. A nested result can carry
              cycle markers that only hold relative to that root, so it is never stored.
        """
        if self._use_cache and self._cached_to_dict is not None:
            return self._cached_to_dict

        seen = _TRAVERSAL.get()
        is_root = seen is None
        token = _TRAVERSAL.set(set()) if is_root else None
        seen = _TRAVERSAL.get()
        try:
            seen.add(id(self))
            data = {"name": self.name, "isactive": self.isactive,
                    "type": self.__class__.__name__}
            if self.SCHEMA_VERSION != 1:
                # Written only by a class that has actually versioned itself. Writing it
                # always put a key nobody asked for into everybody's data, and broke every
                # hand-written `from_dict` override that reasonably rejected what it did not
                # recognise. A class at version 1 therefore serializes exactly as it did
                # before versioning existed, and data carrying no version reads as 1.
                data[SCHEMA_FIELD] = self.SCHEMA_VERSION
            for key in self._fields:
                if key.startswith('_'):
                    continue
                if not hasattr(self, key):
                    continue
                data[key] = self._serialize_value(getattr(self, key), seen)
        finally:
            if is_root:
                _TRAVERSAL.reset(token)

        if self._use_cache and is_root:
            self._cached_to_dict = data
        return data
    @classmethod
    def _resolve_entity_type(cls, type_name: str, expected_type: Any = None) -> Any:
        """Find the entity class that a serialized 'type' field refers to.

        Args:
            type_name (str): The class name recorded by `to_dict`.
            expected_type (Any): The annotated type of the attribute being restored, used to
                narrow the search. May be any type hint, or None.

        Returns:
            Any: The matching entity class, or None if the name is not known.

        Raises:
            TypeError: If several registered classes share the name and none of them can be
                singled out.

        Notes:
            - Candidates are taken from the metaclass registry, so classes defined anywhere
              are found; the previous lookup consulted only the framework module's globals
              and therefore never resolved a user type.
            - Resolution order: this class, then the annotated type, then a class declared in
              the same module as this one, then a subclass of the annotated type.
        """
        if type_name == cls.__name__:
            return cls
        if isinstance(expected_type, type) and expected_type.__name__ == type_name:
            return expected_type

        candidates = EntityMeta.registered_classes(type_name)
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        same_module = [c for c in candidates if c.__module__ == cls.__module__]
        if len(same_module) == 1:
            return same_module[0]
        if isinstance(expected_type, type):
            narrowed = [c for c in candidates if issubclass(c, expected_type)]
            if len(narrowed) == 1:
                return narrowed[0]

        raise ResolutionError(
            f"Ambiguous type '{type_name}' while restoring {cls.__name__}: "
            f"{sorted(f'{c.__module__}.{c.__name__}' for c in candidates)}"
        )
    @classmethod
    def _lookup_type_name(cls, type_name: str, field_path: str = "") -> Any:
        """Resolve a bare type name against the module that defines this class.

        Args:
            type_name (str): The name to resolve.
            field_path (str): Optional description of the field being resolved, used in errors.

        Returns:
            Any: The resolved object.

        Raises:
            TypeError: If the name cannot be found.

        Notes:
            - Resolution order: this class itself, the module that defines it, the framework
              module, then the entity registry. The defining module is consulted before the
              framework module so a user class never loses to a same-named framework symbol.
            - Checking this class first lets a self-referential entity such as
              `peer: 'Node'` inside `class Node` resolve wherever the class is declared,
              including inside a function, where it is not reachable through its module.
            - The registry is a last resort and only accepted when the name is unambiguous,
              so a name declared in two modules still reports an error rather than guessing.
        """
        from inspect import getmodule

        if type_name == cls.__name__:
            return cls

        module = getmodule(cls)
        resolved = getattr(module, type_name, None) if module else None
        if resolved is None:
            resolved = globals().get(type_name)
        if resolved is None:
            candidates = EntityMeta.registered_classes(type_name)
            if len(candidates) == 1:
                resolved = candidates[0]
            elif len(candidates) > 1:
                raise ResolutionError(
                    f"Ambiguous type name '{type_name}' for {field_path or cls.__name__}: "
                    f"{sorted(f'{c.__module__}.{c.__name__}' for c in candidates)}"
                )
        if resolved is None:
            raise ResolutionError(f"Cannot resolve type name '{type_name}' for {field_path or cls.__name__}")
        return resolved

    @classmethod
    def _resolve_type_variable(cls, variable: Any, field_path: str = "") -> Any:
        """Resolve a type variable to whatever the class was parameterized with.

        Args:
            variable (TypeVar): The type variable to resolve.
            field_path (str, optional): Where it was found, for error messages. Defaults to "".

        Returns:
            Any: The type the variable stands for in this class, or `Any` when nothing
                determines it.

        Notes:
            - **By position.** A variable is matched against the parameters its own generic
              base declares, so the second parameter of `Generic[T, U]` resolves to the second
              argument. Taking the first argument regardless, as this did before, silently
              gave every field the first type.
            - Constraints become a union: `TypeVar('V', int, str)` accepts an `int` or a `str`,
              where before it accepted only an `int`.
            - A bound resolves to the bound.
            - Anything left unparameterized resolves to `Any` rather than raising. That
              matches what `_check_type` already does with a hint it cannot reduce to a class:
              an unresolvable annotation does not block an otherwise valid assignment.
        """
        for base in getattr(cls, '__orig_bases__', ()) or ():
            parameters = getattr(get_origin(base), '__parameters__', ())
            arguments = get_args(base)
            if variable in parameters and len(arguments) == len(parameters):
                argument = arguments[parameters.index(variable)]
                # A base that is still generic answers with the variable itself.
                if argument is not variable:
                    return cls._resolve_type(argument, field_path)

        if variable.__bound__:
            return cls._resolve_type(variable.__bound__, field_path)
        if variable.__constraints__:
            return cls._resolve_type(Union[variable.__constraints__], field_path)

        logger.debug("TypeVar '%s' in %s is unparameterized; accepting any value",
                     variable, field_path or cls.__name__)
        return Any

    @classmethod
    def _resolve_type(cls, type_hint: Any, field_path: str = "") -> Any:
        """Resolve forward references and type variables to actual types.

        Args:
            type_hint (Any): The type hint to resolve, potentially a string or `ForwardRef`.
            field_path (str): Optional description of the field being resolved, used in errors.

        Returns:
            Any: The resolved type.

        Raises:
            TypeError: If the type hint cannot be resolved.

        Notes:
            - Results are cached per class, so a name is always resolved in the context of
              the class that declared it.
            - Parameterized generics are returned unchanged; `_check_type` walks their
              arguments and resolves each of them in turn.
        """
        from typing import ForwardRef, TypeVar, get_args

        cache = cls._type_cache
        # One lookup rather than a membership test followed by a read: nothing ever removes
        # from this cache, so a concurrent write can only add the value we would compute.
        cached = cache.get(type_hint, _MISSING)
        if cached is not _MISSING:
            return cached
        try:
            if isinstance(type_hint, (ForwardRef, str)):
                type_name = type_hint.__forward_arg__ if isinstance(type_hint, ForwardRef) else type_hint
                resolved = cls._lookup_type_name(type_name, field_path)
                if hasattr(resolved, '_fields') and resolved is not cls:
                    # Warm the target's own cache in its own context, not in ours.
                    for field, field_type in resolved._fields.items():
                        try:
                            resolved._resolve_type(field_type, field_path=f"{resolved.__name__}.{field}")
                        except TypeError:
                            logger.debug("Deferred resolution of '%s.%s'", resolved.__name__, field)
                cache[type_hint] = resolved
                return resolved

            if isinstance(type_hint, TypeVar):
                resolved = cls._resolve_type_variable(type_hint, field_path)
                cache[type_hint] = resolved
                return resolved

            cache[type_hint] = type_hint
            return type_hint
        except TypeError:
            raise
        except Exception as e:
            logger.error("Failed to resolve type hint %s: %s", type_hint, str(e))
            raise ResolutionError(f"Type resolution failed for {type_hint} in {field_path or cls.__name__}: {str(e)}")
    def __hash__(self) -> int:
        """Return a hash consistent with `__eq__`.

        Returns:
            int: A hash derived from the concrete class and the entity name.

        Notes:
            - Defining `__eq__` without this made every entity unhashable, so entities could
              not be put in a set or used as a dictionary key.
            - Only the class and the name take part. Equal entities therefore always hash
              equal, as the data model requires, while two entities sharing a name simply
              collide and are separated by `__eq__`.
            - Entities are mutable. Changing `name` while the entity sits in a set or is used
              as a key makes it unreachable, exactly as for any mutable key.
        """
        return hash((type(self), self.name))
    def __setattr__(self, key: str, value: Any) -> None:
        """Set an attribute with type validation.

        Args:
            key (str): The name of the attribute to set.
            value (Any): The value to assign.

        Raises:
            ValueError: If the key is not in the entity's fields (except for 'name' and 'isactive').
            TypeError: If the value does not match the annotated type.

        Notes:
            - Assigning a nested entity records this entity as its owner, so mutating the
              nested entity later invalidates the cached serialization of both.
        """
        internal_attrs = {"name", "isactive", "_use_cache", "_cached_to_dict", "_container"}
        if key in internal_attrs or key.startswith('_'):
            super().__setattr__(key, value)
        elif key in self._fields:
            expected_type = self._resolve_type(self._fields[key])
            self._validate_type(key, value, expected_type)
            super().__setattr__(key, value)
            if isinstance(value, Serializable):
                value._adopt(self)
            self._invalidate_cache()
            logger.debug("Set attribute '%s' of %s", key, self.__class__.__name__)
        else:
            raise UnknownAttributeError(f"Unknown attribute '{key}' for {self.__class__.__name__}")


def cache_statistics() -> Dict[str, int]:
    """Report what the serialization cache is holding, right now.

    Returns:
        Dict[str, int]: `objects` -- how many live objects have caching enabled; `populated`
            -- how many of them currently hold a mapping; `entries` -- the total number of
            keys across those mappings, which is what grows with the model.

    Notes:
        - Computed on demand from the registry invalidation already keeps, so nothing is
          counted while the framework runs and the hot paths stay as they were measured.
        - Counters for how often invalidation runs, or how long serialization takes, are
          deliberately **not** maintained here. Both would put an unconditional increment into
          paths that were just measured down to 39 µs and 7.4 µs, to serve a question most
          applications never ask. An application that does ask can wrap `to_dict` on its own
          classes, or read request timings from `RequestMetrics`, which costs nothing until it
          is registered.
    """
    populated = 0
    entries = 0
    for obj in list(_CACHING_OBJECTS.values()):
        cached = obj.__dict__.get('_cached_to_dict')
        if cached is not None:
            populated += 1
            entries += len(cached)
    return {"objects": len(_CACHING_OBJECTS), "populated": populated, "entries": entries}
