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
from .protocols import MethodProvider
from .super import Super, Project
from .super.builtins import Configurator, Inspector
from .mega import Manipulator
from .results import MethodResults
from .utils import logger, setup_logging
from .utils.validation import (Constraint,
                               NonEmpty,
                               NonNegative,
                               NonZero,
                               Positive,
                               Predicate,
                               Range)

__all__ = ["Serializable", "BaseEntity", "BaseContainer", "Super", "Project", "Manipulator", "MethodResults", "logger", "setup_logging",
           "MSBError", "ValidationError", "TypeValidationError", "ConstraintError", "UnknownAttributeError", "ItemNameError",
           "DuplicateNameError", "ResolutionError", "NotFoundError", "AttributeNotFoundError", "SerializationError",
           "OperationError", "RegistrationError", "DispatchError", "RequestError", "HandlerError",
           "Constraint", "Positive", "NonNegative", "NonZero", "NonEmpty", "Range", "Predicate",
           "MethodProvider", "Inspector", "Configurator"]

__version__ = "0.6.0"