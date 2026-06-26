# TheHive MCP Server (FastMCP)

Ce dépôt contient un serveur MCP (Model Context Protocol) générique et performant pour **TheHive** (plateforme d'orchestration et de réponse aux incidents de sécurité).

Il permet à des agents IA ou assistants de sécurité (comme Claude Desktop ou d'autres passerelles MCP) de manipuler et de requêter de manière sécurisée les **Cases**, **Alerts**, **Observables** (IoCs) et **Tasks** dans TheHive.

## ⚙️ Configuration

Le serveur s'appuie exclusivement sur des variables d'environnement pour sa configuration :

| Variable | Description | Obligatoire | Valeur par défaut |
| :--- | :--- | :--- | :--- |
| `THEHIVE_URL` | URL de base de votre instance TheHive (ex: `https://thehive.votre-domaine.com`). | **Oui** | - |
| `THEHIVE_API_KEY` | Clé API de l'utilisateur (Bearer Token). | **Oui** | - |
| `THEHIVE_VERIFY_SSL` | Activer ou désactiver la vérification du certificat SSL. Utile en environnement auto-hébergé. | Non | `true` |
| `THEHIVE_ORG` | Nom de l'organisation cible (ajoute le header `X-Organisation`). | Non | - |

---

## 🛠️ Utilisation avec Docker

Ce serveur MCP est publié automatiquement sur **GitHub Container Registry (GHCR)**. Vous pouvez l'utiliser directement sans cloner le code source ou construire l'image vous-même : Docker s'occupe de tout télécharger de manière transparente au premier lancement.

### 1. Exécution directe en ligne de commande

Comme le protocole MCP fonctionne via les flux d'entrée/sortie standard (`stdio`), vous devez exécuter le conteneur en mode interactif (`-i`) et sans allouer de pseudo-TTY (`-t` n'est pas utilisé pour éviter de polluer les flux avec des caractères d'échappement ANSI) :

```bash
docker run -i --rm \
  -e THEHIVE_URL="https://thehive.votre-domaine.com" \
  -e THEHIVE_API_KEY="VOTRE_CLE_API" \
  -e THEHIVE_VERIFY_SSL="false" \
  ghcr.io/hoopshaker/thehive-fastmcp:latest
```

### 2. Configuration pour les clients MCP (Gemini / Claude Desktop)

Pour connecter ce serveur automatiquement à votre client MCP (comme l'extension Gemini MCP ou Claude Desktop), ajoutez cette configuration à votre fichier de configuration (`gemini-config.json` ou `claude_desktop_config.json`) :

```json
{
  "mcpServers": {
    "thehive": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e", "THEHIVE_URL=https://thehive.votre-domaine.com",
        "-e", "THEHIVE_API_KEY=VOTRE_CLE_API",
        "-e", "THEHIVE_VERIFY_SSL=false",
        "ghcr.io/hoopshaker/thehive-fastmcp:latest"
      ]
    }
  }
}
```

---

### 🔨 Build local (Optionnel / Développement)

Si vous souhaitez modifier le code ou construire l'image Docker vous-même localement :

1. Depuis la racine du projet, construisez l'image :
   ```bash
   docker build -t thehive-fastmcp .
   ```

2. Exécutez-la en remplaçant la référence GHCR par votre tag local :
   ```bash
   docker run -i --rm \
     -e THEHIVE_URL="https://thehive.votre-domaine.com" \
     -e THEHIVE_API_KEY="VOTRE_CLE_API" \
     thehive-fastmcp
   ```

---

## 🔧 Outils Exposés (Tools)

Une fois connecté, le serveur MCP expose les outils suivants :

### 📁 Cases (Dossiers d'incident)
*   `get_case(id_or_name)` : Récupère les détails complets d'un dossier par ID (ex: `~1234`) ou numéro.
*   `create_case(title, description, severity, tags, tlp, pap, flag)` : Crée un nouveau dossier d'incident.
*   `search_cases(title, severity, tags, status, limit)` : Recherche des dossiers selon plusieurs critères.

### 🚨 Alerts (Alertes de sécurité)
*   `get_alert(alert_id)` : Récupère les détails complets d'une alerte.
*   `create_alert(type_name, source, source_ref, title, description, severity, tags, tlp, pap)` : Crée une alerte provenant d'un SIEM/EDR.
*   `search_alerts(title, severity, tags, status, limit)` : Recherche des alertes.

### 🔍 Observables (IoCs)
*   `create_observable(case_id, data_type, data, message, tags, tlp, pap, ioc)` : Ajoute un observable (ex: IP, domaine, hash) à un dossier.
*   `get_case_observables(case_id, limit)` : Liste tous les observables liés à un dossier.

### 📋 Tasks & Logs (Tâches d'investigation)
*   `create_task(case_id, title, description, group, assignee)` : Ajoute une tâche à accomplir dans un dossier d'incident.
*   `get_case_tasks(case_id, limit)` : Liste les tâches d'un dossier.
*   `add_task_log(task_id, message)` : Ajoute une note de progression ou un compte-rendu textuel à une tâche.

---

## 💻 Développement Local (sans Docker)

Si vous souhaitez lancer ou déboguer le serveur localement en utilisant `uv` :

1. Installez `uv` si ce n'est pas déjà fait.
2. Créez un environnement virtuel et installez les dépendances :
   ```bash
   uv sync
   ```
3. Exportez vos variables d'environnement :
   ```bash
   export THEHIVE_URL="https://..."
   export THEHIVE_API_KEY="..."
   export THEHIVE_VERIFY_SSL="false"
   ```
4. Lancez le serveur MCP :
   ```bash
   uv run python -m thehive_mcp.server
   ```

---

## 🧪 Test Manuel du Protocole JSON-RPC (Handshake)

Puisque le protocole MCP communique via des messages **JSON-RPC 2.0** sur l'entrée standard (`stdin`), vous pouvez tester manuellement le serveur en saisissant directement les messages d'initialisation du handshake MCP dans votre terminal.

### Étape 1 : Lancer l'initialisation
Une fois le serveur démarré, saisissez cette requête JSON-RPC d'initialisation et faites **Entrée** :
```json
{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0.0"}}}
```
*Le serveur va répondre avec un bloc JSON contenant ses métadonnées et ses capacités.*

### Étape 2 : Confirmer l'initialisation (Notification)
Envoyez ensuite cette notification (sans `id`) pour finaliser le handshake :
```json
{"jsonrpc": "2.0", "method": "notifications/initialized"}
```
*Le serveur est maintenant initialisé et prêt à recevoir des commandes.*

### Étape 3 : Lister les outils disponibles
Vous pouvez désormais requêter la liste des outils :
```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
```
*Le serveur répondra avec la liste complète des outils TheHive (`get_case`, `create_case`, etc.) décrits au format JSON.*
