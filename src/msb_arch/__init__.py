# msb/__init__.py
"""
Mega-Super-Base (MSB) architecture package.
"""

from .catalogue import derive, label_for, order
from .model import dependents_of, derive_model, holdings_of, path_of
from .base import Serializable, BaseEntity, BaseContainer
from .base.serializable import ReadOnlyList, ReadOnlyMapping, cache_statistics
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
from .interceptors import RequestJournal, RequestMetrics
from .protocols import Interceptor, MethodProvider
from .super import Super, Project
from .super.builtins import Catalogue, Configurator, Inspector, Loader, Persistence
from .mega import Manipulator
from .results import MethodOutcome, MethodResults, Response, ResponseData
from .utils import logger, setup_logging
from .utils.validation import (Constraint,
                               NonEmpty,
                               NonNegative,
                               NonZero,
                               Positive,
                               Predicate,
                               Range)

__all__ = ["Serializable", "BaseEntity", "BaseContainer", "Super", "Project", "Manipulator", "MethodResults", "Response", "ResponseData", "MethodOutcome", "logger", "setup_logging",
           "MSBError", "ValidationError", "TypeValidationError", "ConstraintError", "UnknownAttributeError", "ItemNameError",
           "DuplicateNameError", "ResolutionError", "NotFoundError", "AttributeNotFoundError", "SerializationError",
           "OperationError", "RegistrationError", "DispatchError", "RequestError", "HandlerError",
           "Constraint", "Positive", "NonNegative", "NonZero", "NonEmpty", "Range", "Predicate",
           "MethodProvider", "Interceptor", "Inspector", "Configurator", "Catalogue", "Persistence", "Loader",
           "derive", "label_for", "order", "derive_model", "dependents_of", "holdings_of",
           "ReadOnlyMapping", "ReadOnlyList",
           "path_of",
           "RequestMetrics", "RequestJournal", "cache_statistics"]

__version__ = "1.9.2"