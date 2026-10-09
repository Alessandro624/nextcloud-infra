import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation as app


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = json.loads((app.backup.ROOT / "config/automation.example.json").read_text())
        self.cfg["timezone"] = "UTC"
        monitor = app.monitoring.Monitor({"enabled": False, "maximum_workflow_seconds": 7200})
        self.monitor_patch = patch.object(app.monitoring.Monitor, "load", return_value=monitor)
        self.monitor_patch.start()
        self.addCleanup(self.monitor_patch.stop)
        self.data = dict(app.backup.DEFAULTS, copy_type="local", copy_destination=str(self.root / "external"), export_directory=str(self.root / "exports"))
        self.service = app.Service(self.cfg, self.data, self.root / "state")
        self.now = 1780315200.0
        self.day = app.datetime.fromtimestamp(self.now, app.ZoneInfo("UTC")).date().isoformat()
        self.service.state["scheduled_day"] = self.day

    def allowed(self, starts):
        with patch.object(app, "next_slot", return_value=self.now + 50000):
            return app.manual_allowed(self.cfg, {"starts": starts, "scheduled_day": self.day}, self.now)[0]

    def test_daily_and_weekly_limits_are_rolling(self):
        self.assertFalse(self.allowed([{"at": self.now - 86399, "manual": True}]))
        self.assertTrue(self.allowed([{"at": self.now - 86400, "manual": True}]))
        self.assertFalse(self.allowed([{"at": self.now - n * 86400, "manual": True} for n in (2, 3, 6)]))

    def test_scheduled_runs_only_consume_cooldown(self):
        self.assertFalse(self.allowed([{"at": self.now - 3600, "manual": False}]))
        self.assertTrue(self.allowed([{"at": self.now - 21600, "manual": False}]))

    def test_upcoming_schedule_and_interrupted_state_block_manual(self):
        with patch.object(app, "next_slot", return_value=self.now + 3600):
            self.assertFalse(app.manual_allowed(self.cfg, {}, self.now)[0])
        self.assertFalse(app.manual_allowed(self.cfg, {"active": True}, self.now)[0])

    def test_quota_survives_restart_and_no_second_worker(self):
        with patch.object(app.time, "time", return_value=self.now), patch.object(app, "next_slot", return_value=self.now + 50000), patch.object(app.threading, "Thread") as thread:
            self.assertIn("started", self.service.begin(True))
            self.service.begin(True)
            self.assertEqual(thread.call_count, 1)
        restored = app.Service(self.cfg, self.data, self.root / "state")
        self.assertEqual(len(restored.state["starts"]), 1)
        self.assertTrue(restored.state["active"])

    def test_unauthorized_user_and_wrong_chat_cannot_confirm(self):
        self.cfg.update(telegram_user_ids=[1], telegram_chat_ids=[2])
        self.service.pending["key"] = (1, 2, self.now + 60)
        with patch.object(self.service, "api") as api, patch.object(self.service, "begin") as begin:
            for user, chat in ((3, 2), (1, 3)):
                self.service.handle({"callback_query": {"from": {"id": user}, "message": {"chat": {"id": chat}}, "data": "key"}})
            api.assert_not_called()
            begin.assert_not_called()

    def test_confirmation_is_single_use_and_expires(self):
        self.cfg.update(telegram_user_ids=[1], telegram_chat_ids=[2])
        event = {"callback_query": {"id": "cb", "from": {"id": 1}, "message": {"chat": {"id": 2}}, "data": "key"}}
        with patch.object(app.time, "time", return_value=self.now), patch.object(self.service, "api"), patch.object(self.service, "begin", return_value="started") as begin:
            self.service.pending["key"] = (1, 2, self.now + 60)
            self.service.handle(event)
            self.service.handle(event)
            self.assertEqual(begin.call_count, 1)
            self.service.pending["key"] = (1, 2, self.now)
            self.service.handle(event)
            self.assertEqual(begin.call_count, 1)

    def test_failed_backup_recovers_without_copy_or_pruning(self):
        states = [{"Running": True}, {"Running": False, "StartedAt": "old"}, {"Running": False, "StartedAt": "old", "ExitCode": 0}]
        with patch.object(app, "inspect", side_effect=states), patch.object(app, "validate_source"), patch.object(app, "aio"), patch.object(
            app.shutil, "disk_usage", return_value=Mock(free=10**15)
        ), patch.object(self.service, "restart") as restart, patch.object(app.backup, "copy") as copy, patch.object(self.service, "prune") as prune, patch.object(self.service, "report_backup") as report:
            self.service.work(False)
            restart.assert_called_once()
            copy.assert_not_called()
            prune.assert_not_called()
            self.assertEqual([call.args[0] for call in report.call_args_list], ["start", "fail"])
        self.assertTrue(self.service.state["failed"])

    def test_restart_failure_blocks_future_work(self):
        with patch.object(app, "inspect", side_effect=[{"Running": True}, {"Running": False}]), patch.object(app, "validate_source"), patch.object(
            app.shutil, "disk_usage", return_value=Mock(free=10**15)
        ), patch.object(app, "aio", side_effect=ValueError("failure")), patch.object(self.service, "restart", side_effect=ValueError("failure")):
            self.service.work(False)
        self.assertTrue(self.service.state["active"])

    def test_success_restarts_before_copy_and_retention(self):
        order = []
        folder = self.root / "20260601T020000Z-1234abcd"
        states = [{"Running": True}, {"Running": False, "StartedAt": "old"}, {"Running": False, "StartedAt": "new", "ExitCode": 0}]
        with patch.object(app, "inspect", side_effect=states), patch.object(app, "validate_source"), patch.object(app, "aio"), patch.object(app.backup, "run"), patch.object(
            app.shutil, "disk_usage", return_value=Mock(free=10**15)
        ), patch.object(app.backup, "export", return_value=folder), patch.object(self.service, "restart", side_effect=lambda: order.append("restart")), patch.object(
            app.backup, "copy", side_effect=lambda *args: order.append("copy")
        ), patch.object(
            self.service, "prune", side_effect=lambda: order.append("prune")
        ), patch.object(self.service, "report_backup", side_effect=lambda event: order.append("monitor:" + event)):
            self.service.work(False)
        self.assertEqual(order, ["monitor:start", "restart", "copy", "prune", "monitor:success"])
        self.assertFalse(self.service.state["failed"])

    def test_retention_only_deletes_recorded_generations(self):
        for n in range(4):
            name = f"2026060{n+1}T020000Z-1234abcd"
            for base in (self.root / "exports", self.root / "external"):
                folder = base / name
                folder.mkdir(parents=True)
                (folder / "aio-backup.tar").write_text("fixture")
            if n != 0:
                self.service.state["copies"].append({"name": name, "base": str((self.root / "exports").resolve()), "type": "local", "destination": self.data["copy_destination"]})
        self.service.prune()
        self.assertTrue((self.root / "exports/20260601T020000Z-1234abcd").exists())
        self.assertFalse((self.root / "exports/20260602T020000Z-1234abcd").exists())
        self.assertEqual(len(self.service.state["copies"]), 2)

    def test_source_mismatch_fails_closed(self):
        with patch.object(app.backup, "run", return_value='[{"Destination":"/mnt/borgbackup","Type":"volume","Name":"different"}]'):
            with self.assertRaises(ValueError):
                app.validate_source(self.data)

    def test_pending_daily_backup_has_priority(self):
        with patch.object(app, "next_slot", return_value=self.now + 50000):
            self.assertFalse(app.manual_allowed(self.cfg, {}, self.now)[0])

    def test_second_service_cannot_acquire_lock(self):
        with app.instance_lock(self.root / "lock"):
            with self.assertRaises(OSError):
                with app.instance_lock(self.root / "lock"):
                    self.fail("Second service acquired lock")

    def test_remote_retention_targets_only_exact_managed_files(self):
        self.data.update(copy_type="rclone", copy_destination="drive:dedicated-backups")
        for n in range(3):
            self.service.state["copies"].append({"name": f"2026060{n+1}T020000Z-1234abcd", "base": str((self.root / "exports").resolve()), "type": "rclone", "destination": "drive:dedicated-backups"})
        with patch.object(app.backup, "run") as run:
            self.service.prune()
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ["rclone", "delete", "drive:dedicated-backups/20260601T020000Z-1234abcd"])
            self.assertNotIn("purge", command)
            self.assertEqual(command.count("--include"), 3)

    def test_retention_failure_keeps_ledger_for_retry(self):
        self.data.update(copy_type="rclone", copy_destination="drive:dedicated-backups")
        for n in range(3):
            self.service.state["copies"].append({"name": f"2026060{n+1}T020000Z-1234abcd", "base": str((self.root / "exports").resolve()), "type": "rclone", "destination": "drive:dedicated-backups"})
        with patch.object(app.backup, "run", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                self.service.prune()
        self.assertEqual(len(self.service.state["copies"]), 3)


if __name__ == "__main__":
    unittest.main()
