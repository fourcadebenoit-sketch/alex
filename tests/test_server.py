import http.client
from importlib.resources import files
import json
import threading
import unittest

from alex_sharepoint.server import LocalServer


class DummyRepository:
    def dispatch(self, action, payload=None):
        return {"analyst": True} if action == "roles" else []


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = LocalServer(0, DummyRepository())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method="POST", path="/rpc", headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        client.request(method, path, json.dumps({"action": "roles"}), headers=headers or {})
        response = client.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        client.close()
        return result

    def test_rpc_requires_session_and_origin(self):
        status, _, _ = self.request()
        self.assertEqual(status, 403)
        headers = {"Content-Type": "application/json", "Origin": self.server.origin, "X-Alex-Session": self.server.secret}
        status, content, _ = self.request(headers=headers)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(content)["result"]["analyst"])
        headers["Origin"] = "https://untrusted.example"
        self.assertEqual(self.request(headers=headers)[0], 403)

    def test_dns_rebinding_and_traversal_rejected(self):
        self.assertEqual(self.request("GET", "/", {"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/../config.json")[0], 404)

    def test_assets_available_without_data_or_token(self):
        for url in ("/", "/app.js", "/analyst.html", "/manager.html"):
            status, content, headers = self.request("GET", url)
            self.assertEqual(status, 200)
            self.assertNotIn(self.server.secret.encode(), content)
            self.assertEqual(headers["Cache-Control"], "no-store")
        for name in ("analyst.html", "manager.html"):
            content = files("alex_sharepoint").joinpath("assets", name).read_text()
            self.assertNotIn("fetch('/api/", content)
            self.assertIn("AlexBridge", content)


if __name__ == "__main__":
    unittest.main()
