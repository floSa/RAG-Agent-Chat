"""LOT-43 — le nom de l'ancien stockage objet ne revient nulle part dans le dépôt.

POURQUOI CETTE GARDE EXISTE.

Le stockage objet du pipeline est SeaweedFS, servi en S3, depuis le
25 septembre 2026. Le propriétaire a décidé qu'il ne resterait AUCUNE trace du
nom du produit d'avant : ni dans le code, ni dans les tests, ni dans la
configuration, ni dans la documentation, historique compris — §4.83 du registre.
Une décision de ce genre ne tient que si quelque chose rougit le jour où le nom
revient, par un copier-coller, un commentaire, une URL d'exemple.

CE QU'ELLE MESURE. Exactement ce que la décision énonce : `git grep -i` du nom
sur les fichiers SUIVIS, arbre de travail compris. Chaque ligne rendue doit être
l'un des sites tolérés, et ils sont trois :

- le NOM DU PAQUET de la bibliothèque cliente S3, qui porte ce nom et qu'on ne
  renomme pas : `requirements.txt`, `pyproject.toml`, `uv.lock` ;
- son IMPORT, à UN SEUL site du code, `src/agent/stockage_objet.py`, qui le
  rebaptise aussitôt `ClientS3` — c'est ce qui garde le nom hors de tout le reste
  du module ;
- la ZONE DE MIGRATION du registre, entre deux balises : la table « ancien nom →
  nouveau nom » des variables d'environnement, dont le déploiement a besoin au
  caractère près. Le lot 28 a fait de même pour les clés du moteur
  (`test_moteur_unique.py`).

LE NOM N'EST ÉCRIT NULLE PART ICI EN UN SEUL MORCEAU. Il est assemblé à
l'exécution, sans quoi cette garde s'attraperait elle-même — et c'est le seul
site de tout le dépôt qui l'assemble : les autres gardes l'importent d'ici.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_RACINE = Path(__file__).resolve().parents[2]

# ─── LE NOM, ASSEMBLÉ EN DEUX MORCEAUX ────────────────────────────────────────
NOM_RETIRE = "min" + "io"

# ─── LES SITES TOLÉRÉS ────────────────────────────────────────────────────────
#
# Chaque tolérance est une LIGNE ENTIÈRE, par fichier : une ligne tolérée qui se
# met à porter le nom une seconde fois, dans un commentaire, ne l'est plus.
_PAQUET = re.escape(NOM_RETIRE)
_VERSION = r"[0-9][0-9A-Za-z.]*"
TOLERANCES: dict[str, tuple[re.Pattern[str], ...]] = {
    "requirements.txt": (re.compile(rf"{_PAQUET}=={_VERSION}"),),
    "pyproject.toml": (
        # La dépendance, puis le module que mypy tient pour non typé.
        re.compile(rf'    "{_PAQUET}=={_VERSION}",'),
        re.compile(rf'    "{_PAQUET}\.\*",'),
    ),
    "uv.lock": (
        re.compile(rf'name = "{_PAQUET}"'),
        re.compile(
            rf'sdist = \{{ url = "https://files\.pythonhosted\.org/packages/[0-9a-f/]+/'
            rf'{_PAQUET}-{_VERSION}\.tar\.gz", hash = "sha256:[0-9a-f]{{64}}", .*\}}'
        ),
        re.compile(
            rf'    \{{ url = "https://files\.pythonhosted\.org/packages/[0-9a-f/]+/'
            rf'{_PAQUET}-{_VERSION}-py3-none-any\.whl", hash = "sha256:[0-9a-f]{{64}}", .*\}},'
        ),
        re.compile(rf'    \{{ name = "{_PAQUET}" \}},'),
        re.compile(rf'    \{{ name = "{_PAQUET}", specifier = "=={_VERSION}" \}},'),
    ),
}

# L'import, et c'est le SEUL site du code où le nom paraît.
SITE_D_IMPORT = "src/agent/stockage_objet.py"
LIGNE_D_IMPORT = f"from {NOM_RETIRE} import {NOM_RETIRE.capitalize()} as ClientS3"

# La zone de migration : un seul fichier, une seule paire de balises, bornée.
FICHIER_DE_MIGRATION = "documentation/axes_amelioration.md"
BALISE_DEBUT = "migration-du-lot-43:" + "début"
BALISE_FIN = "migration-du-lot-43:" + "fin"
# La table porte cinq variables : une zone plus longue que ceci n'est plus une
# table, c'est un document qu'on a soustrait à la garde.
LIGNES_MAX_DE_LA_ZONE = 20


def _git_grep() -> list[tuple[str, int, str]]:
    """`git grep -i -n` du nom, sur les fichiers suivis : (chemin, ligne, texte).

    `rc=1` est « aucune ligne », pas une panne ; tout autre code non nul en est
    une, et elle lève plutôt que de rendre un vide qu'on lirait comme un vert.
    """
    sortie = subprocess.run(
        ["git", "-C", str(_RACINE), "grep", "-i", "-n", "--no-color", "-e", NOM_RETIRE],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sortie.returncode in (0, 1), f"git grep a échoué : rc={sortie.returncode}"
    lignes: list[tuple[str, int, str]] = []
    for brute in sortie.stdout.splitlines():
        chemin, numero, texte = brute.split(":", 2)
        lignes.append((chemin, int(numero), texte))
    return lignes


def zones_de_migration(chemin: str, texte: str) -> list[tuple[int, int]]:
    """Les zones balisées d'un texte, en numéros de ligne 1-indexés, balises comprises.

    Une balise de début non refermée n'ouvre AUCUNE zone : le reste du document
    reste lu. C'est le sens sûr — une balise oubliée ne doit pas rendre la garde
    muette sur tout ce qui suit.
    """
    zones: list[tuple[int, int]] = []
    debut: int | None = None
    for numero, ligne in enumerate(texte.splitlines(), 1):
        if BALISE_DEBUT in ligne:
            debut = numero
        elif BALISE_FIN in ligne and debut is not None:
            zones.append((debut, numero))
            debut = None
    return zones


def sites_non_toleres(
    lignes: list[tuple[str, int, str]], zones: dict[str, list[tuple[int, int]]]
) -> list[str]:
    """FONCTION PURE : les lignes rendues par le grep qui ne sont d'aucun site toléré.

    Pure, parce que c'est ce qui permet au contrôle positif de lui donner des
    lignes fabriquées dont il connaît la réponse, sans muter le dépôt.
    """
    fautives: list[str] = []
    for chemin, numero, texte in lignes:
        if any(motif.fullmatch(texte) for motif in TOLERANCES.get(chemin, ())):
            continue
        if chemin == SITE_D_IMPORT and texte == LIGNE_D_IMPORT:
            continue
        if chemin == FICHIER_DE_MIGRATION and any(
            debut <= numero <= fin for debut, fin in zones.get(chemin, [])
        ):
            continue
        fautives.append(f"{chemin}:{numero}: {texte.strip()[:120]}")
    return fautives


def _zones_du_depot() -> dict[str, list[tuple[int, int]]]:
    chemin = _RACINE / FICHIER_DE_MIGRATION
    return {FICHIER_DE_MIGRATION: zones_de_migration(FICHIER_DE_MIGRATION, chemin.read_text())}


# ─── LA GARDE ─────────────────────────────────────────────────────────────────


def test_le_nom_retire_ne_revient_nulle_part_hors_des_sites_toleres() -> None:
    """LA garde de la décision : `git grep -i` ne rend que les sites tolérés."""
    fautives = sites_non_toleres(_git_grep(), _zones_du_depot())
    assert not fautives, (
        "Le nom de l'ancien stockage objet est revenu dans le dépôt :\n  "
        + "\n  ".join(fautives)
        + "\nDites « le stockage objet » (présent) ou « l'ancien stockage objet » "
        "(passé), et les variables S3_* — §4.83 du registre."
    )


# ─── LES CONTRÔLES POSITIFS : UN ZÉRO N'A DE VALEUR QUE SI LE GREP VOIT ───────


def test_controle_positif_chaque_site_tolere_est_bien_rendu_par_le_grep() -> None:
    """Sans ce contrôle, un grep qui ne voit rien rendrait la garde verte.

    Chacun des trois sites tolérés doit être RENDU par le vrai `git grep` : le
    paquet dans chacun de ses trois fichiers, l'import, et la zone. Si l'un
    manque, c'est que le grep ne mesure plus ce qu'on croit — ou qu'une
    tolérance est devenue sans objet, et elle doit alors sortir de ce module.
    """
    lignes = _git_grep()
    fichiers = {chemin for chemin, _n, _t in lignes}
    for chemin in TOLERANCES:
        assert chemin in fichiers, f"le grep ne rend plus rien de {chemin}"
    assert (SITE_D_IMPORT, LIGNE_D_IMPORT) in {(c, t) for c, _n, t in lignes}, (
        "l'import unique de la bibliothèque cliente n'est plus rendu par le grep"
    )
    (debut, fin), = _zones_du_depot()[FICHIER_DE_MIGRATION]
    dans_la_zone = [n for c, n, _t in lignes if c == FICHIER_DE_MIGRATION and debut <= n <= fin]
    assert dans_la_zone, "la zone de migration ne porte plus aucun ancien nom"


def test_controle_positif_la_garde_rougit_sur_chaque_forme_hors_tolerance() -> None:
    """Des lignes fabriquées, dont on connaît la réponse, une par manière de fauter."""
    majuscules = NOM_RETIRE[:3].capitalize() + NOM_RETIRE[3:].upper()
    fabriquees = [
        # Le nom du produit en prose, dans un fichier quelconque.
        ("documentation/stores.md", 3, f"Le {majuscules} du pipeline."),
        # L'ancien champ, dans le code.
        ("src/agent/lexical.py", 9, f'    x = meta.get("{NOM_RETIRE}_url")'),
        # Une ancienne variable, dans la configuration.
        (".env.example", 4, f"{NOM_RETIRE.upper()}_ENDPOINT=seaweedfs:8333"),
        # Un SECOND import, ailleurs que sur le site unique.
        ("src/api/main.py", 1, LIGNE_D_IMPORT),
        # L'import unique, mais qui garde le nom de la classe.
        (SITE_D_IMPORT, 6, f"from {NOM_RETIRE} import {NOM_RETIRE.capitalize()}"),
        # La ligne du paquet, suivie d'un commentaire qui renomme le produit.
        ("requirements.txt", 28, f"{NOM_RETIRE}==7.2.20  # le client {majuscules}"),
        # Le paquet toléré, mais dans un fichier qui n'est pas le sien.
        ("Makefile", 2, f"{NOM_RETIRE}==7.2.20"),
        # Le registre, HORS de sa zone.
        (FICHIER_DE_MIGRATION, 1, f"{majuscules.upper()}_BUCKET"),
    ]
    toleree = [
        ("requirements.txt", 28, f"{NOM_RETIRE}==7.2.20"),
        (SITE_D_IMPORT, 6, LIGNE_D_IMPORT),
        (FICHIER_DE_MIGRATION, 11, f"| `{NOM_RETIRE.upper()}_BUCKET` | `S3_BUCKET` |"),
    ]
    zones = {FICHIER_DE_MIGRATION: [(10, 12)]}

    assert len(sites_non_toleres(fabriquees, zones)) == len(fabriquees), (
        "une ligne fautive a été tolérée : "
        f"{sorted(set(map(str, fabriquees)) - set(sites_non_toleres(fabriquees, zones)))}"
    )
    assert sites_non_toleres(toleree, zones) == []


def test_la_zone_de_migration_est_unique_bornee_et_dans_le_registre() -> None:
    """Une seule paire de balises dans tout le dépôt, et elle enclot une table.

    Deux zones, ou une zone qui grandit, seraient deux façons de soustraire du
    texte à la garde sans que personne ne le décide.
    """
    sortie = subprocess.run(
        ["git", "-C", str(_RACINE), "grep", "-n", "--no-color", "-e", BALISE_DEBUT,
         "-e", BALISE_FIN],
        capture_output=True,
        text=True,
        check=False,
    )
    assert sortie.returncode == 0, "aucune balise de la zone de migration n'est trouvée"
    porteurs = [ligne.split(":", 1)[0] for ligne in sortie.stdout.splitlines()]
    # Ce module-ci ASSEMBLE les balises et ne les écrit jamais d'un seul morceau.
    assert porteurs == [FICHIER_DE_MIGRATION, FICHIER_DE_MIGRATION], sortie.stdout

    zones = _zones_du_depot()[FICHIER_DE_MIGRATION]
    assert len(zones) == 1, zones
    (debut, fin), = zones
    assert fin - debut + 1 <= LIGNES_MAX_DE_LA_ZONE, (
        f"la zone de migration fait {fin - debut + 1} lignes : ce n'est plus une table"
    )


def test_une_balise_non_refermee_n_ouvre_aucune_zone() -> None:
    """Le sens sûr : une balise de fin oubliée laisse le reste du document LU."""
    texte = f"a\n<!-- {BALISE_DEBUT} -->\n{NOM_RETIRE}\nb\n"
    assert zones_de_migration("x.md", texte) == []
    fautives = sites_non_toleres(
        [(FICHIER_DE_MIGRATION, 3, NOM_RETIRE)],
        {FICHIER_DE_MIGRATION: zones_de_migration(FICHIER_DE_MIGRATION, texte)},
    )
    assert len(fautives) == 1
