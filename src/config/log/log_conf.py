import logging
from pymodbus.logging import pymodbus_apply_logging_config

pymodbus_apply_logging_config(
    level=logging.DEBUG, log_file_name="../log/pymodbus.log")

pymodbus_internal_logger = logging.getLogger("pymodbus_internal")
if pymodbus_internal_logger is not None:
    pymodbus_internal_logger.setLevel(logging.WARNING)
    pymodbus_internal_logger.removeHandler(pymodbus_internal_logger.handlers[0])

pymodbus_logger = logging.getLogger("pymodbus.logging")
if pymodbus_logger is not None:
    pymodbus_logger.removeHandler(pymodbus_logger.handlers[0])
    for handler in pymodbus_logger.handlers:
        print("handler:", handler)
