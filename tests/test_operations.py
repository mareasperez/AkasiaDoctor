import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from akasia.config import AppPaths
from akasia.operations import DoctorOperations
from akasia.repository import DoctorRepository
from akasia.service import DoctorService


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.local = self.root / "local"
        self.local.mkdir()
        self.paths = AppPaths(self.root / "data")
        self.paths.data.mkdir()
        self.repository = DoctorRepository(self.paths.database)
        self.service = DoctorService(self.repository)
        self.operations = DoctorOperations(self.service, self.paths, local=self.local)

    def tearDown(self):
        self.repository.close()
        self.temporary.cleanup()

    def test_scan_records_matching_executable_and_scan_time(self):
        cache = self.local / "Apps" / "2.0" / "0123456789abcdef"
        cache.mkdir(parents=True)
        executable = cache / "Akasia.exe"
        executable.touch()
        (cache / "Other.exe").touch()
        with patch("akasia.operations.shortcut_roots", return_value=[]):
            self.assertEqual(self.operations.scan(), (1, 0))
        installation = self.service.installation(str(executable))
        assert installation is not None
        self.assertEqual(installation["identity_hash"], "0123456789abcdef")
        self.assertIsNotNone(self.service.get("last_scan"))

    def test_config_scan_and_reset_back_up_only_corrupted_file(self):
        valid = self.local / "Akasia" / "valid" / "user.config"
        corrupted = self.local / "Akasia" / "broken" / "user.config"
        valid.parent.mkdir(parents=True)
        corrupted.parent.mkdir(parents=True)
        valid.write_text("<settings/>", encoding="utf-8")
        corrupted.write_bytes(b"<settings>\x00")

        items = self.operations.config_health()
        self.assertEqual(len(items), 2)
        self.assertEqual(sum(not item["valid"] for item in items), 1)
        results, folder = self.operations.reset_configs()
        self.assertEqual(results[0][1], "reset")
        self.assertTrue(valid.exists())
        self.assertFalse(corrupted.exists())
        assert folder is not None
        self.assertEqual(len(list(folder.glob("*_user.config"))), 1)
        self.assertEqual(len(list(corrupted.parent.glob("user.config.corrupted.*"))), 1)
        self.assertEqual(len(self.service.report()["backups"]), 1)

    def test_export_report_uses_configured_directory(self):
        exported = self.operations.export_report()
        self.assertEqual(exported.parent, self.paths.reports)
        self.assertIn('"network_tests": []', exported.read_text(encoding="utf-8"))

    def test_open_logs_folder_creates_directory_and_opens_explorer(self):
        with patch("akasia.operations.os.startfile") as open_folder:
            opened = self.operations.open_logs()
        self.assertEqual(opened, self.paths.logs)
        self.assertTrue(self.paths.logs.is_dir())
        open_folder.assert_called_once_with(str(self.paths.logs))


if __name__ == "__main__":
    unittest.main()