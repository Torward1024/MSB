# super/super.py
from abc import ABC
from typing import Dict, Any, Callable, List, Type, Optional
from ..utils.logging_setup import logger
from ..mega.manipulator import Manipulator
from ..base.basecontainer import BaseContainer
from collections import OrderedDict
from threading import Lock
import inspect

# Sentinel: None is a legitimate cached outcome, meaning "no handler matches".
_MISSING = object()

class Super(ABC):
    """Abstract super-class providing common functionality for operation handlers.

    Designed to work with a Manipulator, this class defines a framework for executing operations on objects
    based on attributes. Subclasses implement specific operations (e.g., configuration, inspection, calculation, etc.)
    by defining methods with naming conventions like `_<operation>_<type>` or `_<operation>`.

    Attributes:
        _manipulator (Manipulator): The associated Manipulator instance for method lookup.
        _methods (Dict[Type, Dict[str, Callable]]): Custom method registry for specific object types.
        _method_cache (OrderedDict): LRU cache of resolved handler lookups, keyed by the
            requested name and the type of the object.
        _cache_size (int): Maximum number of remembered lookups.
        OPERATION (str): The operation name. Used as the default for `_operation`, and
            overwritten by Manipulator during registration.

    Notes:
        - Method resolution order: the requested name if it already denotes a handler, prefixed method (`_<operation>_<method>`), type-specific method (`_<operation>_<type>`), `_<operation>_basecontainer` for containers, default method (`_<operation>`).
        - Only handlers of this operation can be reached from a request. The name arrives as
          data, so anything else would let a request call arbitrary methods on the instance.
        - Only the lookup is cached, never the outcome: operations have side effects.
        - Logging is integrated via `utils.logging_setup.logger`.
        - Results are returned as dictionaries with keys: status (bool), object (str), method (str | None),
          result (Any), error (str | None, included only if status=False).

    Extension points:
        The following carry a single underscore in the sense the language intends: protected
        rather than private. The framework itself never calls them; they exist for the
        handlers a subclass writes, and they are part of the contract even though they are
        not part of the public surface. Changing their signatures breaks subclasses.

        - `_build_response(obj, status, method, result, error)`: produce the response
          dictionary every handler is expected to return.
        - `_get_methods(obj_type)`: the methods registered for a type, from this instance
          first and from the Manipulator otherwise.
        - `_validate_and_apply_method(obj, name, args, valid_methods, extra_args)`: check a
          method name against a set of allowed ones, bind the arguments and call it.
        - `_do_nested(obj, attributes, key, getter, handler)`: descend into a member of a
          container and run a handler against it.
        - `register_method(obj_type, name, method)`: add a method for a type at run time.
    """

    OPERATION: Optional[str] = None # Default operation name for auto-registration

    def __init__(self, manipulator: 'Manipulator' = None, methods: Optional[Dict[Type, Dict[str, Callable]]] = None,
                 cache_size: int = 2048):
        """Initialize a Super instance with an optional Manipulator and method registry.

        Args:
            manipulator (Manipulator, optional): The Manipulator instance to associate with. Defaults to None.
            methods (Optional[Dict[Type, Dict[str, Callable]]]): Custom method registry. Defaults to None (empty dict).
            cache_size (int): Maximum number of resolved handler lookups to remember. Defaults to 2048.

        Notes:
            - `_operation` starts from the class level `OPERATION`, so a Super that was never
              registered with a Manipulator is still usable. Registration overwrites it.
        """
        self._manipulator = manipulator
        self._methods = methods or {}
        self._method_cache = OrderedDict()
        self._cache_size = cache_size
        self._cache_lock = Lock()
        self._operation = self.OPERATION

    def _build_response(self, obj: Any, status: bool, method: str = None, result: Any = None,
                        error: str = None) -> Dict[str, Any]:
        """Format a standardized response dictionary.

        Args:
            obj (Any): The object associated with the operation.
            status (bool): Whether the operation was successful.
            method (str, optional): Name of the method executed. Defaults to None.
            result (Any, optional): Result of the operation. Defaults to None.
            error (str, optional): Error message if status is False. Defaults to None.

        Returns:
            Dict[str, Any]: Standardized response dictionary with object name in 'object' key.
        """
        obj_name = getattr(obj, 'name', None)
        if obj_name is None:
            obj_name = obj
        
        response = {
            "status": status,
            "object": obj_name,
            "method": method,
            "result": result
        }
        if not status and error:
            response["error"] = error
        return response

    def _get_methods(self, obj_type: Type) -> Dict[str, Callable]:
        """Retrieve methods available for a given object type.

        Args:
            obj_type (Type): The type of object to query methods for.

        Returns:
            Dict[str, Callable]: Dictionary of method names mapped to their callable implementations.

        Raises:
            ValueError: If no methods are available for the type in either _methods or the Manipulator.
        """
        if obj_type in self._methods:
            return self._methods[obj_type]
        if self._manipulator:
            return self._manipulator.get_methods_for_type(obj_type)
        raise ValueError(f"No methods available for {obj_type.__name__}")

    def _get_nested_object(self, obj: Any, key: Any, getter_method: Callable) -> Any:
        """Retrieve a nested object from a container.

        Args:
            obj (Any): The object to query.
            key (Any): The key or index to access the nested object.
            getter_method (Callable): Method to retrieve the nested object by key.

        Returns:
            Any: The nested object, or None if the key is invalid.
        """
        try:
            nested_obj = getter_method(key)
            if nested_obj is None:
                logger.error("Item '%s' not found in %s", key, type(obj).__name__)
                return None
            return nested_obj
        except Exception as e:
            logger.error("Invalid key %s for %s: %s", key, type(obj).__name__, str(e))
            return None

    def _do_nested(self, obj: Any, attributes: Dict[str, Any], key: str, getter_method: Callable,
                   nested_handler: Callable) -> Dict[str, Any]:
        """Handle nested operations on an object using an index and a handler.

        Args:
            obj (Any): The object containing nested elements.
            attributes (Dict[str, Any]): Attributes dictionary with an optional key.
            key (str): The key in attributes specifying the index or name.
            getter_method (Callable): Method to retrieve the nested object by key.
            nested_handler (Callable): Method to process the nested object.

        Returns:
            Dict[str, Any]: Dictionary with status, object, method, result, and error (if status=False).
        """
        index = attributes.get(key)
        if index is None:
            logger.debug("No %s provided for nested operation", key)
            return self._build_response(obj, False, None, None, "Operation not executed")

        try:
            nested_obj = self._get_nested_object(obj, index, getter_method)
            if nested_obj is None:
                return self._build_response(obj, False, None, None, f"Name '{index}' not found in {type(obj).__name__}")

            nested_attrs = {k: v for k, v in attributes.items() if k != key}
            result = nested_handler(nested_obj, nested_attrs)
            method_name = nested_handler.__name__ if hasattr(nested_handler, '__name__') else None
            logger.info("Processed nested operation on %s with %s=%s", type(obj).__name__, key, index)
            return self._build_response(nested_obj, True, method_name, result)
        except Exception as e:
            logger.error("Nested operation failed: %s", str(e))
            return self._build_response(obj, False, None, None, str(e))

    def _validate_and_apply_method(self, obj: Any, method_name: str, method_args: Any,
                                   valid_methods: Dict[str, Callable], extra_args: Dict[str, Any] = None) -> Dict[str, Any]:
        """Validate and apply a method to an object with given arguments.

        Args:
            obj (Any): The object to apply the method to.
            method_name (str): The name of the method to apply.
            method_args (Any): Arguments to pass to the method.
            valid_methods (Dict[str, Callable]): Dictionary of valid methods for the object type.
            extra_args (Dict[str, Any], optional): Additional arguments to include. Defaults to None.

        Returns:
            Dict[str, Any]: Response dictionary with status, object, method, result, and error if status is False.
        """
        if method_name not in valid_methods:
            logger.error("Invalid method '%s' for '%s'", method_name, type(obj).__name__)
            return self._build_response(obj, False, method_name, None, f"Method '{method_name}' not found")

        method = valid_methods[method_name]
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())
        expected_params = [p for p in params if p != 'self']

        try:
            final_args = {}
            if 'obj' in expected_params:
                final_args['obj'] = obj
            else:
                pass
            required_params = [
                p for p in expected_params
                if sig.parameters[p].default == inspect.Parameter.empty
                and sig.parameters[p].kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
            ]

            if not expected_params:
                logger.debug("Applying %s to %s with no args", method_name, type(obj).__name__)
                result = method(obj)
            else:
                if method_args is not None:
                    if isinstance(method_args, dict):
                        final_args.update(method_args)
                    else:
                        if required_params:
                            final_args[required_params[0]] = method_args
                        else:
                            final_args[expected_params[0]] = method_args

                if extra_args:
                    final_args.update(extra_args)

                for param in required_params:
                    if param not in final_args:
                        logger.error("Missing required argument '%s' for %s", param, method_name)
                        return self._build_response(obj, False, method_name, None, f"Missing required argument '{param}'")

                valid_args = {k: v for k, v in final_args.items() if k in expected_params}
                result = method(obj, **valid_args) if 'obj' not in expected_params else method(**valid_args)

            logger.debug("Applied %s to %s, result=%s", method_name, type(obj).__name__, result)
            return self._build_response(obj, True, method_name, result)
        except TypeError as e:
            logger.error("TypeError applying %s to %s: %s", method_name, type(obj).__name__, str(e))
            return self._build_response(obj, False, method_name, None, f"TypeError: {str(e)}")
        except Exception as e:
            logger.error("Failed to apply %s to %s: %s", method_name, type(obj).__name__, str(e))
            return self._build_response(obj, False, method_name, None, f"Failed to apply {method_name}: {str(e)}")
    
    def register_method(self, obj_type: Type, method_name: str, method: Callable) -> None:
        """Register a custom method for a specific object type.

        Args:
            obj_type (Type): The type of object the method applies to.
            method_name (str): The name of the method.
            method (Callable): The callable method to register.
        """
        if obj_type not in self._methods:
            self._methods[obj_type] = {}
        self._methods[obj_type][method_name] = method
        self._method_cache.clear()
        logger.info("Registered method '%s' for %s", method_name, obj_type.__name__)

    def _is_handler_name(self, name: str) -> bool:
        """Report whether a name denotes a handler for this operation.

        Args:
            name (str): The attribute name to test.

        Returns:
            bool: True if the name is `_<operation>` or starts with `_<operation>_`.

        Notes:
            - Handler names are the only ones `execute` will call. The name arrives in a
              request, so without this restriction a request could reach any attribute of
              the instance, including `clear`, `execute` or `register_method`.
        """
        if not name or not self._operation:
            return False
        prefix = f"_{self._operation}"
        return name == prefix or name.startswith(f"{prefix}_")

    def _handler_candidates(self, obj: Any, method_name: Optional[str]) -> List[str]:
        """List the handler names to try, most specific first.

        Args:
            obj (Any): The object the operation runs on.
            method_name (Optional[str]): The handler requested by name, if any.

        Returns:
            List[str]: Candidate attribute names in resolution order.
        """
        candidates = []
        if method_name:
            if self._is_handler_name(method_name):
                candidates.append(method_name)
            candidates.append(f"_{self._operation}_{method_name}")
        candidates.append(f"_{self._operation}_{type(obj).__name__.lower()}")
        if isinstance(obj, BaseContainer):
            candidates.append(f"_{self._operation}_basecontainer")
        candidates.append(f"_{self._operation}")
        return candidates

    def _resolve_handler(self, obj: Any, method_name: Optional[str]) -> Optional[str]:
        """Resolve the handler for an operation, remembering the outcome.

        Args:
            obj (Any): The object the operation runs on.
            method_name (Optional[str]): The handler requested by name, if any.

        Returns:
            Optional[str]: The name of the handler to call, or None if nothing matches.

        Notes:
            - Only the lookup is cached, never the result of an operation: operations have
              side effects, so replaying a stored response would be wrong.
            - The cache is keyed by the requested name and the type of the object, and is
              dropped by `register_method` and `clear_cache`. Attaching a handler to an
              instance by any other route needs an explicit `clear_cache()`.
        """
        key = (method_name, type(obj))
        # A single lookup, so eviction on another thread cannot land between a membership
        # test and the read. Entries are not reordered on access either: that would make
        # every hit a write, and eviction order is immaterial for handler resolution.
        cached = self._method_cache.get(key, _MISSING)
        if cached is not _MISSING:
            return cached

        resolved = None
        for candidate in self._handler_candidates(obj, method_name):
            if callable(getattr(self, candidate, None)):
                resolved = candidate
                break
        self._update_cache(key, resolved)
        return resolved

    def _update_cache(self, key: tuple, value: Optional[str]) -> None:
        """Store a resolved handler name, evicting the least recently used entry.

        Args:
            key (tuple): The cache key, a requested name paired with an object type.
            value (Optional[str]): The resolved handler name, or None if nothing matched.
        """
        with self._cache_lock:
            while len(self._method_cache) >= self._cache_size:
                self._method_cache.popitem(last=False)
            self._method_cache[key] = value

    def execute(self, obj: Any, attributes: Dict[str, Any] = None, method: str = None) -> Dict[str, Any]:
        """Execute an operation on an object based on attributes and an optional method.

        Args:
            obj (Any): The object to process.
            attributes (Dict[str, Any], optional): Dictionary of operation attributes. Defaults to None.
            method (str, optional): Explicit method to call, if provided in the request.

        Returns:
            Dict[str, Any]: Dictionary with status, object (name), method, result, and error (if status=False).

        Notes:
            - Resolution order: the requested name if it already denotes a handler, then
              `_<operation>_<name>`, then `_<operation>_<type>`, then
              `_<operation>_basecontainer` for containers, then `_<operation>`.
            - Only handlers of this operation can be reached. A request naming anything else
              fails with "No suitable method found" instead of calling it.
        """
        if attributes is None:
            attributes = {}
        logger.debug("Executing operation '%s' on %s with attributes=%s, method=%s",
                     self._operation, type(obj).__name__, attributes, method)

        try:
            if not self._operation:
                raise ValueError(
                    f"{self.__class__.__name__} has no operation name: set OPERATION or register "
                    "it with a Manipulator"
                )

            method_name = method or attributes.get("method")
            if not method_name and isinstance(attributes.get("attributes"), dict):
                nested_attrs = attributes["attributes"]
                method_name = nested_attrs.get("method")
                object_attributes = nested_attrs
            else:
                object_attributes = {k: v for k, v in attributes.items() if k != 'method'}

            handler_name = self._resolve_handler(obj, method_name)
            if handler_name is None:
                raise ValueError(
                    f"No suitable method found for operation '{self._operation}' and object "
                    f"'{type(obj).__name__.lower()}' in {self.__class__.__name__}"
                )

            result = getattr(self, handler_name)(obj, object_attributes)
            return self._build_response(obj, True, handler_name, result)
        except ValueError as e:
            logger.error("Execution failed for operation '%s': %s", self._operation, e)
            return self._build_response(obj, False, None, None, str(e))
        except Exception as e:
            logger.error("Unexpected error in execute for '%s': %s", self._operation, e)
            return self._build_response(obj, False, None, None, str(e))
        
    def clear_cache(self) -> None:
        """Clear the resolved handler lookups, forcing them to be resolved again."""
        self._method_cache.clear()
        logger.debug("Cleared method cache for %s", self.__class__.__name__)

    def clear(self) -> None:
        """Clear all references to prevent memory leaks.

        This method clears the manipulator reference, method registry, and cache
        to break potential reference cycles and aid garbage collection.
        """
        self._manipulator = None
        self._methods.clear()
        self.clear_cache()
        logger.debug("Cleared references for %s", self.__class__.__name__)

    def __repr__(self) -> str:
        """Return a string representation of the Super instance.

        Returns:
            str: A formatted string with the class name.
        """
        return f"{self.__class__.__name__}()"