"""LOT-42 puis LOT-43 — `media_url` et `object_key`, et eux seuls, aux cinq sites.

POURQUOI CES SCÈNES EXISTENT.

`rag-ingestion-pipeline` a renommé le champ de l'URL en `media_url`, dans le
graphe ET dans les métadonnées ChromaDB, et publie une propriété nouvelle,
`object_key`, qui porte la clé nue de l'objet — §4.82 du registre. LOT-42 a
tenu la transition avec un repli sur l'ancien nom ; la réingestion faite, LOT-43
(§4.83) retire ce repli. Un seul état des stores est lu, et deux cas ne doivent
ni planter ni produire d'image :

- APRÈS : la purge fait `DROP SPACE` puis `CREATE TAG`, sans `ALTER` —
  `media_url` et `object_key` seuls, l'ancien nom n'existe PLUS dans le schéma.
  ChromaDB suit le même mouvement ;
- ANCIEN NOM SEUL : l'état d'avant la réingestion. Il n'est plus lu, et c'est
  ce qui rougit si le repli revient ;
- AUCUN : aucune des propriétés média.

Chaque état est rejoué aux cinq sites qui lisent le store — les propriétés d'un
sommet, la liste blanche du proxy, les enfants d'une section, les métadonnées
des deux chemins ChromaDB — et jusqu'aux trois conséquences qui comptent pour
le lecteur : l'image SERVIE par `/media`, la liste blanche NON VIDE, la
citation AVEC son image.

LE PRODUCTEUR EST DOUBLÉ, JAMAIS LE CONSOMMATEUR. Le double du graphe ne rend
pas des lignes toutes faites : il RÉPOND à la requête que le vrai code écrit, en
appliquant la sémantique `mesurée` le 25 septembre 2026 sur le graphd installé
(`vesoft/nebula-graphd:v3.6.0`, lecture seule, §4.82) — une propriété absente
du schéma d'un tag existant rend `__NULL__` en `RETURN`/`YIELD`, un `!= ""` sur
elle n'est pas vrai, et un `OR` est vrai dès qu'un membre l'est. Une requête que
le double ne sait pas modéliser le fait ÉCHOUER plutôt que de répondre au
hasard : c'est ce qui l'empêche de valider une forme qu'il ne comprend pas.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pytest

from src.agent import graph as graph_module
from src.agent import graph_context, lexical, retriever, stockage_objet
from src.api.schemas import ChunkResult, SectionContext
from tests.unit.test_contrat_champs_externes import CHAMP_URL_RETIRE

# Hôte FICTIF : le dépôt est public, aucun hôte de stockage réel n'y entre.
_URL = "http://stockage-fictif:9000/documents/images/rapport/bbbbbbbb02_picture.png"
_CLE = "images/rapport/bbbbbbbb02_picture.png"

_ID_SECTION = "5ec1104bcd"
_ID_TABLEAU = "aaaaaaaa01"
_ID_FIGURE = "bbbbbbbb02"

# L'état lu des propriétés média d'une illustration. Une propriété absente du
# dict est ABSENTE DU SCHÉMA : le double la rend NULL, comme le graphd.
ETATS: dict[str, dict[str, str]] = {
    "apres-media_url-et-object_key": {"media_url": _URL, "object_key": _CLE},
}
AUCUN: dict[str, str] = {}
# Les états qui ne doivent produire AUCUNE image : rien, ou l'ancien nom seul.
SANS_IMAGE: dict[str, dict[str, str]] = {
    "aucun": AUCUN,
    "ancien-nom-seul": {CHAMP_URL_RETIRE: _URL},
}

_PARAMETRES_ETATS = pytest.mark.parametrize("etat", list(ETATS), ids=list(ETATS))
_PARAMETRES_SANS_IMAGE = pytest.mark.parametrize("etat", list(SANS_IMAGE), ids=list(SANS_IMAGE))


# ─── Le double du graphe : il répond à la requête, il ne la devine pas ────────

_MATCH = re.compile(r"^MATCH \(n:(\w+)\) WHERE (.+?) RETURN (.+);$", re.S)
_CONDITION = re.compile(r'^n\.(\w+)\.(\w+) != ""$')
_COLONNE_MATCH = re.compile(r"^n\.(\w+)\.(\w+) AS (\w+)$")
_GO_ENFANTS = re.compile(
    r'^GO FROM "(\w+)" OVER PARENT_OF YIELD (.+?) \| ORDER BY \$-\.seq ASC;$', re.S
)
_COLONNE_GO = re.compile(r"^properties\(\$\$\)\.(\w+) AS (\w+)$")


def _vrai(valeur: Any) -> bool:
    """`valeur != ""` en nGQL : NULL n'est pas vrai (mesuré, §4.82)."""
    return valeur is not None and valeur != ""


class GrapheDouble:
    """Une section, un tableau qui porte la citation, une figure qui porte l'image."""

    def __init__(self, media_figure: dict[str, str]) -> None:
        self.noeuds: dict[str, dict[str, Any]] = {
            _ID_TABLEAU: {
                "tag": "Table",
                "props": {"label": "table", "text": "Relevés par trimestre.", "page_no": 12},
                "seq": 0,
            },
            _ID_FIGURE: {
                "tag": "Picture",
                "props": {"label": "picture", "text": "", "page_no": 12, **media_figure},
                "seq": 1,
            },
        }
        self.requetes: list[str] = []

    def execute(self, nql: str) -> list[dict[str, Any]]:
        self.requetes.append(nql)
        match = _MATCH.match(nql)
        if match:
            return self._match(*match.groups())
        go = _GO_ENFANTS.match(nql)
        if go:
            return self._enfants(*go.groups())
        raise AssertionError(f"requête que le double ne modélise pas : {nql!r}")

    def _match(self, tag: str, where: str, retour: str) -> list[dict[str, Any]]:
        conditions = []
        for membre in where.split(" OR "):
            cond = _CONDITION.match(membre.strip())
            assert cond and cond.group(1) == tag, f"condition non modélisée : {membre!r}"
            conditions.append(cond.group(2))
        colonnes = []
        for morceau in retour.split(","):
            col = _COLONNE_MATCH.match(morceau.strip())
            assert col and col.group(1) == tag, f"colonne non modélisée : {morceau!r}"
            colonnes.append((col.group(2), col.group(3)))
        lignes = []
        for noeud in self.noeuds.values():
            if noeud["tag"] != tag:
                continue
            props = noeud["props"]
            if any(_vrai(props.get(p)) for p in conditions):
                lignes.append({alias: props.get(p) for p, alias in colonnes})
        return lignes

    def _enfants(self, parent: str, yield_: str) -> list[dict[str, Any]]:
        if parent != _ID_SECTION:
            return []
        colonnes: list[tuple[str, str]] = []
        for morceau in yield_.split(","):
            morceau = morceau.strip()
            if morceau in ("dst(edge) AS child_id", "properties(edge).sequence AS seq"):
                continue
            col = _COLONNE_GO.match(morceau)
            assert col, f"colonne non modélisée : {morceau!r}"
            colonnes.append((col.group(1), col.group(2)))
        lignes = []
        for vid, noeud in sorted(self.noeuds.items(), key=lambda kv: kv[1]["seq"]):
            ligne = {"child_id": vid, "seq": noeud["seq"]}
            ligne.update({alias: noeud["props"].get(p) for p, alias in colonnes})
            lignes.append(ligne)
        return lignes


def _brancher(monkeypatch: pytest.MonkeyPatch, graphe: GrapheDouble) -> None:
    monkeypatch.setattr(graph_context, "_execute", graphe.execute)
    stockage_objet._allowed_objects.cache_clear()


@pytest.fixture(autouse=True)
def _liste_blanche_neuve() -> Any:
    stockage_objet._allowed_objects.cache_clear()
    yield
    stockage_objet._allowed_objects.cache_clear()


def test_controle_positif_le_double_refuse_une_forme_quil_ne_modelise_pas() -> None:
    """Sans ce contrôle, un double permissif validerait n'importe quelle requête."""
    graphe = GrapheDouble(ETATS["apres-media_url-et-object_key"])
    with pytest.raises(AssertionError, match="non modélisée"):
        graphe.execute(
            'MATCH (n:Picture) WHERE n.Picture.media_url != "" AND 1 == 1 RETURN 1 AS x;'
        )
    # Et il applique bien la sémantique mesurée : une propriété absente n'est
    # jamais vraie, et elle rend NULL.
    lignes = graphe.execute(
        'MATCH (n:Picture) WHERE n.Picture.s3_url != "" '
        "RETURN n.Picture.s3_url AS s3_url;"
    )
    assert lignes == []


# ─── Site 1 — la liste blanche du proxy : NON VIDE dans l'état lu ────────────


@_PARAMETRES_ETATS
def test_la_liste_blanche_porte_la_cle_dans_chaque_etat(
    etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _brancher(monkeypatch, GrapheDouble(ETATS[etat]))
    assert graph_context.media_object_names() == {_CLE}


@_PARAMETRES_SANS_IMAGE
def test_la_liste_blanche_sans_aucun_champ_est_vide_sans_lever(
    etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    graphe = GrapheDouble(SANS_IMAGE[etat])
    _brancher(monkeypatch, graphe)
    assert graph_context.media_object_names() == set()
    assert graphe.requetes, "le double n'a été traversé par aucune requête : montage faux"


# ─── L'image SERVIE par /media, de la liste blanche au client objet ───────────


class _Reponse:
    def __init__(self, donnees: bytes) -> None:
        self._donnees = donnees

    def read(self) -> bytes:
        return self._donnees

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class _ClientObjet:
    """Le seau `documents` porte l'objet `_CLE`, et rien d'autre."""

    def __init__(self) -> None:
        self.demandes: list[tuple[str, str]] = []

    def get_object(self, seau: str, cle: str) -> _Reponse:
        self.demandes.append((seau, cle))
        if (seau, cle) != ("documents", _CLE):
            raise KeyError(cle)
        return _Reponse(b"\x89PNG-figure")


def _servir(monkeypatch: pytest.MonkeyPatch, chemin: str) -> bytes | None:
    """Ce que fait la route `GET /media/{object_name}` : `get_object_bytes`."""
    client = _ClientObjet()
    monkeypatch.setattr(stockage_objet, "_get_client_s3", lambda: client)
    monkeypatch.setattr(stockage_objet.settings, "restrict_media_to_graph", True)
    monkeypatch.setattr(stockage_objet.settings, "s3_bucket", "documents")
    assert chemin.startswith("/media/"), f"l'image ne passe pas par le proxy : {chemin}"
    return stockage_objet.get_object_bytes(chemin.removeprefix("/media/"))


def _section(monkeypatch: pytest.MonkeyPatch, graphe: GrapheDouble) -> SectionContext:
    _brancher(monkeypatch, graphe)
    elements = graph_context._to_elements(graph_context._get_children(_ID_SECTION))
    return SectionContext(
        element_id=_ID_TABLEAU,
        section_id=_ID_SECTION,
        breadcrumbs=[],
        elements=elements,
        markdown=graph_context._build_markdown([], elements, ""),
        filename="rapport.pdf",
        collection="Relevés trimestriels",
        section_title="Résultats",
    )


_REPONSE = f"Les relevés progressent au dernier trimestre [src:{_ID_TABLEAU}]."


# ─── Site 3 — les enfants d'une section : la citation AVEC son image ──────────


@_PARAMETRES_ETATS
def test_la_citation_du_graphe_porte_son_image_dans_chaque_etat(
    etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    contexte = _section(monkeypatch, GrapheDouble(ETATS[etat]))
    assert f"[img:{_ID_FIGURE}]" in contexte.markdown, "la figure n'est pas soumise au modèle"

    citations, images = graph_module.resolve_citations(_REPONSE, [contexte], [])

    assert [c.element_id for c in citations] == [_ID_TABLEAU]
    assert [(i.element_id, i.media_url) for i in images] == [(_ID_FIGURE, f"/media/{_CLE}")]


@_PARAMETRES_ETATS
def test_l_image_citee_est_servie_par_media_dans_chaque_etat(
    etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De bout en bout : la liste blanche ET la clé de l'ImageRef viennent du même état."""
    graphe = GrapheDouble(ETATS[etat])
    contexte = _section(monkeypatch, graphe)
    _citations, images = graph_module.resolve_citations(_REPONSE, [contexte], [])
    assert images, "aucune image citée : la scène ne mesure plus le proxy"

    assert _servir(monkeypatch, images[0].media_url) == b"\x89PNG-figure"


@_PARAMETRES_SANS_IMAGE
def test_aucun_champ_media_ni_image_ni_plantage(
    etat: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """AUCUN, ou l'ancien nom seul : la citation reste, l'image disparaît, rien ne lève."""
    contexte = _section(monkeypatch, GrapheDouble(SANS_IMAGE[etat]))
    assert "[img:" not in contexte.markdown

    with caplog.at_level(logging.DEBUG):
        citations, images = graph_module.resolve_citations(_REPONSE, [contexte], [])

    assert [c.element_id for c in citations] == [_ID_TABLEAU]
    assert images == []
    assert _servir(monkeypatch, f"/media/{_CLE}") is None


# ─── Site 1 bis — les propriétés d'un sommet ──────────────────────────────────


class _Noeud:
    def __init__(self, props: dict[str, Any]) -> None:
        self._props = props

    def tags(self) -> list[str]:
        return ["Picture"]

    def properties(self, _tag: str) -> dict[str, Any]:
        return {k: _Valeur(v) for k, v in self._props.items()}


class _Valeur:
    def __init__(self, v: Any) -> None:
        self.v = v

    def is_string(self) -> bool:
        return isinstance(self.v, str)

    def as_string(self) -> str:
        return str(self.v)

    def is_int(self) -> bool:
        return isinstance(self.v, int)

    def as_int(self) -> int:
        return int(self.v)

    def is_null(self) -> bool:
        return self.v is None

    def is_vertex(self) -> bool:
        return True

    def as_node(self) -> _Noeud:
        assert isinstance(self.v, _Noeud)
        return self.v


class _Resultat:
    def __init__(self, noeud: _Noeud) -> None:
        self._noeud = noeud

    def row_size(self) -> int:
        return 1

    def row_values(self, _i: int) -> list[_Valeur]:
        return [_Valeur(self._noeud)]


def _proprietes(monkeypatch: pytest.MonkeyPatch, media: dict[str, str]) -> dict[str, Any]:
    noeud = _Noeud({"label": "picture", "text": "", "page_no": 3, **media})
    monkeypatch.setattr(graph_context, "_execute_raw", lambda _nql: _Resultat(noeud))
    return graph_context._get_node_properties(_ID_FIGURE)


@_PARAMETRES_ETATS
def test_les_proprietes_du_sommet_portent_url_et_cle_dans_chaque_etat(
    etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    props = _proprietes(monkeypatch, ETATS[etat])
    assert props["tag"] == "Picture"
    assert props["media_url"] == _URL
    assert props["object_key"] == (ETATS[etat].get("object_key"))


@_PARAMETRES_SANS_IMAGE
def test_les_proprietes_du_sommet_sans_champ_media(
    etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    props = _proprietes(monkeypatch, SANS_IMAGE[etat])
    assert props["tag"] == "Picture"
    assert props["media_url"] is None
    assert props["object_key"] is None
    assert CHAMP_URL_RETIRE not in props


# ─── Sites 4 et 5 — les métadonnées ChromaDB, sur les deux chemins ────────────


def _meta(media: dict[str, str]) -> dict[str, Any]:
    return {
        "element_id": _ID_FIGURE,
        "graph_node_id": _ID_FIGURE,
        "filename": "rapport.pdf",
        "collection": "Relevés trimestriels",
        "section_title": "Résultats",
        "page_no": 12,
        "label": "picture",
        **media,
    }


def _lexical(media: dict[str, str]) -> ChunkResult:
    return lexical.chunk_from_record(f"{_ID_FIGURE}_part0", "Figure : relevés.", _meta(media))


def _dense(media: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> ChunkResult:
    class _Embedder:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            self.device = None

        def encode(self, _q: str) -> Any:
            import numpy

            return numpy.zeros(3)

    class _Collection:
        def query(self, **_k: Any) -> dict[str, Any]:
            return {
                "ids": [[f"{_ID_FIGURE}_part0"]],
                "documents": [["Figure : relevés."]],
                "metadatas": [[_meta(media)]],
                "distances": [[0.2]],
            }

    monkeypatch.setattr(retriever, "SentenceTransformer", _Embedder)
    monkeypatch.setattr(retriever, "verifier_modele_embedding", lambda: None)
    monkeypatch.setattr(retriever, "_get_chroma_collection", lambda: _Collection())
    retriever._get_embedding_model.cache_clear()
    try:
        chunks = retriever._dense_search("les relevés", 5)
    finally:
        retriever._get_embedding_model.cache_clear()
    assert len(chunks) == 1, "le montage dense ne rend plus de chunk : scène morte"
    return chunks[0]


_CHEMINS = ("lexical", "dense")


def _chunk(chemin: str, media: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> ChunkResult:
    return _lexical(media) if chemin == "lexical" else _dense(media, monkeypatch)


@pytest.mark.parametrize("chemin", _CHEMINS)
@_PARAMETRES_ETATS
def test_le_chunk_chromadb_porte_son_image_servie_dans_chaque_etat(
    chemin: str, etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le chunk cité porte son image, et c'est l'objet du seau qui est servi."""
    chunk = _chunk(chemin, ETATS[etat], monkeypatch)
    assert chunk.media_url == _URL

    reponse = f"La figure résume les relevés [img:{_ID_FIGURE}] [src:{_ID_FIGURE}]."
    contexte = SectionContext(
        element_id=_ID_FIGURE,
        section_id=_ID_SECTION,
        breadcrumbs=[],
        elements=[],
        markdown=f"Figure : relevés. [src:{_ID_FIGURE}] [img:{_ID_FIGURE}]",
        filename="rapport.pdf",
        collection="Relevés trimestriels",
        section_title="Résultats",
    )
    citations, images = graph_module.resolve_citations(reponse, [contexte], [chunk])

    assert [c.element_id for c in citations] == [_ID_FIGURE]
    assert [(i.element_id, i.media_url) for i in images] == [(_ID_FIGURE, f"/media/{_CLE}")]
    _brancher(monkeypatch, GrapheDouble(ETATS[etat]))
    assert _servir(monkeypatch, images[0].media_url) == b"\x89PNG-figure"


@pytest.mark.parametrize("chemin", _CHEMINS)
@_PARAMETRES_SANS_IMAGE
def test_le_chunk_chromadb_sans_champ_media_ne_plante_pas(
    chemin: str, etat: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunk = _chunk(chemin, SANS_IMAGE[etat], monkeypatch)
    assert chunk.media_url is None
    assert chunk.object_key is None
    assert chunk.element_id == _ID_FIGURE


# ─── `object_key` d'abord, la clé déduite de l'URL à défaut ───────────────────
#
# Dans l'état APRÈS du contrat, `object_key` et la clé déduite de l'URL coïncident :
# les scènes ci-dessus ne peuvent donc pas dire LAQUELLE a été lue. Celles-ci le
# peuvent, parce qu'elles les font diverger. Le cas n'est pas d'école : le §4.62
# a mesuré qu'une URL en virtual-host style est décodée de façon cohérente et
# FAUSSE par la règle positionnelle — `object_key` est ce qui nous en affranchit.

_URL_VIRTUAL_HOST = "http://documents.stockage-fictif:9000/images/rapport/bbbbbbbb02_picture.png"


def test_object_key_l_emporte_sur_la_cle_deduite_de_l_url(monkeypatch: pytest.MonkeyPatch) -> None:
    media = {"media_url": _URL_VIRTUAL_HOST, "object_key": _CLE}
    assert stockage_objet.object_name_from_url(_URL_VIRTUAL_HOST) != _CLE, (
        "l'URL de la scène se décode juste : elle ne départage plus rien"
    )
    _brancher(monkeypatch, GrapheDouble(media))
    assert graph_context.media_object_names() == {_CLE}

    contexte = _section(monkeypatch, GrapheDouble(media))
    _citations, images = graph_module.resolve_citations(_REPONSE, [contexte], [])
    assert [i.media_url for i in images] == [f"/media/{_CLE}"]

    for chemin in _CHEMINS:
        chunk = _chunk(chemin, media, monkeypatch)
        assert chunk.object_key == _CLE, chemin
        # Et c'est la clé PUBLIÉE qui fait le chemin `/media` d'une image venue
        # d'un chunk : né de la mutation M3j, qui survivait sans cette ligne.
        reponse = f"La figure [img:{_ID_FIGURE}] [src:{_ID_FIGURE}]."
        contexte = SectionContext(
            element_id=_ID_FIGURE,
            section_id=_ID_SECTION,
            breadcrumbs=[],
            elements=[],
            markdown=f"Figure. [src:{_ID_FIGURE}] [img:{_ID_FIGURE}]",
            filename="rapport.pdf",
            collection="Relevés trimestriels",
            section_title="Résultats",
        )
        _c, images_du_chunk = graph_module.resolve_citations(reponse, [contexte], [chunk])
        assert [i.media_url for i in images_du_chunk] == [f"/media/{_CLE}"], chemin


def test_to_media_path_prefere_la_cle_publiee() -> None:
    assert stockage_objet.to_media_path(_URL_VIRTUAL_HOST, _CLE) == f"/media/{_CLE}"
    # Sans clé publiée, la règle d'aujourd'hui, inchangée.
    assert stockage_objet.to_media_path(_URL) == f"/media/{_CLE}"
    assert stockage_objet.to_media_path(_URL, None) == f"/media/{_CLE}"


def test_la_cle_d_objet_ne_fuit_pas_dans_notre_api() -> None:
    """NOTRE réponse publie l'URL sous `media_url` depuis LOT-43, et jamais la clé."""
    chunk = _lexical(ETATS["apres-media_url-et-object_key"])
    assert chunk.object_key == _CLE
    assert "object_key" not in chunk.model_dump()
    assert chunk.model_dump()["media_url"] == _URL
    assert CHAMP_URL_RETIRE not in chunk.model_dump()
