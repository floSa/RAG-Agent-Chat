# Le moteur LLM relevé par l'agent

Ce que l'agent relève du serveur d'inférence qu'il interroge, où il le publie, comment une campagne s'en sert, et comment migrer un `.env` antérieur au moteur unique. Pour qui compare deux campagnes ou déploie l'agent. Site canonique de la clé `moteur_llm`.

## 1. Pourquoi ce relevé

Le nom du modèle demandé ne dit pas ce qui répond. Il reste identique quand le serveur d'en face est remplacé, mis à jour, ou sert un autre poids sous le même nom. L'agent relève donc le moteur réellement servi, le publie dans `GET /health` sous `moteur_llm`, et chaque campagne de `scripts/evaluate.py` le consigne à la racine de son artefact.

Seules les campagnes produites après ce relevé en portent un ; les campagnes archivées de `runs/` antérieures n'en portent pas et restent « muettes » (§5).

## 2. Les champs

| Champ | Fait ou réglage | Source |
|---|---|---|
| `serveur` | fait | la route de version qui répond |
| `endpoint` | fait, expurgé | l'URL réellement jointe, sans userinfo ni chemin |
| `version` | fait | `GET /version` |
| `modele_servi` | fait | `GET /v1/models`, confronté au modèle demandé |
| `fenetre_servie` | fait | `max_model_len` |
| `modele_demande` | réglage | `LLM_MODEL` |
| `options` | réglage | les cinq drapeaux d'appel de l'agent |
| `releve_le` | fait, sur l'agent | l'horloge de l'agent à l'instant du relevé, ISO-8601 UTC |

Le relevé est mémorisé pour la vie du processus après un premier succès complet (le serveur a dit son nom et ce qu'il porte). C'est le seul état de `/health` qui ne soit pas relancé à chaque battement : `releve_le` date donc le relevé, pas la lecture. Un relevé partiel est publié mais pas mémorisé, et se redemande au battement suivant. Un échec n'est jamais mémorisé.

Le relevé coûte au plus deux requêtes, toutes en lecture, et aucune génération.

## 3. Ce que le serveur rend

`mesuré` le 27 septembre 2026 à 06:19 UTC, `curl -s http://localhost:8011/health` :

```json
{"serveur": "vllm", "endpoint": "http://vllm-central:8000", "version": "0.28.0",
 "modele_demande": "google/gemma-4-E4B-it-qat-w4a16-ct",
 "modele_servi": "google/gemma-4-E4B-it-qat-w4a16-ct",
 "fenetre_servie": 32768,
 "options": {"thinking": false, "outils_natifs": true, "temperature": 0.1,
             "num_ctx": 32768, "max_tokens": 4096},
 "releve_le": "2026-09-27T05:54:09+00:00"}
```

`fenetre_servie` (la fenêtre du serveur) et `options.num_ctx` (le budget que l'agent s'autorise) sont deux grandeurs distinctes ; le défaut du code pour la seconde est 8192 ([llm.md](llm.md)).

Le catalogue `/v1/models` porte aussi `created`, `owned_by`, `root`, `parent` et un bloc `permission`. `created` et `permission[].id` sont régénérés à chaque requête (`mesuré` le 15 septembre 2026, deux lectures à 14 s d'écart) : ils ne sont pas relevés, et un test l'interdit, sinon deux relevés du même moteur différeraient.

## 4. Le relevé exige une réponse positive

`GET /version` doit rendre un champ `version` de type chaîne ; à défaut, `moteur_llm` vaut `null`, qui se lit « je n'ai pas pu lire ». Le relevé ne sait pas nommer un autre moteur que vLLM : il dit seulement que ce n'est pas le serveur attendu. Un code HTTP 200 n'est pas un fait.

Le modèle servi est cherché dans le catalogue, pas pris en première position. La relation d'appariement réduit les deux noms à leurs caractères alphanumériques minuscules et exige que le demandé soit un infixe du servi (`gemma4e4b` dans `googlegemma4e4bitqatw4a16ct`). Elle refuse un `id` qui porte, en segment entier, un mot de dérivation absent du nom demandé (`_MARQUEURS_DE_DERIVATION`, `src/api/main.py`).

## 5. Ce que `--compare` en dit

| Position | Quand | Ce qui est imprimé |
|---|---|---|
| `IDENTIQUE` | les deux signatures coïncident | `moteur LLM : IDENTIQUE des deux côtés — …` |
| `DIFFÉRENT` | les deux sont connues et diffèrent | les deux signatures et l'avertissement d'attribution |
| `MUET` | l'une au moins est inconnue | ce qu'on sait de chaque côté, et pourquoi |

- `IDENTIQUE` est imprimé : un garde qui ne parle que lorsqu'il mord ne se distingue pas d'un garde absent.
- `MUET` n'est pas `DIFFÉRENT` : on ne peut ni affirmer ni exclure une bascule.
- Un champ entre dans la signature si et seulement s'il est invariant pour un moteur donné et varie quand le moteur change. `fenetre_servie` y entre ; `releve_le` et `options` n'y entrent pas. Les options sont confrontées à part, sur leur propre ligne.
- `--compare` signale, il ne refuse pas : confronter deux moteurs est l'usage prévu. Un corpus différent (`empreinte_des_ancrages`), lui, reste un refus.

## 6. Les bornes connues

- **`DIFFÉRENT` est inatteignable sur deux poids servis sous le même `id`.** Aucune des sept routes GET de `vllm-central` ne porte de digest de poids (`mesuré` le 15 septembre 2026 en lecture seule : `/health`, `/load`, `/metrics`, `/ping`, `/v1/models`, `/v1/responses/{response_id}`, `/version`). Restent visibles le nom, qui porte la quantification sur cette instance, et la fenêtre servie.
- **La relation d'appariement a trois angles morts, mesurés par des tests** : une dérivation publiée sans mot de la liste est acceptée ; la forme réduite jette les frontières (`qwen2:5b` reconnu dans `Qwen/Qwen-2.5B-Chat`) ; deux quantifications publiées par l'éditeur sous son propre `id` ne se distinguent pas.
- **Un tag complet (modèle, taille, variante, quantification) n'est pas toujours reconnu** dans l'`id` servi. Le relevé reste alors partiel et se redemande à chaque battement : 2 requêtes par battement au lieu de 2 en tout, compté par `tests/unit/test_moteur_llm.py` et annoncé par un `warning` à chaque relevé non mémorisé.
- **Un serveur relancé pendant la vie de l'agent** est décrit par le relevé d'avant ; `releve_le` le rend visible. Le déploiement tourne un seul worker uvicorn (`mesuré` le 15 septembre 2026, `docker top`), donc un seul relevé à la fois.

## 7. Recettes

```bash
# Ce que l'agent publie
curl -s localhost:8011/health | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin).get('moteur_llm'), indent=2, ensure_ascii=False))"

# Ce qu'une campagne a consigné
python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('moteur_llm'))" runs/une-campagne.json

# L'âge du relevé publié
curl -s localhost:8011/health | python3 -c "
import datetime, json, sys
d = json.load(sys.stdin).get('moteur_llm') or {}
pris = d.get('releve_le')
print('relevé le', pris, '— il y a',
      datetime.datetime.now(datetime.UTC) - datetime.datetime.fromisoformat(pris)
      if pris else 'DATE ABSENTE')"

# Combien de campagnes du disque sont muettes
python3 -c "import json,glob; f=glob.glob('runs/*.json'); print(sum(1 for x in f if json.load(open(x)).get('moteur_llm') is None), 'muettes sur', len(f))"
```

## 8. Un seul moteur : la migration du `.env`

Depuis le lot 28 (18 septembre 2026), le code ne supporte qu'un moteur, vLLM : le réglage qui choisissait entre deux dialectes a été retiré avec le support de l'autre. Un `.env` écrit avant doit être migré avant de redéployer une image de cette époque ou plus récente.

<!-- migration-du-lot-28:début — SEUL bloc de ce fichier autorisé à nommer
     l'ancien moteur. Il porte les clés EXACTES à retirer d'un `.env` existant ;
     sans leurs noms, la migration est injouable. Le garde
     `test_le_nom_de_l_ancien_moteur_ne_revient_pas` borne cette exemption à ce
     bloc et rougit partout ailleurs dans ce fichier. -->

### La migration du `.env`, exacte

Elle se joue sur le `.env` du clone principal, qui n'est pas versionné. Garder une copie du fichier d'avant.

Retirer cinq clés, qui ne sont plus lues :

```
LLM_ENGINE
OLLAMA_HOST
OLLAMA_MODEL
VLLM_HOST
VLLM_MODEL
```

Ajouter deux clés, avec les valeurs de ce poste (celles que `VLLM_HOST` et `VLLM_MODEL` y portaient) :

```
LLM_HOST=http://vllm-central:8000
LLM_MODEL=google/gemma-4-E4B-it-qat-w4a16-ct
```

`Settings` est configuré en `extra="ignore"` : des clés anciennes laissées en place sont ignorées sans un mot, et des clés neuves absentes retombent sur les défauts du code. Vérifier après déploiement l'hôte réellement joint dans `GET /health`, champ `moteur_llm.endpoint`.

<!-- migration-du-lot-28:fin -->

Deux clés de `/health` ont changé de nom au même lot : le modèle demandé se lit sous `llm_model`, et la sonde du serveur sous `services.llm`. Le healthcheck de `docker-compose.yml` ne lit que le code HTTP ; un lecteur hors dépôt doit lire les nouveaux noms. Dans la capture d'usage, `config_json` porte `llm_model` ([capture_usage.md](capture_usage.md)).

Revenir à l'autre moteur n'est plus un réglage : c'est réétiqueter l'image d'avant la bascule et redéployer, ce qui ramène tout le code d'avant. La marche exacte, avec l'étiquette, est au §4 de [identite_du_code_servi.md](identite_du_code_servi.md).

Historique de la bascule et du retrait : lignes du lot 28 dans le [journal](pilotage_du_chantier.md) et banc go/no-go daté dans [audits/](audits/2026-09-15-banc-go-no-go-vllm.md).
