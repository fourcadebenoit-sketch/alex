"""Single-user, loopback-only HTTP service. Not a multi-user production server."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
import json
import secrets
from urllib.parse import urlsplit

from .config import AlexError

MAX_BODY = 8 * 1024 * 1024
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/analyst.html": ("analyst.html", "text/html"), "/manager.html": ("manager.html", "text/html")}


class LocalServer(HTTPServer):
    def __init__(self, port, repository):
        self.repository = repository
        self.secret = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server_version = "ALEX"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(60)

    def log_message(self, *_args):
        # Request payloads, tokens and business data are intentionally not logged.
        pass

    def send(self, status, content, mime="application/json"):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=True, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        # srcdoc child forms have their own stricter CSP; parent scripts are self-hosted.
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self' about:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
        self.end_headers()
        self.wfile.write(content)

    def valid_host(self):
        if self.headers.get("Host") != self.server.origin.removeprefix("http://"):
            self.send(403, {"error": "Hôte refusé."})
            return False
        return True

    def do_GET(self):
        if not self.valid_host():
            return
        path = urlsplit(self.path).path
        if path not in ASSETS:
            self.send(404, {"error": "Page introuvable."})
            return
        name, mime = ASSETS[path]
        self.send(200, files("alex_sharepoint").joinpath("assets", name).read_bytes(), mime)

    def do_POST(self):
        if not self.valid_host():
            return
        if self.path != "/rpc":
            self.send(404, {"error": "Action inconnue."})
            return
        if self.headers.get("Origin") != self.server.origin:
            self.send(403, {"error": "Origine refusée."})
            return
        supplied = self.headers.get("X-Alex-Session", "")
        if not secrets.compare_digest(supplied, self.server.secret):
            self.send(403, {"error": "Session locale invalide. Ouvrez le lien de lancement ALEX."})
            return
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.send(415, {"error": "JSON requis."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.send(413, {"error": "Requête trop volumineuse ou vide."})
                return
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete body")
            message = json.loads(body)
            if not isinstance(message, dict) or not isinstance(message.get("action"), str):
                raise ValueError("Invalid action")
            result = self.server.repository.dispatch(message["action"], message.get("payload"))
            self.send(200, {"result": result})
        except AlexError as exc:
            self.send(400, {"error": str(exc)})
        except (ValueError, TypeError, KeyError, AttributeError):
            self.send(400, {"error": "Requête ou données invalides."})
        except Exception:
            self.send(500, {"error": "Action interrompue. Rechargez les dossiers avant de réessayer."})
