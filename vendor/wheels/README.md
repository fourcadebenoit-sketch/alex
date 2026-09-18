# Dépendances vendorisées

Wheels pré-téléchargées pour installer `alex-sharepoint` sans accès à pypi.org (poste derrière un proxy d'entreprise sans configuration possible).

Cible : **Windows 64 bits, Python 3.14** (résolution complète de `msal>=1.31,<2` et `requests>=2.32.4,<3`, y compris les paquets compilés `cryptography` et `cffi`).

| Paquet | Version | Plateforme |
|---|---|---|
| msal | 1.39.0 | universelle |
| requests | 2.34.2 | universelle |
| PyJWT | 2.14.0 | universelle |
| cryptography | 50.0.1 | win_amd64 (wheel `abi3`, compatible Python ≥3.11) |
| cffi | 2.1.1 | win_amd64, cp314 |
| pycparser | 3.0 | universelle |
| charset_normalizer | 3.5.1 | win_amd64, cp314 |
| idna | 3.20 | universelle |
| urllib3 | 2.8.0 | universelle |
| certifi | 2026.7.22 | universelle |

## Régénérer pour une autre plateforme ou version de Python

Depuis un poste ayant accès à pypi.org (ou via ce sandbox) :

```text
pip download --dest vendor/wheels \
  --platform win_amd64 \
  --python-version 3.14 \
  --implementation cp \
  --abi cp314 \
  --only-binary=:all: \
  "msal>=1.31,<2" "requests>=2.32.4,<3"
```

Adapter `--platform` (`win_amd64`, `manylinux_2_28_x86_64`, `macosx_11_0_arm64`, …), `--python-version` et `--abi` à la cible réelle, puis remplacer le contenu de ce dossier.
