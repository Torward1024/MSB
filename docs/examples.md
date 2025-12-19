# MSB Framework Examples

This document provides comprehensive examples of using the MSB Framework for various scenarios.

## Basic Entity and Container Usage

### Creating Entities

```python
from msb_arch.base import BaseEntity

class Person(BaseEntity):
    name: str
    age: int
    email: str = "default@example.com"

# Create instances
person1 = Person(name="Alice", age=30)
person2 = Person(name="Bob", age=25, email="bob@example.com")

print(person1.name)      # "Alice"
print(person1.isactive)  # True
print(person2.email)     # "bob@example.com"
```

### Using Containers

```python
from msb_arch.base import BaseContainer

# Create typed container
class MyContainer(BaseContainer[Person]):
    pass

people = MyContainer(name="people")

# Add items
people.add(person1)
people.add(person2)

# Access items
alice = people["Alice"]
print(alice.age)  # 30

# Query items
adults = people.get_by_value({"age": 25})
print(len(adults))  # 1

# Iterate over items
for person in people:
    print(f"{person.name}: {person.age}")
```

## Advanced Entity Features

### Nested Entities

```python
from msb_arch.base import BaseEntity
class Address(BaseEntity):
    street: str
    city: str
    zip_code: str

class Company(BaseEntity):
    name: str
    address: Address
    employee_count: int

# Create nested structure
address = Address(name='address1', street="123 Business St", city="Tech City", zip_code="12345")
company = Company(name="Tech Corp", address=address, employee_count=50)

# Access nested properties
print(company.address.city)  # "Tech City"

# Serialize with nesting
data = company.to_dict()
print(data["address"]["city"])  # "Tech City"
```

### Serialization and Deserialization

```python
# Serialize to dict
person_dict = person1.to_dict()
print(person_dict)
# {'name': 'Alice', 'isactive': True, 'age': 30, 'email': 'default@example.com', 'type': 'Person'}

# Deserialize from dict
person_copy = Person.from_dict(person_dict)
print(person_copy.name)  # "Alice"

# Container serialization
people_data = people.to_dict()
print(people_data["items"]["Alice"]["age"])  # 30

# Container deserialization
people_copy = MyContainer.from_dict(people_data)
```

## Project Management

### Basic Project

```python
from msb_arch.super import Project
from msb_arch.base import BaseEntity

class Task(BaseEntity):
    title: str
    priority: int
    completed: bool = False

class TaskProject(Project):
    _item_type = Task

    def create_item(self, item_code="TASK"):
        self.add_item(Task(name=item_code, title=f"New {item_code}", priority=1))
    
    def from_dict():
        pass

# Create project
project = TaskProject(name="my_tasks")

# Add tasks
task1 = Task(name='DesignSystemTask', title="Design system", priority=3)
project.add_item(task1)
project.create_item("Implement")  # Creates and adds automatically

# Manage tasks
project.activate_item("DesignSystemTask")
high_priority = project.get_active_items()
print(len(high_priority))  # 2
```

### Project Operations

```python
# Bulk operations
project.deactivate_all()
inactive = project.get_inactive_items()
print(len(inactive))  # 2

# Query by attributes
urgent_tasks = project._items.get_by_value({"priority": 3})
print(len(urgent_tasks))  # 1

# Project serialization
project_data = project.to_dict()
print(project_data["name"])  # "my_tasks"
print(len(project_data["items"]))  # 2
```

## Operation Handling with Super

### Calculator Operations

```python
from msb_arch.super import Super

class Calculator(Super):
    _operation = "calculate" # if you use without Manipulator

    def _calculate_add(self, obj, attributes):
        """Add two numbers"""
        return attributes.get("a", 0) + attributes.get("b", 0)

    def _calculate_multiply(self, obj, attributes):
        """Multiply two numbers"""
        return attributes.get("a", 1) * attributes.get("b", 1)

    def _calculate_power(self, obj, attributes):
        """Calculate power"""
        return attributes.get("base", 1) ** attributes.get("exp", 1)

# Use calculator
calc = Calculator()

# Execute operations
result1 = calc.execute(None, {"method": "add", "a": 5, "b": 3})
print(result1["result"])  # 8

result2 = calc.execute(None, {"method": "power", "base": 2, "exp": 3})
print(result2["result"])  # 8
```

### Data Processor

```python
from msb_arch.super import Super

class DataProcessor(Super):
    _operation = 'process'
    
    def _process_string_upper(self, obj, attributes):
        return str(obj).upper()

    def _process_string_lower(self, obj, attributes):
        return str(obj).lower()

    def _process_list_sort(self, obj, attributes):
        if isinstance(obj, list):
            return sorted(obj)
        return obj

processor = DataProcessor()

# Process different data types
upper_result = processor.execute("hello", {"method": "string_upper"})
print(upper_result["result"])  # "HELLO"

sort_result = processor.execute([3, 1, 4, 1, 5], {"method": "list_sort"})
print(sort_result["result"])  # [1, 1, 3, 4, 5]
```

## Manipulator Orchestration

### Basic Setup

```python
from msb_arch.mega import Manipulator
from msb_arch.super import Super

class DataProcessor(Super):
    OPERATION = 'process' # if you Manipulator
    
    def _process_string_upper(self, obj, attributes):
        return str(obj).upper()

    def _process_string_lower(self, obj, attributes):
        return str(obj).lower()

    def _process_list_sort(self, obj, attributes):
        if isinstance(obj, list):
            return sorted(obj)
        return obj
    
class Calculator(Super):
    OPERATION = "calculate" # if you Manipulator

    def _calculate_add(self, obj, attributes):
        """Add two numbers"""
        return attributes.get("a", 0) + attributes.get("b", 0)

    def _calculate_multiply(self, obj, attributes):
        """Multiply two numbers"""
        return attributes.get("a", 1) * attributes.get("b", 1)

    def _calculate_power(self, obj, attributes):
        """Calculate power"""
        return attributes.get("base", 1) ** attributes.get("exp", 1)

# Create manipulator
manipulator = Manipulator()

# Register operations
manipulator.register_operation(Calculator())
manipulator.register_operation(DataProcessor())

# Process requests
add_result = manipulator.process_request({
    "operation": "calculate",
    "obj": int,
    "attributes": {"method": "add", "a": 10, "b": 20}
})
print(add_result["result"])  # 30

upper_result = manipulator.process_request({
    "operation": "process",
    "obj": "world",
    "attributes": {"method": "string_upper"}
})
print(upper_result["result"])  # "WORLD"
```

### Using Facade Methods

```python
# Facade methods are created automatically
calc_result = manipulator.calculate(int, a=5, b=7, method="multiply")
print(calc_result)  # 35

process_result = manipulator.process(obj="hello world", method="string_lower")
print(process_result)  # "hello world"
```

### Batch Processing

```python
# Process multiple operations
batch_request = {
    "calc1": {
        "operation": "calculate",
        "obj": int,
        "attributes": {"method": "add", "a": 1, "b": 2}
    },
    "calc2": {
        "operation": "calculate",
        "obj": int,
        "attributes": {"method": "multiply", "a": 3, "b": 4}
    },
    "process1": {
        "operation": "process",
        "obj": "TEST",
        "attributes": {"method": "string_lower"}
    }
}

batch_results = manipulator.process_request(batch_request)
print(batch_results["calc1"]["result"])    # 3
print(batch_results["calc2"]["result"])    # 12
print(batch_results["process1"]["result"]) # "test"
```

## Complex Application Example

### E-commerce System

```python
from msb_arch.base import BaseEntity, BaseContainer
from msb_arch.super import Project, Super
from msb_arch.mega import Manipulator

# Define entities
class Product(BaseEntity):
    name: str
    price: float
    category: str
    stock: int

class Customer(BaseEntity):
    name: str
    email: str
    loyalty_points: int = 0

class Order(BaseEntity):
    customer: Customer
    products: list[Product]
    total: float
    status: str = "pending"

class Products(BaseContainer[Product]):
    pass

class Customers(BaseContainer[Customer]):
    pass

class Orders(BaseContainer[Order]):
    pass

# Define operations
class OrderProcessor(Super):
    OPERATION = "order"

    def _order_create(self, obj, attributes):
        customer_name = attributes["customer"]
        product_names = attributes["products"]
        customer = obj["customers"].get(customer_name)
        products = [obj["products"].get(name) for name in product_names]

        for name in product_names:
            product = obj["products"].get(name)
            if product:
                products.append(product)

        if not customer or len(products) != len(product_names):
            return False

        total = sum(p.price for p in products)
        order = Order(name='test', customer=customer, products=products, total=total)
        return order

    def _order_process_payment(self, obj, attributes):
        order_id = attributes.get("order_id")
        # Payment processing logic here
        return f"Payment processed for order {order_id}"

# Create system components
products = Products(name="products")
customers = Customers(name="customers")
orders = Orders(name="orders")

# Add sample data
products.add(Product(name="Laptop", price=999.99, category="Electronics", stock=10))
products.add(Product(name="Book", price=19.99, category="Education", stock=50))
customers.add(Customer(name="John Doe", email="john@example.com", loyalty_points=100))

# Create manipulator and register operations
manipulator = Manipulator()
manipulator.register_operation(OrderProcessor())

# Set managing objects
manipulator.set_managing_object({"products": products, "customers": customers, "orders": orders})


# Create order
order_result = manipulator.order(
    customer="John Doe",
    products=["Laptop", "Book"],
    method="create",
    raise_on_error=False
)

if order_result["status"]:
    order = order_result["result"]
    print(f"Order created: ${order.total}")
    orders.add(order)
else:
    print(f"Order creation failed: {order_result.get('error', 'Unknown error')}")
```

## Error Handling Examples

### Validation Errors

```python
try:
    # This will fail validation
    invalid_person = Person(name="", age=-5)
except ValueError as e:
    print(f"Validation error: {e}")

try:
    # Type mismatch
    wrong_type = Person(name="Test", age="not_a_number")
except TypeError as e:
    print(f"Type error: {e}")
```

### Operation Errors

```python
# Handle operation errors gracefully
result = manipulator.process_request({
    "operation": "nonexistent",
    "attributes": {}
})

if not result["status"]:
    print(f"Operation failed: {result['error']}")

# Or use raise_on_error=False
result = manipulator.calculate(a=1, b=2, method="invalid_method", raise_on_error=False)
if not result["status"]:
    print(f"Method error: {result['error']}")
```

## Performance Optimization

### Using Caching

```python
# Enable caching for entities
person = Person(name="Cached", age=25, use_cache=True)

# First serialization
data1 = person.to_dict()

# Modify and serialize again (uses cache if no changes)
person.age = 26
data2 = person.to_dict()

# Clear cache when needed
person._invalidate_cache()
```

### Batch Operations for Performance

```python
# Instead of multiple individual calls
results = []
for i in range(10):
    result = manipulator.calculate(int, a=i, b=i+1, method="add")
    results.append(result)

# Use batch processing
batch = {}
for i in range(10):
    batch[f"calc_{i}"] = {
        "operation": "calculate",
        "obj": int,
        "attributes": {"method": "add", "a": i, "b": i+1}
    }

batch_results = manipulator.process_request(batch)
```

## Integration with External Systems

### REST API Example

```python
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

# Framework setup
manipulator = Manipulator()
# ... register operations ...

@app.route('/api/operation', methods=['POST'])
def handle_operation():
    try:
        req_data = request.get_json()

        # Convert to framework format
        fw_request = {
            "operation": req_data["operation"],
            "obj": req_data.get("obj"),
            "attributes": req_data.get("attributes", {})
        }

        # Process with framework
        result = manipulator.process_request(fw_request)

        # Convert back to API format
        if result["status"]:
            return jsonify({
                "success": True,
                "data": result["result"],
                "method": result["method"]
            })
        else:
            return jsonify({
                "success": False,
                "error": result["error"]
            }), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
```

### Database Integration

```python
import sqlite3

class DatabaseManager(Super):
    def __init__(self, db_path=":memory:"):
        super().__init__()
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                type TEXT,
                data TEXT
            )
        ''')

    def _db_save(self, obj, attributes):
        """Save entity to database"""
        if hasattr(obj, 'to_dict'):
            data = json.dumps(obj.to_dict())
            self.conn.execute(
                'INSERT OR REPLACE INTO entities (name, type, data) VALUES (?, ?, ?)',
                (obj.name, obj.__class__.__name__, data)
            )
            self.conn.commit()
            return f"Saved {obj.name}"

    def _db_load(self, obj, attributes):
        """Load entity from database"""
        name = attributes.get("name")
        cursor = self.conn.execute(
            'SELECT data FROM entities WHERE name = ?',
            (name,)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

# Usage
db_manager = DatabaseManager("entities.db")
manipulator.register_operation(db_manager)

# Save entity
manipulator.db(obj=person1, method="save")

# Load entity
loaded_data = manipulator.db(method="load", name="Alice")
if loaded_data:
    loaded_person = Person.from_dict(loaded_data)
```

These examples demonstrate the flexibility and power of the MSB Framework for building complex, maintainable applications with strong typing, validation, and operation orchestration.