import pytest
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent

SUITES = [
    'test_basecontainer.py',
    'test_baseentity.py',
    'test_manipulator.py',
    'test_project.py',
    'test_super.py',
    'test_utils_functions.py',
    'integration/test_integration.py',
    'performance/test_performance.py',
]

def test_run_all_tests():
    """
    Runs all unit, integration, and performance tests using pytest.
    Checks successful execution of all tests and prints the results report.

    Notes:
        - Paths are resolved from this file rather than from the working directory, so the
          suite runs the same wherever it is started from.
        - The subprocess manipulates no import path: it exercises the installed msb_arch,
          which is the point of running the tests against a built package.
    """
    # Run pytest for all tests in the tests/ directory
    # Exclude test_all.py itself to avoid recursion
    result = subprocess.run([
        sys.executable, '-m', 'pytest',
        '--tb=short',
        '--disable-warnings',
        *[str(TESTS_DIR / suite) for suite in SUITES]
    ], capture_output=True, text=True)

    # Print the results report
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)

    # Check for successful execution
    assert result.returncode == 0, f"Some tests failed. Exit code: {result.returncode}"
