#!/usr/bin/env python3

from __future__ import annotations

from typing import Any

import requests

from src.brandfolder import get_product_images
from src.media_audit import verify_product
from src.media.planner import (
    filename_from_url,
    normalize_sku,
    prepare_image_update,
)
from src.media.updater import update_product_images


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
