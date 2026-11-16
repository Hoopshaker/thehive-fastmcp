# CLAUDE.md

Serveur MCP (Model Context Protocol) en Python pour une instance **TheHive** auto-hébergée (API v1). Il expose aux agents IA des outils sur les Cases, Alerts, Observables et Tasks. Transport : **stdio** uniquement (FastMCP du SDK officiel `mcp`).

## Commandes

```bash
uv sync                                               # installer les dépendances (.venv)
uv run python -m unittest tests/test_thehive_client.py   # lancer les tests (depuis la racine)
uv run python -m thehive_mcp.server                   # lancer le serveur (stdio, attend du JSON-RPC)
docker build -t thehive-fastmcp .                     # build de l'image locale
```

- Les tests importent `src.thehive_mcp...` : ils doivent être lancés **depuis la racine du dépôt**. `unittest discover -s tests` échoue (pas de `tests/__init__.py`). Pas de pytest, pas de linter ni de formateur configurés.
- Les tests n'appellent jamais TheHive : ils remplacent `client.query`, `client._post` ou `client._patch` par une fonction factice et vérifient le chemin, le payload ou la liste d'opérations générée. Garder ce modèle (aucun appel réseau dans les tests).

## Architecture

Deux fichiers portent tout le code :

- [src/thehive_mcp/thehive_client.py](src/thehive_mcp/thehive_client.py) — `TheHiveClient` : client HTTP `requests` vers `/api/v1/...`.
  - `_get` / `_post` / `_patch` : wrappers qui transforment toute erreur en `RuntimeError` (message renvoyé à l'agent).
  - `query(ops, limit)` : POST sur `/api/v1/query` avec la **Query DSL** de TheHive (liste d'opérations `_name`), ajoute la pagination `page` si absente.
  - `parse_date_to_ms` : accepte timestamp ms, ISO 8601 (`Z` ou offset) ou `YYYY-MM-DD` (UTC par défaut).
- [src/thehive_mcp/server.py](src/thehive_mcp/server.py) — instance `FastMCP` et fonctions `@mcp.tool()` qui délèguent au client. Le client est instancié paresseusement (`get_client()`) pour que le serveur démarre même sans variables d'environnement.

Les fonctions de recherche (`search_cases`, `search_alerts`, `get_case_observables`, `get_case_tasks`) construisent chacune la même chaîne d'opérations : opération source (`listCase`, `listAlert`, `getCase` + `observables`/`tasks`) → filtres (`_like` titre, `_eq` severity/status/tags, `_gte`/`_lte` sur `_createdAt`) → `query` JSON libre → `sort`. Ce bloc est **dupliqué quatre fois** : toute modification de la logique de filtre, de `query` ou de `sort` doit être répercutée partout (ou factorisée).

Paramètre `query` libre : chaîne JSON qui peut être un filtre nu (`{"_eq": ...}`, enveloppé automatiquement dans `{"_name": "filter", ...}`), une opération nommée, ou une liste d'opérations. JSON invalide → `ValueError`.

## Ajouter ou modifier un outil

1. Méthode dans `TheHiveClient` (noms de champs API en camelCase : `sourceRef`, `dataType`…).
2. Wrapper `@mcp.tool()` dans `server.py` avec une **docstring complète** (`Args:` détaillés) : c'est la description vue par le modèle, elle doit indiquer les valeurs admises et les échelles.
3. Test dans `tests/test_thehive_client.py` vérifiant le chemin et le payload.
4. Mettre à jour la section « Outils exposés » du [README.md](README.md) (actuellement en retard : `update_case`, `update_alert` et `add_alert_comment` n'y figurent pas).

Pour les mises à jour partielles (`update_*`), n'envoyer que les champs non `None` dans le PATCH.

## Conventions TheHive

- Sévérité : 1 Low, 2 Medium, 3 High, 4 Critical (défaut 2).
- TLP : 0 White, 1 Green, 2 Amber, 3 Amber+Strict, 4 Red. PAP : 0 White à 3 Red (défaut 2 pour les deux).
- Identifiants d'objets préfixés par `~` (ex. `~1234`) ; les cases acceptent aussi leur numéro.
- Statuts d'alerte : `New`, `Imported`, `Ignored`. Statuts de case : `Open`, `Resolved`, `Closed`.
- Tri : nom de champ avec `-` pour l'ordre décroissant (`-_createdAt`, `-_updatedAt`).

## Configuration

Variables d'environnement lues par `TheHiveClient` : `THEHIVE_URL` et `THEHIVE_API_KEY` (obligatoires), `THEHIVE_VERIFY_SSL` (`false`/`0`/`no` pour désactiver), `THEHIVE_ORG` (ajoute l'en-tête `X-Organisation`).

- Ne jamais écrire de clé API, d'URL d'instance réelle ou de données d'alerte/case réelles dans le code, les tests ou la documentation : utiliser des valeurs factices (`http://dummy`, `dummy_key`). `.env` est ignoré par git.

## Points d'attention

- **stdio** : rien ne doit être écrit sur stdout hors du protocole MCP (pas de `print`). Utiliser le logger `thehive_mcp` (stderr).
- Les appels `requests` n'ont pas de `timeout`.
- Un objet `requests.Response` en 4xx/5xx est évalué à faux (`Response.__bool__` renvoie `ok`) : toujours tester `e.response is not None`, jamais `if e.response`, sinon le corps de l'erreur TheHive est perdu (couvert par `test_http_error_body_is_surfaced`).
- Le `Dockerfile` installe les dépendances depuis `pyproject.toml` (pas depuis `uv.lock`) et lance `python -m thehive_mcp.server` avec `PYTHONPATH=/app/src`.

## CI / livraison

[.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml) construit et publie l'image sur GHCR à chaque push sur `main`/`master` et sur les tags `v*`. Aucun test n'est exécuté en CI : lancer les tests localement avant de pousser.

Messages de commit au format Conventional Commits (`feat:`, `fix:`, `ci:`…).
