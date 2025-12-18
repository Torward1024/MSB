# msb/__init__.py
"""
Mega-Super-Base (MSB) architecture package.
"""

from .base import BaseEntity, BaseContainer
from .super import Super, Project
from .mega import Manipulator
from .utils import logger, setup_logging

__all__ = ["BaseEntity", "BaseContainer", "Super", "Project", "Manipulator", "logger", "setup_logging"]

__version__ = "0.1.0"