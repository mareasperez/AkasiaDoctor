import tempfile
import unittest
from pathlib import Path

from akasia.config import resolve_paths
from akasia.repository import DoctorRepository
from akasia.service import DoctorService, now


class ConfigTests(unittest.TestCase):
    def test_data_directory_precedence(self):
        environment = {"LOCALAPPDATA": "C:/local", "AKASIA_DOCTOR_DATA_DIR": "C:/configured"}
        self.assertEqual(resolve_paths(environ=environment).data, Path("C:/configured").resolve())
        self.assertEqual(resolve_paths("C:/cli", environment).data, Path("C:/cli").resolve())
        self.assertEqual(resolve_paths(environ={"LOCALAPPDATA": "C:/local"}).data, Path("C:/local/AkasiaDoctor"))

    def test_adjacent_env_file_is_used_only_when_no_override_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            configured = Path(directory) / "configured"
            env_file.write_text(f"AKASIA_DOCTOR_DATA_DIR={configured}\n", encoding="utf-8")
            self.assertEqual(resolve_paths(environ={}, env_file=env_file).data, configured.resolve())
            self.assertEqual(resolve_paths(environ={"AKASIA_DOCTOR_DATA_DIR": directory}, env_file=env_file).data, Path(directory).resolve())


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = DoctorRepository(Path(self.temporary.name) / "doctor.db")
        self.service = DoctorService(self.repository)

    def tearDown(self):
        self.repository.close()
        self.temporary.cleanup()

    def test_running_executable_updates_last_working_but_failure_does_not(self):
        stamp = now()
        self.service.save_installation("working.exe", "1", stamp, "hash", stamp)
        self.service.save_installation("failed.exe", "2", stamp, "hash", stamp)
        self.service.commit()

        self.service.record_launch("exe", "working.exe", "1", "running", pid=42)
        self.service.record_launch("exe", "failed.exe", "2", "exited", code=-532462766)

        self.assertEqual(self.service.get("last_tested"), "failed.exe")
        self.assertEqual(self.service.get("last_working"), "working.exe")
        self.assertEqual(self.service.installation("failed.exe")["last_result"], "exited")
        self.assertEqual(self.service.launch_history()[0]["exit_hex"], "0xE0434352")

    def test_shortcut_does_not_change_executable_state(self):
        self.service.record_launch("shortcut", "akasia.appref-ms", None, "invoked")
        self.assertIsNone(self.service.get("last_tested"))
        self.assertEqual(self.service.launch_history()[0]["type"], "shortcut")


if __name__ == "__main__":
    unittest.main()