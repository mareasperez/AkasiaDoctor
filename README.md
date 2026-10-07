# Akasia Doctor

Akasia Doctor is a dependency-free Python terminal UI for discovering, launching, and diagnosing Akasia Punto de Venta ClickOnce installations on Windows.

## Run

Double-click `run_akasia_doctor.cmd`, or run:

```powershell
python .\akasia_doctor.py
```

Python 3.9 or newer is recommended. No third-party packages are required.

## Persistent history

The tool uses SQLite and stores its data at:

```text
%LOCALAPPDATA%\AkasiaDoctor\akasia_doctor.db
```

It remembers every discovered version, the selected version, the last version tested, the last version that remained running, launch exit codes, Windows error summaries, configuration scans, backups, and DNS tests.

## Features

- Discovers Akasia executables in the ClickOnce cache.
- Discovers `.appref-ms`, `.application`, and `.lnk` shortcuts.
- Highlights `SELECTED`, `LAST TESTED`, and `LAST WORKING` versions.
- Detects immediate exits and unhandled .NET exceptions.
- Reads relevant Windows Application events.
- Detects corrupted `user.config` files and NULL bytes (`0x00`).
- Backs up and renames corrupted configuration only after explicit confirmation.
- Tests DNS for `akasia.mx` and `api.ipify.org`.
- Exports a JSON diagnostic report.

Backups and reports are stored under `%LOCALAPPDATA%\AkasiaDoctor`. Configuration recovery does not modify the Akasia MySQL database containing POS business data.

