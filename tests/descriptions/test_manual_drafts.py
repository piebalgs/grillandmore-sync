from __future__ import annotations

import pytest

from src.descriptions.manual_drafts import (
    ManualDraftNotFoundError,
    ManualDraftRepository,
)
from src.descriptions.models import TranslationDraft


def test_repository_returns_q1200n_manual_draft() -> None:
    repository = ManualDraftRepository()

    draft = repository.get("WEBERQ_1200N_BL")

    assert isinstance(draft, TranslationDraft)
    assert draft.title == "Weber Q 1200N gāzes grils"
    assert "līdz 9 burgeriem" in draft.introduction
    assert "hamburger_capacity" not in draft.specifications_summary


def test_repository_rejects_unknown_import_id() -> None:
    repository = ManualDraftRepository()

    with pytest.raises(
        ManualDraftNotFoundError,
        match="UNKNOWN_PRODUCT",
    ):
        repository.get("UNKNOWN_PRODUCT")
def test_repository_can_translate_context_by_import_id() -> None:
    repository = ManualDraftRepository()

    class Product:
        import_id = "WEBERQ_1200N_BL"

    class Context:
        product = Product()

    draft = repository.translate(Context())

    assert isinstance(draft, TranslationDraft)
    assert draft.title == "Weber Q 1200N gāzes grils"