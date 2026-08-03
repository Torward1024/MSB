# base/baseentity.py
from abc import ABC
from typing import Any, Dict, List, Union

from .serializable import CYCLIC_REFERENCE, EntityMeta, Serializable
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
            if key in self._fields:
                self._validate_type(key, value, self._fields.get(key))
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown attribute '{key}' for {self.__class__.__name__}")
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
            logger.debug("Retrieved all public attributes from %s: %s", self.__class__.__name__, result)
            return result
        elif isinstance(key, str):
            if key not in self._fields:
                logger.error("Attribute '%s' not found in %s", key, self.__class__.__name__)
                raise KeyError(f"Attribute '{key}' not found in {self.__class__.__name__}")
            value = getattr(self, key) if hasattr(self, key) else None
            logger.debug("Retrieved attribute '%s' from %s: %s", key, self.__class__.__name__, value)
            return value
        elif isinstance(key, list):
            invalid_keys = [k for k in key if k not in self._fields]
            if invalid_keys:
                logger.error("Attributes %s not found in %s", invalid_keys, self.__class__.__name__)
                raise KeyError(f"Attributes {invalid_keys} not found in {self.__class__.__name__}")
            result = {k: getattr(self, k) if hasattr(self, k) else None for k in key}
            logger.debug("Retrieved attributes %s from %s: %s", key, self.__class__.__name__, result)
            return result
        
        raise TypeError(f"Argument 'key' must be str, list of str, or None, got {type(key)}")
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
                type_cls = cls._resolve_entity_type(value["type"], expected_type)
                if type_cls is not None:
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
    def clear(self) -> None:
        """Clear all public attributes to release references.

        Notes:
            - 'name' and 'isactive' are kept, and so is every underscore-prefixed field:
              those hold framework state such as the shared type cache, and nulling them
              on the instance would shadow the class-level value.
        """
        for key in self._fields:
            if key in ("name", "isactive") or key.startswith('_'):
                continue
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
        return (self.name == other.name and
                self.isactive == other.isactive and
                all(self.get(k) == other.get(k) for k in self._fields
                    if k not in ("name", "isactive") and not k.startswith('_')))
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