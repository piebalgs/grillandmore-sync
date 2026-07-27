"""Run the GrillAndMore product-description pipeline for one product.

This first CLI version uses a prepared JSON response through FakeLLMClient.
It allows us to test the complete parser -> pipeline workflow safely before
connecting the real OpenAI client.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.descriptions.description_pipeline import (
    DescriptionPipeline,
    PipelineQualityError,
    PipelineResult,
)
from src.descriptions.llm_client import FakeLLMClient
from src.descriptions.parser import (
    DescriptionParseError,
    ProductDescription,
    products_by_sku,
)
from src.descriptions.translator import Translator


SEPARATOR = "=" * 72


class CLIError(RuntimeError):
    """Raised for expected command-line usage errors."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Palaiž GrillAndMore produktu aprakstu pipeline vienam "
            "produktam drošā testa režīmā."
        )
    )

    parser.add_argument(
        "csv_path",
        type=Path,
        help="Ceļš uz Weber Digital Premium CSV failu.",
    )

    parser.add_argument(
        "--sku",
        required=True,
        help="Apstrādājamā produkta SKU.",
    )

    parser.add_argument(
        "--response-json",
        type=Path,
        required=True,
        help=(
            "Fails ar iepriekš sagatavotu LLM JSON atbildi. "
            "Šajā versijā reālais OpenAI API vēl netiek izsaukts."
        ),
    )

    parser.add_argument(
        "--show-html",
        action="store_true",
        help="Parādīt formatēto WooCommerce HTML.",
    )

    parser.add_argument(
        "--show-draft",
        action="store_true",
        help="Parādīt validēto tulkojuma melnrakstu.",
    )

    return parser.parse_args()


def normalize_sku(value: str) -> str:
    sku = value.strip()

    if not sku:
        raise CLIError("SKU nedrīkst būt tukšs.")

    return sku


def load_product(
    csv_path: Path,
    sku: str,
) -> ProductDescription:
    source = csv_path.expanduser()

    if not source.is_file():
        raise CLIError(f"CSV fails nav atrasts: {source}")

    try:
        products = products_by_sku(source)
    except (FileNotFoundError, DescriptionParseError) as exc:
        raise CLIError(str(exc)) from exc

    product = products.get(sku)

    if product is None:
        available_count = len(products)
        raise CLIError(
            f"SKU '{sku}' CSV failā nav atrasts. "
            f"Failā kopā atrasti {available_count} produkti."
        )

    return product


def load_llm_response(path: Path) -> str:
    source = path.expanduser()

    if not source.is_file():
        raise CLIError(
            f"LLM atbildes fails nav atrasts: {source}"
        )

    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise CLIError(
            "LLM atbildes failu neizdevās nolasīt kā UTF-8 tekstu."
        ) from exc
    except OSError as exc:
        raise CLIError(
            f"LLM atbildes failu neizdevās nolasīt: {exc}"
        ) from exc

    stripped = text.strip()

    if not stripped:
        raise CLIError("LLM atbildes fails ir tukšs.")

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise CLIError(
            "LLM atbildes failā nav derīga JSON objekta: "
            f"{exc.msg}, rinda {exc.lineno}, kolonna {exc.colno}."
        ) from exc

    if not isinstance(payload, dict):
        raise CLIError(
            "LLM atbildes faila augšējam līmenim jābūt JSON objektam."
        )

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_pipeline(
    llm_response: str,
) -> DescriptionPipeline:
    llm_client = FakeLLMClient(
        responses=[llm_response],
    )

    translator = Translator(
        llm_client=llm_client,
    )

    return DescriptionPipeline(
        translator=translator,
    )


def value_or_dash(value: Any) -> str:
    if value is None:
        return "-"

    text = str(value).strip()
    return text or "-"


def print_header(
    product: ProductDescription,
    csv_path: Path,
    response_path: Path,
) -> None:
    print(SEPARATOR)
    print("GrillAndMore Description Pipeline")
    print(SEPARATOR)
    print(f"SKU:               {product.sku}")
    print(f"Avota nosaukums:   {value_or_dash(product.title)}")
    print(f"CSV fails:         {csv_path.expanduser()}")
    print(f"LLM atbilde:       {response_path.expanduser()}")
    print("Režīms:            SAFE LOCAL TEST")
    print(SEPARATOR)


def print_quality(result: PipelineResult) -> None:
    quality = result.quality

    print()
    print("KVALITĀTES PĀRBAUDE")
    print("-" * 72)
    print(
        "Statuss:           "
        + ("PASSED" if quality.passed else "FAILED")
    )

    issues = getattr(quality, "issues", ())
    violations = getattr(quality, "violations", ())

    entries = issues or violations

    if entries:
        print(f"Atrasto problēmu skaits: {len(entries)}")

        for entry in entries:
            code = getattr(entry, "code", "")
            message = getattr(entry, "message", str(entry))
            severity = getattr(entry, "severity", "")

            prefix_parts = [
                str(value)
                for value in (severity, code)
                if value
            ]
            prefix = " / ".join(prefix_parts)

            if prefix:
                print(f"  - [{prefix}] {message}")
            else:
                print(f"  - {message}")
    else:
        print("Problēmas:         nav")


def print_update(result: PipelineResult) -> None:
    update = result.update

    print()
    print("ATJAUNINĀŠANAS REZULTĀTS")
    print("-" * 72)
    print(
        f"Veiksmīgs:         "
        f"{'JĀ' if update.success else 'NĒ'}"
    )

    action = getattr(update, "action", None)
    message = getattr(update, "message", None)
    changed = getattr(update, "changed", None)

    if action is not None:
        print(f"Darbība:           {value_or_dash(action)}")

    if changed is not None:
        print(f"Ir izmaiņas:       {'JĀ' if changed else 'NĒ'}")

    if message is not None:
        print(f"Ziņojums:          {value_or_dash(message)}")


def print_draft(result: PipelineResult) -> None:
    draft = result.draft

    print()
    print("VALIDĒTAIS MELNRAKSTS")
    print("-" * 72)

    field_names = (
        "title",
        "introduction",
        "benefits",
        "technologies",
        "suitability",
        "specifications_summary",
        "conclusion",
        "used_knowledge_keys",
        "warnings",
    )

    for field_name in field_names:
        value = getattr(draft, field_name, None)

        if value in (None, "", (), []):
            continue

        print()
        print(f"{field_name}:")

        if isinstance(value, (tuple, list)):
            for item in value:
                print(f"  - {item}")
        else:
            print(value)


def print_html(result: PipelineResult) -> None:
    formatted = result.formatted

    print()
    print("WOOCOMMERCE HTML")
    print("-" * 72)

    html_fields = (
        "description_html",
        "html",
        "long_description",
        "description",
    )

    for field_name in html_fields:
        value = getattr(formatted, field_name, None)

        if isinstance(value, str) and value.strip():
            print(value)
            return

    print(
        "Formatētajā objektā netika atrasts zināms HTML lauks. "
        "Objekta saturs:"
    )
    print(formatted)


def print_summary(result: PipelineResult) -> None:
    print()
    print(SEPARATOR)
    print("PIPELINE KOPSAVILKUMS")
    print(SEPARATOR)
    print(f"SKU:               {result.sku}")
    print(
        "Kvalitāte:         "
        + ("PASSED" if result.quality.passed else "FAILED")
    )
    print(
        "Atjaunināšana:     "
        + ("SUCCESS" if result.update.success else "FAILED")
    )
    print(
        "Kopējais rezultāts:"
        f" {'SUCCESS' if result.success else 'FAILED'}"
    )
    print(SEPARATOR)


def run(args: argparse.Namespace) -> int:
    sku = normalize_sku(args.sku)

    product = load_product(
        csv_path=args.csv_path,
        sku=sku,
    )

    llm_response = load_llm_response(
        args.response_json,
    )

    print_header(
        product=product,
        csv_path=args.csv_path,
        response_path=args.response_json,
    )

    pipeline = build_pipeline(
        llm_response=llm_response,
    )

    try:
        result = pipeline.process(product)
    except PipelineQualityError as exc:
        print()
        print("PIPELINE APTURĒTS KVALITĀTES PĀRBAUDĒ")
        print("-" * 72)
        print(str(exc))

        report = exc.quality_report
        print(
            "Statuss:           "
            + ("PASSED" if report.passed else "FAILED")
        )
        return 1

    print_quality(result)
    print_update(result)

    if args.show_draft:
        print_draft(result)

    if args.show_html:
        print_html(result)

    print_summary(result)

    return 0 if result.success else 1


def main() -> int:
    args = parse_args()

    try:
        return run(args)
    except CLIError as exc:
        print(f"Kļūda: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(
            "\nDarbību pārtrauca lietotājs.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
