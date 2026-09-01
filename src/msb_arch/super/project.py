# super/project.py
from abc import ABC, abstractmethod
from threading import RLock
from typing import Dict, Any, Optional, Type, List, TypeVar
from ..utils.validation import check_non_empty_string
from ..errors import DuplicateNameError, InvariantError, SerializationError, TypeValidationError
from ..utils.logging_setup import logger
from ..base.basecontainer import BaseContainer
from ..base.baseentity import BaseEntity
from ..base.serializable import Serializable
T = TypeVar('T', bound=Serializable)

class Project(Serializable, ABC):
    """A named collection of entities with a factory for creating them.

    Attributes:
        _items (BaseContainer[BaseEntity]): Container of BaseEntity items indexed by their names.
        _item_type (Type[Serializable]): The type of items stored in the container, defaults to
            BaseEntity. A project can hold containers too, since both share Serializable.

    Notes:
        - **A `Serializable`, like an entity and a container.** It was an `ABC` of its own for a
          while, and everything the base layer gained went past it: two equal projects compared
          unequal, `fingerprint` and `revision` were missing, and a rule declared with
          `@invariant` was never checked. Its own surface is unchanged -- `add_item`, `get_item`,
          `create_item` -- and so is the shape of a saved file.
        - It **holds** a container rather than being one, because a project is defined by its
          factory: `create_item` is what an application fills in.
    """
    name: str

    # The version of a saved project's shape. A project is the thing an application writes to
    # a file, so it is the class most worth versioning -- and for a while it was the one that
    # could not be, because the version check lived only on `BaseEntity`.
    #
    # Written only once it is no longer 1, so nothing changes until it has to.
    SCHEMA_VERSION = 1

    # Deliberately unannotated, like `DISCRIMINATORS` on `Serializable`: an annotation here
    # would make each one of `_fields`, and the constructor would then set it to None on every
    # instance -- which turned `isinstance(item, self._item_type)` into a TypeError.
    _item_type = BaseEntity
    _container_types = {}
    # Guards the cache above: two threads creating the first project of a type would
    # otherwise each build a class, and the projects would hold containers of unrelated
    # classes that compare unequal.
    _container_lock = RLock()

    def __init__(self, name: str = "DEFAULT_PROJECT", items: Optional[Dict[str, BaseEntity]] = None):
        """Initialize a Project with a name and an optional dictionary of BaseEntity items.

        Args:
            name (str): The name of the project. Must be a non-empty string. Defaults to "DEFAULT_PROJECT".
            items (Optional[Dict[str, BaseEntity]]): Optional dictionary of BaseEntity items to initialize the project with. Defaults to None.

        Raises:
            ValueError: If the name is not a non-empty string.
        """
        check_non_empty_string(name, "Project name")
        # A rule about a project is usually about what it holds, and what it holds does not
        # exist until three lines further down. Held back over the base constructor and run once
        # the project is whole.
        self.__dict__['_holding_invariants'] = True
        super().__init__(name=name)
        # Set past `__setattr__`: `_items` is framework state, and the container adopts the
        # project as its owner so that an item's address runs through the project.
        object.__setattr__(self, '_items', self._create_container(items=items, name=f"{name}_items"))
        self._items._adopt(self)
        self.__dict__.pop('_holding_invariants', None)
        if self.__class__._invariant_cache:
            self.check_invariants()
        logger.debug("Initialized project '%s' with %s items", name, len(self._items))

    @classmethod
    def _create_container(cls, items: Optional[Dict[str, BaseEntity]] = None, name: str = None) -> BaseContainer:
        """Create a BaseContainer instance with the specified item type.

        Args:
            items (Optional[Dict[str, BaseEntity]]): Optional dictionary of items to initialize the container with. Defaults to None.
            name (str): Optional name for the container. Defaults to None.

        Returns:
            BaseContainer: A new BaseContainer instance typed for the project's item type.

        Notes:
            - The generated container class is cached per item type. Building a fresh class
              on every call leaked one class per project and made containers of two projects
              of the same type unrelated, which broke equality between them.
        """
        item_type = cls._item_type
        with Project._container_lock:
            container_type = Project._container_types.get(item_type)
            if container_type is None:
                class TypedContainer(BaseContainer[item_type]):
                    pass
                container_type = TypedContainer
                Project._container_types[item_type] = container_type
                logger.debug("Created container type for items of type '%s'", item_type.__name__)
        return container_type(items=items, name=name)

    def _rules_hold(self, restore: Optional[Dict[str, Any]] = None) -> None:
        """Check any rule about the project, and put its items back when one refuses.

        Args:
            restore (Optional[Dict[str, Any]]): The items as they were, or None when this class
                declares no rule and taking a snapshot would be paid for nothing.

        Notes:
            - A project's rules are usually about what it holds -- at least one source, no two
              stations at one site -- so every method that changes the contents ends here.
        """
        if not self.__class__._invariant_cache:
            return
        try:
            self.check_invariants()
        except InvariantError:
            if restore is not None:
                self._items.set_items(restore)
            raise

    def _guarded(self) -> Optional[Dict[str, Any]]:
        """Return what to put back if a rule refuses the change, or None when none can."""
        return dict(self._items.get_all()) if self.__class__._invariant_cache else None

    def add_item(self, item: BaseEntity) -> None:
        """Add a BaseEntity item to the project's container.

        Args:
            item (BaseEntity): The item to add.

        Raises:
            TypeError: If the item type does not match the expected type.
            ValueError: If an item with the same name already exists in the project.
        """
        if not isinstance(item, self._item_type):
            raise TypeValidationError(f"Item must be of type {self._item_type.__name__} for project '{self.name}', got {type(item).__name__}")
        if self._items.has_item(item.name):
            raise DuplicateNameError(f"Item with name '{item.name}' already exists in project '{self.name}'")
        guarded = self._guarded()
        self._items.add(item)
        logger.debug("Added item '%s' to project '%s'", item.name, self.name)
        self._rules_hold(guarded)

    @abstractmethod
    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        """Create and add a new BaseEntity item to the project.

        Args:
            item_code (str): The code identifier for the new item. Defaults to "ITEM_DEFAULT".
            isactive (bool): Whether the new item should be active. Defaults to True.
        """
        pass

    def set_item(self, name: str, item: BaseEntity) -> None:
        """Set an item in the project by its name.

        Args:
            name (str): The name to assign to the item.
            item (BaseEntity): The BaseEntity item to set in the project.
        """
        guarded = self._guarded()
        self._items.set_item(name, item)
        logger.info("Set item '%s' in project '%s'", item.name, self.name)
        self._rules_hold(guarded)

    def remove_item(self, name: str) -> None:
        """Remove an item from the project by its name.

        Args:
            name (str): The name of the item to remove from the project.
        """
        guarded = self._guarded()
        self._items.remove(name)
        logger.info("Removed item '%s' from project '%s'", name, self.name)
        self._rules_hold(guarded)
    
    def get_active_items(self) -> List[T]:
        """Retrieve all active items in the container.

        Returns:
            List[T]: A list of items where isactive is True.
        """
        return self._items.get_active_items()

    def get_inactive_items(self) -> List[T]:
        """Retrieve all inactive items in the container.

        Returns:
            List[T]: A list of items where isactive is False.
        """
        return self._items.get_inactive_items()

    def get_item(self, name: str) -> BaseEntity:
        """Retrieve an item from the project by its name.

        Args:
            name (str): The name of the item to retrieve.

        Returns:
            BaseEntity: The BaseEntity item associated with the given name.
        """
        item = self._items.get(name)
        logger.debug("Retrieved item '%s' from project '%s'", name, self.name)
        return item

    def get_items(self) -> List[BaseEntity]:
        """Return every item the project holds.

        Returns:
            List[BaseEntity]: The items, in the order they were added.

        Notes:
            - **The same thing `BaseContainer.get_items` returns**, which it did not until 2.0:
              a project answered with a mapping and a container with a list, so one handler
              written for both walked objects in one case and names in the other, silently. Ask
              `get_all()` for the mapping, exactly as on a container.

        Examples:
            >>> [item.name for item in project.get_items()]
            ['s1', 's2']
        """
        return self._items.get_items()

    def get_all(self) -> Dict[str, BaseEntity]:
        """Return every item the project holds, keyed by name.

        Returns:
            Dict[str, BaseEntity]: The items by name -- what `get_items` used to return.

        Examples:
            >>> sorted(project.get_all())
            ['s1', 's2']
        """
        return self._items.get_all()

    def get_name(self) -> str:
        """Retrieve the project's name.

        Returns:
            str: The name of the project.
        """
        logger.debug("Retrieved name '%s' for project", self.name)
        return self.name

    def set_name(self, name: str) -> None:
        """Set the project's name.

        Args:
            name (str): The new name to assign to the project.

        Raises:
            ValueError: If the name is not a non-empty string.
        """
        check_non_empty_string(name, "Project name")
        old_name = self.name
        self.name = name
        self._items.name = f"{name}_items"
        logger.info("Project name changed from '%s' to '%s'", old_name, name)

    def set_project(self, name: str, items: Dict[str, BaseEntity]) -> None:
        """Set the entire project configuration, replacing name and items.

        Args:
            name (str): The new name for the project.
            items (Dict[str, BaseEntity]): The new dictionary of BaseEntity items to set in the project.

        Raises:
            ValueError: If the name is not a non-empty string.
        """
        check_non_empty_string(name, "Project name")
        old_name = self.name
        old_count = len(self._items)
        self.name = name
        guarded = self._guarded()
        self._items.set_items(items)
        self._items.name = f"{name}_items"
        logger.info("Project updated: name changed from '%s' to '%s', items count changed from %s to %s", old_name, name, old_count, len(self._items))
        self._rules_hold(guarded)

    def get_project(self) -> Dict[str, Any]:
        """Get the entire project configuration as a dictionary.

        Returns:
            Dict[str, Any]: A dictionary with 'name' and 'items' keys representing the project configuration.
        """
        result = {"name": self.name, "items": self._items.to_dict()["items"]}
        logger.debug("Retrieved project configuration for '%s' with %s items", self.name, len(self._items))
        return result
    
    def remove_all(self) -> None:
        """Remove every item from the project's container.

        Notes:
            - The project itself stays: its name, its container and its factory are untouched.
            - Named for what it does, matching `BaseContainer.remove_all`.

        Examples:
            >>> project.remove_all()
            >>> project.get_items()
            []
        """
        guarded = self._guarded()
        self._items.remove_all()
        logger.debug("Removed all items from project '%s'", self.name)
        self._rules_hold(guarded)

    def activate_item(self, name: str) -> None:
        """Activate an item in the project's container by its name.

        Args:
            name (str): The name of the item to activate.

        Raises:
            ValueError: If the item with the specified name does not exist.
        """
        self._items.activate_item(name)
        logger.info("Activated item '%s' in project '%s'", name, self.name)

    def deactivate_item(self, name: str) -> None:
        """Deactivate an item in the project's container by its name.

        Args:
            name (str): The name of the item to deactivate.

        Raises:
            ValueError: If the item with the specified name does not exist.
        """
        self._items.deactivate_item(name)
        logger.info("Deactivated item '%s' in project '%s'", name, self.name)
    
    def activate_all(self) -> None:
        """Activate all items in the container.

        Raises:
            ValueError: If the container is empty.
        """
        return self._items.activate_all()

    def deactivate_all(self) -> None:
        """Deactivate all items in the container.

        Raises:
            ValueError: If the container is empty.
        """
        return self._items.deactivate_all()

    def drop_active(self) -> None:
        """Remove all active items from the container.

        Raises:
            ValueError: If there are no active items.
        """
        guarded = self._guarded()
        dropped = self._items.drop_active()
        self._rules_hold(guarded)
        return dropped

    def drop_inactive(self) -> None:
        """Remove all inactive items from the container.

        Raises:
            ValueError: If there are no inactive items.
        """
        guarded = self._guarded()
        dropped = self._items.drop_inactive()
        self._rules_hold(guarded)
        return dropped

    def to_dict(self) -> Dict[str, Any]:
        """Convert the project to a dictionary for serialization.

        Returns:
            Dict[str, Any]: A dictionary containing the project's name and serialized items.
        """
        data = {"name": self.name, "items": self._items.to_dict()["items"]}
        if self.SCHEMA_VERSION != 1:
            # Written only by a project that has actually versioned itself, so a file saved
            # by an application that never touches this is byte for byte what it always was.
            data["schema_version"] = self.SCHEMA_VERSION
        return data

    @classmethod
    def _item_class(cls, data: Any) -> Type[Serializable]:
        """Return the class to rebuild one item as.

        Args:
            data (Any): The item's serialized mapping, which carries the name of the class that
                wrote it.

        Returns:
            Type[Serializable]: The class that data names, when it is the project's item type or
                a subclass of it; the declared `_item_type` when the data names nothing.

        Raises:
            SerializationError: If the data names a type this project does not hold.
        """
        declared = cls._item_type
        named = data.get("type") if isinstance(data, dict) else None
        if not named:
            return declared

        resolved = declared._resolve_entity_type(named, declared)
        if resolved is None:
            return declared
        if not issubclass(resolved, declared):
            raise SerializationError(
                f"'{named}' is not a {declared.__name__}, which is what {cls.__name__} holds")
        return resolved

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
        """Create a project instance from a dictionary.

        Args:
            data (Dict[str, Any]): Dictionary with project configuration.

        Returns:
            Project: A new instance of the subclass initialized with the dictionary data.

        Raises:
            ValueError: If the data is invalid or cannot be deserialized.

        Notes:
            - This used to be abstract while carrying a full implementation, which forced
              every subclass to write a stub it could not meaningfully fill. Subclasses that
              already override it are unaffected; the rest now inherit a working method.
            - **An item is rebuilt as the class its data names**, so a project holding a
              subclass of its item type reads back as that subclass -- which is what a container
              has always done. Restoring everything as `_item_type` meant a project with any
              hierarchy in it could be written and not read: the extra fields of the subclass
              were rejected as unknown attributes, and the default `_item_type` of `BaseEntity`
              rejected every field there was.
        """
        data = cls._apply_migration(dict(data))
        try:
            check_non_empty_string(data["name"], "Project name")
            items = {}
            for k, v in data.get("items", {}).items():
                try:
                    items[k] = cls._item_class(v).from_dict(v)
                except (TypeError, ValueError) as e:
                    logger.error("Failed to deserialize item '%s' for project: %s", k, str(e))
                    raise SerializationError(f"Invalid data for item '{k}': {str(e)}") from e
            return cls(name=data["name"], items=items)
        except (KeyError, TypeError, ValueError) as e:
            logger.error("Failed to deserialize Project from dict with name '%s': %s", data.get('name', 'unknown'), str(e))
            raise SerializationError(f"Invalid project data: {str(e)}") from e

    def __eq__(self, other: Any) -> bool:
        """Two projects are equal when they are the same kind, named the same and hold the same.

        Args:
            other (Any): The object to compare with.

        Returns:
            bool: True when both are of this class, share a name and their items compare equal.

        Notes:
            - The items are compared by the container, which already knows how. Before this a
              project inherited identity comparison, so `load(...) == project` was False for a
              file just written from it.
        """
        if not isinstance(other, self.__class__):
            return NotImplemented if not isinstance(self, other.__class__) else False
        return self.name == other.name and self._items == other._items

    def __hash__(self) -> int:
        """Projects are mutable; hashing one by identity keeps it usable as a dict key."""
        return object.__hash__(self)

    def __repr__(self) -> str:
        """Return a string representation of the Project."""
        return f"Project(name='{self.name}', items_count={len(self._items)})"