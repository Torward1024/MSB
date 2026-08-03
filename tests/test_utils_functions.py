import pytest
import logging
import os
from unittest.mock import patch, MagicMock
from msb_arch.utils.logging_setup import setup_logging, update_logging_level, update_logging_clear, logger
from msb_arch.utils.validation import (
    check_type, check_range, check_positive, check_list_type,
    check_non_negative, check_non_empty_string, check_non_zero
)


@pytest.fixture
def pristine_logger():
    """Restore the package logger after a test reconfigures it."""
    saved_handlers = logger.handlers[:]
    saved_level = logger.level
    yield logger
    for handler in logger.handlers[:]:
        if handler not in saved_handlers:
            logger.removeHandler(handler)
            handler.close()
    logger.handlers[:] = saved_handlers
    logger.setLevel(saved_level)


class TestLibraryLoggingHygiene:
    """A library must not configure logging for the application embedding it.

    Import-time side effects are checked in a clean interpreter: pytest's own logging
    plugin attaches handlers to the root logger, so they cannot be observed in-process.
    """

    def _import_in_clean_interpreter(self, tmp_path, probe):
        import subprocess
        import sys
        script = (
            "import logging, os, sys\n"
            "before = list(logging.getLogger().handlers)\n"
            "import msb_arch\n"
            f"{probe}\n"
        )
        result = subprocess.run([sys.executable, "-c", script], capture_output=True,
                                text=True, cwd=str(tmp_path))
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def test_importing_does_not_touch_the_root_logger(self, tmp_path):
        probe = "print(list(logging.getLogger().handlers) == before)"
        assert self._import_in_clean_interpreter(tmp_path, probe) == "True"

    def test_importing_does_not_create_a_log_file(self, tmp_path):
        probe = "print(os.listdir('.'))"
        assert self._import_in_clean_interpreter(tmp_path, probe) == "[]"

    def test_the_package_logger_is_named_and_silent_by_default(self):
        assert logger.name == "msb_arch"
        assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)


class TestSetupLogging:
    def test_setup_logging_configures_the_package_logger(self, pristine_logger, tmp_path):
        log_file = tmp_path / "msb.log"
        result = setup_logging(log_file=str(log_file), log_level=logging.DEBUG)
        assert result is pristine_logger
        assert result.level == logging.DEBUG
        assert any(isinstance(h, logging.FileHandler) for h in result.handlers)
        # the handlers land on the package logger, never on root
        assert not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file)
                       for h in logging.getLogger().handlers)

    def test_setup_logging_writes_to_the_requested_file(self, pristine_logger, tmp_path):
        log_file = tmp_path / "msb.log"
        setup_logging(log_file=str(log_file), log_level=logging.INFO)
        pristine_logger.info("hello from the test")
        for handler in pristine_logger.handlers:
            handler.flush()
        assert "hello from the test" in log_file.read_text(encoding="utf-8")

    def test_setup_logging_does_not_duplicate_handlers(self, pristine_logger, tmp_path):
        log_file = tmp_path / "msb.log"
        setup_logging(log_file=str(log_file))
        first = len(pristine_logger.handlers)
        setup_logging(log_file=str(log_file))
        assert len(pristine_logger.handlers) == first


class TestUpdateLoggingLevel:
    def test_update_logging_level_applies_to_logger_and_handlers(self, pristine_logger, tmp_path):
        setup_logging(log_file=str(tmp_path / "msb.log"), log_level=logging.INFO)
        update_logging_level(logging.DEBUG)
        assert pristine_logger.level == logging.DEBUG
        assert all(h.level == logging.DEBUG for h in pristine_logger.handlers)


class TestUpdateLoggingClear:
    def test_update_logging_clear_truncates_the_file(self, pristine_logger, tmp_path):
        log_file = tmp_path / "msb.log"
        setup_logging(log_file=str(log_file), log_level=logging.INFO)
        pristine_logger.info("first run")
        for handler in pristine_logger.handlers:
            handler.flush()
        assert "first run" in log_file.read_text(encoding="utf-8")

        update_logging_clear(str(log_file), True)
        assert "first run" not in log_file.read_text(encoding="utf-8")

    def test_update_logging_clear_is_a_no_op_when_not_asked(self, pristine_logger, tmp_path):
        log_file = tmp_path / "msb.log"
        setup_logging(log_file=str(log_file), log_level=logging.INFO)
        before = len(pristine_logger.handlers)
        update_logging_clear(str(log_file), False)
        assert len(pristine_logger.handlers) == before


class TestCheckType:
    def test_check_type_valid(self):
        check_type("test", str, "param")  # Should not raise

    def test_check_type_none(self):
        check_type(None, str, "param")  # Should not raise

    @pytest.mark.parametrize("value,expected", [
        (123, str),
        ([], int),
        ({}, list),
    ])
    def test_check_type_invalid(self, value, expected):
        with pytest.raises(TypeError):
            check_type(value, expected, "param")

    def test_check_type_tuple(self):
        check_type(123, (int, float), "param")  # Should not raise


class TestCheckRange:
    def test_check_range_valid(self):
        check_range(5.0, 0.0, 10.0, "param")  # Should not raise

    @pytest.mark.parametrize("value", [-1, 11])
    def test_check_range_out_of_range(self, value):
        with pytest.raises(ValueError):
            check_range(value, 0.0, 10.0, "param")

    @pytest.mark.parametrize("value", ["string", None])
    def test_check_range_invalid_type(self, value):
        with pytest.raises(TypeError):
            check_range(value, 0.0, 10.0, "param")


class TestCheckPositive:
    def test_check_positive_valid(self):
        check_positive(1.0, "param")  # Should not raise

    @pytest.mark.parametrize("value", [0, -1])
    def test_check_positive_invalid(self, value):
        with pytest.raises(ValueError):
            check_positive(value, "param")

    @pytest.mark.parametrize("value", ["string", None])
    def test_check_positive_invalid_type(self, value):
        with pytest.raises(TypeError):
            check_positive(value, "param")


class TestCheckListType:
    def test_check_list_type_valid(self):
        check_list_type(["a", "b"], str, "param")  # Should not raise

    def test_check_list_type_tuple(self):
        check_list_type(("a", "b"), str, "param")  # Should not raise

    def test_check_list_type_invalid_container(self):
        with pytest.raises(TypeError):
            check_list_type("string", str, "param")

    def test_check_list_type_invalid_item(self):
        with pytest.raises(TypeError):
            check_list_type([1, "b"], str, "param")


class TestCheckNonNegative:
    def test_check_non_negative_valid(self):
        check_non_negative(0.0, "param")  # Should not raise
        check_non_negative(1.0, "param")  # Should not raise

    def test_check_non_negative_negative(self):
        with pytest.raises(ValueError):
            check_non_negative(-1.0, "param")

    @pytest.mark.parametrize("value", ["string", None])
    def test_check_non_negative_invalid_type(self, value):
        with pytest.raises(TypeError):
            check_non_negative(value, "param")


class TestCheckNonEmptyString:
    def test_check_non_empty_string_valid(self):
        check_non_empty_string("test", "param")  # Should not raise

    @pytest.mark.parametrize("value", ["", "   ", "\t"])
    def test_check_non_empty_string_empty(self, value):
        with pytest.raises(ValueError):
            check_non_empty_string(value, "param")

    @pytest.mark.parametrize("value", [123, None, []])
    def test_check_non_empty_string_invalid_type(self, value):
        with pytest.raises(TypeError):
            check_non_empty_string(value, "param")


class TestCheckNonZero:
    def test_check_non_zero_valid(self):
        check_non_zero(1.0, "param")  # Should not raise
        check_non_zero(-1.0, "param")  # Should not raise

    def test_check_non_zero_zero(self):
        with pytest.raises(ValueError):
            check_non_zero(0.0, "param")

    @pytest.mark.parametrize("value", ["string", None])
    def test_check_non_zero_invalid_type(self, value):
        with pytest.raises(TypeError):
            check_non_zero(value, "param")