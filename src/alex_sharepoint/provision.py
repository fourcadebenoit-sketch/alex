"""Explicit, additive provisioning. Never run as a side effect of serving the app."""
from importlib.resources import files
import json
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

from .config import AlexError


def provision(sp, title="ALEX - Dossiers"):
    schema = json.loads(files("alex_sharepoint").joinpath("provisioning/schema.json").read_text())
    query = quote("Title eq '" + title.replace("'", "''") + "'", safe="")
    result, _ = sp.request("GET", "/lists?$filter=" + query)
    existing = result.get("value", result.get("results", []))
    created = not existing
    if created:
        entry, _ = sp.request("POST", "/lists", data={"Title": title, "BaseTemplate": 100, "Description": "Dossiers ALEX"})
    else:
        entry = existing[0]
    list_id = entry["Id"]
    path = f"/lists(guid'{list_id}')"
    if created:
        # A new empty list must not inherit site-wide write permissions.
        sp.request("POST", path + "/breakroleinheritance(copyRoleAssignments=false,clearSubscopes=false)")
    sp.request("POST", path, data={"EnableVersioning": True, "MajorVersionLimit": 500, "EnableAttachments": False},
               headers={"X-HTTP-Method": "MERGE", "IF-MATCH": "*"})
    fields, _ = sp.request("GET", path + "/fields?$select=InternalName,TypeAsString")
    found = {field["InternalName"]: field for field in fields.get("value", fields.get("results", []))}
    for field in schema["fields"]:
        name = field["name"]
        if name in found and found[name]["TypeAsString"] != field["type"]:
            raise AlexError(f"La colonne {name} existe avec un type incompatible. Aucune conversion automatique.")
        if name not in found:
            extra = ' RichText="FALSE" AppendOnly="FALSE" NumLines="6"' if field["type"] == "Note" else ""
            choices = "<CHOICES>" + "".join("<CHOICE>" + escape(c) + "</CHOICE>" for c in field.get("choices", [])) + "</CHOICES>" if field["type"] == "Choice" else ""
            xml = f'<Field Type={quoteattr(field["type"])} Name={quoteattr(name)} StaticName={quoteattr(name)} DisplayName={quoteattr(field["label"])}{extra}>{choices}</Field>'
            sp.request("POST", path + "/fields/CreateFieldAsXml", data={"parameters": {"SchemaXml": xml, "Options": 0}})
        attributes = {"Indexed": True} if field.get("indexed") else {}
        if name == "AlexKey":
            attributes.update(EnforceUniqueValues=True, Required=True)
        if attributes:
            sp.request("POST", path + f"/fields/getbyinternalnameortitle('{name}')", data=attributes,
                       headers={"X-HTTP-Method": "MERGE", "IF-MATCH": "*"})
    groups, _ = sp.request("GET", "/sitegroups?$select=Id,Title")
    found_groups = {g["Title"]: g for g in groups.get("value", groups.get("results", []))}
    roles, _ = sp.request("GET", "/roledefinitions?$select=Id,RoleTypeKind")
    contribute = next((r["Id"] for r in roles.get("value", roles.get("results", [])) if r["RoleTypeKind"] == 3), None)
    if not contribute:
        raise AlexError("Niveau de permission Contribution introuvable.")
    for name in ("ALEX Analystes", "ALEX Managers", "ALEX Deontologie"):
        group = found_groups.get(name)
        if not group:
            group, _ = sp.request("POST", "/sitegroups", data={"Title": name, "Description": "Membres directs autorisés dans ALEX"})
        if created:
            sp.request("POST", path + f"/roleassignments/addroleassignment(principalid={group['Id']},roledefid={contribute})")
    views, _ = sp.request("GET", path + "/views?$select=Title")
    titles = {v["Title"] for v in views.get("value", views.get("results", []))}
    for view in schema["views"]:
        if view["title"] not in titles:
            sp.request("POST", path + "/views/add", data={"parameters": {
                "Title": view["title"], "Query": view["query"], "RowLimit": 100, "Paged": True,
                "ViewFields": {"results": ["LinkTitle", "AlexClient", "AlexType", "AlexStatus", "AlexPriority", "AlexAnalyst", "Modified"]}}})
    return {"list_id": list_id, "created": created,
            "next_step": "Ajouter les membres directs aux groupes ALEX. Vérifier les permissions, notamment si la liste existait déjà ou si une première exécution a été interrompue."}
