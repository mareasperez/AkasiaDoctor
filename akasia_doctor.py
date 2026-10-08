#!/usr/bin/env python3
"""Akasia ClickOnce discovery, launch diagnostics, and configuration recovery."""

import argparse
from pathlib import Path

from akasia.config import resolve_paths
from akasia.operations import DoctorOperations
from akasia.repository import DoctorRepository
from akasia.service import DoctorService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-only", action="store_true", help="scan without starting the TUI")
    parser.add_argument("--data-dir", type=Path, help="override the data directory")
    args = parser.parse_args()

    paths = resolve_paths(args.data_dir)
    for folder in (paths.data, paths.backups, paths.reports):
        folder.mkdir(parents=True, exist_ok=True)

    repository = DoctorRepository(paths.database)
    service = DoctorService(repository)
    operations = DoctorOperations(service, paths)
    try:
        if args.scan_only:
            executables, shortcuts = operations.scan()
            print(f"Found {executables} executable(s) and {shortcuts} shortcut(s).")
            for row in service.installations():
                print(f"{row['version'] or 'unknown'} | {row['path']}")
        else:
            from akasia.tui import DoctorApp

            DoctorApp(service, operations).run()
    finally:
        repository.close()


if __name__ == "__main__":
    main()