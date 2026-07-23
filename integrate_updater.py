#!/usr/bin/env python3

from __future__ import annotations

import ast
import shutil
from pathlib import Path


IMAGE_SYNC_PATH = Path("src/image_sync.py")
BACKUP_PATH = Path("src/image_sync_before_updater.py")

UPDATER_FUNCTIONS = {
    "ImageSyncError",
    "validate_configuration",
    "wordpress_auth",
    "wc_auth",
    "request_with_retry",
    "upload_media_file",
    "verify_media_exists",
    "put_product_image_ids",
    "update_product_images",
}

PLANNER_IMPORT = """from src.media.planner import (
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
"""

UPDATER_IMPORT = """from src.media.updater import (
    ImageSyncError,
    update_product_images,
)
"""


def remove_ast_blocks(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    ranges: list[tuple[int, int]] = []

    for node in tree.body:
        node_name = getattr(node, "name", None)

        if node_name in UPDATER_FUNCTIONS:
            if node.end_lineno is None:
                raise RuntimeError(
                    f"Nevar noteikt bloka beigas: {node_name}"
                )

            ranges.append(
                (
                    node.lineno,
                    node.end_lineno,
                )
            )

    found_names = {
        getattr(node, "name", None)
        for node in tree.body
        if getattr(node, "name", None) in UPDATER_FUNCTIONS
    }

    missing_names = UPDATER_FUNCTIONS - found_names

    if missing_names:
        raise RuntimeError(
            "Failā netika atrasti updater bloki: "
            + ", ".join(sorted(missing_names))
        )

    for start_line, end_line in sorted(
        ranges,
        reverse=True,
    ):
        del lines[start_line - 1:end_line]

    return "".join(lines)


def remove_old_imports(source: str) -> str:
    replacements = {
        "import os\n": "",
        "import time\n": "",
        "from pathlib import Path\n": "",
        "from dotenv import load_dotenv\n": "",
        (
            "from src.image_processor import (\n"
            "    describe_processed_image,\n"
            "    process_remote_image,\n"
            ")\n"
        ): "",
    }

    for old_text, new_text in replacements.items():
        source = source.replace(
            old_text,
            new_text,
            1,
        )

    return source


def remove_old_configuration(source: str) -> str:
    start_marker = "PROJECT_ROOT = "
    end_marker = "def find_product_by_sku("

    start_position = source.find(start_marker)
    end_position = source.find(end_marker)

    if start_position == -1:
        raise RuntimeError(
            "Netika atrasts PROJECT_ROOT konfigurācijas bloks."
        )

    if end_position == -1:
        raise RuntimeError(
            "Netika atrasta find_product_by_sku() funkcija."
        )

    if start_position >= end_position:
        raise RuntimeError(
            "Konfigurācijas bloka robežas nav pareizas."
        )

    return (
        source[:start_position]
        + source[end_position:]
    )


def add_updater_import(source: str) -> str:
    if UPDATER_IMPORT in source:
        return source

    if PLANNER_IMPORT not in source:
        raise RuntimeError(
            "Netika atrasts src.media.planner importa bloks."
        )

    return source.replace(
        PLANNER_IMPORT,
        PLANNER_IMPORT + UPDATER_IMPORT,
        1,
    )


def normalize_blank_lines(source: str) -> str:
    while "\n\n\n\n" in source:
        source = source.replace(
            "\n\n\n\n",
            "\n\n\n",
        )

    return source


def main() -> None:
    if not IMAGE_SYNC_PATH.exists():
        raise SystemExit(
            f"Fails nav atrasts: {IMAGE_SYNC_PATH}"
        )

    if not Path("src/media/updater.py").exists():
        raise SystemExit(
            "Fails nav atrasts: src/media/updater.py"
        )

    original_source = IMAGE_SYNC_PATH.read_text(
        encoding="utf-8"
    )

    # Pirms izmaiņām pārbaudām, ka esošais fails ir sintaktiski derīgs.
    ast.parse(original_source)

    shutil.copy2(
        IMAGE_SYNC_PATH,
        BACKUP_PATH,
    )

    updated_source = remove_ast_blocks(
        original_source
    )
    updated_source = remove_old_imports(
        updated_source
    )
    updated_source = remove_old_configuration(
        updated_source
    )
    updated_source = add_updater_import(
        updated_source
    )
    updated_source = normalize_blank_lines(
        updated_source
    )

    # Pārbaudām jauno failu pirms rakstīšanas.
    ast.parse(updated_source)

    IMAGE_SYNC_PATH.write_text(
        updated_source,
        encoding="utf-8",
    )

    print("Integrācija pabeigta.")
    print(f"Atjaunināts: {IMAGE_SYNC_PATH}")
    print(f"Rezerves kopija: {BACKUP_PATH}")
    print(
        "Jaunais image_sync.py rindu skaits:",
        len(updated_source.splitlines()),
    )


if __name__ == "__main__":
    main()

