# Pour le pipeline d'ingestion

Ce que l'agent attend des stores que remplit `rag-ingestion-pipeline`, ce qui casse en silence sinon, et ce que l'agent demande à la machine. Pour les équipes qui travaillent sur le pipeline ; se lit sans ouvrir le reste de ce dépôt.

L'agent ne lit jamais les documents sources. Il lit trois stores que le pipeline remplit, en lecture seule. Le détail de la lecture, côté agent, est dans [stores.md](stores.md).

## 1. La règle sans exception : le même modèle d'embedding

Le modèle d'embedding doit être `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions), le même des deux côtés. C'est le défaut du réglage `EMBEDDING_MODEL_NAME` de l'agent.

L'agent confronte son réglage à l'estampille `embedding_model` de la collection `rag_documents` avant chaque recherche dense :

- estampille absente : l'agent refuse de chercher, toute recherche rend `503` et `/health` passe en `degraded` ;
- estampille différente du réglage : même refus, les deux noms sont publiés ;
- estampille conforme : rien à faire. La collection en service la porte déjà.

Trois consignes en découlent :

- **Ne changer le modèle que des deux côtés à la fois**, et seulement après une campagne comparative : un changement impose une réingestion complète.
- **Redémarrer l'agent après une réingestion faite avec un autre modèle.** L'estampille est lue à l'ouverture de la collection, et `POST /reindex` ne touche que l'index lexical.
- **Ignorer toute mention de `all-MiniLM-L6-v2` dans l'historique de ce dépôt** : c'est un modèle anglais, un vestige et non une instruction. L'inventaire de ses mentions est tenu par `tests/unit/test_coherence_depot.py`.

Le cross-encoder de reranking, réglé côté agent (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`), est lui aussi multilingue : un reranker anglais rendait des scores plats sur une question française. Raisonnement complet : §4.4 du [registre](axes_amelioration.md).

## 2. Ce que l'agent lit

### ChromaDB, collection `rag_documents`

Métadonnées attendues par chunk : `element_id`, `graph_node_id`, `filename`, `collection`, `source_path`, `section_title`, `language`, `depth`, `label`, `page_no`, `media_url`, `object_key`, `chunk_index`, `chunk_count`.

- **`element_id` est déterministe** : sha256 tronqué à 10 hexadécimaux, validé par l'agent contre `^[a-f0-9]{10}$`. Réingérer le même corpus rend les mêmes identifiants, et les jeux de questions de l'agent restent valides. Remplacer le corpus change les identifiants par construction : un jeu de questions est un état de corpus, et l'agent le revérifie contre les stores avant toute mesure (`make verifier-les-ancrages`, §4.3 du registre).
- **`source_path` est l'identité d'un document**, jamais `filename` seul : deux ouvrages peuvent contenir une « Préface ».
- **Les chunks d'un élément long partagent son `element_id`**, ordonnés par `chunk_index` et `chunk_count`. La déduplication de l'agent en dépend.

### NebulaGraph, space `rag_space`

`Document → SectionHeader → … → élément` par `PARENT_OF(sequence)`, plus une arête de chaque légende vers son illustration (`DESCRIBES` ou `LINKED_TO`). VIDs : sha256[:10] pour les éléments, `doc_{chemin}` pour les documents.

`sequence` porte l'ordre de lecture ; un `sequence` absent ou non monotone casse la reconstruction sans erreur visible. Les trois réserves de lecture de `sequence` sont écrites et gardées côté agent : [stores.md](stores.md#les-trois-réserves-de-lecture-de-sequence).

Le graphe est hiérarchique depuis la réingestion du 2 septembre 2026 : 78,2 % des `SectionHeader` ont pour parent un autre `SectionHeader` (§4.6 du registre). L'agent en construit le fil d'Ariane sans réglage.

### Le stockage objet, bucket `documents`

Les crops des figures et tableaux sont référencés par `media_url` et `object_key`. L'agent ne sert au navigateur que les objets cités par le graphe (`RESTRICT_MEDIA_TO_GRAPH=true`) : un objet présent dans le bucket mais absent du graphe reste inaccessible, délibérément. L'agent lit avec le jeu de clés en lecture seule publié par le pipeline.

## 3. La seule chose que le pipeline doit appeler : `POST /reindex`

L'agent tient un index BM25 en mémoire. La recherche dense suit ChromaDB ; la recherche lexicale, non.

**Appeler `POST /reindex` en fin d'ingestion**, sur le port hôte `8011`. Sans cet appel, un document ingéré après le démarrage de l'agent reste invisible en recherche lexicale. La réponse porte le nombre de chunks indexés, à confronter à ce qui vient d'être écrit.

Un filet existe côté agent (comparaison de `collection.count()` au nombre de chunks indexés), mais il ne voit pas un corpus dont on a retiré autant de chunks qu'on en a ajouté. L'appel est un contrat, pas une option.

## 4. Ce que l'agent demande à la machine

### Le démarrage exige une carte NVIDIA

`docker-compose.yml` réserve une carte au service `agent-api`. Sur une machine sans carte, sans pilote ou sans NVIDIA Container Toolkit, le conteneur ne démarre pas : `mesuré` le 11 septembre 2026, `docker run` rend `rc=125` et `nvidia-container-cli: device error`. Le pipeline, lui, n'a pas besoin de GPU.

Pour faire tourner l'agent sans carte, jouer les deux lignes ensemble :

```bash
# 1. dans le .env de l'agent ; sans elle, le service démarre mais chaque recherche rend 500
TORCH_DEVICE=cpu
```
```bash
# 2. après avoir commenté le bloc deploy: du service agent-api dans docker-compose.yml
docker compose up -d agent-api
```

Vérifier ensuite :

```bash
curl -s http://localhost:8011/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['torch_device']['hors_d_atteinte'], 'inconnues:', d['services_unknown'])"
```

| Sortie | Lecture |
|---|---|
| `ok None inconnues: []` | Le geste a marché |
| `degraded` suivi d'un motif | La première ligne manque ; le motif nomme la condition en défaut |
| `ok None inconnues: ['peripherique_torch', …]` | La sonde n'a pas répondu sous son plafond de 3 s : état inconnu, rejouer |

Mode d'emploi complet du GPU : [gpu_cuda.md](gpu_cuda.md).

### La mémoire que l'agent prend sur une carte partagée

L'agent partage la carte avec le serveur d'inférence. Il publie ce qu'il prend dans `/health` :

```bash
curl -s http://localhost:8011/health | python3 -c "import json,sys; d=json.load(sys.stdin)['torch_device']; print('borne =', d['concurrence_max'], '| pic réservé =', d['pic_memoire_reservee_mio'], 'Mio')"
```

**Réservation à prévoir : 2 048 Mio**, `calculé` le 14 septembre 2026 à la borne par défaut `TORCH_MAX_CONCURRENCY = 4`. La base : cinq paliers mesurés sur `/sources` (1 → 1 362 Mio, 2 → 1 370, 4 → 1 506, 8 → 1 570, 16 → 1 984), dont on tire la pente marginale maximale, 68,0 Mio par requête :

    réservation(N) = 1 362 Mio + (N - 1) x 68,0 Mio

soit 1 566 Mio à N = 4, arrondis à 2 048. La marge de 482 Mio (+30,8 %) couvre les 226 MiB de contexte CUDA que `pic_memoire_reservee_mio` ne compte pas. Détail et réserves : §4.51 du registre.

Trois conditions pour que ce chiffre vaille :

- la borne est en service et l'agent a redémarré depuis : l'allocateur de torch ne rend jamais ce qu'il a pris ;
- la réservation est inconditionnelle : l'empreinte de l'agent est paresseuse, 0 Mio au repos, ses modèles ne se chargeant qu'à la première question ;
- le dimensionnement de `--gpu-memory-utilization`, option de lancement du serveur d'inférence, compte deux désérialisations simultanées, pas une.

Le nombre de désérialisations simultanées, `mesuré` le 14 septembre 2026 (site canonique : §10bis de [gpu_cuda.md](gpu_cuda.md), recopié ici pour que ce document se lise seul) :

| `TORCH_MAX_CONCURRENCY` | Désérialisations simultanées |
|---:|---:|
| 1 | 1 |
| 4 (défaut) | 1 |
| 5 | 2 |
| 8 | 2 |

Chaque modèle n'est construit qu'une fois, quelle que soit la borne ; le majorant sûr est donc 2, le nombre de modèles. Le surcoût transitoire d'une désérialisation n'est pas mesuré.

Relevé courant sur ce poste, `mesuré` le 27 septembre 2026 à 06:19 UTC par `nvidia-smi --query-compute-apps` croisé avec le PID du conteneur : l'agent tient 1 460 MiB de la carte, et `/health` publie un pic réservé de 1 234 Mio.

## 5. L'ordre de remise en route

1. Démarrer `rag-ingestion-pipeline`, qui crée le réseau `rag_network` et les trois stores.
2. Vérifier le modèle d'embedding avant d'ingérer (§1).
3. Ingérer le corpus.
4. Rendre le serveur d'inférence joignable : `llm-service` et son réseau `llm-net`, ou un autre serveur au dialecte OpenAI désigné par `LLM_HOST`.
5. Démarrer `rag-agent-chat` et vérifier que `GET /health` rend `status: ok`.
6. Appeler `POST /reindex`.
7. Côté agent : `make verifier-les-ancrages`, puis une campagne `make eval`.

## 6. Ce qui reste ouvert chez le pipeline

- **Illustrations sans légende.** L'arête de légende ne couvre que les visuels légendés dans le document d'origine. Une figure sans légende est introuvable par la recherche et impossible à juger pour le modèle. Une description générée à l'ingestion et indexée comblerait ce trou.
- **Le coût du filet de réindexation.** L'agent appelle `collection.count()` à chaque recherche lexicale et à chaque `/health`. Ce coût n'est pas mesuré ; si `POST /reindex` est toujours appelé, le filet pourra être allégé côté agent.

## 7. Ce qu'il est utile de rapporter après une ingestion

- le modèle d'embedding effectivement utilisé ;
- le nombre de documents et de chunks, à confronter à `collection.count()` ;
- la sortie de `POST /reindex`.

L'historique des échanges entre les deux dépôts (constats rendus, demandes closes) est au §4.16 du registre et dans le [journal](pilotage_du_chantier.md).
