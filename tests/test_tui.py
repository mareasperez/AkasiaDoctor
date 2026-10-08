import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import OptionList

from akasia.config import AppPaths
from akasia.operations import DoctorOperations
from akasia.repository import DoctorRepository
from akasia.service import DoctorService, now
from akasia.tui import DoctorApp, ResetConfirmation


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.paths = AppPaths(Path(self.temporary.name))
        self.repository = DoctorRepository(self.paths.database)
        self.service = DoctorService(self.repository)
        self.operations = DoctorOperations(self.service, self.paths, local=self.paths.data)

    def tearDown(self):
        self.repository.close()
        self.temporary.cleanup()

    def test_keyboard_navigation_changes_section(self):
        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch.object(self.operations, "scan", return_value=(0, 0)):
                async with app.run_test(size=(100, 32)) as pilot:
                    await pilot.pause()
                    app.query_one("#nav", OptionList).focus()
                    await pilot.press("down", "enter")
                    self.assertEqual(app.view, "shortcuts")

        asyncio.run(check())

    def test_selecting_version_updates_service(self):
        stamp = now()
        self.service.save_installation("C:/Akasia.exe", "1.0", stamp, None, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            async with app.run_test(size=(100, 32)) as pilot:
                app.query_one("#items", OptionList).focus()
                await pilot.press("enter")
                self.assertEqual(self.service.get("selected_exe"), "C:/Akasia.exe")

        asyncio.run(check())

    def test_cancel_reset_does_not_change_file(self):
        corrupted = self.paths.data / "Akasia" / "user.config"
        corrupted.parent.mkdir()
        corrupted.write_bytes(b"<bad>\x00")

        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch.object(self.operations, "scan", return_value=(0, 0)):
                async with app.run_test(size=(100, 32)) as pilot:
                    await pilot.pause()
                    app.view = "config"
                    app.config_items = [{"path": corrupted, "valid": False, "null": True, "error": "invalid"}]
                    app.refresh_view()
                    await pilot.click("#select")
                    self.assertIsInstance(app.screen, ResetConfirmation)
                    await pilot.click("#cancel")
                    self.assertTrue(corrupted.exists())

        asyncio.run(check())

    def test_reports_open_log_folder(self):
        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch.object(self.operations, "scan", return_value=(0, 0)), patch.object(self.operations, "open_logs", return_value=self.paths.logs) as open_logs:
                async with app.run_test(size=(100, 32)) as pilot:
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    app.view = "report"
                    app.refresh_view()
                    await pilot.pause()
                    await pilot.click("#open-logs")
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    open_logs.assert_called_once_with()

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()