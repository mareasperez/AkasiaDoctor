# Akasia Doctor

Akasia Doctor is a Windows terminal dashboard for discovering, launching, and diagnosing Akasia Punto de Venta ClickOnce installations.

## Run

Download `AkasiaDoctor.exe` from the latest GitHub Release and open it in a Windows terminal. It includes Python and its dependencies. To run the source instead:

```powershell
poetry install
poetry run python .\akasia_doctor.py
```

Python 3.9 through 3.15 is supported for development. The dashboard uses Textual; its navigation, lists, and recovery confirmation are keyboard-accessible. `run_akasia_doctor.cmd` uses the locally built executable when present, otherwise the Poetry environment.

## Configuration

The data directory defaults to `%LOCALAPPDATA%\AkasiaDoctor`. To change it, set `AKASIA_DOCTOR_DATA_DIR` in the environment or copy `.env.example` to `.env` beside the script or executable and set its value there. `--data-dir` has highest priority, followed by the process environment and `.env`.

## Build and release

Run `build_akasia_doctor.cmd` on Windows to create `dist\AkasiaDoctor.exe`. Poetry installs the locked dependencies; PyInstaller creates the one-file console executable. To run tests:

```powershell
poetry install --with build
poetry run python -m unittest discover -s tests -v
```

There are two ways to start a release after pushing the desired commit:

- Push a version tag such as `v1.0.0`: the Release Windows executable workflow runs automatically.
- In GitHub Actions, run Create version tag on the desired branch and enter `1.0.0`: it creates `v1.0.0` on that commit and starts the Release Windows executable workflow.

The release workflow tests, builds on Windows, checks the executable, and attaches it to a GitHub Release. A version tag can be created only once. Repository Actions must be enabled and allowed to write repository contents and run workflows.

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

