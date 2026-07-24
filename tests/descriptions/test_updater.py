"""Tests for updater.py."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from src.descriptions.models import (
    FormattedProduct,
    QualityCheck,
    QualityReport,
    Severity,
)
from src.descriptions.updater import (
    ProductUpdater,
    ProductUpdaterConfig,
    ProductUpdaterError,
    UpdateChange,
    UpdatePlan,
    UpdateResult,
    UpdateStatus,
    _build_meta_update,
    _extract_product_id,
    _meta_data_to_mapping,
    _normalize_html,
    _normalize_keywords,
    _normalize_text,
    format_update_result,
)


# ----------------------------------------------------------------------
# Helper factories
# ----------------------------------------------------------------------


def make_product(**changes: Any) -> FormattedProduct:
    """Create a valid formatted product for updater tests."""

    values: dict[str, Any] = {
        "sku": "ABC-123",
        "title": "Weber Genesis EP-335W",
        "short_description": (
            "<p>Jaudīgs gāzes grils ērtai gatavošanai.</p>"
        ),
        "description_html": (
            "<p>Weber Genesis EP-335W nodrošina vienmērīgu "
            "karstuma sadali.</p>"
        ),
        "meta_description": (
            "Weber Genesis EP-335W gāzes grils ar vienmērīgu "
            "karstuma sadali un ērtu temperatūras kontroli."
        ),
        "search_keywords": (
            "Weber",
            "Genesis",
            "gāzes grils",
        ),
        "warnings": (),
        "metadata": {},
    }

    values.update(changes)

    return FormattedProduct(**values)


def make_quality_report(
    *,
    sku: str = "ABC-123",
    passed: bool = True,
    error_count: int = 0,
    warning_count: int = 0,
    checks: tuple[QualityCheck, ...] = (),
) -> QualityReport:
    """Create a quality report for updater tests."""

    return QualityReport(
        sku=sku,
        checks=checks,
        passed=passed,
        error_count=error_count,
        warning_count=warning_count,
    )


def make_failed_quality_report(
    *,
    sku: str = "ABC-123",
) -> QualityReport:
    """Create a quality report containing one error."""

    check = QualityCheck(
        code="required_fields.title",
        message="Produkta nosaukums nav norādīts.",
        severity=Severity.ERROR,
        passed=False,
        field_name="title",
    )

    return make_quality_report(
        sku=sku,
        passed=False,
        error_count=1,
        warning_count=0,
        checks=(check,),
    )


def make_warning_quality_report(
    *,
    sku: str = "ABC-123",
) -> QualityReport:
    """Create a passing report containing one warning."""

    check = QualityCheck(
        code="sentence_length",
        message="Atrasts pārāk garš teikums.",
        severity=Severity.WARNING,
        passed=False,
        field_name="description_html",
    )

    return make_quality_report(
        sku=sku,
        passed=True,
        error_count=0,
        warning_count=1,
        checks=(check,),
    )


def make_current_product(**changes: Any) -> dict[str, Any]:
    """Create an existing WooCommerce product."""

    values: dict[str, Any] = {
        "id": 321,
        "sku": "ABC-123",
        "name": "Vecais produkta nosaukums",
        "short_description": "<p>Vecais īsais apraksts.</p>",
        "description": "<p>Vecais pilnais apraksts.</p>",
        "meta_data": [],
    }

    values.update(changes)

    return values


def make_matching_current_product(
    product: FormattedProduct | None = None,
) -> dict[str, Any]:
    """Create WooCommerce data matching the formatted product."""

    formatted = product or make_product()

    return make_current_product(
        name=formatted.title,
        short_description=formatted.short_description,
        description=formatted.description_html,
    )


class LoaderSpy:
    """Callable test double for get_product_by_sku."""

    def __init__(
        self,
        result: dict[str, Any] | None,
    ) -> None:
        self.result = result
        self.calls: list[str] = []

    def __call__(
        self,
        sku: str,
    ) -> dict[str, Any] | None:
        self.calls.append(sku)
        return self.result


class WriterSpy:
    """Callable test double for update_product."""

    def __init__(
        self,
        result: dict[str, Any] | None = None,
    ) -> None:
        self.result = result or {
            "id": 321,
            "name": "Atjaunināts produkts",
        }
        self.calls: list[tuple[int, dict[str, Any]]] = []

    def __call__(
        self,
        product_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            (
                product_id,
                payload,
            )
        )
        return self.result


# ----------------------------------------------------------------------
# UpdateStatus
# ----------------------------------------------------------------------


def test_update_status_values_are_stable():
    assert UpdateStatus.UPDATED.value == "updated"
    assert UpdateStatus.DRY_RUN.value == "dry_run"
    assert UpdateStatus.UNCHANGED.value == "unchanged"
    assert UpdateStatus.NOT_FOUND.value == "not_found"
    assert UpdateStatus.BLOCKED.value == "blocked"


def test_update_status_is_string_enum():
    assert isinstance(UpdateStatus.UPDATED, str)


# ----------------------------------------------------------------------
# ProductUpdaterConfig
# ----------------------------------------------------------------------


def test_config_has_safe_defaults():
    config = ProductUpdaterConfig()

    assert config.dry_run is True
    assert config.require_quality_pass is True
    assert config.allow_warnings is True

    assert config.update_title is True
    assert config.update_short_description is True
    assert config.update_description is True
    assert config.update_meta_description is True
    assert config.update_search_keywords is True

    assert config.meta_description_key == ""
    assert config.search_keywords_key == ""


@pytest.mark.parametrize(
    "field_name",
    (
        "dry_run",
        "require_quality_pass",
        "allow_warnings",
        "update_title",
        "update_short_description",
        "update_description",
        "update_meta_description",
        "update_search_keywords",
    ),
)
def test_config_rejects_non_boolean_values(
    field_name: str,
):
    with pytest.raises(
        TypeError,
        match=rf"{field_name} jābūt bool vērtībai",
    ):
        ProductUpdaterConfig(
            **{
                field_name: 1,
            }
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "meta_description_key",
        "search_keywords_key",
    ),
)
def test_config_rejects_non_string_meta_keys(
    field_name: str,
):
    with pytest.raises(
        TypeError,
        match=rf"{field_name} jābūt teksta vērtībai",
    ):
        ProductUpdaterConfig(
            **{
                field_name: 123,
            }
        )


def test_config_accepts_custom_values():
    config = ProductUpdaterConfig(
        dry_run=False,
        require_quality_pass=False,
        allow_warnings=False,
        update_title=False,
        update_short_description=False,
        update_description=False,
        update_meta_description=False,
        update_search_keywords=False,
        meta_description_key="rank_math_description",
        search_keywords_key="rank_math_focus_keyword",
    )

    assert config.dry_run is False
    assert config.require_quality_pass is False
    assert config.allow_warnings is False
    assert config.update_title is False
    assert config.meta_description_key == "rank_math_description"
    assert config.search_keywords_key == "rank_math_focus_keyword"


# ----------------------------------------------------------------------
# UpdateChange
# ----------------------------------------------------------------------


def test_update_change_stores_values():
    change = UpdateChange(
        field_name="title",
        old_value="Vecais nosaukums",
        new_value="Jaunais nosaukums",
    )

    assert change.field_name == "title"
    assert change.old_value == "Vecais nosaukums"
    assert change.new_value == "Jaunais nosaukums"


def test_update_change_is_immutable():
    change = UpdateChange(
        field_name="title",
        old_value="A",
        new_value="B",
    )

    with pytest.raises(AttributeError):
        change.field_name = "description"


# ----------------------------------------------------------------------
# UpdatePlan
# ----------------------------------------------------------------------


def test_update_plan_reports_changes():
    change = UpdateChange(
        field_name="title",
        old_value="A",
        new_value="B",
    )

    plan = UpdatePlan(
        sku="ABC-123",
        product_id=321,
        payload={
            "name": "B",
        },
        changes=(change,),
        current_product={
            "id": 321,
        },
    )

    assert plan.has_changes is True


def test_update_plan_reports_no_changes():
    plan = UpdatePlan(
        sku="ABC-123",
        product_id=321,
        payload={},
        changes=(),
        current_product={
            "id": 321,
        },
    )

    assert plan.has_changes is False


# ----------------------------------------------------------------------
# UpdateResult
# ----------------------------------------------------------------------


def test_update_result_defaults():
    result = UpdateResult(
        sku="ABC-123",
        status=UpdateStatus.UNCHANGED,
    )

    assert result.product_id is None
    assert result.payload == {}
    assert result.changes == ()
    assert result.updated_product is None
    assert result.message == ""
    assert result.changed is False
    assert result.sent_to_woocommerce is False


def test_update_result_reports_changed_data():
    change = UpdateChange(
        field_name="title",
        old_value="A",
        new_value="B",
    )

    result = UpdateResult(
        sku="ABC-123",
        status=UpdateStatus.DRY_RUN,
        changes=(change,),
    )

    assert result.changed is True
    assert result.sent_to_woocommerce is False


def test_update_result_reports_real_update():
    result = UpdateResult(
        sku="ABC-123",
        status=UpdateStatus.UPDATED,
    )

    assert result.sent_to_woocommerce is True


@pytest.mark.parametrize(
    "status",
    (
        UpdateStatus.DRY_RUN,
        UpdateStatus.UNCHANGED,
        UpdateStatus.NOT_FOUND,
        UpdateStatus.BLOCKED,
    ),
)
def test_only_updated_status_was_sent_to_woocommerce(
    status: UpdateStatus,
):
    result = UpdateResult(
        sku="ABC-123",
        status=status,
    )

    assert result.sent_to_woocommerce is False


# ----------------------------------------------------------------------
# _normalize_text
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, ""),
        ("", ""),
        ("   ", ""),
        (" Produkts ", "Produkts"),
        (123, "123"),
        (False, ""),
        (True, "True"),
    ),
)
def test_normalize_text(
    value: Any,
    expected: str,
):
    assert _normalize_text(value) == expected


# ----------------------------------------------------------------------
# _normalize_html
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (None, ""),
        ("", ""),
        ("  <p>Teksts</p>  ", "<p>Teksts</p>"),
        (
            "<p>  Iekšējās atstarpes  </p>",
            "<p>  Iekšējās atstarpes  </p>",
        ),
        (123, "123"),
    ),
)
def test_normalize_html(
    value: Any,
    expected: str,
):
    assert _normalize_html(value) == expected


# ----------------------------------------------------------------------
# _normalize_keywords
# ----------------------------------------------------------------------


def test_normalize_keywords_accepts_tuple():
    result = _normalize_keywords(
        (
            "Weber",
            "Genesis",
            "gāzes grils",
        )
    )

    assert result == (
        "Weber",
        "Genesis",
        "gāzes grils",
    )


def test_normalize_keywords_accepts_list():
    result = _normalize_keywords(
        [
            "Weber",
            "Genesis",
        ]
    )

    assert result == (
        "Weber",
        "Genesis",
    )


def test_normalize_keywords_accepts_comma_separated_string():
    result = _normalize_keywords(
        "Weber, Genesis, gāzes grils"
    )

    assert result == (
        "Weber",
        "Genesis",
        "gāzes grils",
    )


def test_normalize_keywords_removes_empty_values():
    result = _normalize_keywords(
        (
            "",
            " ",
            "Weber",
            None,
            "Genesis",
        )
    )

    assert result == (
        "Weber",
        "Genesis",
    )


def test_normalize_keywords_removes_duplicates_case_insensitively():
    result = _normalize_keywords(
        (
            "Weber",
            "WEBER",
            "weber",
            "Genesis",
        )
    )

    assert result == (
        "Weber",
        "Genesis",
    )


def test_normalize_keywords_preserves_original_order():
    result = _normalize_keywords(
        (
            "Genesis",
            "Weber",
            "gāzes grils",
        )
    )

    assert result == (
        "Genesis",
        "Weber",
        "gāzes grils",
    )


def test_normalize_keywords_strips_outer_whitespace():
    result = _normalize_keywords(
        (
            " Weber ",
            " Genesis ",
        )
    )

    assert result == (
        "Weber",
        "Genesis",
    )


def test_normalize_keywords_none_returns_empty_tuple():
    assert _normalize_keywords(None) == ()


def test_normalize_keywords_rejects_non_iterable_value():
    with pytest.raises(
        TypeError,
        match=(
            "Meklēšanas atslēgvārdiem jābūt "
            "virknei vai kolekcijai"
        ),
    ):
        _normalize_keywords(123)


# ----------------------------------------------------------------------
# _extract_product_id
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_id", "expected"),
    (
        (1, 1),
        (321, 321),
        ("321", 321),
        (" 321 ", 321),
    ),
)
def test_extract_product_id_accepts_valid_values(
    raw_id: Any,
    expected: int,
):
    assert _extract_product_id(
        {
            "id": raw_id,
        }
    ) == expected


@pytest.mark.parametrize(
    "raw_id",
    (
        None,
        "",
        "abc",
        [],
        {},
    ),
)
def test_extract_product_id_rejects_invalid_values(
    raw_id: Any,
):
    with pytest.raises(
        ProductUpdaterError,
        match="WooCommerce produktam nav derīga ID",
    ):
        _extract_product_id(
            {
                "id": raw_id,
            }
        )


@pytest.mark.parametrize(
    "raw_id",
    (
        0,
        -1,
        "-5",
    ),
)
def test_extract_product_id_rejects_non_positive_values(
    raw_id: Any,
):
    with pytest.raises(
        ProductUpdaterError,
        match="WooCommerce produkta ID jābūt pozitīvam",
    ):
        _extract_product_id(
            {
                "id": raw_id,
            }
        )


@pytest.mark.parametrize(
    "raw_id",
    (
        True,
        False,
    ),
)
def test_extract_product_id_rejects_boolean_values(
    raw_id: bool,
):
    with pytest.raises(
        ProductUpdaterError,
        match="WooCommerce produkta ID nav derīgs",
    ):
        _extract_product_id(
            {
                "id": raw_id,
            }
        )


def test_extract_product_id_rejects_missing_id():
    with pytest.raises(
        ProductUpdaterError,
        match="WooCommerce produktam nav derīga ID",
    ):
        _extract_product_id({})


# ----------------------------------------------------------------------
# _meta_data_to_mapping
# ----------------------------------------------------------------------


def test_meta_data_to_mapping_converts_entries():
    result = _meta_data_to_mapping(
        [
            {
                "id": 1,
                "key": "rank_math_description",
                "value": "Meta apraksts",
            },
            {
                "id": 2,
                "key": "rank_math_focus_keyword",
                "value": "Weber",
            },
        ]
    )

    assert result == {
        "rank_math_description": "Meta apraksts",
        "rank_math_focus_keyword": "Weber",
    }


@pytest.mark.parametrize(
    "value",
    (
        None,
        "",
        {},
        (),
        123,
    ),
)
def test_meta_data_to_mapping_non_list_returns_empty_mapping(
    value: Any,
):
    assert _meta_data_to_mapping(value) == {}


def test_meta_data_to_mapping_ignores_non_mapping_items():
    result = _meta_data_to_mapping(
        [
            None,
            "text",
            123,
            {
                "key": "valid_key",
                "value": "Vērtība",
            },
        ]
    )

    assert result == {
        "valid_key": "Vērtība",
    }


def test_meta_data_to_mapping_ignores_empty_keys():
    result = _meta_data_to_mapping(
        [
            {
                "key": "",
                "value": "A",
            },
            {
                "key": "   ",
                "value": "B",
            },
            {
                "key": None,
                "value": "C",
            },
        ]
    )

    assert result == {}


def test_meta_data_to_mapping_normalizes_keys():
    result = _meta_data_to_mapping(
        [
            {
                "key": "  custom_key  ",
                "value": "Vērtība",
            },
        ]
    )

    assert result == {
        "custom_key": "Vērtība",
    }


def test_meta_data_to_mapping_last_duplicate_wins():
    result = _meta_data_to_mapping(
        [
            {
                "key": "custom_key",
                "value": "Pirmā",
            },
            {
                "key": "custom_key",
                "value": "Otrā",
            },
        ]
    )

    assert result == {
        "custom_key": "Otrā",
    }


# ----------------------------------------------------------------------
# _build_meta_update
# ----------------------------------------------------------------------


def test_build_meta_update_creates_changed_entry():
    entry, change = _build_meta_update(
        key="rank_math_description",
        new_value="Jaunais meta apraksts",
        current_meta={
            "rank_math_description": "Vecais meta apraksts",
        },
    )

    assert entry == {
        "key": "rank_math_description",
        "value": "Jaunais meta apraksts",
    }

    assert change == UpdateChange(
        field_name="meta_data.rank_math_description",
        old_value="Vecais meta apraksts",
        new_value="Jaunais meta apraksts",
    )


def test_build_meta_update_creates_new_entry_when_missing():
    entry, change = _build_meta_update(
        key="rank_math_description",
        new_value="Jaunais meta apraksts",
        current_meta={},
    )

    assert entry == {
        "key": "rank_math_description",
        "value": "Jaunais meta apraksts",
    }

    assert change is not None
    assert change.old_value == ""
    assert change.new_value == "Jaunais meta apraksts"


def test_build_meta_update_returns_none_when_unchanged():
    entry, change = _build_meta_update(
        key="rank_math_description",
        new_value="Vienāds teksts",
        current_meta={
            "rank_math_description": "Vienāds teksts",
        },
    )

    assert entry is None
    assert change is None


@pytest.mark.parametrize(
    "key",
    (
        "",
        "   ",
        None,
    ),
)
def test_build_meta_update_skips_empty_key(
    key: Any,
):
    entry, change = _build_meta_update(
        key=key,
        new_value="Jaunais teksts",
        current_meta={},
    )

    assert entry is None
    assert change is None


def test_build_meta_update_normalizes_outer_whitespace():
    entry, change = _build_meta_update(
        key="  custom_key  ",
        new_value="  Jaunā vērtība  ",
        current_meta={
            "custom_key": " Vecā vērtība ",
        },
    )

    assert entry == {
        "key": "custom_key",
        "value": "Jaunā vērtība",
    }

    assert change == UpdateChange(
        field_name="meta_data.custom_key",
        old_value="Vecā vērtība",
        new_value="Jaunā vērtība",
    )


# ----------------------------------------------------------------------
# ProductUpdater construction
# ----------------------------------------------------------------------


def test_updater_uses_default_config():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    assert updater.config == ProductUpdaterConfig()


def test_updater_uses_custom_config():
    config = ProductUpdaterConfig(
        dry_run=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    assert updater.config is config


def test_updater_rejects_non_callable_loader():
    with pytest.raises(
        TypeError,
        match="product_loader jābūt izsaucamai funkcijai",
    ):
        ProductUpdater(
            product_loader="not callable",
            product_writer=WriterSpy(),
        )


def test_updater_rejects_non_callable_writer():
    with pytest.raises(
        TypeError,
        match="product_writer jābūt izsaucamai funkcijai",
    ):
        ProductUpdater(
            product_loader=LoaderSpy(None),
            product_writer="not callable",
        )


# ----------------------------------------------------------------------
# ProductUpdater input validation
# ----------------------------------------------------------------------


def test_prepare_plan_rejects_invalid_product_type():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        TypeError,
        match="product jābūt FormattedProduct objektam",
    ):
        updater.prepare_plan(
            product={},
            quality_report=make_quality_report(),
            current_product=make_current_product(),
        )


def test_prepare_plan_rejects_invalid_quality_report_type():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        TypeError,
        match="quality_report jābūt QualityReport objektam",
    ):
        updater.prepare_plan(
            product=make_product(),
            quality_report={},
            current_product=make_current_product(),
        )


def test_prepare_plan_rejects_empty_product_sku():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        ProductUpdaterError,
        match="Produkta SKU nedrīkst būt tukšs",
    ):
        updater.prepare_plan(
            product=make_product(
                sku="   ",
            ),
            quality_report=make_quality_report(
                sku="   ",
            ),
            current_product=make_current_product(),
        )


def test_prepare_plan_rejects_mismatching_skus():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        ProductUpdaterError,
        match=(
            "FormattedProduct un QualityReport SKU nesakrīt"
        ),
    ):
        updater.prepare_plan(
            product=make_product(
                sku="ABC-123",
            ),
            quality_report=make_quality_report(
                sku="XYZ-999",
            ),
            current_product=make_current_product(),
        )


def test_prepare_plan_rejects_non_mapping_current_product():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        TypeError,
        match="current_product jābūt vārdnīcai",
    ):
        updater.prepare_plan(
            product=make_product(),
            quality_report=make_quality_report(),
            current_product=[],
        )


# ----------------------------------------------------------------------
# prepare_plan
# ----------------------------------------------------------------------


def test_prepare_plan_detects_title_change():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name="Vecais nosaukums",
            short_description=product.short_description,
            description=product.description_html,
        ),
    )

    assert plan.product_id == 321
    assert plan.sku == "ABC-123"
    assert plan.payload == {
        "name": product.title,
    }

    assert plan.changes == (
        UpdateChange(
            field_name="title",
            old_value="Vecais nosaukums",
            new_value=product.title,
        ),
    )


def test_prepare_plan_detects_short_description_change():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name=product.title,
            short_description="<p>Vecais apraksts.</p>",
            description=product.description_html,
        ),
    )

    assert plan.payload == {
        "short_description": product.short_description,
    }

    assert plan.changes[0].field_name == "short_description"


def test_prepare_plan_detects_description_change():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name=product.title,
            short_description=product.short_description,
            description="<p>Vecais pilnais apraksts.</p>",
        ),
    )

    assert plan.payload == {
        "description": product.description_html,
    }

    assert plan.changes[0].field_name == "description_html"


def test_prepare_plan_detects_all_standard_text_changes():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(),
    )

    assert plan.payload == {
        "name": product.title,
        "short_description": product.short_description,
        "description": product.description_html,
    }

    assert tuple(
        change.field_name
        for change in plan.changes
    ) == (
        "title",
        "short_description",
        "description_html",
    )


def test_prepare_plan_returns_no_changes_for_matching_product():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert plan.payload == {}
    assert plan.changes == ()
    assert plan.has_changes is False


def test_prepare_plan_ignores_outer_whitespace():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name=f"  {product.title}  ",
            short_description=(
                f"  {product.short_description}  "
            ),
            description=(
                f"  {product.description_html}  "
            ),
        ),
    )

    assert plan.payload == {}
    assert plan.changes == ()


def test_prepare_plan_can_disable_title_update():
    product = make_product()

    config = ProductUpdaterConfig(
        update_title=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name="Vecais nosaukums",
            short_description=product.short_description,
            description=product.description_html,
        ),
    )

    assert "name" not in plan.payload
    assert all(
        change.field_name != "title"
        for change in plan.changes
    )


def test_prepare_plan_can_disable_short_description_update():
    product = make_product()

    config = ProductUpdaterConfig(
        update_short_description=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name=product.title,
            short_description="<p>Vecais teksts.</p>",
            description=product.description_html,
        ),
    )

    assert "short_description" not in plan.payload
    assert plan.changes == ()


def test_prepare_plan_can_disable_description_update():
    product = make_product()

    config = ProductUpdaterConfig(
        update_description=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_current_product(
            name=product.title,
            short_description=product.short_description,
            description="<p>Vecais teksts.</p>",
        ),
    )

    assert "description" not in plan.payload
    assert plan.changes == ()


# ----------------------------------------------------------------------
# prepare_plan meta_data
# ----------------------------------------------------------------------


def test_prepare_plan_adds_meta_description():
    product = make_product()

    config = ProductUpdaterConfig(
        meta_description_key="rank_math_description",
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert plan.payload == {
        "meta_data": [
            {
                "key": "rank_math_description",
                "value": product.meta_description,
            },
        ],
    }

    assert plan.changes[0].field_name == (
        "meta_data.rank_math_description"
    )


def test_prepare_plan_adds_search_keywords():
    product = make_product()

    config = ProductUpdaterConfig(
        search_keywords_key="rank_math_focus_keyword",
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert plan.payload == {
        "meta_data": [
            {
                "key": "rank_math_focus_keyword",
                "value": "Weber, Genesis, gāzes grils",
            },
        ],
    }


def test_prepare_plan_adds_both_meta_fields():
    product = make_product()

    config = ProductUpdaterConfig(
        meta_description_key="rank_math_description",
        search_keywords_key="rank_math_focus_keyword",
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert plan.payload["meta_data"] == [
        {
            "key": "rank_math_description",
            "value": product.meta_description,
        },
        {
            "key": "rank_math_focus_keyword",
            "value": "Weber, Genesis, gāzes grils",
        },
    ]


def test_prepare_plan_does_not_change_matching_meta_fields():
    product = make_product()

    config = ProductUpdaterConfig(
        meta_description_key="rank_math_description",
        search_keywords_key="rank_math_focus_keyword",
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    current = make_matching_current_product(
        product
    )
    current["meta_data"] = [
        {
            "key": "rank_math_description",
            "value": product.meta_description,
        },
        {
            "key": "rank_math_focus_keyword",
            "value": "Weber, Genesis, gāzes grils",
        },
    ]

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=current,
    )

    assert plan.payload == {}
    assert plan.changes == ()


def test_prepare_plan_skips_meta_fields_when_keys_are_empty():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert "meta_data" not in plan.payload
    assert plan.changes == ()


def test_prepare_plan_can_disable_meta_description():
    product = make_product()

    config = ProductUpdaterConfig(
        update_meta_description=False,
        meta_description_key="rank_math_description",
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert "meta_data" not in plan.payload


def test_prepare_plan_can_disable_search_keywords():
    product = make_product()

    config = ProductUpdaterConfig(
        update_search_keywords=False,
        search_keywords_key="rank_math_focus_keyword",
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=product,
        quality_report=make_quality_report(),
        current_product=make_matching_current_product(
            product
        ),
    )

    assert "meta_data" not in plan.payload


# ----------------------------------------------------------------------
# Quality blocking
# ----------------------------------------------------------------------


def test_prepare_plan_blocks_failed_quality_report():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        ProductUpdaterError,
        match="kvalitātes pārbaudē ir 1 kļūdas",
    ):
        updater.prepare_plan(
            product=make_product(),
            quality_report=make_failed_quality_report(),
            current_product=make_current_product(),
        )


def test_prepare_plan_can_allow_failed_quality_report():
    config = ProductUpdaterConfig(
        require_quality_pass=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=make_product(),
        quality_report=make_failed_quality_report(),
        current_product=make_current_product(),
    )

    assert plan.has_changes is True


def test_prepare_plan_allows_warnings_by_default():
    updater = ProductUpdater(
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    plan = updater.prepare_plan(
        product=make_product(),
        quality_report=make_warning_quality_report(),
        current_product=make_current_product(),
    )

    assert plan.has_changes is True


def test_prepare_plan_can_block_warnings():
    config = ProductUpdaterConfig(
        allow_warnings=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=LoaderSpy(None),
        product_writer=WriterSpy(),
    )

    with pytest.raises(
        ProductUpdaterError,
        match="kvalitātes pārbaudē ir 1 brīdinājumi",
    ):
        updater.prepare_plan(
            product=make_product(),
            quality_report=make_warning_quality_report(),
            current_product=make_current_product(),
        )


# ----------------------------------------------------------------------
# update
# ----------------------------------------------------------------------


def test_update_returns_blocked_for_failed_quality():
    loader = LoaderSpy(
        make_current_product()
    )
    writer = WriterSpy()

    updater = ProductUpdater(
        product_loader=loader,
        product_writer=writer,
    )

    result = updater.update(
        product=make_product(),
        quality_report=make_failed_quality_report(),
    )

    assert result.status == UpdateStatus.BLOCKED
    assert result.product_id is None
    assert result.changes == ()
    assert loader.calls == []
    assert writer.calls == []


def test_update_returns_blocked_for_warning_when_disallowed():
    loader = LoaderSpy(
        make_current_product()
    )
    writer = WriterSpy()

    config = ProductUpdaterConfig(
        allow_warnings=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=loader,
        product_writer=writer,
    )

    result = updater.update(
        product=make_product(),
        quality_report=make_warning_quality_report(),
    )

    assert result.status == UpdateStatus.BLOCKED
    assert loader.calls == []
    assert writer.calls == []


def test_update_returns_not_found():
    loader = LoaderSpy(None)
    writer = WriterSpy()

    updater = ProductUpdater(
        product_loader=loader,
        product_writer=writer,
    )

    result = updater.update(
        product=make_product(),
        quality_report=make_quality_report(),
    )

    assert result.status == UpdateStatus.NOT_FOUND
    assert result.product_id is None
    assert result.changes == ()
    assert loader.calls == ["ABC-123"]
    assert writer.calls == []


def test_update_returns_unchanged():
    product = make_product()

    loader = LoaderSpy(
        make_matching_current_product(
            product
        )
    )
    writer = WriterSpy()

    updater = ProductUpdater(
        product_loader=loader,
        product_writer=writer,
    )

    result = updater.update(
        product=product,
        quality_report=make_quality_report(),
    )

    assert result.status == UpdateStatus.UNCHANGED
    assert result.product_id == 321
    assert result.payload == {}
    assert result.changes == ()
    assert loader.calls == ["ABC-123"]
    assert writer.calls == []


def test_update_returns_dry_run():
    product = make_product()

    loader = LoaderSpy(
        make_current_product()
    )
    writer = WriterSpy()

    updater = ProductUpdater(
        product_loader=loader,
        product_writer=writer,
    )

    result = updater.update(
        product=product,
        quality_report=make_quality_report(),
    )

    assert result.status == UpdateStatus.DRY_RUN
    assert result.product_id == 321
    assert result.changed is True
    assert result.sent_to_woocommerce is False
    assert writer.calls == []


def test_update_dry_run_contains_payload():
    product = make_product()

    updater = ProductUpdater(
        product_loader=LoaderSpy(
            make_current_product()
        ),
        product_writer=WriterSpy(),
    )

    result = updater.update(
        product=product,
        quality_report=make_quality_report(),
    )

    assert result.payload == {
        "name": product.title,
        "short_description": product.short_description,
        "description": product.description_html,
    }


def test_update_performs_real_update():
    product = make_product()

    loader = LoaderSpy(
        make_current_product()
    )
    writer = WriterSpy(
        {
            "id": 321,
            "sku": "ABC-123",
            "name": product.title,
        }
    )

    config = ProductUpdaterConfig(
        dry_run=False,
    )

    updater = ProductUpdater(
        config=config,
        product_loader=loader,
        product_writer=writer,
    )

    result = updater.update(
        product=product,
        quality_report=make_quality_report(),
    )

    assert result.status == UpdateStatus.UPDATED
    assert result.product_id == 321
    assert result.sent_to_woocommerce is True

    assert writer.calls == [
        (
            321,
            {
                "name": product.title,
                "short_description": product.short_description,
                "description": product.description_html,
            },
        )
    ]

    assert result.updated_product == {
        "id": 321,
        "sku": "ABC-123",
        "name": product.title,
    }


def test_update_rejects_invalid_writer_response():
    product = make_product()

    loader = LoaderSpy(
        make_current_product()
    )

    def invalid_writer(
        product_id: int,
        payload: dict[str, Any],
    ) -> Any:
        return []

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=False,
        ),
        product_loader=loader,
        product_writer=invalid_writer,
    )

    with pytest.raises(
        ProductUpdaterError,
        match=(
            "WooCommerce atjaunināšanas funkcija "
            "neatgrieza vārdnīcu"
        ),
    ):
        updater.update(
            product=product,
            quality_report=make_quality_report(),
        )


def test_update_passes_product_sku_to_loader():
    loader = LoaderSpy(None)

    updater = ProductUpdater(
        product_loader=loader,
        product_writer=WriterSpy(),
    )

    updater.update(
        product=make_product(
            sku="SKU-999",
        ),
        quality_report=make_quality_report(
            sku="SKU-999",
        ),
    )

    assert loader.calls == ["SKU-999"]


# ----------------------------------------------------------------------
# format_update_result
# ----------------------------------------------------------------------


def test_format_update_result_rejects_invalid_type():
    with pytest.raises(
        TypeError,
        match="result jābūt UpdateResult objektam",
    ):
        format_update_result({})


def test_format_update_result_without_changes():
    result = UpdateResult(
        sku="ABC-123",
        status=UpdateStatus.UNCHANGED,
        product_id=321,
        message="WooCommerce produkta dati jau ir aktuāli.",
    )

    text = format_update_result(result)

    assert text == (
        "UNCHANGED: SKU ABC-123\n"
        "WooCommerce produkta dati jau ir aktuāli.\n"
        "WooCommerce produkta ID: 321\n"
        "Maināmi lauki nav atrasti."
    )


def test_format_update_result_without_product_id():
    result = UpdateResult(
        sku="ABC-123",
        status=UpdateStatus.NOT_FOUND,
        message="Produkts netika atrasts.",
    )

    text = format_update_result(result)

    assert "WooCommerce produkta ID:" not in text
    assert "Maināmi lauki nav atrasti." in text


def test_format_update_result_with_changes():
    result = UpdateResult(
        sku="ABC-123",
        status=UpdateStatus.DRY_RUN,
        product_id=321,
        message="Dry-run režīms.",
        changes=(
            UpdateChange(
                field_name="title",
                old_value="Vecais",
                new_value="Jaunais",
            ),
            UpdateChange(
                field_name="description_html",
                old_value="<p>Vecais</p>",
                new_value="<p>Jaunais</p>",
            ),
        ),
    )

    text = format_update_result(result)

    assert text == (
        "DRY_RUN: SKU ABC-123\n"
        "Dry-run režīms.\n"
        "WooCommerce produkta ID: 321\n"
        "Maināmi lauki: 2\n"
        "- title\n"
        "- description_html"
    )