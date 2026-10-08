import asyncio
import logging
import tempfile
import unittest
from logging.handlers import TimedRotatingFileHandler
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

    def tearDown(self):
        logger = logging.getLogger("akasia_doctor")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
        self.temporary.cleanup()

    def test_daily_rotation_keeps_a_dated_log_and_traceback(self):
        logger = configure_logging(self.paths)
        handler = next(item for item in logger.handlers if isinstance(item, TimedRotatingFileHandler))
        try:
            raise RuntimeError("diagnostic failure")
        except RuntimeError:
            logger.exception("Doctor operation failed")

        handler.doRollover()
        logger.error("next day failure")

        dated_logs = list(self.paths.logs.glob("doctor.log.*"))
        self.assertEqual(len(dated_logs), 1)
        self.assertRegex(dated_logs[0].name, r"^doctor\.log\.\d{4}-\d{2}-\d{2}$")
        self.assertIn("RuntimeError: diagnostic failure", dated_logs[0].read_text(encoding="utf-8"))
        self.assertIn("next day failure", (self.paths.logs / "doctor.log").read_text(encoding="utf-8"))

    def test_startup_failure_writes_traceback(self):
        arguments = ["akasia_doctor.py", "--data-dir", str(self.paths.data)]
        with patch("sys.argv", arguments), patch("akasia_doctor.DoctorRepository", side_effect=RuntimeError("database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                main()

        content = (self.paths.logs / "doctor.log").read_text(encoding="utf-8")
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

        content = (self.paths.logs / "doctor.log").read_text(encoding="utf-8")
        self.assertIn("Operation scan failed", content)
        self.assertIn("RuntimeError: scan unavailable", content)


if __name__ == "__main__":
    unittest.main()