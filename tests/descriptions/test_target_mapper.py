from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
)
from src.descriptions.target_mapper import map_to_target


def test_map_to_target_replaces_only_sku():
    product = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N",
        short_description="Latviešu īsais apraksts.",
        description_html="<p>Latviešu pilnais apraksts.</p>",
        meta_description="Latviešu meta apraksts.",
        search_keywords=("weber", "q1200n"),
        warnings=("Brīdinājums",),
        metadata={"source": "weber"},
    )

    quality = QualityReport(
        sku="WEBERQ_1200N_BL",
        checks=(),
        passed=True,
        error_count=0,
        warning_count=0,
    )

    mapped_product, mapped_quality = map_to_target(
        product=product,
        quality_report=quality,
        target_sku="1501071",
    )

    assert mapped_product.sku == "1501071"
    assert mapped_quality.sku == "1501071"

    assert mapped_product.title == product.title
    assert mapped_product.short_description == product.short_description
    assert mapped_product.description_html == product.description_html
    assert mapped_product.meta_description == product.meta_description
    assert mapped_product.search_keywords == product.search_keywords
    assert mapped_product.warnings == product.warnings
    assert mapped_product.metadata == product.metadata

    assert mapped_quality.checks == quality.checks
    assert mapped_quality.passed == quality.passed
    assert mapped_quality.error_count == quality.error_count
    assert mapped_quality.warning_count == quality.warning_count


def test_map_to_target_does_not_modify_source_objects():
    product = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N",
        short_description="Īsais apraksts.",
        description_html="<p>Pilnais apraksts.</p>",
    )

    quality = QualityReport(
        sku="WEBERQ_1200N_BL",
        checks=(),
        passed=True,
        error_count=0,
        warning_count=0,
    )

    map_to_target(
        product=product,
        quality_report=quality,
        target_sku="1501086",
    )

    assert product.sku == "WEBERQ_1200N_BL"
    assert quality.sku == "WEBERQ_1200N_BL"
import pytest


def test_map_to_target_rejects_empty_target_sku():
    product = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N",
        short_description="Īsais apraksts.",
        description_html="<p>Pilnais apraksts.</p>",
    )

    quality = QualityReport(
        sku="WEBERQ_1200N_BL",
        checks=(),
        passed=True,
        error_count=0,
        warning_count=0,
    )

    with pytest.raises(ValueError, match="target_sku"):
        map_to_target(
            product=product,
            quality_report=quality,
            target_sku="   ",
        )


def test_map_to_target_rejects_mismatched_source_skus():
    product = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N",
        short_description="Īsais apraksts.",
        description_html="<p>Pilnais apraksts.</p>",
    )

    quality = QualityReport(
        sku="OTHER_PRODUCT",
        checks=(),
        passed=True,
        error_count=0,
        warning_count=0,
    )

    with pytest.raises(ValueError, match="SKU nesakrīt"):
        map_to_target(
            product=product,
            quality_report=quality,
            target_sku="1501071",
        )


def test_map_to_target_rejects_invalid_target_sku_type():
    product = FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N",
        short_description="Īsais apraksts.",
        description_html="<p>Pilnais apraksts.</p>",
    )

    quality = QualityReport(
        sku="WEBERQ_1200N_BL",
        checks=(),
        passed=True,
        error_count=0,
        warning_count=0,
    )

    with pytest.raises(TypeError, match="target_sku"):
        map_to_target(
            product=product,
            quality_report=quality,
            target_sku=123,  # type: ignore[arg-type]
        )