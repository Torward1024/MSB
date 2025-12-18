import pytest
import subprocess
import sys

def test_run_all_tests():
    """
    Runs all unit, integration, and performance tests using pytest.
    Checks successful execution of all tests and prints the results report.
    """
    # Run pytest for all tests in the tests/ directory
    # Exclude test_all.py itself to avoid recursion
    result = subprocess.run([
        sys.executable, '-m', 'pytest',
        '--tb=short',  # Короткий traceback
        '--disable-warnings',  # Отключаем предупреждения для чистоты вывода
        'tests/test_basecontainer.py',
        'tests/test_baseentity.py',
        'tests/test_manipulator.py',
        'tests/test_project.py',
        'tests/test_super.py',
        'tests/test_utils_functions.py',
        'tests/integration/test_integration.py',
        'tests/performance/test_performance.py'
    ], capture_output=True, text=True)

    # Print the results report
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)

    # Check for successful execution
    assert result.returncode == 0, f"Some tests failed. Exit code: {result.returncode}"