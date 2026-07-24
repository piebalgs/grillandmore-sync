"""Knowledge-base API for the GrillAndMore description engine.

Only verified records are returned by default. Draft records may be inspected
explicitly during editorial work, but they must not be used for automatic
publication until their source and wording have been reviewed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import re
from typing import Iterable, Iterator

from src.descriptions.models import KnowledgeCategory, KnowledgeItem


class KnowledgeBaseError(ValueError):
    """Base exception for knowledge-base integrity problems."""


class DuplicateKnowledgeKeyError(KnowledgeBaseError):
    """Raised when two records use the same canonical key."""


class DuplicateKnowledgeAliasError(KnowledgeBaseError):
    """Raised when one alias points to multiple records."""


class UnknownKnowledgeItemError(KeyError):
    """Raised when a requested item cannot be found."""


def _normalize(value: str) -> str:
    """Normalize keys and queries for case-insensitive matching."""
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _validate_item(item: KnowledgeItem) -> None:
    """Validate mandatory fields before registration."""
    required = {
        "key": item.key,
        "translation": item.translation,
        "short_description": item.short_description,
        "explanation": item.explanation,
        "customer_benefit": item.customer_benefit,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise KnowledgeBaseError(
            f"Ierakstam “{item.key or '<bez atslēgas>'}” trūkst lauku: "
            f"{', '.join(missing)}"
        )

    if item.verified:
        if not item.source.strip():
            raise KnowledgeBaseError(
                f"Verificētam ierakstam “{item.key}” nav norādīts avots."
            )
        if not item.evidence:
            raise KnowledgeBaseError(
                f"Verificētam ierakstam “{item.key}” nav pierādījuma."
            )
        if item.last_reviewed is None:
            raise KnowledgeBaseError(
                f"Verificētam ierakstam “{item.key}” nav pārskatīšanas datuma."
            )


@dataclass(frozen=True, slots=True)
class KnowledgeBaseStatistics:
    """Summary information about registered knowledge records."""

    total: int
    verified: int
    draft: int
    categories: dict[str, int]


class KnowledgeBase:
    """In-memory knowledge registry with a stable public API."""

    def __init__(self, items: Iterable[KnowledgeItem] = ()) -> None:
        self._items: dict[str, KnowledgeItem] = {}
        self._aliases: dict[str, str] = {}
        for item in items:
            self.register(item)

    def register(self, item: KnowledgeItem) -> None:
        """Register and validate one knowledge record."""
        _validate_item(item)
        normalized_key = _normalize(item.key)

        if normalized_key in self._items:
            raise DuplicateKnowledgeKeyError(
                f"Dublēta zināšanu bāzes atslēga: “{item.key}”."
            )
        if normalized_key in self._aliases:
            raise DuplicateKnowledgeAliasError(
                f"Atslēga “{item.key}” jau izmantota kā cita ieraksta alias."
            )

        normalized_aliases: list[str] = []
        for alias in item.aliases:
            normalized_alias = _normalize(alias)
            if not normalized_alias or normalized_alias == normalized_key:
                continue
            if normalized_alias in self._items:
                raise DuplicateKnowledgeAliasError(
                    f"Alias “{alias}” sakrīt ar citas vienības atslēgu."
                )
            if normalized_alias in self._aliases:
                raise DuplicateKnowledgeAliasError(
                    f"Alias “{alias}” jau piesaistīts citam ierakstam."
                )
            normalized_aliases.append(normalized_alias)

        self._items[normalized_key] = item
        for normalized_alias in normalized_aliases:
            self._aliases[normalized_alias] = normalized_key

    def get(
        self,
        key: str,
        *,
        include_unverified: bool = False,
    ) -> KnowledgeItem:
        """Return one record by canonical key or alias."""
        normalized = _normalize(key)
        canonical = self._aliases.get(normalized, normalized)
        item = self._items.get(canonical)

        if item is None or (not include_unverified and not item.verified):
            raise UnknownKnowledgeItemError(key)
        return item

    def find(
        self,
        key: str,
        *,
        include_unverified: bool = False,
    ) -> KnowledgeItem | None:
        """Return one record or ``None`` when it is unavailable."""
        try:
            return self.get(key, include_unverified=include_unverified)
        except UnknownKnowledgeItemError:
            return None

    def exists(
        self,
        key: str,
        *,
        include_unverified: bool = False,
    ) -> bool:
        """Return whether a visible record exists."""
        return self.find(key, include_unverified=include_unverified) is not None

    def all_items(
        self,
        *,
        include_unverified: bool = False,
    ) -> tuple[KnowledgeItem, ...]:
        """Return all visible records ordered by canonical key."""
        items = (
            item
            for item in self._items.values()
            if include_unverified or item.verified
        )
        return tuple(sorted(items, key=lambda item: item.key.casefold()))

    def by_category(
        self,
        category: KnowledgeCategory | str,
        *,
        include_unverified: bool = False,
    ) -> tuple[KnowledgeItem, ...]:
        """Return records belonging to one category."""
        normalized_category = KnowledgeCategory(category)
        return tuple(
            item
            for item in self.all_items(include_unverified=include_unverified)
            if item.category == normalized_category
        )

    def search(
        self,
        query: str,
        *,
        category: KnowledgeCategory | str | None = None,
        include_unverified: bool = False,
        limit: int | None = None,
    ) -> tuple[KnowledgeItem, ...]:
        """Search keys, translations, aliases, keywords and descriptions."""
        normalized_query = _normalize(query)
        if not normalized_query:
            return ()

        selected_category = (
            KnowledgeCategory(category) if category is not None else None
        )

        scored: list[tuple[int, str, KnowledgeItem]] = []
        for item in self.all_items(include_unverified=include_unverified):
            if selected_category is not None and item.category != selected_category:
                continue

            key = _normalize(item.key)
            translation = _normalize(item.translation)
            aliases = {_normalize(alias) for alias in item.aliases}
            searchable = item.searchable_text()

            if normalized_query == key:
                score = 100
            elif normalized_query in aliases:
                score = 90
            elif key.startswith(normalized_query):
                score = 80
            elif normalized_query in key:
                score = 70
            elif normalized_query in translation:
                score = 60
            elif normalized_query in searchable:
                score = 40
            else:
                continue

            scored.append((score, item.key.casefold(), item))

        scored.sort(key=lambda row: (-row[0], row[1]))
        results = tuple(row[2] for row in scored)
        return results if limit is None else results[: max(limit, 0)]

    def related(
        self,
        key: str,
        *,
        include_unverified: bool = False,
    ) -> tuple[KnowledgeItem, ...]:
        """Resolve the explicitly configured related records."""
        item = self.get(key, include_unverified=include_unverified)
        related_items: list[KnowledgeItem] = []
        for related_key in item.related_items:
            related = self.find(
                related_key,
                include_unverified=include_unverified,
            )
            if related is not None:
                related_items.append(related)
        return tuple(related_items)

    def statistics(self) -> KnowledgeBaseStatistics:
        """Return counts for editorial and diagnostic reporting."""
        items = tuple(self._items.values())
        verified = sum(item.verified for item in items)
        categories = Counter(item.category.value for item in items)
        return KnowledgeBaseStatistics(
            total=len(items),
            verified=verified,
            draft=len(items) - verified,
            categories=dict(sorted(categories.items())),
        )

    def validate_relations(self) -> tuple[str, ...]:
        """Return missing related-item references without changing the registry."""
        known = set(self._items)
        missing: list[str] = []
        for item in self._items.values():
            for related_key in item.related_items:
                if _normalize(related_key) not in known:
                    missing.append(f"{item.key} -> {related_key}")
        return tuple(sorted(missing))


_ITEMS: tuple[KnowledgeItem, ...] = (
    KnowledgeItem(
        key="Flavorizer Bars",
        category=KnowledgeCategory.COOKING_SYSTEM,
        translation="Flavorizer aromatizējošās plāksnes",
        short_description=(
            "Plāksnes virs gāzes grila degļiem, kas uztver ēdiena sulas un taukus."
        ),
        explanation=(
            "Pilieni uz sakarsušajām plāksnēm dūmo un iztvaiko, papildinot "
            "ēdiena grilējuma aromātu."
        ),
        customer_benefit=(
            "Palīdz veidot raksturīgu grilējuma aromātu un nosedz degļu zonu."
        ),
        sales_argument=(
            "Flavorizer plāksnes apvieno degļu zonas pārklājumu ar aromāta "
            "veidošanos grilēšanas laikā."
        ),
        aliases=("Flavorizer® Bars", "Flavorizer bars"),
        keywords=("drippings", "smoky flavour", "degļu zona"),
        related_items=("Grease Management System",),
        source="Weber oficiālā produkta lapa",
        evidence=(
            "Flavorizer Bars produkta funkcija: pilieni dūmo un piešķir ēdienam dūmu aromātu.",
        ),
        verified=True,
        last_reviewed=date(2026, 7, 24),
    ),
    KnowledgeItem(
        key="PureBlu Burners",
        category=KnowledgeCategory.TECHNOLOGY,
        translation="PureBlu degļi",
        short_description="Weber gāzes grilu degļu sistēmas nosaukums.",
        explanation=(
            "Ieraksts sagatavots kā redakcionāls melnraksts; tehniskais "
            "skaidrojums jāpārbauda oficiālā Weber avotā."
        ),
        customer_benefit="Klienta ieguvums jāapstiprina pēc avota pārbaudes.",
        aliases=("PureBlu",),
        related_items=("Flavorizer Bars",),
        verified=False,
        notes="DRAFT: neizmantot automātiskai publicēšanai.",
    ),
    KnowledgeItem(
        key="Sear Zone",
        category=KnowledgeCategory.COOKING_SYSTEM,
        translation="Sear Zone intensīvās karstuma zona",
        short_description="Atsevišķi izcelta intensīvas karsēšanas zona.",
        explanation="Precīzs darbības apraksts jāpārbauda konkrētā modeļa avotā.",
        customer_benefit="Ieguvums jāformulē tikai pēc modeļa datu pārbaudes.",
        aliases=("SearZone", "Sear Station"),
        verified=False,
        notes="DRAFT: modeļu paaudzēs nosaukumi un izpildījums var atšķirties.",
    ),
    KnowledgeItem(
        key="WEBER CRAFTED",
        category=KnowledgeCategory.COOKING_SYSTEM,
        translation="WEBER CRAFTED grilēšanas sistēma",
        short_description="Weber maināmu grilēšanas piederumu sistēmas nosaukums.",
        explanation="Saderība un nepieciešamās detaļas jāpārbauda katram modelim.",
        customer_benefit="Ļauj izmantot konkrētam ēdienam paredzētu piederumu.",
        aliases=("Weber Crafted", "WEBER CRAFTED Gourmet BBQ System"),
        verified=False,
        notes="DRAFT: saderību nekad neģenerēt bez produkta avota.",
    ),
    KnowledgeItem(
        key="Weber Connect",
        category=KnowledgeCategory.THERMOMETER,
        translation="Weber Connect viedā grilēšanas sistēma",
        short_description="Weber digitālās grilēšanas vadības sistēmas nosaukums.",
        explanation="Funkciju klāsts jāpārbauda konkrētajai ierīcei vai grilam.",
        customer_benefit="Var palīdzēt sekot gatavošanas procesam.",
        aliases=("WEBER CONNECT",),
        verified=False,
        notes="DRAFT: lietotnes un ierīču iespējas var mainīties.",
    ),
    KnowledgeItem(
        key="Infinity Ignition",
        category=KnowledgeCategory.IGNITION,
        translation="Infinity aizdedzes sistēma",
        short_description="Weber gāzes grilu aizdedzes sistēmas nosaukums.",
        explanation="Tehniskais izpildījums jāpārbauda konkrētā modeļa dokumentācijā.",
        customer_benefit="Paredzēta degļu aizdedzināšanai.",
        aliases=("Infinity Ignition System",),
        verified=False,
        notes="DRAFT.",
    ),
    KnowledgeItem(
        key="Snap-Jet Ignition",
        category=KnowledgeCategory.IGNITION,
        translation="Snap-Jet aizdedzes sistēma",
        short_description="Weber gāzes grilu aizdedzes sistēmas nosaukums.",
        explanation="Degļu vadības un aizdedzes darbība jāpārbauda modeļa rokasgrāmatā.",
        customer_benefit="Paredzēta ērtai degļu aizdedzināšanai.",
        aliases=("Snap-Jet", "SnapJet"),
        verified=False,
        notes="DRAFT.",
    ),
    KnowledgeItem(
        key="Gourmet BBQ System",
        category=KnowledgeCategory.COOKING_SYSTEM,
        translation="Gourmet BBQ System grilēšanas sistēma",
        short_description="Maināmu centrālo grilēšanas piederumu sistēmas nosaukums.",
        explanation="Piederumu un režģu saderība jāpārbauda pēc produkta numura.",
        customer_benefit="Ļauj pielāgot grilu dažādiem gatavošanas veidiem.",
        aliases=("GBS", "Gourmet Barbecue System"),
        verified=False,
        notes="DRAFT: nejaukt ar WEBER CRAFTED.",
    ),
    KnowledgeItem(
        key="Grease Management System",
        category=KnowledgeCategory.CLEANING,
        translation="tauku savākšanas sistēma",
        short_description="Sistēma tauku un gatavošanas atlikumu novadīšanai.",
        explanation="Konstrukcija un detaļu izvietojums atšķiras starp modeļiem.",
        customer_benefit="Palīdz organizēt tauku savākšanu un grila kopšanu.",
        aliases=("Grease Management",),
        related_items=("Flavorizer Bars",),
        verified=False,
        notes="DRAFT.",
    ),
    KnowledgeItem(
        key="Side Burner",
        category=KnowledgeCategory.COOKING_SURFACE,
        translation="sānu deglis",
        short_description="Papildu deglis grila sānu darba virsmā.",
        explanation="Jauda un paredzētais lietojums jāņem no konkrētā produkta datiem.",
        customer_benefit="Ļauj paralēli gatavot piedevas vai mērces piemērotā traukā.",
        aliases=("Sideburner",),
        verified=False,
        notes="DRAFT: ieguvumu izmantot tikai produktiem, kuriem sānu deglis ir norādīts.",
    ),
)


kb = KnowledgeBase(_ITEMS)


def main() -> int:
    """Print a small diagnostic report."""
    stats = kb.statistics()
    print("GrillAndMore zināšanu bāze")
    print("=" * 31)
    print(f"Ieraksti kopā: {stats.total}")
    print(f"Verificēti: {stats.verified}")
    print(f"Melnraksti: {stats.draft}")
    print(f"Kategorijas: {len(stats.categories)}")
    print()

    item = kb.get("Flavorizer® Bars")
    print(f"Atrasts: {item.key}")
    print(f"Tulkojums: {item.translation}")
    print(f"Ieguvums: {item.customer_benefit}")
    print()

    drafts = kb.search("aizdedzes", include_unverified=True)
    print(f"Meklējot “aizdedzes” atrasti: {len(drafts)}")

    missing = kb.validate_relations()
    if missing:
        print("WARNING: trūkstošas saites:")
        for relation in missing:
            print(f"- {relation}")
        return 1

    print("PASS: ierakstu saites ir derīgas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
