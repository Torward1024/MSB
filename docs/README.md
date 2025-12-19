# MSB (Mega-Super-Base) Framework Documentation

## Overview

The MSB Framework is a flexible and extensible architecture for building Python applications, based on a modular structure with four main components: **Base**, **Super**, **Mega**, and **Utils**. The framework provides tools for managing entities, containers, operations, and projects with built-in validation, serialization, caching, and logging.

## Architecture

The framework consists of the following modules:

- [**Base**](modules/base.md) - Core classes for entities and containers with type validation and serialization
- [**Super**](modules/super.md) - Classes for operation handling, method resolution, and project management
- [**Mega**](modules/mega.md) - Classes for object manipulation, request processing, and orchestration
- [**Utils**](modules/utils.md) - Utilities for logging setup and data validation

## Key Features

- **Typed entities** with automatic attribute validation and type checking
- **Generic containers** for managing collections of entities with bulk operations
- **Operation handlers** with flexible method resolution and caching
- **Projects** for organizing complex data structures with abstract factory patterns
- **Manipulator orchestration** for processing requests and managing operations
- **Bidirectional serialization** with support for nested objects and cyclic references
- **Configurable logging** with file and console handlers
- **Comprehensive validation** with detailed error messages and logging
- **Performance optimization** through caching and lazy loading

## Installation

```bash
pip install msb-arch
```

## Requirements

- Python 3.12+
- No external dependencies (uses only standard library)

## Quick Start

```python
from msb_arch.base import BaseEntity, BaseContainer
from msb_arch.super import Super
from msb_arch.mega import Manipulator

# Define an entity
class MyEntity(BaseEntity):
    name: str
    value: int
    description: str = "Default"

class MyContainer(BaseContainer[MyEntity]):
    pass

# Create instances
entity = MyEntity(name="test", value=42)

# Create a container
container = MyContainer(name="my_container")
container.add(entity)

# Define an operation handler
class Calculator(Super):
    OPERATION = "calculate"

    def _calculate_add(self, obj, attributes):
        return obj.value  + attributes.get("a", 0)

# Create manipulator and register operations
manipulator = Manipulator(entity)
manipulator.register_operation(Calculator())

# Process requests
result = manipulator.process_request({
    "operation": "calculate",
    "object": entity,
    "attributes": {"method": "add", "a": 5}
})
print(result["result"])  # 8

# Use facade methods
result = manipulator.calculate(entity, a=10, method="add")
print(result)  # 14
```

## Documentation

- [Architecture](architecture.md) - Detailed architecture description and design patterns
- [Diagrams](diagrams.md) - Mermaid diagrams of classes and interactions
- [Examples](examples.md) - Comprehensive usage examples
- [API Reference](api.md) - Complete API reference with parameters and types

## Version

Current version: 0.1.0

## License

The project is distributed under the license described in the [LICENSE](../LICENSE) file.