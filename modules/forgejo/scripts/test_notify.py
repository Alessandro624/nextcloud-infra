import contextlib
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import MagicMock, patch


class NotificationTests(unittest.TestCase):
    def invoke(self, urls):
        output = io.StringIO()
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b"OK"
        with patch("pathlib.Path.read_text", return_value=json.dumps(urls)), patch("sys.argv", ["notify.py", "backup", "success"]), patch(
            "urllib.request.build_opener", return_value=opener
        ), contextlib.redirect_stderr(output):
            try:
                runpy.run_path(str(Path(__file__).with_name("notify.py")))
                code = 0
            except SystemExit as error:
                code = error.code
        return code, opener, output.getvalue()

    def test_unapproved_destination_never_contacted_or_logged(self):
        urls = {"backup": "https://unapproved.example/private-secret", "service": "https://hc-ping.com/" + "1" * 8 + "-1111-1111-1111-" + "1" * 12}
        code, opener, output = self.invoke(urls)
        self.assertEqual(code, 1)
        opener.open.assert_not_called()
        self.assertNotIn("private-secret", output)

    def test_only_fixed_status_fields_are_sent(self):
        urls = {k: "https://hc-ping.com/" + d * 8 + "-" + d * 4 + "-" + d * 4 + "-" + d * 4 + "-" + d * 12 for k, d in [("backup", "1"), ("service", "2")]}
        code, opener, output = self.invoke(urls)
        self.assertEqual(code, 0)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, urls["backup"])
        self.assertEqual(json.loads(request.data), {"component": "forgejo", "check": "backup", "event": "success"})
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
