# MSB Architecture

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MSB%20Software%20License-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](https://github.com/Torward1024/MSB)

Mega-Super-Base (MSB) - a flexible and extensible architecture for Python applications, providing a modular system for managing entities, containers, operations, and projects with built-in type safety, serialization, and logging.

## Features

- **Typed Entity Management**: Automatic attribute validation and serialization.
- **Containers for Collections**: Support for queries and bulk operations on entities.
- **Flexible Operation System**: Through Super-classes with method resolution.
- **Projects as High-Level Containers**: High-level data organization.
- **Universal Serialization**: Support for nested objects and cyclic references.
- **Integrated Logging and Validation**: Full support for logging and data validation.
- **No External Dependencies**: Requires only Python >= 3.12.

## Installation

```bash
pip install msb_arch
```

## Quick Start

```python
from msb_arch.base.baseentity import BaseEntity
from msb_arch.super.project import Project

class MyEntity(BaseEntity):
    value: int

class MyProject(Project):
    _item_type = MyEntity

    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        item = MyEntity(name=item_code, isactive=isactive, value=42)
        self.add_item(item)
    def from_dict():
        pass

project = MyProject(name="MyProject")
project.create_item("item1")
print(project.get_item("item1").to_dict())
# Output: {'name': 'item1', 'isactive': True, 'type': 'MyEntity', 'value': 42}
```

## Architecture

The project is divided into 4 modules:

- **Base**: [`src/msb_arch/base/baseentity.py`](src/msb_arch/base/baseentity.py), [`src/msb_arch/base/basecontainer.py`](src/msb_arch/base/basecontainer.py) - base classes for entities and containers.
- **Super**: [`src/msb_arch/super/super.py`](src/msb_arch/super/super.py), [`src/msb_arch/super/project.py`](src/msb_arch/super/project.py) - operation handlers and project management.
- **Mega**: [`src/msb_arch/mega/manipulator.py`](src/msb_arch/mega/manipulator.py) - central orchestrator for operations.
- **Utils**: [`src/msb_arch/utils/logging_setup.py`](src/msb_arch/utils/logging_setup.py), [`src/msb_arch/utils/validation.py`](src/msb_arch/utils/validation.py) - utilities for logging and validation.

Main classes:
- **BaseEntity**: Abstract class for entities with type validation, serialization, and caching.
- **BaseContainer[T]**: Generic container for BaseEntity collections with query and operation support.
- **Super**: Abstract class for operation handlers with method resolution.
- **Project**: Class for managing projects as entity containers.
- **Manipulator**: Central class for operation registration and request processing.

## API

Complete API reference is available in [`docs/api.md`](docs/api.md).

## Examples

Practical usage examples are available in [`docs/examples.md`](docs/examples.md).

## Testing

The project includes a complete set of unit, integration, and performance tests using pytest. Tests are located in the `tests/` directory and cover all modules with high coverage rates.

To run tests:

```bash
pytest tests/
```

## License

MSB is licensed under the [MSB Software License](LICENSE) for non-commercial and research use, allowing free use, modification, and distribution for non-commercial purposes with attribution.

For commercial use, a separate royalty-bearing license is required. Please contact [almax1024@gmail.com](mailto:almax1024@gmail.com) for details.

## Contacts

- **Author**: Alexey Rudnitskiy
- **Email**: [almax1024@gmail.com](mailto:almax1024@gmail.com)
- **Repository**: [https://github.com/Torward1024/MSB](https://github.com/Torward1024/MSB)
- **Version**: 0.1.0