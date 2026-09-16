"""Non-secret configuration. Credentials are never loaded from this file."""
from dataclasses import dataclass
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID


class AlexError(Exception):
    """An error that can safely be shown to the user."""


@dataclass(frozen=True)
class Config:
    tenant_id: str
    client_id: str
    site_url: str
    list_id: str = ""

    def __post_init__(self):
        for value in (self.tenant_id, self.client_id):
            try:
                UUID(value)
            except (ValueError, TypeError, AttributeError) as exc:
                raise AlexError("tenant_id et client_id doivent être des GUID Entra valides.") from exc
        url = urlsplit(self.site_url)
        if (url.scheme != "https" or not url.hostname or
                not url.hostname.endswith(".sharepoint.com") or url.username or
                url.password or url.port not in (None, 443) or url.query or url.fragment or
                ".." in url.path.split("/")):
            raise AlexError("site_url doit être l’URL HTTPS d’un site SharePoint Online commercial (.sharepoint.com).")
        if self.list_id:
            try:
                object.__setattr__(self, "list_id", str(UUID(self.list_id)))
            except ValueError as exc:
                raise AlexError("list_id doit être le GUID de la liste, sans accolades.") from exc

    @property
    def resource(self):
        return "https://" + urlsplit(self.site_url).netloc

    @classmethod
    def read(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) - {"tenant_id", "client_id", "site_url", "list_id"}:
                raise ValueError("Champs inattendus")
            return cls(**data)
        except (OSError, TypeError, ValueError) as exc:
            raise AlexError("Configuration illisible ou invalide. Utilisez alex init-config.") from exc
