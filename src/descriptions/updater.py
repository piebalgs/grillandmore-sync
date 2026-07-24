"""Safe WooCommerce updater for generated product descriptions.

The updater receives a WooCommerce-ready FormattedProduct together with its
QualityReport, finds the existing WooCommerce product by SKU, calculates only
the changed fields and optionally sends the update through the existing
src.woocommerce API module.

Pipeline:

    FormattedProduct
          +
    QualityReport
          |
          v
    ProductUpdater
          |
          +--> dry run
          |
          +--> WooCommerce update
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
)
from src.woocommerce import (
    get_product_by_sku,
    update_product,
)


UPDATER_VERSION = "1.0"


class ProductUpdaterError(RuntimeError):
    """Raised when a product update cannot be prepared or completed."""


class UpdateStatus(str, Enum):
    """Possible outcomes of one product update operation."""

    UPDATED = "updated"
    DRY_RUN = "dry_run"
    UNCHANGED = "unchanged"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ProductUpdaterConfig:
    """Configuration controlling WooCommerce product updates."""

    dry_run: bool = True
    require_quality_pass: bool = True
    allow_warnings: bool = True

    update_title: bool = True
    update_short_description: bool = True
    update_description: bool = True
    update_meta_description: bool = True
    update_search_keywords: bool = True

    meta_description_key: str = ""
    search_keywords_key: str = ""

    def __post_init__(self) -> None:
        """Validate configuration values."""

        boolean_fields = {
            "dry_run": self.dry_run,
            "require_quality_pass": self.require_quality_pass,
            "allow_warnings": self.allow_warnings,
            "update_title": self.update_title,
            "update_short_description": self.update_short_description,
            "update_description": self.update_description,
            "update_meta_description": self.update_meta_description,
            "update_search_keywords": self.update_search_keywords,
        }

        for field_name, value in boolean_fields.items():
            if not isinstance(value, bool):
                raise TypeError(
                    f"{field_name} jābūt bool vērtībai."
                )

        string_fields = {
            "meta_description_key": self.meta_description_key,
            "search_keywords_key": self.search_keywords_key,
        }

        for field_name, value in string_fields.items():
            if not isinstance(value, str):
                raise TypeError(
                    f"{field_name} jābūt teksta vērtībai."
                )


@dataclass(frozen=True, slots=True)
class UpdateChange:
    """One changed WooCommerce field."""

    field_name: str
    old_value: Any
    new_value: Any


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    """Prepared update before it is sent to WooCommerce."""

    sku: str
    product_id: int
    payload: Mapping[str, Any]
    changes: tuple[UpdateChange, ...]
    current_product: Mapping[str, Any]

    @property
    def has_changes(self) -> bool:
        """Return whether the update plan contains any changed fields."""

        return bool(self.changes)


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """Final result of one product update operation."""

    sku: str
    status: UpdateStatus
    product_id: int | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    changes: tuple[UpdateChange, ...] = ()
    updated_product: Mapping[str, Any] | None = None
    message: str = ""

    @property
    def changed(self) -> bool:
        """Return whether WooCommerce data differs from generated data."""

        return bool(self.changes)

    @property
    def sent_to_woocommerce(self) -> bool:
        """Return whether a real WooCommerce update was performed."""

        return self.status == UpdateStatus.UPDATED


ProductLoader = Callable[[str], dict[str, Any] | None]
ProductWriter = Callable[[int, dict[str, Any]], dict[str, Any]]


def _normalize_text(value: Any) -> str:
    """Normalize optional text values for deterministic comparison."""

    return str(value or "").strip()


def _normalize_html(value: Any) -> str:
    """Normalize HTML outer whitespace without modifying its structure."""

    return str(value or "").strip()


def _normalize_keywords(values: Any) -> tuple[str, ...]:
    """Return normalized unique search keywords."""

    if values is None:
        return ()

    if isinstance(values, str):
        raw_values = values.split(",")
    else:
        try:
            raw_values = tuple(values)
        except TypeError as error:
            raise TypeError(
                "Meklēšanas atslēgvārdiem jābūt virknei vai kolekcijai."
            ) from error

    normalized: list[str] = []
    seen: set[str] = set()

    for value in raw_values:
        keyword = _normalize_text(value)

        if not keyword:
            continue

        identity = keyword.casefold()

        if identity in seen:
            continue

        seen.add(identity)
        normalized.append(keyword)

    return tuple(normalized)


def _extract_product_id(product: Mapping[str, Any]) -> int:
    """Extract and validate a WooCommerce product ID."""

    raw_product_id = product.get("id")

    if isinstance(raw_product_id, bool):
        raise ProductUpdaterError(
            "WooCommerce produkta ID nav derīgs."
        )

    try:
        product_id = int(raw_product_id)
    except (TypeError, ValueError) as error:
        raise ProductUpdaterError(
            "WooCommerce produktam nav derīga ID."
        ) from error

    if product_id <= 0:
        raise ProductUpdaterError(
            "WooCommerce produkta ID jābūt pozitīvam."
        )

    return product_id


def _meta_data_to_mapping(
    meta_data: Any,
) -> dict[str, Any]:
    """Convert WooCommerce meta_data list to a key-value mapping."""

    if not isinstance(meta_data, list):
        return {}

    result: dict[str, Any] = {}

    for item in meta_data:
        if not isinstance(item, Mapping):
            continue

        key = _normalize_text(item.get("key"))

        if not key:
            continue

        result[key] = item.get("value")

    return result


def _build_meta_update(
    *,
    key: str,
    new_value: str,
    current_meta: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, UpdateChange | None]:
    """Build one WooCommerce meta_data entry when its value changed."""

    normalized_key = _normalize_text(key)

    if not normalized_key:
        return None, None

    old_value = _normalize_text(
        current_meta.get(normalized_key)
    )
    normalized_new_value = _normalize_text(new_value)

    if old_value == normalized_new_value:
        return None, None

    return (
        {
            "key": normalized_key,
            "value": normalized_new_value,
        },
        UpdateChange(
            field_name=f"meta_data.{normalized_key}",
            old_value=old_value,
            new_value=normalized_new_value,
        ),
    )


class ProductUpdater:
    """Prepare and perform safe WooCommerce description updates."""

    def __init__(
        self,
        *,
        config: ProductUpdaterConfig | None = None,
        product_loader: ProductLoader | None = None,
        product_writer: ProductWriter | None = None,
    ) -> None:
        self._config = config or ProductUpdaterConfig()
        self._product_loader = (
            product_loader or get_product_by_sku
        )
        self._product_writer = (
            product_writer or update_product
        )

        if not callable(self._product_loader):
            raise TypeError(
                "product_loader jābūt izsaucamai funkcijai."
            )

        if not callable(self._product_writer):
            raise TypeError(
                "product_writer jābūt izsaucamai funkcijai."
            )

    @property
    def config(self) -> ProductUpdaterConfig:
        """Return immutable updater configuration."""

        return self._config

    def prepare_plan(
        self,
        *,
        product: FormattedProduct,
        quality_report: QualityReport,
        current_product: Mapping[str, Any],
    ) -> UpdatePlan:
        """Build an update plan without modifying WooCommerce."""

        self._validate_input(
            product=product,
            quality_report=quality_report,
        )
        self._validate_quality(
            product=product,
            quality_report=quality_report,
        )

        if not isinstance(current_product, Mapping):
            raise TypeError(
                "current_product jābūt vārdnīcai."
            )

        product_id = _extract_product_id(current_product)

        payload: dict[str, Any] = {}
        changes: list[UpdateChange] = []

        self._add_text_change(
            payload=payload,
            changes=changes,
            enabled=self._config.update_title,
            payload_key="name",
            field_name="title",
            old_value=current_product.get("name"),
            new_value=product.title,
            html=False,
        )

        self._add_text_change(
            payload=payload,
            changes=changes,
            enabled=self._config.update_short_description,
            payload_key="short_description",
            field_name="short_description",
            old_value=current_product.get("short_description"),
            new_value=product.short_description,
            html=True,
        )

        self._add_text_change(
            payload=payload,
            changes=changes,
            enabled=self._config.update_description,
            payload_key="description",
            field_name="description_html",
            old_value=current_product.get("description"),
            new_value=product.description_html,
            html=True,
        )

        current_meta = _meta_data_to_mapping(
            current_product.get("meta_data")
        )
        meta_updates: list[dict[str, Any]] = []

        if self._config.update_meta_description:
            meta_entry, meta_change = _build_meta_update(
                key=self._config.meta_description_key,
                new_value=product.meta_description,
                current_meta=current_meta,
            )

            if meta_entry is not None:
                meta_updates.append(meta_entry)

            if meta_change is not None:
                changes.append(meta_change)

        if self._config.update_search_keywords:
            keywords = _normalize_keywords(
                product.search_keywords
            )
            keyword_value = ", ".join(keywords)

            meta_entry, meta_change = _build_meta_update(
                key=self._config.search_keywords_key,
                new_value=keyword_value,
                current_meta=current_meta,
            )

            if meta_entry is not None:
                meta_updates.append(meta_entry)

            if meta_change is not None:
                changes.append(meta_change)

        if meta_updates:
            payload["meta_data"] = meta_updates

        return UpdatePlan(
            sku=product.sku,
            product_id=product_id,
            payload=payload,
            changes=tuple(changes),
            current_product=dict(current_product),
        )

    def update(
        self,
        *,
        product: FormattedProduct,
        quality_report: QualityReport,
    ) -> UpdateResult:
        """Find and optionally update one WooCommerce product."""

        self._validate_input(
            product=product,
            quality_report=quality_report,
        )

        try:
            self._validate_quality(
                product=product,
                quality_report=quality_report,
            )
        except ProductUpdaterError as error:
            return UpdateResult(
                sku=product.sku,
                status=UpdateStatus.BLOCKED,
                message=str(error),
            )

        current_product = self._product_loader(product.sku)

        if current_product is None:
            return UpdateResult(
                sku=product.sku,
                status=UpdateStatus.NOT_FOUND,
                message=(
                    f"WooCommerce produkts ar SKU "
                    f"{product.sku} netika atrasts."
                ),
            )

        plan = self.prepare_plan(
            product=product,
            quality_report=quality_report,
            current_product=current_product,
        )

        if not plan.has_changes:
            return UpdateResult(
                sku=product.sku,
                product_id=plan.product_id,
                status=UpdateStatus.UNCHANGED,
                payload=plan.payload,
                changes=plan.changes,
                message="WooCommerce produkta dati jau ir aktuāli.",
            )

        if self._config.dry_run:
            return UpdateResult(
                sku=product.sku,
                product_id=plan.product_id,
                status=UpdateStatus.DRY_RUN,
                payload=plan.payload,
                changes=plan.changes,
                message=(
                    "Dry-run režīms: izmaiņas netika nosūtītas "
                    "uz WooCommerce."
                ),
            )

        updated_product = self._product_writer(
            plan.product_id,
            dict(plan.payload),
        )

        if not isinstance(updated_product, dict):
            raise ProductUpdaterError(
                "WooCommerce atjaunināšanas funkcija neatgrieza vārdnīcu."
            )

        return UpdateResult(
            sku=product.sku,
            product_id=plan.product_id,
            status=UpdateStatus.UPDATED,
            payload=plan.payload,
            changes=plan.changes,
            updated_product=updated_product,
            message="WooCommerce produkts veiksmīgi atjaunināts.",
        )

    @staticmethod
    def _validate_input(
        *,
        product: FormattedProduct,
        quality_report: QualityReport,
    ) -> None:
        """Validate updater input objects."""

        if not isinstance(product, FormattedProduct):
            raise TypeError(
                "product jābūt FormattedProduct objektam."
            )

        if not isinstance(quality_report, QualityReport):
            raise TypeError(
                "quality_report jābūt QualityReport objektam."
            )

        product_sku = _normalize_text(product.sku)
        report_sku = _normalize_text(quality_report.sku)

        if not product_sku:
            raise ProductUpdaterError(
                "Produkta SKU nedrīkst būt tukšs."
            )

        if product_sku != report_sku:
            raise ProductUpdaterError(
                "FormattedProduct un QualityReport SKU nesakrīt: "
                f"“{product_sku}” pret “{report_sku}”."
            )

    def _validate_quality(
        self,
        *,
        product: FormattedProduct,
        quality_report: QualityReport,
    ) -> None:
        """Block updates that do not meet quality requirements."""

        if (
            self._config.require_quality_pass
            and not quality_report.passed
        ):
            raise ProductUpdaterError(
                f"SKU {product.sku} atjaunināšana bloķēta: "
                f"kvalitātes pārbaudē ir "
                f"{quality_report.error_count} kļūdas."
            )

        if (
            not self._config.allow_warnings
            and quality_report.warning_count > 0
        ):
            raise ProductUpdaterError(
                f"SKU {product.sku} atjaunināšana bloķēta: "
                f"kvalitātes pārbaudē ir "
                f"{quality_report.warning_count} brīdinājumi."
            )

    @staticmethod
    def _add_text_change(
        *,
        payload: dict[str, Any],
        changes: list[UpdateChange],
        enabled: bool,
        payload_key: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        html: bool,
    ) -> None:
        """Add one changed field to the update payload."""

        if not enabled:
            return

        normalizer = (
            _normalize_html
            if html
            else _normalize_text
        )

        normalized_old_value = normalizer(old_value)
        normalized_new_value = normalizer(new_value)

        if normalized_old_value == normalized_new_value:
            return

        payload[payload_key] = normalized_new_value
        changes.append(
            UpdateChange(
                field_name=field_name,
                old_value=normalized_old_value,
                new_value=normalized_new_value,
            )
        )


def format_update_result(result: UpdateResult) -> str:
    """Return a deterministic terminal representation of an update result."""

    if not isinstance(result, UpdateResult):
        raise TypeError(
            "result jābūt UpdateResult objektam."
        )

    lines = [
        f"{result.status.value.upper()}: SKU {result.sku}",
        result.message,
    ]

    if result.product_id is not None:
        lines.append(
            f"WooCommerce produkta ID: {result.product_id}"
        )

    if not result.changes:
        lines.append("Maināmi lauki nav atrasti.")
        return "\n".join(lines)

    lines.append(
        f"Maināmi lauki: {len(result.changes)}"
    )

    for change in result.changes:
        lines.append(
            f"- {change.field_name}"
        )

    return "\n".join(lines)