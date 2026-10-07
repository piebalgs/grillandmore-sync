"""Approved manual Latvian product-description drafts."""

from __future__ import annotations

from src.descriptions.models import TranslationDraft


class ManualDraftNotFoundError(LookupError):
    """Raised when no approved manual draft exists for an import ID."""


_Q1200N = TranslationDraft(
    title="Weber Q 1200N gāzes grils",
    introduction=(
        "Weber Q 1200N ir kompakts un viegls gāzes grils ar pietiekami "
        "plašu grilēšanas virsmu, lai vienlaikus pagatavotu līdz 9 "
        "burgeriem. Augstais kupolveida vāks nodrošina vairāk vietas "
        "lielāku cepešu gatavošanai, bet efektīvais deglis un porcelāna "
        "emaljētās čuguna restes palīdz uzturēt vienmērīgu karstumu."
    ),
    benefits=(
        "Efektīvais deglis ātri sasniedz augstu temperatūru un palīdz "
        "uzturēt vienmērīgu karstumu.",
        "Augstais kupolveida vāks nodrošina vairāk vietas lielāku cepešu "
        "gatavošanai.",
        "Porcelāna emaljētās čuguna restes labi saglabā karstumu un ir "
        "piemērotas produktu apbrūnināšanai.",
        "Noņemamie sānu galdiņi nodrošina papildu darba virsmu un ir "
        "ievietojami grila pamatnē uzglabāšanai.",
        "Priekšpusē novietotā tauku savākšanas paplāte atvieglo tās "
        "izņemšanu un tīrīšanu.",
        "Vākā iebūvētais termometrs ļauj ērti sekot temperatūrai.",
        "Elektroniskā aizdedze ļauj degli iedegt ar vienu pogas "
        "nospiešanu.",
    ),
    technologies=(),
    suitability=(
        "Kompaktais un vieglais Weber Q 1200N ir piemērots vietām, kur "
        "svarīgi taupīgi izmantot pieejamo platību. Sānu rokturi atvieglo"
        "grila pārvietošanu, bet noņemamie sānu galdiņi nodrošina papildu "
        "darba vietu gatavošanas laikā."
    ),
    specifications_summary=(
        "Grilēšanas restes: 49 x 38 cm. Restu forma: kvadrātveida. "
        "Krāsa: melna. Izmēri ar atvērtu vāku: 64 x 56 x 105 cm. "
        "Izmēri ar aizvērtu vāku: 38 x 46 x 105 cm. "
        "Neto svars: 11 kg. Garantija: 5 gadi."
    ),
    conclusion=(
        "Weber Q 1200N apvieno kompaktus izmērus, praktisku grilēšanas "
        "virsmu un ērtai ikdienas gatavošanai nepieciešamās funkcijas."
    ),
    used_knowledge_keys=(),
    warnings=(),
    metadata={
        "source": "manual",
        "status": "approved",
    },
)


_MANUAL_DRAFTS: dict[str, TranslationDraft] = {
    "WEBERQ_1200N_BL": _Q1200N,
}


class ManualDraftRepository:
    """Provide approved manual drafts by Weber import ID."""

    def get(self, import_id: str) -> TranslationDraft:
        """Return the approved draft for one source product."""
        try:
            return _MANUAL_DRAFTS[import_id]
        except KeyError as exc:
            raise ManualDraftNotFoundError(
                f"Nav apstiprināta manuālā apraksta produktam {import_id}."
            ) from exc

    def translate(self, context) -> TranslationDraft:
        """Return an approved manual draft for a translation context."""
        return self.get(context.product.import_id)