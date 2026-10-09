"""ClickOnce discovery, launch diagnostics, and configuration recovery."""

import datetime as dt
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import traceback
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .config import AppPaths
from .logging_config import LOGGER_NAME
from .models import ConfigScan
from .service import DoctorService, now


IS_WINDOWS = os.name == "nt"
LOGGER = logging.getLogger(LOGGER_NAME)


def path_hash(path: Path) -> Optional[str]:
    found = re.findall(r"(?i)([0-9a-f]{16})(?=[\\/]|$)", str(path))
    return found[-1].lower() if found else None


def file_version(path: Path) -> str:
    if not IS_WINDOWS:
        return ""
    escaped = str(path).replace("'", "''")
    command = f"(Get-Item -LiteralPath '{escaped}').VersionInfo.FileVersion"
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.strip()
    except Exception:
        return ""


def shortcut_roots() -> list[Path]:
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    program_data = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
    candidates = [Path.home() / "Desktop", roaming / "Microsoft/Windows/Start Menu/Programs", program_data / "Microsoft/Windows/Start Menu/Programs"]
    return [path for path in candidates if path.exists()]


def windows_event() -> Optional[str]:
    if not IS_WINDOWS:
        return None
    try:
        result = subprocess.run(["wevtutil", "qe", "Application", "/rd:true", "/c:40", "/f:text"], capture_output=True, text=True, errors="replace", timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        for block in result.stdout.split("Event["):
            lower = block.lower()
            if "akasia" in lower and (".net runtime" in lower or "application error" in lower):
                return " ".join(block.split())[:4000]
    except Exception:
        pass
    return None


class DoctorOperations:
    def __init__(self, service: DoctorService, paths: AppPaths, local: Optional[Path] = None) -> None:
        self.service = service
        self.paths = paths
        self.local = local or Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))

    def scan(self) -> tuple[int, int]:
        stamp = now()
        count_exe = 0
        root = self.local / "Apps/2.0"
        if root.exists():
            for path in root.rglob("*.exe"):
                if "akasia" not in path.name.lower():
                    continue
                try:
                    modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
                    self.service.save_installation(str(path), file_version(path), modified, path_hash(path), stamp)
                    count_exe += 1
                except OSError:
                    pass
        count_shortcuts = 0
        for base in shortcut_roots():
            for path in base.rglob("*"):
                try:
                    if path.is_file() and "akasia" in path.name.lower() and path.suffix.lower() in {".appref-ms", ".lnk", ".application"}:
                        modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
                        self.service.save_shortcut(str(path), path.suffix.lower(), modified, stamp)
                        count_shortcuts += 1
                except OSError:
                    pass
        self.service.finish_scan(stamp)
        return count_exe, count_shortcuts

    def launch_exe(self, path_text: Optional[str]) -> str:
        row = self.service.installation(path_text) if path_text else None
        if not row or not Path(row["path"]).exists():
            return "Select an existing executable first."
        path = Path(row["path"])
        try:
            process = subprocess.Popen([str(path)], cwd=str(path.parent))
            time.sleep(4)
            code = process.poll()
            if code is None:
                self.service.record_launch("exe", str(path), row["version"], "running", process.pid)
                return f"Akasia is running. PID: {process.pid}"
            hex_code = f"0x{code & 0xFFFFFFFF:08X}"
            event = windows_event()
            self.service.record_launch("exe", str(path), row["version"], "exited", process.pid, code, event)
            if hex_code == "0xE0434352" and event and "System.Xml.XmlException" in event and "System.Configuration" in event:
                diagnosis = ("\nDiagnosis: Akasia could not read its configuration XML."
                             "\nOpen Configuration and run Analyze. If damaged settings are found, back them up and reset them.")
            else:
                diagnosis = "\nDiagnosis: unhandled .NET exception." if hex_code == "0xE0434352" else ""
            return f"Akasia exited: {code} ({hex_code}){diagnosis}" + (f"\nWindows event: {event}" if event else "")
        except Exception as exc:
            LOGGER.exception("Unable to launch executable %s", path)
            self.service.record_launch("exe", str(path), row["version"], "start_failed", error=str(exc))
            return f"Unable to start Akasia: {exc}\n{traceback.format_exc()}"

    def launch_shortcut(self, path: Optional[str]) -> str:
        if not path or not Path(path).exists():
            return "Select an existing shortcut first."
        try:
            os.startfile(path)
            self.service.record_launch("shortcut", path, None, "invoked")
            return "ClickOnce shortcut invoked."
        except Exception as exc:
            LOGGER.exception("Unable to open shortcut %s", path)
            self.service.record_launch("shortcut", path, None, "start_failed", error=str(exc))
            return f"Unable to open shortcut: {exc}\n{traceback.format_exc()}"

    def find_configs(self) -> list[ConfigScan]:
        results: list[ConfigScan] = []
        for path in self.local.rglob("user.config"):
            try:
                raw = path.read_bytes()
                if "akasia" not in str(path).lower() and b"AkasiaPuntoVenta" not in raw[:250000]:
                    continue
                error = None
                try:
                    ET.fromstring(raw)
                except Exception as exc:
                    error = str(exc)
                results.append({"path": path, "valid": error is None, "null": b"\x00" in raw, "error": error})
            except OSError:
                pass
        return results

    def config_health(self) -> list[ConfigScan]:
        items = self.find_configs()
        stamp = now()
        for item in items:
            self.service.record_config_scan(stamp, item)
        self.service.commit()
        return items

    def reset_configs(self) -> tuple[list[tuple[Path, str, Optional[str]]], Optional[Path]]:
        items = [item for item in self.find_configs() if not item["valid"]]
        if not items:
            return [], None
        folder = self.paths.backups / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        folder.mkdir(parents=True, exist_ok=True)
        results: list[tuple[Path, str, Optional[str]]] = []
        for item in items:
            original = item["path"]
            backup = folder / f"{uuid.uuid4().hex}_user.config"
            renamed = original.with_name(f"user.config.corrupted.{dt.datetime.now():%Y%m%d-%H%M%S}")
            result, error = "reset", None
            try:
                shutil.copy2(original, backup)
                original.rename(renamed)
            except Exception as exc:
                LOGGER.exception("Unable to back up and reset %s", original)
                result, error = "failed", str(exc)
            self.service.record_backup(original, backup, renamed, result, error)
            results.append((original, result, error))
        self.service.commit()
        return results, folder

    def network_test(self) -> list[tuple[str, list[str], Optional[str]]]:
        results: list[tuple[str, list[str], Optional[str]]] = []
        for host in ("akasia.mx", "api.ipify.org"):
            try:
                addresses = sorted({str(address[4][0]) for address in socket.getaddrinfo(host, 443)})
                self.service.record_network_test(host, addresses)
                results.append((host, addresses, None))
            except Exception as exc:
                LOGGER.exception("DNS lookup failed for %s", host)
                self.service.record_network_test(host, error=str(exc))
                results.append((host, [], str(exc)))
        self.service.commit()
        return results

    def export_report(self) -> Path:
        self.paths.reports.mkdir(parents=True, exist_ok=True)
        path = self.paths.reports / f"AkasiaDiagnostic-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(self.service.report(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def open_logs(self) -> Path:
        self.paths.logs.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.paths.logs))
        return self.paths.logs