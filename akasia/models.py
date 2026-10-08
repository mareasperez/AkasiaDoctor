"""Structured results shared by diagnostics and persistence."""

from pathlib import Path
from typing import Optional, TypedDict


class ConfigScan(TypedDict):
    path: Path
    valid: bool
    null: bool
    error: Optional[str]