#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from src.brandfolder import (
    create_session as create_brandfolder_session,
)
from src.brandfolder import get_product_images
from src.media_audit import verify_product
from src.media.planner import (
    deduplicate_brandfolder_images,
    existing_woocommerce_keys,
    filename_from_url,
    image_key,
    image_priority,
    normalize_filename,
    normalize_sku,
    prepare_image_update,
    safe_position,
)
from src.image_processor import (
    describe_processed_image,
    process_remote_image,
)
from src.woocommerce import get_product_by_sku, load_products


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")

WP_USERNAME = os.getenv("WP_USERNAME", "").strip()
WP_APP_PASSWORD = "".join(
    os.getenv("WP_APP_PASSWORD", "").split()
)

RETRY_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

RETRY_DELAYS = (
    20,
    45,
    90,
)

PRODUCT_UPDATE_PAUSE = 3

# Vienam WooCommerce produktam kopā atļaujam maksimums 10 attēlus.
# Vajadzības gadījumā .env failā vari norādīt citu vērtību:
# MAX_IMAGES_PER_PRODUCT=10
MAX_IMAGES_PER_PRODUCT = max(
    1,
    int(os.getenv("MAX_IMAGES_PER_PRODUCT", "10")),
)


class ImageSyncError(RuntimeError):
    """WooCommerce vai WordPress attēlu sinhronizācijas kļūda."""


def find_product_by_sku(
    products: list[dict[str, Any]],
    sku: str,
) -> dict[str, Any] | None:
    wanted = normalize_sku(sku)

    for product in products:
        if normalize_sku(product.get("sku")) == wanted:
            return product

    return None


def validate_configuration() -> None:
    missing: list[str] = []

    if not WC_URL:
        missing.append("WC_URL")

    if not WC_CONSUMER_KEY:
        missing.append("WC_CONSUMER_KEY")

    if not WC_CONSUMER_SECRET:
        missing.append("WC_CONSUMER_SECRET")

    if not WP_USERNAME:
        missing.append("WP_USERNAME")

    if not WP_APP_PASSWORD:
        missing.append("WP_APP_PASSWORD")

    if missing:
        raise ImageSyncError(
            ".env failā trūkst: "
            + ", ".join(missing)
        )


def wordpress_auth() -> tuple[str, str]:
    if not WP_USERNAME or not WP_APP_PASSWORD:
        raise ImageSyncError(
            "WordPress Media API piekļuves dati nav norādīti."
        )

    return WP_USERNAME, WP_APP_PASSWORD


def wc_auth() -> tuple[str, str]:
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        raise ImageSyncError(
            "WooCommerce API piekļuves dati nav norādīti."
        )

    return WC_CONSUMER_KEY, WC_CONSUMER_SECRET


def request_with_retry(
    *,
    method: str,
    url: str,
    request_name: str,
    acceptable_statuses: set[int] | None = None,
    **kwargs: Any,
) -> requests.Response:
    last_error: Exception | None = None

    acceptable = acceptable_statuses or {
        200,
        201,
    }

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = requests.request(
                method,
                url,
                **kwargs,
            )

            if response.status_code in acceptable:
                return response

            if response.status_code not in RETRY_STATUS_CODES:
                print("\nServera atbilde:")
                print(response.text[:2000])
                response.raise_for_status()

            last_error = requests.HTTPError(
                (
                    f"{request_name}: "
                    f"HTTP {response.status_code}"
                ),
                response=response,
            )

        except requests.HTTPError as error:
            status_code = (
                error.response.status_code
                if error.response is not None
                else None
            )

            # 400, 401, 403, 404 u.c. pastāvīgas kļūdas
            # netiek atkārtotas.
            if status_code not in RETRY_STATUS_CODES:
                raise

            last_error = error

        except requests.RequestException as error:
            last_error = error

        if attempt >= len(RETRY_DELAYS):
            break

        delay = RETRY_DELAYS[attempt]

        print(
            f"    ⚠ {request_name} neizdevās. "
            f"Mēģinājums {attempt + 2} no "
            f"{len(RETRY_DELAYS) + 1} pēc "
            f"{delay} sekundēm..."
        )

        time.sleep(delay)

    raise ImageSyncError(
        f"{request_name} neizdevās pēc "
        f"{len(RETRY_DELAYS) + 1} mēģinājumiem. "
        f"Pēdējā kļūda: {last_error}"
    )


def upload_media_file(
    *,
    file_path: Path,
    filename: str,
    content_type: str,
    alt_text: str,
) -> dict[str, Any]:
    endpoint = (
        f"{WC_URL}/wp-json/wp/v2/media"
    )

    file_bytes = file_path.read_bytes()

    response = request_with_retry(
        method="POST",
        url=endpoint,
        request_name=f"Media augšupielāde {filename}",
        acceptable_statuses={201},
        auth=wordpress_auth(),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Content-Type": content_type,
            "Accept": "application/json",
        },
        data=file_bytes,
        timeout=(30, 300),
    )

    media = response.json()

    if not isinstance(media, dict):
        raise ImageSyncError(
            "WordPress Media API atgrieza "
            "negaidītu datu formātu."
        )

    media_id = media.get("id")

    if not media_id:
        raise ImageSyncError(
            f"WordPress neizveidoja Media ID failam {filename}."
        )

    metadata_endpoint = (
        f"{WC_URL}/wp-json/wp/v2/media/{media_id}"
    )

    metadata_response = request_with_retry(
        method="POST",
        url=metadata_endpoint,
        request_name=f"Media metadati {filename}",
        acceptable_statuses={200},
        auth=wordpress_auth(),
        json={
            "title": Path(filename).stem,
            "alt_text": alt_text,
            "caption": "",
            "description": "",
        },
        timeout=(30, 120),
    )

    metadata = metadata_response.json()

    if isinstance(metadata, dict):
        media.update(metadata)

    return media


def verify_media_exists(
    media_id: int,
) -> dict[str, Any]:
    endpoint = (
        f"{WC_URL}/wp-json/wp/v2/media/"
        f"{media_id}?context=edit"
    )

    response = requests.get(
        endpoint,
        auth=wordpress_auth(),
        timeout=(30, 120),
    )

    if response.status_code == 404:
        raise ImageSyncError(
            f"WordPress Media ID {media_id} "
            "pēc augšupielādes vairs neeksistē."
        )

    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict):
        raise ImageSyncError(
            f"Media ID {media_id} atgrieza "
            "negaidītu datu formātu."
        )

    if payload.get("media_type") != "image":
        raise ImageSyncError(
            f"Media ID {media_id} nav attēls."
        )

    return payload


def put_product_image_ids(
    *,
    product_id: int,
    image_ids: list[int],
) -> dict[str, Any]:
    endpoint = (
        f"{WC_URL}/wp-json/wc/v3/products/{product_id}"
    )

    response = request_with_retry(
        method="PUT",
        url=endpoint,
        request_name=f"WooCommerce produkts {product_id}",
        acceptable_statuses={200},
        auth=wc_auth(),
        json={
            "images": [
                {
                    "id": image_id,
                }
                for image_id in image_ids
            ]
        },
        timeout=(30, 300),
    )

    payload = response.json()

    if not isinstance(payload, dict):
        raise ImageSyncError(
            "WooCommerce atgrieza negaidītu datu formātu."
        )

    return payload


def update_product_images(
    product_id: int,
    payload_images: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Saglabā esošos Media ID un katru jauno attēlu:

      1. lejupielādē Python pusē;
      2. pārveido uz 800×800;
      3. augšupielādē WordPress Media Library;
      4. pārbauda Media ID;
      5. uzreiz piesaista WooCommerce produktam.

    Stingrais limits tiek pārbaudīts arī šajā līmenī,
    tāpēc fiziski nevar augšupielādēt vairāk par brīvajām
    vietām līdz MAX_IMAGES_PER_PRODUCT.
    """
    validate_configuration()

    existing_ids: list[int] = []
    remote_images: list[dict[str, Any]] = []

    for item in payload_images:
        image_id = item.get("id")

        if image_id:
            existing_ids.append(int(image_id))
            continue

        source_url = str(
            item.get("src") or ""
        ).strip()

        if source_url:
            remote_images.append(item)

    current_ids = list(dict.fromkeys(existing_ids))

    available_slots = max(
        0,
        MAX_IMAGES_PER_PRODUCT - len(current_ids),
    )

    skipped_count = max(
        0,
        len(remote_images) - available_slots,
    )

    remote_images = remote_images[:available_slots]

    print(
        f"  Esošie WooCommerce attēli: {len(current_ids)}"
    )
    print(
        f"  Brīvās vietas līdz limitam: {available_slots}"
    )

    if skipped_count:
        print(
            f"  ⚠ Limita dēļ netiks augšupielādēti "
            f"{skipped_count} attēli."
        )

    if not remote_images:
        print(
            "  Attēlu limits sasniegts vai nav jaunu attēlu."
        )

        # Ja ir esoši attēli, atstājam tos nemainītus.
        # Produktam ar vairāk nekā 10 esošiem attēliem
        # neko automātiski nedzēšam.
        return put_product_image_ids(
            product_id=product_id,
            image_ids=current_ids,
        )

    download_session = requests.Session()
    download_session.headers.update(
        {
            "User-Agent": (
                "GrillAndMore-Sync/0.4 "
                "(image processor)"
            ),
            "Accept": "image/*,*/*;q=0.8",
        }
    )

    last_product: dict[str, Any] | None = None

    try:
        for number, image in enumerate(
            remote_images,
            start=1,
        ):
            source_url = str(
                image.get("src") or ""
            ).strip()

            original_filename = str(
                image.get("name")
                or filename_from_url(source_url)
                or "product-image"
            ).strip()

            alt_text = str(
                image.get("alt")
                or Path(original_filename).stem
            ).strip()

            print(
                f"\n  [{number}/{len(remote_images)}] "
                f"{original_filename}"
            )

            processed = process_remote_image(
                url=source_url,
                filename=original_filename,
                session=download_session,
                use_cache=True,
            )

            print(
                "    "
                + describe_processed_image(processed)
            )

            media = upload_media_file(
                file_path=processed.path,
                filename=processed.filename,
                content_type=processed.content_type,
                alt_text=alt_text,
            )

            media_id = int(media["id"])
            verify_media_exists(media_id)

            if media_id not in current_ids:
                current_ids.append(media_id)

            # Papildu drošība: nekad nepārsniedzam limitu
            # ar jaunajiem attēliem.
            if len(existing_ids) < MAX_IMAGES_PER_PRODUCT:
                current_ids = current_ids[:MAX_IMAGES_PER_PRODUCT]

            print(
                f"    ✓ Media Library ID: {media_id}"
            )

            last_product = put_product_image_ids(
                product_id=product_id,
                image_ids=current_ids,
            )

            print(
                "    ✓ Pievienots WooCommerce produktam."
            )

            time.sleep(PRODUCT_UPDATE_PAUSE)

    finally:
        download_session.close()

    if last_product is None:
        last_product = put_product_image_ids(
            product_id=product_id,
            image_ids=current_ids,
        )

    return last_product


def display_filename(
    image: dict[str, Any],
) -> str:
    return str(
        image.get("filename")
        or image.get("name")
        or filename_from_url(image.get("src"))
        or ""
    )


def print_image_list(
    title: str,
    images: list[dict[str, Any]],
) -> None:
    print(f"\n{title}: {len(images)}")

    for number, image in enumerate(
        images,
        start=1,
    ):
        print(
            f"  {number}. {display_filename(image)}"
        )


def product_matches_brand(
    product: dict[str, Any],
    brand: str | None,
) -> bool:
    if not brand:
        return True

    wanted = brand.strip().casefold()

    if not wanted:
        return True

    searchable_values: list[str] = [
        str(product.get("name") or ""),
        str(product.get("brand") or ""),
        str(product.get("producer") or ""),
    ]

    for key in ("categories", "tags", "attributes"):
        values = product.get(key, [])

        if not isinstance(values, list):
            continue

        for item in values:
            if not isinstance(item, dict):
                continue

            searchable_values.extend(
                [
                    str(item.get("name") or ""),
                    str(item.get("option") or ""),
                    str(item.get("slug") or ""),
                ]
            )

            options = item.get("options", [])

            if isinstance(options, list):
                searchable_values.extend(
                    str(option)
                    for option in options
                )

    searchable_text = " ".join(searchable_values).casefold()
    return wanted in searchable_text


def print_audit_result(
    audit: dict[str, Any],
    *,
    verbose: bool,
) -> None:
    print(
        f"  Audits: {audit['status']} — "
        f"{audit['message']}"
    )
    print(
        f"  WC={audit['wc_count']}, "
        f"BF={audit['brandfolder_count']}, "
        f"trūkst={audit['missing_count']}, "
        f"papildu={audit['extra_count']}, "
        f"dublikāti={audit['duplicate_count']}"
    )

    if verbose and audit["missing_images"]:
        print(
            f"  Trūkstošie attēli: "
            f"{audit['missing_images']}"
        )

    if verbose and audit["extra_images"]:
        print(
            f"  Papildu WooCommerce attēli: "
            f"{audit['extra_images']}"
        )


def process_product(
    product: dict[str, Any],
    *,
    session: requests.Session,
    apply: bool,
    use_cache: bool,
    verbose: bool,
) -> dict[str, Any]:
    sku = normalize_sku(product.get("sku"))
    name = str(product.get("name") or "").strip()

    result = {
        "sku": sku,
        "name": name,
        "audit_status": "ERROR",
        "verify_status": "NOT_RUN",
        "action": "ERROR",
        "message": "",
    }

    if not sku:
        result["message"] = "Produktam nav SKU."
        print("  ❌ Produktam nav SKU.")
        return result

    try:
        audit = verify_product(
            product,
            use_cache=use_cache,
            session=session,
        )
    except Exception as exc:
        result["message"] = f"Audita kļūda: {exc}"
        print(f"  ❌ {result['message']}")
        return result

    audit_status = str(audit["status"])
    result["audit_status"] = audit_status
    result["message"] = str(audit["message"])

    print_audit_result(
        audit,
        verbose=verbose,
    )

    if audit_status == "OK":
        result["action"] = "SKIP_OK"
        print("  ✓ Izmaiņas nav nepieciešamas.")
        return result

    if audit_status == "REVIEW":
        result["action"] = "SKIP_REVIEW"
        print(
            "  ⚠ Nepieciešama manuāla pārbaude. "
            "Produkts netiks mainīts."
        )
        return result

    if audit_status == "ERROR":
        result["action"] = "ERROR"
        print("  ❌ Audita kļūda. Produkts netiks mainīts.")
        return result

    if audit_status != "SYNC":
        result["action"] = "ERROR"
        result["message"] = (
            f"Nezināms audita statuss: {audit_status}"
        )
        print(f"  ❌ {result['message']}")
        return result

    try:
        raw_brandfolder_images = get_product_images(
            sku,
            use_cache=use_cache,
            session=session,
        )

        plan = prepare_image_update(
            product=product,
            raw_brandfolder_images=raw_brandfolder_images,
        )
    except Exception as exc:
        result["action"] = "ERROR"
        result["message"] = (
            f"Neizdevās sagatavot sinhronizācijas plānu: {exc}"
        )
        print(f"  ❌ {result['message']}")
        return result

    missing_images = plan["missing_images"]
    skipped_images = plan["skipped_due_to_limit"]

    print(
        f"  Pievienojamie attēli: {len(missing_images)}"
    )
    print(
        f"  Attēli pēc sinhronizācijas: "
        f"{len(plan['existing_images']) + len(missing_images)}"
    )

    if verbose:
        print_image_list(
            "  Pievienojamie attēli",
            missing_images,
        )

    if not missing_images:
        result["action"] = "SKIP_REVIEW"
        result["message"] = (
            "Audits norādīja SYNC, bet plāns "
            "neatrada pievienojamus attēlus."
        )
        print(f"  ⚠ {result['message']}")
        return result

    if skipped_images:
        result["action"] = "SKIP_REVIEW"
        result["message"] = (
            "Visus attēlus nevar pievienot "
            "galerijas limita dēļ."
        )
        print(f"  ⚠ {result['message']}")
        return result

    if not apply:
        result["action"] = "DRY_RUN"
        print(
            "  DRY RUN — WooCommerce nekas netika mainīts."
        )
        return result

    product_id = product.get("id")

    if not product_id:
        result["action"] = "ERROR"
        result["message"] = "WooCommerce produktam nav ID."
        print(f"  ❌ {result['message']}")
        return result

    try:
        updated_product = update_product_images(
            product_id=int(product_id),
            payload_images=plan["payload_images"],
        )
    except Exception as exc:
        result["action"] = "ERROR"
        result["message"] = f"Sinhronizācijas kļūda: {exc}"
        print(f"  ❌ {result['message']}")
        return result

    updated_images = updated_product.get("images", [])
    updated_count = (
        len(updated_images)
        if isinstance(updated_images, list)
        else 0
    )

    print(
        f"  UPDATE: OK — WooCommerce tagad ir "
        f"{updated_count} attēli."
    )
    print("  VERIFY: pārbauda rezultātu...")

    try:
        verify_audit = verify_product(
            updated_product,
            use_cache=use_cache,
            session=session,
        )
    except Exception as exc:
        result["verify_status"] = "ERROR"
        result["action"] = "VERIFY_FAILED"
        result["message"] = (
            "Atjaunināšana izdevās, bet verifikācijas laikā "
            f"radās kļūda: {exc}"
        )
        print(f"  ❌ VERIFY: ERROR — {exc}")
        return result

    verify_status = str(verify_audit["status"])
    result["verify_status"] = verify_status

    if verify_status == "OK":
        result["action"] = "UPDATED"
        result["message"] = (
            "Sinhronizācija un verifikācija pabeigta; "
            f"WooCommerce tagad ir {updated_count} attēli."
        )
        print("  ✅ VERIFY: PASSED")
        return result

    result["action"] = "VERIFY_FAILED"
    result["message"] = (
        "Pēc atjaunināšanas audits joprojām rāda "
        f"{verify_status}: {verify_audit['message']}"
    )

    print(
        f"  ❌ VERIFY: FAILED — statuss {verify_status}"
    )
    print_audit_result(
        verify_audit,
        verbose=True,
    )
    return result


def sync_one_product(
    sku: str,
    *,
    apply: bool = False,
    use_cache: bool = False,
    verbose: bool = True,
) -> bool:
    normalized_sku = normalize_sku(sku)
    product = get_product_by_sku(normalized_sku)

    if not product:
        print(
            f"SKU {normalized_sku} WooCommerce netika atrasts."
        )
        return False

    print(
        f"\n{normalized_sku} | "
        f"{product.get('name', '')}"
    )

    with create_brandfolder_session() as session:
        result = process_product(
            product,
            session=session,
            apply=apply,
            use_cache=use_cache,
            verbose=verbose,
        )

    return (
        result["action"] == "UPDATED"
        and result["verify_status"] == "OK"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Auditē un droši sinhronizē Brandfolder "
            "attēlus uz WooCommerce."
        )
    )

    parser.add_argument(
        "sku",
        nargs="?",
        help="Viena WooCommerce produkta SKU.",
    )

    parser.add_argument(
        "--brand",
        help="Apstrādāt tikai norādītā zīmola produktus.",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Apstrādāt visus WooCommerce produktus.",
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Izlaist sākumā norādīto produktu skaitu.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Maksimālais apstrādājamo produktu skaits.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli augšupielādēt attēlus.",
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help="Izmantot Brandfolder kešatmiņu.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Parādīt detalizētus attēlu sarakstus.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.offset < 0:
        print("Kļūda: --offset nevar būt negatīvs.")
        return 2

    if args.limit is not None and args.limit < 1:
        print("Kļūda: --limit jābūt vismaz 1.")
        return 2

    selection_modes = sum(
        [
            bool(args.sku),
            bool(args.brand),
            bool(args.all),
        ]
    )

    if selection_modes == 0:
        print(
            "Kļūda: norādi SKU, --brand vai --all."
        )
        return 2

    if selection_modes > 1:
        print(
            "Kļūda: vienlaikus izmanto tikai vienu no "
            "SKU, --brand vai --all."
        )
        return 2

    if args.sku:
        product = get_product_by_sku(
            normalize_sku(args.sku),
        )

        if not product:
            print(
                f"SKU {normalize_sku(args.sku)} "
                "WooCommerce netika atrasts."
            )
            return 1

        selected_products = [product]

    else:
        products = load_products()

        filtered_products = [
            product
            for product in products
            if product_matches_brand(
                product,
                args.brand,
            )
        ]

        start = args.offset
        end = (
            None
            if args.limit is None
            else start + args.limit
        )

        selected_products = filtered_products[start:end]

        if args.brand:
            print(
                f'Pēc zīmola filtra "{args.brand}" '
                f"atrasti {len(filtered_products)} produkti."
            )

    print(
        f"Apstrādās {len(selected_products)} produktus."
    )

    if args.apply:
        print(
            "REĀLAIS REŽĪMS — SYNC produkti tiks mainīti."
        )
    else:
        print(
            "DRY RUN — WooCommerce nekas netiks mainīts."
        )

    results: list[dict[str, Any]] = []

    with create_brandfolder_session() as session:
        for index, product in enumerate(
            selected_products,
            start=1,
        ):
            sku = normalize_sku(product.get("sku"))
            name = str(product.get("name") or "").strip()

            print("\n" + "=" * 70)
            print(
                f"[{index}/{len(selected_products)}] "
                f"{sku or '(nav SKU)'} | {name}"
            )

            result = process_product(
                product,
                session=session,
                apply=args.apply,
                use_cache=args.cache,
                verbose=args.verbose,
            )
            results.append(result)

    action_counts: dict[str, int] = {}

    for result in results:
        action = str(result["action"])
        action_counts[action] = (
            action_counts.get(action, 0) + 1
        )

    print("\n" + "=" * 70)
    print("ATTĒLU SINHRONIZĀCIJAS KOPSAVILKUMS")
    print("=" * 70)
    print(
        f"Apstrādāti:       {len(results)}"
    )
    print(
        f"Atjaunināti:      "
        f"{action_counts.get('UPDATED', 0)}"
    )
    print(
        f"Verify passed:    "
        f"{sum(1 for item in results if item.get('verify_status') == 'OK')}"
    )
    print(
        f"Verify failed:    "
        f"{action_counts.get('VERIFY_FAILED', 0)}"
    )
    print(
        f"Dry run SYNC:     "
        f"{action_counts.get('DRY_RUN', 0)}"
    )
    print(
        f"Jau kārtībā:      "
        f"{action_counts.get('SKIP_OK', 0)}"
    )
    print(
        f"Manuāli jāpārbauda: "
        f"{action_counts.get('SKIP_REVIEW', 0)}"
    )
    print(
        f"Kļūdas:           "
        f"{action_counts.get('ERROR', 0)}"
    )

    failed_count = (
        action_counts.get("ERROR", 0)
        + action_counts.get("VERIFY_FAILED", 0)
    )
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
