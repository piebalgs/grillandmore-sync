"""Approved manual Latvian product-description drafts."""

from __future__ import annotations

from src.descriptions.models import TranslationDraft


class ManualDraftNotFoundError(LookupError):
    """Raised when no approved manual draft exists for an import ID."""


_Q1200N = TranslationDraft(
    title="Weber Q 1200N gāzes grils",
    introduction=(
        "Weber Q 1200N ir kompakts un viegls gāzes grils, kas nodrošina "
        "pietiekami plašu grilēšanas virsmu līdz 9 burgeriem. Augsts "
        "kupolveida vāks palielina vietu zem vāka, tāpēc grilā iespējams "
        "gatavot arī lielākus cepešus. Efektīvais deglis un porcelāna "
        "emaljētas čuguna restes palīdz nodrošināt vienmērīgu karstumu "
        "un paredzamu gatavošanas rezultātu."
    ),
    benefits=(
        "Plaša grilēšanas virsma ļauj vienlaikus pagatavot līdz 9 burgeriem.",
        "Augsts kupolveida vāks nodrošina vairāk vietas lielāku cepešu "
        "gatavošanai.",
        "Efektīvais deglis nodrošina ātru un vienmērīgu augstu karstumu.",
        "Porcelāna emaljētas čuguna restes labi saglabā karstumu "
        "apbrūnināšanai.",
        "Noņemamie sānu galdiņi nodrošina papildu darba virsmu un ir "
        "ievietojami grila pamatnē uzglabāšanai.",
        "Priekšpusē novietotā tauku savākšanas paplāte atvieglo tās "
        "izņemšanu un tīrīšanu.",
        "Vākā iebūvēts termometrs ļauj ērti sekot temperatūrai.",
        "Elektroniskā aizdedze ļauj degli iedegt ar vienu pogas nospiešanu.",
    ),
    technologies=(),
    suitability=(
        "Kompaktais un vieglais Weber Q 1200N ir piemērots vietām, kur "
        "svarīgi taupīgi izmantot pieejamo platību. Sānu rokturi atvieglo "
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
        "Weber Q 1200N apvieno kompaktus izmērus ar praktisku grilēšanas "
        "virsmu un funkcijām ērtai ikdienas gatavošanai."
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