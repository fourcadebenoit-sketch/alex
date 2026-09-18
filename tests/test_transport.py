import unittest
from alex_sharepoint.config import Config, AlexError
from alex_sharepoint.sharepoint import SharePoint


class Response:
    def __init__(self, status, data=None):
        self.status_code = status
        self.content = b"{}"
        self.headers = {"ETag": '"2"'}
        self.data = data or {}

    def json(self):
        return self.data


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.config = Config("12345678-1234-1234-1234-123456789012", "12345678-1234-1234-1234-123456789012", "https://tenant.sharepoint.com/sites/alex")

    def test_bounded_authenticated_request_no_redirect(self):
        session = Session(Response(200, {"value": []}))
        sp = SharePoint(self.config, lambda: "test-token", session)
        value, etag = sp.request("GET", "/lists")
        self.assertEqual(value, {"value": []})
        self.assertEqual(etag, '"2"')
        self.assertFalse(session.calls[0][1]["allow_redirects"])
        self.assertEqual(session.calls[0][1]["timeout"], (10, 45))
        self.assertEqual(session.calls[0][1]["headers"]["Authorization"], "Bearer test-token")

    def test_errors_are_sanitized_and_not_retried(self):
        for code in (302, 401, 403, 404, 409, 412, 429, 503):
            session = Session(Response(code, {"error": "sensitive upstream content"}))
            with self.assertRaises(AlexError) as ctx:
                SharePoint(self.config, lambda: "test-token", session).request("POST", "/lists", data={})
            self.assertNotIn("test-token", str(ctx.exception))
            self.assertNotIn("sensitive", str(ctx.exception))
            self.assertEqual(len(session.calls), 1)

    def test_identity_roles_from_sharepoint(self):
        session = Session(Response(200, {"Id": 9, "Title": "Test", "LoginName": "test@example.test", "Groups": [{"Title": "ALEX Managers"}]}))
        user, roles = SharePoint(self.config, lambda: "test-token", session).identity()
        self.assertTrue(roles["manager"])
        self.assertFalse(roles["analyst"])
        self.assertEqual(user["id"], 9)
