from copy import deepcopy
import json
import re
import unittest

from alex_sharepoint.config import AlexError
from alex_sharepoint.repository import Repository, pack, unpack


def draft(key="test-1", kind="pthr"):
    prefix = "analyste_fiche_ppe_d_" if kind == "ppe" else "analyste_fiche_d_"
    return {"id": key, "module": kind, "info": {"nom": "TEST Alice", "trigramme": "TST", "priorite": "sans_operation"},
            "state": {"fields": {"val_" + prefix + "nom": "TEST", "val_" + prefix + "prenom": "Alice",
                                  "txt_" + prefix + "avis": "Analyse fictive", "sel_" + prefix + "preco_analyste": "poursuite_sans"}}, "timestamp": 0}


class FakeSP:
    def __init__(self):
        self.rows = {}
        self.fail = False

    def request(self, method, path, *, data=None, headers=None):
        if self.fail:
            self.fail = False
            raise AlexError("SharePoint indisponible")
        match = re.search(r"items\((\d+)\)", path)
        key = int(match[1]) if match else None
        if method == "GET" and key:
            return deepcopy(self.rows[key]), self.rows[key]["odata.etag"]
        if method == "GET":
            match = re.search(r"gt%20(\d+)", path)
            cursor = int(match[1]) if match else 0
            return {"value": [deepcopy(v) for k, v in sorted(self.rows.items()) if k > cursor][:100]}, None
        if key:
            if headers["IF-MATCH"] != self.rows[key]["odata.etag"]:
                raise AlexError("Un autre utilisateur a modifié le dossier")
            version = int(self.rows[key]["odata.etag"].strip('"')) + 1
            self.rows[key].update(deepcopy(data), **{"odata.etag": f'"{version}"'})
            return {}, None
        if any(v["AlexKey"] == data["AlexKey"] for v in self.rows.values()):
            raise AlexError("Identifiant déjà présent")
        key = len(self.rows) + 1
        self.rows[key] = {**deepcopy(data), "Id": key, "odata.etag": '"1"'}
        return deepcopy(self.rows[key]), '"1"'


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.sp = FakeSP()
        self.repo = Repository(self.sp, "12345678-1234-1234-1234-123456789012",
                               {"id": 1, "login": "alice@example.test", "displayName": "Alice TEST"},
                               {"analyst": True, "manager": True, "deontology": True})

    def test_unicode_compatibility_and_size(self):
        data = draft()
        data["extra"] = "é😀" * 10000
        self.assertEqual(unpack(pack(data)), data)
        old_raw = json.dumps(data, ensure_ascii=False)
        self.assertEqual(unpack({"AlexData1": old_raw}), data)
        with self.assertRaises(AlexError):
            pack({"long": "x" * 700000})

    def test_workflow_same_list_item(self):
        self.repo.save_draft(draft())
        self.repo.save_draft(self.repo.analyst_list()[0], True)
        review = self.repo.manager_list()[0]
        self.assertEqual(review["client"]["nom"], "TEST")
        self.repo.save_manager({**review, "statut": "rejetee", "motifRejet": "Veuillez compléter les éléments demandés dans le dossier."})
        correction = self.repo.analyst_list()[0]
        self.assertEqual(correction["status"], "brouillon")
        self.repo.save_draft(correction, True)
        self.repo.save_manager({**self.repo.manager_list()[0], "statut": "signee", "decision": "poursuite_sans", "decideur": "forged"})
        self.assertEqual(self.repo.manager_list()[0]["decideur"], "Alice TEST")
        self.assertEqual(len(self.sp.rows), 1)
        with self.assertRaises(AlexError):
            self.repo.save_manager(self.repo.manager_list()[0])

    def test_ppe_requires_persisted_opinion(self):
        self.repo.save_draft(draft(kind="ppe"), True)
        review = self.repo.manager_list()[0]
        with self.assertRaisesRegex(AlexError, "Déontologie"):
            self.repo.save_manager({**review, "statut": "signee", "decision": "poursuite_sans", "signed_deonto": True, "deonto_avis": "favorable"})
        self.repo.save_manager({**review, "signed_deonto": True, "deonto_avis": "favorable"})
        self.repo.save_manager({**self.repo.manager_list()[0], "statut": "signee", "decision": "poursuite_sans", "deonto_avis": "defavorable"})
        self.assertEqual(self.repo.manager_list()[0]["deonto_avis"], "favorable")

    def test_stale_read_and_etag(self):
        self.repo.save_draft(draft())
        old = self.repo.analyst_list()[0]
        self.repo.save_draft(old)
        with self.assertRaisesRegex(AlexError, "ouverture"):
            self.repo.save_draft(old)
        new = self.repo.analyst_list()[0]
        self.sp.rows[1]["odata.etag"] = '"99"'
        with self.assertRaisesRegex(AlexError, "autre utilisateur"):
            self.repo.save_draft(new)

    def test_failure_does_not_change_cache(self):
        self.repo.save_draft(draft())
        data = self.repo.analyst_list()[0]
        data["info"]["nom"] = "Changed"
        self.sp.fail = True
        with self.assertRaises(AlexError):
            self.repo.save_draft(data)
        self.assertEqual(self.repo.analyst_list()[0]["info"]["nom"], "TEST Alice")

    def test_server_roles(self):
        self.repo.save_draft(draft(), True)
        review = self.repo.manager_list()[0]
        self.repo.roles["manager"] = False
        with self.assertRaises(AlexError):
            self.repo.save_manager({**review, "statut": "signee", "decision": "poursuite_sans"})
        self.repo.roles["analyst"] = False
        with self.assertRaises(AlexError):
            self.repo.dispatch("loadAnalyst")

    def test_review_cannot_mutate_analyst_fields(self):
        self.repo.save_draft(draft(), True)
        self.repo.save_manager({**self.repo.manager_list()[0], "client": {"nom": "forged"}})
        self.assertEqual(self.repo.manager_list()[0]["client"]["nom"], "TEST")

    def test_paging_and_logical_removal(self):
        for i in range(101):
            data = {**draft("item-" + str(i)), "workflow": "brouillon"}
            self.sp.rows[i+1] = {"Id": i+1, "odata.etag": '"1"', **pack(data)}
        self.repo.load()
        self.assertEqual(len(self.repo.analyst_list()), 101)
        self.repo.remove("item-0")
        self.assertEqual(len(self.repo.analyst_list()), 100)
        self.assertEqual(len(self.sp.rows), 101)

    def test_validation_and_no_false_signature(self):
        with self.assertRaises(AlexError):
            self.repo.save_draft({**draft(), "id": "x');alert(1)//"})
        self.repo.save_draft(draft(), True)
        with self.assertRaises(AlexError):
            self.repo.save_manager({**self.repo.manager_list()[0], "statut": "signee", "decision": "invalid"})


if __name__ == "__main__":
    unittest.main()
