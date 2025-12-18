# MSB Architecture

Mega-Super-Base (MSB) is a flexible and extensible architecture for Python applications, built around base classes (`BaseEntity`, `BaseContainer`), super classes (`Super`, `Project`), and a managing class (`Manipulator`). It provides a robust framework for managing entities and operations with type safety and serialization support.

## Installation

```bash
pip install msb_arch
```

## Usage
```python
from msb.base.baseentity import BaseEntity
from msb.super.project import Project

class MyEntity(BaseEntity):
    value: int

class MyProject(Project):
    _item_type = MyEntity

    def create_item(self, item_code: str = "ITEM_DEFAULT", isactive: bool = True) -> None:
        item = MyEntity(name=item_code, isactive=isactive, value=42)
        self.add_item(item)

project = MyProject(name="MyProject")
project.create_item("item1")
print(project.get_item("item1").to_dict())
# Output: {'name': 'item1', 'isactive': True, 'type': 'MyEntity', 'value': 42}
```

## License

MSB is licensed under the [MSB Software License](LICENSE) for non-commercial and research use, allowing free use, modification, and distribution for non-commercial purposes with proper attribution.

For commercial use, a separate license with royalty terms is required. Please contact [almax1024@gmail.com](mailto:almax1024@gmail.com) for details.