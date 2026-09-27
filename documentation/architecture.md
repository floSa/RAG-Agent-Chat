# Architecture du système

Le système vu de haut : ses services, ce qu'il écrit, comment il tient face aux services voisins, et les décisions qui lui donnent sa forme. Pour qui reprend le projet et doit savoir où chaque chose se passe.

Les schémas (architecture, chemin d'une question, déploiement) sont dans le [README](../README.md#architecture). Le détail de l'agent (nœuds, état, prompts, réglages) est dans [agent_architecture.md](agent_architecture.md).

## Les services

| Service | Conteneur | Build | Port hôte → conteneur | Réseaux | Rôle |
|---|---|---|---|---|---|
| `agent-api` | `rag-agent-api` | `Dockerfile.agent` (`python:3.12-slim`, torch `cu130`) | 8011 → 8000 | `rag_network`, `llm-net`, `internal` | API FastAPI, agent LangGraph, embedder et reranker sur GPU |
| `frontend` | `rag-frontend` | `Dockerfile.frontend` | 8506 → 8501 | `internal` | Interface Streamlit ; démarre quand `agent-api` est `healthy` |

Tout le reste est externe à ce dépôt :

| Dépendance | Propriétaire | Réseau | Adresse vue de l'agent |
|---|---|---|---|
| ChromaDB, NebulaGraph, stockage objet S3 | `rag-ingestion-pipeline` | `rag_network`, externe | `chromadb:8000`, `graphd:9669`, `seaweedfs:8333` |
| Serveur d'inférence vLLM | `llm-service`, équipe voisine | `llm-net`, externe | `vllm-central:8000` |

Volumes : `rag_hf_cache` (poids de l'embedder et du cross-encoder, téléchargés au premier démarrage) et `rag_agent_state` (sessions et capture d'usage, deux fichiers SQLite). Le dossier `prompts/` est monté en lecture seule depuis le clone.

## Deux entrées dans le même graphe

L'agent est une machine à états LangGraph, compilée deux fois :

| Compilation | Interruption | Checkpointer | Routes |
|---|---|---|---|
| `agent_graph` | avant `await_source_selection` | SQLite | `/chat/start` puis `/chat/resume` |
| `answer_graph` | aucune | aucun | `/answer` |

Le flux interactif attend un humain et ne se rejoue pas en lot ; `answer_graph` existe pour que les campagnes d'évaluation puissent mesurer le système. `/chat/simple` contourne le graphe : il génère à partir de sources déjà choisies, sans recherche ni boucle agentique.

## Ce que le service écrit

### La capture d'usage

`src/agent/usage.py` enregistre la question, le classement proposé, les sources retenues ou décochées, la réponse, les latences et l'appréciation. Le branchement appartient à l'API, pas au graphe : `/chat/start` sait ce qui a été proposé, `/chat/resume` ce qui a été retenu, et aucun nœud ne voit les deux.

```
/chat/start  → graphe jusqu'à rerank → record_start          (1 ligne + N sources)
/chat/resume → graphe jusqu'à END → dernier événement SSE → record_completion
/answer      → graphe complet → record_start + record_completion  (endpoint = 'answer')
/feedback    → record_feedback
```

L'écriture de `/chat/resume` suit le dernier événement SSE ; aucun échec ne remonte ; le mode WAL est posé au démarrage. Schéma, vues et requêtes : [capture_usage.md](capture_usage.md).

### Purge durable des sessions

Le checkpointer ne purge rien de lui-même. L'API garantit trois choses :

- une session en attente de sélection survit au redémarrage de l'API, donc aucune purge n'a lieu pour cette seule raison ;
- une session périmée finit par disparaître du disque, même créée avant le dernier redémarrage : le registre de la purge, table `sessions_agent`, vit dans `checkpoints.sqlite`, et les sessions présentes sans registre y sont adoptées au démarrage ;
- le journal et `GET /health` (`sessions.purged`, `sessions.failures`) comptent les suppressions abouties, pas les candidates.

Deux bornes la déclenchent, `SESSION_TTL_SECONDS` (3600) et `MAX_LIVE_SESSIONS` (200), au démarrage puis à chaque `POST /chat/start`. La session en cours de création est épargnée. L'âge se mesure à l'horloge murale, la seule qui survive à un redémarrage.

Le registre n'est pas adossé à la capture d'usage, qui est désactivable : la purge ne dépend d'aucun autre réglage.

## Face aux services voisins

- **Un corpus qui bouge.** L'ingestion écrit pendant que l'agent tourne. La recherche dense suit ; l'index BM25 en mémoire est reconstruit par `POST /reindex`, que le pipeline appelle, ou par un filet de comptage ([stores.md](stores.md#lindex-bm25-vit-dans-le-processus-de-lagent)). Une reconstruction déclenchée par le filet tourne en tâche de fond, l'ancien index servant pendant ce temps ; une seule construction a lieu sous N requêtes concurrentes.
- **Un store qui redémarre.** Les clients sont mémorisés et savent se rouvrir une fois ; une purge du graphe, qui rend la session NebulaGraph aveugle aux tags, est traitée de la même façon (§4.80 du [registre](axes_amelioration.md)).
- **Un serveur d'inférence partagé.** L'agent ne l'administre pas. Il relève et publie ce qui est servi ([moteur_llm.md](moteur_llm.md)), borne ses prompts côté client ([llm.md](llm.md)), et partage la carte avec lui ([gpu_cuda.md](gpu_cuda.md)).
- **Un `/health` sous délai.** Les sondes partent en parallèle sous un plafond de 3 s, pour tenir dans les 5 s du healthcheck Docker ; sinon le frontend, qui attend `agent-api` en `service_healthy`, ne démarrerait jamais.

## La partition du temps

`src/agent/chronometrie.py` tient une partition du temps de réponse par étage, publiée par `/answer` : la somme des étages et du résidu égale le temps mural, le résidu peut être négatif (trace d'un double comptage), un nom d'étage inconnu lève `KeyError`, et les étages se cumulent sur les tours de la boucle agentique. `retrieval_ms` est un agrégat, pas un étage. Liste des étages : [rag_evaluation_strategy.md](rag_evaluation_strategy.md#la-décomposition-du-temps). Le post-traitement des citations n'a pas d'étage propre et tombe dans le résidu.

## Les décisions d'architecture

- **Reconstruction par le graphe plutôt que chunks isolés** (*parent-document retrieval*) : le modèle reçoit la section, ses voisines et ses illustrations, chaque élément suivi de son marqueur `[src:ID]`.
- **Le graphe porte la structure, l'index porte le texte** : l'ingestion tronque le texte des nœuds à 2000 caractères, l'agent relit le texte intégral dans ChromaDB.
- **Fusion par RRF, pas par somme de scores** : une distance cosinus et un score BM25 ne vivent pas sur la même échelle ; RRF n'additionne que des rangs.
- **Modèles multilingues des deux côtés** : le corpus mêle français et anglais, et un cross-encoder anglais rendait des scores plats sur une question française.
- **Un seul moteur d'inférence, en dialecte OpenAI**, par un site unique (`src/agent/dialecte_llm.py`) : un champ d'un autre dialecte est accepté puis ignoré par le serveur, sans erreur.
- **`LLM_NUM_CTX` borne le client** et n'est pas envoyé : la fenêtre du serveur est fixée à son lancement, et le serveur refuse en HTTP 400 une requête qui la dépasse.
- **Le budget se calcule sur tout le prompt** (système, gabarit, historique, outil, sources), et l'estimation est confrontée au décompte du serveur à chaque génération.
- **Appel d'outil natif, repli dans la prose** : `search_vectors` est déclaré comme outil ; le repérage d'un appel écrit dans le texte a un seul site, `src/agent/repli_outil.py`.
- **Raisonnement désactivé par requête** (`LLM_THINKING=false` dans `chat_template_kwargs`), jamais côté serveur : le serveur est partagé avec d'autres équipes.
- **Proxy `/media`** : le navigateur ne résout pas les adresses internes du stockage objet ; l'API sert les objets, chemin validé et borné au graphe.
- **Sessions sur disque** (SQLite) : une session en attente de sélection survit au redémarrage.
- **Les compteurs publiés comptent ce qui a abouti**, jamais ce qui a été tenté.
- **VIDs échappés, pas filtrés** : les identifiants de documents dérivent d'un chemin et ne viennent jamais de l'utilisateur ; la validation stricte reste sur le seul format qu'un appelant fournit.
- **Routes synchrones en `def`** : le calcul torch tourne dans le threadpool de FastAPI, la boucle d'événements reste libre.
- **Embedder et cross-encoder sur GPU**, décision mesurée le 11 septembre 2026 ([gpu_cuda.md](gpu_cuda.md), §7). Trois conditions décident du périphérique, et `/health` les publie toutes.
- **Capture d'usage active par défaut** : les premières semaines d'usage ne se rattrapent pas ([SECURITY.md](SECURITY.md)).

## Le contrat avec l'ingestion

Ce que l'agent lit dans chaque store, et ce qui casse sinon : [stores.md](stores.md). Le même contrat écrit à l'intention du pipeline : [pour_le_pipeline_ingestion.md](pour_le_pipeline_ingestion.md). Le plan de conception d'avant le projet, historique : [llm_integration_plan.md](llm_integration_plan.md).
