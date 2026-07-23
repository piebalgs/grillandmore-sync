#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests

import src.media_audit as media_audit

from src.brandfolder import (
    BrandfolderError,
    create_session as create_brandfolder_session,
    get_product_images,
)
from src.media_audit import (
    MAX_IMAGES_PER_PRODUCT,
    MediaAuditResult,
    audit_product,
    filter_products,
    normalize_sku,
    select_product_range,
    summarize_results,
)
from src.woocommerce import load_products


VERSION = "2.1.0"
PROJECT_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = PROJECT_ROOT / "reports"


def filename_from_value(value: Any) -> str:
    """Atgriež faila nosaukumu no URL, ceļa vai vienkārša nosaukuma."""
    text = unquote(str(value or "")).strip()

    if not text:
        return ""

    text = text.split("?", 1)[0].split("#", 1)[0]
    parsed = urlparse(text)

    if parsed.scheme or parsed.netloc:
        text = parsed.path

    return Path(text).name


def image_filename(image: dict[str, Any]) -> str:
    """Atrod ticamāko attēla faila nosaukumu dažādos API laukos."""
    for key in ("filename", "name", "src", "url", "alt"):
        filename = filename_from_value(image.get(key))

        if filename:
            return filename

    return ""


def normalized_image_key(value: Any) -> str:
    """
    Normalizē attēla nosaukumu, saglabājot nozīmīgus ciparus.

    Tiek ignorēti:
      - faila paplašinājums;
      - WordPress izmēra sufiksi, piemēram, -300x300;
      - -scaled;
      - WordPress dublikāta sufiksi ar defisi, piemēram, -1;
      - atstarpes, defises un pasvītrojumi.
    """
    filename = filename_from_value(value)

    if not filename:
        return ""

    stem = Path(filename).stem.casefold()
    stem = re.sub(r"-\d+x\d+$", "", stem)
    stem = re.sub(r"-scaled$", "", stem)
    stem = re.sub(r"-\d+$", "", stem)
    stem = re.sub(r"[\s_-]+", "", stem)

    return stem.upper()


def smart_woocommerce_keys(
    images: list[dict[str, Any]],
    brandfolder_keys: set[str],
) -> set[str]:
    """
    Izveido WooCommerce attēlu atslēgas.

    WordPress reizēm pievieno ciparu tieši faila beigās:
      14801004a.webp   -> 14801004a1.webp
      3400134argb.webp -> 3400134argb2.webp

    Cipars tiek noņemts tikai tad, ja iegūtais pamata nosaukums tiešām
    eksistē Brandfolder attēlu kopā.
    """
    keys: set[str] = set()

    for image in images:
        key = normalized_image_key(image_filename(image))

        if not key:
            continue

        keys.add(key)

        duplicate_match = re.fullmatch(r"(.+[A-Z])([1-9]\d*)", key)

        if duplicate_match:
            candidate = duplicate_match.group(1)

            if candidate in brandfolder_keys:
                keys.add(candidate)

    return keys


def smart_compare_image_keys(
    *,
    wc: list[dict[str, Any]],
    brandfolder: list[dict[str, Any]],
) -> tuple[int, int]:
    """Salīdzina attēlus pēc gudri normalizētiem nosaukumiem."""
    bf_keys = {
        normalized_image_key(image_filename(image))
        for image in brandfolder
    }
    bf_keys.discard("")

    wc_keys = smart_woocommerce_keys(wc, bf_keys)
    missing_from_wc = len(bf_keys - wc_keys)

    original_wc_keys = {
        normalized_image_key(image_filename(image))
        for image in wc
    }
    original_wc_keys.discard("")

    matched_original_wc: set[str] = set()

    for wc_key in original_wc_keys:
        if wc_key in bf_keys:
            matched_original_wc.add(wc_key)
            continue

        duplicate_match = re.fullmatch(r"(.+[A-Z])([1-9]\d*)", wc_key)

        if (
            duplicate_match
            and duplicate_match.group(1) in bf_keys
        ):
            matched_original_wc.add(wc_key)

    extra_in_wc = len(original_wc_keys - matched_original_wc)

    return missing_from_wc, extra_in_wc


# audit_product() atrodas src/media_audit.py. Aizstājam tikai attēlu
# salīdzināšanas funkciju. Skripts joprojām ir tikai audits.
media_audit.compare_image_keys = smart_compare_image_keys


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def load_sku_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"SKU fails nav atrasts: {path}"
        )

    skus: set[str] = set()

    with path.open("r", encoding="utf-8-sig") as file:
        for line in file:
            value = line.strip()

            if not value or value.startswith("#"):
                continue

            for part in value.replace(";", ",").split(","):
                sku = normalize_sku(part)

                if sku:
                    skus.add(sku)

    return skus


def report_path(
    *,
    brand: str | None,
    exclude_brand: str | None,
    custom_path: str | None,
) -> Path:
    if custom_path:
        path = Path(custom_path).expanduser()

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        return path

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    brand_part = (
        "".join(
            character.lower()
            if character.isalnum()
            else "_"
            for character in (
                brand
                or (f"non_{exclude_brand}" if exclude_brand else "all")
            )
        ).strip("_")
        or "all"
    )

    return (
        REPORTS_DIR
        / f"media_report_{brand_part}_{timestamp}.csv"
    )


def save_csv(
    results: list[MediaAuditResult],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "catalogue_position",
        "product_id",
        "sku",
        "product",
        "brand",
        "wc_images",
        "bf_images",
        "expected_images",
        "webp_images",
        "legacy_images",
        "other_images",
        "missing_media_ids",
        "duplicate_media_ids",
        "duplicate_filenames",
        "missing_from_wc",
        "extra_in_wc",
        "over_limit",
        "status",
        "severity",
        "health",
        "notes",
        "brandfolder_error",
    ]

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            delimiter=";",
        )

        writer.writeheader()

        for result in results:
            writer.writerow(result.to_dict())


def html_report_path(csv_path: Path) -> Path:
    """Atgriež HTML atskaites ceļu blakus CSV failam."""
    return csv_path.with_suffix(".html")


def save_html(
    results: list[MediaAuditResult],
    path: Path,
    *,
    brand: str | None,
    exclude_brand: str | None,
    elapsed: float,
) -> None:
    """Saglabā interaktīvu, pašpietiekamu HTML audita atskaiti."""
    path.parent.mkdir(parents=True, exist_ok=True)
    statistics = summarize_results(results)
    generated_at = datetime.now().strftime("%d.%m.%Y. %H:%M:%S")
    filter_text = brand or (
        f"visi, izņemot {exclude_brand}" if exclude_brand else "visi zīmoli"
    )
    rows: list[str] = []

    for result in results:
        data = result.to_dict()
        severity = str(data.get("severity") or "").upper()
        product_id = str(data.get("product_id") or "").strip()
        sku = str(data.get("sku") or "")
        product = str(data.get("product") or "")
        notes = str(data.get("notes") or "")
        brand_name = str(data.get("brand") or "")
        edit_url = (
            "https://grillandmore.lv/shop/wp-admin/post.php?"
            f"post={product_id}&action=edit"
            if product_id
            else ""
        )
        action = (
            f'<a class="action-link" href="{html.escape(edit_url, quote=True)}" '
            'target="_blank" rel="noopener noreferrer">Atvērt produktu</a>'
            if edit_url
            else '<span class="muted">Nav ID</span>'
        )
        searchable = " ".join(
            [sku, product, brand_name, severity, notes]
        ).casefold()
        bf_value = (
            data.get("bf_images")
            if data.get("bf_images") is not None
            else "Kļūda"
        )
        rows.append(
            "<tr "
            f'data-severity="{html.escape(severity, quote=True)}" '
            f'data-search="{html.escape(searchable, quote=True)}">'
            f'<td>{html.escape(str(data.get("catalogue_position") or ""))}</td>'
            f'<td class="sku">{html.escape(sku)}</td>'
            f'<td><strong>{html.escape(product)}</strong>'
            f'<div class="notes">{html.escape(notes)}</div></td>'
            f'<td>{html.escape(brand_name)}</td>'
            f'<td class="number">{html.escape(str(data.get("wc_images") or 0))}</td>'
            f'<td class="number">{html.escape(str(bf_value))}</td>'
            f'<td class="number">{html.escape(str(data.get("missing_from_wc") or 0))}</td>'
            f'<td class="number">{html.escape(str(data.get("extra_in_wc") or 0))}</td>'
            f'<td><span class="badge {severity.lower()}">{html.escape(severity)}</span></td>'
            f'<td class="number">{html.escape(str(data.get("health") or 0))}%</td>'
            f'<td>{action}</td>'
            "</tr>"
        )

    document = f"""<!doctype html>
<html lang="lv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grillandmore attēlu audits</title>
<style>
:root {{ color-scheme:light dark; --bg:#f4f6f8; --panel:#fff; --text:#18212b; --muted:#6b7280; --line:#dfe3e8; --pass:#157347; --warning:#9a6700; --fail:#b42318; }}
@media (prefers-color-scheme:dark) {{ :root {{ --bg:#111827; --panel:#1f2937; --text:#f3f4f6; --muted:#9ca3af; --line:#374151; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1600px; margin:auto; padding:24px; }}
h1 {{ margin:0 0 4px; font-size:28px; }}
.meta {{ color:var(--muted); margin-bottom:20px; }}
.cards {{ display:grid; grid-template-columns:repeat(4,minmax(140px,1fr)); gap:12px; margin-bottom:18px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px; box-shadow:0 2px 8px rgba(0,0,0,.04); }}
.card .label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
.card .value {{ font-size:30px; font-weight:700; margin-top:4px; }}
.controls {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:12px; margin-bottom:14px; position:sticky; top:0; z-index:10; }}
input[type="search"] {{ flex:1 1 320px; padding:10px 12px; border:1px solid var(--line); border-radius:8px; background:var(--panel); color:var(--text); }}
button {{ border:1px solid var(--line); background:var(--panel); color:var(--text); padding:9px 12px; border-radius:8px; cursor:pointer; }}
button.active {{ outline:2px solid currentColor; }}
.table-wrap {{ overflow:auto; background:var(--panel); border:1px solid var(--line); border-radius:12px; }}
table {{ width:100%; border-collapse:collapse; min-width:1180px; }}
th,td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ position:sticky; top:61px; background:var(--panel); z-index:5; cursor:pointer; white-space:nowrap; }}
tbody tr:hover {{ background:rgba(127,127,127,.07); }}
.number {{ text-align:right; font-variant-numeric:tabular-nums; }}
.sku {{ white-space:nowrap; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.notes {{ color:var(--muted); margin-top:4px; max-width:620px; }}
.badge {{ display:inline-block; border-radius:999px; padding:3px 8px; font-size:12px; font-weight:700; }}
.badge.pass {{ color:#fff; background:var(--pass); }}
.badge.warning {{ color:#fff; background:var(--warning); }}
.badge.fail {{ color:#fff; background:var(--fail); }}
.action-link {{ white-space:nowrap; }}
.muted {{ color:var(--muted); }}
.footer {{ color:var(--muted); margin-top:12px; }}
@media (max-width:760px) {{ main {{ padding:12px; }} .cards {{ grid-template-columns:repeat(2,1fr); }} }}
</style>
</head>
<body>
<main>
<h1>Grillandmore attēlu audits</h1>
<div class="meta">Versija {VERSION} · filtrs: {html.escape(filter_text)} · izveidots {generated_at} · ilgums {format_duration(elapsed)}</div>
<section class="cards">
<div class="card"><div class="label">Kopā</div><div class="value">{len(results)}</div></div>
<div class="card"><div class="label">PASS</div><div class="value">{statistics['pass']}</div></div>
<div class="card"><div class="label">WARNING</div><div class="value">{statistics['warning']}</div></div>
<div class="card"><div class="label">FAIL</div><div class="value">{statistics['fail']}</div></div>
</section>
<div class="controls">
<input id="search" type="search" placeholder="Meklēt pēc SKU, produkta, zīmola vai piezīmēm…">
<button class="filter active" data-filter="ALL">Visi</button>
<button class="filter" data-filter="PASS">PASS</button>
<button class="filter" data-filter="WARNING">WARNING</button>
<button class="filter" data-filter="FAIL">FAIL</button>
<span id="visibleCount" class="muted"></span>
</div>
<div class="table-wrap">
<table id="auditTable">
<thead><tr>
<th data-col="0">Nr.</th><th data-col="1">SKU</th><th data-col="2">Produkts / piezīmes</th><th data-col="3">Zīmols</th><th data-col="4">WC</th><th data-col="5">BF</th><th data-col="6">Trūkst WC</th><th data-col="7">Lieki WC</th><th data-col="8">Statuss</th><th data-col="9">Veselība</th><th>Darbība</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
<div class="footer">CSV un HTML satur viena un tā paša audita rezultātus. Šī atskaite neveic izmaiņas WooCommerce.</div>
</main>
<script>
const state={{filter:'ALL',query:'',sortCol:null,sortAsc:true}};
const tbody=document.querySelector('#auditTable tbody');
const rows=[...tbody.querySelectorAll('tr')];
const count=document.getElementById('visibleCount');
function applyFilters(){{
 let visible=0;
 for(const row of rows){{
  const okFilter=state.filter==='ALL'||row.dataset.severity===state.filter;
  const okSearch=!state.query||row.dataset.search.includes(state.query);
  row.hidden=!(okFilter&&okSearch);
  if(!row.hidden) visible++;
 }}
 count.textContent=`Redzami ${{visible}} no ${{rows.length}}`;
}}
document.getElementById('search').addEventListener('input',event=>{{
 state.query=event.target.value.trim().toLocaleLowerCase('lv');
 applyFilters();
}});
document.querySelectorAll('.filter').forEach(button=>button.addEventListener('click',()=>{{
 document.querySelectorAll('.filter').forEach(item=>item.classList.remove('active'));
 button.classList.add('active');
 state.filter=button.dataset.filter;
 applyFilters();
}}));
document.querySelectorAll('th[data-col]').forEach(header=>header.addEventListener('click',()=>{{
 const col=Number(header.dataset.col);
 state.sortAsc=state.sortCol===col?!state.sortAsc:true;
 state.sortCol=col;
 rows.sort((a,b)=>{{
  const av=a.children[col].innerText.trim();
  const bv=b.children[col].innerText.trim();
  const an=Number(av.replace('%',''));
  const bn=Number(bv.replace('%',''));
  let comparison=Number.isFinite(an)&&Number.isFinite(bn)
   ? an-bn
   : av.localeCompare(bv,'lv',{{numeric:true,sensitivity:'base'}});
  return state.sortAsc?comparison:-comparison;
 }});
 rows.forEach(row=>tbody.appendChild(row));
 applyFilters();
}}));
applyFilters();
</script>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def print_result(
    result: MediaAuditResult,
    *,
    verbose: bool,
) -> None:
    icon = {
        "PASS": "✅",
        "WARNING": "⚠️",
        "FAIL": "❌",
    }.get(result.severity, "•")

    bf_text = (
        str(result.bf_images)
        if result.bf_images is not None
        else "KĻŪDA"
    )

    print(
        f"{icon} {result.catalogue_position:>4} | "
        f"{result.sku:<14} | "
        f"WC {result.wc_images:<2} | "
        f"BF {bf_text:<6} | "
        f"{result.status:<22} | "
        f"{result.health:>3}%"
    )

    if verbose or result.severity != "PASS":
        print(f"      {result.product}")

        if result.notes:
            print(f"      {result.notes}")

        if result.brandfolder_error:
            print(
                "      Brandfolder: "
                f"{result.brandfolder_error}"
            )


def print_summary(
    *,
    brand: str | None,
    exclude_brand: str | None,
    offset: int,
    products_count: int,
    total_filtered: int,
    results: list[MediaAuditResult],
    elapsed: float,
    report: Path,
) -> None:
    statistics = summarize_results(results)

    print("\n" + "=" * 72)
    print("ATTĒLU AUDITA KOPSAVILKUMS")
    print("=" * 72)
    print(f"Versija:                       {VERSION}")
    if brand:
        filter_text = brand
    elif exclude_brand:
        filter_text = f"visi, izņemot {exclude_brand}"
    else:
        filter_text = "visi zīmoli"

    print(f"Zīmola filtrs:                 {filter_text}")
    print(f"Zīmola/SKU produkti kopā:      {total_filtered}")
    print(f"Offset:                        {offset}")
    print(f"Pārbaudīti produkti:           {products_count}")
    print(f"PASS:                          {statistics['pass']}")
    print(f"WARNING:                       {statistics['warning']}")
    print(f"FAIL:                          {statistics['fail']}")
    print(
        "Bez WooCommerce attēliem:      "
        f"{statistics['without_wc_images']}"
    )
    print(
        "Bez Brandfolder attēliem:       "
        f"{statistics['without_bf_images']}"
    )
    print(
        "Ar atlikušiem PNG/JPG:          "
        f"{statistics['products_with_legacy']}"
    )
    print(
        "PNG/JPG attēli kopā:            "
        f"{statistics['legacy_images']}"
    )
    print(
        "Galerijas virs 10 attēliem:     "
        f"{statistics['products_over_limit']}"
    )
    print(
        "Produkti ar dublikātiem:        "
        f"{statistics['products_with_duplicates']}"
    )
    print(
        "Produkti ar nederīgiem ID:      "
        f"{statistics['products_with_invalid_ids']}"
    )
    print(
        "Trūkst Brandfolder attēlu WC:   "
        f"{statistics['products_missing_bf_images']}"
    )
    print(
        "Brandfolder pārbaudes kļūdas:   "
        f"{statistics['brandfolder_errors']}"
    )
    print(f"Izpildes laiks:                 {format_duration(elapsed)}")
    print(f"CSV atskaite:                   {report}")
    print(f"HTML atskaite:                  {html_report_path(report)}")
    print("=" * 72)

    if statistics["fail"]:
        print(
            "\nSTATUSS: ❌ Atrastas problēmas, kuras jāpārbauda."
        )
    elif statistics["warning"]:
        print(
            "\nSTATUSS: ⚠️ Kritisku kļūdu nav, bet ir brīdinājumi."
        )
    else:
        print("\nSTATUSS: ✅ Audits veiksmīgs.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Pārbauda WooCommerce un Brandfolder produktu attēlus. "
            "Skripts neko nemaina."
        )
    )

    brand_group = parser.add_mutually_exclusive_group()

    brand_group.add_argument(
        "--brand",
        default=None,
        help='Pārbaudīt tikai norādīto zīmolu, piemēram, "Weber".',
    )

    brand_group.add_argument(
        "--exclude-brand",
        default=None,
        help='Izslēgt norādīto zīmolu, piemēram, "Weber".',
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Izlaist pirmos N atlasītos produktus.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Pārbaudīt tikai N produktus pēc offset.",
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help="Izmantot Brandfolder kešatmiņu, ja tā ir pieejama.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Rādīt piezīmes arī produktiem ar PASS statusu.",
    )

    parser.add_argument(
        "--sku-file",
        default=None,
        help=(
            "Teksta fails ar SKU, pa vienam rindā vai atdalītiem ar komatu."
        ),
    )

    parser.add_argument(
        "--report",
        default=None,
        help="Norādīt CSV atskaites ceļu.",
    )

    parser.add_argument(
        "--max-images",
        type=int,
        default=MAX_IMAGES_PER_PRODUCT,
        help=(
            "Maksimālais pieļaujamais attēlu skaits produktam "
            f"(noklusējums: {MAX_IMAGES_PER_PRODUCT})."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    return parser


def validate_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if args.offset < 0:
        parser.error("--offset nedrīkst būt negatīvs.")

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit jābūt pozitīvam veselam skaitlim.")

    if args.max_images <= 0:
        parser.error("--max-images jābūt pozitīvam veselam skaitlim.")

    if args.brand is not None and not args.brand.strip():
        parser.error("--brand vērtība nedrīkst būt tukša.")

    if args.exclude_brand is not None and not args.exclude_brand.strip():
        parser.error("--exclude-brand vērtība nedrīkst būt tukša.")


def run_audit(args: argparse.Namespace) -> int:
    started_at = time.monotonic()

    print("=" * 72)
    print("GRILLANDMORE ATTĒLU AUDITS")
    print("=" * 72)
    print(f"Versija:           {VERSION}")
    if args.brand:
        filter_text = args.brand
    elif args.exclude_brand:
        filter_text = f"visi, izņemot {args.exclude_brand}"
    else:
        filter_text = "visi zīmoli"

    print(f"Zīmola filtrs:     {filter_text}")
    print(f"Offset:            {args.offset}")
    print(
        "Limits:            "
        + (str(args.limit) if args.limit is not None else "visi")
    )
    print(f"Attēlu limits:     {args.max_images}")
    print(
        "Brandfolder cache: "
        + ("JĀ" if args.cache else "NĒ")
    )
    print("Režīms:            TIKAI AUDITS — izmaiņu nav")
    print("=" * 72)

    sku_filter: set[str] | None = None

    if args.sku_file:
        sku_path = Path(args.sku_file).expanduser()

        if not sku_path.is_absolute():
            sku_path = PROJECT_ROOT / sku_path

        sku_filter = load_sku_file(sku_path)
        print(f"\nSKU failā atrasti: {len(sku_filter)}")

    try:
        all_products = load_products()
    except Exception as error:
        print(
            "\n❌ Neizdevās nolasīt WooCommerce produktus: "
            f"{error}"
        )
        return 1

    filtered = filter_products(
        all_products,
        brand=args.brand,
        exclude_brand=args.exclude_brand,
        sku_filter=sku_filter,
    )

    filtered.sort(
        key=lambda product: (
            str(product.get("name") or "").casefold(),
            int(product.get("id") or 0),
        )
    )

    selected = select_product_range(
        filtered,
        offset=args.offset,
        limit=args.limit,
    )

    print(f"\nWooCommerce produkti kopā: {len(all_products)}")
    print(f"Atlasīti pēc filtra:       {len(filtered)}")
    print(f"Produkti auditam:          {len(selected)}\n")

    if not selected:
        print("Nav produktu auditam.")
        return 0

    results: list[MediaAuditResult] = []

    with create_brandfolder_session() as session:
        for number, product in enumerate(selected, start=1):
            sku = normalize_sku(product.get("sku"))
            catalogue_position = args.offset + number
            brandfolder_images: list[dict[str, Any]] | None = None
            brandfolder_error = ""

            try:
                brandfolder_images = get_product_images(
                    sku,
                    use_cache=args.cache,
                    session=session,
                )

            except KeyboardInterrupt:
                print("\n\nAudits pārtraukts ar Ctrl+C.")
                break

            except (
                BrandfolderError,
                requests.RequestException,
                ValueError,
                TypeError,
                KeyError,
            ) as error:
                brandfolder_error = str(error)

            except Exception as error:
                brandfolder_error = (
                    f"{type(error).__name__}: {error}"
                )

            result = audit_product(
                product=product,
                catalogue_position=catalogue_position,
                brandfolder_images=brandfolder_images,
                brandfolder_error=brandfolder_error,
                max_images=args.max_images,
            )

            results.append(result)

            print_result(
                result,
                verbose=args.verbose,
            )

    output_path = report_path(
        brand=args.brand,
        exclude_brand=args.exclude_brand,
        custom_path=args.report,
    )

    save_csv(results, output_path)

    elapsed = time.monotonic() - started_at
    save_html(
        results,
        html_report_path(output_path),
        brand=args.brand,
        exclude_brand=args.exclude_brand,
        elapsed=elapsed,
    )

    print_summary(
        brand=args.brand,
        exclude_brand=args.exclude_brand,
        offset=args.offset,
        products_count=len(results),
        total_filtered=len(filtered),
        results=results,
        elapsed=elapsed,
        report=output_path,
    )

    statistics = summarize_results(results)

    return 1 if statistics["fail"] else 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    validate_arguments(parser, args)

    return run_audit(args)


if __name__ == "__main__":
    sys.exit(main())
