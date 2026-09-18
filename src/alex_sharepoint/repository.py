"""Workflow and optimistic concurrency, executed in Python, not in the browser."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from threading import RLock
import time

from .config import AlexError

CHUNK_SIZE = 58000
CHUNK_COUNT = 12
PRIORITIES = {"urgent", "prioritaire", "sans_operation"}
DECISIONS = {"entree_accord_sans", "entree_accord_avec", "entree_refus", "poursuite_sans", "poursuite_avec", "rupture"}
OPINIONS = {"favorable", "favorable_1an", "defavorable"}


def now():
    return datetime.now(timezone.utc).isoformat()


def pack(data):
    # ASCII escaping avoids splitting UTF-16 surrogate pairs between SharePoint columns.
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    if len(raw) > CHUNK_SIZE * CHUNK_COUNT:
        raise AlexError("Dossier trop volumineux. Réduisez le contenu avant d’enregistrer.")
    return {f"AlexData{i+1}": raw[i*CHUNK_SIZE:(i+1)*CHUNK_SIZE] for i in range(CHUNK_COUNT)}


def unpack(row):
    try:
        raw = "".join(row.get(f"AlexData{i+1}") or "" for i in range(CHUNK_COUNT))
        raw = raw.encode("utf-16", errors="surrogatepass").decode("utf-16")
        data = json.loads(raw)
        validate(data)
        return data
    except (ValueError, TypeError, AttributeError, KeyError, UnicodeError) as exc:
        raise AlexError(f"Dossier SharePoint {row.get('Id', '?')} invalide. Aucune donnée remplacée.") from exc


def validate(data):
    if not isinstance(data, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", str(data.get("id", ""))):
        raise AlexError("Identifiant de dossier invalide.")
    if data.get("module") not in {"ppe", "pthr"}:
        raise AlexError("Typologie de dossier invalide.")
    if not isinstance(data.get("state"), dict) or not isinstance(data["state"].get("fields"), dict):
        raise AlexError("Contenu de formulaire invalide.")
    if not isinstance(data.get("info"), dict):
        raise AlexError("Informations de dossier invalides.")
    if data["info"].get("priorite", "sans_operation") not in PRIORITIES:
        raise AlexError("Priorité invalide.")


def manager_from(data):
    fields = data["state"]["fields"]
    prefix = "analyste_fiche_ppe_" if data["module"] == "ppe" else "analyste_fiche_"
    result = {}
    for name, value in fields.items():
        name = re.sub(r"^(val_|sel_|txt_|chk_)", "", name)
        if name.startswith(prefix + "d_"):
            result[name[len(prefix) + 2:]] = value
    raw = data["state"].get("managerControls", {})
    result.update(raw)
    result["client"] = {a: result.get(b, "") for a, b in (
        ("civilite", "civ"), ("nom", "nom"), ("nomMarital", "nom_marital"),
        ("prenom", "prenom"), ("ric", "ric"), ("ddn", "ddn"), ("paysResidence", "pays_residence"))}
    result.update({"id": data["id"], "typologie": data["module"],
                   "analyste": result.get("preco_par") or data["info"].get("trigramme", ""),
                   "dateReception": data.get("submittedAt") or datetime.fromtimestamp(data.get("timestamp", 0)/1000, timezone.utc).isoformat(),
                   "typeOperation": result.get("typeOp") or data["info"].get("typeOpLabel", ""),
                   "paysSensible": result.get("pays") or data["info"].get("pays", ""),
                   "montant_operation": result.get("montant_ops", ""),
                   "tag": data["info"].get("priorite", "sans_operation"),
                   "profilType": data["info"].get("ficheType", ""),
                   "contratNum": result.get("contratNum", ""),
                   "doc_factiva_nums": raw.get("doc_factiva_nums", []),
                   "ppe_cat": raw.get("ppe_cat") or fields.get("rad_analyste_fiche_ppe_cat", "")})
    if data["module"] == "ppe":
        for key in ("is_ppe", "is_rca_famille", "is_rca_assoc", "lien_pays_sf", "nom_ppe", "lien_ppe",
                    "connu_cliente", "connu_benef_nom", "connu_benef_eff_pm", "concerne", "origineDetection_autre"):
            result["ppe_" + key] = result.get(key, "")
    result.update(data.get("manager") or {})
    result.update(id=data["id"], typologie=data["module"],
                  statut=data["workflow"] if data.get("workflow") in {"signee", "rejetee"} else "a_traiter")
    return result


class Repository:
    def __init__(self, sp, list_id, user, roles):
        self.sp, self.user, self.roles = sp, user, roles
        self.base = f"/lists(guid'{list_id}')/items"
        self.rows = {}
        self.lock = RLock()

    def require(self, *roles):
        if not any(self.roles.get(role) for role in roles):
            raise AlexError("Votre rôle ALEX ne permet pas cette action.")

    @staticmethod
    def entry(row, etag=None):
        return {"row": row, "data": unpack(row), "etag": etag or row.get("@odata.etag") or row.get("odata.etag") or row.get("__metadata", {}).get("etag")}

    def load(self):
        with self.lock:
            self.require("analyst", "manager", "deontology")
            rows, cursor = {}, 0
            while True:
                payload, _ = self.sp.request("GET", self.base + f"?$filter=Id%20gt%20{cursor}&$orderby=Id&$top=100")
                page = payload.get("value", payload.get("results", []))
                for row in page:
                    entry = self.entry(row)
                    key = entry["data"]["id"]
                    if key in rows:
                        raise AlexError("Identifiant ALEX présent plusieurs fois. Chargement interrompu.")
                    rows[key] = entry
                if len(page) < 100:
                    break
                if len(rows) >= 10000:
                    raise AlexError("Limite de 10 000 dossiers atteinte. Un filtrage serveur par périmètre est nécessaire.")
                cursor = page[-1]["Id"]
            self.rows = rows

    def analyst_list(self):
        self.require("analyst")
        result = []
        for entry in self.rows.values():
            if entry["data"].get("workflow") == "supprime":
                continue
            data = deepcopy(entry["data"])
            data.update(_version=entry["etag"], status="brouillon" if data.get("workflow") in {"brouillon", "rejetee"} else "historique")
            result.append(data)
        return result

    def manager_list(self):
        self.require("manager", "deontology")
        return [{**manager_from(entry["data"]), "_version": entry["etag"]}
                for entry in self.rows.values()
                if entry["data"].get("workflow") in {"soumis", "deontologie", "signee", "rejetee"}]

    def check_version(self, data):
        prior = self.rows.get(data["id"])
        if prior and (not data.get("_version") or data["_version"] != prior["etag"]):
            raise AlexError("Dossier modifié depuis son ouverture. Rechargez avant de poursuivre.")
        return prior

    def write(self, data):
        prior = self.rows.get(data["id"])
        data = deepcopy(data)
        data.pop("_version", None)
        data["schemaVersion"] = 1
        body = {"Title": str(data.get("ref") or data["id"])[:255], "AlexKey": data["id"],
                "AlexType": data["module"], "AlexStatus": data["workflow"],
                "AlexPriority": data["info"].get("priorite", "sans_operation"),
                "AlexClient": str(data["info"].get("nom", ""))[:255],
                "AlexAnalyst": str(data["info"].get("trigramme", ""))[:255], **pack(data)}
        if prior:
            if not prior["etag"]:
                raise AlexError("Version SharePoint inconnue. Actualisez la liste.")
            path = self.base + f"({prior['row']['Id']})"
            self.sp.request("POST", path, data=body, headers={"X-HTTP-Method": "MERGE", "IF-MATCH": prior["etag"]})
            row, etag = self.sp.request("GET", path)
        else:
            row, etag = self.sp.request("POST", self.base, data=body)
            # Fetch the persisted item, including the exact version used by subsequent updates.
            if not row.get("AlexData1"):
                row, etag = self.sp.request("GET", self.base + f"({row['Id']})")
        self.rows[data["id"]] = self.entry(row, etag)
        return deepcopy(self.rows[data["id"]]["data"])

    def save_draft(self, incoming, submit=False):
        with self.lock:
            self.require("analyst")
            validate(incoming)
            prior = self.check_version(incoming)
            old = prior["data"] if prior else {}
            if old and (old["module"] != incoming["module"] or old["workflow"] not in {"brouillon", "rejetee"}):
                raise AlexError("Ce dossier n’est pas un brouillon modifiable de cette typologie.")
            if submit:
                manager = manager_from(incoming)
                if not all(str(value).strip() for value in (manager["client"]["nom"], manager["client"]["prenom"], manager.get("avis", ""))):
                    raise AlexError("Complétez le nom, le prénom et la synthèse avant de soumettre.")
                if manager.get("preco_analyste") not in DECISIONS:
                    raise AlexError("Préconisation obligatoire avant soumission.")
            data = {key: deepcopy(incoming[key]) for key in ("id", "module", "state", "info")}
            data.update(ownerId=old.get("ownerId", self.user["id"]), workflow="soumis" if submit else "brouillon",
                        status="historique" if submit else "brouillon", updatedBy=self.user["login"],
                        manager={} if submit else old.get("manager", {}), timestamp=int(time.time()*1000), dateUpdate=now())
            if submit:
                data["submittedAt"] = now()
            data["ref"] = "ALEX-" + data["module"].upper() + "-" + data["id"]
            return self.write(data)

    def save_manager(self, incoming):
        with self.lock:
            self.require("manager", "deontology")
            if not isinstance(incoming, dict) or incoming.get("id") not in self.rows:
                raise AlexError("Dossier introuvable.")
            old = self.check_version(incoming)["data"]
            if old["workflow"] not in {"soumis", "deontologie"}:
                raise AlexError("Dossier non modifiable.")
            previous = manager_from(old)
            deonto = not previous.get("signed_deonto") and incoming.get("signed_deonto") is True
            decision = incoming.get("statut") in {"signee", "rejetee"}
            if deonto:
                self.require("deontology")
                if incoming.get("deonto_avis") not in OPINIONS:
                    raise AlexError("Avis Déontologie obligatoire.")
            if decision:
                self.require("manager")
            if incoming.get("statut") == "signee":
                if old["module"] == "ppe" and not previous.get("signed_deonto"):
                    raise AlexError("L’avis Déontologie doit être enregistré avant la validation manager.")
                if incoming.get("decision") not in DECISIONS:
                    raise AlexError("Décision invalide.")
            if incoming.get("statut") == "rejetee" and len(str(incoming.get("motifRejet", "")).strip()) < 20:
                raise AlexError("Motif de rejet obligatoire : 20 caractères minimum.")
            manager = deepcopy(previous)
            allowed = []
            if self.roles.get("deontology"):
                allowed += ["deonto_trigramme", "deonto_detection", "deonto_avis", "deonto_explications", "signed_deonto"]
            if self.roles.get("manager"):
                allowed += ["statut", "decision", "commentaireManager", "motifRejet", "tag"]
            for key in allowed:
                if key in incoming:
                    manager[key] = deepcopy(incoming[key])
            if previous.get("signed_deonto"):
                for key, value in previous.items():
                    if key.startswith("deonto_") or key == "signed_deonto":
                        manager[key] = value
            if deonto:
                manager.update(deontoIdentite=self.user["login"], deonto_date_signature=now())
            if decision:
                manager.update(decideur=self.user["displayName"], decisionIdentite=self.user["login"], dateDecision=now())
            if manager.get("tag") not in PRIORITIES:
                raise AlexError("Priorité invalide.")
            data = deepcopy(old)
            data["info"]["priorite"] = manager["tag"]
            data.update(manager=manager, updatedBy=self.user["login"],
                        workflow=incoming["statut"] if decision else "deontologie" if deonto else old["workflow"])
            return self.write(data)

    def remove(self, key):
        with self.lock:
            self.require("analyst")
            prior = self.rows.get(key)
            if not prior or prior["data"]["workflow"] != "brouillon":
                raise AlexError("Seuls les brouillons peuvent être retirés.")
            data = deepcopy(prior["data"])
            data["workflow"] = "supprime"
            return self.write(data)

    def dispatch(self, action, payload=None):
        with self.lock:
            if action == "roles":
                return dict(self.roles)
            if action in {"loadAnalyst", "loadManager"}:
                self.require("analyst" if action == "loadAnalyst" else "manager", *([] if action == "loadAnalyst" else ["deontology"]))
                self.load()
            if action in {"loadAnalyst", "analystCached"}:
                return self.analyst_list()
            if action in {"loadManager", "managerCached"}:
                return self.manager_list()
            if action == "saveDraft":
                return self.save_draft(payload)
            if action == "submit":
                return self.save_draft(payload, submit=True)
            if action == "saveManager":
                return self.save_manager(payload)
            if action == "remove":
                return self.remove(payload)
            raise AlexError("Action ALEX inconnue.")
