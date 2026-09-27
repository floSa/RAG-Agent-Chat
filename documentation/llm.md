# Le serveur d'inférence et le budget de la fenêtre

Comment l'agent parle au serveur d'inférence, comment il remplit la fenêtre de contexte, et comment vérifier l'un et l'autre. Pour qui règle la génération ou diagnostique un prompt trop long.

## Le serveur

L'agent n'embarque aucun serveur d'inférence. Il parle au conteneur `vllm-central` du projet [`llm-service`](https://github.com/floSa/llm-service), sur le réseau Docker `llm-net`, en dialecte OpenAI (`POST /v1/chat/completions`). Ce serveur appartient à une équipe voisine et sert aussi d'autres projets : l'agent ne fait qu'y lire et y générer.

Ce qui est servi, `mesuré` le 27 septembre 2026 à 06:19 UTC par `curl -s http://localhost:8011/health` (bloc `moteur_llm`) : serveur `vllm` version `0.28.0`, modèle `google/gemma-4-E4B-it-qat-w4a16-ct` demandé et servi, fenêtre servie `32768`. Le relevé du moteur, ses champs et sa signature dans les campagnes sont décrits dans [moteur_llm.md](moteur_llm.md).

Démarrer le serveur, puis vérifier le modèle servi :

```bash
cd ~/mes_projets/llm-service && make up
```
```bash
make models
```

## La configuration

| Variable | Défaut du code | Rôle |
|---|---|---|
| `LLM_HOST` | `http://vllm-central:8000` | Adresse du serveur |
| `LLM_MODEL` | `google/gemma-4-E4B-it-qat-w4a16-ct` | Modèle de génération |
| `LLM_NUM_CTX` | `8192` | Budget de prompt que le client s'autorise |
| `LLM_MAX_TOKENS` | `4096` | Plafond de génération |
| `LLM_TEMPERATURE` | `0.1` | Température |
| `LLM_THINKING` | `false` | Raisonnement du modèle, passé par requête dans `chat_template_kwargs` |
| `HISTORY_WINDOW_SHARE` | `0.25` | Part de la fenêtre de prompt laissée à l'historique |
| `TRUNCATION_FLOOR_SHARE` | `1/3` | Part minimale d'une source tronquée |

`LLM_NUM_CTX` n'est pas envoyé au serveur : le dialecte OpenAI n'a pas de champ de fenêtre, et celle de `vllm-central` est fixée à son lancement (`--max-model-len 32768`). Il borne ce que le client envoie. `/health` publie en regard la fenêtre servie (`moteur_llm.fenetre_servie`) et la valeur en vigueur (`moteur_llm.options.num_ctx`).

Le défaut du dépôt reste `8192`. Sur ce poste, le `.env` le porte à `32768` depuis le 22 septembre 2026 : `/health` publie `options.num_ctx` à `32768` (`mesuré` le 27 septembre 2026 à 06:19 UTC). Élargir la fenêtre n'a pas été mesuré comme un gain, et le plus gros prompt mesuré au §4.66 du [registre](axes_amelioration.md) vaut 4849 jetons, soit 15 % de la fenêtre servie. Historique de ce changement : §4.63 et §4.64 du registre.

Deux avertissements, mesurés le 16 septembre 2026 :

- `LLM_THINKING=true` n'est pas exploitable sur `vllm-central`, qui tourne sans `--reasoning-parser` : hors flux la réponse est `null`, en flux le raisonnement brut part à l'écran. Aucun des deux cas ne lève.
- Un champ d'un autre dialecte envoyé au serveur est accepté en HTTP 200 puis ignoré. Toute requête passe donc par un site unique, `src/agent/dialecte_llm.py`.

La migration d'un `.env` antérieur au moteur unique est décrite dans [moteur_llm.md](moteur_llm.md), section « La migration du `.env`, exacte ».

## Le budget de contexte

### La formule

`num_ctx` est partagé entre le prompt et la génération, et le prompt ne contient pas que des sources :

```
fenêtre utile     = (LLM_NUM_CTX − LLM_MAX_TOKENS) × 3,5 caractères/token
budget sources    = fenêtre utile − prompt système
                                  − gabarit rendu sans ses sources
                                  − historique retenu
                                  − balises de tour (une par message)
                                  − déclaration de l'outil search_vectors
coût d'une source = len(markdown) + son encadrement, mesuré dans le gabarit
```

Chaque terme est la longueur d'une chaîne réellement construite, pas une provision. L'encadrement d'une source n'est facturé qu'au moment où elle est retenue.

Valeurs mesurées à l'exécution, à `8192 / 4096` :

| Terme | Caractères |
|---|---|
| Fenêtre utile | 14 336 |
| Prompt système (`prompts/system.txt`) | 935 |
| Gabarit rendu sans sources | 472 |
| Déclaration de l'outil `search_vectors` (si `NATIVE_TOOL_CALLING`) | 417 |
| Encadrement d'une source, sans fil des titres | 34 |
| Encadrement d'une source, fil des titres à 2 niveaux | 134 |
| Encadrement d'une source, fil des titres à 5 niveaux | 275 |
| Budget de sources, premier tour | 12 444 |
| Budget de sources, trois tours de 600 caractères par message (dont un tour écarté) | 9 908 |

L'encadrement est mesuré source par source, par décomposition (`rendu([source]) − rendu([]) − len(markdown)`). La déclaration de l'outil est comptée : le serveur la rend dans le prompt par le gabarit de chat.

Ce qui reste un forfait, liste complète :

| Forfait | Valeur | Ce qui le réglerait |
|---|---|---|
| Ratio caractères/token | 3,5 | Le ratio mesuré que publie chaque génération (voir plus bas) |
| Balises de tour, par message | 34 | Le décompte du gabarit Gemma, appliqué à tous |
| Part de l'historique (`HISTORY_WINDOW_SHARE`) | 25 % | Une mesure de la qualité multi-tour, qui n'existe pas |
| Part minimale d'une source tronquée (`TRUNCATION_FLOOR_SHARE`) | 1/3 | Une mesure de la qualité des réponses ; la grille ci-dessous établit seulement que le plancher doit exister |
| Marge sous `num_ctx` à partir de laquelle on avertit | 8 tokens | Des `prompt_eval_count` réels |
| Fraction de l'estimation sous laquelle une mesure est imputée à un cache de préfixe | 0,6 | La distribution observée en campagne |

### Ce qui est écarté, et par quel bout

`node_reconstruct_context` reconstruit les sections par pertinence décroissante, sur le classement du reranker. `fit_prompt` est le point d'entrée unique, appelé une fois par génération ; `/answer` en publie le résultat (`dropped_contexts`).

| Élément | Coupe | Règle |
|---|---|---|
| Sources | Les moins bien classées | Remplissage au mieux : une petite source qui suit une grosse écartée est conservée |
| La marge de fenêtre restante | Donnée à la mieux classée des écartées, tronquée | Elle restait vide : 1 355 caractères de fenêtre inutilisés en moyenne et 7 970 au maximum sur 88 configurations, ramenés à 408 en moyenne — 70 % de la marge reprise, 38 configurations gagnées et aucune perdue. Si la première candidate est refusée par le plancher, la suivante est essayée |
| Fragment sous `TRUNCATION_FLOOR_SHARE` | Source écartée entière | Sans plancher, la grille descend à 1 % d'une source |
| Source unique trop grosse | Tronquée par la fin, sur une frontière d'élément, avec une marque | Plancher relâché dans ce seul cas ; la coupe recule jusqu'au dernier `[src:ID]` complet |
| Historique | Les tours les plus anciens, entiers | La coupe porte sur des tours, pas des messages, pour garder l'alternance du gabarit de chat |
| Tour trop gros à lui seul | Écarté | `node_rewrite` a déjà rendu la question autonome |

Au-delà de sa fenêtre, le serveur refuse la requête entière : HTTP 400, « maximum context length is 32768 tokens » (`mesuré` le 18 septembre 2026 à 12:35 UTC). Le budget existe pour ne jamais l'atteindre.

Bornes d'entrée correspondantes, dans `src/api/schemas.py` : `MAX_MESSAGE_CHARS` (14 336), `MAX_HISTORY_MESSAGES` (6, soumis au modèle), `MAX_HISTORY_PAYLOAD` (50, acceptés par requête).

### Remesurer la marge de fenêtre

La grille est un calcul pur sur `fit_contexts` : elle ne demande ni serveur ni store. Elle reconstruit l'algorithme d'avant dans la même exécution, et tire des sources de tailles inégales à graine fixe. Depuis la racine du dépôt, `.venv` activé, sans `.env` (les défauts `8192 / 4096` s'appliquent) :

```bash
python - <<'EOF'
import random
from src.agent import llm
from src.agent.llm import (_TRUNCATION_MARKER, context_budget_chars, fit_contexts,
                           source_framing_chars)
from src.agent.settings import settings
from src.api.schemas import BreadcrumbEntry, SectionContext
Q = "Quelle est la difference entre un pipeline de features et un feature store ?"

def source(rang, taille, niveaux):
    parties, i = [], 0
    while sum(len(m) for m in parties) < taille:
        parties.append(f"Paragraphe {i} de la section {rang}, avec assez de texte pour "
                       f"peser dans la fenetre. [src:{rang:04d}{i:06d}]\n\n")
        i += 1
    return SectionContext(
        element_id=f"abcdef{rang:04d}", section_id=f"section{rang:04d}",
        breadcrumbs=[BreadcrumbEntry(node_id=f"n{j}", label="SectionHeader", text="T"*44)
                     for j in range(niveaux)],
        elements=[], markdown="".join(parties)[:taille])

def avant(contexts, budget, framing):
    """Algorithme d'avant le remplissage : seule la PREMIERE pouvait etre coupee."""
    kept, used = [], 0
    for ctx, enc in zip(contexts, framing, strict=True):
        cout = len(ctx.markdown) + enc
        if not kept and cout > budget:
            place = budget - enc - len(_TRUNCATION_MARKER)
            if place <= 0:
                continue
            garde = llm._cut_on_marker(ctx.markdown, place, exiger_marqueur=False)
            kept.append(ctx.model_copy(update={"markdown": garde + _TRUNCATION_MARKER}))
            used = budget
        elif not kept or used + cout <= budget:
            kept.append(ctx); used += cout
    return kept

def marge(budget, kept, fr):
    return budget - sum(len(c.markdown) for c in kept) - sum(fr[:len(kept)])

def campagne():
    av, ap, gagnees, perdues, parts = [], [], 0, 0, []
    alea = random.Random(1789)          # graine fixe : la grille est reproductible
    for niv in (0, 2, 5):
        for taille in (500, 1000, 1500, 2000, 2500, 3000, 4000, 6000):
            for n in (1, 3, 5, 7, 10, 12):
                cands = [source(i, max(120, int(taille * alea.uniform(0.25, 3.0))), niv)
                         for i in range(n)]
                budget = context_budget_chars(Q, [])
                fr = source_framing_chars(Q, cands)
                k_av = avant(list(cands), budget, fr)
                if len(k_av) == len(cands):
                    continue
                k_ap, _ = fit_contexts(list(cands), budget, fr)
                av.append(marge(budget, k_av, fr)); ap.append(marge(budget, k_ap, fr))
                gagnees += len(k_ap) > len(k_av); perdues += len(k_ap) < len(k_av)
                tailles = {c.element_id: len(c.markdown) for c in cands}
                parts += [(len(c.markdown) - len(_TRUNCATION_MARKER)) / tailles[c.element_id]
                          for c in k_ap if c.markdown.endswith(_TRUNCATION_MARKER)]
    return av, ap, gagnees, perdues, parts

av, ap, gagnees, perdues, parts = campagne()
print(f"configurations avec au moins une ecartee : {len(av)} / 144")
print(f"marge inutilisee AVANT : moyenne {sum(av)/len(av):.0f}, max {max(av)}")
print(f"marge inutilisee APRES : moyenne {sum(ap)/len(ap):.0f}, max {max(ap)}")
print(f"marge reprise : {100*(1-sum(ap)/sum(av)):.0f} %")
print(f"configurations gagnees : {gagnees}, perdues : {perdues}")
print(f"plus petite part retenue : {100*min(parts):.0f} %")
for plancher in (0.0, 0.15, 0.25, 1/3, 0.40, 0.50):
    settings.truncation_floor_share = plancher
    _, ap2, g2, _, p2 = campagne()
    print(f"plancher {plancher:.2f} : marge {sum(ap2)/len(ap2):6.0f}, {g2:2d} gagnees, "
          f"plus petite part {100*min(p2):.0f} %")
EOF
```

Sortie, `rejoué` le 27 septembre 2026 à 06:28 UTC, `rc=0` (le journal des troncatures s'imprime avant ces lignes) :

```
configurations avec au moins une ecartee : 88 / 144
marge inutilisee AVANT : moyenne 1355, max 7970
marge inutilisee APRES : moyenne 408, max 3865
marge reprise : 70 %
configurations gagnees : 38, perdues : 0
plus petite part retenue : 34 %
plancher 0.00 : marge     76, 70 gagnees, plus petite part 1 %
plancher 0.15 : marge    175, 55 gagnees, plus petite part 15 %
plancher 0.25 : marge    266, 48 gagnees, plus petite part 25 %
plancher 0.33 : marge    408, 38 gagnees, plus petite part 34 %
plancher 0.40 : marge    457, 35 gagnees, plus petite part 41 %
plancher 0.50 : marge    585, 31 gagnees, plus petite part 51 %
```

La première moitié de cette sortie est reprise dans le docstring de `fit_contexts` et au §1.30 du registre ; `tests/unit/test_coherence_depot.py` exige que les trois copies restent identiques. Remesurer, c'est éditer les trois.

## L'instrumentation : `prompt_eval_count`

L'événement d'usage du flux porte les décomptes du serveur, dont le nombre réel de tokens du prompt. Chaque génération journalise l'estimation en regard :

```
INFO  Prompt : estimé 3214 tokens, réel 3480, écart -7.6 % — ratio mesuré
      3.23 caractères/token (retenu : 3.50).
```

Cette ligne montre la forme du journal ; ses chiffres sont un exemple, pas une mesure. Lecture :

- écart négatif : l'estimation sous-estime le prompt, le budget est trop permissif ;
- écart positif : le budget est trop prudent et écarte des sources qui auraient tenu ;
- ratio mesuré : la valeur qu'aurait dû avoir `_CHARS_PER_TOKEN`.

| Avertissement | Signal |
|---|---|
| `prompt_eval_count` à moins de 8 tokens de `num_ctx` | Le prompt affleure le budget du client ; une source de plus et la borne coupe |
| `prompt_eval_count` au-delà de `num_ctx − num_predict` | La génération n'a plus tous ses tokens et sera rognée sans le dire |

Un serveur qui ne réévaluerait que le suffixe absent de son cache de préfixe rapporterait un décompte amputé. `vllm-central` ne le fait pas : deux requêtes identiques rendent `prompt_tokens = 616` toutes les deux (`mesuré` le 18 septembre 2026 à 12:42 UTC). La garde reste en place, défensive : sous 60 % de l'estimation, la mesure est écartée de la calibration et le journal le dit. Ne jamais recalibrer `_CHARS_PER_TOKEN` sur ces échantillons.

```bash
docker logs -f rag-agent-api 2>&1 | grep "Prompt :"
```

`/answer` publie ces décomptes sous `generation`, et `scripts/evaluate.py` les enregistre par question :

| Champ | Contenu |
|---|---|
| `prompt_eval_count` | Décompte réel du prompt |
| `prompt_tokens_estimated` | Estimation du même prompt |
| `prompt_tokens_reliable` | Faux : échantillon pollué par un cache, écarté de la calibration |
| `eval_count` | Tokens générés |
| `num_predict` | Le plafond appliqué |

La décision d'écarter un échantillon a un seul site, `llm.mesure_prompt_exploitable`, appliqué par le journal comme par la campagne. Le résumé de campagne en tire `ratio_caracteres_par_token_mesure`, sur les seuls échantillons exploitables.

## `LLM_MAX_TOKENS` reste à mesurer

`LLM_MAX_TOKENS = 4096` réserve la moitié de la fenêtre par défaut à la génération, et la longueur réelle des réponses n'est pas encore mesurée. `make eval` publie les chiffres qui trancheront :

| Chiffre du résumé | Ce qu'il décide |
|---|---|
| `generations_au_plafond` | Zéro sur toutes les questions : le plafond ne sert jamais. Non nul : le baisser tronquerait des réponses |
| `eval_count_p95`, `eval_count_max` | Où poser le plafond |
| `eval_count_sur` | Sur combien de réponses portent les chiffres précédents |
| `reponse_caracteres_p95` | Le repli si le serveur ne rend pas `eval_count` |

Après tout changement, relancer `make eval` : le budget de sources en dérive, et la comparaison appariée dit quelles questions basculent.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `/health` rend `services.llm: false` | `llm-service` n'est pas démarré, ou le réseau `llm-net` n'existe pas |
| `network llm-net not found` au démarrage | Lancer `make up` dans `llm-service` d'abord |
| HTTP 400 « maximum context length » | `LLM_NUM_CTX` dépasse la fenêtre servie, publiée sous `moteur_llm.fenetre_servie` |
| Réponse de 17 à 30 s | Ordre de grandeur normal d'une réponse réelle ; la génération porte l'essentiel du temps ([README](../README.md#retours-de-fonctionnement)) |
