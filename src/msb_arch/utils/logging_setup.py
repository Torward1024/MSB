# utils/logging_setup.py
import logging

LOGGER_NAME = "msb_arch"

logger = logging.getLogger(LOGGER_NAME)
logger.addHandler(logging.NullHandler())

def setup_logging(log_file: str = "output.log", log_level: int = logging.INFO, clear_log: bool = False) -> logging.Logger:
    """Set up and configure logging for the system.

    Attaches file and console handlers to the package logger, using a consistent format for
    log messages. Allows specifying the logging level and whether to clear the log file on start.

    Args:
        log_file (str): Path to the log file. Defaults to "output.log".
        log_level (int): Logging level (e.g., logging.DEBUG, logging.INFO). Defaults to logging.INFO.
        clear_log (bool): If True, clears the log file before adding new logs. Defaults to False.

    Returns:
        logging.Logger: The configured logger instance.

    Notes:
        - Log format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s".
        - Handlers are added only if the logger has no configured handlers to avoid duplication.
        - If clear_log is True, the log file is truncated before adding new logs.
        - Calling this is optional and never happens on import. A library that configures
          logging by itself would create a file in the working directory and take over the
          handlers of the application embedding it; MSB only attaches a NullHandler and
          leaves every decision to the application.

    Examples:
        >>> from msb_arch import setup_logging
        >>> import logging
        >>> setup_logging(log_level=logging.DEBUG)   # opt in to the built-in configuration
    """
    logger.setLevel(log_level)

    if not any(not isinstance(handler, logging.NullHandler) for handler in logger.handlers):
        mode = 'w' if clear_log else 'a'
        fh = logging.FileHandler(log_file, mode=mode)
        fh.setLevel(log_level)

        ch = logging.StreamHandler()
        ch.setLevel(log_level)

        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger

def update_logging_level(log_level: int) -> None:
    """Update the logging level for the package logger and its handlers.

    Args:
        log_level (int): New logging level (e.g., logging.DEBUG, logging.INFO).

    Notes:
        - Updates the level of the package logger and all of its configured handlers.
    """
    logger.setLevel(log_level)
    for handler in logger.handlers:
        handler.setLevel(log_level)

def update_logging_clear(log_file: str, clear_log: bool) -> None:
    """Update the logging configuration to clear the log file if specified.

    Args:
        log_file (str): Path to the log file.
        clear_log (bool): If True, reconfigures the file handler to clear the log file.

    Notes:
        - Does nothing unless clear_log is True.
    """
    if not clear_log:
        return

    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
            handler.close()

    fh = logging.FileHandler(log_file, mode='w')
    fh.setLevel(logger.level)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.debug("Log file cleared due to clear_log=True")
