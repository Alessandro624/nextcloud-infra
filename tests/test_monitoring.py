import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation as app
import monitoring as mon


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "credentials").mkdir()
        self.cfg = json.loads((app.backup.ROOT / "config/healthchecks.example.json").read_text())
        (self.root / "config/healthchecks.example.json").write_text(json.dumps(self.cfg))
        self.urls = {"backup": "https://hc-ping.com/00000000-0000-0000-0000-000000000001", "service": "https://hc-ping.com/00000000-0000-0000-0000-000000000002"}

    def enabled(self):
        self.cfg["enabled"] = True
        (self.root / "config/healthchecks.json").write_text(json.dumps(self.cfg))
        (self.root / "credentials/healthchecks.secret").write_text(json.dumps(self.urls))
        return mon.Monitor.load(self.root)

    def test_disabled_needs_no_secret_and_makes_no_request(self):
        with patch.object(mon, "http_client") as client:
            self.assertTrue(mon.Monitor.load(self.root).ping("service", "success", {}))
            client.assert_not_called()

    def test_payload_excludes_secrets_and_arbitrary_strings(self):
        raw = {"token": "TOPSECRET", "phase": "TOPSECRET", "error_code": "TOPSECRET", "nextcloud": "TOPSECRET", "last_copy": "TOPSECRET", "export_free_gib": float("nan"), "path": "TOPSECRET"}
        payload = mon.safe_payload(raw)
        self.assertNotIn("TOPSECRET", json.dumps(payload))
        self.assertIsNone(payload["export_free_gib"])
        self.assertEqual(payload["error_code"], "STATUS_UNAVAILABLE")

    def test_urls_reject_unapproved_hosts_credentials_query_and_http(self):
        for url in ("http://hc-ping.com/", self.urls["backup"].replace("hc-ping.com", "evil.example"), self.urls["backup"] + "?secret=x", self.urls["backup"] + "#fragment", self.urls["backup"].replace("hc-ping.com", "user:pass@hc-ping.com"), self.urls["backup"].replace("hc-ping.com", "hc-ping.com:8443"), self.urls["backup"] + "/start"):
            self.urls["service"] = url
            with self.assertRaises(ValueError) as error:
                self.enabled()
            self.assertNotIn(url, str(error.exception))

    def test_distinct_checks_required(self):
        self.urls["service"] = self.urls["backup"]
        with self.assertRaises(ValueError):
            self.enabled()

    def test_post_is_bounded_and_response_is_not_interpreted_as_commands(self):
        monitor = self.enabled()
        response = Mock(status=200)
        response.read.return_value = b"OK"
        client = Mock()
        client.open.return_value.__enter__ = Mock(return_value=response)
        client.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(mon, "http_client", return_value=client):
            self.assertTrue(monitor.ping("service", "fail", {"error_code": "LOW_SPACE", "token": "SECRET"}))
        request = client.open.call_args.args[0]
        self.assertEqual(request.full_url, self.urls["service"] + "/fail")
        self.assertEqual(request.method, "POST")
        self.assertNotIn(b"SECRET", request.data)
        self.assertEqual(client.open.call_args.kwargs["timeout"], 5)
        response.read.assert_called_once_with(64)

    def test_network_failure_redacts_secret_url_and_returns_false(self):
        monitor = self.enabled()
        output = io.StringIO()
        with patch.object(mon, "http_client", side_effect=RuntimeError(self.urls["backup"])), contextlib.redirect_stdout(output):
            self.assertFalse(monitor.ping("backup", "start", {}))
        self.assertNotIn(self.urls["backup"], output.getvalue())

    def test_redirect_is_rejected_and_no_environment_proxy_is_used(self):
        with self.assertRaises(ValueError):
            mon.NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")
        with patch.object(mon.urllib.request, "build_opener") as build, patch.object(mon.urllib.request, "ProxyHandler") as proxy:
            mon.http_client()
            proxy.assert_called_once_with({})
            self.assertIsInstance(build.call_args.args[1], mon.NoRedirect)

    def test_success_like_error_response_is_not_accepted(self):
        monitor = self.enabled()
        response = Mock(status=200)
        response.read.return_value = b"OK (not found)"
        client = Mock()
        client.open.return_value.__enter__ = Mock(return_value=response)
        client.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(mon, "http_client", return_value=client):
            self.assertFalse(monitor.ping("backup", "success", {}))

    def service(self):
        cfg = json.loads((app.backup.ROOT / "config/automation.example.json").read_text())
        data = dict(app.backup.DEFAULTS, export_directory=str(self.root))
        with patch.object(mon.Monitor, "load", return_value=mon.Monitor(self.cfg)):
            return app.Service(cfg, data, self.root / "state")

    def test_health_and_disk_report_with_bounded_maintenance(self):
        service = self.service()
        service.busy = True
        service.state.update(active=True, active_since=app.time.time(), phase="Export")
        with patch.object(app, "inspect", return_value={"Running": False}), patch.object(app.shutil, "disk_usage", return_value=Mock(free=100 * 1024**3)):
            report = service.status_report()
            self.assertTrue(report["maintenance"])
            self.assertEqual(report["nextcloud"], "stopped")
            self.assertEqual(report["error_code"], "NONE")
            service.state["active_since"] -= 7201
            self.assertEqual(service.status_report()["error_code"], "WORKFLOW_TIMEOUT")

    def test_healthy_containers_do_not_hide_stalled_scheduler(self):
        service = self.service()
        service.scheduler_tick -= 100
        with patch.object(app, "inspect", return_value={"Running": True, "Health": {"Status": "healthy"}}), patch.object(app.shutil, "disk_usage", return_value=Mock(free=100 * 1024**3)):
            self.assertEqual(service.status_report()["error_code"], "SCHEDULER_STALLED")

    def test_reporting_failure_cannot_escape_into_workflow(self):
        service = self.service()
        service.monitor.cfg["enabled"] = True
        with patch.object(service, "status_report", side_effect=RuntimeError("broken")) as status:
            service.report_backup("start")
            status.assert_not_called()
            self.assertEqual(service.monitor_events.get_nowait(), "start")

    def test_full_reporting_queue_does_not_block_workflow(self):
        service = self.service()
        service.monitor.cfg["enabled"] = True
        for _ in range(16):
            service.report_backup("start")
        service.report_backup("fail")
        self.assertEqual(service.monitor_events.qsize(), 16)


if __name__ == "__main__":
    unittest.main()
