import asyncio
import datetime as dt
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasia.config import AppPaths
from akasia.logging_config import configure_logging
from akasia.operations import DoctorOperations
from akasia.repository import DoctorRepository
from akasia.service import DoctorService
from akasia.tui import DoctorApp
from akasia_doctor import main


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = AppPaths(Path(self.temporary.name))

    def log_file(self, day: dt.date | None = None) -> Path:
        day = day or dt.date.today()
        return self.paths.logs / f"doctor-{day:%Y-%m-%d}.log"

    def tearDown(self):
        logger = logging.getLogger("akasia_doctor")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        self.temporary.cleanup()

    def test_daily_rotation_keeps_a_dated_log_and_traceback(self):
        self.paths.logs.mkdir(parents=True)
        legacy_log = self.paths.logs / "doctor.log"
        legacy_log.write_text("existing diagnostics\n", encoding="utf-8")
        logger = configure_logging(self.paths)
        today = dt.date.today()
        tomorrow = today + dt.timedelta(days=1)
        try:
            raise RuntimeError("diagnostic failure")
        except RuntimeError:
            logger.exception("Doctor operation failed")

        next_day_record = logger.makeRecord(logger.name, logging.ERROR, __file__, 0, "next day failure", (), None)
        next_day_record.created = dt.datetime.combine(tomorrow, dt.time(12)).timestamp()
        logger.handle(next_day_record)

        self.assertIn("RuntimeError: diagnostic failure", self.log_file(today).read_text(encoding="utf-8"))
        self.assertNotIn("next day failure", self.log_file(today).read_text(encoding="utf-8"))
        self.assertIn("next day failure", self.log_file(tomorrow).read_text(encoding="utf-8"))
        self.assertEqual(legacy_log.read_text(encoding="utf-8"), "existing diagnostics\n")

    def test_daily_logs_keep_fourteen_previous_days(self):
        today = dt.date.today()
        self.paths.logs.mkdir(parents=True)
        recent = self.log_file(today - dt.timedelta(days=14))
        expired = self.log_file(today - dt.timedelta(days=15))
        recent.write_text("recent\n", encoding="utf-8")
        expired.write_text("expired\n", encoding="utf-8")

        configure_logging(self.paths)

        self.assertEqual(recent.read_text(encoding="utf-8"), "recent\n")
        self.assertFalse(expired.exists())

    def test_startup_failure_writes_traceback(self):
        arguments = ["akasia_doctor.py", "--data-dir", str(self.paths.data)]
        with patch("sys.argv", arguments), patch("akasia_doctor.DoctorRepository", side_effect=RuntimeError("database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                main()

        content = self.log_file().read_text(encoding="utf-8")
        self.assertIn("Akasia Doctor failed", content)
        self.assertIn("RuntimeError: database unavailable", content)

    def test_tui_operation_failure_writes_traceback(self):
        configure_logging(self.paths)
        repository = DoctorRepository(self.paths.database)
        service = DoctorService(repository)
        operations = DoctorOperations(service, self.paths, local=self.paths.data)

        async def check():
            app = DoctorApp(service, operations)
            with patch.object(operations, "scan", side_effect=RuntimeError("scan unavailable")):
                async with app.run_test(size=(100, 32)) as pilot:
                    await pilot.pause()
                    await app.workers.wait_for_complete()

        try:
            asyncio.run(check())
        finally:
            repository.close()

        content = self.log_file().read_text(encoding="utf-8")
        self.assertIn("Operation scan failed", content)
        self.assertIn("RuntimeError: scan unavailable", content)

    def test_activity_messages_are_written_to_daily_log(self):
        configure_logging(self.paths)
        repository = DoctorRepository(self.paths.database)
        service = DoctorService(repository)
        operations = DoctorOperations(service, self.paths, local=self.paths.data)

        async def check():
            app = DoctorApp(service, operations)
            with patch.object(operations, "scan", return_value=(2, 1)):
                async with app.run_test(size=(100, 32)) as pilot:
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)

        try:
            asyncio.run(check())
        finally:
            repository.close()

        content = self.log_file().read_text(encoding="utf-8")
        self.assertIn("Working: scan...", content)
        self.assertIn("Found 2 executable(s) and 1 shortcut(s).", content)

    def test_handled_launch_failure_keeps_traceback_in_file(self):
        configure_logging(self.paths)
        repository = DoctorRepository(self.paths.database)
        service = DoctorService(repository)
        operations = DoctorOperations(service, self.paths, local=self.paths.data)
        executable = self.paths.data / "Akasia.exe"
        executable.touch()
        service.save_installation(str(executable), "1", "today", None, "today")
        service.commit()

        try:
            with patch("akasia.operations.subprocess.Popen", side_effect=OSError("cannot launch")):
                result = operations.launch_exe(str(executable))
                self.assertIn("cannot launch", result)
                self.assertIn("Traceback (most recent call last)", result)
                self.assertIn("OSError: cannot launch", result)
        finally:
            repository.close()

        content = self.log_file().read_text(encoding="utf-8")
        self.assertIn("Traceback (most recent call last)", content)
        self.assertIn("OSError: cannot launch", content)


if __name__ == "__main__":
    unittest.main()