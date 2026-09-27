# Sécurité

La posture de sécurité de `rag-agent-chat` : ce que l'API expose, les défenses en place, ce qui n'est pas protégé et ce qui est enregistré. Pour qui déploie l'agent au-delà d'un poste local ou audite ce qu'il conserve.

La sécurité des stores relève de [rag-ingestion-pipeline](https://github.com/floSa/rag-ingestion-pipeline), celle du serveur d'inférence de [llm-service](https://github.com/floSa/llm-service).

## Ce que l'API expose

| Surface | État par défaut | Réglage |
|---|---|---|
| Authentification | Désactivée | `API_KEY` |
| CORS | Origines déclarées (`http://localhost:8506,http://localhost:8501`), méthodes `GET` et `POST` | `CORS_ORIGINS` |
| Proxy média | Borné aux objets cités par le graphe | `RESTRICT_MEDIA_TO_GRAPH` |
| Chiffrement | Aucun, HTTP en clair | — |
| Limitation de débit | Aucune | — |
| Capture d'usage | Active, sur le disque local | `USAGE_CAPTURE` |

Le déploiement par défaut convient à un poste local derrière un pare-feu, pas à une exposition. Avant d'exposer l'API : poser `API_KEY`, restreindre `CORS_ORIGINS` aux origines réelles, placer un reverse proxy TLS devant.

## Les défenses

### Clé d'API

Avec `API_KEY` renseignée, toutes les routes exigent l'en-tête `X-API-Key`, sauf `/health`, qui reste ouverte pour les sondes. La comparaison passe par `secrets.compare_digest`. Vide, la dépendance ne fait rien.

**Limite : le frontend Streamlit n'envoie pas d'en-tête `X-API-Key`** (`src/frontend/app.py`, 0 occurrence). Poser `API_KEY` coupe donc l'interface de chat, qui reçoit 401 sur chaque appel. En l'état, la clé protège un accès direct à l'API, pas un déploiement avec l'interface.

### CORS

Les origines sont déclarées, jamais `*` : une page web quelconque ouverte dans le navigateur de l'utilisateur ne peut pas interroger l'API.

### Proxy média

`GET /media/{chemin}` applique deux contrôles, dans cet ordre, et un test vérifie l'ordre :

1. **anti-traversée** : le chemin est validé contre un motif, `..` est refusé ;
2. **référencement** : l'objet doit être cité par un nœud `Picture` ou `Table` du graphe. Un objet inconnu déclenche une relecture unique de la liste, pour qu'un document fraîchement ingéré n'exige pas de redémarrage.

### Injection nGQL

Le pilote NebulaGraph ne propose pas de requêtes paramétrées : les identifiants sont interpolés.

- **Identifiants d'éléments** : hash `^[a-f0-9]{10}$`, validé strictement dès le schéma Pydantic (`ElementId`). C'est le seul format qu'un appelant fournit.
- **Identifiants de documents** : dérivés d'un chemin, jamais fournis par l'utilisateur, découverts en remontant le graphe. Ils sont échappés, antislash en premier ; les caractères de contrôle sont refusés.

## Ce qui n'est pas protégé

- **Injection de prompt.** Un document ingéré peut contenir des instructions que le modèle suivra. Le corpus est réputé de confiance.
- **Données personnelles.** Aucune détection ni anonymisation, ni dans le corpus ni dans les questions enregistrées.
- **Épuisement de ressources.** Rien ne limite le débit ; une boucle sur `/answer` saturerait le serveur d'inférence partagé.
- **Chiffrement au repos.** Les fichiers de `rag_agent_state` sont lisibles par qui accède au volume.

## Ce qui est enregistré

| | |
|---|---|
| Quoi | La question, sa réécriture et sa traduction, le classement des sources, celles retenues ou décochées, la réponse, les citations, les latences, l'appréciation |
| Où | `/app/data/usage.sqlite`, volume `rag_agent_state`, sur l'hôte |
| Combien de temps | Indéfiniment, aucune purge |
| Sortie réseau | Aucune |
| Désactiver | `USAGE_CAPTURE=false` (ou `USAGE_DB_PATH=` vide) : le fichier n'est pas créé |
| Surveiller | `GET /health`, bloc `usage` : nombre de lignes et poids du fichier |

Le drapeau est à vrai par défaut : les premières semaines d'usage sont les plus instructives et ne se rattrapent pas. L'exposition n'est pas nouvelle : le checkpointer LangGraph persiste déjà l'état complet d'une session (question, historique, contextes, réponse, en clair) dans `/app/data/checkpoints.sqlite`, jusqu'à sa purge, `SESSION_TTL_SECONDS` (une heure par défaut) après sa création. `GET /health` publie `sessions.purged` et `sessions.failures` pour vérifier que la purge aboutit. Historique du défaut de purge corrigé : §1.20 du [registre](axes_amelioration.md).

Schéma et requêtes : [capture_usage.md](capture_usage.md).

## Secrets

- `.env` est ignoré par git ; `.env.example` documente les clés sans valeurs secrètes.
- Avant de publier : `git ls-files | grep -c '^\.env$'` doit rendre `0`.
- Pour le stockage objet, l'agent reçoit le jeu de clés en lecture seule que publie le pipeline, jamais ses clés d'administration.
- Ce dépôt est public : aucune valeur du `.env`, aucun secret et aucune adresse interne dans un document, un commit ou un rapport.

## Dépendances

```bash
make audit          # pip-audit sur requirements.txt
```

`make audit` sort sur le réseau et ne tourne pas en intégration continue. Dernier état écrit dans ce dépôt, au 3 août 2026 : 1 vulnérabilité connue, dans `chromadb` (PYSEC-2026-311), sans version corrigée publiée à cette date. Cet état n'a pas été remesuré depuis.

Une montée de version de `sentence-transformers` ou de `chromadb` touche la qualité de la recherche, pas seulement la sécurité : vérifier avant de monter que les vecteurs produits sont identiques, puis rejouer une campagne. Un épinglage doit porter une raison vérifiable, vérifiée avant d'être écrite.
