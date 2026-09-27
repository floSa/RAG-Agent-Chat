# L'état du projet

Ce qui marche, par quelle mesure on le sait, ce qui ne marche pas et ce qui n'est pas mesuré. Pour qui reprend le projet ou décide de la suite ; se lit seul.

Version livrée : étiquette git `v1.1.0`, code servi `a1f3036` (ligne 97 du [journal](pilotage_du_chantier.md)). Aucun chiffre n'est créé ici : chacun est repris de son site canonique, une section du [registre](axes_amelioration.md) ou une ligne du journal (§6.1), et le renvoi est écrit à côté. Quand deux sites mesurent une même grandeur autrement, les deux sont publiés avec leur définition. Les questions ouvertes sont ordonnées dans [prochaines_etapes.md](prochaines_etapes.md).

## 1. Ce qui marche

### 1.1 La chaîne répond, et le code servi est identifié

`mesuré` le 27 septembre 2026 à 06:19 UTC, `curl -s http://localhost:8011/health` (HTTP 200) : `status: ok`, les quatre dépendances à `true` (ChromaDB, NebulaGraph, index lexical, serveur d'inférence), `services_unknown` vide, moteur `vllm` `0.28.0` avec une fenêtre servie de 32768, `code_servi.etat: identifie` sur `a1f3036`, image construite le 27 septembre 2026 à 05:53:53 UTC. `/health` distingue le modèle demandé du modèle servi ([moteur_llm.md](moteur_llm.md)) et déclare `anonyme` une image non construite par `make image` ([identite_du_code_servi.md](identite_du_code_servi.md)).

### 1.2 La porte qualité est verte

`make lint` → `rc=0`, `make test` → `rc=0`, 1316 passés, mesurés par le pilote sur le résultat de la fusion du lot 43 (ligne 97 du journal). Le compte est celui que [tests.md](tests.md) annonce, et une garde le tient. La porte de la présente documentation est mesurée dans le [README](../README.md#porte-qualité).

### 1.3 Le rappel, sur les trois jeux

Trois jeux, qui ne mesurent pas la même chose :

| Jeu | Effectif | Ce qu'il sait mesurer |
|---|---|---|
| `golden_qa_generated.yaml`, réglage | 138 questions, dont 130 portent un ancrage, un seul chacune (§4.67) | Classer deux configurations ; aveugle à la sélection |
| `jeu_de_questions_pipeline.yaml`, contrôle | 30 questions, dont 26 portent 47 ancrages, 1 à 3 chacune (§4.67) | Contredire le générateur : écrit à la main, après l'ingestion |
| `jeu_ancrages_disperses.yaml`, dispersion | 60 questions, 120 ancrages (2 par question, 2 sections distinctes), 109 distincts (§4.76, ligne 88 du journal) | Voir le quatrième étage : une seule section reconstruite ne suffit pas |

**Le rappel au prompt, par `AUTO_SELECT_TOP_K`** (§4.67) : le contenu de l'ancrage est-il dans le markdown soumis au modèle ? Au défaut `k = 3` :

| Jeu | Rappel au prompt | IC 95 % (Wilson) | Questions | Ancrages |
|---|---|---|---|---|
| réglage (130 q) | 0,9538 | [0,903 – 0,979] | 124 | 124/130 |
| contrôle (26 q) | 0,7308 | [0,539 – 0,863] | 19 | 26/47 |

Sur le jeu de réglage, `k=1 → k=2` gagne 4 questions sans en perdre, et toutes les autres transitions rendent +0, −0. Sur le contrôle, de 3 à 6 : +1 question sur 26 et +2 ancrages sur 47 ; de 3 à 10 : +2 questions et +7 ancrages. Les intervalles se recouvrent : un écart de deux points est du bruit. Sur les huit transitions des deux jeux, aucun ancrage et aucune question n'est perdu quand `k` monte, borné à ces huit transitions, ces deux jeux, cette campagne.

**Le jeu dispersé : questions dont tous les ancrages arrivent** (§4.76, ligne 88 du journal). De `k=1` à `k=10` : 0, 2, 6, 7, 7, 7, 8, 8, 9, 10, soit +10 gagnées, 0 perdue. Le même banc sur le jeu de réglage rend +0 à toutes les bascules après k=2 : le plateau était une propriété du jeu. Éléments au prompt en moyenne : 33,48 à k=3, 102,5 à k=10.

**Ancrages dans le top-10 du reranker, variante de production `unique_avec_traduction`** (§4.79), ancrages / questions complètes : dispersé 53 / 7 (60 q, 120 anc.), contrôle 33 / 14 (26 q, 47 anc.), réglage 127 / 127 (130 q, 130 anc.).

### 1.4 Le plafond de récupération est la requête

Site canonique : §4.77. Le plafond n'est ni l'index, ni la profondeur seule, ni le reranker : c'est la requête. À profondeur de production (`FETCH_K=50`, `RETRIEVAL_TOP_K=50`, `RERANK_TOP_K=10`), le banc retrouve 56 / 46 / 67 ancrages absents du dense, de la fusion et du top-10 du reranker, les chiffres du §4.76 à l'unité ; les 120 triplets de rangs sont identiques un à un.

| Profondeur | Ancrages au top-10 du reranker / 120 |
|---|---|
| 50 (production) | 53 |
| 200 | 64 |
| 1000 | 62 |

- L'index est hors de cause : 109/109 ancrages indexés, 0 émietté, 109/109 portent leur preuve.
- La profondeur est réelle et bornée : +11 de 50 à 200, −2 de 200 à 1000.
- L'oracle `preuve` ramène 120/120 : aucun ancrage n'est hors d'atteinte du classement, borné à ce jeu et à cette campagne.

Le tableau des causes somme à 120 : arrive 53, écarté par le reranker 21, profondeur qui récupère 13, profondeur insuffisante 31, requête unique 2, hors base vectorielle 0, texte indexé 0, non expliqué 0.

### 1.5 La décomposition de la requête, mesurée

Sites canoniques : §4.78 (sans traduction) et §4.79 (avec). La question est découpée en au plus trois sous-questions par le modèle, qui ne voit ni les passages ni le nombre de besoins ; chaque sous-question passe par la récupération de production ; les listes sont fondues par le `fuse` de `src/` au même `RRF_K` ; le reranker score contre la question entière ou par sous-question, chaque candidat gardant son meilleur score.

Ancrages / questions complètes (§4.79) :

| Variante | Dispersé | Contrôle | Réglage |
|---|---|---|---|
| `unique_avec_traduction` (production) | 53 / 7 | 33 / 14 | 127 / 127 |
| `unique_sans_traduction` (base appariée) | 57 / 6 | 33 / 14 | 125 / 125 |
| `fusion_rerank_entiere` | 60 / 8 | 33 / 14 | 124 / 124 |
| `fusion_rerank_sous_questions` | 72 / 19 | 33 / 14 | 124 / 124 |
| `fusion_traduite_rerank_entiere` | 59 / 6 | 33 / 14 | 125 / 125 |
| `fusion_traduite_rerank_sous_questions` | 72 / 18 | 33 / 14 | 125 / 125 |
| `fusion_question_traduite_decomposee` (l'autre ordre) | 73 / 19 | 33 / 14 | 127 / 127 |
| oracle `decomposition` du §4.77 (borne) | 86 / 28 | — | — |

1. Le gain sur le jeu visé est réel : 7 → 19 questions complètes, soit 68 % de la borne de l'oracle (§4.78), et c'est le reranking par sous-question qui décide (+11 à liste fusionnée identique).
2. La traduction ne gagne rien sur le jeu dispersé, monolingue anglais, mais ferme presque toute la perte du jeu de réglage : 125 contre 124, et 127 pour l'autre ordre, le chiffre de la production (§4.79).
3. L'écart à la borne n'est pas 28 − 19 = 9 : c'est 11 manquées et 2 gagnées hors borne, dont 6 à la fusion, 4 au reranking, 1 jamais récupérée (§4.79, qui corrige l'imputation du §4.78 sur `G-119`).

### 1.6 Les coûts, mesurés

**`AUTO_SELECT_TOP_K` de 3 à 6** (§4.66, six questions distinctes, `prompt_tokens_reliable` vrai aux douze appels) : prompt médian 2358 → 4224 jetons, durée totale médiane 9 712 → 13 970 ms (+44 %), citations cumulées 34 → 55 (en hausse 6 fois sur 6). Le budget n'écarte rien, ni à 3 ni à 6 : le plus gros prompt mesuré vaut 4849 jetons contre une fenêtre servie de 32768, soit 15 %.

**La décomposition** (§4.78, ligne 90 du journal, et §4.79) :

| | Médiane | p95 |
|---|---|---|
| Appel de décomposition (§4.79, les trois jeux) | 826 – 1322 ms | 1734 – 2338 ms |
| Traduction d'une sous-question (§4.79) | 429 – 587 ms | 996 – 1029 ms |
| Récupération des sous-questions + fusion, jeu dispersé (§4.79) | 102 ms (contre 177 ms en production) | 1130 ms |
| Reranking par sous-question, jeu dispersé, en `cpu` (§4.79) | 1322 ms (contre 704 ms sur la question entière) | 4105 ms |

Le prix est en paires scorées (§4.79) : le reranking par sous-question coûte ×1,60 à ×2,03 selon le jeu, l'autre ordre ×2,51 à ×4,03. La variante traduite ne coûte pas une paire de plus que celle du §4.78.

### 1.7 La réingestion du pipeline est vérifiée conforme

Site canonique : la ligne « LE VERDICT D'APRÈS LA CAMPAGNE DU PIPELINE » du journal, entre les lignes 90 et 91. `mesuré` le 25 septembre 2026 à 06:17 UTC, après la purge et la réingestion menées par le pipeline :

| Contrôle | Avant (25 sept., 00:32–00:33 UTC) | Après (06:17 UTC) |
|---|---|---|
| `POST /reindex` | — | 4367 chunks indexés |
| `make verifier-les-ancrages` | `rc=0`, 0 désaccord | `rc=0`, 0 désaccord |
| Ancrages présents dans le graphe et dans la base vectorielle | 130/130, 44/44, 109/109, soit 267 distincts | identiques |
| Clés d'objets médias | 212, SHA-256 `c91f5be6e24fbcba…` | identiques |
| Graphe | 23 `Document`, 15 173 arêtes `PARENT_OF` distinctes | identiques |

Le pipeline date la fin de sa réingestion à 03:50:41 UTC (23 runs `SUCCESS`, `comparer` 23/23, 0 `element_id` déplacé) : le relevé de 06:17 lui est postérieur et vaut verdict.

### 1.8 Les incidents traités

| Incident | Effet | Correction | Sites |
|---|---|---|---|
| Session NebulaGraph périmée après une purge du graphe | Le proxy `/media` rendait 404 sur toutes les images pendant que `/health` restait vert ; `nebula3` rend un résultat en échec au lieu de lever | Réouverture de la session et nouvel essai, une fois, sur cette seule erreur ; la sonde de `/health` lit un tag | §4.80, §4.81, ligne 94 du journal |
| Fichier `-wal` supprimé entre `exists()` et `stat()` | `/health` publiait 0 interaction et 0 octet pour une base pleine, et `failures` montait définitivement | `FileNotFoundError` rattrapé sur ce seul `stat()` | §4.75, ligne 87 du journal |
| Bascule du stockage objet chez le pipeline | Champs médias renommés dans les stores | Lecture de `media_url` et `object_key`, puis retrait de toute trace de l'ancien nom | §4.82, §4.83, lignes 95 à 97 du journal |

Après le déploiement de la version servie, une vraie question rend son image sous `media_url`, et `GET /media/…` rend 200 avec des octets identiques (ligne 97 du journal).

## 2. Ce qui ne marche pas, ou n'est pas mesuré

### 2.1 La décomposition est mesurée, pas implémentée

C'est le point le plus important de ce document. Les §4.78 et §4.79 sont des bancs : ils appellent `retrieve`, `fuse` et `rerank` de `src/` tels quels et relèvent un rang. `src/` n'est pas touché (lignes 90 et 91 du journal), et les deux sections se terminent par la même phrase : le lot ne propose aucun réglage et ne recommande rien. L'agent servi ne décompose pas les questions : le 7 du §1.5 est ce qu'il rend ; le 19 est ce qu'il rendrait si le code existait.

### 2.2 Aucune réponse n'est jugée en qualité

Borné à tout ce qui est publié aux §4.66 à §4.79 : aucun banc ne juge une réponse. Un ancrage au top-10 n'est pas une bonne réponse (§4.79, réserve 1) ; plus de citations n'est pas une meilleure réponse (§4.66), raison écrite pour laquelle `AUTO_SELECT_TOP_K` reste à 3 ; le §4.77 conclut qu'aucun coût n'est mesuré et qu'aucune réponse n'est jugée (ligne 89 du journal). Il n'existe dans ce dépôt ni jeu de réponses de référence, ni juge, humain ou modèle.

### 2.3 Le banc tourne en `cpu`, le service en `cuda`

Tenu délibérément identique aux §4.76 à §4.79, pour que les chiffres se comparent. Les poids des deux modèles ont été sortis du conteneur servi et confrontés octet pour octet à ceux du lot précédent (`diff -rq`, aucun écart). Ce qu'un écart d'arrondi flottant déplacerait dans l'ordre du reranking n'est pas mesuré (§4.79). Les coûts du §4.79 disent combien de paires chaque variante ajoute, pas ce qu'elles coûteraient sur GPU ; le §4.78 relève un p95 de 8 483 ms en `cpu` pour le reranking par sous-question.

### 2.4 Les jeux ne sont pas relus, et le dispersé est monolingue

- 190 questions sur 228 portent `reviewed: false` : 130 des 138 du jeu de réglage et les 60 du jeu dispersé. Les 30 du jeu de contrôle et 8 du jeu de réglage sont relues (`mesuré` par `yaml.safe_load` le 25 septembre 2026, ligne 93 du journal).
- Le jeu dispersé est monolingue anglais, sans que ce soit voulu (§4.76) : le générateur tirait 30 % de questions françaises, le jeu en porte 0 sur 60. Le garde de vocabulaire partagé exige deux jetons communs avec chacun des deux passages anglais, ce qu'une question française n'a pas. L'axe translinguistique est donc hors de portée de ce jeu.
- La circularité est déplacée, pas supprimée (§4.76) : 30 ancrages sur 120 sortent au rang 1 du reranker, et le juge de non-suffisance est le modèle qui a écrit la question. Les sous-questions des §4.78 et §4.79 sont écrites par ce même modèle (§4.79, réserve 3).
- 60, 130 et 26 questions ne tranchent pas un réglage (§4.79, réserve 8).

### 2.5 Le corps vide arrive au prompt

Site canonique : §4.71, à lire en entier ; il porte deux corrections datées, et sa première lecture y était fausse. Le chiffre à citer est celui du 24 septembre 2026 à 15:02 UTC, dans le conteneur servi : `reconstruct_section` sur les 172 ancrages distincts des deux jeux rend 148 sections uniques, 0 échec, et 1 751 éléments, dont 20 `code` vides sur 152 et 26 `list_item` vides sur 289.

Une puce vide rend une chaîne vide et disparaît du markdown ; un `code` vide rend un bloc vide suivi d'un marqueur `[src:ID]` citable qui ne cite rien, 20 sur 1 698 marqueurs. Les deux prennent une place de la fenêtre, comptée en éléments avant le rendu : 46 places sur 1 751.

Retirés par le site lui-même, à ne pas reprendre : les « 37 pertes sèches » sur les puces vides n'existent pas (les 202 puces vides n'ont aucun enfant, leur texte vit dans 727 fragments frères et arrive déjà au prompt ; les 15 173 arêtes `PARENT_OF` partent toutes d'un `SectionHeader`, 15 007, ou d'un `Document`, 166) ; les sommets `Code` vides sont des lignes blanches entre deux lignes de code (0 perte sèche prouvée sur 1 362). La réparation juste filtrerait avant le fenêtrage ; son coût mesuré ne justifiait pas un lot à la date du site, et ce que le modèle fait d'un bloc vide n'est pas mesuré. La fonction concernée est `_restore_full_text` (`src/agent/graph_context.py`).

### 2.6 Les non bloquantes des audits, encore ouvertes

L'audit du lot 34 a rendu sept non bloquantes (§4.74) ; le lot 35 a fermé la seule qui nommait une sortie fausse (constat E, §4.75). Restent ouvertes, toutes de méthode :

- **A** : une mesure étiquetée `mesuré` sans date dans un commentaire de `src/api/main.py` ;
- **B** : un « n'a jamais été atteinte sans injection » non borné au même site (remesuré par l'audit : 0 sur 250) ;
- **C** : les bancs des tableaux de coût du §4.74 sont hors dépôt et ne se rejouent pas ;
- **D** : la barrière du lot 33 n'est défendue que par son propre garde ;
- **F** : `grep -rn '_sonder\b'` rend 58 lignes à cause d'une fixture homonyme ; les appelants de production sont 5 ;
- **G** : un détecteur de résidus mal posé rend des chiffres faux dans les deux sens.

Le §4.75 laisse la fenêtre du `-wal` jamais atteinte sans injection : ni par l'audit 34 (4000 appels contre 32 957 fermetures concurrentes), ni par le lot 35.

### 2.7 Les réglages que rien ne tranche

- `AUTO_SELECT_TOP_K` reste à 3 : le coût de 6 est connu et modéré, le gain ne l'est pas (§4.66, §4.76).
- La profondeur reste à 50 : +11 ancrages au top-10 à 200, sans coût mesuré (§4.77).
- `TRANSLATION_WEIGHT` vaut 1,0 : l'effet d'un poids moindre n'est pas mesuré (§4.79, réserve 6).

### 2.8 Jusqu'à quand ces mesures valent

Les mesures décrivent l'état des stores du 25 septembre 2026, 4367 chunks (§4.79, réserve 9). Les empreintes d'avant la bascule du stockage objet sont versionnées dans [references/](references/2026-09-22-cles-medias.md), et le verdict du §1.7 dit que la réingestion les a rendues identiques. Une nouvelle réingestion impose de rejouer `make verifier-les-ancrages` avant toute mesure.

## 3. En une phrase

La chaîne fonctionne et son plafond est nommé (la requête, pas l'index) ; son levier le plus fort est chiffré et non implémenté (la décomposition, 7 → 19 questions complètes sur le jeu dispersé) ; aucune réponse n'a encore été jugée.
