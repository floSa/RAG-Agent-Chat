# Les prochaines étapes, ordonnées par le coût de l'échec

Les questions ouvertes du projet, ce qu'il faudrait mesurer pour trancher chacune, et dans quel ordre. Pour qui choisit le prochain lot.

L'ordre n'est pas celui du gain : il classe par ce que coûte de se tromper (§4.71 du [registre](axes_amelioration.md) : ordonner par le coût de l'échec, pas par la taille du pourcentage). Une question dont l'échec invalide tout le reste passe devant une question dont l'échec coûte onze ancrages. Chaque chiffre renvoie à sa section du registre ou à une ligne du [journal](pilotage_du_chantier.md) (§6.1). Chaque estimation d'effort porte l'étiquette `supposé` : ce sont des suppositions, jamais des chiffres du chantier.

## 1. Juger la qualité des réponses

**Sites** : aucune section ne la porte, et c'est le sujet. Elle est nommée comme manquante aux §4.66, §4.77 (ligne 89 du journal), §4.78 (ligne 90) et §4.79 (réserve 1).

**Le chiffre** : zéro. Aucune réponse n'est jugée, ni par un humain, ni par un modèle, ni contre un jeu de réponses de référence, qui n'existe pas.

**Pourquoi en tête** : tout ce que le chantier mesure est une procuration ; un ancrage au top-10 n'est pas une bonne réponse (§4.79). Si la procuration ne prédit pas la qualité, le plafond du §4.77, le +12 du §4.78 et la répartition par étage du §4.79 ne disent rien de ce qui intéresse un lecteur. C'est la seule question dont l'échec rend les sept autres sans objet.

**À mesurer** :

1. un jeu de réponses de référence, distinct des jeux d'ancrages, écrit à la main sur un sous-ensemble des trois jeux, pas par le modèle qui a écrit la question (§4.79, réserve 3) ;
2. la corrélation entre « les ancrages sont au prompt » et « la réponse est juste », sur ce sous-ensemble, avant tout jugement en masse ;
3. ensuite seulement, un protocole de jugement, humain d'abord.

**Effort, `supposé`** : deux lots. Le premier décide : si la procuration tient, le reste du chantier est validé ; sinon l'ordre ci-dessous change entièrement.

## 2. Faire relire les jeux par un humain

**Sites** : §4.67, §4.76, §4.79 réserve 8 ; ligne 93 du journal.

**Les chiffres** : 190 questions sur 228 portent `reviewed: false` (130 des 138 du jeu de réglage, les 60 du jeu dispersé ; les 30 du contrôle et 8 du réglage sont relues). Sur le jeu dispersé, 30 ancrages sur 120 sortent au rang 1 du reranker, et le juge de non-suffisance est le modèle qui a écrit la question (§4.76). 4 paires rejetées par la condition de reconstruction sur 139 examinées, 8 par la non-suffisance, 67 par les gardes lexicaux (§4.76).

**Pourquoi ici** : une question mal écrite ne rend pas un résultat faux mais un résultat plausible et faux, qui ne se voit pas. Les trois jeux sont le dénominateur de tous les chiffres de [etat_du_projet.md](etat_du_projet.md).

**À mesurer** : le taux de désaccord entre un relecteur humain et les conditions automatiques, sur un échantillon tiré au sort des trois jeux. Au-delà de quelques pour cent, les intervalles de confiance du §4.67 sont trop étroits.

**Effort, `supposé`** : un lot pour le protocole et l'échantillon, puis du temps humain hors chantier. Corollaire connu : le jeu dispersé est monolingue anglais, 0 question française sur 60 (§4.76) ; l'axe translinguistique n'a pas de jeu.

## 3. La décomposition de requête, et sa traduction

**Sites** : §4.78, §4.79 ; lignes 90 et 91 du journal.

**Les chiffres** : jeu dispersé, questions complètes sur 60 : production 7, `fusion_rerank_sous_questions` 19, variante traduite 18, autre ordre (question traduite puis décomposée) 19 ; borne de l'oracle 28, soit 68 % de la borne atteints (§4.78). Jeu de réglage : 127 en production, 124 sans traduction, 125 avec, 127 pour l'autre ordre. Jeu de contrôle : 14 partout.

L'écart à la borne n'est pas 28 − 19 = 9 : c'est 11 manquées et 2 gagnées hors borne, dont 6 à la fusion, 4 au reranking, 1 jamais récupérée. Réparti par étage sur les 120 ancrages du jeu dispersé (§4.79) :

| Variante | `arrive` | perdu au `rerank` | perdu à la `fusion` | `jamais` |
|---|---|---|---|---|
| `fusion_rerank_sous_questions` | 72 | 12 | 11 | 25 |
| `fusion_traduite_rerank_sous_questions` | 72 | 13 | 8 | 27 |
| `fusion_question_traduite_decomposee` | 73 | 9 | 18 | 20 |

La fusion coupée à 50 est un étage qui perd, d'autant plus qu'on fond de sous-requêtes : `G-119` est perdue à la fusion, au rang 49 d'une sous-requête (§4.79, qui corrige l'imputation du §4.78).

**Pourquoi ce rang et pas le premier** : le gain est le plus gros du chantier, mais l'échec est visible et réversible, sur les jeux de contrôle et de réglage appariés. Contre la production, le bilan du §4.78 est +12 sur le jeu visé et −3 hors de lui, et le §4.79 montre que la traduction ferme presque toute cette perte.

**À mesurer** :

1. ce que coûte la fusion coupée à 50 quand on fond des sous-requêtes (6 à 18 ancrages perdus là) ;
2. les poids : les sous-requêtes sont fondues à poids égaux, choix déclaré (§4.78) ;
3. le coût en `cuda` (§4 ci-dessous) ;
4. le 127 de l'autre ordre repose en partie sur une panne du producteur (`G-024`), et ce qu'il rendrait sans elle n'est pas mesuré (§4.79, réserve 2).

**Effort, `supposé`** : un lot de mesure pour (1) et (2), puis un lot d'implémentation dans `src/` si la mesure tient. L'implémentation est bornée : `retrieve(requête, translation=…)` est exactement l'appel que `graph.py` émet, seul le texte donné change (§4.79).

## 4. L'écart `cpu` / `cuda`

**Sites** : §4.79 (« L'environnement » et réserve 7), même écart aux §4.76 à §4.78.

**Les chiffres** : le service tourne en `cuda` (`/health` publie `torch_device.requested: cuda`, `cuda_available: true`, torch `2.14.0+cu130`, `mesuré` le 27 septembre 2026 à 06:19 UTC). Les quatre bancs tournent en `cpu`, avec les mêmes poids, confrontés octet pour octet (§4.79). Ordre de grandeur : `rerank_ms` p50 de 58 ms sur GPU pour 50 paires (§4.47, cité par le §4.77), contre une médiane de 704 ms pour le reranking sur la question entière en `cpu` (§4.79).

**Pourquoi l'échec coûte cher** : les arbitrages de coût du chantier reposent sur des latences `cpu`. Un facteur dix mal placé peut inverser une décision : le §4.78 ne recommande pas le reranking par sous-question, dont le p95 vaut 8 483 ms en `cpu`. L'écart touche aussi la justesse : ce qu'un écart d'arrondi déplacerait dans l'ordre du reranking n'est pas mesuré.

**À mesurer** : rejouer un banc versionné sur GPU (le contrôle positif du §4.77, dont les 120 triplets de rangs sont publiés) et confronter rang par rang, puis relever les latences des mêmes étages.

**Effort, `supposé`** : un demi-lot. Il manque un environnement GPU pour le banc, sur une carte que le service occupe déjà ([gpu_cuda.md](gpu_cuda.md), §10bis).

## 5. Le reranker face à une question à deux besoins

**Site** : §4.77, question ouverte 3.

**Le chiffre** : 52 ancrages sont dans la fusion et n'atteignent jamais son top-10, alors que l'oracle `preuve` les y met tous les 52. Ce n'est pas une incapacité à scorer.

**Pourquoi ici** : l'échec est borné et connu ; c'est le même geste que le §3 vu du quatrième étage, et le reranking par sous-question rend +11 à liste fusionnée identique (§4.78). Reste inexpliqué pourquoi le cross-encoder préfère un passage tiède sur deux besoins à un passage parfait sur un seul.

**À mesurer** : un reranking par segment de la question sans décomposition par le modèle (par proposition, par clause) ; la tenue du choix du maximum plutôt que de la moyenne hors du jeu dispersé.

**Effort, `supposé`** : compris dans le lot de mesure du §3 si on le lui rattache, un lot à part sinon.

## 6. La profondeur `50 → 200`

**Site** : §4.77, question ouverte 2.

**Les chiffres** : à seuil constant, top-10 du reranker : 53 ancrages sur 120 à profondeur 50, 64 à 200, 62 à 1000. +11 de 50 à 200, −2 de 200 à 1000. Deux variables d'environnement, pas une ligne de code.

**Pourquoi si bas, alors que c'est le moins cher à faire** : l'échec est un coût continu et silencieux, payé à chaque requête. Le cross-encoder scorerait 200 paires au lieu de 50, et c'est déjà l'étage le plus cher (§4.77, citant le §4.47). Le +11 n'est établi que sur un jeu.

**À mesurer** : le prix à 200 paires par requête, en `cuda`, donc après le §4 ; la tenue du +11 sur les deux autres jeux.

**Effort, `supposé`** : un demi-lot de mesure.

## 7. Filtrer les corps vides avant le fenêtrage

**Site** : §4.71, à lire en entier : il porte deux corrections datées qui retirent ses premières conclusions.

**Les chiffres** (`mesuré` le 24 septembre 2026 à 15:02 UTC, dans le conteneur servi) : sur 172 ancrages distincts, 148 sections reconstruites, 1 751 éléments rendus, dont 20 `code` vides sur 152 et 26 `list_item` vides sur 289. Un `code` vide laisse un marqueur `[src:ID]` citable qui ne cite rien, 20 sur 1 698. Coût réel : 46 places de fenêtre sur 1 751. Le pipeline a tranché : les éléments vides ne sont pas réparés à la source.

**Pourquoi tout en bas** : 46 places sur 1 751, soit 2,6 % (`calculé` depuis les deux chiffres du site), sans sortie fausse et sans perte de contenu ; le site écrit qu'un coût de cet ordre ne justifie pas un lot.

**À mesurer** : les places récupérées par un filtrage avant le fenêtrage, et surtout ce que le modèle fait d'un bloc vide, seule mesure qui pourrait remonter ce point : un marqueur citable qui ne cite rien invite à citer du vide.

**Effort, `supposé`** : un quart de lot pour la mesure, un petit lot de `src/` ensuite. La fonction concernée est `_restore_full_text` (`src/agent/graph_context.py`).

## 8. Les non bloquantes des audits encore ouvertes

**Sites** : §4.74 (les sept de l'audit du lot 34) et §4.75 (ce que le lot 35 n'a pas prouvé). La seule qui nommait une sortie fausse, le constat E, est fermée (ligne 87 du journal).

| | Ouvert | À faire |
|---|---|---|
| A | Une mesure étiquetée `mesuré` sans date dans un commentaire de `src/api/main.py` | Retrouver la date dans le journal et l'écrire |
| B | « n'a jamais été atteinte sans injection », non borné ; remesuré par l'audit, il tient (0 sur 250) | Borner la phrase à sa campagne, ou la remesurer et la dater |
| C | Les bancs de coût du §4.74 sont hors dépôt | Les verser dans `scripts/` avec leur recette |
| D | La barrière du lot 33 n'est défendue que par son propre garde (sous mutation : 1 rouge sur 1126) | Un second garde d'une autre nature, ou l'acceptation écrite du risque |
| F | `grep -rn '_sonder\b'` rend 58 lignes, dont une fixture homonyme ; 5 appelants en production | Rien à réparer ; à savoir avant de compter |
| G | Un détecteur de résidus mal posé rend des chiffres faux dans les deux sens | Rien à réparer ; leçon de banc déjà écrite |
| §4.75 | La fenêtre du `-wal` n'a jamais été atteinte sans injection (0 sur 4000 appels contre 32 957 fermetures) ; le `-shm` n'a pas été exercé séparément | Rejouer le banc s'il est versé (voir C) |

**Pourquoi en dernier** : aucune ne nomme une sortie fausse. Ce sont des dettes de méthode, qui coûtent le jour où quelqu'un s'appuie dessus.

**Effort, `supposé`** : un lot pour A, B et C ensemble ; D et le `-shm` relèvent d'un lot de gardes ; F et G n'appellent rien.

## Hors de l'ordre : trois constats relevés à la réécriture de la documentation

Relevés dans le code le 27 septembre 2026, sans mesure de leur coût, et donc non classés :

- le frontend n'envoie pas d'en-tête `X-API-Key` : poser `API_KEY` coupe l'interface ([SECURITY.md](SECURITY.md)) ;
- des commentaires de `docker-compose.yml` et de `Dockerfile.agent` donnent `cpu` comme défaut de `TORCH_DEVICE`, alors que le code vaut `cuda` (`src/agent/settings.py`) ;
- la bibliothèque cliente S3 garde un nom de paquet que le dépôt ne veut plus porter ; son remplacement, avec le pipeline, reste à faire (ligne 97 du journal).

## L'ordre en une ligne

Valider la procuration (1) → valider les jeux (2) → décomposer (3) → savoir ce que coûte le GPU (4) → le reranker à deux besoins (5) → la profondeur (6) → les corps vides (7) → les dettes de méthode (8).

Les deux premières ne changent aucun réglage et ne gagnent aucun point de rappel ; elles décident si les six autres veulent dire quelque chose.
