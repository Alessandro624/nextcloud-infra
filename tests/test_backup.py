import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("backup", Path(__file__).resolve().parents[1] / "scripts/backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class BackupTests(unittest.TestCase):
    def test_unexpected_export_files_are_not_uploaded(self):
        folder = self.export_fixture()
        (folder / "credentials.txt").write_text("private fixture")
        with patch.object(backup, "run") as run:
            with self.assertRaises(ValueError):
                backup.copy(dict(backup.DEFAULTS, copy_type="rclone", copy_destination="offsite:backup"), folder)
            run.assert_not_called()

    def test_linked_archive_is_rejected(self):
        folder = self.export_fixture()
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                backup.verify(folder)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def export_fixture(self):
        folder = self.root / "generation"
        folder.mkdir()
        (folder / "aio-backup.tar").write_bytes(b"fixture archive bytes")
        (folder / "aio-backup.tar.sha256").write_text(backup.digest(folder / "aio-backup.tar") + "  aio-backup.tar\n")
        return folder

    def test_volume_and_path_configuration(self):
        cfg = self.root / "backup.json"
        for mode, source in (("volume", "nextcloud_aio_backupdir"), ("path", "/mnt/backup")):
            cfg.write_text(json.dumps({"source_type": mode, "source": source}))
            self.assertEqual(backup.config(cfg)["source"], source)

    def test_invalid_settings_rejected(self):
        cfg = self.root / "backup.json"
        for value in (
            {"source_type": "wrong"},
            {"source_type": "path", "source": "/"},
            {"copy_type": "local", "copy_destination": "relative"},
            {"copy_type": "rclone", "copy_destination": "https://example.com"},
            {"password": "not-accepted"},
        ):
            cfg.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                backup.config(cfg)

    def test_active_master_blocks_export(self):
        def fake(args):
            if args[1] == "ps":
                return "nextcloud-aio-mastercontainer\nnextcloud-aio-borgbackup"
            return json.dumps({"Running": True})

        with patch.object(backup, "run", side_effect=fake):
            with self.assertRaisesRegex(ValueError, "Stop nextcloud-aio-mastercontainer"):
                backup.export(dict(backup.DEFAULTS))

    def test_failed_borg_blocks_export(self):
        responses = ["nextcloud-aio-mastercontainer\nnextcloud-aio-borgbackup", '{"Running": false, "ExitCode": 0}', '{"Running": false, "ExitCode": 2}']
        with patch.object(backup, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "Last Borg operation failed"):
                backup.stopped()

    def test_tamper_detected_before_copy(self):
        folder = self.export_fixture()
        (folder / "aio-backup.tar").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            backup.copy(dict(backup.DEFAULTS), folder)

    def test_local_copy_and_no_overwrite(self):
        folder = self.export_fixture()
        destination = self.root / "external"
        destination.mkdir()
        cfg = dict(backup.DEFAULTS, copy_type="local", copy_destination=str(destination))
        backup.copy(cfg, folder)
        backup.verify(destination / folder.name)
        with self.assertRaisesRegex(ValueError, "already exists"):
            backup.copy(cfg, folder)

    def test_missing_destination_not_created(self):
        folder = self.export_fixture()
        destination = self.root / "unmounted"
        with self.assertRaisesRegex(ValueError, "already exist"):
            backup.copy(dict(backup.DEFAULTS, copy_type="local", copy_destination=str(destination)), folder)
        self.assertFalse(destination.exists())

    def test_remote_failure_does_not_publish_success(self):
        folder = self.export_fixture()
        calls = []

        def fake(args):
            calls.append(args)
            if args[1] == "check":
                raise subprocess.CalledProcessError(1, args)
            return ""

        with patch.object(backup, "run", side_effect=fake):
            with self.assertRaises(subprocess.CalledProcessError):
                backup.copy(dict(backup.DEFAULTS, copy_type="rclone", copy_destination="offsite:backups"), folder)
        self.assertEqual([c[1] for c in calls], ["copy", "check"])
        self.assertIn("--immutable", calls[0])
        self.assertIn("--download", calls[1])

    def test_prepare_path_does_not_create_a_volume(self):
        with patch.object(backup, "run") as mocked:
            backup.prepare(dict(backup.DEFAULTS, source_type="path", source="/mnt/backups"))
            mocked.assert_not_called()

    def test_export_failure_does_not_publish_generation(self):
        base = self.root / "exports"
        with patch.object(backup, "stopped"), patch.object(backup, "run", side_effect=["exists", subprocess.CalledProcessError(1, ["docker", "run"])]):
            with self.assertRaises(subprocess.CalledProcessError):
                backup.export(dict(backup.DEFAULTS, export_directory=str(base)))
        self.assertTrue(all(p.name.startswith(".partial-") for p in base.iterdir()))

    def test_export_cannot_be_inside_source(self):
        cfg = dict(backup.DEFAULTS, source_type="path", source=str(self.root), export_directory=str(self.root / "nested"))
        with patch.object(backup, "stopped"):
            with self.assertRaisesRegex(ValueError, "outside the backup source"):
                backup.export(cfg)

    def test_remote_success_publishes_marker_last(self):
        folder = self.export_fixture()
        with patch.object(backup, "run", return_value="") as mocked:
            backup.copy(dict(backup.DEFAULTS, copy_type="rclone", copy_destination="offsite:backups"), folder)
        calls = [call.args[0] for call in mocked.call_args_list]
        self.assertEqual([c[1] for c in calls], ["copy", "check", "copyto"])
        self.assertTrue(calls[-1][3].endswith("/COPY-VERIFIED.txt"))


if __name__ == "__main__":
    unittest.main()
