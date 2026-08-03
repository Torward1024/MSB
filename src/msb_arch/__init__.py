# msb/__init__.py
"""
Mega-Super-Base (MSB) architecture package.
"""

from .base import Serializable, BaseEntity, BaseContainer
from .super import Super, Project
from .mega import Manipulator
from .results import MethodResults
from .utils import logger, setup_logging

__all__ = ["Serializable", "BaseEntity", "BaseContainer", "Super", "Project", "Manipulator", "MethodResults", "logger", "setup_logging"]

__version__ = "0.3.2"