# MSB Architecture Tests

This document describes the test structure, test types, tools used, and running instructions for the MSB Architecture project.

## Test Structure

Tests are organized in the following hierarchical structure:

```
tests/
├── __init__.py
├── test_*.py                    # Unit-тесты для отдельных модулей
├── integration/
│   ├── __init__.py
│   └── test_integration.py      # Интеграционные тесты
└── performance/
    ├── __init__.py
    └── test_performance.py      # Performance-тесты
```

### File Descriptions

- **test_baseentity.py**: Unit tests for the `BaseEntity` class
- **test_basecontainer.py**: Unit tests for the `BaseContainer` class
- **test_manipulator.py**: Unit tests for the `Manipulator` class
- **test_super.py**: Unit tests for the `Super` class
- **test_project.py**: Unit tests for the `Project` class
- **test_utils_functions.py**: Unit tests for utility functions
- **integration/test_integration.py**: Integration tests for interactions between components (Manipulator, Super, Project, BaseContainer)
- **performance/test_performance.py**: Performance tests for serialization, caching, and operations

## Test Types

### Unit Tests
Test individual components in isolation:
- Object initialization validation
- Data type validation
- Method testing (get, set, clone, etc.)
- Error and exception handling
- Serialization and deserialization

### Integration Tests
Test interactions between components:
- Operation registration in Manipulator
- Request processing through Super classes
- Serialization of complex structures (nested objects, containers)
- Working with Project and BaseContainer

### Performance Tests
Measure performance of key operations:
- Serialization/deserialization of large structures
- to_dict/from_dict caching
- Manipulator operation performance
- Super.execute execution time

## Tools Used

### pytest
Main framework for running tests. Supports:
- Fixtures for setting up test data
- Test parametrization
- Test marking
- Detailed execution reports

### pytest fixtures
Used for creating and configuring test objects:
- `test_entity`: basic test BaseEntity object
- `test_container`: test container
- `test_project`: test project
- `manipulator_with_super`: configured manipulator with registered operation

### unittest.mock
Used for:
- Mocking dependencies
- Patching methods and functions
- Testing logging
- Simulating external calls

## Running Instructions

### Run all tests
```bash
pytest
```

### Run unit tests
```bash
pytest tests/
```

### Run integration tests
```bash
pytest tests/integration/
```

### Run performance tests
```bash
pytest tests/performance/
```

### Run a specific test file
```bash
pytest tests/test_baseentity.py
```

### Run with additional information
```bash
pytest -v  # verbose output
pytest -s  # show print statements
pytest --tb=short  # shorter traceback
```

### Run with code coverage
```bash
pytest --cov=src/msb_arch --cov-report=html
```

### Run only specific test types
```bash
pytest -k "performance"  # only performance tests
pytest -k "test_to_dict"  # tests with specific name
```

## Notes

- All tests are written using pytest and are compatible with Python 3.12+
- Performance tests use timeit for accurate time measurement
- Integration tests verify correct component interactions
- Tests include error handling and edge case validation