"""Application state transitions backed by the SQLite repository."""

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Optional, Union

from .models import ConfigScan
from .repository import DoctorRepository


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DoctorService:
    def __init__(self, repository: DoctorRepository) -> None:
        self.repository = repository

    def get(self, key: str) -> Optional[str]:
        return self.repository.get_setting(key)

    def set(self, key: str, value: str) -> None:
        self.repository.set_setting(key, value, now())

    def installations(self) -> list[sqlite3.Row]:
        return self.repository.installations()

    def shortcuts(self) -> list[sqlite3.Row]:
        return self.repository.shortcuts()

    def installation(self, path: str) -> Optional[sqlite3.Row]:
        return self.repository.installation(path)

    def save_installation(self, path: str, version: str, modified: str, identity_hash: Optional[str], stamp: str) -> None:
        self.repository.save_installation(path, version, modified, identity_hash, stamp)

    def save_shortcut(self, path: str, kind: str, modified: str, stamp: str) -> None:
        self.repository.save_shortcut(path, kind, modified, stamp)

    def finish_scan(self, stamp: str) -> None:
        self.repository.commit()
        self.set("last_scan", stamp)

    def record_launch(self, kind: str, path: str, version: Optional[str], result: str,
                      pid: Optional[int] = None, code: Optional[int] = None,
                      event: Optional[str] = None, error: Optional[str] = None) -> None:
        stamp = now()
        hex_code = f"0x{code & 0xFFFFFFFF:08X}" if code is not None else None
        self.repository.save_launch(stamp, kind, path, version, result, pid, code, hex_code, event, error)
        if kind == "exe":
            self.repository.update_installation_launch(stamp, result, code, path)
            self.set("last_tested", path)
            if result == "running":
                self.set("last_working", path)
        self.repository.commit()

    def record_config_scan(self, stamp: str, item: ConfigScan) -> None:
        self.repository.save_config_scan(stamp, str(item["path"]), int(item["valid"]), int(item["null"]), item["error"])

    def record_backup(self, original: Path, backup: Path, renamed: Path, result: str, error: Optional[str]) -> None:
        self.repository.save_backup(now(), str(original), str(backup), str(renamed), result, error)

    def record_network_test(self, host: str, addresses: Optional[list[str]] = None,
                            error: Optional[str] = None) -> None:
        self.repository.save_network_test(now(), host, int(error is None), json.dumps(addresses or []), error)

    def commit(self) -> None:
        self.repository.commit()

    def launch_history(self) -> list[sqlite3.Row]:
        return self.repository.launch_history()

    def report(self) -> dict[str, Union[list[dict[str, object]], str]]:
        return {**self.repository.report(), "generated": now()}