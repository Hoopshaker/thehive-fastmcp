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
  - `_request` (et ses raccourcis `_get` / `_post` / `_patch`) : une réponse non 2xx lève `TheHiveHTTPError` (sous-classe de `RuntimeError`, avec `status_code`) dont le message est `<MÉTHODE> <chemin> -> HTTP <code> : <corps tronqué à 500 caractères>` ; une erreur réseau lève `RuntimeError`.
  - `create_case_from_alert` vérifie avant d'écrire (alerte non rattachée, modèle existant via `listCaseTemplate`), utilise `POST /api/v1/alert/{id}/case` et se replie sur la route v0 `POST /api/alert/{id}/createCase` si la route v1 renvoie 404/405. `merge_alerts_into_case` résout d'abord le case (numéro → `~id`) puis traite chaque alerte indépendamment.
  - `query(ops, limit)` : POST sur `/api/v1/query` avec la **Query DSL** de TheHive (liste d'opérations `_name`), ajoute la pagination `page` si absente.
  - `parse_date_to_ms` : accepte timestamp ms, ISO 8601 (`Z` ou offset) ou `YYYY-MM-DD` (UTC par défaut).
- [src/thehive_mcp/server.py](src/thehive_mcp/server.py) — instance `FastMCP` et fonctions `@mcp.tool()` qui délèguent au client. Le client est instancié paresseusement (`get_client()`) pour que le serveur démarre même sans variables d'environnement.

Les fonctions de recherche (`search_cases`, `search_alerts`, `get_case_observables`, `get_case_tasks`) construisent chacune la même chaîne d'opérations : opération source (`listCase`, `listAlert`, `getCase` + `observables`/`tasks`) → filtres (`_like` titre, `_eq` severity/status/tags, `_gte`/`_lte` sur `_createdAt`) → `query` JSON libre → `sort`. Ce bloc est **dupliqué quatre fois** : toute modification de la logique de filtre, de `query` ou de `sort` doit être répercutée partout (ou factorisée).

Paramètre `query` libre : chaîne JSON qui peut être un filtre nu (`{"_eq": ...}`, enveloppé automatiquement dans `{"_name": "filter", ...}`), une opération nommée, ou une liste d'opérations. JSON invalide → `ValueError`.

## Ajouter ou modifier un outil

1. Méthode dans `TheHiveClient` (noms de champs API en camelCase : `sourceRef`, `dataType`…).
2. Wrapper `@mcp.tool()` dans `server.py` avec une **docstring complète** (`Args:` détaillés) : c'est la description vue par le modèle, elle doit indiquer les valeurs admises et les échelles.
3. Test dans `tests/test_thehive_client.py` vérifiant le chemin et le payload.
4. Mettre à jour la section « Outils exposés » du [README.md](README.md).

Pour les mises à jour partielles (`update_*`), n'envoyer que les champs non `None` dans le PATCH.

Tests : la classe `FakeClient` de `tests/test_thehive_client.py` remplace `_request` par une table de routes `(MÉTHODE, chemin)` et enregistre chaque appel. L'utiliser pour tout nouvel outil.

## Garde-fous (choix de conception, à préserver)

Le serveur est utilisé par des agents de l'équipe Sécurité. Par conception, un agent ne doit pas pouvoir :

- clôturer un case ou une alerte : `server.allow_close()` (variable `THEHIVE_ALLOW_CLOSE`, `false` par défaut) bloque `status`/`summary` dans `update_case`, et `stage=Closed` ou un statut de `ALERT_FINAL_STATUSES` dans `update_alert` ;
- supprimer quoi que ce soit (aucun outil `delete_*`, vérifié par un test) ;
- réassigner un case (`update_case` n'expose pas `assignee`).

Ne pas lever ces garde-fous sans demande explicite. Les outils de promotion et de fusion (`create_case_from_alert`, `merge_alerts_into_case`, `add_case_comment`) et les refus de garde-fou renvoient `{"error": str(e)}` au lieu de lever une exception, pour que l'agent lise la cause.

## Conventions TheHive

- Sévérité : 1 Low, 2 Medium, 3 High, 4 Critical (défaut 2).
- TLP : 0 White, 1 Green, 2 Amber, 3 Amber+Strict, 4 Red. PAP : 0 White à 3 Red (défaut 2 pour les deux).
- Identifiants d'objets préfixés par `~` (ex. `~1234`) ; les cases acceptent aussi leur numéro.
- Statuts d'alerte : `New`, `Imported`, `Ignored`. Statuts de case : `Open`, `Resolved`, `Closed`.
- Tri : nom de champ avec `-` pour l'ordre décroissant (`-_createdAt`, `-_updatedAt`).

## Configuration

Variables d'environnement lues par `TheHiveClient` : `THEHIVE_URL` et `THEHIVE_API_KEY` (obligatoires), `THEHIVE_VERIFY_SSL` (`false`/`0`/`no` pour désactiver), `THEHIVE_ORG` (ajoute l'en-tête `X-Organisation`), `THEHIVE_ALLOW_CLOSE` (voir Garde-fous).

- Ne jamais écrire de clé API, d'URL d'instance réelle ou de données d'alerte/case réelles dans le code, les tests ou la documentation : utiliser des valeurs factices (`http://dummy`, `dummy_key`). `.env` est ignoré par git.

## Points d'attention

- **stdio** : rien ne doit être écrit sur stdout hors du protocole MCP (pas de `print`). Utiliser le logger `thehive_mcp` (stderr).
- Les appels `requests` n'ont pas de `timeout`.
- Un objet `requests.Response` en 4xx/5xx est évalué à faux (`Response.__bool__` renvoie `ok`) : ne jamais écrire `if response` pour tester sa présence, sinon le corps de l'erreur TheHive est perdu (couvert par `test_http_error_body_is_surfaced`).
- Le `Dockerfile` installe les dépendances depuis `pyproject.toml` (pas depuis `uv.lock`) et lance `python -m thehive_mcp.server` avec `PYTHONPATH=/app/src`.

## CI / livraison

[.github/workflows/docker-publish.yml](.github/workflows/docker-publish.yml) construit et publie l'image sur GHCR à chaque push sur `main`/`master` et sur les tags `v*`. Aucun test n'est exécuté en CI : lancer les tests localement avant de pousser.

Messages de commit au format Conventional Commits (`feat:`, `fix:`, `ci:`…).
