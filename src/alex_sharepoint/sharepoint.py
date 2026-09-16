"""Delegated MSAL login and bounded SharePoint REST requests."""
import threading

from .config import AlexError


class MicrosoftLogin:
    def __init__(self, config):
        import msal
        self.scopes = [config.resource + "/.default"]
        self.app = msal.PublicClientApplication(
            config.client_id,
            authority="https://login.microsoftonline.com/" + config.tenant_id,
        )
        self.lock = threading.Lock()

    def login(self):
        result = self.app.acquire_token_interactive(scopes=self.scopes, timeout=300)
        if "access_token" not in result:
            raise AlexError("Connexion Microsoft refusée ou interrompue. Vérifiez l’application Entra et le consentement avec votre DSI.")

    def token(self):
        with self.lock:
            accounts = self.app.get_accounts()
            result = self.app.acquire_token_silent(self.scopes, account=accounts[0]) if accounts else None
        if not result or "access_token" not in result:
            raise AlexError("Session Microsoft expirée. Arrêtez puis relancez alex serve pour vous reconnecter.")
        return result["access_token"]


class SharePoint:
    def __init__(self, config, token_provider, session=None):
        import requests
        self.root = config.site_url.rstrip("/") + "/_api/web"
        self.token_provider = token_provider
        self.session = session or requests.Session()

    def request(self, method, path, *, data=None, headers=None):
        import requests
        if not path.startswith("/") or path.startswith("//"):
            raise AlexError("Chemin SharePoint invalide.")
        auth = {
            "Authorization": "Bearer " + self.token_provider(),
            "Accept": "application/json;odata=nometadata",
            "Content-Type": "application/json;odata=nometadata",
        }
        auth.update(headers or {})
        try:
            result = self.session.request(method, self.root + path, json=data,
                                          headers=auth, timeout=(10, 45), allow_redirects=False)
        except requests.RequestException as exc:
            # Never expose request objects containing access tokens or business data.
            raise AlexError("SharePoint injoignable. Vérifiez le réseau ; après une écriture, rechargez les dossiers avant de réessayer.") from exc
        messages = {
            401: "Session Microsoft refusée. Relancez l’application.",
            403: "Votre compte ou l’application Entra n’a pas les droits SharePoint nécessaires.",
            404: "Site, liste ou dossier SharePoint introuvable.",
            409: "Identifiant déjà présent. Rechargez les dossiers avant de réessayer.",
            412: "Un autre utilisateur a modifié le dossier. Rechargez avant de poursuivre.",
            429: "SharePoint est occupé. Attendez puis réessayez.",
            503: "SharePoint est temporairement indisponible.",
        }
        if not 200 <= result.status_code < 300:
            raise AlexError(messages.get(result.status_code, f"Échec SharePoint ({result.status_code})."))
        if result.status_code == 204 or not result.content:
            return {}, result.headers.get("ETag")
        try:
            value = result.json()
            return value.get("d", value), result.headers.get("ETag")
        except (ValueError, AttributeError) as exc:
            raise AlexError("Réponse SharePoint invalide. Aucune confirmation de sauvegarde.") from exc

    def identity(self):
        user, _ = self.request("GET", "/currentuser?$expand=Groups")
        groups = user.get("Groups", [])
        if isinstance(groups, dict):
            groups = groups.get("results", [])
        names = {group["Title"] for group in groups}
        admin = bool(user.get("IsSiteAdmin"))
        roles = {key: admin or name in names for key, name in (
            ("analyst", "ALEX Analystes"), ("manager", "ALEX Managers"),
            ("deontology", "ALEX Deontologie"))}
        return {"id": user["Id"], "login": user["LoginName"], "displayName": user["Title"]}, roles
