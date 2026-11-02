import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import forgejo_bot as app


class BotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = json.loads(Path(__file__).with_name("config.example.json").read_text())
        self.cfg.update(user_ids=[1], chat_ids=[2], timezone="UTC", backup_enabled=True)
        token = self.root / "token"
        token.write_text("TEST_SECRET")
        self.cfg["token_file"] = str(token)
        self.bot = app.Bot(self.cfg, self.root)
        self.now = app.datetime(2026, 10, 22, 12, tzinfo=app.ZoneInfo("UTC")).timestamp()

    def test_rolling_limits_and_clock(self):
        for starts in ([self.now - 1], [self.now - d * 86400 for d in (2, 3, 6)], [self.now + 1]):
            self.assertFalse(app.allowed(self.cfg, {"starts": starts}, self.now, "success", 0)[0])
        self.assertTrue(app.allowed(self.cfg, {"starts": [self.now - 86400]}, self.now, "success", 0)[0])

    def test_schedule_and_running_fail_closed(self):
        stamp = app.datetime(2026, 10, 22, 3, tzinfo=app.ZoneInfo("UTC")).timestamp()
        self.assertFalse(app.allowed(self.cfg, {}, stamp, "success", 0)[0])
        for status in ("running", "overdue", "unavailable"):
            self.assertFalse(app.allowed(self.cfg, {}, self.now, status, 0)[0])

    def test_permission_failure_consumes_quota_across_restart(self):
        with patch.object(app.time, "time", return_value=self.now), patch.object(app, "unit_status", return_value=("success", 0)), patch.object(app.subprocess, "run", side_effect=OSError()):
            self.assertIn("uncertain", self.bot.start_backup())
        restored = app.Bot(self.cfg, self.root)
        self.assertEqual(restored.state["starts"], [self.now])

    def test_exact_start_command_and_no_replay(self):
        with patch.object(app.time, "time", return_value=self.now), patch.object(app, "unit_status", return_value=("success", 0)), patch.object(app.subprocess, "run") as run:
            self.bot.start_backup()
            self.bot.start_backup()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0], ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", "forgejo-backup.service"])

    def test_confirmation_single_use_and_both_allowlists(self):
        event = {"callback_query": {"id": "cb", "data": "key", "from": {"id": 1}, "message": {"chat": {"id": 2}}}}
        self.bot.pending["key"] = (1, 2, self.now + 60)
        with patch.object(app.time, "time", return_value=self.now), patch.object(self.bot, "api"), patch.object(self.bot, "start_backup", return_value="requested") as start:
            event["callback_query"]["from"]["id"] = 3
            self.bot.handle(event)
            start.assert_not_called()
            event["callback_query"]["from"]["id"] = 1
            event["callback_query"]["message"]["chat"]["id"] = 3
            self.bot.handle(event)
            start.assert_not_called()
            event["callback_query"]["message"]["chat"]["id"] = 2
            self.bot.handle(event)
            self.bot.handle(event)
            start.assert_called_once()

    def test_expired_and_old_messages_do_not_start(self):
        with patch.object(app.time, "time", return_value=self.now), patch.object(self.bot, "api") as api:
            self.bot.handle({"message": {"from": {"id": 1}, "chat": {"id": 2}, "date": self.now - 61, "text": "/backup"}})
            api.assert_not_called()
        self.bot.pending["old"] = (1, 2, self.now)
        with patch.object(app.time, "time", return_value=self.now), patch.object(self.bot, "api"), patch.object(self.bot, "start_backup") as start:
            self.bot.handle({"callback_query": {"id": "cb", "data": "old", "from": {"id": 1}, "message": {"chat": {"id": 2}}}})
            start.assert_not_called()

    def test_alert_delivery_retries_and_recovers(self):
        with patch.object(self.bot, "status", return_value={"service": "unavailable"}), patch.object(self.bot, "api", side_effect=[RuntimeError(), None]) as api:
            self.bot.poll_alerts()
            self.assertEqual(self.bot.state["alerts"], {})
            self.bot.poll_alerts()
            self.bot.poll_alerts()
            self.assertEqual(api.call_count, 2)
        with patch.object(self.bot, "status", return_value={"service": "healthy"}), patch.object(self.bot, "api") as api:
            self.bot.poll_alerts()
            api.assert_called_once()

    def test_api_exception_redacts_token(self):
        with patch.object(app, "client", side_effect=ValueError("TEST_SECRET")):
            with self.assertRaises(RuntimeError) as error:
                self.bot.api("getUpdates")
        self.assertNotIn("TEST_SECRET", str(error.exception))

    def test_empty_allowlists_are_rejected_except_discovery(self):
        self.cfg["user_ids"] = []
        path = self.root / "config.json"
        path.write_text(json.dumps(self.cfg))
        with self.assertRaises(ValueError):
            app.settings(path)
        app.settings(path, discover=True)

    def test_systemd_retry_wait_is_not_reported_as_running_backup(self):
        output = "LoadState=loaded\nActiveState=activating\nSubState=auto-restart\nExecMainStartTimestampMonotonic=1000000\nExecMainExitTimestampMonotonic=2000000\n"
        with patch.object(app.subprocess, "run", return_value=type("Result", (), {"stdout": output})()):
            status, start = app.unit_status()
        self.assertEqual(status, "retrying")
        self.assertFalse(app.allowed(self.cfg, {}, self.now, status, start)[0])


if __name__ == "__main__":
    unittest.main()
