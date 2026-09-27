# Les stores, vus de l'agent

Ce que l'agent lit dans les stores du pipeline d'ingestion, et ce qui casse quand l'attente n'est pas tenue. Pour qui exploite l'agent ou modifie sa lecture des stores.

L'agent ne possède aucune donnée du corpus. Il lit, en lecture seule, trois stores produits par [rag-ingestion-pipeline](https://github.com/floSa/rag-ingestion-pipeline), dont la configuration et l'exploitation sont documentées là-bas. Le contrat écrit à l'intention du pipeline est [pour_le_pipeline_ingestion.md](pour_le_pipeline_ingestion.md).

| Store | Adresse par défaut (`settings.py`) | Lu par | Usage |
|---|---|---|---|
| ChromaDB, collection `rag_documents` | `chromadb:8000` | `retriever.py`, `lexical.py` | Recherche dense, texte intégral, source de l'index BM25 |
| NebulaGraph, space `rag_space` | `graphd:9669` | `graph_context.py` | Reconstruction de section, liste blanche du proxy média |
| Stockage objet compatible S3, bucket `documents` | `seaweedfs:8333` | `stockage_objet.py` | Illustrations et tableaux servis par `GET /media/…` |

Les trois sont joints par le réseau Docker `rag_network`, créé par le pipeline.

## ChromaDB : la recherche

### Métadonnées lues

| Clé | Usage |
|---|---|
| `element_id` | Pivot vers le graphe. Hash `^[a-f0-9]{10}$` |
| `source_path` | Identité du document, clé de groupement des sources |
| `filename` | Nom du chapitre, affiché dans la citation |
| `collection` | Ouvrage, repli quand le graphe ne le donne pas |
| `section_title` | Situe le passage dans l'écran de sélection, sans appel au graphe |
| `language` | Langue du document, affichée et utilisée pour stratifier l'évaluation |
| `page_no` | Situe le passage ; vaut 1 pour les formats non paginés |
| `chunk_index`, `chunk_count` | Remettent dans l'ordre les fenêtres d'un élément long |
| `media_url`, `object_key` | Lien vers l'objet média ; `object_key` porte la clé nue |
| `depth` | Lu, non utilisé : la remontée du graphe fait mieux |

Un élément long est réparti sur plusieurs chunks (`abc#0`, `abc#1`) qui partagent leur `element_id`. L'agent déduplique avant de couper au top-K ; sans cela, plusieurs fenêtres d'un même passage occuperaient plusieurs places.

### Le modèle d'embedding doit être le même des deux côtés

C'est la panne la plus coûteuse du système : les deux candidats rendent des vecteurs de même largeur, rien dans la forme ne les distingue. Le réglage est `EMBEDDING_MODEL_NAME`, défaut `paraphrase-multilingual-MiniLM-L12-v2`.

Avant chaque recherche dense, l'agent confronte son réglage à l'estampille `embedding_model` de la collection. Estampille différente ou absente : la recherche rend `503` en nommant les deux modèles, et `/health` passe en `degraded`. Raisonnement et décisions : §4.4 du [registre](axes_amelioration.md).

Une réserve : `/chat/resume` vérifie la concordance avant d'ouvrir son flux, mais une divergence apparue pendant une réponse déjà commencée ne peut plus rendre `503`. Le flux s'arrête alors tronqué, rien de faux n'est servi, et la cause est journalisée en `ERROR` (§4.20 et §4.21 du registre).

### L'index BM25 vit dans le processus de l'agent

La recherche dense interroge ChromaDB à chaque requête et suit le corpus sans rien faire. L'index BM25, lui, est une copie en mémoire, construite à la première recherche lexicale à partir de tous les chunks de la collection.

- Après une ingestion, appeler `POST /reindex` : c'est le contrat, et la réponse porte le nombre de chunks indexés.
- À défaut, l'agent compare `collection.count()` au nombre de chunks indexés et reconstruit en tâche de fond quand les deux divergent. Ce filet ne voit pas un corpus dont on a retiré autant de chunks qu'on en a ajouté.
- `/health` rend `index_lexical: false` tant que l'index n'est pas construit ou qu'il décrit un corpus disparu. Juste après un redémarrage, la valeur est donc `false` jusqu'à la première recherche.
- Avec plusieurs workers uvicorn, `POST /reindex` ne reconstruit que l'index du worker qui reçoit la requête. Le déploiement actuel tourne un seul worker.

## NebulaGraph : la structure

L'agent remonte de l'élément trouvé jusqu'au `Document` en notant les titres traversés, puis redescend chercher une fenêtre d'éléments, la fin de la section précédente et le début de la suivante.

| Élément | Attente |
|---|---|
| VIDs | Hash de 10 hexadécimaux, ou `doc_{chemin}` jusqu'à 256 octets |
| `PARENT_OF(sequence)` | Hiérarchie et ordre de lecture ; `sequence` permet d'atteindre la section voisine |
| Arête légende → visuel | Cherchée dans le schéma parmi `LINKED_TO` puis `DESCRIBES` ; son absence est un cas normal |
| `Document.collection` | Ouvrage, source préférée pour les citations |
| Propriété `text` | Tronquée à 2000 caractères par l'ingestion |

Deux pièges à connaître :

- sous `GO … OVER … REVERSELY`, `dst(edge)` rend le nœud de départ ; c'est `src(edge)` qui porte le parent. L'erreur est silencieuse : la remontée n'avance jamais ;
- l'arête des légendes a déjà été renommée une fois. Son nom est donc lu dans le schéma.

Le graphe porte la structure, pas le texte complet. L'agent relit dans ChromaDB le texte des éléments qui frôlent la troncature ; un tableau exporté dépasse souvent la limite. `GRAPH_TEXT_TRUNCATION` doit suivre le `graph_text_max_chars` de l'ingestion.

Après une purge du graphe par le pipeline, la session que l'agent garde ouverte ne connaît plus les tags : `nebula3` rend alors un résultat en échec (`E_SEMANTIC_ERROR`), sans lever. L'agent rouvre la session et rejoue une fois sur cette seule erreur, et la sonde de `/health` lit un tag pour la voir (§4.80 du registre).

### Les trois réserves de lecture de `sequence`

Site canonique de ces réserves ; les autres pages y renvoient. Le contrat d'ingestion garantit que `sequence` porte l'ordre de lecture et qu'elle est monotone ; ces réserves disent comment la lire. Chaque chiffre se rejoue en lecture seule :

```bash
docker exec -i rag-agent-api python - < scripts/mesurer_le_graphe.py
```

1. **`sequence` repart à 0 dans chaque document.** `mesuré` le 3 septembre 2026 : les 23 documents commencent à 0, et les 253 paires de documents ont des intervalles qui se recouvrent. Tout « avant / après » se borne donc au document ; le code part toujours d'un VID de parent, jamais d'une valeur de `sequence` seule.
2. **Elle n'est pas contiguë sous un parent.** `mesuré` le 3 septembre 2026 : 167 parents sur les 692 qui ont au moins deux enfants portent des valeurs non contiguës (les 71 parents à enfant unique ne peuvent pas l'être). L'écart s'explique entièrement par la taille du sous-arbre du frère précédent : 0 discordance sur les 14 410 couples de frères consécutifs. `sequence` numérote l'ouvrage entier, pas les enfants d'un parent.
3. **L'écart entre deux enfants peut être grand.** `mesuré` le 3 septembre 2026 : 994 au plus, sous `doc_htms/MLOps with Databricks/7. Foundation Models and Context Engineering`.

**Conséquence : la fenêtre d'éléments se découpe sur des positions de liste, jamais sur des valeurs de `sequence`.** `_get_children` lit tous les enfants avec un `ORDER BY` et sans filtre d'intervalle, puis `_window_around` découpe par position. Un encadrement `sequence ∈ [s−k, s+k]` poussé dans la requête serait silencieusement amputé : `mesuré` le 3 septembre 2026 à la fenêtre par défaut (13 éléments), 1 141 ancres sur 15 173 (7,5 %) rendraient moins d'éléments, chez 162 parents, avec une perte maximale de 12 éléments sur 13.

Le découpage est gardé par `tests/unit/test_lecture_sequence.py`, contre un graphe factice qui honore les clauses `WHERE` et rend ses enfants dans un ordre non trié. La définition de « section voisine » (le frère en-tête sous le parent commun) n'est gardée par aucun test : c'est une décision ouverte, §4.6 du registre, qui porte aussi la forme du graphe (profondeur, imbrication des titres).

### Ce que le bouchon modélise

Le graphe factice de `test_lecture_sequence.py` évalue une conjonction (`AND`) de comparaisons entre la `sequence` de l'arête, ou une colonne d'amont qui la porte, et un littéral entier. Sur toute autre écriture qui touche à `sequence`, il lève `ClauseNonEvaluableError` au lieu de rendre toutes les lignes : une cécité du bouchon produit un rouge, jamais un vert.

Les écritures refusées ont été confrontées au graphd réel, en lecture seule, par `scripts/mesurer_le_graphe.py` (`rejoué` le 4 septembre 2026, sur 80 des 334 parents à treize enfants ou plus) :

| Écriture de l'encadrement | Même ensemble que l'écriture classique |
|---|---|
| en aval d'un tube, `\| YIELD … WHERE $-.seq >= …` | 80 sur 80 |
| `IN` sur une liste de valeurs | 80 sur 80 |
| arithmétique, `sequence − B >= 0 AND H − sequence >= 0` | 80 sur 80 |
| alias de la liste `YIELD` filtré dans le même `YIELD` | 0 ligne : nGQL refuse l'alias |

La requête réelle de `_get_children`, qui nomme `sequence` en projection sans la comparer, ne lève pas ; un prédicat étranger à `sequence` est ignoré. Les deux cas sont gardés.

## Le stockage objet : les illustrations

Les objets médias (crops PNG des figures et tableaux) vivent dans un stockage compatible S3, configuré par `S3_ENDPOINT`, `S3_BUCKET`, `S3_SECURE`, `S3_ACCESS_KEY` et `S3_SECRET_KEY`. L'agent lit avec le jeu de clés en lecture seule que publie le pipeline ; aucune valeur n'est écrite dans ce dépôt, qui est public.

Le navigateur ne résout pas les adresses internes : l'API relaie chaque objet par `GET /media/{chemin}`. Avec `RESTRICT_MEDIA_TO_GRAPH=true` (défaut), le proxy ne sert que les objets cités par le graphe. Au déploiement de la version servie, le journal de l'agent annonçait `Proxy média : 212 objets autorisés.` (ligne 97 du [journal](pilotage_du_chantier.md)). Posture de sécurité : [SECURITY.md](SECURITY.md).

## Quand un store tombe

- Les clients sont mémorisés. Chaque module sait oublier son cache et retenter une fois : un redémarrage de store coûte une requête, pas un redémarrage de l'agent.
- `GET /health` sonde ChromaDB, NebulaGraph, le serveur LLM et l'index BM25 en parallèle, sous un plafond global de 3 s, pour tenir dans le délai de 5 s du healthcheck Docker (§1.27 du registre). Une sonde qui n'a pas répondu vaut `false` dans `services` et est nommée dans `services_unknown`.
- L'état de l'index BM25 n'entre pas dans `status` : son absence dégrade la recherche sans l'empêcher.
- Un compte de collection illisible n'est pas traité comme un index périmé : la panne de ChromaDB est déjà rapportée par `services.chromadb`.

## Les fichiers que l'agent écrit

L'agent n'écrit que dans son propre volume, `rag_agent_state`, monté sur `/app/data` :

| Fichier | Contenu | Détail |
|---|---|---|
| `checkpoints.sqlite` | Sessions LangGraph suspendues entre `/chat/start` et `/chat/resume`, plus la table `sessions_agent`, registre de leur purge | [architecture.md](architecture.md#purge-durable-des-sessions) |
| `usage.sqlite` | Capture d'usage | [capture_usage.md](capture_usage.md) |

`GET /health` publie `sessions.purged` et `sessions.failures` : un `purged` qui reste à zéro pendant que le fichier grossit est le symptôme à surveiller.
