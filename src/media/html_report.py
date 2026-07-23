from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "templates" / "image_sync_report.html"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _first_value(result: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = result.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _result_sku(result: dict[str, Any]) -> str:
    return _text(_first_value(result, "sku", "product_sku", "normalized_sku"))


def _result_name(result: dict[str, Any]) -> str:
    return _text(_first_value(result, "name", "product_name", "title"))


def _result_action(result: dict[str, Any]) -> str:
    return _text(_first_value(result, "action", "status")).upper() or "UNKNOWN"


def _result_verify_status(result: dict[str, Any]) -> str:
    return _text(
        _first_value(
            result,
            "verify_status",
            "verification_status",
            "verify",
        )
    ).upper()


def _result_message(result: dict[str, Any]) -> str:
    return _text(_first_value(result, "message", "error", "reason", "details"))


def _image_count(result: dict[str, Any]) -> int | str:
    direct_count = _first_value(
        result,
        "image_count",
        "images_count",
        "target_image_count",
        "brandfolder_image_count",
    )
    if direct_count != "":
        try:
            return int(direct_count)
        except (TypeError, ValueError):
            return _text(direct_count)

    for key in (
        "images",
        "target_images",
        "brandfolder_images",
        "prepared_images",
        "woocommerce_images",
    ):
        images = result.get(key)
        if isinstance(images, list):
            return len(images)

    return ""


def _category_for_result(
    result: dict[str, Any],
) -> tuple[str, str, str]:
    action = _result_action(result)
    verify_status = _result_verify_status(result)

    if action in {"ERROR", "FAILED", "EXCEPTION"}:
        return "error", "Kļūda", "🔴"

    if (
        action in {"VERIFY_FAILED", "VERIFICATION_FAILED"}
        or verify_status in {"FAILED", "FAIL", "ERROR"}
    ):
        return "verify-failed", "Verify failed", "🔴"

    if action in {
        "MANUAL_REVIEW",
        "REVIEW",
        "NEEDS_REVIEW",
        "SKIPPED_MANUAL_REVIEW",
        "SKIP_REVIEW",
    }:
        return "manual-review", "Manuāli jāpārbauda", "🟠"

    if action in {
        "DRY_RUN_SYNC",
        "DRY_RUN",
        "WOULD_UPDATE",
        "PLANNED_UPDATE",
    }:
        return "dry-run", "Dry run SYNC", "🔵"

    if action in {"UPDATED", "SYNCED"}:
        if verify_status == "OK":
            return "updated", "Atjaunināts un pārbaudīts", "🟢"
        return "updated", "Atjaunināts", "🟡"

    if action in {
        "ALREADY_OK",
        "OK",
        "UNCHANGED",
        "NO_CHANGE",
        "SKIPPED_ALREADY_OK",
        "SKIP_OK",
    }:
        return "already-ok", "Jau kārtībā", "🟢"

    if verify_status == "OK":
        return "verify-passed", "Verify passed", "🟢"

    return "unknown", action.replace("_", " ").title(), "⚪"


def _filename_list_html(title: str, values: Any) -> str:
    """Izveido attēlu sarakstu ar priekšskatījumiem, ja pieejams URL."""
    if not isinstance(values, list) or not values:
        return ""

    items: list[str] = []

    for value in values:
        if isinstance(value, dict):
            filename = _text(value.get("filename"))
            image_url = _text(value.get("url"))

            if not filename and not image_url:
                continue

            escaped_filename = html.escape(
                filename or "(nav faila nosaukuma)"
            )

            if image_url:
                escaped_url = html.escape(
                    image_url,
                    quote=True,
                )

                items.append(
                    "<li>"
                    f'<a href="{escaped_url}" '
                    'target="_blank" rel="noopener noreferrer">'
                    f'<img src="{escaped_url}" '
                    f'alt="{escaped_filename}" '
                    'loading="lazy" '
                    'style="width:120px;height:90px;'
                    'object-fit:contain;display:block;'
                    'margin-bottom:6px;">'
                    "</a>"
                    f"<span>{escaped_filename}</span>"
                    "</li>"
                )
            else:
                items.append(
                    f"<li>{escaped_filename}</li>"
                )

        else:
            filename = _text(value)

            if filename:
                items.append(
                    f"<li>{html.escape(filename)}</li>"
                )

    if not items:
        return ""

    return (
        '<section class="image-list">'
        f"<strong>{html.escape(title)}</strong>"
        f"<ol>{''.join(items)}</ol>"
        "</section>"
    )


def _details_html(result: dict[str, Any]) -> str:
    preview = "".join(
        [
            _filename_list_html("Esošie WooCommerce attēli", result.get("existing_images")),
            _filename_list_html("Pievienos no Brandfolder", result.get("missing_images")),
            _filename_list_html("Neiekļaus galerijas limita dēļ", result.get("skipped_images")),
            _filename_list_html("Galerija pēc sinhronizācijas", result.get("payload_images")),
        ]
    )

    raw_json = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    return (
        "<details>"
        "<summary>Skatīt sinhronizācijas plānu</summary>"
        f"{preview}"
        "<details class=\"raw-details\">"
        "<summary>Tehniskā informācija</summary>"
        f"<pre>{html.escape(raw_json)}</pre>"
        "</details>"
        "</details>"
    )


def _table_rows(results: list[dict[str, Any]]) -> str:
    rows: list[str] = []

    for result in results:
        category, label, icon = _category_for_result(result)
        sku = _result_sku(result) or "(nav SKU)"
        name = _result_name(result) or "(nav nosaukuma)"
        message = _result_message(result)
        verify_status = _result_verify_status(result)
        image_count = _image_count(result)

        searchable = " ".join(
            [
                sku,
                name,
                label,
                _result_action(result),
                verify_status,
                message,
            ]
        ).casefold()

        rows.append(
            "\n".join(
                [
                    (
                        f'<tr data-category="{html.escape(category)}" '
                        f'data-search="{html.escape(searchable)}">'
                    ),
                    f'<td class="sku-cell">{html.escape(sku)}</td>',
                    f"<td>{html.escape(name)}</td>",
                    (
                        f'<td><span class="status-badge status-{html.escape(category)}">'
                        f'<span aria-hidden="true">{icon}</span> '
                        f"{html.escape(label)}</span></td>"
                    ),
                    f"<td>{html.escape(verify_status or '—')}</td>",
                    (
                        '<td class="number-cell">'
                        f"{html.escape(str(image_count)) if image_count != '' else '—'}"
                        "</td>"
                    ),
                    f"<td>{html.escape(message) if message else '—'}</td>",
                    f"<td>{_details_html(result)}</td>",
                    "</tr>",
                ]
            )
        )

    if rows:
        return "\n".join(rows)

    return (
        '<tr class="empty-row">'
        '<td colspan="7">Nav rezultātu, ko attēlot.</td>'
        "</tr>"
    )


def _summary_counts(results: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for result in results:
        category, _, _ = _category_for_result(result)
        counts[category] += 1
    return counts


def _summary_cards(results: list[dict[str, Any]]) -> str:
    counts = _summary_counts(results)
    cards = [
        ("processed", "Apstrādāti", len(results), "📦"),
        ("already-ok", "Jau kārtībā", counts["already-ok"], "✅"),
        ("updated", "Atjaunināti", counts["updated"], "🔄"),
        ("dry-run", "Dry run SYNC", counts["dry-run"], "🧪"),
        (
            "manual-review",
            "Manuāli jāpārbauda",
            counts["manual-review"],
            "⚠️",
        ),
        (
            "verify-failed",
            "Verify failed",
            counts["verify-failed"],
            "❌",
        ),
        ("error", "Kļūdas", counts["error"], "🛑"),
    ]

    return "\n".join(
        (
            f'<article class="summary-card card-{category}">'
            f'<div class="summary-icon">{icon}</div>'
            '<div class="summary-content">'
            f'<div class="summary-value">{value}</div>'
            f'<div class="summary-label">{html.escape(label)}</div>'
            "</div></article>"
        )
        for category, label, value, icon in cards
    )


def generate_html_report(
    *,
    results: list[dict[str, Any]],
    brand: str | None = None,
    apply: bool = False,
    selection: str | None = None,
    template_path: Path | None = None,
    reports_dir: Path | None = None,
) -> Path:
    selected_template = template_path or DEFAULT_TEMPLATE_PATH
    selected_reports_dir = reports_dir or DEFAULT_REPORTS_DIR

    if not selected_template.exists():
        raise FileNotFoundError(
            f"HTML atskaites veidne nav atrasta: {selected_template}"
        )

    template = selected_template.read_text(encoding="utf-8")
    generated_at = datetime.now()
    timestamp = generated_at.strftime("%Y-%m-%d_%H%M%S")
    report_path = selected_reports_dir / f"image_sync_{timestamp}.html"
    selected_reports_dir.mkdir(parents=True, exist_ok=True)

    mode_label = "REĀLAIS REŽĪMS" if apply else "DRY RUN"
    selection_label = (
        selection
        or (f"Zīmols: {brand}" if brand else "Visi izvēlētie produkti")
    )

    replacements = {
        "{{PAGE_TITLE}}": "GrillAndMore Image Sync Report",
        "{{GENERATED_AT}}": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        "{{MODE}}": mode_label,
        "{{MODE_CLASS}}": "mode-live" if apply else "mode-dry-run",
        "{{SELECTION}}": selection_label,
        "{{SUMMARY_CARDS}}": _summary_cards(results),
        "{{TABLE_ROWS}}": _table_rows(results),
        "{{TOTAL_RESULTS}}": str(len(results)),
    }

    report_html = template
    escaped_placeholders = {
        "{{PAGE_TITLE}}",
        "{{GENERATED_AT}}",
        "{{MODE}}",
        "{{MODE_CLASS}}",
        "{{SELECTION}}",
        "{{TOTAL_RESULTS}}",
    }

    for placeholder, value in replacements.items():
        report_html = report_html.replace(
            placeholder,
            html.escape(value) if placeholder in escaped_placeholders else value,
        )

    report_path.write_text(report_html, encoding="utf-8")
    return report_path
