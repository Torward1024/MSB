# base/baseentity.py
from abc import ABC
from typing import Any, Dict, List, Union

from .serializable import (CYCLIC_REFERENCE, EntityMeta, SCHEMA_FIELD,
                           Serializable, _INTERNAL)
from ..errors import (NotFoundError,
                      ResolutionError,
                      TypeValidationError,
                      UnknownAttributeError)
from ..utils.logging_setup import logger

__all__ = ["BaseEntity", "EntityMeta", "Serializable", "CYCLIC_REFERENCE"]

class BaseEntity(Serializable):
    """A single object addressed by its attributes.

    Adds the attribute-oriented surface on top of `Serializable`: reading and writing
    annotated attributes by name, dictionary-style access to them, and equality over their
    values.

    Notes:
        - `get`, `set`, `clear` and the item operators address *attributes* here. The
          container spells the same ideas over its *items*, which is why the two classes are
          siblings rather than parent and child.

    Examples:
        >>> class NestedEntity(BaseEntity):
        ...     value: int
        >>> class MyEntity(BaseEntity):
        ...     nested: NestedEntity
        >>> entity = MyEntity(name="test", nested=NestedEntity(name="inner", value=42))
        >>> entity.to_dict()["nested"]["value"]
        42
    """

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
            if key not in self._fields:
                raise UnknownAttributeError(f"Unknown attribute '{key}' for {self.__class__.__name__}")
            if key in _INTERNAL:
                # `__setattr__` sets these without checking, since the framework writes them
                # itself; a caller naming one through `set` still has to mean it.
                self._validate_type(key, value, self._fields.get(key))
            setattr(self, key, value)          # which validates everything else
        self._invalidate_cache()
        logger.debug("Updated attributes of %s: %s", self.__class__.__name__, list(params.keys()))
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
            >>> part = Part(name="bolt", price=4.5, weight=0.02)
            >>> part.get("price")
            1000.0
            >>> part.get(["price", "weight"])
            {'price': 4.5, 'weight': 0.02}
            >>> if_obj.get()
            {'name': 'bolt', 'isactive': True, 'price': 4.5, 'weight': 0.02, 'tags': []}
        """
        if key is None:
            result = {k: getattr(self, k) for k in self._fields if not k.startswith('_') and hasattr(self, k)}
            logger.debug("Retrieved all public attributes from %s: %s", self.__class__.__name__, result)
            return result
        elif isinstance(key, str):
            if key not in self._fields:
                logger.error("Attribute '%s' not found in %s", key, self.__class__.__name__)
                raise NotFoundError(f"Attribute '{key}' not found in {self.__class__.__name__}")
            value = getattr(self, key) if hasattr(self, key) else None
            logger.debug("Retrieved attribute '%s' from %s: %s", key, self.__class__.__name__, value)
            return value
        elif isinstance(key, list):
            invalid_keys = [k for k in key if k not in self._fields]
            if invalid_keys:
                logger.error("Attributes %s not found in %s", invalid_keys, self.__class__.__name__)
                raise NotFoundError(f"Attributes {invalid_keys} not found in {self.__class__.__name__}")
            result = {k: getattr(self, k) if hasattr(self, k) else None for k in key}
            logger.debug("Retrieved attributes %s from %s: %s", key, self.__class__.__name__, result)
            return result
        
        raise TypeValidationError(f"Argument 'key' must be str, list of str, or None, got {type(key)}")
    def clone(self) -> 'BaseEntity':
        """Create a deep copy of the entity.

        Returns:
            BaseEntity: A new instance of the same class with identical attributes.
        """
        return self.__class__.from_dict(self.to_dict())
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

        data = cls._apply_migration(data)

        resolved = cls._resolved_fields()
        kwargs = {}
        for key, value in data.items():
            if key in ("name", "isactive"):
                continue
            if key not in resolved:
                raise UnknownAttributeError(f"Unknown attribute '{key}' for {cls.__name__}")
            expected_type = resolved[key]
            if isinstance(expected_type, str):
                from inspect import getmodule
                module = getmodule(cls)
                expected_type = getattr(module, expected_type, None) if module else globals().get(expected_type)
                if expected_type is None:
                    raise ResolutionError(f"Cannot resolve forward reference '{cls._fields[key]}' for attribute '{key}'")
            kwargs[key] = cls._deserialize_value(value, expected_type, f"{cls.__name__}.{key}",
                                                 cls.DISCRIMINATORS.get(key))
        return cls(name=data.get("name"), isactive=data.get("isactive", True), **kwargs)
    def reset_attributes(self) -> None:
        """Set every public attribute to None, releasing whatever it referred to.

        Notes:
            - 'name' and 'isactive' are kept, and so is every underscore-prefixed field:
              those hold framework state such as the shared type cache, and nulling them
              on the instance would shadow the class-level value.
            - The object stays usable: this empties it rather than discarding it.
            - Named for what it does, because `clear` meant three different things across the
              framework. `BaseContainer.remove_all` drops items and `Super.release` drops
              references; none of the three is a special case of another.

        Examples:
            >>> part.reset_attributes()
            >>> part.price is None
            True
        """
        for key in self._fields:
            if key in ("name", "isactive") or key.startswith('_'):
                continue
            if hasattr(self, key):
                super().__setattr__(key, None)
        self._invalidate_cache()

    def clear(self) -> None:
        """Deprecated. Use `reset_attributes()`.

        Notes:
            - Deprecated in 1.9.0, removed in 2.0. Behaves exactly as it did.
        """
        import warnings

        warnings.warn("BaseEntity.clear is deprecated; use reset_attributes()",
                      DeprecationWarning, stacklevel=2)
        self.reset_attributes()
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
            raise NotFoundError(f"Attribute '{key}' not found in {self.__class__.__name__}")
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
            raise NotFoundError(f"Attribute '{key}' not found in {self.__class__.__name__}")
        expected_type = self._resolve_type(self._fields[key])
        self._validate_type(key, value, expected_type)
        setattr(self, key, value)
        self._invalidate_cache()
        logger.debug("Set attribute '%s' of %s", key, self.__class__.__name__)
    def __eq__(self, other: Any) -> bool:
        """Compare two entities for equality based on their attributes and state.

        Args:
            other (Any): The object to compare with.

        Returns:
            bool: True if the entities are equal, False otherwise.

        Notes:
            - Only public attributes take part: underscore-prefixed fields hold framework
              state such as the cached serialization, which says nothing about equality.
        """
        if not isinstance(other, self.__class__):
            return False
        if self.name != other.name or self.isactive != other.isactive:
            return False
        # The same fields `to_dict` writes, worked out per class rather than per comparison,
        # and read directly: `get` validates a key that came from the class's own table.
        return all(getattr(self, key, None) == getattr(other, key, None)
                   for key in self.__class__._written_fields()
                   if key not in ("name", "isactive"))
    # Defining __eq__ sets __hash__ to None unless it is restated; the shared
    # implementation stays valid, so take it from the base explicitly.
    __hash__ = Serializable.__hash__

    def __contains__(self, key: str) -> bool:
        """Check if an attribute exists in the entity.

        Args:
            key (str): The name of the attribute to check.

        Returns:
            bool: True if the attribute exists and is set, False otherwise.
        """
        return key in self._fields and hasattr(self, key)
    def __repr__(self) -> str:
        """Return a string representation of the BaseEntity.

        Returns:
            str: A formatted string with the class name, name (if set), activation status, and attributes.
        """
        attrs = [f"name={self.name!r}" if self.name else ""]
        attrs.append(f"isactive={self.isactive}")
        for k in self._fields:
            if k.startswith('_'):
                continue
            if k not in ('name', 'isactive') and hasattr(self, k):
                value = getattr(self, k)
                if isinstance(value, BaseEntity):
                    attrs.append(f"{k}=<{value.__class__.__name__} at {id(value)}>")
                else:
                    attrs.append(f"{k}={value!r}")
        return f"{self.__class__.__name__}({', '.join(attr for attr in attrs if attr)})"