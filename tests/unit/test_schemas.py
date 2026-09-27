import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from src.api.schemas import (
    ChatRequest,
    ChunkResult,
    ImageRef,
    SearchRequest,
    SectionElement,
    SourceSelectionRequest,
)
from tests.unit.test_contrat_champs_externes import CHAMP_URL_RETIRE


def test_search_request_valid() -> None:
    req = SearchRequest(question="Comment Docling gère les tableaux ?")
    # None = la valeur configurée : un défaut chiffré dans le schéma écrasait
    # le réglage du service sans que rien ne le signale.
    assert req.top_k is None  # valeur par défaut


def test_search_request_empty_question() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(question="")


def test_chunk_result_optional_fields() -> None:
    chunk = ChunkResult(
        chunk_id="abc_part0",
        element_id="abc",
        graph_node_id="abc",
        document="Texte du chunk",
        filename="doc.pdf",
        page_no=1,
        label="paragraph",
        distance=0.15,
    )
    assert chunk.media_url is None
    assert chunk.rerank_score is None


def test_source_selection_requires_at_least_one() -> None:
    with pytest.raises(ValidationError):
        SourceSelectionRequest(question="test", selected_element_ids=[])


def test_chat_request_defaults() -> None:
    req = ChatRequest(question="Ma question")
    assert req.stream is True
    assert req.chat_history == []
    assert req.selected_element_ids == []


# ─── LOT-43 : le nom que NOTRE API publie, et celui que le frontend lit ──────
#
# L'agent et le frontend sont déployés ENSEMBLE : le nom `media_url` est un
# contrat entre eux deux. Il sort par DEUX chemins — la réponse FastAPI, qui
# sérialise par alias, et le flux SSE, qui appelle `model_dump()` nu — et un
# alias de sérialisation rendu à l'ancien nom ne changerait que le premier.
# Nés des mutations M3b à M3e du §4.83, que seule la garde du nom attrapait.

_URL_MEDIA = "/media/images/rapport/aaaaaaaa01_picture.png"


# Des FABRIQUES, et non des instances : un objet construit à la collecte fait
# tomber le fichier entier en erreur (`rc=2`, suite interrompue) le jour où le
# champ change de nom, au lieu de rougir scène par scène — mutation M3a du §4.83.
_FABRIQUES: dict[str, Callable[[], BaseModel]] = {
    "ImageRef": lambda: ImageRef(element_id="aaaaaaaa01", media_url=_URL_MEDIA),
    "ChunkResult": lambda: ChunkResult(
        chunk_id="aaaaaaaa01_part0",
        element_id="aaaaaaaa01",
        graph_node_id="aaaaaaaa01",
        document="Figure.",
        filename="rapport.pdf",
        page_no=1,
        label="picture",
        distance=0.1,
        media_url=_URL_MEDIA,
    ),
    "SectionElement": lambda: SectionElement(
        node_id="aaaaaaaa01", label="picture", text="", sequence=0, media_url=_URL_MEDIA
    ),
}


@pytest.mark.parametrize("nom", list(_FABRIQUES))
def test_notre_api_publie_l_url_sous_media_url_par_les_deux_chemins(nom: str) -> None:
    modele = _FABRIQUES[nom]()
    for par_alias in (False, True):
        publie = modele.model_dump(by_alias=par_alias)
        assert publie.get("media_url") == _URL_MEDIA, (type(modele).__name__, par_alias, publie)
        assert CHAMP_URL_RETIRE not in publie
    schema = type(modele).model_json_schema(by_alias=True)["properties"]
    assert "media_url" in schema and CHAMP_URL_RETIRE not in schema


def test_le_frontend_lit_les_images_sous_les_noms_que_l_api_publie() -> None:
    """Les clés que `src/frontend/app.py` lit sur une image, relevées par AST.

    Elles doivent toutes être publiées par `ImageRef`, et `media_url` doit en
    être : un frontend qui relirait l'ancien nom afficherait des réponses sans
    une image, sans une erreur. `element_id` est le témoin du releveur.
    """
    source = (Path(__file__).resolve().parents[2] / "src" / "frontend" / "app.py").read_text()
    lues = {
        n.slice.value
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Subscript)
        and isinstance(n.value, ast.Name)
        and n.value.id == "img"
        and isinstance(n.slice, ast.Constant)
        and isinstance(n.slice.value, str)
    }
    assert "element_id" in lues, f"le releveur ne voit plus les lectures d'image : {lues}"
    publiees = set(ImageRef.model_json_schema(by_alias=True)["properties"])
    assert "media_url" in lues, lues
    assert lues <= publiees, f"le frontend lit {sorted(lues - publiees)}, que l'API ne publie pas"
