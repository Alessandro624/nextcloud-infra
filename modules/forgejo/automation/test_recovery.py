import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import backup_recovery as app


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = {"LOCAL_REPO": "/var/backups/forgejo/restic", "REMOTE_REPO": "rclone:test:forgejo", "RESTIC_PASSWORD_FILE": "/secret", "RCLONE_CONFIG": "/rclone", "MIN_FREE_GIB": "1"}
        self.env = patch.dict(os.environ, env)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.marker = patch.object(app, "MARKER", self.root / "maintenance")
        self.marker.start()
        self.addCleanup(self.marker.stop)
        self.workflow = app.Workflow(self.root)
        self.workflow.job = {"version": 1, "config": dict(self.workflow.config), "snapshot": "a" * 64, "restart_needed": False, "created": 1, "phase": "External copy", "full_check": False}
        self.workflow.save()

    def test_offline_then_recovery_reuses_snapshot(self):
        def offline(repo, command, *args):
            if command == "copy":
                raise OSError("offline")
            return ""
        with patch.object(self.workflow, "restic", side_effect=offline) as restic, patch.object(self.workflow, "notify"):
            with self.assertRaises(OSError):
                self.workflow.execute()
        self.assertTrue(self.workflow.path.exists())
        self.assertFalse(any(call.args[1] == "forget" for call in restic.call_args_list))
        restored = app.Workflow(self.root)
        with patch.object(restored, "restic", return_value="") as restic, patch.object(restored, "dc") as dc, patch.object(restored, "notify"):
            restored.execute()
        dc.assert_not_called()
        self.assertFalse(any(call.args[1] == "backup" for call in restic.call_args_list))
        copied = next(call.args for call in restic.call_args_list if call.args[1] == "copy")
        self.assertEqual(copied[-1], "a" * 64)
        self.assertFalse(restored.path.exists())

    def test_power_loss_restores_app_before_network(self):
        self.workflow.job["restart_needed"] = True
        self.workflow.save()
        restored = app.Workflow(self.root)
        order = []
        with patch.object(restored, "dc", side_effect=lambda *a: order.append("start")), patch.object(restored, "health"), patch.object(restored, "restic", side_effect=lambda *a: order.append(a[1]) or ""), patch.object(restored, "notify"):
            restored.execute()
        self.assertEqual(order[0], "start")
        self.assertLess(order.index("copy"), order.index("forget"))

    def test_changed_destination_is_not_used(self):
        with patch.dict(os.environ, {"REMOTE_REPO": "rclone:other:backup"}):
            with self.assertRaises(ValueError):
                app.Workflow(self.root)

    def test_verification_failure_never_prunes(self):
        def failed(repo, command, *args):
            if repo.startswith("rclone:") and command == "check":
                raise ValueError("integrity failure")
            return ""
        with patch.object(self.workflow, "restic", side_effect=failed) as restic, patch.object(self.workflow, "notify"):
            with self.assertRaises(ValueError):
                self.workflow.execute()
        self.assertTrue(self.workflow.path.exists())
        self.assertFalse(any(call.args[1] == "forget" for call in restic.call_args_list))
        self.assertFalse(any("--remove-all" in call.args for call in restic.call_args_list))

    def test_partial_snapshot_is_never_promoted(self):
        self.workflow.job["snapshot"] = None
        self.workflow.save()
        order = []
        def restic(repo, command, *args):
            if command == "backup":
                raise subprocess.CalledProcessError(3, ["restic", "backup"])
            return ""
        def dc(*args):
            order.append(args[0])
            return "container"
        with patch.object(self.workflow, "restic", side_effect=restic) as calls, patch.object(self.workflow, "dc", side_effect=dc), patch.object(self.workflow, "health"), patch.object(self.workflow, "notify"), patch.object(app.shutil, "disk_usage", return_value=Mock(free=10**15)), patch.object(Path, "is_file", return_value=True), patch.object(app, "run", return_value="false"):
            with self.assertRaises(subprocess.CalledProcessError):
                self.workflow.execute()
        self.assertIn("start", order)
        self.assertIsNone(self.workflow.job["snapshot"])
        self.assertFalse(any(call.args[1] == "copy" for call in calls.call_args_list))

    def test_restart_failure_keeps_durable_intent(self):
        self.workflow.job["restart_needed"] = True
        self.workflow.save()
        with patch.object(self.workflow, "dc", side_effect=OSError()), patch.object(self.workflow, "notify"), patch.object(self.workflow, "restic") as restic:
            with self.assertRaises(OSError):
                self.workflow.execute()
        restic.assert_not_called()
        self.assertTrue(app.Workflow(self.root).job["restart_needed"])

    def test_command_timeout_terminates_child_process_group(self):
        process = Mock(pid=123, returncode=None)
        process.communicate.side_effect = [subprocess.TimeoutExpired("restic", 1), ("", None)]
        with patch.object(app.subprocess, "Popen", return_value=process), patch.object(app.os, "killpg", create=True) as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                app.run(["restic", "check"], timeout=1)
        kill.assert_called_once_with(123, app.signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
