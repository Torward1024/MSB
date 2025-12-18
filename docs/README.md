# MSB (Mega-Super-Base) Framework Documentation

## Overview

The MSB Framework is a flexible and extensible architecture for building Python applications, based on a modular structure with four main components: **Base**, **Super**, **Mega**, and **Utils**. The framework provides tools for managing entities, containers, operations, and projects with built-in validation, serialization, and logging.

## Architecture

The framework consists of the following modules:

- [**Base**](modules/base.md) - Core classes for entities and containers
- [**Super**](modules/super.md) - Classes for operation handling and project management
- [**Mega**](modules/mega.md) - Classes for object manipulation and request processing
- [**Utils**](modules/utils.md) - Utilities for logging and validation

## Key Features

- **Typed entities** with automatic attribute validation
- **Containers** for managing collections of entities
- **Operations** with a flexible request processing system
- **Projects** for organizing complex data structures
- **Serialization/deserialization** with support for nested objects
- **Logging** with configurable levels
- **Data validation** with detailed error messages

## Installation

```bash
pip install msb-arch
```

## Quick Start

```python
from msb_arch.base import BaseEntity, BaseContainer
from msb_arch.super import Project
from msb_arch.mega import Manipulator

# Create an entity
class MyEntity(BaseEntity):
    name: str
    value: int

entity = MyEntity(name="test", value=42)

# Create a container
container = BaseContainer[MyEntity](name="my_container")
container.add(entity)

# Create a project
class MyProject(Project):
    pass

project = MyProject(name="my_project")
project.add_item(entity)

# Use manipulator
manipulator = Manipulator()
# ... register operations and process requests
```

## Documentation

- [Architecture](architecture.md) - Detailed architecture description and diagrams
- [Diagrams](diagrams.md) - Mermaid diagrams of classes and interactions
- [Examples](examples.md) - Usage examples of the framework
- [API Reference](api.md) - Complete API reference

## License

The project is distributed under the license decsribed in the [LICENSE](../LICENSE) file.