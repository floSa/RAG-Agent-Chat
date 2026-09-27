# Quel code tourne, et comment revenir en arrière

Comment savoir quel commit le conteneur `rag-agent-api` exécute, comment construire et déployer une image identifiée, et comment revenir à l'image précédente. Pour qui déploie l'agent ou compare une campagne à un commit.

Une étiquette, une image et un conteneur sont trois choses différentes. Une étiquette peut désigner une autre image que celle que son nom suggère : trancher toujours par le conteneur, jamais par une étiquette.

## 1. Ce que l'image porte

`Dockerfile.agent` grave l'identité du code deux fois :

| Chemin | Lu par | Intérêt |
|---|---|---|
| `ENV RAG_AGENT_CODE_*` | `src/api/identite_du_code.py`, publié par `GET /health` | Lisible sans accès au démon Docker |
| `LABEL org.opencontainers.image.revision` et voisins | `docker image inspect` | Figé à la construction, l'exécution ne peut pas le contredire |

Un désaccord entre les deux signale une variable `RAG_AGENT_CODE_*` posée dans le `.env`, qui surcharge l'`ENV` à l'exécution (§5).

`/health` publie sous `code_servi` un état parmi trois :

| `etat` | Signification | Conduite |
|---|---|---|
| `identifie` | Sha gravé au build, arbre de construction propre | Comparer une campagne à ce commit |
| `arbre_sale` | Sha présent, mais l'arbre portait des modifications non commitées | Ne pas comparer ; reconstruire depuis un arbre propre |
| `anonyme` | Aucun sha fiable ; `avertissement` dit pourquoi | Construire par `make image` |

Les `ARG` de `Dockerfile.agent` n'ont aucune valeur par défaut : une image construite sans eux se déclare `anonyme` et ne peut pas passer pour identifiée. Gardes : `tests/unit/test_identite_du_code.py`.

## 2. Savoir ce qui tourne

```bash
docker inspect -f '{{.Image}}' rag-agent-api
```

L'image que le conteneur exécute réellement. C'est le seul fait ; le reste en dérive.

```bash
docker image inspect -f '{{range .RepoTags}}{{println .}}{{end}}' "$(docker inspect -f '{{.Image}}' rag-agent-api)"
```

Toutes les étiquettes de cette image. Aucune ligne : un `docker build` qui reprend `latest` la rendrait irrécupérable.

```bash
curl -s http://localhost:8011/health | python3 -m json.tool
```

Le port hôte est 8011 ; 8000 est le port interne du conteneur.

`mesuré` le 27 septembre 2026 à 06:31 UTC : image `sha256:3eaf733ef1c2…`, étiquetée `latest` et `v1.1.0`, label `a1f3036c2eaf19ef8370db7e11ba94ff79cc647d` ; `/health` publie `code_servi.etat: identifie`, même sha, `construite_le: 2026-09-27T05:53:53Z`.

## 3. Construire une image identifiée

```bash
make image
```

Depuis le clone principal, où vivent `.env` et `prompts/`. La cible relève le sha et la propreté de l'arbre, puis appelle `docker compose build agent-api`. Elle ne démarre rien : construire et déployer sont deux gestes. Tout autre chemin (`docker compose build` nu, `docker build` à la main) produit une image `anonyme`.

La ligne `transferring context: …` du build n'est pas la taille du dépôt : BuildKit ne transfère que les chemins que les `COPY` réclament (`requirements.txt`, `src/agent`, `src/api`), et seulement le delta depuis le build précédent. Il n'existe pas de `.dockerignore` ; il deviendrait nécessaire le jour où un `COPY . .` apparaîtrait.

## 4. Redéployer, et pouvoir revenir

Étiqueter l'image servie avant tout autre geste : une fois `latest` repris par une image neuve, l'ancienne n'a plus de nom.

```bash
# (a) Ce qui sert maintenant, tranché par le conteneur.
SERVI="$(docker inspect -f '{{.Image}}' rag-agent-api)"
NOM="$(docker inspect -f '{{.Config.Image}}' rag-agent-api)"
echo "$NOM sert $SERVI"
```

```bash
# (b) L'étiqueter avant de construire. L'étiquette est capturée une fois,
#     jamais recalculée : deux date -u peuvent tomber de part et d'autre de minuit.
ETIQUETTE="$NOM:$(date -u +%Y-%m-%d)-avant-redeploiement"
docker image tag "$SERVI" "$ETIQUETTE"
echo "$ETIQUETTE"   # à noter : c'est le chemin du retour
```

```bash
# (c) Vérifier à quoi l'étiquette pend. La sortie doit être identique à $SERVI ;
#     sinon, s'arrêter.
docker image inspect -f '{{.Id}}' "$ETIQUETTE"
```

```bash
# (d) Construire : le sha et la propreté de l'arbre entrent dans l'image.
make image
```

```bash
# (e) Déployer sans reconstruire.
docker compose up -d --no-build agent-api
```

```bash
# (f) Vérifier ce qui tourne, par le conteneur.
curl -s http://localhost:8011/health | python3 -c 'import json,sys; print(json.load(sys.stdin).get("code_servi", "CLÉ ABSENTE : agent antérieur à l identité du code"))'
```

Attendu : `etat: "identifie"` et le sha du commit déployé. Un `anonyme` ici signifie que le build n'est pas passé par `make image` : refaire le déploiement.

Ce que le geste (e) fait, `mesuré` le 16 septembre 2026 : `rc=0` en 3 s, le conteneur est recréé (identifiant et PID neufs, `RestartCount` à 0), rien n'est reconstruit, `latest` ne bouge pas, `rag-frontend` n'est pas touché, et le service redevient `healthy` en 21 s. Le frontend est un service distinct, `frontend`, que ce geste ne reconstruit pas.

### Revenir

```bash
NOM="$(docker inspect -f '{{.Config.Image}}' rag-agent-api)"
ETIQUETTE="<celle que (b) a affichée, recopiée telle quelle>"

# Vérifier d'abord à quoi elle pend, puis seulement la faire servir.
docker image inspect -f '{{.Id}}' "$ETIQUETTE"
docker image tag "$ETIQUETTE" "$NOM:latest"
docker compose up -d --no-build agent-api

# Contrôler par le conteneur : l'identifiant doit être celui relevé en (a).
docker inspect -f '{{.Image}}' rag-agent-api
```

Chaque ligne est éprouvée séparément ; leur enchaînement complet n'a jamais été joué, aucun retour arrière n'ayant été nécessaire. La dernière commande est celle qui dit si le retour a eu lieu.

Étiquettes de retour présentes sur ce poste, `mesuré` le 27 septembre 2026 à 06:31 UTC :

| Étiquette | Image | Code (label) | Construite le |
|---|---|---|---|
| `rag-agent-chat-agent-api:2026-09-27-avant-lot43` | `sha256:1f85bd880764…` | `3f7203f` | 2026-09-25T13:34:52Z |
| `rag-agent-chat-agent-api:2026-09-17-avant-bascule-vllm` | `sha256:48b00a43e150…` | `b7337a3` | 2026-09-16T13:39:21Z |

La seconde est la seule façon de revenir à l'ancien moteur d'inférence : le code courant n'en porte plus le support. Revenir sur elle ramène tout le code du 16 septembre 2026, pas seulement le moteur.

<!-- migration-du-lot-28:début — ce paragraphe nomme les trois clés que le
     retour arrière vers l'ancien moteur doit RESTAURER dans le `.env`. Sans
     leurs noms exacts, le geste est injouable. Le garde
     `test_le_nom_de_l_ancien_moteur_ne_revient_pas` borne cette exemption à ce
     bloc et mord partout ailleurs dans ce fichier. -->

Ce retour-là se joue en deux temps. L'image d'avant la bascule lit `LLM_ENGINE`, `OLLAMA_HOST` et `OLLAMA_MODEL`, que la migration du `.env` a retirées ([moteur_llm.md](moteur_llm.md), « La migration du `.env`, exacte »). Sous un `.env` migré, elle retomberait sur ses défauts sans un mot. Restaurer d'abord ces trois clés dans le `.env` du clone principal, depuis la copie d'avant la migration, puis réétiqueter et redéployer.

<!-- migration-du-lot-28:fin -->

## 4 bis. La propreté de l'arbre compte des fichiers qui n'entrent pas dans l'image

`make image` grave `arbre=sale` dès que `git status --porcelain` rend une ligne, fichiers non suivis compris. Or l'image ne copie que `requirements.txt`, `src/agent` et `src/api` : un fichier non suivi ailleurs ne change pas l'image mais la fait déclarer `arbre_sale`.

Cas courant : un outillage qui pose des arbres de travail dans un répertoire caché du clone principal. L'exclure dans `.git/info/exclude` (local, non versionné) avant le premier `make image`, par un motif étroit qui ne masque que ce répertoire. Contrôle positif avant de construire : un fichier témoin créé à la racine doit ressortir dans `git status --porcelain`.

La correction durable serait de restreindre la sonde aux chemins que les `COPY` réclament (`git status --porcelain -- requirements.txt src/agent src/api`) ; elle touche le `Makefile` et relève d'un lot avec sa garde.

## 5. Quand `/health` et le label divergent

```bash
SERVI="$(docker inspect -f '{{.Image}}' rag-agent-api)"
docker image inspect -f 'label={{index .Config.Labels "org.opencontainers.image.revision"}}' "$SERVI"
curl -s http://localhost:8011/health | python3 -c 'import json,sys; print("env  =", (json.load(sys.stdin).get("code_servi") or {}).get("sha"))'
```

Les deux doivent concorder. S'ils diffèrent, l'`ENV` a été surchargé à l'exécution, presque toujours par une variable `RAG_AGENT_CODE_*` du `.env` : le label dit ce que le build a gravé. Retirer la variable et recréer le conteneur.

## 6. Ce que ce mécanisme ne dit pas

- **Les dépendances.** Deux images d'un même sha construites à des dates différentes n'embarquent pas les mêmes roues ; `construite_le` les sépare.
- **La preuve du contenu.** Il rapporte ce que le build a déclaré. La seule preuve indépendante est de comparer le contenu du conteneur au dépôt, fichier par fichier au SHA-256 :
  ```bash
  docker cp rag-agent-api:/app/src /tmp/servi
  ```
  Doubler un « tout est identique » d'un contrôle positif (un octet ajouté, un fichier retiré doivent rougir).
- **La surveillance.** Il publie ; c'est à la campagne appariée, au pipeline et à l'exploitant de refuser de comparer deux mesures qui ne viennent pas du même code.

Historique des déploiements et de leurs vérifications : lignes du [journal](pilotage_du_chantier.md), §6.1.
