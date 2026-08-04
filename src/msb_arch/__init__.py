# msb/__init__.py
"""
Mega-Super-Base (MSB) architecture package.
"""

from .base import Serializable, BaseEntity, BaseContainer
from .errors import (AttributeNotFoundError,
                     ConstraintError,
                     DispatchError,
                     DuplicateNameError,
                     HandlerError,
                     ItemNameError,
                     MSBError,
                     NotFoundError,
                     OperationError,
                     RegistrationError,
                     RequestError,
                     ResolutionError,
                     SerializationError,
                     TypeValidationError,
                     UnknownAttributeError,
                     ValidationError)
from .super import Super, Project
from .mega import Manipulator
from .results import MethodResults
from .utils import logger, setup_logging

__all__ = ["Serializable", "BaseEntity", "BaseContainer", "Super", "Project", "Manipulator", "MethodResults", "logger", "setup_logging",
           "MSBError", "ValidationError", "TypeValidationError", "ConstraintError", "UnknownAttributeError", "ItemNameError",
           "DuplicateNameError", "ResolutionError", "NotFoundError", "AttributeNotFoundError", "SerializationError",
           "OperationError", "RegistrationError", "DispatchError", "RequestError", "HandlerError"]

__version__ = "0.5.0"