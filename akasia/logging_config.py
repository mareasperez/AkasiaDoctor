"""Persistent diagnostics for failures in Akasia Doctor itself."""

import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from .config import AppPaths


LOGGER_NAME = "akasia_doctor"


def configure_logging(paths: AppPaths) -> logging.Logger:
    paths.logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        if isinstance(handler, (RotatingFileHandler, TimedRotatingFileHandler)):
            logger.removeHandler(handler)
            handler.close()
    handler = TimedRotatingFileHandler(paths.logs / "doctor.log", when="midnight", backupCount=14, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger