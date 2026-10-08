"""Application paths and environment configuration."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union

from dotenv import dotenv_values


@dataclass(frozen=True)
class AppPaths:
    data: Path

    @property
    def database(self):
        return self.data / "akasia_doctor.db"

    @property
    def backups(self):
        return self.data / "Backups"

    @property
    def reports(self):
        return self.data / "Reports"

    @property
    def logs(self):
        return self.data / "Logs"


def resolve_paths(data_dir: Optional[Union[str, Path]] = None,
                  environ: Optional[Mapping[str, str]] = None,
                  env_file: Optional[Path] = None) -> AppPaths:
    environment = os.environ if environ is None else environ
    if env_file is None:
        env_file = (Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent) / ".env"
    file_values = dotenv_values(env_file)
    configured = data_dir if data_dir is not None else (environment.get("AKASIA_DOCTOR_DATA_DIR") or file_values.get("AKASIA_DOCTOR_DATA_DIR"))
    if configured:
        return AppPaths(Path(configured).expanduser().resolve())
    local = Path(environment.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    return AppPaths(local / "AkasiaDoctor")