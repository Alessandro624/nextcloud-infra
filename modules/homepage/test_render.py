import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from render import https_url


class RenderTests(unittest.TestCase):
    def test_rejects_credentials_and_non_root_urls(self):
        for value in (
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/?token=x",
            "https://example.com/#secret",
            "https://example.com/path",
            "https://example.com:0",
            "https://example.com\n",
        ):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                https_url(value)

    def test_optional_forgejo_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "home.html"
            command = [sys.executable, str(Path(__file__).with_name("render.py")), "--nextcloud", "https://files.example.com", "--output", str(output)]
            subprocess.run(command, check=True, capture_output=True)
            page = output.read_text(encoding="utf-8")
            self.assertIn("https://files.example.com/", page)
            self.assertNotIn("{{", page)
            self.assertNotIn("Open Forgejo", page)
            self.assertIn("noopener noreferrer", page)
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), page)


if __name__ == "__main__":
    unittest.main()
