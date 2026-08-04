# mega/manipulator.py
from abc import ABC
from typing import Dict, Any, Optional, Callable, List, Sequence, Type, Union
from ..errors import DispatchError, HandlerError, NotFoundError, RegistrationError, RequestError
from ..protocols import Interceptor
from ..utils.logging_setup import logger
from ..results import MethodResults
import inspect
import types

class Manipulator(ABC):
    """Abstract class for managing and processing operations on objects.

    Provides a framework for registering operations and their associated methods, managing a central object,
    and processing requests. Maintains a registry of supported object types and their methods, with caching
    for performance. Subclasses can extend this to implement specific manipulation logic.

    Attributes:
        _managing_object (Optional[Any]): The central object being managed.
        _base_classes (List[Type]): List of base classes whose methods are registered.
        _operations (Dict[str, Callable]): Dictionary mapping operation names to super-instance handlers.
        _registry (Dict[Type, Dict[str, Callable]]): Registry of object types and their available methods.
        _strict_type_check (bool): If True, enforces strict type checking for objects.

    Notes:
        - The method registry is held per instance in `_registry` and rebuilt by `update_registry`.
        - Logging is integrated via `..utils.logging_setup.logger`.
        - Operations are executed via super-instances that must have an `execute` method.
        - Results are returned as dictionaries with keys: status (bool), object (Any), method (str | None),
          result (Any), error (str | None, included only if status=False).

    Examples:
        >>> manip = Manipulator(base_classes=[list])
        >>> manip.register_operation("append", Super())  # Assuming super-class with execute method
        >>> manip.process_request({"operation": "append", "obj": [], "attributes": {"value": 1}})
        {"status": True, "object": [1], "method": "append", "result": True}
    """
    def __init__(self, managing_object: Optional[Any] = None,
                 base_classes: Optional[List[Type]] = None,
                 operations: Optional[Dict[str, Callable]] = None,
                 strict_type_check: bool = False,
                 builtins: bool = True):
        """Initialize a Manipulator with an optional managing object, base classes, and operations.

        Args:
            managing_object (Optional[Any]): The central object to manage. Defaults to None.
            base_classes (Optional[List[Type]]): List of base classes for method registration. Defaults to None.
            operations (Optional[Dict[str, Callable]]): Initial operations to register. Defaults to None.
            strict_type_check (bool): If True, enforce strict type checking for objects. Defaults to False.
            builtins (bool): Register the built-in `inspect` and `configure` operations.
                Defaults to True.

        Notes:
            - The built-ins make an application that only reads and writes its model need no
              `Super` of its own. Registering an operation of the same name replaces one
              silently, so an application that supplies its own `Inspector` behaves exactly as
              it did before they existed. Two registrations of one name that are both yours
              still raise.
            - Pass `builtins=False` to start with nothing registered.
        """
        self._managing_object = managing_object
        self._strict_type_check = strict_type_check
        self._base_classes = base_classes if base_classes is not None else []
        if managing_object is not None and type(managing_object) not in self._base_classes:
            self._base_classes.append(type(managing_object))
        self._operations = {}
        self._registry = {}
        self._builtin_operations = set()
        self._interceptors = []
        self._chain = None
        if builtins:
            from ..super.builtins import Configurator, Inspector
            for builtin in (Inspector(self), Configurator(self)):
                self.register_operation(builtin)
                self._builtin_operations.add(builtin.OPERATION)
        if operations:
            for op_name, super_inst in operations.items():
                self.register_operation(super_inst, operation=op_name)
        
        self._registry = self._get_method_registry()
        logger.debug("Initialized Manipulator with %s initial operations", len(self._operations))
        self._create_facades()

    def set_managing_object(self, obj: Any) -> None:
        """Set the central managing object.

        Args:
            obj (Any): The object to set as the managing object.
        """
        self._managing_object = obj
        if obj is not None and type(obj) not in self._base_classes:
            self._base_classes.append(type(obj))
            self.update_registry()
        logger.info("Set managing object of type '%s' in Manipulator", type(obj).__name__)

    def get_managing_object(self) -> Optional[Any]:
        """Retrieve the central managing object.

        Returns:
            Optional[Any]: The managing object, or None if not set.
        """
        return self._managing_object

    def _validate_object(self, obj: Any, obj_type: str) -> Any:
        """Validate that an object is provided and supported.

        Args:
            obj (Any): The object to validate.
            obj_type (str): Descriptive name of the object type for error messages.

        Returns:
            Any: The validated object.

        Raises:
            ValueError: If no object is provided or the type is unsupported.
        """
        effective_obj = obj if obj is not None else self._managing_object
        if effective_obj is None:
            logger.error("No %s or managing object provided for operation", obj_type)
            raise RequestError(f"No {obj_type} or managing object provided")
        if self._strict_type_check and type(effective_obj) not in self._registry:
            logger.error("Unsupported object type for %s: %s", obj_type, type(effective_obj))
            raise DispatchError(f"Unsupported object type: {type(effective_obj)}")
        return effective_obj

    def get_methods_for_type(self, obj_type: Type) -> Dict[str, Callable]:
        """Retrieve the registered methods for a given object type.

        Args:
            obj_type (Type): The type of object to query methods for.

        Returns:
            Dict[str, Callable]: Dictionary of method names and their callable implementations.

        Raises:
            ValueError: If no methods are registered for the type.
        """
        if obj_type not in self._registry:
            logger.error("No methods registered for type %s", obj_type.__name__)
            raise DispatchError(f"No methods registered for type {obj_type.__name__}")
        return self._registry[obj_type]

    def update_registry(self, additional_classes: Optional[List[Type]] = None, clear_operations: bool = False) -> None:
        """Update the method registry with additional base classes or clear operations.

        Args:
            additional_classes (Optional[List[Type]]): Additional classes to register. Defaults to None.
            clear_operations (bool): If True, clear all operations. Defaults to False.
        """
        if clear_operations:
            self._operations.clear()
            logger.info("Cleared all operations in registry")
        if additional_classes:
            self._base_classes.extend([cls for cls in additional_classes if cls not in self._base_classes])
        self._registry = self._get_method_registry()
        logger.info("Registry updated with %s types", len(self._registry))

    def register_operation(self, super_instance: Callable, operation: Optional[str] = None) -> None:
        """Register an operation with its super-instance handler.

        If operation is not provided, it is taken from super_instance.OPERATION if available.

        Args:
            super_instance (Callable): The super-instance with an 'execute' method.
            operation (Optional[str]): The name of the operation. Defaults to None (auto from super_instance.OPERATION).

        Raises:
            ValueError: If the operation name is invalid, duplicate, or the super-instance lacks an 'execute' method.
        """
        if not hasattr(super_instance, "execute"):
            logger.error("Super-instance must have 'execute' method")
            raise RegistrationError(f"Super-instance must have 'execute' method")

        if operation is None:
            if hasattr(super_instance, 'OPERATION') and super_instance.OPERATION:
                operation = super_instance.OPERATION
            else:
                logger.error("No operation name provided and no OPERATION attribute in super_instance")
                raise RegistrationError("Operation name required or set OPERATION in super_instance")

        if not isinstance(operation, str) or not operation:
            logger.error("Operation name must be a non-empty string")
            raise RegistrationError("Operation name must be a non-empty string")

        if operation in self._operations:
            if operation in self._builtin_operations:
                # A default being overridden, not two intentions colliding. Registering an
                # `Inspector` of your own is how it has always been written, and must keep
                # meaning the same thing now that one is supplied.
                logger.debug("Operation '%s' replaces the built-in", operation)
                self._builtin_operations.discard(operation)
            else:
                logger.error("Operation '%s' already registered", operation)
                raise RegistrationError(f"Operation '{operation}' already registered")

        if not operation.isidentifier():
            logger.error("Operation name '%s' is not a valid identifier", operation)
            raise RegistrationError(f"Operation name '{operation}' is not a valid identifier")

        if hasattr(type(self), operation):
            logger.error("Operation '%s' would shadow %s.%s", operation, type(self).__name__, operation)
            raise RegistrationError(
                f"Operation '{operation}' would shadow the existing "
                f"{type(self).__name__}.{operation}; choose another name"
            )

        super_instance._operation = operation
        self._operations[operation] = super_instance

        super_type = type(super_instance)
        if super_type not in self._registry:
            methods = {
                name: method for name, method in inspect.getmembers(super_instance, predicate=inspect.ismethod)
                if not name.startswith('__') and callable(method)
            }
            self._registry[super_type] = methods
            logger.debug("Registered %s methods for %s", len(methods), super_type.__name__)
        logger.debug("Registered operation '%s' with %s", operation, type(super_instance).__name__)

        self._add_facade(operation)
    
    def _create_facades(self) -> None:
        """Create facade methods for all registered operations.

        Iterates through all registered operations and adds facade methods to the instance.
        """
        for op in self._operations:
            self._add_facade(op)
    
    def _add_facade(self, operation: str) -> None:
        """Dynamically add a facade method for the given operation.

        Args:
            operation (str): The name of the operation to add a facade for.
        """
        def facade_wrapper(self, obj: Optional[Any] = None, method: Optional[str] = None, raise_on_error: bool = True, **attributes) -> Any:
            """Facade for {operation}.

            Args:
                obj (Optional[Any]): The object to operate on. Defaults to managing_object.
                method (Optional[str]): Specific method to call.
                raise_on_error (bool): If True, raise Exception on error; if False, return dict with {{status: bool, result: Any, error: str}}.

            Returns:
                Any: If raise_on_error=True, the result, or the value itself when the
                    request named exactly one method. If False, the whole response.

            Raises:
                Exception: If raise_on_error=True and operation fails.

            Notes:
                - The protocol does not change with the shape of the request: a handler
                  built on `_apply_methods` always reports every method it ran, which is
                  what makes a request history replayable.
                - This facade is sugar over `process_request`, so it unwraps the common
                  case: one method named, its value returned rather than a mapping of one.
            """
            request_attributes = attributes.copy()
            if method:
                request_attributes["method"] = method
            elif "method" in request_attributes:
                pass
            
            request = {"operation": operation, "obj": obj, "attributes": request_attributes}
            logger.debug("Facade request for %s: %s", operation, request)
            result = self.process_request(request)
            if not raise_on_error:
                return result
            if not result["status"]:
                raise HandlerError(result.get("error", "Unknown error"))
            return self._unwrap_single(result["result"])

        facade_wrapper.__doc__ = facade_wrapper.__doc__.format(operation=operation)
        bound_method = types.MethodType(facade_wrapper, self)
        setattr(self, operation, bound_method)
        logger.debug("Added facade method '%s' to Manipulator with docstring: %s", operation, bound_method.__doc__)

    @staticmethod
    def _unwrap_single(result: Any) -> Any:
        """Reduce a one-method result mapping to the value it holds.

        Args:
            result (Any): Whatever the handler returned.

        Returns:
            Any: The single value if `result` reports exactly one method, `result` otherwise.

        Notes:
            - Only `MethodResults` is unwrapped, never a plain dictionary a handler happens
              to return, so a handler producing real data of its own is left alone.
        """
        if isinstance(result, MethodResults) and len(result) == 1:
            return next(iter(result.values()))["result"]
        return result

    def _get_method_registry(self, validate_annotations: bool = False) -> Dict[Type, Dict[str, Callable]]:
        """Generate the method registry for registered operations and base classes.

        The result is stored by the caller in `self._registry`; this method always rebuilds
        it from the current operations and base classes.

        Args:
            validate_annotations (bool): If True, validate method return annotations. Defaults to False.

        Returns:
            Dict[Type, Dict[str, Callable]]: Registry of types and their methods.
        """
        registry = {}
        for operation, instance in self._operations.items():
            super_type = type(instance)
            methods = {
                name: method for name, method in inspect.getmembers(instance, predicate=inspect.ismethod)
                if not name.startswith('__') and callable(method)
            }
            if validate_annotations:
                for name, method in methods.items():
                    sig = inspect.signature(method)
                    if not sig.return_annotation or sig.return_annotation is inspect.Signature.empty:
                        logger.warning("Method %s in %s lacks return annotation", name, super_type.__name__)
            registry[super_type] = methods
            logger.debug("Registered %s methods for %s: %s", len(methods), super_type.__name__, list(methods.keys()))

        for cls in self._base_classes:
            methods = {}
            if cls in (list, dict, set):
                for name in dir(cls):
                    if name.startswith('_'):
                        continue
                    method = getattr(cls, name, None)
                    if callable(method) and not isinstance(method, (type, property)):
                        methods[name] = method
            else:
                for name, method in inspect.getmembers(cls, predicate=lambda x: inspect.isfunction(x) or inspect.ismethod(x)):
                    if name.startswith('_') or not callable(method) or name in ('__getattribute__', '__setattr__'):
                        continue
                    if validate_annotations:
                        sig = inspect.signature(method)
                        if not sig.return_annotation or sig.return_annotation is inspect.Signature.empty:
                            logger.warning("Method %s in %s lacks return annotation", name, cls.__name__)
                    methods[name] = method
            if methods:
                registry[cls] = methods
                logger.debug("Registered %s methods for %s: %s", len(methods), cls.__name__, list(methods.keys()))
            else:
                logger.warning("No valid methods found for %s", cls.__name__)
        return registry

    def process_request(self, request: Dict[str, Any]) -> Any:
        """Process a request or sequence of requests.

        Args:
            request (Dict[str, Any]): The request dictionary specifying the operation, object, and attributes.
                For a single request, expected keys include "operation", and optionally "obj", "method" (str),
                "attributes" (dict). For a sequence of requests, expected format is {request_id: {sub_request}}
                where each sub_request has the same structure as a single request.

        Returns:
            Any: For a single request, a dictionary with status, object, method, result, and error (if status=False).
                For a sequence of requests, a dictionary mapping request IDs to results.

        Raises:
            TypeError: If the request is not a dictionary or contains invalid types.
            ValueError: If the request structure is invalid.
        """
        if not isinstance(request, dict):
            logger.error("Invalid request type: expected dict, got %s", type(request).__name__)
            raise RequestError(f"Request must be a dictionary, got {type(request).__name__}")

        is_potential_sequence = len(request) > 0 and "operation" not in request

        if is_potential_sequence:
            invalid_sub_requests = [
                (k, type(v).__name__) for k, v in request.items() if not isinstance(v, dict)
            ]
            if invalid_sub_requests:
                error_msg = f"Invalid sub-request type in sequence: {invalid_sub_requests}"
                logger.error(error_msg)
                return {
                    "status": False,
                    "object": None,
                    "method": None,
                    "result": None,
                    "error": error_msg
                }

            logger.info("Processing sequence of %s requests", len(request))
            results = {}
            for req_id, sub_request in request.items():
                if "operation" not in sub_request:
                    logger.error("Missing 'operation' in sub-request for ID '%s'", req_id)
                    results[req_id] = {
                        "status": False,
                        "object": sub_request.get("obj"),
                        "method": None,
                        "result": None,
                        "error": "Missing 'operation' in sub-request"
                    }
                    continue
                if "method" in sub_request and not isinstance(sub_request["method"], (str, type(None))):
                    logger.error("Invalid 'method' type in sub-request for ID '%s': expected str or None, got %s", req_id, type(sub_request['method']).__name__)
                    results[req_id] = {
                        "status": False,
                        "object": sub_request.get("obj"),
                        "method": None,
                        "result": None,
                        "error": f"Invalid 'method' type: expected str or None, got {type(sub_request['method']).__name__}"
                    }
                    continue
                if "attributes" in sub_request and not isinstance(sub_request["attributes"], (dict, type(None))):
                    logger.error("Invalid 'attributes' type in sub-request for ID '%s': expected dict or None, got %s", req_id, type(sub_request['attributes']).__name__)
                    results[req_id] = {
                        "status": False,
                        "object": sub_request.get("obj"),
                        "method": None,
                        "result": None,
                        "error": f"Invalid 'attributes' type: expected dict or None, got {type(sub_request['attributes']).__name__}"
                    }
                    continue
                result = self._process_single_request(sub_request)
                results[req_id] = result
            logger.debug("Sequence processing results: %s", results)
            return results

        if "operation" not in request:
            error_msg = "No operation specified in request"
            logger.error(error_msg)
            return {"status": False, "object": request.get("obj"), "method": None, "result": None, "error": error_msg}

        if "method" in request and not isinstance(request["method"], (str, type(None))):
            error_msg = f"Invalid 'method' type: expected str or None, got {type(request['method']).__name__}"
            logger.error(error_msg)
            return {"status": False, "object": request.get("obj"), "method": None, "result": None, "error": error_msg}

        if "attributes" in request and not isinstance(request["attributes"], (dict, type(None))):
            error_msg = f"Invalid 'attributes' type: expected dict or None, got {type(request['attributes']).__name__}"
            logger.error(error_msg)
            return {"status": False, "object": request.get("obj"), "method": None, "result": None, "error": error_msg}

        return self._process_single_request(request)

    def add_interceptor(self, interceptor: Interceptor) -> None:
        """Add an interceptor around every request this orchestrator processes.

        Args:
            interceptor (Interceptor): Called as `interceptor(request, call_next)` and
                expected to return a response.

        Raises:
            RegistrationError: If the interceptor is not callable.

        Notes:
            - The first added is the outermost: it sees a request first and its response last.
            - Metrics, auditing, rate limiting and authorisation are all this hook. MSB
              supplies it and none of them, because a library that chose a metrics backend
              would end the promise of no dependencies.
            - Each entry of a batch is intercepted separately, since a batch is a container of
              requests rather than a request.
        """
        if not callable(interceptor):
            logger.error("Interceptor must be callable, got %s", type(interceptor).__name__)
            raise RegistrationError(
                f"Interceptor must be callable, got {type(interceptor).__name__}")
        self._interceptors.append(interceptor)
        self._chain = None
        logger.debug("Added interceptor %s", getattr(interceptor, '__name__', interceptor))

    def remove_interceptor(self, interceptor: Interceptor) -> None:
        """Remove an interceptor added earlier.

        Args:
            interceptor (Interceptor): The one to remove.

        Raises:
            NotFoundError: If it was never added.
        """
        if interceptor not in self._interceptors:
            raise NotFoundError(f"Interceptor {interceptor!r} is not registered")
        self._interceptors.remove(interceptor)
        self._chain = None
        logger.debug("Removed interceptor %s", getattr(interceptor, '__name__', interceptor))

    def get_interceptors(self) -> List[Interceptor]:
        """Return the interceptors in the order they wrap a request, outermost first."""
        return list(self._interceptors)

    def _build_chain(self) -> Callable[[Dict[str, Any]], Any]:
        """Fold the interceptors around `_dispatch_request`, outermost first.

        Returns:
            Callable[[Dict[str, Any]], Any]: The entry point of the chain.

        Notes:
            - Built once and kept until the list changes, rather than per request.
        """
        call_next = self._dispatch_request
        for interceptor in reversed(self._interceptors):
            def step(request, _interceptor=interceptor, _next=call_next):
                return _interceptor(request, _next)
            call_next = step
        return call_next

    def _process_single_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Run one request through the interceptor chain, if there is one.

        Args:
            request (Dict[str, Any]): The request to process.

        Returns:
            Dict[str, Any]: The response.

        Notes:
            - With no interceptors registered, which is the default, this costs one check and
              a direct call.
        """
        if not self._interceptors:
            return self._dispatch_request(request)
        if self._chain is None:
            self._chain = self._build_chain()
        return self._chain(request)

    def _dispatch_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single request by executing the specified operation.

        Args:
            request (Dict[str, Any]): The request dictionary with operation, object, and attributes.

        Returns:
            Dict[str, Any]: Dictionary with status, object, method, result, and error (if status=False).
        """
        operation = request.get("operation")
        obj = request.get("obj")
        method = request.get("method")
        attributes = request.get("attributes", {})

        if not operation:
            error_msg = "No operation specified in request"
            logger.error(error_msg)
            return {"status": False, "object": obj, "method": None, "result": None, "error": error_msg}

        super_instance = self._operations.get(operation)
        if super_instance is None:
            error_msg = f"Operation '{operation}' not registered"
            logger.error(error_msg)
            return {"status": False, "object": obj, "method": None, "result": None, "error": error_msg}

        try:
            effective_obj = self._validate_object(obj, "request object")
        except ValueError as e:
            logger.error("Object validation failed: %s", str(e))
            return {"status": False, "object": obj, "method": None, "result": None, "error": str(e)}

        execute_args = {"obj": effective_obj}
        if attributes or method:
            if not isinstance(attributes, dict):
                logger.error("Attributes must be a dictionary, got %s", type(attributes).__name__)
                return {"status": False, "object": effective_obj, "method": None, "result": None, "error": "Invalid attributes type"}
            execute_args["attributes"] = attributes.copy()
            if method:
                execute_args["method"] = method

        try:
            super_result = super_instance.execute(**execute_args)
            logger.debug("Processed operation '%s' on %s", operation, type(effective_obj).__name__)
            result_dict = {
                "status": super_result["status"],
                "object": super_result["object"],
                "method": super_result["method"],
                "result": super_result["result"]
            }
            if not super_result["status"]:
                result_dict["error"] = super_result["error"]
            return result_dict
        except Exception as e:
            logger.error("Failed to process request '%s' via execute: %s", operation, str(e))
            return {"status": False, "object": effective_obj, "method": None, "result": None, "error": str(e)}

    def batch(self, requests: Union[Sequence[Dict[str, Any]], Dict[str, Dict[str, Any]]],
              raise_on_error: bool = False) -> Dict[str, Any]:
        """Run several requests in order and report the outcome of each.

        Args:
            requests: Either a sequence of request dictionaries, which are numbered from
                zero, or a mapping of an identifier of your choosing to a request.
            raise_on_error (bool): If True, raise as soon as a request fails. If False, the
                default, every request is attempted and the report carries the failures.

        Returns:
            Dict[str, Any]: Identifier mapped to the response of that request.

        Raises:
            TypeError: If `requests` is neither a sequence nor a mapping of requests.
            Exception: If `raise_on_error` and a request fails.

        Notes:
            - This is sugar over the sequence form of `process_request`, in the same way the
              per-operation facades are sugar over its single form.
            - Requests run in the order given and are independent of one another: nothing
              here feeds the result of one into the next.

        Examples:
            >>> manipulator.batch([
            ...     {"operation": "configure", "obj": telescope, "attributes": {"set_diameter": 30.0}},
            ...     {"operation": "inspect", "obj": telescope, "attributes": {"get_code": None}},
            ... ])
            {'0': {'status': True, ...}, '1': {'status': True, ...}}
        """
        if isinstance(requests, dict):
            numbered = {str(key): value for key, value in requests.items()}
        elif isinstance(requests, Sequence) and not isinstance(requests, (str, bytes)):
            numbered = {str(index): request for index, request in enumerate(requests)}
        else:
            raise RequestError(f"Requests must be a sequence or a mapping, got {type(requests).__name__}")

        if not numbered:
            return {}

        invalid = [key for key, value in numbered.items() if not isinstance(value, dict)]
        if invalid:
            raise RequestError(f"Requests {invalid} are not dictionaries")

        logger.debug("Batch of %s request(s)", len(numbered))
        results = self.process_request(numbered)

        if raise_on_error:
            for key, response in results.items():
                if not response.get("status"):
                    raise HandlerError(f"Request '{key}' failed: {response.get('error', 'Unknown error')}")
        return results

    def get_supported_operations(self) -> List[str]:
        """Retrieve the list of supported operation names.

        Returns:
            List[str]: List of registered operation names.
        """
        return list(self._operations.keys())
    
    def clear_cache(self) -> None:
        """Drop the method registry so that it is rebuilt on the next update.

        Notes:
            - The registry is rebuilt by `update_registry`; this only releases the
              references it holds to the currently registered types and methods.
        """
        self._registry = {}
    
    def clear_base_classes(self) -> None:
        """Clear the list of base classes and update the method registry.

        This method removes all registered base classes and refreshes the method
        registry to prevent memory retention of class references.
        """
        self._base_classes.clear()
        self._registry = self._get_method_registry()
    
    def clear_ops(self):
        """Clear all registered operations and their handlers."""
        try:
            self._operations.clear()
        except Exception as e:
            logger.error("Error clearing operations: %s", str(e))

    def __repr__(self) -> str:
        """Return a string representation of the Manipulator.

        Returns:
            str: A formatted string with the managing object type and operations.
        """
        obj_type = type(self._managing_object).__name__ if self._managing_object else "None"
        return f"Manipulator(managing_object='{obj_type}', operations={list(self._operations.keys())})"
