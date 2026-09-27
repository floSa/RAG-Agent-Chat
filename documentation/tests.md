# Les tests, et ce qu'ils ne disent pas

Les trois niveaux de test du dépôt, ce que chaque fichier garde, et ce que rien ne couvre. Pour qui modifie le code ou lit une porte qualité.

| Niveau | Commande | Question |
|---|---|---|
| Unitaire | `make test` | La logique est-elle correcte ? |
| Intégration | `make test-integration` | Le système tient-il debout avec les vrais stores ? |
| Campagne | `make eval` | La recherche trouve-t-elle les bons passages ? |

La porte qualité est `make lint && make test`, dans l'environnement décrit au §2.2 du [journal](pilotage_du_chantier.md) ; la marche à suivre est dans le [README](../README.md#porte-qualité).

## Unitaire — 1316 tests, aucune dépendance

Tout est simulé : ni ChromaDB, ni NebulaGraph, ni serveur d'inférence. C'est ce qui tourne en intégration continue.

Le compte se remesure ainsi, la somme par fichier devant égaler le total que `pytest` annonce :

```bash
pytest tests/unit/ --collect-only -q | awk -F': ' '/^tests\/unit\/.*: [0-9]+$/ {s+=$2} END {print s}'
```

> `mesuré` le 27 septembre 2026 à 05:34 UTC par LOT-43 : **1316** tests sur **64** fichiers, et les deux comptes de la recette concordent.
> *(LOT-42 relevait **1304** sur **63** fichiers le 25 septembre à 12:54 UTC ; les **12** de plus sont **5** dans le fichier neuf `test_zero_trace_du_nom_retire.py`, 4 dans `test_schemas.py`, 3 dans `test_contrat_champs_externes.py`, 1 dans `test_bascule_du_nom_de_champ_media.py`, et 1 de moins dans `test_media_url_et_object_key.py`. Détail : §4.83 du registre.)*

Ce compte a déjà été faux sans que rien ne le voie : cette page a annoncé **520** tests sur **36** fichiers, le 4 septembre 2026, quand le dépôt en portait 539 sur 37 (§4.13 du registre). Il est donc gardé : `tests/unit/test_coherence_depot.py` confronte le titre de cette section, la note ci-dessus et sa parenthèse à ce que `pytest` collecte, et exige que la note soit la seule phrase de sa forme qui porte `mesuré`. Ajouter un test, c'est mettre à jour les trois, avec le relevé précédent comme antécédent. La chaîne des relevés antérieurs est au [journal](pilotage_du_chantier.md), une ligne par lot. Recollecté pour cette page le 27 septembre 2026 à 06:36 UTC : même total, même nombre de fichiers.

### Ce que garde chaque fichier

| Fichier | Ce qu'il garde |
|---|---|
| `test_absorptions.py` | Les absorptions d'exceptions resserrées, et le garde qui les empêche de s'élargir |
| `test_affichage_sources.py` | L'affichage des sources dans l'écran de sélection |
| `test_answer_endpoint.py` | `/answer`, le point d'entrée non interactif |
| `test_bascule_du_nom_de_champ_media.py` | Ce que coûterait, en silence, un champ média renommé par la source |
| `test_borne_des_sources.py` | La borne de `max_sources` est celle que la chaîne sert réellement |
| `test_capture_branchement.py` | La capture branchée sur l'API : deux phases, trois chemins, la panne |
| `test_capture_usage.py` | Le module de capture, sa résilience, ce qu'il rend interrogeable |
| `test_champs_du_dialecte.py` | L'inventaire des champs qui dépendent du moteur |
| `test_chauffe_lexicale.py` | La chauffe de l'index BM25 avant une campagne, et le refus qui la garde |
| `test_chronometrie.py` | La partition du temps par étage, et ce qui la fait mentir |
| `test_citations_soumises.py` | Une citation ne résout jamais vers un texte non soumis au modèle |
| `test_coherence_depot.py` | Les endroits du dépôt qui doivent s'accorder : documentation, code, `Makefile`, compte de tests |
| `test_comparaison_appariee.py` | La comparaison appariée de deux campagnes, et son refus sur deux jeux différents |
| `test_context_assembly.py` | Échappement des VIDs, fenêtrage autour de l'ancre, rendu markdown |
| `test_contrat_champs_externes.py` | Le contrat des noms de champs rendus par les stores |
| `test_decomposition_traduite.py` | Le banc de la décomposition avec traduction |
| `test_dialecte_llm.py` | Le dialecte sortant vers le serveur d'inférence : adresse et forme |
| `test_fenetre_heritee.py` | Des scènes dont le verdict ne dépend pas de la fenêtre du poste |
| `test_flux_interactif.py` | Le flux `/chat/start` → sélection → `/chat/resume` |
| `test_full_text.py` | La relecture du texte intégral depuis l'index vectoriel |
| `test_fusion_des_sous_questions.py` | Le banc de la fusion réelle des sous-requêtes |
| `test_garde_modele_embedding.py` | Le garde du modèle d'embedding, côté lecteur |
| `test_garde_reranker.py` | Le garde du reranker |
| `test_graph_context.py` | Le rendu markdown d'une section et de son fil des titres |
| `test_health_parallele.py` | `/health` tient dans le délai du healthcheck Docker |
| `test_historique_soumis.py` | La profondeur d'historique soumise au modèle, par route |
| `test_identite_du_code.py` | L'identité du code gravée dans l'image et publiée par `/health` |
| `test_index_lexical.py` | L'index BM25 face à un corpus qui bouge et à des requêtes concurrentes |
| `test_installation_des_garde_fous.py` | `make install` et le garde-fou d'identité git, indépendants de tout arbre de travail |
| `test_jeu_ancrages_disperses.py` | Le jeu à ancrages dispersés |
| `test_jeux_de_questions.py` | La forme des jeux de questions |
| `test_lecteur_de_flux.py` | Le lecteur de flux et l'accumulation des appels d'outil fragmentés |
| `test_lecture_sequence.py` | Les trois réserves de lecture de `sequence` ([stores.md](stores.md#les-trois-réserves-de-lecture-de-sequence)) |
| `test_lexical.py` | Tokenisation BM25 et fusion RRF sur les rangs |
| `test_llm_budget.py` | Le budget de la fenêtre de contexte ([llm.md](llm.md)) |
| `test_media_url_et_object_key.py` | `media_url` et `object_key`, et eux seuls, aux cinq sites de lecture |
| `test_mesure_de_la_selection.py` | Le banc qui mesure la sélection |
| `test_mesure_generation.py` | Ce que coûte la génération (`eval_count`, plafond) |
| `test_montage_des_tests.py` | Les garanties du montage des tests |
| `test_moteur_llm.py` | Le moteur LLM consigné dans les campagnes ([moteur_llm.md](moteur_llm.md)) |
| `test_moteur_unique.py` | Le nom de l'ancien moteur ne revient pas hors des archives |
| `test_numerotation_des_documents.py` | Les numéros du registre et du journal |
| `test_ordre_des_sources.py` | L'ordre d'entrée des sources dans la fenêtre |
| `test_partition_etages.py` | La partition du temps exercée sur les vrais nœuds du graphe |
| `test_peripherique_torch.py` | Le périphérique de torch : choisi, réglable, observable ([gpu_cuda.md](gpu_cuda.md)) |
| `test_plafond_de_recuperation.py` | Le banc du plafond de récupération du jeu dispersé |
| `test_postprocess.py` | L'extraction des citations et des images de la réponse |
| `test_precision_contexte.py` | La précision du contexte remis au modèle |
| `test_purge_sessions.py` | La purge des sessions : ce qu'elle supprime et ce qu'elle annonce |
| `test_query_rewrite.py` | La réécriture d'une question de suivi en question autonome |
| `test_repli_dans_la_prose.py` | La reconnaissance d'un appel d'outil écrit dans la prose |
| `test_resilience.py` | La réouverture des connexions mises en cache |
| `test_retrieval_logic.py` | Déduplication, calibration, groupement par document |
| `test_retriever.py` | Le groupement des sources par document |
| `test_schemas.py` | Les modèles de requête et de réponse, et le nom `media_url` que l'API publie |
| `test_schemas_validation.py` | La validation des identifiants, de `top_k` et de la longueur des messages |
| `test_section_voisine.py` | La définition de « section voisine », gardée par mutation |
| `test_securite.py` | Traversée de chemin, échappement nGQL, comparaison de clé à temps constant |
| `test_sens_des_metriques.py` | Le sens de lecture d'une métrique dans `--compare` |
| `test_session_perimee_apres_purge.py` | La session NebulaGraph rendue aveugle par une purge du graphe |
| `test_stockage_objet.py` | La conversion entre URL d'objet, clé et chemin `/media` |
| `test_tool_calling.py` | La détection d'une demande de recherche supplémentaire par le modèle |
| `test_verification_des_ancrages.py` | La sonde qui prouve qu'un jeu de questions désigne quelque chose |
| `test_zero_trace_du_nom_retire.py` | Le nom de l'ancien stockage objet ne revient nulle part hors des sites tolérés |

### Les règles de ces tests

- **Un double doit ressembler à la bibliothèque.** Simuler une panne réseau par une exception que la bibliothèque ne lève jamais laisse vert n'importe quelle absorption.
- **Asserter le disque, pas le compteur du code.** Une purge qui annonce « 1 supprimée » sans rien supprimer passe tout test qui croit le compteur.
- **Prouver la simultanéité par une barrière, pas par un chronomètre.** Simuler une sonde qui ne revient pas, pas une sonde qui dort.
- **Une garde se double d'un contrôle positif** : un zéro n'a de valeur que si l'instrument sait voir un cas non nul.

## Intégration — 10 tests, pile requise

Ils existent pour les défauts invisibles en unitaire, qui vivent dans l'écart entre ce que le code croit et ce que les services font : une requête nGQL écrite à l'envers, une arête renommée côté ingestion, un checkpointer synchrone branché sur un flux asynchrone.

```bash
make test-integration
```

Sans la pile, ils sont ignorés, pas en échec. Ils exigent l'API sur le port 8011.

## Campagne — la mesure de la recherche

`make eval` rejoue le jeu de réglage contre `POST /answer` et compare la campagne à une référence, question par question. `make eval-controle` fait de même sur le jeu de contrôle. Les deux dépendent de `make verifier-les-ancrages`, qui prouve d'abord que les jeux désignent des passages existants.

Métriques et lecture : [rag_evaluation_strategy.md](rag_evaluation_strategy.md). Résultats versionnés : [runs/README.md](../runs/README.md).

Trois règles :

1. Mesurer après le reranking : c'est ce qui atteint le modèle qui compte.
2. Vérifier ce que le `.env` impose : il surcharge les défauts du code.
3. Ne rien toucher pendant une campagne, ni build ni redémarrage.

## Ce que rien ne teste

- **La qualité des réponses.** Aucune réponse n'est jugée, ni par un humain ni par un modèle ([etat_du_projet.md](etat_du_projet.md)).
- **La relecture humaine des jeux.** 190 questions sur 228 portent `reviewed: false` (ligne 93 du [journal](pilotage_du_chantier.md)).
- **Le frontend de bout en bout.** Les fonctions d'affichage sont testées ; le parcours dans un navigateur ne l'est qu'à la main, boutons d'appréciation compris.
- **La charge.** Deux points seulement : les écritures de la capture à dix interactions concurrentes, et la construction de l'index lexical à huit requêtes concurrentes. Aucun test ne fait passer deux questions entières en parallèle.
- **Les requêtes servies pendant une reconstruction de l'index lexical.** Le test attend le fil de reconstruction ; la correction des requêtes concurrentes repose sur le remplacement atomique de l'état de l'index, relu et non testé.
- **L'ordre exact de l'écriture de la capture après le dernier événement SSE.** Il est observé par un espion dans l'application, pas depuis le client.
