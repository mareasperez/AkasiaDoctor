import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import OptionList, RichLog

from akasia.config import AppPaths
from akasia.operations import DoctorOperations
from akasia.repository import DoctorRepository
from akasia.service import DoctorService, now
from akasia.tui import ActivityScreen, DoctorApp, ResetConfirmation


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

    def test_selection_and_navigation_work_during_analysis(self):
        stamp = now()
        self.service.save_installation("C:/Akasia-old.exe", "1.0", stamp, None, stamp)
        self.service.save_installation("C:/Akasia-new.exe", "2.0", stamp, None, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            async with app.run_test(size=(100, 32)) as pilot:
                app.busy = True
                items = app.query_one("#items", OptionList)
                items.highlighted = 1
                items.focus()
                await pilot.press("enter")
                self.assertEqual(self.service.get("selected_exe"), "C:/Akasia-new.exe")
                nav = app.query_one("#nav", OptionList)
                nav.focus()
                await pilot.press("down", "enter")
                self.assertEqual(app.view, "shortcuts")

        asyncio.run(check())

    def test_can_select_another_version_after_launch(self):
        stamp = now()
        self.service.save_installation("C:/Akasia-old.exe", "1.0", stamp, None, stamp)
        self.service.save_installation("C:/Akasia-new.exe", "2.0", stamp, None, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch.object(self.operations, "launch_exe", return_value="Akasia is running. PID: 123") as launch:
                async with app.run_test(size=(100, 32)) as pilot:
                    items = app.query_one("#items", OptionList)
                    items.highlighted = 1
                    items.focus()
                    await pilot.press("enter")
                    await pilot.click("#launch")
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertEqual(items.highlighted, 1)
                    await pilot.press("up", "enter")
                    self.assertEqual(self.service.get("selected_exe"), "C:/Akasia-old.exe")
                    await pilot.click("#launch")
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertEqual([call.args[0] for call in launch.call_args_list],
                                     ["C:/Akasia-new.exe", "C:/Akasia-old.exe"])

        asyncio.run(check())

    def test_can_select_another_shortcut_after_launch(self):
        stamp = now()
        self.service.save_shortcut("C:/Akasia-first.appref-ms", ".appref-ms", stamp, stamp)
        self.service.save_shortcut("C:/Akasia-second.appref-ms", ".appref-ms", stamp, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch.object(self.operations, "launch_shortcut", return_value="ClickOnce shortcut invoked.") as launch:
                async with app.run_test(size=(100, 32)) as pilot:
                    nav = app.query_one("#nav", OptionList)
                    nav.focus()
                    await pilot.press("down", "enter")
                    items = app.query_one("#items", OptionList)
                    items.highlighted = 1
                    items.focus()
                    await pilot.press("enter")
                    self.assertEqual(self.service.get("selected_shortcut"), "C:/Akasia-second.appref-ms")
                    await pilot.click("#launch")
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertEqual(items.highlighted, 1)
                    await pilot.press("up", "enter")
                    self.assertEqual(self.service.get("selected_shortcut"), "C:/Akasia-first.appref-ms")
                    await pilot.click("#launch")
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertEqual([call.args[0] for call in launch.call_args_list],
                                     ["C:/Akasia-second.appref-ms", "C:/Akasia-first.appref-ms"])

        asyncio.run(check())

    def test_activity_can_be_expanded_to_read_full_error(self):
        stamp = now()
        self.service.save_installation("C:/Akasia.exe", "1.0", stamp, None, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            async with app.run_test(size=(100, 32)) as pilot:
                app.log_message("Akasia exited: -532462766 (0xE0434352)\nWindows event: full error details")
                await pilot.click("#expand-activity")
                self.assertIsInstance(app.screen, ActivityScreen)
                detail = app.screen.query_one("#activity-detail", RichLog)
                self.assertIn("Windows event: full error details", "\n".join(
                    "".join(segment.text for segment in line) for line in detail.lines
                ))
                app.log_message("More diagnostic detail")
                self.assertIn("More diagnostic detail", "\n".join(
                    "".join(segment.text for segment in line) for line in detail.lines
                ))
                with patch.object(app.screen, "get_selected_text", return_value="full error"), \
                     patch.object(app, "copy_to_clipboard") as copy:
                    await pilot.press("ctrl+c")
                    copy.assert_called_once_with("full error")
                await pilot.click("#close-activity")
                self.assertNotIsInstance(app.screen, ActivityScreen)

        asyncio.run(check())

    def test_activity_shows_summary_and_keeps_windows_event_in_details(self):
        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch.object(self.operations, "scan", return_value=(0, 0)):
                async with app.run_test(size=(100, 32)) as pilot:
                    await pilot.pause()
                    event = "Windows event: System.Xml.XmlException " + "stack frame " * 80
                    app.log_message("Akasia exited: 3762504530 (0xE0434352)\nDiagnosis: Invalid XML configuration.\n" + event)
                    activity = app.query_one("#activity", RichLog)
                    compact = "\n".join("".join(segment.text for segment in line) for line in activity.lines)
                    self.assertIn("Invalid XML configuration", compact)
                    self.assertIn("Expand", compact)
                    self.assertNotIn("stack frame", compact)
                    await pilot.click("#expand-activity")
                    detail = app.screen.query_one("#activity-detail", RichLog)
                    expanded = "\n".join("".join(segment.text for segment in line) for line in detail.lines)
                    self.assertIn("stack frame", expanded)

        asyncio.run(check())

    def test_ctrl_c_copies_first_and_quits_on_second_press(self):
        stamp = now()
        self.service.save_installation("C:/Akasia.exe", "1.0", stamp, None, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            async with app.run_test(size=(100, 32)) as pilot:
                with patch.object(app.screen, "get_selected_text", return_value="full error"), \
                     patch.object(app, "copy_to_clipboard") as copy:
                    await pilot.press("ctrl+c")
                    copy.assert_called_once_with("full error")
                    self.assertTrue(app.is_running)
                    await pilot.press("ctrl+c")
                    self.assertFalse(app.is_running)

        asyncio.run(check())

    def test_ctrl_c_without_selection_requires_second_press_to_quit(self):
        stamp = now()
        self.service.save_installation("C:/Akasia.exe", "1.0", stamp, None, stamp)
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            async with app.run_test(size=(100, 32)) as pilot:
                await pilot.press("ctrl+c")
                self.assertTrue(app.is_running)
                await pilot.press("ctrl+c")
                self.assertFalse(app.is_running)

        asyncio.run(check())

    def test_launch_failure_is_visible_in_expanded_activity(self):
        executable = self.paths.data / "Akasia.exe"
        executable.touch()
        stamp = now()
        self.service.save_installation(str(executable), "1.0", stamp, None, stamp)
        self.service.set("selected_exe", str(executable))
        self.service.commit()

        async def check():
            app = DoctorApp(self.service, self.operations)
            with patch("akasia.operations.subprocess.Popen", side_effect=OSError("cannot launch")), \
                 patch("akasia.operations.LOGGER"):
                async with app.run_test(size=(100, 32)) as pilot:
                    await pilot.click("#launch")
                    for _ in range(10):
                        if not app.busy:
                            break
                        await pilot.pause()
                    self.assertFalse(app.busy)
                    await pilot.click("#expand-activity")
                    detail = app.screen.query_one("#activity-detail", RichLog)
                    self.assertIn("OSError: cannot launch", "\n".join(
                        "".join(segment.text for segment in line) for line in detail.lines
                    ))

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