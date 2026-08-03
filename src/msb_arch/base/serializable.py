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
from ..utils.logging_setup import logger

CYCLIC_REFERENCE = "<cyclic reference>"

# Identities already serialized during the current to_dict traversal. Kept here rather than
# in a parameter so that `to_dict()` keeps the signature subclasses override, and so that
# concurrent serializations do not share marks.
_TRAVERSAL: ContextVar = ContextVar("msb_arch_to_dict_seen", default=None)

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
        entry = mcs._entity_registry.get(type_name)
        if not entry:
            return []
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
    """
    name: str
    isactive: bool
    _type_cache: Dict[Any, Any] = {}
    _cached_to_dict: Dict[str, Any]
    _use_cache: bool

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
            raise ValueError(f"Unknown attributes provided for {self.__class__.__name__}: {unknown_attrs}")
        
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
    def _invalidate_cache(self) -> None:
        """Drop the cached serialization of this entity and of everything that owns it.

        Notes:
            - A container serializes its items, so a mutated item makes every ancestor
              stale. Invalidation therefore walks up the ownership graph rather than down
              into the children, which is both correct and cheap.
            - Every owner is visited, not just one: an item added with `copy_items=False`
              belongs to each container that holds it, and all of them go stale together.
            - The walk is guarded against a cycle in the ownership graph.
        """
        if not self.__dict__.get('_parents'):
            # Overwhelmingly the common case: nothing owns this entity, so there is no graph
            # to walk and no reason to allocate one.
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
            raise TypeError(f"Attribute '{key}' cannot be None")
        if value is None:
            return

        self._check_type(key, value, expected_type, f"Attribute '{key}'")
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

        # Unwrap Annotated[X, ...] down to X.
        while hasattr(resolved_type, '__metadata__'):
            resolved_type = cls._resolve_type(resolved_type.__origin__)

        if resolved_type is Any:
            return
        if resolved_type is None or resolved_type is type(None):
            raise TypeError(f"{subject} must be None, got {type(value)}")

        origin = get_origin(resolved_type)
        type_args = get_args(resolved_type)

        if origin is None:
            if isinstance(resolved_type, (type, tuple)):
                if not isinstance(value, resolved_type):
                    raise TypeError(f"{subject} must be of type {resolved_type}, got {type(value)}")
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
            raise TypeError(f"{subject} does not match any type in {resolved_type}, got {type(value)}")

        if origin is Literal:
            for literal_value in type_args:
                if type(value) is type(literal_value) and value == literal_value:
                    return
            raise TypeError(f"{subject} must be one of {list(type_args)}, got {value!r}")

        if origin is type:
            if not isinstance(value, type):
                raise TypeError(f"{subject} must be a class, got {type(value)}")
            if type_args:
                bound = cls._resolve_type(type_args[0])
                if isinstance(bound, type) and not issubclass(value, bound):
                    raise TypeError(f"{subject} must be a subclass of {bound}, got {value}")
            return

        if origin is AbcCallable:
            if not callable(value):
                raise TypeError(f"{subject} must be callable, got {type(value)}")
            return

        if origin is dict or (isinstance(origin, type) and issubclass(origin, AbcMapping)):
            if not isinstance(value, origin):
                raise TypeError(f"{subject} must be a {origin.__name__}, got {type(value)}")
            if origin is dict and len(type_args) == 2:
                cls._check_mapping(key, value, type_args[0], type_args[1], subject)
            return

        if origin in (list, set, frozenset):
            if not isinstance(value, origin):
                raise TypeError(f"{subject} must be a {origin.__name__}, got {type(value)}")
            if type_args:
                cls._check_elements(key, value, type_args[0], f"Item in {origin.__name__} '{key}'")
            return

        if origin is tuple:
            if not isinstance(value, tuple):
                raise TypeError(f"{subject} must be a tuple, got {type(value)}")
            cls._check_tuple(key, value, type_args, subject)
            return

        # Any other generic alias (user generics, abstract collections): check the origin only.
        if isinstance(origin, type) and not isinstance(value, origin):
            raise TypeError(f"{subject} must be of type {resolved_type}, got {type(value)}")
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
            raise TypeError(f"{subject} must have {len(type_args)} items, got {len(value)}")
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
            data = {"name": self.name, "isactive": self.isactive, "type": self.__class__.__name__}
            for key in self._fields:
                if key.startswith('_'):
                    continue
                if not hasattr(self, key):
                    continue
                value = getattr(self, key)
                if isinstance(value, Serializable):
                    data[key] = CYCLIC_REFERENCE if id(value) in seen else value.to_dict()
                else:
                    data[key] = value
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

        raise TypeError(
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
                raise TypeError(
                    f"Ambiguous type name '{type_name}' for {field_path or cls.__name__}: "
                    f"{sorted(f'{c.__module__}.{c.__name__}' for c in candidates)}"
                )
        if resolved is None:
            raise TypeError(f"Cannot resolve type name '{type_name}' for {field_path or cls.__name__}")
        return resolved
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
        if type_hint in cache:
            return cache[type_hint]
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
                args = get_args(cls.__orig_bases__[0]) if getattr(cls, '__orig_bases__', None) else ()
                if args:
                    resolved = cls._resolve_type(args[0], field_path)
                elif type_hint.__bound__:
                    resolved = cls._resolve_type(type_hint.__bound__, field_path)
                elif type_hint.__constraints__:
                    resolved = cls._resolve_type(type_hint.__constraints__[0], field_path)
                else:
                    raise TypeError(f"Cannot resolve TypeVar '{type_hint}' in {cls.__name__}")
                cache[type_hint] = resolved
                return resolved

            cache[type_hint] = type_hint
            return type_hint
        except TypeError:
            raise
        except Exception as e:
            logger.error("Failed to resolve type hint %s: %s", type_hint, str(e))
            raise TypeError(f"Type resolution failed for {type_hint} in {field_path or cls.__name__}: {str(e)}")
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
            raise ValueError(f"Unknown attribute '{key}' for {self.__class__.__name__}")
