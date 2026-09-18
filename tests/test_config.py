from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from alex_sharepoint.cli import main
from alex_sharepoint.config import Config, AlexError


class ConfigTests(unittest.TestCase):
    def test_valid_and_invalid_config(self):
        values = {"tenant_id": "12345678-1234-1234-1234-123456789012", "client_id": "12345678-1234-1234-1234-123456789012", "site_url": "https://tenant.sharepoint.com/sites/alex"}
        self.assertEqual(Config(**values).resource, "https://tenant.sharepoint.com")
        for url in ("http://tenant.sharepoint.com", "https://evil.example", "https://tenant.sharepoint.com@evil.example", "https://tenant.sharepoint.com/sites/x?token=x"):
            with self.assertRaises(AlexError):
                Config(**{**values, "site_url": url})

    def test_init_never_overwrites_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            with redirect_stdout(io.StringIO()):
                main(["init-config", "--output", str(path)])
            content = path.read_bytes()
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(["init-config", "--output", str(path)])
            self.assertEqual(path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
