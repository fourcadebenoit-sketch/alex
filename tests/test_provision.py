import unittest
from alex_sharepoint.provision import provision


class ProvisionSP:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == "GET":
            return {"value": [{"Id": 1073741827, "RoleTypeKind": 3}] if path.startswith("/roledefinitions") else []}, None
        if path == "/lists":
            return {"Id": "12345678-1234-1234-1234-123456789012"}, None
        if path == "/sitegroups":
            return {"Id": 42}, None
        return {}, None


class ProvisionTests(unittest.TestCase):
    def test_provision_creates_empty_list_and_typed_fields(self):
        sp = ProvisionSP()
        result = provision(sp)
        self.assertTrue(result["created"])
        self.assertEqual(len([c for c in sp.calls if "CreateFieldAsXml" in c[1]]), 18)
        self.assertEqual(len([c for c in sp.calls if "addroleassignment" in c[1]]), 3)
        self.assertTrue(any("breakroleinheritance" in c[1] for c in sp.calls))
        self.assertFalse(any(c[0] == "DELETE" or c[1].endswith("/items") for c in sp.calls))
