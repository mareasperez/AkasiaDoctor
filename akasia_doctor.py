#!/usr/bin/env python3
"""Akasia ClickOnce discovery, launch diagnostics, and configuration recovery."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "1.0.0"
IS_WINDOWS = os.name == "nt"
LOCAL = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
DATA = LOCAL / "AkasiaDoctor"
DB_PATH = DATA / "akasia_doctor.db"
BACKUPS = DATA / "Backups"
REPORTS = DATA / "Reports"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def path_hash(path):
    import re
    found = re.findall(r"(?i)([0-9a-f]{16})(?=[\\/]|$)", str(path))
    return found[-1].lower() if found else None


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS installations(
          path TEXT PRIMARY KEY,version TEXT,modified TEXT,identity_hash TEXT,
          first_seen TEXT,last_seen TEXT,last_tested TEXT,last_result TEXT,last_exit INTEGER);
        CREATE TABLE IF NOT EXISTS shortcuts(
          path TEXT PRIMARY KEY,type TEXT,modified TEXT,first_seen TEXT,last_seen TEXT);
        CREATE TABLE IF NOT EXISTS launches(
          id INTEGER PRIMARY KEY,created TEXT,type TEXT,path TEXT,version TEXT,result TEXT,
          pid INTEGER,exit_code INTEGER,exit_hex TEXT,event TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS config_scans(
          id INTEGER PRIMARY KEY,created TEXT,path TEXT,valid INTEGER,has_null INTEGER,error TEXT);
        CREATE TABLE IF NOT EXISTS backups(
          id INTEGER PRIMARY KEY,created TEXT,original TEXT,backup TEXT,renamed TEXT,result TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS network_tests(
          id INTEGER PRIMARY KEY,created TEXT,host TEXT,success INTEGER,addresses TEXT,error TEXT);
        """)
        self.db.commit()

    def set(self, key, value):
        self.db.execute("INSERT INTO settings VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated=excluded.updated", (key, value, now()))
        self.db.commit()

    def get(self, key):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def installations(self):
        return list(self.db.execute("SELECT * FROM installations ORDER BY modified DESC"))

    def shortcuts(self):
        return list(self.db.execute("SELECT * FROM shortcuts ORDER BY modified DESC"))

    def record_launch(self, kind, path, version, result, pid=None, code=None, event=None, error=None):
        stamp = now()
        hex_code = f"0x{code & 0xFFFFFFFF:08X}" if code is not None else None
        self.db.execute("INSERT INTO launches(created,type,path,version,result,pid,exit_code,exit_hex,event,error) VALUES(?,?,?,?,?,?,?,?,?,?)", (stamp, kind, path, version, result, pid, code, hex_code, event, error))
        if kind == "exe":
            self.db.execute("UPDATE installations SET last_tested=?,last_result=?,last_exit=? WHERE path=?", (stamp, result, code, path))
            self.set("last_tested", path)
            if result == "running":
                self.set("last_working", path)
        self.db.commit()


def file_version(path):
    if not IS_WINDOWS:
        return ""
    escaped = str(path).replace("'", "''")
    command = f"(Get-Item -LiteralPath '{escaped}').VersionInfo.FileVersion"
    try:
        flags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=8, creationflags=flags)
        return result.stdout.strip()
    except Exception:
        return ""


def shortcut_roots():
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    program_data = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
    candidates = [Path.home() / "Desktop", roaming / "Microsoft/Windows/Start Menu/Programs", program_data / "Microsoft/Windows/Start Menu/Programs"]
    return [p for p in candidates if p.exists()]


def scan(store):
    print("\nScanning ClickOnce cache and shortcuts...")
    stamp = now()
    count_exe = 0
    root = LOCAL / "Apps/2.0"
    if root.exists():
        for path in root.rglob("*.exe"):
            if "akasia" not in path.name.lower():
                continue
            try:
                modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
                store.db.execute("INSERT INTO installations(path,version,modified,identity_hash,first_seen,last_seen) VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET version=excluded.version,modified=excluded.modified,identity_hash=excluded.identity_hash,last_seen=excluded.last_seen", (str(path), file_version(path), modified, path_hash(path), stamp, stamp))
                count_exe += 1
            except OSError:
                pass
    count_shortcuts = 0
    for base in shortcut_roots():
        for path in base.rglob("*"):
            try:
                if path.is_file() and "akasia" in path.name.lower() and path.suffix.lower() in {".appref-ms", ".lnk", ".application"}:
                    modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
                    store.db.execute("INSERT INTO shortcuts VALUES(?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET type=excluded.type,modified=excluded.modified,last_seen=excluded.last_seen", (str(path), path.suffix.lower(), modified, stamp, stamp))
                    count_shortcuts += 1
            except OSError:
                pass
    store.db.commit()
    store.set("last_scan", stamp)
    print(f"Found {count_exe} executable(s) and {count_shortcuts} shortcut(s).")


def show_installations(store):
    rows = store.installations()
    selected, tested, working = store.get("selected_exe"), store.get("last_tested"), store.get("last_working")
    for i, row in enumerate(rows, 1):
        labels = []
        if row["path"] == selected: labels.append("SELECTED")
        if row["path"] == tested: labels.append("LAST TESTED")
        if row["path"] == working: labels.append("LAST WORKING")
        suffix = f" [{' | '.join(labels)}]" if labels else ""
        print(f"\n[{i}] Version {row['version'] or 'unknown'}{suffix}")
        print(f"    Result: {row['last_result'] or 'not tested'}")
        print(f"    Hash:   {row['identity_hash'] or 'unknown'}")
        print(f"    Path:   {row['path']}")
    return rows


def choose(rows, prompt):
    try:
        value = input(prompt).strip()
        return rows[int(value) - 1] if value and 1 <= int(value) <= len(rows) else None
    except (ValueError, IndexError):
        return None


def select_exe(store):
    rows = show_installations(store)
    row = choose(rows, "\nSelect a version, or Enter to cancel: ")
    if row:
        store.set("selected_exe", row["path"])
        print(f"Selected: {row['path']}")


def select_shortcut(store):
    rows = store.shortcuts()
    for i, row in enumerate(rows, 1):
        print(f"\n[{i}] {Path(row['path']).name}\n    {row['path']}")
    row = choose(rows, "\nSelect a shortcut, or Enter to cancel: ")
    if row:
        store.set("selected_shortcut", row["path"])
        print(f"Selected: {row['path']}")


def windows_event():
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


def launch_exe(store):
    path_text = store.get("selected_exe")
    row = store.db.execute("SELECT * FROM installations WHERE path=?", (path_text,)).fetchone() if path_text else None
    if not row or not Path(row["path"]).exists():
        print("Select an existing executable first.")
        return
    path = Path(row["path"])
    try:
        process = subprocess.Popen([str(path)], cwd=str(path.parent))
        time.sleep(4)
        code = process.poll()
        if code is None:
            print(f"Akasia is running. PID: {process.pid}")
            store.record_launch("exe", str(path), row["version"], "running", process.pid)
        else:
            hex_code = f"0x{code & 0xFFFFFFFF:08X}"
            print(f"Akasia exited: {code} ({hex_code})")
            if hex_code == "0xE0434352": print("Diagnosis: unhandled .NET exception.")
            event = windows_event()
            if event: print(f"Windows event: {event}")
            store.record_launch("exe", str(path), row["version"], "exited", process.pid, code, event)
    except Exception as exc:
        print(f"Unable to start Akasia: {exc}")
        store.record_launch("exe", str(path), row["version"], "start_failed", error=str(exc))


def launch_shortcut(store):
    path = store.get("selected_shortcut")
    if not path or not Path(path).exists():
        print("Select an existing shortcut first.")
        return
    try:
        os.startfile(path)
        print("ClickOnce shortcut invoked.")
        store.record_launch("shortcut", path, None, "invoked")
    except Exception as exc:
        print(f"Unable to open shortcut: {exc}")
        store.record_launch("shortcut", path, None, "start_failed", error=str(exc))


def find_configs():
    results = []
    for path in LOCAL.rglob("user.config"):
        try:
            raw = path.read_bytes()
            if "akasia" not in str(path).lower() and b"AkasiaPuntoVenta" not in raw[:250000]:
                continue
            error = None
            try: ET.fromstring(raw)
            except Exception as exc: error = str(exc)
            results.append({"path": path, "valid": error is None, "null": b"\x00" in raw, "error": error})
        except OSError:
            pass
    return results


def config_health(store, display=True):
    items = find_configs()
    stamp = now()
    for item in items:
        store.db.execute("INSERT INTO config_scans(created,path,valid,has_null,error) VALUES(?,?,?,?,?)", (stamp, str(item["path"]), int(item["valid"]), int(item["null"]), item["error"]))
        if display:
            print(f"\n{'VALID' if item['valid'] else 'CORRUPTED'}: {item['path']}")
            if not item["valid"]: print("Reason: invalid NULL bytes (0x00)." if item["null"] else item["error"])
    store.db.commit()
    if not items and display: print("No Akasia user.config files were found.")
    return items


def reset_configs(store):
    items = [x for x in find_configs() if not x["valid"]]
    if not items:
        print("No corrupted configuration was found.")
        return
    print(f"Found {len(items)} corrupted file(s). This resets preferences, not POS database data.")
    if input("Type YES to back up and reset them: ").strip() != "YES":
        print("No files changed.")
        return
    folder = BACKUPS / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    for item in items:
        original = item["path"]
        backup = folder / f"{uuid.uuid4().hex}_user.config"
        renamed = original.with_name(f"user.config.corrupted.{dt.datetime.now():%Y%m%d-%H%M%S}")
        result, error = "reset", None
        try:
            shutil.copy2(original, backup)
            original.rename(renamed)
            print(f"Reset: {original}")
        except Exception as exc:
            result, error = "failed", str(exc)
            print(f"Failed: {original}: {exc}")
        store.db.execute("INSERT INTO backups(created,original,backup,renamed,result,error) VALUES(?,?,?,?,?,?)", (now(), str(original), str(backup), str(renamed), result, error))
    store.db.commit()
    print(f"Backups: {folder}")


def network_test(store):
    for host in ("akasia.mx", "api.ipify.org"):
        try:
            addresses = sorted({x[4][0] for x in socket.getaddrinfo(host, 443)})
            print(f"{host}: {', '.join(addresses)}")
            store.db.execute("INSERT INTO network_tests(created,host,success,addresses,error) VALUES(?,?,?,?,?)", (now(), host, 1, json.dumps(addresses), None))
        except Exception as exc:
            print(f"{host}: FAILED - {exc}")
            store.db.execute("INSERT INTO network_tests(created,host,success,addresses,error) VALUES(?,?,?,?,?)", (now(), host, 0, "[]", str(exc)))
    store.db.commit()


def history(store):
    rows = store.db.execute("SELECT * FROM launches ORDER BY id DESC LIMIT 20")
    for row in rows:
        print(f"{row['created']} | {row['version'] or 'unknown'} | {row['result']} | {row['exit_hex'] or '-'}")
        print(f"    {row['path']}")


def export_report(store):
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"AkasiaDiagnostic-{dt.datetime.now():%Y%m%d-%H%M%S}.json"
    tables = ["settings", "installations", "shortcuts", "launches", "config_scans", "backups", "network_tests"]
    report = {table: [dict(row) for row in store.db.execute(f"SELECT * FROM {table}")] for table in tables}
    report["generated"] = now()
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report: {path}")


def pause(): input("\nPress Enter to continue...")


def menu(store):
    actions = {"1": lambda: scan(store), "2": lambda: select_exe(store), "3": lambda: select_shortcut(store), "4": lambda: launch_exe(store), "5": lambda: launch_shortcut(store), "6": lambda: config_health(store), "7": lambda: reset_configs(store), "8": lambda: network_test(store), "9": lambda: history(store), "10": lambda: export_report(store)}
    while True:
        os.system("cls" if IS_WINDOWS else "clear")
        print(f"Akasia Doctor {VERSION}\n" + "=" * 72)
        print(f"Selected:     {store.get('selected_exe') or '<none>'}")
        print(f"Last tested:  {store.get('last_tested') or '<none>'}")
        print(f"Last working: {store.get('last_working') or '<none>'}\n")
        print("[1] Scan versions and shortcuts\n[2] Select executable\n[3] Select ClickOnce shortcut\n[4] Launch executable and diagnose\n[5] Launch ClickOnce shortcut\n[6] Analyze user.config\n[7] Back up and reset corrupted configs\n[8] Test DNS\n[9] Show launch history\n[10] Export report\n[Q] Quit")
        choice = input("\nChoose: ").strip().upper()
        if choice == "Q": return
        if choice in actions: actions[choice](); pause()


def main():
    global DATA, DB_PATH, BACKUPS, REPORTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    if args.data_dir:
        DATA = args.data_dir.resolve(); DB_PATH = DATA / "akasia_doctor.db"; BACKUPS = DATA / "Backups"; REPORTS = DATA / "Reports"
    for folder in (DATA, BACKUPS, REPORTS): folder.mkdir(parents=True, exist_ok=True)
    store = Store(DB_PATH)
    try:
        if args.scan_only: scan(store); show_installations(store)
        else:
            if not store.installations(): scan(store)
            menu(store)
    finally:
        store.db.close()


if __name__ == "__main__":
    main()

