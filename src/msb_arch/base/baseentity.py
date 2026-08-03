# base/baseentity.py
from abc import ABC, ABCMeta
from collections.abc import Callable as AbcCallable, Mapping as AbcMapping
from types import UnionType
from typing import (Dict,
                    Union,
                    List,
                    Any,
                    Literal,
                    get_origin,
                    get_args)
from ..utils.logging_setup import logger

class EntityMeta(ABCMeta):
    """Metaclass for BaseEntity to handle type annotations and enforce attribute validation.

    Automatically collects type annotations from the subclass and configures the entity to validate
    attributes against these types during initialization and updates.

    Attributes:
        _fields (Dict[str, type]): Dictionary of annotated attribute names and their expected types.
    """
    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)
        annotations = {}
        for base in reversed(bases):
            if hasattr(base, '_fields'):
                annotations.update(base._fields)
            annotations.update(getattr(base, '__annotations__', {}))
        annotations.update(attrs.get('__annotations__', {}))
        new_class._fields = annotations
        return new_class

class BaseEntity(ABC, metaclass=EntityMeta):
    """Abstract base class for entities with attribute management, type validation, and universal serialization.

    Provides a foundation for base entity classes in the MSB system. Defines common functionality
    for managing attributes with type checking, an active/inactive state, and universal serialization methods,
    including support for nested entities.

    Attributes:
        name (str): An identifier for the entity.
        isactive (bool): Indicates whether the entity is active or inactive.
        _fields (Dict[str, type]): Class-level mapping of attribute names to their expected types (from annotations).

    Notes:
        - Logging is integrated via `utils.logging_setup.logger` to track initialization and state changes.
        - This is an abstract base class and cannot be instantiated directly; it must be subclassed.
        - Attributes are validated against type annotations defined in `__annotations__`.
        - Serialization methods `to_dict` and `from_dict` automatically handle all annotated attributes, including nested entities.

    Examples:
        >>> class NestedEntity(BaseEntity):
        ...     value: int
        >>> class MyEntity(BaseEntity):
        ...     name: str
        ...     nested: NestedEntity
        >>> nested = NestedEntity(value=42)
        >>> entity = MyEntity(name="test", isactive=True, nested=nested)
        >>> print(entity.to_dict())
        {'name': 'test', 'isactive': True, 'nested': {'name': None, 'isactive': True, 'value': 42}}
        >>> new_entity = MyEntity.from_dict({'name': 'test', 'isactive': True, 'nested': {'name': None, 'isactive': True, 'value': 42}})
        >>> print(new_entity)
        MyEntity(name='test', isactive=True, nested=NestedEntity(isactive=True, value=42))
    """
    name: str
    isactive: bool
    _type_cache: Dict[Any, Any] = {}
    _cached_to_dict: Dict[str, Any]
    _use_cache: bool

    def __init__(self, *, name: str, isactive: bool = True, use_cache: bool = False, **kwargs):
        """Initialize the BaseEntity with a name, activation status, and optional typed attributes.

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

        unknown_attrs = set(kwargs.keys()) - set(self._fields.keys())
        if unknown_attrs:
            raise ValueError(f"Unknown attributes provided for {self.__class__.__name__}: {unknown_attrs}")
        
        logger.debug(f"Initialized {self.__class__.__name__} instance with name={name}, isactive={isactive}")
    
    def _invalidate_cache(self) -> None:
        """Invalidate the cache of the entity."""
        if self._use_cache and hasattr(self, '_cached_to_dict'):
            self._cached_to_dict = None

    def _validate_type(self, key: str, value: Any, expected_type: Any) -> None:
        """Validate that a value matches the expected type.

        Args:
            key (str): The attribute name being validated.
            value (Any): The value to check.
            expected_type (Any): The expected type from type annotations.

        Raises:
            TypeError: If the value does not match the expected type, or if 'name' or 'value' is None.

        Notes:
            - `None` is accepted for every attribute except 'name' and 'value', because unset
              annotated attributes are initialized to None by `__init__`.
            - The structural check is delegated to `_check_type`, which walks nested generics.
        """
        if key in ('name', 'value') and value is None:
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


    def set(self, params: Dict[str, Any]) -> None:
        """Set entity attributes from a dictionary with type validation.

        Args:
            params (dict): Dictionary with attribute names and values to update.

        Raises:
            TypeError: If an attribute value does not match its annotated type.
            ValueError: If an attribute is not defined in the class annotations.

        Notes:
            - Only attributes defined in `__annotations__` can be set.
            - Logs an info message with updated attributes.
        """

        for key, value in params.items():
            if key in self._fields:
                self._validate_type(key, value, self._fields.get(key))
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown attribute '{key}' for {self.__class__.__name__}")
        self._invalidate_cache()
        logger.debug(f"Updated attributes of {self.__class__.__name__}: {list(params.keys())}")

    def get(self, key: Union[str, List[str], None] = None) -> Union[Any, Dict[str, Any]]:
        """Retrieve one or more attributes of the entity.

        Args:
            key (Union[str, List[str], None], optional): The name of a single attribute, a list of attribute
                names, or None. If a string, returns the attribute's value. If a list of strings, returns a
                dictionary with the specified attributes. If None, returns a dictionary of all public attributes.
                Defaults to None.

        Returns:
            Union[Any, Dict[str, Any]]: The value of the specified attribute if `key` is a string,
                a dictionary of requested attributes if `key` is a list, or a dictionary of all public attributes
                if `key` is None.

        Raises:
            KeyError: If any specified key is not found in the entity's annotated fields.

        Examples:
            >>> if_obj = IF(name="IF1", frequency=1000.0, bandwidth=16.0)
            >>> if_obj.get("frequency")
            1000.0
            >>> if_obj.get(["frequency", "bandwidth"])
            {'frequency': 1000.0, 'bandwidth': 16.0}
            >>> if_obj.get()
            {'name': 'IF1', 'isactive': True, 'frequency': 1000.0, 'bandwidth': 16.0, 'polarizations': []}
        """
        if key is None:
            result = {k: getattr(self, k) for k in self._fields if not k.startswith('_') and hasattr(self, k)}
            logger.debug(f"Retrieved all public attributes from {self.__class__.__name__}: {result}")
            return result
        elif isinstance(key, str):
            if key not in self._fields:
                logger.error(f"Attribute '{key}' not found in {self.__class__.__name__}")
                raise KeyError(f"Attribute '{key}' not found in {self.__class__.__name__}")
            value = getattr(self, key) if hasattr(self, key) else None
            logger.debug(f"Retrieved attribute '{key}' from {self.__class__.__name__}: {value}")
            return value
        elif isinstance(key, list):
            invalid_keys = [k for k in key if k not in self._fields]
            if invalid_keys:
                logger.error(f"Attributes {invalid_keys} not found in {self.__class__.__name__}")
                raise KeyError(f"Attributes {invalid_keys} not found in {self.__class__.__name__}")
            result = {k: getattr(self, k) if hasattr(self, k) else None for k in key}
            logger.debug(f"Retrieved attributes {key} from {self.__class__.__name__}: {result}")
            return result
        
        raise TypeError(f"Argument 'key' must be str, list of str, or None, got {type(key)}")

    def activate(self) -> None:
        """Activate the entity, setting its status to active.

        Notes:
            - Logs an info message indicating the entity has been activated.
        """
        self.isactive = True
        self._invalidate_cache()
        logger.debug(f"Activated {self.__class__.__name__} instance")

    def deactivate(self) -> None:
        """Deactivate the entity, setting its status to inactive.

        Notes:
            - Logs an info message indicating the entity has been deactivated.
        """
        self.isactive = False
        self._invalidate_cache()
        logger.debug(f"Deactivated {self.__class__.__name__} instance")
    
    def has_attribute(self, key: str) -> bool:
        """Check if the entity has a specific attribute.

        Args:
            key (str): The name of the attribute to check.

        Returns:
            bool: True if the attribute exists in the entity's fields and is set, False otherwise.
        """
        return key in self._fields and hasattr(self, key)
    
    def clone(self) -> 'BaseEntity':
        """Create a deep copy of the entity.

        Returns:
            BaseEntity: A new instance of the same class with identical attributes.
        """
        return self.__class__.from_dict(self.to_dict())

    def to_dict(self) -> dict:
        """Convert the entity to a dictionary for serialization.

        Automatically serializes the entity's state, including all annotated attributes,
        with nested entities recursively serialized. Always includes a 'type' field with the class name.

        Returns:
            dict: A dictionary containing the entity's serialized data.
        """
        if self._use_cache and self._cached_to_dict is not None:
            valid_cache = True
            for key in self._fields:
                if key.startswith('_'):
                    continue
                if hasattr(self, key):
                    value = getattr(self, key)
                    if isinstance(value, BaseEntity):
                        cached_nested = self._cached_to_dict.get(key)
                        current_nested = value.to_dict()
                        if cached_nested != current_nested:
                            valid_cache = False
                            break
            if valid_cache:
                return self._cached_to_dict
        
        seen = set()
        data = {"name": self.name, "isactive": self.isactive, "type": self.__class__.__name__}
        seen.add(id(self))
        for key in self._fields:
            if key.startswith('_'):
                continue
            if hasattr(self, key):
                value = getattr(self, key)
                if isinstance(value, BaseEntity):
                    if id(value) in seen:
                        data[key] = "<cyclic reference>"
                    else:
                        data[key] = value.to_dict()
                        seen.add(id(value))
                else:
                    data[key] = value
        
        if self._use_cache:
            self._cached_to_dict = data
            return self._cached_to_dict
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'BaseEntity':
        """Create an entity instance from a dictionary.

        Automatically reconstructs an entity instance from serialized data, ignoring the 'type' field,
        and setting its name, activation status, and annotated attributes, including nested entities.

        Args:
            data (dict): Dictionary containing the entity's serialized data, typically from `to_dict`.

        Returns:
            BaseEntity: A new instance of the subclass initialized with the dictionary data.

        Raises:
            TypeError: If a value in the dictionary does not match the annotated type.
            ValueError: If an unknown attribute is provided in the dictionary.
        """
        data = data.copy()
        data.pop("type", None)
        kwargs = {}
        for key, value in data.items():
            if key in ("name", "isactive"):
                continue
            if key not in cls._fields:
                raise ValueError(f"Unknown attribute '{key}' for {cls.__name__}")
            expected_type = cls._resolve_type(cls._fields[key])
            if isinstance(value, dict) and "type" in value:
                type_name = value["type"]
                type_cls = None
                if type_name == cls.__name__:
                    type_cls = cls
                else:
                    type_cls = globals().get(type_name)
                if type_cls and issubclass(type_cls, BaseEntity):
                    kwargs[key] = type_cls.from_dict(value)
                    continue
            if isinstance(expected_type, str):
                from inspect import getmodule
                module = getmodule(cls)
                expected_type = getattr(module, expected_type, None) if module else globals().get(expected_type)
                if expected_type is None:
                    raise TypeError(f"Cannot resolve forward reference '{cls._fields[key]}' for attribute '{key}'")
            if isinstance(expected_type, type) and issubclass(expected_type, BaseEntity) and isinstance(value, dict):
                kwargs[key] = expected_type.from_dict(value)
            else:
                kwargs[key] = value
        return cls(name=data.get("name"), isactive=data.get("isactive", True), **kwargs)
    
    @classmethod
    def _resolve_type(cls, type_hint):
        """Resolve forward references to actual types.

        Args:
            type_hint: The type hint to resolve, potentially a string (forward reference) or a type.

        Returns:
            The resolved type, or raises an error if unresolvable.

        Raises:
            TypeError: If the type hint cannot be resolved.
        """
        from typing import ForwardRef, TypeVar, get_args

        if type_hint in cls._type_cache:
            return cls._type_cache[type_hint]
        try:
            if isinstance(type_hint, ForwardRef):
                type_name = type_hint.__forward_arg__
                resolved = globals().get(type_name)
                if resolved is None:
                    from inspect import getmodule
                    module = getmodule(cls)
                    resolved = getattr(module, type_name, None) if module else None
                    if resolved is None:
                        raise TypeError(f"Cannot resolve forward reference '{type_name}' in {cls.__name__}")
                if hasattr(resolved, '_fields'):
                    for field, field_type in resolved._fields.items():
                        cls._resolve_type(field_type)
                cls._type_cache[type_hint] = resolved
                return resolved

            if isinstance(type_hint, str):
                resolved = globals().get(type_hint)
                if resolved is None:
                    from inspect import getmodule
                    module = getmodule(cls)
                    resolved = getattr(module, type_hint, None) if module else None
                    if resolved is None:
                        raise TypeError(f"Cannot resolve type hint '{type_hint}' in {cls.__name__}")
                cls._type_cache[type_hint] = resolved
                return resolved

            elif isinstance(type_hint, TypeVar):
                if hasattr(cls, '__orig_bases__'):
                    for base in cls.__orig_bases__:
                        args = get_args(base)
                        if args and isinstance(type_hint, TypeVar):
                            if len(args) > 0:
                                resolved = cls._resolve_type(args[0])
                                cls._type_cache[type_hint] = resolved
                                return resolved
                            bound = type_hint.__bound__
                            if bound:
                                resolved = cls._resolve_type(bound)
                                cls._type_cache[type_hint] = resolved
                                return resolved
                            constraints = type_hint.__constraints__
                            if constraints:
                                resolved = cls._resolve_type(constraints[0])
                                cls._type_cache[type_hint] = resolved
                                return resolved
                raise TypeError(f"Cannot resolve TypeVar '{type_hint}' in {cls.__name__}")

            elif hasattr(type_hint, "__origin__"):
                cls._type_cache[type_hint] = type_hint
                return type_hint

            cls._type_cache[type_hint] = type_hint
            return type_hint
        except Exception as e:
            logger.error(f"Failed to resolve type hint {type_hint}: {str(e)}")
            raise TypeError(f"Type resolution failed for {type_hint} in {cls.__name__}: {str(e)}")
    
    def clear(self) -> None:
        """Clear all non-internal attributes to release references."""
        for key in self._fields:
            if key not in {"name", "isactive", "_use_cache", "_cached_to_dict"}:
                if hasattr(self, key):
                    super().__setattr__(key, None)
        self._invalidate_cache()

    def __getitem__(self, key: str) -> Any:
        """Access an attribute using dictionary-like syntax.

        Args:
            key (str): The name of the attribute to retrieve.

        Returns:
            Any: The value of the specified attribute.

        Raises:
            KeyError: If the key is not found in the entity's fields.
        """
        if key not in self._fields:
            raise KeyError(f"Attribute '{key}' not found in {self.__class__.__name__}")
        return getattr(self, key) if hasattr(self, key) else None

    def __setitem__(self, key: str, value: Any) -> None:
        """Set an attribute using dictionary-like syntax.

        Args:
            key (str): The name of the attribute to set.
            value (Any): The value to assign.

        Raises:
            KeyError: If the key is not found in the entity's fields.
            TypeError: If the value does not match the annotated type.
        """
        if key not in self._fields:
            raise KeyError(f"Attribute '{key}' not found in {self.__class__.__name__}")
        expected_type = self._resolve_type(self._fields[key])
        self._validate_type(key, value, expected_type)
        setattr(self, key, value)
        self._invalidate_cache()
        logger.debug(f"Set attribute '{key}' of {self.__class__.__name__}")

    def __eq__(self, other: Any) -> bool:
        """Compare two entities for equality based on their attributes and state.

        Args:
            other (Any): The object to compare with.

        Returns:
            bool: True if the entities are equal, False otherwise.
        """
        if not isinstance(other, self.__class__):
            return False
        return (self.name == other.name and
                self.isactive == other.isactive and
                all(self.get(k) == other.get(k) for k in self._fields if k not in ("name", "isactive")))

    def __contains__(self, key: str) -> bool:
        """Check if an attribute exists in the entity.

        Args:
            key (str): The name of the attribute to check.

        Returns:
            bool: True if the attribute exists and is set, False otherwise.
        """
        return key in self._fields and hasattr(self, key)
    
    def __setattr__(self, key: str, value: Any) -> None:
        """Set an attribute with type validation.

        Args:
            key (str): The name of the attribute to set.
            value (Any): The value to assign.

        Raises:
            ValueError: If the key is not in the entity's fields (except for 'name' and 'isactive').
            TypeError: If the value does not match the annotated type.
        """
        internal_attrs = {"name", "isactive", "_use_cache", "_cached_to_dict", "_container"}
        if key in internal_attrs or key.startswith('_'):
            super().__setattr__(key, value)
        elif key in self._fields:
            expected_type = self._resolve_type(self._fields[key])
            self._validate_type(key, value, expected_type)
            super().__setattr__(key, value)
            self._invalidate_cache()
            logger.debug(f"Set attribute '{key}' of {self.__class__.__name__}")
        else:
            raise ValueError(f"Unknown attribute '{key}' for {self.__class__.__name__}")

    def __repr__(self) -> str:
        """Return a string representation of the BaseEntity.

        Returns:
            str: A formatted string with the class name, name (if set), activation status, and attributes.
        """
        attrs = [f"name={self.name!r}" if self.name else ""]
        attrs.append(f"isactive={self.isactive}")
        for k in self._fields:
            if k not in ('name', 'isactive') and hasattr(self, k):
                value = getattr(self, k)
                if isinstance(value, BaseEntity):
                    attrs.append(f"{k}=<{value.__class__.__name__} at {id(value)}>")
                else:
                    attrs.append(f"{k}={value!r}")
        return f"{self.__class__.__name__}({', '.join(attr for attr in attrs if attr)})"
    
    def __del__(self) -> None:
        """Ensure cleanup of references to prevent memory leaks."""
        try:
            self.clear()
        except Exception as e:
            logger.error(f"Error during cleanup of {self.__class__.__name__}: {str(e)}")