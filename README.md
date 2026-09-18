# ALEX — Package Python

Version 1.0.0. Python 3.11 ou supérieur. Cible : SharePoint Online commercial.

Cette version conserve les deux interfaces analyste et manager de la livraison précédente, ainsi que sa liste ALEX et ses champs `AlexData1` à `AlexData12`. La connexion SharePoint et les transitions de dossier sont maintenant exécutées en Python. Les formulaires restent en HTML/JavaScript : un navigateur est nécessaire.

**Ce n’est plus un composant à installer dans SharePoint.** Le package lance une application sur le poste de chaque utilisateur, accessible uniquement sur `127.0.0.1`. SharePoint reste la source de données partagée. Python ne peut pas s’exécuter dans une page SharePoint moderne. Aucun serveur d’entreprise multi-utilisateur, reverse proxy ou intégration iframe dans SharePoint n’est inclus.

## Installation

Dans un terminal, après extraction du ZIP :

```text
python -m venv .venv
```

Sous Windows :

```text
.venv\Scripts\activate
```

Sous macOS/Linux :

```text
source .venv/bin/activate
```

Puis, si le poste a un accès direct à PyPI :

```text
python -m pip install dist/alex_sharepoint-1.0.0-py3-none-any.whl
alex init-config
```

**Poste sans accès à pypi.org (proxy d'entreprise, pas de droits admin pour le configurer)** : les dépendances (`msal`, `requests` et leurs sous-dépendances) sont fournies pré-téléchargées dans `vendor/wheels/`. Installer entièrement hors-ligne avec :

```text
python -m pip install --no-index --find-links vendor/wheels dist/alex_sharepoint-1.0.0-py3-none-any.whl
alex init-config
```

`--no-index` empêche pip de contacter pypi.org ; `--find-links vendor/wheels` lui indique où trouver les paquets à la place. Voir `vendor/wheels/README.md` pour le détail des versions vendorisées et la procédure si le poste cible a une autre plateforme ou version de Python.

Le fichier `alex-config.json` créé contient quatre valeurs à renseigner :

```json
{
  "tenant_id": "GUID-DU-TENANT",
  "client_id": "GUID-APPLICATION-ENTRA",
  "site_url": "https://VOTRE-TENANT.sharepoint.com/sites/VOTRE-SITE",
  "list_id": "GUID-DE-LA-LISTE"
}
```

Les libellés ci-dessus sont des emplacements à remplacer, pas des paramètres fonctionnels. Ne mettre ni mot de passe, ni secret client, ni jeton dans ce fichier. Le modèle n’est jamais écrasé si le fichier existe déjà.

## Configuration Microsoft 365 par l’équipe informatique

1. Enregistrer ou utiliser une application **client public, mono-tenant** autorisée par votre entreprise. Ajouter l’URI de redirection de type application mobile/bureau `http://localhost` pour la connexion interactive MSAL.
2. Configurer ses permissions **déléguées pour l’API SharePoint**, pas seulement pour Microsoft Graph. Le package demande `https://VOTRE-TENANT.sharepoint.com/.default` : les permissions correspondantes doivent être préconfigurées et consenties. Préférer `Sites.Selected` avec un accès explicitement accordé au site cible et adapté aux opérations autorisées ; le consentement seul ne donne pas accès au site.
3. Pour l’utilisation, prévoir les droits de lecture/écriture de dossiers ; pour le provisionnement (création de liste, colonnes, groupes et permissions), une application et un compte autorisés à administrer le site sont nécessaires. La commande de provisionnement ne crée pas l’application Entra et n’accorde pas elle-même son consentement.
4. Les personnes doivent appartenir **directement** aux groupes SharePoint `ALEX Analystes`, `ALEX Managers` ou `ALEX Deontologie`. Les groupes Entra imbriqués ne sont pas développés. Un administrateur de collection de sites dispose des trois rôles.
5. Autoriser les connexions du poste vers Microsoft Entra et le site SharePoint. Le package respecte le contrôle TLS de `requests` et sa configuration réseau habituelle ; ne pas désactiver TLS pour contourner un proxy d’entreprise.

La session Microsoft et son cache restent en mémoire dans Python, jusqu’à l’arrêt. Les jetons Microsoft ne sont pas transmis aux formulaires. Une nouvelle connexion est demandée au lancement ; une session expirée impose de relancer. Les refus de consentement ou de politique d’accès conditionnel doivent être résolus par la DSI, pas contournés.

## Lancer l’application

```text
alex check-config
alex serve
```

Une fenêtre Microsoft permet la connexion, puis ALEX s’ouvre dans le navigateur. Garder le terminal ouvert. Arrêter avec `Ctrl+C` après avoir enregistré les saisies.

Autres options :

```text
alex serve --config autre-config.json --port 8766
alex serve --no-browser
python -m alex_sharepoint --help
```

`--no-browser` empêche seulement l’ouverture automatique d’ALEX ; la connexion Microsoft reste interactive. Le terminal fournit un lien local contenant une clé de session après `#`. Ce lien ne doit pas être partagé. La clé reste en mémoire ; un rafraîchissement complet de la page nécessite de rouvrir ce lien. Pour recharger les données sans perdre la clé, utiliser « Actualiser les dossiers ».

Le service refuse les accès réseau distants, les origines étrangères, les requêtes sans clé de session et les hôtes inattendus. Le lancement sur `0.0.0.0` n’est volontairement pas proposé. Ne pas exposer ce service derrière un proxy : tous ses appels utilisent le compte Microsoft de la personne qui l’a démarré.

## Créer la liste en Python

Si la liste existe déjà, **ne pas la recréer** : renseigner simplement son GUID dans `list_id`. Les données enregistrées par la version SPFx restent lisibles. Aucune migration ni conversion de statut n’est déclenchée au lancement.

Sinon, laisser `list_id` vide dans une configuration de provisionnement et exécuter :

```text
alex provision --config alex-config.json --yes
```

Cette commande se connecte à Microsoft puis crée la liste **ALEX - Dossiers**, ses colonnes et vues et les trois groupes ALEX. Le GUID à reporter dans la configuration est affiché. Elle ne modifie pas le fichier de configuration. Elle n’insère aucune donnée fictive.

Le provisionnement active 500 versions et désactive les pièces jointes. Pour une nouvelle liste, il interrompt l’héritage des droits du site et attribue Contribution aux groupes ALEX ; le compte exécutant conserve normalement l’administration lors de cette interruption. Pour une liste déjà existante, il ne change pas ses attributions de rôles : l’administrateur doit les vérifier. Les colonnes existantes de mauvais type interrompent la commande. Une exécution interrompue peut laisser une création partielle : contrôler la liste et ses permissions avant de reprendre. Pas de rollback destructif.

Le module contient également le script PowerShell de la livraison précédente, à titre d’alternative administrateur. La commande Python est indépendante de PowerShell.

## Fonctionnement et périmètre conservé

- Brouillon, reprise, soumission, avis Déontologie, validation ou rejet avec motif.
- Une fiche rejetée revient chez l’analyste pour correction ; la resoumission conserve le dossier et réinitialise les avis courants. Les versions SharePoint conservent l’historique.
- Les avis et décisions utilisent l’identité du compte connecté ; les rôles sont contrôlés côté Python. Ils sont relus au lancement, donc relancer après un changement de groupe.
- Une fiche PPE nécessite un avis Déontologie enregistré avant la validation manager.
- Les modifications concurrentes sont contrôlées avec la version de lecture et l’ETag SharePoint, jamais avec `IF-MATCH: *` pour les données métier.
- Les enregistrements sont explicites. Aucun succès n’est annoncé sur simple clic ni à la fermeture de l’onglet. Un délai réseau après écriture nécessite une actualisation pour vérifier le résultat réel avant de réessayer.
- Les suppressions de brouillons sont logiques, sans suppression de ligne.
- Les vues détaillées, statistiques et exports du manager restent ceux de la version précédente.
- Le scénario décès multi-bénéficiaires reste à recetter particulièrement en cas d’interruption : plusieurs éléments SharePoint sont écrits, sans transaction globale entre les fiches et le brouillon.

La liste comprend les colonnes de suivi `AlexKey`, `AlexType`, `AlexStatus`, `AlexPriority`, `AlexClient`, `AlexAnalyst` et les douze colonnes multilignes de contenu. Le JSON Python est échappé en ASCII pour éviter les problèmes de caractères Unicode découpés entre colonnes. La limite est de 696 000 caractères de JSON encodé ; elle peut donc être atteinte plus tôt qu’avec la version JavaScript sur des textes contenant beaucoup de caractères non ASCII. Les données trop volumineuses ne sont pas tronquées.

## Limites à connaître

Cette livraison vise un **usage local mono-utilisateur et une recette interne**, pas une mise en production réglementaire. Plusieurs personnes peuvent installer le package sur leur propre poste et travailler sur la même liste ; chaque instance utilise sa propre connexion Microsoft.

Les groupes ALEX disposent encore de Contribution sur la liste. Les contrôles Python protègent les actions passant par cette application, mais n’interdisent pas à un utilisateur habilité une écriture directe dans SharePoint. Une séparation des tâches opposable exige une architecture serveur approuvée et une suppression des écritures directes. La validation n’est pas une signature électronique certifiée.

Aucune notification email/Teams, aucun mode hors ligne, aucun stockage de pièces jointes et aucun hébergement Python dans SharePoint ne sont ajoutés. Les données ne sont pas copiées dans une base locale. Le cache de dossiers est en mémoire uniquement. Le chargement est plafonné à 10 000 dossiers ; un périmètre plus large nécessite une pagination fonctionnelle côté serveur.

Les paramètres actuels acceptent seulement les tenants SharePoint Online commerciaux `.sharepoint.com`. SharePoint Server sur site et clouds souverains ne sont pas pris en charge par cette version.

## Vérification et développement

Les tests locaux vérifient les transitions, les rôles serveur, les conflits, les données Unicode, le transport HTTP et le contenu du package. Ils utilisent des réponses SharePoint simulées. **La connexion réelle, la création de liste et la recette dans votre tenant n’ont pas pu être effectuées.** Les règles métier des maquettes et les droits réels sont à valider en recette avec des données fictives.

Les sources sont dans `src/alex_sharepoint/`. Pour installer les sources :

```text
python -m pip install -e .
python -m unittest discover -s tests -v
```

Pour reconstruire les distributions :

```text
python -m pip install build
python -m build
```

La wheel contient les deux HTML adaptés et les fichiers de configuration de la liste. Aucun Node.js, npm, SPFx ni catalogue d’applications SharePoint n’est requis pour exécuter cette version.

Références : [connexion interactive MSAL Python](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens), [permissions SharePoint déléguées Sites.Selected](https://devblogs.microsoft.com/microsoft365dev/sharepoint-now-supports-delegated-sites-selected-authentication/), [ETag et opérations REST SharePoint](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/working-with-lists-and-list-items-with-rest).
