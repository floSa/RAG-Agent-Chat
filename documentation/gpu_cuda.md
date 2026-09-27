# Le GPU de l'agent : l'activer, le vérifier, le retirer

Comment l'agent calcule ses embeddings et son reranking sur le GPU, comment le vérifier, ce que cela coûte et comment revenir au processeur. Pour qui monte le projet sur une machine neuve ou partage la carte avec un autre service.

Seuls l'embedder et le cross-encoder de l'agent sont concernés. La génération tourne sur le serveur d'inférence, externe à ce dépôt ([llm.md](llm.md)).

## 1. Les trois conditions

Le calcul part sur la carte si et seulement si les trois conditions sont vraies. Chacune, seule, ramène tout sur le processeur, sans message : le service répond, plus lentement.

| | Condition | Où elle se règle | Ce qui la lit |
|---|---|---|---|
| (a) | `torch` est un build CUDA dans l'image | `Dockerfile.agent`, `ARG TORCH_INDEX_URL` (défaut `cu130`) | `torch.version.cuda` |
| (b) | le conteneur accède à la carte | bloc `deploy.resources.reservations.devices` du service `agent-api` dans `docker-compose.yml`, plus le NVIDIA Container Toolkit sur l'hôte | `torch.cuda.is_available()` |
| (c) | le réglage nomme la carte | `TORCH_DEVICE` dans le `.env` (défaut du code : `cuda`) | `settings.torch_device` |

`GET /health` publie les trois sous `torch_device` :

```bash
curl -s http://localhost:8011/health | python3 -m json.tool
```

`mesuré` le 27 septembre 2026 à 06:19 UTC sur le service :

```
"torch_device": {
    "requested": "cuda",             <- condition (c)
    "torch_version": "2.14.0+cu130", <- condition (a), le suffixe
    "cuda_build": "13.0",            <- condition (a), la version CUDA compilée
    "cuda_available": true,          <- condition (b)
    "embedding": "cuda:0",           <- le modèle est posé sur la carte
    "rerank": "cuda:0",
    "hors_d_atteinte": null,
    "concurrence_max": 4,
    "pic_memoire_reservee_mio": 1234.0
}
```

`embedding` et `rerank` valent `null` tant que le modèle n'a pas été chargé : la route de santé ne charge rien. Poser une question, puis relire.

## 2. Vérifier (a) : le build de torch

```bash
docker exec rag-agent-api python -c "import torch; print(torch.__version__, torch.version.cuda, torch.backends.cuda.is_built(), torch.cuda.is_available())"
```

| Sortie | Lecture |
|---|---|
| `2.14.0+cpu None False False` | Build CPU : reconstruire l'image |
| `2.14.0+cu130 13.0 True False` | Build CUDA, carte invisible : condition (b), §3 |
| `2.14.0+cu130 13.0 True True` | (a) et (b) tenues ; reste (c), §4 |

`mesuré` le 27 septembre 2026 à 06:27 UTC : `2.14.0+cu130 13.0 True True`.

Vérifier une image avant de la servir (sans `--gpus`, `is_available()` rend `False`, ce qui est attendu : seule la ligne du build compte) :

```bash
docker run --rm --entrypoint sh rag-agent-chat-agent-api:latest -c 'python -c "import torch; print(torch.__version__, torch.version.cuda)"'
```

## 3. Vérifier (b) : le conteneur atteint la carte

### 3.1 Sur l'hôte

```bash
nvidia-smi
nvidia-ctk --version
docker info | grep -i runtime
```

`nvidia-smi` affiche la carte et, en haut à droite, la version CUDA du pilote (celle du §5). `nvidia-ctk` est le NVIDIA Container Toolkit ; sans lui, Docker ne donne pas de carte à un conteneur. `docker info` doit lister `nvidia` parmi les runtimes.

`mesuré` sur ce poste le 27 septembre 2026 à 06:27 UTC : pilote 595.91.07, CUDA du pilote 13.2, NVIDIA L4 de 23 034 MiB, toolkit 1.19.1, runtime `nvidia` présent.

Si le toolkit manque : installer le paquet `nvidia-container-toolkit`, puis `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`. Redémarrer le démon Docker redémarre tous les conteneurs de la machine : c'est une décision d'exploitation.

### 3.2 La réservation dans le compose

Elle vit sur le seul service `agent-api` :

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

Elle ne vaut qu'après recréation du conteneur.

### 3.3 La carte est-elle entrée dans le conteneur ?

```bash
docker inspect rag-agent-api --format '{{json .HostConfig.DeviceRequests}}'
docker exec rag-agent-api sh -c 'ls /dev/nvidia*'
docker exec rag-agent-api python -c "import torch; print(torch.cuda.is_available())"
```

- La première dit ce que Docker a demandé ; elle ne doit pas rendre `null`.
- La deuxième dit ce qui est entré. Aucun périphérique avec une demande non nulle désigne le toolkit de l'hôte.
- La troisième dit que torch voit la carte. `False` avec `/dev/nvidia*` présent désigne la condition (a) ou une incompatibilité de version (§5).

## 4. Vérifier (c) : le réglage

```bash
docker exec rag-agent-api python -c "from src.agent.settings import settings; print(settings.torch_device)"
```

Le réglage se change dans le `.env`, sans reconstruire, puis `docker compose up -d agent-api` (le conteneur est recréé ; `docker compose restart` ne relit pas le `.env`). Valeurs acceptées : ce que torch accepte, `cpu`, `cuda`, `cuda:1`. La valeur n'est pas validée au démarrage : un service debout qui publie son état se diagnostique mieux qu'un service qui refuse de démarrer.

Demander `cuda` sans (a) ou (b) fait lever torch au chargement du premier modèle, donc à la première recherche : `Torch not compiled with CUDA enabled` pour (a), `no CUDA-capable device is detected` ou `Found no NVIDIA driver` pour (b). `/health` reste à 200. Lire `/health` avant de changer ce réglage.

## 5. Quelle roue de torch pour quel pilote

Le suffixe d'une roue PyTorch (`+cpu`, `+cu126`, `+cu128`, `+cu130`) est la version du runtime CUDA embarqué dans la roue. Un pilote sert les runtimes antérieurs ou égaux au sien, jamais postérieurs : un pilote CUDA 13.2 sert `cu130`, `cu129`, `cu128`, `cu126`.

| Erreur | Symptôme |
|---|---|
| Roue trop récente pour le pilote | `is_available()` rend `False`, ou `CUDA driver version is insufficient` au premier calcul ; seules les recherches tombent |
| Roue CPU installée par-dessus une roue CUDA, ou l'inverse | `torch.__version__` et `torch.version.cuda` se contredisent ; `test_le_suffixe_du_build_et_la_version_cuda_disent_la_meme_chose` le voit |
| Carte trop ancienne pour le build | `… with CUDA capability sm_XX is not compatible …` ; la L4 est `sm_89`, dans la fenêtre |

Choisir le plus haut index que le pilote sert et qui publie la version de torch voulue. `mesuré` le 11 septembre 2026, en cp312 / x86_64 :

```bash
curl -s https://download.pytorch.org/whl/cu130/torch/ | grep -o 'torch-[0-9][0-9.]*+[a-z0-9]*-cp312-cp312-manylinux[_0-9]*x86_64\.whl' | sed 's/torch-//;s/-cp312.*//' | sort -V -u | tail -3
```

| Index | Plus haute version de torch |
|---|---|
| `cu126` | 2.14.0 |
| `cu128` | 2.11.0 |
| `cu129` | 2.13.0 |
| `cu130` | 2.14.0 |
| `cpu` | 2.14.0 |

Le dépôt retient `cu130` : le plus haut runtime servi par le pilote, à la même version de torch que le build CPU. Changer d'index sans éditer le Dockerfile :

```bash
docker build -f Dockerfile.agent --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126 -t rag-agent-chat-agent-api:latest .
```

## 6. Ce que cela coûte : la taille de l'image

Mesurer la taille par `docker image inspect -f '{{.Size}}'`. La colonne `SIZE` de `docker images` rend une autre grandeur sur ce poste (10,5 GB affichés pour l'image servie) et ne sert pas à comparer.

`mesuré` le 27 septembre 2026 à 06:20 UTC, champ `.Size` :

| Build | Image | Étiquette | Taille |
|---|---|---|---|
| `+cpu` | `2f4f1aa93f55` | `2026-09-11-avant-gpu` | 627 992 741 octets (0,63 Go) |
| `+cu130` | `fc06b6f86168` | `2026-09-11-gpu-cu130` | 3 445 750 805 octets (3,45 Go) |
| `+cu130`, image servie | `3eaf733ef1c2` | `latest`, `v1.1.0` | 3 446 416 662 octets (3,45 Go) |

Le build CUDA multiplie la taille par 5,5 environ (`calculé` depuis les deux premières lignes). Vérifier la place disponible avant de reconstruire : `df -h /var/lib/docker`.

## 7. Ce que le GPU rapporte

`mesuré` le 11 septembre 2026, `make eval`, 138 questions ; site canonique : [la campagne du 11 septembre](campagnes/2026-09-11-le-gpu-sur-les-etages-torch.md). Les deux bases CPU sont publiées, parce que la base change le chiffre :

| Métrique | CPU `08-reference` | CPU `10-lecteur-neuf` | GPU `11-cuda` |
|---|---:|---:|---:|
| `rerank_ms` p50 | 498 | 622 | 58 |
| `rerank_ms` p95 | 2 943 | 1 216 | 68 |
| `dense_ms` p50 | 120 | 115 | 72 |
| `dense_ms` p95 | 1 516 | 549 | 85 |
| `generation_ms` p50 | 4 682 | 4 616 | 4 722 |
| `total_ms` p50 | 7 298 | 6 846 | 6 481 |

| | contre `2026-09-08-reference` | contre `2026-09-10-lecteur-neuf-reglage` |
|---|---:|---:|
| `total_ms` p50 | −817 ms (−11,2 %) | −365 ms (−5,33 %) |
| `generation_ms` p50 (contention) | +40 ms | +106 ms |
| rapport gain / contention | 20,4 pour 1 | 3,4 pour 1 |

- La contention avec le serveur d'inférence est réelle et petite ; le gain vaut 3,4 à 20,4 fois son coût selon la base. Ne citer l'un de ces rapports qu'avec sa base.
- Le GPU est surtout plus régulier : `rerank_ms` p95 passe de 2 943 à 68 ms.
- Le rappel ne bouge pas : neuf métriques sur dix identiques question par question, 130/130 ex æquo ; `rang_reciproque` baisse sur une seule question (`G-006`, 1,0 → 0,5), effet numérique de deux candidats quasi ex æquo.

`TORCH_DEVICE` vaut `cuda` par défaut depuis cette campagne, décision du propriétaire.

## 8. Revenir au processeur

**Éteindre le GPU sans rien reconstruire** :

```bash
# dans le .env du projet
TORCH_DEVICE=cpu
```
```bash
docker compose up -d agent-api
curl -s http://localhost:8011/health | python3 -m json.tool | grep -A6 torch_device
```

**Revenir à l'image CPU étiquetée** :

```bash
docker image inspect -f '{{.Id}}' rag-agent-chat-agent-api:2026-09-11-avant-gpu
docker tag rag-agent-chat-agent-api:2026-09-11-avant-gpu rag-agent-chat-agent-api:latest
docker compose up -d --no-build agent-api
```

Cette image porte le code du 11 septembre 2026, pas seulement un autre build : tous les correctifs livrés depuis repartent avec. Pour garder le code courant, reconstruire en CPU :

```bash
docker build -f Dockerfile.agent --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu -t rag-agent-chat-agent-api:latest .
```

**Retirer la réservation : deux lignes, jamais une.** Retirer la réservation sans poser `TORCH_DEVICE=cpu` donne un conteneur qui démarre, un healthcheck vert, et 500 sur chaque recherche (`mesuré` le 14 septembre 2026 sur un jumeau branché aux vrais stores : `POST /search` → 500, `GET /health` → 200).

```bash
# 1. dans le .env
TORCH_DEVICE=cpu
```
```bash
# 2. après avoir commenté le bloc deploy: du service agent-api
docker compose up -d agent-api
docker inspect rag-agent-api --format '{{json .HostConfig.DeviceRequests}}'
curl -s http://localhost:8011/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d['torch_device']['hors_d_atteinte'])"
```

La dernière commande doit rendre `ok None`. `degraded` suivi d'un motif signale que la première ligne manque.

## 9. Après un redémarrage

Juste après la recréation du conteneur, `/health` annonce `index_lexical: false` jusqu'à la première recherche. Ne jamais lancer une campagne sur un service froid ; `scripts/evaluate.py` chauffe l'index et refuse la campagne (`rc=2`) s'il n'est toujours pas prêt. Détail : [stores.md](stores.md#lindex-bm25-vit-dans-le-processus-de-lagent).

## 10. Diagnostic

| Symptôme | Condition | Commande qui tranche |
|---|---|---|
| `cuda_build: null` | (a), image CPU | `docker exec rag-agent-api python -c "import torch; print(torch.version.cuda)"` |
| `cuda_build: "13.0"`, `cuda_available: false` | (b), carte absente du conteneur | `docker exec rag-agent-api sh -c 'ls /dev/nvidia*'` |
| `cuda_available: true`, `embedding: "cpu"` | (c), un `.env` pose `cpu` | `docker exec rag-agent-api python -c "from src.agent.settings import settings; print(settings.torch_device)"` |
| `embedding: null` après une requête, `status: ok` | le modèle n'a pas été chargé (voir les 503 de concordance) | `curl -s localhost:8011/health \| grep embedding_model` |
| `embedding: null` après une requête, `status: degraded` | le chargement lève ; `hors_d_atteinte` en donne la cause | `curl -s localhost:8011/health \| python3 -c "import json,sys; print(json.load(sys.stdin)['torch_device']['hors_d_atteinte'])"` |
| une recherche rend 500, `status: degraded` | `TORCH_DEVICE` nomme un périphérique non servi, ou le chargement a levé (mémoire, cache HF) | `docker logs rag-agent-api --tail 50` |
| une recherche rend 500, `status: ok` | la levée ne tient pas au périphérique | `docker logs rag-agent-api --tail 50` |
| tout est vert, rien n'est plus rapide | contention (§7) | `nvidia-smi` pendant une recherche |

## 10bis. Ce que l'agent prend sur la carte

À lire avant de dimensionner un voisin de carte : `--gpu-memory-utilization` du serveur d'inférence est une option de lancement.

```bash
curl -s http://localhost:8011/health | python3 -c "import json,sys; d=json.load(sys.stdin)['torch_device']; print('borne =', d['concurrence_max'], '| pic réservé =', d['pic_memoire_reservee_mio'], 'Mio')"
```

- `concurrence_max` : la borne `TORCH_MAX_CONCURRENCY` (défaut 4), nombre maximal de requêtes admises en même temps dans un étage torch. Au-delà, elles attendent.
- `pic_memoire_reservee_mio` : `torch.cuda.max_memory_reserved()`, avec trois pièges.
  1. C'est un maximum historique : l'allocateur ne rend rien (`mesuré` le 14 septembre 2026 : 1 294 Mio à 09:08 UTC, 1 984 à 09:28, même PID).
  2. `null` veut dire « aucun modèle chargé », pas zéro. Ne jamais dimensionner à ce moment-là.
  3. Il sous-estime ce que `nvidia-smi` attribue au processus, de la taille du contexte CUDA (`mesuré` le 14 septembre 2026 à 09:34 UTC : 1 036,0 Mio contre 1 262 MiB, 226 MiB d'écart).
- Il n'est lisible que par `/health` : un `docker exec … torch.cuda.max_memory_reserved()` démarre un autre processus et rend 0.

Réservation à rendre à un voisin de carte, `calculé` le 14 septembre 2026 depuis cinq paliers mesurés en régime chaud :

    réservation(N) = 1 362 Mio + (N - 1) x 68,0 Mio

À N = 4 : 1 566 Mio, arrondis à 2 048 Mio. Le chiffre ne vaut qu'une fois la borne en service et l'agent redémarré. Dérivation et réserves : §4.51 et §4.53 du [registre](axes_amelioration.md).

Chaque modèle n'est construit qu'une fois, sous un permis de la borne, mais les deux modèles ont chacun leur verrou et peuvent se désérialiser ensemble. `mesuré` le 14 septembre 2026 (4 `/search` + 4 `/sources` à froid, pic tous modèles confondus) :

| `TORCH_MAX_CONCURRENCY` | Pic de désérialisations simultanées | Constructions au total |
|---:|---:|---:|
| 1 | 1 | 2 |
| 4 (défaut) | 1 | 2 |
| 5 | 2 | 2 |
| 8 | 2 | 2 |

Ce tableau est le site canonique de ce chiffre. Le majorant qu'aucun réglage ne franchit est 2. Le surcoût transitoire d'une désérialisation n'est pas mesuré.

Coût de la borne quand elle mord, `mesuré` avec un étage de 70 ms : rien jusqu'à 4 requêtes simultanées, +625 ms sur la dernière servie à 40.

Relevé courant, `mesuré` le 27 septembre 2026 à 06:19 UTC (`nvidia-smi --query-compute-apps` croisé avec le cgroup du PID de chaque conteneur) : sur 23 034 MiB, le serveur d'inférence `vllm-central` tient 14 264 MiB, l'agent 1 460 MiB, un serveur d'inférence d'un autre projet du poste 4 468 MiB ; 2 355 MiB restent libres.

## 11. Prouver que le GPU est atteint

`cuda_available: true` dit que la carte est là, pas qu'elle sert. Trois preuves, et il en faut plus d'une :

1. `torch_device.embedding` et `.rerank` nomment `cuda` après une question ;
2. le journal du chargement nomme le périphérique demandé puis celui que torch a posé : `docker logs rag-agent-api 2>&1 | grep -i "périphérique"` ;
3. la mémoire prise sur la carte, seule preuve extérieure au programme : `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`, où le processus de l'agent apparaît à côté de celui du serveur d'inférence.
