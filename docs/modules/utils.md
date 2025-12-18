# Utils Module

Utility modules for the MSB architecture.

This package contains utilities for logging setup and data validation. These utilities are used throughout the MSB Framework to ensure consistent behavior and error handling.

## Logging Setup

The `logging_setup` module provides centralized logging configuration for the framework.

### Functions

#### `setup_logging(log_file="output.log", log_level=logging.INFO, clear_log=False)`

Configures and returns a logger with file and console handlers.

**Parameters:**
- `log_file` (str): Path to the log file (default: "output.log")
- `log_level` (int): Logging level (default: logging.INFO)
- `clear_log` (bool): Whether to clear the log file on setup (default: False)

**Returns:** `logging.Logger` instance

**Example:**
```python
from msb_arch.utils.logging_setup import setup_logging
import logging

logger = setup_logging(log_file="app.log", log_level=logging.DEBUG, clear_log=True)
logger.info("Application started")
```

#### `update_logging_level(log_level)`

Updates the logging level for the singleton logger.

**Parameters:**
- `log_level` (int): New logging level

**Example:**
```python
from msb_arch.utils.logging_setup import update_logging_level
import logging

update_logging_level(logging.ERROR)  # Only log errors
```

#### `update_logging_clear(log_file, clear_log)`

Updates logging configuration to clear the log file.

**Parameters:**
- `log_file` (str): Path to the log file
- `clear_log` (bool): Whether to clear the log file

### Usage in Framework

The framework automatically sets up logging when modules are imported:

```python
import msb_arch  # Logging is configured automatically
```

All framework classes use the logger for debugging, info, warning, and error messages.

## Validation Functions

The `validation` module provides functions for data validation with detailed error messages and logging.

### Type Validation

#### `check_type(value, expected_type, name)`

Validates that a value matches an expected type.

**Parameters:**
- `value`: The value to check
- `expected_type`: Expected type or tuple of types
- `name` (str): Parameter name for error messages

**Raises:** `TypeError` if validation fails

**Example:**
```python
from msb_arch.utils.validation import check_type

check_type("hello", str, "message")  # OK
check_type(42, (int, float), "number")  # OK
check_type("hello", int, "number")  # Raises TypeError
```

### Range Validation

#### `check_range(value, min_val, max_val, name)`

Validates that a numeric value is within a specified range.

**Parameters:**
- `value` (float): Value to check
- `min_val` (float): Minimum allowed value (inclusive)
- `max_val` (float): Maximum allowed value (inclusive)
- `name` (str): Parameter name for error messages

**Raises:** `TypeError` if not numeric, `ValueError` if out of range

**Example:**
```python
from msb_arch.utils.validation import check_range

check_range(5.0, 0.0, 10.0, "score")  # OK
check_range(-1, 0, 100, "percentage")  # Raises ValueError
```

### Positive/Negative Validation

#### `check_positive(value, name)`

Validates that a value is positive.

**Parameters:**
- `value` (float): Value to check
- `name` (str): Parameter name

**Raises:** `TypeError` if not numeric, `ValueError` if not positive

#### `check_non_negative(value, name)`

Validates that a value is non-negative.

**Parameters:**
- `value` (float): Value to check
- `name` (str): Parameter name

**Raises:** `TypeError` if not numeric, `ValueError` if negative

**Example:**
```python
from msb_arch.utils.validation import check_positive, check_non_negative

check_positive(5, "count")  # OK
check_positive(-1, "count")  # Raises ValueError

check_non_negative(0, "score")  # OK
check_non_negative(-1, "score")  # Raises ValueError
```

### String Validation

#### `check_non_empty_string(value, name)`

Validates that a value is a non-empty string.

**Parameters:**
- `value` (str): String to check
- `name` (str): Parameter name

**Raises:** `TypeError` if not string, `ValueError` if empty

**Example:**
```python
from msb_arch.utils.validation import check_non_empty_string

check_non_empty_string("hello", "name")  # OK
check_non_empty_string("", "name")  # Raises ValueError
check_non_empty_string("   ", "name")  # Raises ValueError
```

### Collection Validation

#### `check_list_type(lst, expected_type, name)`

Validates that all elements in a list/tuple match an expected type.

**Parameters:**
- `lst` (list or tuple): Collection to check
- `expected_type`: Expected element type
- `name` (str): Parameter name

**Raises:** `TypeError` if not list/tuple or elements don't match type

**Example:**
```python
from msb_arch.utils.validation import check_list_type

check_list_type([1, 2, 3], int, "numbers")  # OK
check_list_type(["a", "b"], str, "letters")  # OK
check_list_type([1, "a"], int, "numbers")  # Raises TypeError
```

### Special Validation

#### `check_non_zero(value, name)`

Validates that a numeric value is non-zero.

**Parameters:**
- `value` (float): Value to check
- `name` (str): Parameter name

**Raises:** `TypeError` if not numeric, `ValueError` if zero

**Example:**
```python
from msb_arch.utils.validation import check_non_zero

check_non_zero(5, "divisor")  # OK
check_non_zero(0, "divisor")  # Raises ValueError
```

## Integration with Framework

### Automatic Validation in BaseEntity

The validation functions are automatically used by `BaseEntity` for attribute validation:

```python
from msb_arch.base import BaseEntity

class Product(BaseEntity):
    name: str
    price: float
    quantity: int

# This uses check_type, check_positive, etc. automatically
product = Product(name="Widget", price=10.99, quantity=5)  # OK
invalid = Product(name="", price=-1, quantity=5)  # Raises ValueError
```

### Logging Integration

All validation functions log errors before raising exceptions:

```python
# Validation errors are logged with context
from msb_arch.utils.validation import check_positive

try:
    check_positive(-5, "age")
except ValueError:
    pass  # Error is already logged
```

## Custom Validation

You can create custom validation functions following the same pattern:

```python
from msb_arch.utils.logging_setup import logger

def check_custom_rule(value, name: str) -> None:
    """Custom validation function."""
    if not meets_custom_criteria(value):
        logger.error(f"{name} does not meet custom criteria: {value}")
        raise ValueError(f"{name} does not meet custom criteria")

    # Use in your classes
    def validate_attribute(self, value, name):
        check_custom_rule(value, name)
        # Other validation...
```

## Error Types

The validation functions raise specific exception types:

- `TypeError`: Type mismatches
- `ValueError`: Value constraint violations

All exceptions include descriptive messages with parameter names and expected values.

## Best Practices

1. **Use Specific Types**: Prefer specific types over generic ones for better validation.

2. **Meaningful Names**: Use descriptive parameter names in validation calls.

3. **Consistent Logging**: All validation errors are automatically logged.

4. **Early Validation**: Validate inputs as early as possible.

5. **Custom Validators**: Extend the validation system for domain-specific rules.

## Performance Considerations

- Validation functions are lightweight and fast
- Logging can be disabled by setting appropriate log levels
- Type checking uses Python's built-in `isinstance()` for efficiency