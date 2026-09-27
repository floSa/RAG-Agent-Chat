# La capture d'usage

Ce que le service enregistre de son propre usage, sous quelle forme, et comment l'interroger. Pour qui exploite les données d'usage ou vérifie ce qui est conservé.

La capture enregistre les questions posées, les sources proposées et leur sort, les réponses et les appréciations. Elle ne décide rien : aucune donnée n'est promue automatiquement en jeu de questions ni en réglage. Posture de sécurité : [SECURITY.md](SECURITY.md).

## Pourquoi

Les jeux de questions du dépôt sont générés ou écrits à la main : ils règlent la recherche, ils ne disent pas ce que les gens demandent. La capture fournit trois choses qu'aucun jeu ne fournit :

1. **les décochages** : une source bien classée qu'un humain écarte est une annotation négative gratuite ;
2. **un jeu de questions réel** : questions posées, sources validées par un humain, appréciation de la réponse ;
3. **la distribution des classes de questions** : résumé de document, agrégation, multi-saut, que l'architecture ne couvre pas. La question est stockée telle qu'elle a été posée.

## Ce qui est capturé, et où

| | |
|---|---|
| Fichier | `/app/data/usage.sqlite` (`USAGE_DB_PATH`), volume `rag_agent_state` |
| Activation | `USAGE_CAPTURE=true` par défaut |
| Conservation | illimitée, aucune purge |
| Taille | journalisée au démarrage, publiée par `GET /health` sous `usage` |
| Sortie réseau | aucune |

Un enregistrement couvre deux requêtes HTTP : `/chat/start` connaît les sources proposées, `/chat/resume` celles qui ont été retenues et la réponse. Les deux phases sont jointes par `thread_id`. L'écriture de `/chat/resume` a lieu après le dernier événement SSE, hors du chemin de diffusion. Aucun échec d'écriture ne remonte à l'appelant : il est journalisé en `WARNING` et compté dans `usage.failures`.

La colonne `endpoint` distingue trois chemins, et toute lecture des décochages doit en tenir compte :

| `endpoint` | Chemin | Sélection des sources | Lignes `sources_proposees` |
|---|---|---|---|
| `chat` | `/chat/start` + `/chat/resume` | humaine | oui |
| `answer` | `/answer` | automatique (`AUTO_SELECT_TOP_K`) | oui |
| `chat_simple` | `/chat/simple` | faite par le client en amont | non |

Une campagne `make eval` écrit une interaction `answer` par question du jeu. `/chat/simple` rend son `thread_id` pour pouvoir être noté ; `/answer` n'en rend pas.

## Le schéma

### `interactions` : une ligne par interaction

| Colonne | Contenu |
|---|---|
| `thread_id` | Clé primaire, identifiant de session LangGraph |
| `endpoint` | `chat`, `answer` ou `chat_simple` |
| `started_at`, `completed_at` | ISO 8601 UTC ; `completed_at` NULL = abandon avant la réponse |
| `question` | La question telle qu'elle a été posée |
| `search_query`, `search_translation` | La question rendue autonome, et sa traduction |
| `ranked_element_ids` | Le classement complet (JSON) |
| `submitted_element_ids`, `submitted_section_ids` | Ce qui a été reconstruit et soumis (JSON), avant la coupe de fenêtre |
| `response`, `citations`, `images` | La réponse et ce qu'elle cite |
| `search_count` | Itérations de la boucle agentique (> 1 : le modèle a redemandé) |
| `dropped_contexts` | Sections écartées par le budget de fenêtre ; une source tronquée et retenue n'y compte plus ([llm.md](llm.md)) |
| `retrieval_ms`, `rerank_ms`, `generation_ms` | Latences par étage |
| `config_hash`, `config_json` | Empreinte de la configuration (§ suivant) |
| `rating`, `rating_comment`, `rated_at` | `utile`, `inutile` ou NULL ; commentaire libre |

### `sources_proposees` : une ligne par source proposée

| Colonne | Contenu |
|---|---|
| `thread_id` + `element_id` | Clé primaire |
| `rang` | Rang du reranker, 1 = le mieux classé (pas l'ordre d'affichage, groupé par document) |
| `filename`, `collection`, `source_path`, `section_title`, `language`, `page_no` | Le passage et son document |
| `relevance` | Pertinence dans [0, 1], sigmoïde du logit |
| `rerank_score` | Logit brut du cross-encoder |
| `retenue` | 1 retenue, 0 écartée, NULL sélection jamais faite |

Les sources ajoutées par une itération de la boucle agentique ne figurent pas ici : personne ne les a vues. Elles apparaissent dans `submitted_element_ids`.

### Les deux vues : lire les décochages humains

`/answer` écrit `retenue = 0` sur toutes les sources au-delà de sa sélection automatique : ce sont des zéros que personne n'a décidés, indiscernables en SQL d'un décochage humain. Les deux vues les écartent :

| Vue | Contenu |
|---|---|
| `sources_humaines` | Sources des interactions `chat`, les trois états de `retenue`, plus `question`, `started_at`, `rating` |
| `decochages` | `sources_humaines` restreinte à `retenue = 0` |

Toujours lire les décochages par ces vues, jamais par `sources_proposees` directement.

## L'empreinte de configuration

Chaque interaction porte `config_json` et `config_hash` (12 caractères) :

```json
{
  "embedding_model": "paraphrase-multilingual-MiniLM-L12-v2",
  "rerank_model": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
  "retrieval_top_k": 50, "rerank_top_k": 10, "translation_weight": 1.0,
  "llm_num_ctx": 8192, "llm_max_tokens": 4096,
  "llm_model": "google/gemma-4-E4B-it-qat-w4a16-ct",
  "prompts_sha256": "5c71fd1d6414"
}
```

`prompts_sha256` est un condensat du contenu de `prompts/` : une modification de prompt change la configuration. La clé `llm_model` porte ce nom depuis le lot 28 ; une requête écrite avant doit être reprise.

```sql
-- Ce que chaque configuration a produit, et comment elle a été jugée.
SELECT i.config_hash,
       json_extract(i.config_json, '$.llm_model')      AS modele,
       json_extract(i.config_json, '$.prompts_sha256') AS prompts,
       COUNT(*)                      AS interactions,
       SUM(i.endpoint = 'chat')      AS interactives,  -- dénominateur des avis
       SUM(i.rating = 'utile')       AS utiles,
       SUM(i.rating = 'inutile')     AS inutiles
FROM   interactions i
GROUP  BY i.config_hash
ORDER  BY interactions DESC;
```

## Les requêtes des trois usages

### 1. Les décochages

```sql
-- Quelles sources bien classées les gens écartent-ils ?
SELECT collection, filename, section_title, language,
       COUNT(*)                 AS decochages,
       MIN(rang)                AS meilleur_rang,
       ROUND(AVG(relevance), 3) AS pertinence_moyenne
FROM   decochages              -- humains uniquement, retenue = 0
WHERE  relevance >= 0.5
GROUP  BY collection, filename, section_title
ORDER  BY decochages DESC, meilleur_rang;
```

```sql
-- Le taux de retenue par rang.
SELECT rang,
       COUNT(*)     AS proposees,
       SUM(retenue) AS retenues,
       ROUND(1.0 * SUM(retenue) / COUNT(*), 3) AS taux_de_retenue
FROM   sources_humaines
WHERE  retenue IS NOT NULL     -- NULL = sélection jamais faite, pas un rejet
GROUP  BY rang
ORDER  BY rang;
```

### 2. Un jeu de questions réel

```sql
-- Question posée, sources validées par un humain, réponse, appréciation.
SELECT i.question, i.response, i.rating, i.rating_comment,
       json_group_array(s.element_id) AS sources_validees
FROM   interactions     i
JOIN   sources_humaines s ON s.thread_id = i.thread_id AND s.retenue = 1
WHERE  i.completed_at IS NOT NULL
GROUP  BY i.thread_id
ORDER  BY i.started_at;
```

### 3. La distribution des classes de questions

```sql
-- Première coupe par mots-clés ; la question étant stockée telle quelle,
-- un meilleur classificateur pourra être passé plus tard sur les mêmes lignes.
SELECT CASE
         WHEN lower(i.question) LIKE '%résume%'
           OR lower(i.question) LIKE '%résumé%'
           OR lower(i.question) LIKE '%summar%'         THEN 'résumé de document'
         WHEN lower(i.question) LIKE '%combien%'
           OR lower(i.question) LIKE '%how many%'
           OR lower(i.question) LIKE '%quels documents%' THEN 'agrégation'
         ELSE 'factuelle ou autre'
       END                              AS classe,
       COUNT(*)                         AS questions,
       ROUND(AVG(i.search_count), 2)    AS recherches_moyennes,
       SUM(i.rating = 'inutile')        AS jugees_inutiles
FROM   interactions i
WHERE  i.endpoint = 'chat'
GROUP  BY classe
ORDER  BY questions DESC;
```

```sql
-- Le multi-saut réel : le modèle a-t-il redemandé à chercher ?
SELECT i.question, i.search_count, i.dropped_contexts
FROM   interactions i
WHERE  i.search_count > 1
  AND  i.endpoint = 'chat'
ORDER  BY i.started_at;
```

Sans le filtre `endpoint = 'chat'`, les campagnes rejouées dominent le comptage.

## L'appréciation

`POST /feedback` attache une note binaire à une interaction enregistrée ; les deux boutons de la phase de réponse du frontend l'appellent.

```bash
curl -X POST http://localhost:8011/feedback \
  -H 'Content-Type: application/json' \
  -d '{"thread_id": "…", "rating": "utile", "comment": "facultatif"}'
```

Un `thread_id` inconnu rend 404 ; la capture désactivée rend 200 avec `recorded: false`.

## Exporter

Le conteneur ne porte pas `scripts/` : lui passer le script par l'entrée standard. La base est ouverte en lecture seule (`mode=ro`), l'export peut tourner pendant que le service écrit.

```bash
docker exec -i rag-agent-api python - < scripts/usage_export.py > usage.json
docker exec -i rag-agent-api python - --endpoint chat --since 2026-09-01 < scripts/usage_export.py
```

La sortie imbrique les sources dans leur interaction, avec l'`endpoint` de celle-ci ; `--endpoint chat` rend directement le sous-ensemble humain. `schema_version` est lu dans le fichier (`PRAGMA user_version`). Un chemin faux rend `rc=1`, jamais une base vide.

## Le coût

Mesuré sur le module seul, sans la pile (100 interactions séquentielles de 10 sources, réponse d'environ 1 000 caractères). Le support de stockage domine :

| Support | `record_start` | `record_completion` |
|---|---|---|
| ext4, disque virtuel WSL2 | médiane 5,2 ms, p95 6,8 ms | médiane 4,6 ms, p95 6,6 ms |
| tmpfs (`/dev/shm`) | médiane 1,3 ms, p95 1,8 ms | médiane 1,1 ms, p95 1,4 ms |

Retenir l'ordre de grandeur, quelques millisecondes par écriture, et remesurer sur le support de déploiement. Un enregistrement pèse environ 4,6 ko (1 interaction + 10 sources).

Trois réglages SQLite portent ces chiffres :

- `PRAGMA journal_mode = WAL`, posé au démarrage seulement : le poser dans le chemin d'écriture faisait perdre des écritures simultanées (six sur vingt à dix interactions simultanées) ;
- `BEGIN IMMEDIATE` avec `isolation_level=None` : une interaction et ses sources partent dans une seule transaction ;
- `PRAGMA synchronous = NORMAL` : perdre la dernière transaction lors d'une coupure est acceptable pour de l'observation (1 162 ms pour vingt interactions simultanées en synchronisation complète, contre 213 ms).

## L'état au 27 septembre 2026

`mesuré` à 06:19 UTC par `GET /health`, bloc `usage` : capture active, 1 618 interactions, 16 180 sources proposées, 10 002 432 octets, 0 échec d'écriture.

`mesuré` à 06:21 UTC par une requête SQLite en lecture seule (`mode=ro`) dans le conteneur, comptes seuls : 1 601 interactions `answer` (campagnes), 21 interactions `chat` dont 20 menées jusqu'à la réponse, 0 `chat_simple` ; 2 appréciations, toutes deux `utile`, et 2 commentaires non vides ; 134 décochages humains. La base grandit pendant la lecture : l'export de 06:34 UTC comptait 22 interactions `chat`.

`/health` ne publie pas le nombre d'appréciations ; il se lit par l'export ou par la requête des configurations ci-dessus.

## Ce que la capture ne fait pas

- **Aucune détection de données personnelles.** Une question peut en contenir ; elle est stockée telle quelle.
- **Aucune purge.** La taille reste visible dans `/health`.
- **Aucun chiffrement au repos**, et aucun endpoint de lecture : la capture écrit, elle ne sert rien.
- **Aucune exploitation automatique.**

## Désactiver

```bash
USAGE_CAPTURE=false     # ou USAGE_DB_PATH= (vide)
```

Désactivée, la capture ne crée même pas le fichier.
