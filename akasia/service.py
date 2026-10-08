"""Application state transitions backed by the SQLite repository."""

import datetime as dt
import json


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class DoctorService:
    def __init__(self, repository):
        self.repository = repository

    def get(self, key):
        return self.repository.get_setting(key)

    def set(self, key, value):
        self.repository.set_setting(key, value, now())

    def installations(self):
        return self.repository.installations()

    def shortcuts(self):
        return self.repository.shortcuts()

    def installation(self, path):
        return self.repository.installation(path)

    def save_installation(self, path, version, modified, identity_hash, stamp):
        self.repository.save_installation(path, version, modified, identity_hash, stamp)

    def save_shortcut(self, path, kind, modified, stamp):
        self.repository.save_shortcut(path, kind, modified, stamp)

    def finish_scan(self, stamp):
        self.repository.commit()
        self.set("last_scan", stamp)

    def record_launch(self, kind, path, version, result, pid=None, code=None, event=None, error=None):
        stamp = now()
        hex_code = f"0x{code & 0xFFFFFFFF:08X}" if code is not None else None
        self.repository.save_launch(stamp, kind, path, version, result, pid, code, hex_code, event, error)
        if kind == "exe":
            self.repository.update_installation_launch(stamp, result, code, path)
            self.set("last_tested", path)
            if result == "running":
                self.set("last_working", path)
        self.repository.commit()

    def record_config_scan(self, stamp, item):
        self.repository.save_config_scan(stamp, str(item["path"]), int(item["valid"]), int(item["null"]), item["error"])

    def record_backup(self, original, backup, renamed, result, error):
        self.repository.save_backup(now(), str(original), str(backup), str(renamed), result, error)

    def record_network_test(self, host, addresses=None, error=None):
        self.repository.save_network_test(now(), host, int(error is None), json.dumps(addresses or []), error)

    def commit(self):
        self.repository.commit()

    def launch_history(self):
        return self.repository.launch_history()

    def report(self):
        report = self.repository.report()
        report["generated"] = now()
        return report