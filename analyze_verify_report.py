#!/usr/bin/env python3

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analizē verify_media CSV atskaiti."
    )
    parser.add_argument(
        "report",
        nargs="?",
        default="reports/verify_media_weber.csv",
        help="Analizējamās CSV atskaites ceļš.",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=10,
        help="Cik SKU piemērus rādīt katrai kategorijai.",
    )
    parser.add_argument(
        "--status",
        choices=("PASS", "WARNING", "FAIL", "ALL"),
        default="FAIL",
        help="Kuru statusu analizēt.",
    )
    return parser.parse_args()


def read_report(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Atskaite nav atrasta: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        return list(csv.DictReader(csv_file))


def as_int(value: Any) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def classify_row(row: dict[str, Any]) -> str:
    message = str(row.get("message", "")).strip()
    wc_count = as_int(row.get("wc_count"))
    bf_count = as_int(row.get("brandfolder_count"))
    missing_count = as_int(row.get("missing_count"))
    extra_count = as_int(row.get("extra_count"))
    duplicate_count = as_int(row.get("duplicate_count"))

    if "Produktam nav SKU" in message:
        return "Produktam nav SKU"

    if "Brandfolder kļūda" in message:
        return "Brandfolder API kļūda"

    if wc_count == 0 and bf_count == 0:
        return "Nav attēlu ne WooCommerce, ne Brandfolder"

    if wc_count == 0 and bf_count > 0:
        return f"WooCommerce nav attēlu, Brandfolder ir {bf_count}"

    if bf_count == 0 and wc_count > 0:
        return f"Brandfolder nav attēlu, WooCommerce ir {wc_count}"

    if duplicate_count > 0:
        return f"WooCommerce ir {duplicate_count} dublikāti"

    if missing_count > 0 and extra_count > 0:
        return (
            f"Trūkst {missing_count}, "
            f"papildu WooCommerce {extra_count}"
        )

    if missing_count > 0:
        return f"WooCommerce trūkst {missing_count} attēli"

    if extra_count > 0:
        return f"WooCommerce ir {extra_count} papildu attēli"

    if wc_count > 10:
        return "WooCommerce ir vairāk nekā 10 attēli"

    return message or "Cita neatbilstība"


def main() -> int:
    args = parse_args()

    report_path = Path(args.report)

    if not report_path.is_absolute():
        report_path = PROJECT_DIR / report_path

    try:
        rows = read_report(report_path)
    except Exception as exc:
        print(f"Kļūda: {exc}")
        return 1

    all_statuses = Counter(
        str(row.get("status", "")).strip()
        for row in rows
    )

    print(f"Atskaite: {report_path}")
    print(f"Kopā ierakstu: {len(rows)}")
    print()
    print("Statusu kopsavilkums:")
    print(f"  PASS:    {all_statuses.get('PASS', 0)}")
    print(f"  WARNING: {all_statuses.get('WARNING', 0)}")
    print(f"  FAIL:    {all_statuses.get('FAIL', 0)}")

    if args.status == "ALL":
        selected_rows = rows
    else:
        selected_rows = [
            row
            for row in rows
            if str(row.get("status", "")).strip() == args.status
        ]

    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in selected_rows:
        categories[classify_row(row)].append(row)

    print()
    print(
        f"{args.status} analīze — "
        f"{len(selected_rows)} ieraksti:"
    )

    sorted_categories = sorted(
        categories.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )

    for category, category_rows in sorted_categories:
        print()
        print(f"{len(category_rows):4}  {category}")

        examples = category_rows[: args.examples]

        for row in examples:
            sku = str(row.get("sku", "")).strip() or "(nav SKU)"
            name = str(row.get("name", "")).strip()
            wc_count = as_int(row.get("wc_count"))
            bf_count = as_int(row.get("brandfolder_count"))
            missing_count = as_int(row.get("missing_count"))
            extra_count = as_int(row.get("extra_count"))

            print(
                f"      {sku} | WC={wc_count} BF={bf_count} "
                f"trūkst={missing_count} papildu={extra_count} "
                f"| {name}"
            )

        remaining = len(category_rows) - len(examples)

        if remaining > 0:
            print(f"      ... un vēl {remaining}")

    print()
    print("Analīze pabeigta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
