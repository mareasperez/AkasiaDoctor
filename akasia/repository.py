"""SQLite persistence for Akasia Doctor."""

import sqlite3
from pathlib import Path
from typing import Optional


TABLES = ("settings", "installations", "shortcuts", "launches", "config_scans", "backups", "network_tests")


class DoctorRepository:
    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(path, check_same_thread=False)
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

    def close(self) -> None:
        self.db.close()

    def commit(self) -> None:
        self.db.commit()

    def set_setting(self, key: str, value: str, stamp: str) -> None:
        self.db.execute("INSERT INTO settings VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated=excluded.updated", (key, value, stamp))
        self.commit()

    def get_setting(self, key: str) -> Optional[str]:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def installations(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM installations ORDER BY modified DESC"))

    def shortcuts(self) -> list[sqlite3.Row]:
        return list(self.db.execute("SELECT * FROM shortcuts ORDER BY modified DESC"))

    def installation(self, path: str) -> Optional[sqlite3.Row]:
        return self.db.execute("SELECT * FROM installations WHERE path=?", (path,)).fetchone()

    def save_installation(self, path: str, version: str, modified: str, identity_hash: Optional[str], stamp: str) -> None:
        self.db.execute("INSERT INTO installations(path,version,modified,identity_hash,first_seen,last_seen) VALUES(?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET version=excluded.version,modified=excluded.modified,identity_hash=excluded.identity_hash,last_seen=excluded.last_seen", (path, version, modified, identity_hash, stamp, stamp))

    def save_shortcut(self, path: str, kind: str, modified: str, stamp: str) -> None:
        self.db.execute("INSERT INTO shortcuts VALUES(?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET type=excluded.type,modified=excluded.modified,last_seen=excluded.last_seen", (path, kind, modified, stamp, stamp))

    def save_launch(self, stamp: str, kind: str, path: str, version: Optional[str], result: str,
                    pid: Optional[int], code: Optional[int], hex_code: Optional[str],
                    event: Optional[str], error: Optional[str]) -> None:
        self.db.execute("INSERT INTO launches(created,type,path,version,result,pid,exit_code,exit_hex,event,error) VALUES(?,?,?,?,?,?,?,?,?,?)", (stamp, kind, path, version, result, pid, code, hex_code, event, error))

    def update_installation_launch(self, stamp: str, result: str, code: Optional[int], path: str) -> None:
        self.db.execute("UPDATE installations SET last_tested=?,last_result=?,last_exit=? WHERE path=?", (stamp, result, code, path))

    def save_config_scan(self, stamp: str, path: str, valid: int, has_null: int, error: Optional[str]) -> None:
        self.db.execute("INSERT INTO config_scans(created,path,valid,has_null,error) VALUES(?,?,?,?,?)", (stamp, path, valid, has_null, error))

    def save_backup(self, stamp: str, original: str, backup: str, renamed: str, result: str, error: Optional[str]) -> None:
        self.db.execute("INSERT INTO backups(created,original,backup,renamed,result,error) VALUES(?,?,?,?,?,?)", (stamp, original, backup, renamed, result, error))

    def save_network_test(self, stamp: str, host: str, success: int, addresses: str, error: Optional[str]) -> None:
        self.db.execute("INSERT INTO network_tests(created,host,success,addresses,error) VALUES(?,?,?,?,?)", (stamp, host, success, addresses, error))

    def launch_history(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM launches ORDER BY id DESC LIMIT 20").fetchall()

    def report(self) -> dict[str, list[dict[str, object]]]:
        return {table: [dict(row) for row in self.db.execute(f"SELECT * FROM {table}")] for table in TABLES}