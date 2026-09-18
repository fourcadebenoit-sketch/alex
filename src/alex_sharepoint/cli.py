import argparse
import json
from pathlib import Path
import sys
import webbrowser

from . import __version__
from .config import Config, AlexError


def main(argv=None):
    parser = argparse.ArgumentParser(prog="alex", description="ALEX — Application Python locale sur SharePoint Online")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init-config", help="Créer un modèle de configuration, sans secret")
    init.add_argument("--output", default="alex-config.json")
    check = commands.add_parser("check-config", help="Vérifier la configuration sans se connecter")
    check.add_argument("--config", default="alex-config.json")
    serve = commands.add_parser("serve", help="Connexion Microsoft et application locale, mono-utilisateur")
    serve.add_argument("--config", default="alex-config.json")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    create = commands.add_parser("provision", help="Créer/configurer la liste sur le site choisi")
    create.add_argument("--config", default="alex-config.json")
    create.add_argument("--yes", action="store_true", help="Confirmer les modifications du site")
    args = parser.parse_args(argv)
    try:
        if args.command == "init-config":
            template = {"tenant_id": "GUID-DU-TENANT", "client_id": "GUID-APPLICATION-ENTRA", "site_url": "https://VOTRE-TENANT.sharepoint.com/sites/VOTRE-SITE", "list_id": ""}
            with Path(args.output).open("x", encoding="utf-8") as handle:
                json.dump(template, handle, indent=2)
            print("Modèle créé : renseignez les paramètres Microsoft 365 avec votre équipe informatique.")
            return
        config = Config.read(args.config)
        if args.command == "check-config":
            print("Configuration valide. " + ("Liste renseignée." if config.list_id else "Liste à créer ou list_id à renseigner."))
            return
        if args.command == "provision" and not args.yes:
            raise AlexError("Cette commande modifie le site (liste, colonnes, groupes). Relancez avec --yes après vérification du site cible.")
        if args.command == "serve" and not config.list_id:
            raise AlexError("Renseignez list_id, ou créez la liste avec alex provision.")
        if args.command == "serve" and not 0 <= args.port <= 65535:
            raise AlexError("Port invalide.")
        from .sharepoint import MicrosoftLogin, SharePoint
        login = MicrosoftLogin(config)
        print("Connexion Microsoft dans votre navigateur…")
        login.login()
        sp = SharePoint(config, login.token)
        if args.command == "provision":
            from .provision import provision
            if config.list_id:
                raise AlexError("La configuration contient déjà list_id. Pour provisionner par titre, utilisez une copie de configuration sans list_id afin d’éviter une ambiguïté de cible.")
            result = provision(sp)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("Recopiez list_id dans votre configuration. Elle n’a pas été écrasée.")
            return
        from .repository import Repository
        from .server import LocalServer
        user, roles = sp.identity()
        if not any(roles.values()):
            raise AlexError("Ajoutez votre compte à un groupe ALEX (membre direct), puis reconnectez-vous.")
        repository = Repository(sp, config.list_id, user, roles)
        server = LocalServer(args.port, repository)
        url = server.origin + "/#" + server.secret
        print("ALEX est lancé en local. Ctrl+C pour arrêter. Ne partagez pas le lien de session.")
        # The fragment is a local capability, not a Microsoft token. It is never sent in URLs to the HTTP server.
        print(url)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nALEX arrêté. Enregistrez vos modifications avant d’arrêter une session.")
        finally:
            server.server_close()
    except (AlexError, OSError) as exc:
        print("Erreur : " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
