"""Tests for applying one generated description to multiple Woo targets."""

from __future__ import annotations

from typing import Any

from src.descriptions.models import FormattedProduct, QualityReport
from src.descriptions.multi_target_updater import update_targets
from src.descriptions.updater import (
    ProductUpdater,
    ProductUpdaterConfig,
    UpdateStatus,
)


def make_product() -> FormattedProduct:
    return FormattedProduct(
        sku="WEBERQ_1200N_BL",
        title="Weber Q1200N",
        short_description="<p>Latviešu īsais apraksts.</p>",
        description_html="<p>Latviešu pilnais apraksts.</p>",
        meta_description="Latviešu meta apraksts.",
        search_keywords=("Weber", "Q1200N", "gāzes grils"),
    )


def make_quality_report() -> QualityReport:
    return QualityReport(
        sku="WEBERQ_1200N_BL",
        checks=(),
        passed=True,
        error_count=0,
        warning_count=0,
    )


class ProductLoader:
    def __init__(self) -> None:
        self.calls: list[str] = []

        self.products: dict[str, dict[str, Any]] = {
            "1501071": {
                "id": 101,
                "sku": "1501071",
                "name": "Gāzes grils Weber Q1200N",
                "short_description": "",
                "description": "",
                "meta_data": [],
            },
            "1501086": {
                "id": 102,
                "sku": "1501086",
                "name": "Gāzes grils Weber Q1200N ar statīvu",
                "short_description": "",
                "description": "",
                "meta_data": [],
            },
        }

    def __call__(self, sku: str) -> dict[str, Any] | None:
        self.calls.append(sku)
        return self.products.get(sku)


class WriterSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, Any]]] = []

    def __call__(
        self,
        product_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((product_id, payload))
        return {"id": product_id}


def test_update_targets_creates_dry_run_for_each_target():
    loader = ProductLoader()
    writer = WriterSpy()

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=loader,
        product_writer=writer,
    )

    results = update_targets(
        product=make_product(),
        quality_report=make_quality_report(),
        target_skus=("1501071", "1501086"),
        updater=updater,
    )

    assert len(results) == 2

    assert tuple(result.sku for result in results) == (
        "1501071",
        "1501086",
    )

    assert all(
        result.status == UpdateStatus.DRY_RUN
        for result in results
    )

    assert loader.calls == [
        "1501071",
        "1501086",
    ]

    assert writer.calls == []


def test_update_targets_preserves_existing_woo_titles():
    loader = ProductLoader()

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=loader,
    )

    results = update_targets(
        product=make_product(),
        quality_report=make_quality_report(),
        target_skus=("1501071", "1501086"),
        updater=updater,
    )

    assert all(
        "name" not in result.payload
        for result in results
    )
import pytest


def test_update_targets_rejects_empty_target_list():
    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=ProductLoader(),
    )

    with pytest.raises(ValueError, match="target_skus"):
        update_targets(
            product=make_product(),
            quality_report=make_quality_report(),
            target_skus=(),
            updater=updater,
        )
def test_update_targets_rejects_string_as_target_skus():
    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=ProductLoader(),
    )

    with pytest.raises(TypeError, match="target_skus"):
        update_targets(
            product=make_product(),
            quality_report=make_quality_report(),
            target_skus="1501071",
            updater=updater,
        )

def test_update_targets_adds_stand_configuration_only_to_bundle():
    loader = ProductLoader()
    writer = WriterSpy()

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=True,
            update_title=False,
        ),
        product_loader=loader,
        product_writer=writer,
    )

    results = update_targets(
        product=make_product(),
        quality_report=make_quality_report(),
        target_skus=("1501071", "1501086"),
        updater=updater,
    )

    results_by_sku = {
        result.sku: result
        for result in results
    }

    regular_html = results_by_sku["1501071"].payload["description"]
    bundle_html = results_by_sku["1501086"].payload["description"]

    assert "<h2>Komplektācija</h2>" not in regular_html

    assert "<h2>Komplektācija</h2>" in bundle_html
    assert "grils un statīvs" in bundle_html

    assert all(
        result.status == UpdateStatus.DRY_RUN
        for result in results
    )

    assert writer.calls == []

def test_invalid_configuration_html_blocks_woo_update(
    monkeypatch,
):
    from dataclasses import replace
    import src.descriptions.multi_target_updater as module

    loader = ProductLoader()
    writer = WriterSpy()

    updater = ProductUpdater(
        config=ProductUpdaterConfig(
            dry_run=False,
            update_title=False,
        ),
        product_loader=loader,
        product_writer=writer,
    )

    original_apply = module.apply_target_configuration

    def invalid_configuration(*, product, target_sku):
        configured = original_apply(
            product=product,
            target_sku=target_sku,
        )

        if target_sku == "1501086":
            return replace(
                configured,
                description_html="<p>Neaizvērts HTML",
            )

        return configured

    monkeypatch.setattr(
        module,
        "apply_target_configuration",
        invalid_configuration,
    )

    with pytest.raises(ValueError):
        module.update_targets(
            product=make_product(),
            quality_report=make_quality_report(),
            target_skus=("1501086",),
            updater=updater,
        )

    assert writer.calls == []

