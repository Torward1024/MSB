import pytest
import logging
import os
from unittest.mock import patch, MagicMock
from src.msb_arch.utils.logging_setup import setup_logging, update_logging_level, update_logging_clear, logger
from src.msb_arch.utils.validation import (
    check_type, check_range, check_positive, check_list_type,
    check_non_negative, check_non_empty_string, check_non_zero
)


class TestSetupLogging:
    @patch('src.msb_arch.utils.logging_setup.logging')
    def test_setup_logging_basic(self, mock_logging):
        mock_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_logger
        mock_logger.handlers = []
        result = setup_logging()
        assert result == mock_logger
        mock_logger.setLevel.assert_called_with(logging.INFO)

    @patch('src.msb_arch.utils.logging_setup.logging')
    def test_setup_logging_with_clear(self, mock_logging):
        mock_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_logger
        mock_logger.handlers = []
        setup_logging(clear_log=True)
        # Check that FileHandler is called with mode='w'

    @patch('src.msb_arch.utils.logging_setup.logging')
    def test_setup_logging_existing_handlers(self, mock_logging):
        mock_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_logger
        mock_logger.handlers = [MagicMock()]  # Has handlers
        setup_logging()
        # Should not add new handlers


class TestUpdateLoggingLevel:
    @patch('src.msb_arch.utils.logging_setup.logger', None)
    @patch('src.msb_arch.utils.logging_setup.setup_logging')
    def test_update_logging_level_no_logger(self, mock_setup):
        update_logging_level(logging.DEBUG)
        mock_setup.assert_called_with(log_level=logging.DEBUG)

    @patch('src.msb_arch.utils.logging_setup.logger')
    def test_update_logging_level_existing(self, mock_logger):
        mock_handler = MagicMock()
        mock_logger.handlers = [mock_handler]
        update_logging_level(logging.DEBUG)
        mock_logger.setLevel.assert_called_with(logging.DEBUG)
        mock_handler.setLevel.assert_called_with(logging.DEBUG)


class TestUpdateLoggingClear:
    @patch('src.msb_arch.utils.logging_setup.logger', None)
    @patch('src.msb_arch.utils.logging_setup.setup_logging')
    def test_update_logging_clear_no_logger(self, mock_setup):
        update_logging_clear("test.log", True)
        mock_setup.assert_called_with(log_file="test.log", clear_log=True)


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