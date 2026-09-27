# Stratégie d'évaluation

Comment le système est mesuré : les jeux de questions, les métriques, la comparaison de deux campagnes, et ce que la mesure ne couvre pas. Pour qui change un réglage et veut savoir s'il a amélioré quelque chose.

Les résultats mesurés sont dans [etat_du_projet.md](etat_du_projet.md) ; les artefacts de campagne dans [runs/](../runs/README.md).

## Le principe

Évaluer, c'est pouvoir répondre à « cette modification a-t-elle amélioré quelque chose, et où cela casse-t-il ? ». Deux règles en découlent :

- **séparer les étages** : une réponse fausse vient d'un passage non trouvé, ou trouvé et mal exploité. `/answer` rend les contextes réellement soumis au modèle pour trancher ;
- **mesurer sans juge ce qui peut l'être** : déterministe, gratuit, reproductible. Un juge-modèle non confronté à une vérité terrain rend une opinion.

## Les outils

| | `scripts/evaluate.py` | [RAG-Eval-Bench](https://github.com/floSa/RAG-Eval-Bench) |
|---|---|---|
| Rôle | Boucle courte, après chaque changement | Campagne de fond, avant de trancher entre deux architectures |
| Métriques | Déterministes, sans modèle | Plus des juges calibrés et des intervalles de confiance |

Pour la recherche seule, sans génération, `scripts/sweep_retrieval.py` balaie un paramètre ; les bancs `scripts/mesurer_*.py` (cibles du `Makefile`) mesurent un étage précis.

## La boucle courte

```bash
make verifier-les-ancrages   # les ancrages des jeux existent-ils dans les stores ?
make eval                    # jeu de réglage, comparé apparié à runs/2026-09-08-reference.json
make eval-controle           # jeu de contrôle, comparé à runs/2026-09-08-controle-30.json
```

Les deux cibles d'évaluation dépendent de `verifier-les-ancrages` : un jeu qui désigne le vide rend 0 % de rappel sans dire pourquoi (§4.3 du [registre](axes_amelioration.md)). Toutes exigent la pile démarrée.

Codes de sortie de `evaluate.py` : `0` la campagne a abouti, `1` aucune question n'a abouti, `2` la comparaison est refusée. La campagne est écrite dans les trois cas. Refus :

1. les deux jeux diffèrent (identifiants manquants, en trop ou répétés) ;
2. la référence ne porte pas la même `empreinte_des_ancrages`, ou n'en porte pas : deux jeux de mêmes identifiants peuvent désigner deux corpus ;
3. la cible de `--compare` n'existe pas ;
4. l'index lexical n'est toujours pas prêt après la chauffe.

## Les trois jeux de questions

Aucun ne remplace les autres. Effectifs repris du registre (§4.67, §4.76) :

| Jeu | Effectif | Origine | Ce qu'il sait mesurer |
|---|---|---|---|
| `tests/fixtures/golden_qa_generated.yaml`, réglage | 138 questions, dont 130 portent un ancrage, un seul chacune ; 45 en français, 93 en anglais | Générées depuis les passages par `scripts/generate_golden.py` | Classer deux configurations ; aveugle à la sélection |
| `tests/fixtures/jeu_de_questions_pipeline.yaml`, contrôle | 30 questions, dont 26 portent 47 ancrages ; 29 anglaises, 1 française | Écrites à la main par le pipeline après l'ingestion | Contredire le générateur ; trop petit pour arbitrer un réglage |
| `tests/fixtures/jeu_ancrages_disperses.yaml`, dispersion | 60 questions, 120 ancrages (2 par question, dans deux sections distinctes), 109 distincts | `scripts/generer_jeu_disperse.py` | Voir la sélection : une section reconstruite ne suffit pas |

Réserves communes : 190 questions sur 228 portent `reviewed: false` (ligne 93 du [journal](pilotage_du_chantier.md)) ; le jeu dispersé est monolingue anglais ; une question générée est écrite pour son passage, donc ne révèle pas un défaut de recherche que le générateur partage.

Chaque question porte `gold_element_ids` (déterministes pour un corpus donné, périmés par un remplacement de corpus), éventuellement `gold_documents`, `chat_history` (question de suivi) ou `unanswerable`. Le générateur pose 40 % des questions dans l'autre langue que leur document (`_PART_TRANSLINGUISTIQUE`) et écarte les questions dont la preuve n'est pas recopiée du passage.

Les jeux sont en YAML : `detect-secrets` lit un `element_id` comme une chaîne à forte entropie, et son lecteur YAML ne signale que les valeurs de mapping.

## Les métriques

| Métrique | Question |
|---|---|
| `rappel_recherche` | Le passage attendu est-il dans le classement ? |
| `rappel_elements` | A-t-il atteint le modèle ? |
| `mrr` | À quel rang ? |
| `rappel_documents` | Le bon document remonte-t-il ? |
| `taux_citation_complete` | Chaque citation nomme-t-elle son document et situe-t-elle le passage ? |
| `abstention_correcte` | Le système admet-il son ignorance quand le corpus est muet ? |
| `taux_contexte_utile` | Parmi les sections payées, quelle part porte un élément d'or ? |
| `part_utile_caracteres` | Parmi les caractères payés, quelle part appartient à une section utile ? |
| `rappel_contexte` | L'élément d'or est-il dans le contexte réellement soumis, fenêtre du graphe comprise ? |
| `contextes_retenus`, `caracteres_par_section` | Le prix monte-t-il par le nombre de sections ou par leur taille ? |
| `contextes_ecartes` | Combien de sources n'ont pas tenu dans la fenêtre ? |
| `eval_count`, `generations_au_plafond` | La génération a-t-elle besoin de son plafond ? ([llm.md](llm.md)) |
| `timings` | Quel étage coûte le temps ? |

Les résultats sont stratifiés par langue. Une strate vide est publiée avec son effectif à zéro plutôt que tue : le jeu de réglage porte 0 question de suivi, donc la campagne ne voit rien du travail sur l'historique.

### La précision du contexte

Le rappel et le MRR mesurent le classement ; la reconstruction par le graphe ne le change pas, elle change la composition du contexte. Trois métriques la voient, et leur dénominateur est ce qui a été payé :

| Métrique | Définition |
|---|---|
| `taux_contexte_utile` | Sections retenues portant un élément d'or ÷ sections retenues |
| `part_utile_caracteres` | Caractères des sections retenues portant un élément d'or ÷ caractères des sections retenues |
| `rappel_contexte` | Éléments d'or présents dans les sections retenues ÷ éléments d'or attendus |

- Une section écartée par le budget n'entre ni au numérateur ni au dénominateur.
- Les questions sans or sont exclues ; les compteurs `precision_contexte_sur`, `…_exclues_sans_or` et `…_exclues_sans_retenue` somment au nombre de questions. `rappel_contexte` publie son propre effectif, `rappel_contexte_sur`.
- L'écart entre `rappel_contexte` et `rappel_elements` est l'apport de la fenêtre du graphe : un élément d'or ramené par la fenêtre sans avoir été classé compte dans le premier, pas dans le second.
- `part_utile_caracteres` raisonne à la section : élargir la fenêtre dans la section utile ne la fait pas bouger. Une ablation de fenêtre se lit sur le couple `caracteres_retenus` et `rappel_contexte`.

### La décomposition du temps

`timings` est une partition : chaque milliseconde appartient à un seul étage, le reste va au résidu.

| Étage | Mesure |
|---|---|
| `rewrite_ms` | Réécriture de la question de suivi (appel au modèle) |
| `translation_ms` | Traduction de la question (appel au modèle) |
| `dense_ms` | Recherche vectorielle, question et traduction cumulées |
| `lexical_ms` | Recherche BM25, idem |
| `fusion_ms` | Fusion RRF |
| `rerank_ms` | Cross-encoder |
| `reconstruction_ms` | Remontée du graphe, fenêtrage, relecture du texte intégral |
| `generation_ms` | Génération, du premier au dernier token |
| `residual_ms` | Ce qu'aucun étage ne réclame ; peut être négatif, et n'est pas borné |
| `total_ms` | Temps mural autour de la traversée entière |

La somme des huit étages et du résidu égale `total_ms`, et un test le tient. `retrieval_ms` est un agrégat qui contient `dense_ms`, `lexical_ms` et `fusion_ms` : il n'entre pas dans la partition. Le résumé publie p50 et p95 par étage.

## La comparaison appariée

`--compare` apparie les deux campagnes question par question. Par métrique : questions améliorées, dégradées, inchangées ; les identifiants qui basculent ; un test des signes exact sur les seules questions qui bougent ; un intervalle de confiance à 95 % de la différence moyenne, par bootstrap à graine fixe (2 000 rééchantillonnages). Tout est déterministe.

- L'appariement porte les huit métriques de qualité, plus `caracteres_retenus` et `contextes_retenus`, dont le sens est inversé (moins est mieux).
- Les latences ne sont pas appariées : deux campagnes ne partagent pas la charge de la machine. Elles se lisent sur les centiles.
- Chaque métrique a un sens de lecture (`HAUT_EST_MIEUX`, `PLUS_BAS_EST_MIEUX`, `SANS_DIRECTION`), et un test rougit sur une clé du résumé ajoutée sans sens tranché.
- Le moteur LLM de chaque campagne est confronté à part ([moteur_llm.md](moteur_llm.md)) ; le périphérique de torch aussi.

## Ce qui n'est pas mesuré

- **La qualité des réponses** : fidélité au contexte, justesse, précision des citations (un `[src:ID]` résoluble n'est pas une citation qui soutient l'affirmation), pertinence des images. Cela demande un jeu de réponses de référence et un juge, qui n'existent pas ([prochaines_etapes.md](prochaines_etapes.md), §1).
- **Les ablations restantes** : avec ou sans reconstruction de section (le pari central du projet), dense seul contre hybride, réécriture sur les seules questions de suivi, autre modèle d'embedding (réingestion complète).
