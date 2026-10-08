"""Persistent diagnostics for failures in Akasia Doctor itself."""

import datetime as dt
import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

from .config import AppPaths


LOGGER_NAME = "akasia_doctor"


class DailyFileHandler(logging.FileHandler):
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.current_day = dt.date.today()
        super().__init__(directory / f"doctor-{self.current_day:%Y-%m-%d}.log", encoding="utf-8")
        self._prune(self.current_day)

    def emit(self, record: logging.LogRecord) -> None:
        day = dt.datetime.fromtimestamp(record.created).date()
        if day != self.current_day:
            if self.stream is not None:
                self.stream.close()
            self.current_day = day
            self.baseFilename = os.path.abspath(self.directory / f"doctor-{day:%Y-%m-%d}.log")
            self.stream = self._open()
            self._prune(day)
        super().emit(record)

    def _prune(self, day: dt.date) -> None:
        cutoff = day - dt.timedelta(days=14)
        for path in self.directory.glob("doctor-????-??-??.log"):
            try:
                log_day = dt.date.fromisoformat(path.stem[len("doctor-"):])
                if log_day < cutoff:
                    path.unlink(missing_ok=True)
            except (ValueError, OSError):
                continue


def configure_logging(paths: AppPaths) -> logging.Logger:
    paths.logs.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        if isinstance(handler, (DailyFileHandler, RotatingFileHandler, TimedRotatingFileHandler)):
            logger.removeHandler(handler)
            handler.close()
    handler = DailyFileHandler(paths.logs)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger