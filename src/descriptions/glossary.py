"""Weber terminology glossary for Latvian product descriptions.

This module does not translate complete product descriptions. It provides:
- approved translations for recurring Weber and barbecue terms;
- Latvian labels and values for structured specifications;
- deterministic terminology replacement for later translator/formatter modules.

The English source text remains unchanged in parser.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class GlossaryTerm:
    """One approved terminology entry."""

    source: str
    target: str
    note: str = ""


# Brand names and registered product-system names that must remain unchanged.
PROTECTED_TERMS: frozenset[str] = frozenset(
    {
        "Weber",
        "Weber Traveler",
        "Weber Connect",
        "Weber Connect Smart Hub",
        "Weber Works",
        "WEBER CRAFTED",
        "Weber Crafted",
        "Gourmet BBQ System",
        "GBS",
        "Flavorizer",
        "Flavorizer Bars",
        "Infinity Ignition",
        "Snap-Jet Ignition",
        "PureBlu",
        "Sear Zone",
        "Boost Burner",
        "Stealth",
    }
)


# Approved recurring terminology.
# Longer and more specific phrases should be listed before shorter ones.
TERMS: tuple[GlossaryTerm, ...] = (
    GlossaryTerm(
        "Weber Crafted Gourmet BBQ System",
        "Weber Crafted Gourmet BBQ System",
        "Produktu sistēmas nosaukumu netulko.",
    ),
    GlossaryTerm(
        "Weber Crafted",
        "Weber Crafted",
        "Produktu sistēmas nosaukumu netulko.",
    ),
    GlossaryTerm(
        "Gourmet BBQ System",
        "Gourmet BBQ System (GBS)",
        "Pirmajā pieminēšanas reizē var pievienot saīsinājumu GBS.",
    ),
    GlossaryTerm(
        "Weber Connect Smart Hub",
        "Weber Connect Smart Hub",
        "Ierīces nosaukumu netulko.",
    ),
    GlossaryTerm(
        "Weber Connect App",
        "Weber Connect lietotne",
    ),
    GlossaryTerm(
        "Weber Works side rails",
        "Weber Works sānu stiprinājuma sliedes",
    ),
    GlossaryTerm(
        "Weber Works side table",
        "Weber Works sānu galdiņš",
    ),
    GlossaryTerm(
        "Flavorizer Bars",
        "Flavorizer aromatizējošās plāksnes",
        "Saglabā Weber preču zīmes nosaukumu un pievieno skaidrojošu latviskojumu.",
    ),
    GlossaryTerm(
        "Flavorizer bars",
        "Flavorizer aromatizējošās plāksnes",
    ),
    GlossaryTerm(
        "Flavorizer® Bars",
        "Flavorizer® aromatizējošās plāksnes",
    ),
    GlossaryTerm(
        "Flavorizer™ bars",
        "Flavorizer™ aromatizējošās plāksnes",
    ),
    GlossaryTerm(
        "Infinity Ignition",
        "Infinity aizdedzes sistēma",
    ),
    GlossaryTerm(
        "Snap-Jet Ignition",
        "Snap-Jet aizdedzes sistēma",
    ),
    GlossaryTerm(
        "Sear Zone",
        "Sear Zone augstas temperatūras zona",
    ),
    GlossaryTerm(
        "Boost Burners",
        "Boost pastiprinātas jaudas degļi",
    ),
    GlossaryTerm(
        "Boost Burner",
        "Boost pastiprinātas jaudas deglis",
    ),
    GlossaryTerm(
        "PureBlu burners",
        "PureBlu degļi",
    ),
    GlossaryTerm(
        "PureBlu burner",
        "PureBlu deglis",
    ),
    GlossaryTerm(
        "porcelain-enamelled cast-iron cooking grates",
        "porcelāna emaljētas čuguna gatavošanas restes",
    ),
    GlossaryTerm(
        "porcelain-enameled cast-iron cooking grates",
        "porcelāna emaljētas čuguna gatavošanas restes",
    ),
    GlossaryTerm(
        "porcelain-enamelled cast-iron grates",
        "porcelāna emaljētas čuguna restes",
    ),
    GlossaryTerm(
        "porcelain-enameled cast-iron grates",
        "porcelāna emaljētas čuguna restes",
    ),
    GlossaryTerm(
        "porcelain-enamelled cooking grate",
        "porcelāna emaljētas gatavošanas restes",
    ),
    GlossaryTerm(
        "porcelain-enameled cooking grate",
        "porcelāna emaljētas gatavošanas restes",
    ),
    GlossaryTerm(
        "stainless steel cooking grates",
        "nerūsējošā tērauda gatavošanas restes",
    ),
    GlossaryTerm(
        "stainless-steel cooking grates",
        "nerūsējošā tērauda gatavošanas restes",
    ),
    GlossaryTerm(
        "cast-iron cooking grates",
        "čuguna gatavošanas restes",
    ),
    GlossaryTerm(
        "cooking grates",
        "gatavošanas restes",
    ),
    GlossaryTerm(
        "cooking grate",
        "gatavošanas reste",
    ),
    GlossaryTerm(
        "warming rack",
        "sildīšanas reste",
    ),
    GlossaryTerm(
        "secondary cooking grate",
        "papildu gatavošanas reste",
    ),
    GlossaryTerm(
        "high-dome lid",
        "augsts kupolveida vāks",
    ),
    GlossaryTerm(
        "porcelain-enamelled lid",
        "porcelāna emaljēts vāks",
    ),
    GlossaryTerm(
        "porcelain-enameled lid",
        "porcelāna emaljēts vāks",
    ),
    GlossaryTerm(
        "built-in lid thermometer",
        "vākā iebūvēts termometrs",
    ),
    GlossaryTerm(
        "integrated digital thermometer",
        "integrēts digitālais termometrs",
    ),
    GlossaryTerm(
        "grease management system",
        "tauku savākšanas sistēma",
    ),
    GlossaryTerm(
        "removable grease tray",
        "izņemama tauku savākšanas paplāte",
    ),
    GlossaryTerm(
        "pull-out enamelled grease tray",
        "izvelkama emaljēta tauku savākšanas paplāte",
    ),
    GlossaryTerm(
        "side burner",
        "sānu deglis",
    ),
    GlossaryTerm(
        "infrared sear zone",
        "infrasarkanā augstas temperatūras apcepšanas zona",
    ),
    GlossaryTerm(
        "rotisserie",
        "rotējošais iesms",
    ),
    GlossaryTerm(
        "cook box",
        "grila korpuss",
    ),
    GlossaryTerm(
        "heat deflector",
        "siltuma deflektors",
    ),
    GlossaryTerm(
        "tool hooks",
        "piederumu āķi",
    ),
    GlossaryTerm(
        "side tables",
        "sānu galdiņi",
    ),
    GlossaryTerm(
        "side table",
        "sānu galdiņš",
    ),
    GlossaryTerm(
        "locking swivel casters",
        "grozāmi riteņi ar fiksatoriem",
    ),
    GlossaryTerm(
        "all-weather wheels",
        "pret laikapstākļiem izturīgi riteņi",
    ),
    GlossaryTerm(
        "propane tank",
        "gāzes balons",
    ),
    GlossaryTerm(
        "gas canister",
        "gāzes baloniņš",
    ),
    GlossaryTerm(
        "gas bottle",
        "gāzes balons",
    ),
    GlossaryTerm(
        "food probe",
        "ēdiena temperatūras zonde",
    ),
    GlossaryTerm(
        "grillware",
        "grilēšanas piederumi",
    ),
    GlossaryTerm(
        "griddle",
        "cepšanas plātne",
    ),
    GlossaryTerm(
        "griddle insert",
        "cepšanas plātnes ieliktnis",
    ),
    GlossaryTerm(
        "barbecue",
        "grils",
    ),
    GlossaryTerm(
        "gas grill",
        "gāzes grils",
    ),
)


# Latvian labels for parser.py ProductDescription.specifications keys.
SPECIFICATION_LABELS_LV: Mapping[str, str] = {
    "barbecue_type": "Grila veids",
    "guarantee": "Garantija",
    "grate_size": "Gatavošanas restes izmērs",
    "grate_shape": "Gatavošanas restes forma",
    "hamburger_capacity": "Burgeru ietilpība",
    "color": "Krāsa",
    "dimensions_open_lid": "Izmēri ar atvērtu vāku",
    "dimensions_closed_lid": "Izmēri ar aizvērtu vāku",
    "net_weight": "Neto svars",
    "packaging_dimensions": "Iepakojuma izmēri",
    "gross_weight": "Bruto svars",
}


SPECIFICATION_VALUES_LV: Mapping[str, Mapping[str, str]] = {
    "barbecue_type": {
        "GAS": "Gāzes grils",
        "ELECTRIC": "Elektriskais grils",
        "CHARCOAL": "Kokogļu grils",
        "PELLET": "Granulu grils",
    },
    "grate_shape": {
        "SQUARE": "Taisnstūrveida",
        "ROUND": "Apaļa",
        "OVAL": "Ovāla",
    },
    "color": {
        "Black": "Melna",
        "BLACK": "Melna",
        "Stainless Steel": "Nerūsējošais tērauds",
    },
}


_GUARANTEE_PATTERN = re.compile(r"^(?P<years>\d+)_L$", re.IGNORECASE)


def translate_specification_value(key: str, value: str) -> str:
    """Translate one structured specification value where a rule is known."""
    cleaned = " ".join(str(value).replace("\u00a0", " ").split())
    if not cleaned:
        return ""

    if key == "guarantee":
        match = _GUARANTEE_PATTERN.fullmatch(cleaned)
        if match:
            years = int(match.group("years"))
            return f"{years} gadu ierobežotā garantija"

    return SPECIFICATION_VALUES_LV.get(key, {}).get(cleaned, cleaned)


def specification_label(key: str) -> str:
    """Return the approved Latvian label for a specification key."""
    return SPECIFICATION_LABELS_LV.get(key, key.replace("_", " ").capitalize())


def translate_specifications(
    specifications: Mapping[str, str],
) -> dict[str, tuple[str, str]]:
    """Return specifications as key -> (Latvian label, translated value)."""
    return {
        key: (
            specification_label(key),
            translate_specification_value(key, value),
        )
        for key, value in specifications.items()
        if value
    }


def apply_approved_terms(text: str) -> str:
    """Apply approved terminology to text without translating full sentences.

    Replacement is case-insensitive and longest phrases are processed first.
    This helper is intended for controlled drafts and diagnostics. The future
    translator must still produce natural Latvian sentence structure.
    """
    result = str(text)
    ordered_terms = sorted(TERMS, key=lambda item: len(item.source), reverse=True)

    for term in ordered_terms:
        pattern = re.compile(
            rf"(?<![\w-]){re.escape(term.source)}(?![\w-])",
            re.IGNORECASE,
        )
        result = pattern.sub(lambda _match, target=term.target: target, result)

    return result


def glossary_as_dict() -> dict[str, str]:
    """Return a simple source-to-target mapping for reports and tests."""
    return {term.source: term.target for term in TERMS}


def main() -> int:
    """Print a small diagnostic preview."""
    examples = (
        "Stainless steel Flavorizer® Bars boost grilled flavor",
        "Snap-Jet Ignition for one hand lighting of individual burners",
        "Porcelain-enameled cast-iron cooking grates retain heat for searing",
    )

    print(f"Apstiprināti termini: {len(TERMS)}")
    print()
    for source in examples:
        print(f"EN: {source}")
        print(f"LV termini: {apply_approved_terms(source)}")
        print()

    print("Specifikāciju piemēri:")
    for key, value in (
        ("barbecue_type", "GAS"),
        ("guarantee", "5_L"),
        ("grate_shape", "SQUARE"),
        ("color", "Black"),
    ):
        print(
            f"- {specification_label(key)}: "
            f"{translate_specification_value(key, value)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
