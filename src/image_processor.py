#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import io
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from PIL import Image, ImageOps, UnidentifiedImageError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_CACHE_DIR = PROJECT_ROOT / "cache" / "processed_images"

OUTPUT_SIZE = 800
JPEG_QUALITY = 88

RETRY_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

RETRY_DELAYS = (
    15,
    30,
    60,
)


class ImageProcessingError(RuntimeError):
    """Attēla lejupielādes vai apstrādes kļūda."""


@dataclass(frozen=True)
class ProcessedImage:
    path: Path
    filename: str
    content_type: str
    width: int
    height: int
    original_width: int
    original_height: int
    was_resized: bool
    from_cache: bool


def sanitize_filename(value: str) -> str:
    """
    Sagatavo drošu faila nosaukumu WordPress augšupielādei.
    """
    decoded = unquote(str(value or "")).strip()
    decoded = Path(decoded).name

    stem = Path(decoded).stem
    suffix = Path(decoded).suffix.lower()

    stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE)
    stem = re.sub(r"_+", "_", stem).strip("._-")

    if not stem:
        stem = "product-image"

    return f"{stem}{suffix}"


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    return Path(unquote(parsed.path)).name


def cache_key(
    url: str,
    filename: str,
) -> str:
    digest = hashlib.sha256(
        f"{url}|{filename}|{OUTPUT_SIZE}|{JPEG_QUALITY}".encode(
            "utf-8"
        )
    ).hexdigest()

    return digest[:24]


def has_transparency(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255

    if image.mode == "P":
        return "transparency" in image.info

    return False


def request_with_retry(
    session: requests.Session,
    url: str,
    *,
    timeout: tuple[int, int] = (30, 180),
) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = session.get(
                url,
                timeout=timeout,
                allow_redirects=True,
            )

            if response.status_code not in RETRY_STATUS_CODES:
                response.raise_for_status()
                return response

            last_error = requests.HTTPError(
                f"HTTP {response.status_code}",
                response=response,
            )

        except requests.RequestException as error:
            last_error = error

        if attempt >= len(RETRY_DELAYS):
            break

        delay = RETRY_DELAYS[attempt]

        print(
            f"    ⚠ Attēla lejupielāde neizdevās. "
            f"Atkārto pēc {delay} sekundēm..."
        )

        time.sleep(delay)

    raise ImageProcessingError(
        f"Neizdevās lejupielādēt attēlu: {url}. "
        f"Pēdējā kļūda: {last_error}"
    )


def open_source_image(content: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
        return image

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as error:
        raise ImageProcessingError(
            f"Fails nav derīgs attēls: {error}"
        ) from error


def prepare_square_image(
    source: Image.Image,
) -> tuple[Image.Image, bool, bool]:
    """
    Izveido precīzi 800 × 800 px attēlu.

    Attēlam saglabā proporcijas un trūkstošo laukumu aizpilda:
      - caurspīdīgu, ja avotam ir transparency;
      - baltu, ja attēls nav caurspīdīgs.
    """
    source = ImageOps.exif_transpose(source)

    transparent = has_transparency(source)

    if transparent:
        working = source.convert("RGBA")
        background: tuple[int, int, int, int] | tuple[int, int, int] = (
            255,
            255,
            255,
            0,
        )
        output_mode = "RGBA"
    else:
        working = source.convert("RGB")
        background = (255, 255, 255)
        output_mode = "RGB"

    original_size = working.size

    resized = ImageOps.contain(
        working,
        (OUTPUT_SIZE, OUTPUT_SIZE),
        method=Image.Resampling.LANCZOS,
    )

    canvas = Image.new(
        output_mode,
        (OUTPUT_SIZE, OUTPUT_SIZE),
        background,
    )

    x = (OUTPUT_SIZE - resized.width) // 2
    y = (OUTPUT_SIZE - resized.height) // 2

    if transparent:
        canvas.paste(
            resized,
            (x, y),
            resized,
        )
    else:
        canvas.paste(
            resized,
            (x, y),
        )

    was_resized = (
        original_size != resized.size
        or original_size != (OUTPUT_SIZE, OUTPUT_SIZE)
    )

    return canvas, transparent, was_resized


def choose_output_filename(
    original_filename: str,
    transparent: bool,
) -> tuple[str, str]:
    safe_filename = sanitize_filename(original_filename)
    stem = Path(safe_filename).stem

    if transparent:
        return f"{stem}.png", "image/png"

    return f"{stem}.jpg", "image/jpeg"


def save_processed_image(
    image: Image.Image,
    *,
    output_path: Path,
    content_type: str,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if content_type == "image/png":
        image.save(
            output_path,
            format="PNG",
            optimize=True,
            compress_level=7,
        )
        return

    rgb_image = image.convert("RGB")

    rgb_image.save(
        output_path,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
        subsampling="4:2:0",
    )


def process_remote_image(
    *,
    url: str,
    filename: str | None = None,
    session: requests.Session | None = None,
    use_cache: bool = True,
) -> ProcessedImage:
    if not url:
        raise ImageProcessingError(
            "Attēla URL ir tukšs."
        )

    source_filename = (
        filename
        or filename_from_url(url)
        or "product-image"
    )

    own_session = session is None

    if session is None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "GrillAndMore-Sync/0.3 "
                    "(WordPress product image importer)"
                ),
                "Accept": "image/*,*/*;q=0.8",
            }
        )

    try:
        response = request_with_retry(
            session,
            url,
        )

        source_image = open_source_image(
            response.content
        )

        original_width, original_height = source_image.size

        processed, transparent, was_resized = (
            prepare_square_image(source_image)
        )

        output_filename, content_type = (
            choose_output_filename(
                source_filename,
                transparent,
            )
        )

        key = cache_key(
            url,
            output_filename,
        )

        output_path = (
            IMAGE_CACHE_DIR
            / f"{key}_{output_filename}"
        )

        if use_cache and output_path.exists():
            return ProcessedImage(
                path=output_path,
                filename=output_filename,
                content_type=content_type,
                width=OUTPUT_SIZE,
                height=OUTPUT_SIZE,
                original_width=original_width,
                original_height=original_height,
                was_resized=was_resized,
                from_cache=True,
            )

        save_processed_image(
            processed,
            output_path=output_path,
            content_type=content_type,
        )

        return ProcessedImage(
            path=output_path,
            filename=output_filename,
            content_type=content_type,
            width=OUTPUT_SIZE,
            height=OUTPUT_SIZE,
            original_width=original_width,
            original_height=original_height,
            was_resized=was_resized,
            from_cache=False,
        )

    finally:
        if own_session:
            session.close()


def describe_processed_image(
    processed: ProcessedImage,
) -> str:
    source = (
        "kešatmiņa"
        if processed.from_cache
        else "lejupielādēts"
    )

    return (
        f"{processed.original_width}×"
        f"{processed.original_height} px "
        f"→ {processed.width}×{processed.height} px; "
        f"{processed.content_type}; {source}"
    )


if __name__ == "__main__":
    raise SystemExit(
        "Šis ir bibliotēkas modulis. "
        "Izmanto to caur src.image_sync."
    )