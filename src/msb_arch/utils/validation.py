# utils/validation.py
from abc import ABC, abstractmethod
from typing import Any, Callable

from ..errors import ConstraintError, TypeValidationError
from ..utils.logging_setup import logger

def check_type(value, expected_type, name: str) -> None:
    """Check if a value matches the expected type or is None for optional parameters.

    Args:
        value: The value to check.
        expected_type: The expected type or tuple of types (e.g., str, (int, float)).
        name (str): Name of the parameter for use in error messages.

    Raises:
        TypeError: If value is neither None nor of the expected type.

    Notes:
        - Allows None as a valid value for optional parameters.
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_type("test", str, "my_string")
        >>> check_type(None, str, "optional_string")  # No exception
        >>> check_type(123, str, "my_string")
        Traceback (most recent call last):
        ...
        TypeError: my_string must be of type <class 'str'>, got <class 'int'>
    """
    if value is None:
        return
    if not isinstance(value, expected_type):
        logger.error("%s must be of type %s, got %s", name, expected_type, type(value))
        raise TypeValidationError(f"{name} must be of type {expected_type}, got {type(value)}")

def _numeric(value: Any, name: str) -> float:
    """Return a value that can be compared, or refuse it.

    Args:
        value (Any): What arrived.
        name (str): The field, for the message.

    Returns:
        float: The value.

    Raises:
        TypeValidationError: If it is not a number.
        ConstraintError: If it is NaN. Every comparison with NaN is false, so a check written
            as `value <= 0` lets it through and a check written as `not 0 <= value` rejects it
            -- the same value passing or failing depending on how the rule happens to be
            spelled. It is refused here instead, once.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        logger.error("%s must be a number, got %s", name, type(value))
        raise TypeValidationError(f"{name} must be a number, got {type(value)}")
    if value != value:
        logger.error("%s must be a number, got NaN", name)
        raise ConstraintError(f"{name} must be a real number, got NaN")
    return value


def check_range(value: float, min_val: float, max_val: float, name: str) -> None:
    """Check if a numeric value is within a specified range.

    Args:
        value (float): The value to check.
        min_val (float): Minimum allowed value (inclusive).
        max_val (float): Maximum allowed value (inclusive).
        name (str): Name of the parameter for error messages.

    Raises:
        TypeError: If value is not a number (int or float).
        ValueError: If value is outside the range [min_val, max_val].

    Notes:
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_range(5.0, 0.0, 10.0, "my_value")
        >>> check_range(-1, 0.0, 10.0, "my_value")
        Traceback (most recent call last):
        ...
        ValueError: my_value must be between 0.0 and 10.0, got -1
    """
    value = _numeric(value, name)
    if not min_val <= value <= max_val:
        logger.error("%s must be between %s and %s, got %s", name, min_val, max_val, value)
        raise ConstraintError(f"{name} must be between {min_val} and {max_val}, got {value}")

def check_positive(value: float, name: str) -> None:
    """Check if a numeric value is positive.

    Args:
        value (float): The value to check.
        name (str): Name of the parameter for error messages.

    Raises:
        TypeError: If value is not a number (int or float).
        ValueError: If value is not positive (less than or equal to 0).

    Notes:
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_positive(1.5, "my_value")
        >>> check_positive(0, "my_value")
        Traceback (most recent call last):
        ...
        ValueError: my_value must be positive, got 0
    """
    value = _numeric(value, name)
    if value <= 0:
        logger.error("%s must be positive, got %s", name, value)
        raise ConstraintError(f"{name} must be positive, got {value}")

def check_list_type(lst: list, expected_type, name: str) -> None:
    """Check if all elements in a list or tuple match the expected type.

    Args:
        lst (list): The list or tuple to check.
        expected_type: The expected type for all elements (e.g., str, int).
        name (str): Name of the parameter for error messages.

    Raises:
        TypeError: If lst is not a list/tuple or any element does not match expected_type.

    Notes:
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_list_type(["a", "b"], str, "my_list")
        >>> check_list_type([1, "b"], str, "my_list")
        Traceback (most recent call last):
        ...
        TypeError: All items in my_list must be of type <class 'str'>, got <class 'int'>
    """
    if not isinstance(lst, (list, tuple)):
        logger.error("%s must be a list or tuple, got %s", name, type(lst))
        raise TypeValidationError(f"{name} must be a list or tuple, got {type(lst)}")
    for item in lst:
        if not isinstance(item, expected_type):
            logger.error("All items in %s must be of type %s, got %s", name, expected_type, type(item))
            raise TypeValidationError(f"All items in {name} must be of type {expected_type}, got {type(item)}")

def check_non_negative(value: float, name: str) -> None:
    """Check if a numeric value is non-negative.

    Args:
        value (float): The value to check.
        name (str): Name of the parameter for error messages.

    Raises:
        TypeError: If value is not a number (int or float).
        ValueError: If value is negative (less than 0).

    Notes:
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_non_negative(0.0, "my_value")
        >>> check_non_negative(-1.0, "my_value")
        Traceback (most recent call last):
        ...
        ValueError: my_value must be non-negative, got -1.0
    """
    value = _numeric(value, name)
    if value < 0:
        logger.error("%s must be non-negative, got %s", name, value)
        raise ConstraintError(f"{name} must be non-negative, got {value}")

def check_non_empty_string(value: str, name: str) -> None:
    """Check if a value is a non-empty string.

    Args:
        value (str): The value to check.
        name (str): Name of the parameter for error messages.

    Raises:
        TypeError: If value is not a string.
        ValueError: If value is empty or contains only whitespace.

    Notes:
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_non_empty_string("test", "my_string")
        >>> check_non_empty_string("", "my_string")
        Traceback (most recent call last):
        ...
        ValueError: my_string must not be empty
    """
    if not isinstance(value, str):
        logger.error("%s must be a string, got %s", name, type(value))
        raise TypeValidationError(f"{name} must be a string, got {type(value)}")
    if not value.strip():
        logger.error("%s must not be empty", name)
        raise ConstraintError(f"{name} must not be empty")

def check_non_zero(value: float, name: str) -> None:
    """Check if a numeric value is non-zero.

    Args:
        value (float): The value to check.
        name (str): Name of the parameter for error messages.

    Raises:
        TypeError: If value is not a number (int or float).
        ValueError: If value is zero.

    Notes:
        - Logs an error message via `logger` before raising an exception.

    Examples:
        >>> check_non_zero(1.0, "my_value")
        >>> check_non_zero(0.0, "my_value")
        Traceback (most recent call last):
        ...
        ValueError: my_value must be non-zero, got 0.0
    """
    value = _numeric(value, name)
    if value == 0:
        logger.error("%s must be non-zero, got %s", name, value)
        raise ConstraintError(f"{name} must be non-zero, got {value}")

class Constraint(ABC):
    """A rule an annotated value must satisfy beyond having the right type.

    Attach one to a field with `Annotated`, and the model enforces it:

        class Product(BaseEntity):
            price: Annotated[float, Positive()]

    The annotation is checked first, then every constraint on it, so a constraint only ever
    sees a value of the declared type. Each delegates to the function of the same meaning
    above, which is where the message and the logging live.

    Subclass this to add a rule of your own; `check` is the whole interface.
    """

    @abstractmethod
    def check(self, value: Any, name: str) -> None:
        """Raise if the value is not allowed.

        Args:
            value (Any): The value assigned to the field.
            name (str): What to call the field in the error message.

        Raises:
            ConstraintError: If the value violates the rule.
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class Positive(Constraint):
    """The value must be greater than zero."""

    def check(self, value: Any, name: str) -> None:
        check_positive(value, name)


class NonNegative(Constraint):
    """The value must be zero or greater."""

    def check(self, value: Any, name: str) -> None:
        check_non_negative(value, name)


class NonZero(Constraint):
    """The value must not be zero."""

    def check(self, value: Any, name: str) -> None:
        check_non_zero(value, name)


class NonEmpty(Constraint):
    """The value must be a string with something other than whitespace in it."""

    def check(self, value: Any, name: str) -> None:
        check_non_empty_string(value, name)


class Range(Constraint):
    """The value must lie between two bounds, inclusive."""

    def __init__(self, minimum: float, maximum: float):
        self.minimum = minimum
        self.maximum = maximum

    def check(self, value: Any, name: str) -> None:
        check_range(value, self.minimum, self.maximum, name)

    def __repr__(self) -> str:
        return f"Range({self.minimum}, {self.maximum})"


class Predicate(Constraint):
    """The escape hatch: any rule expressible as a function returning True when allowed.

    Args:
        test (Callable[[Any], bool]): Returns True for a value that is allowed.
        description (str): How to describe the rule in the error message, phrased to follow
            the field name -- "must be even", "must be a valid ISO date".

    Example:
        ```python
        class Frame(BaseEntity):
            width: Annotated[int, Predicate(lambda v: v % 2 == 0, "must be even")]
        ```
    """

    def __init__(self, test: Callable[[Any], bool], description: str):
        self.test = test
        self.description = description

    def check(self, value: Any, name: str) -> None:
        if not self.test(value):
            logger.error("%s %s, got %r", name, self.description, value)
            raise ConstraintError(f"{name} {self.description}, got {value!r}")

    def __repr__(self) -> str:
        return f"Predicate({self.description!r})"
