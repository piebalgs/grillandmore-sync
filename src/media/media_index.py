#!/usr/bin/env python3

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WP_USERNAME = os.getenv("WP_USERNAME", "").strip()
WP_APP_PASSWORD = "".join(
    os.getenv("WP_APP_PASSWORD", "").split()
)

MEDIA_PER_PAGE = 100
REQUEST_TIMEOUT = (30, 120)
RETRY_DELAYS = (10, 30, 60)
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class MediaIndexError(RuntimeError):
    """WordPress Media Library indeksa izveides kļūda."""


def validate_configuration() -> None:
    """Pārbauda Media Library API nepieciešamos .env iestatījumus."""
    missing: list[str] = []

    if not WC_URL:
        missing.append("WC_URL")

    if not WP_USERNAME:
        missing.append("WP_USERNAME")

    if not WP_APP_PASSWORD:
        missing.append("WP_APP_PASSWORD")

    if missing:
        raise MediaIndexError(
            ".env failā trūkst: " + ", ".join(missing)
        )


def wordpress_auth() -> tuple[str, str]:
    """Atgriež WordPress REST API autentifikācijas datus."""
    validate_configuration()
    return WP_USERNAME, WP_APP_PASSWORD


def normalize_filename(value: Any) -> str:
    """
    Izveido stabilu Media Library indeksa atslēgu.

    Atslēga ir faila nosaukuma pamats bez mapes, URL parametriem
    un paplašinājuma, rakstīts ar mazajiem burtiem.

    Tādēļ Brandfolder fails:
        81010004B.png

    un WordPress optimizētais fails:
        81010004B.webp

    iegūst vienādu atslēgu:
        81010004b
    """
    raw_value = unquote(str(value or "").strip())

    if not raw_value:
        return ""

    parsed = urlparse(raw_value)
    path_value = parsed.path if parsed.scheme else raw_value
    filename = Path(path_value).name.strip()

    if not filename:
        return ""

    return Path(filename).stem.strip().casefold()


def media_filename(media: dict[str, Any]) -> str:
    """
    Atrod WordPress media ieraksta faktisko faila nosaukumu.

    Priekšroka tiek dota media_details.file laukam, jo tas norāda
    WordPress saglabāto oriģinālo failu, nevis sīktēlu.
    """
    media_details = media.get("media_details")

    if isinstance(media_details, dict):
        stored_file = str(media_details.get("file") or "").strip()

        if stored_file:
            return Path(stored_file).name

    source_url = str(media.get("source_url") or "").strip()

    if source_url:
        return Path(urlparse(source_url).path).name

    slug = str(media.get("slug") or "").strip()

    if slug:
        return slug

    return ""


def request_media_page(
    *,
    page: int,
    session: requests.Session,
) -> requests.Response:
    """Nolasa vienu WordPress Media Library lapu ar retry loģiku."""
    endpoint = f"{WC_URL}/wp-json/wp/v2/media"
    last_error: Exception | None = None

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = session.get(
                endpoint,
                auth=wordpress_auth(),
                params={
                    "page": page,
                    "per_page": MEDIA_PER_PAGE,
                    "media_type": "image",
                    "context": "edit",
                    "_fields": (
                        "id,slug,source_url,media_type,"
                        "media_details"
                    ),
                },
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 400:
                # WordPress atgriež 400, ja pieprasīta lapa aiz
                # pēdējās pieejamās lapas.
                total_pages = int(
                    response.headers.get("X-WP-TotalPages", "0") or 0
                )

                if total_pages and page > total_pages:
                    return response

            if response.status_code == 200:
                return response

            if response.status_code not in RETRY_STATUS_CODES:
                raise MediaIndexError(
                    "Media Library API atgrieza "
                    f"HTTP {response.status_code}: "
                    f"{response.text[:1000]}"
                )

            last_error = requests.HTTPError(
                f"Media Library lapa {page}: "
                f"HTTP {response.status_code}",
                response=response,
            )

        except requests.RequestException as error:
            last_error = error

        if attempt >= len(RETRY_DELAYS):
            break

        delay = RETRY_DELAYS[attempt]

        print(
            f"  ⚠ Media Library {page}. lapu neizdevās nolasīt. "
            f"Atkārtots mēģinājums pēc {delay} sekundēm..."
        )
        time.sleep(delay)

    raise MediaIndexError(
        f"Media Library {page}. lapu neizdevās nolasīt. "
        f"Pēdējā kļūda: {last_error}"
    )


def fetch_media_page(
    *,
    page: int,
    session: requests.Session | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    Nolasa vienu Media Library lapu.

    Atgriež:
        (media ieraksti, kopējais lapu skaits)
    """
    owns_session = session is None
    active_session = session or requests.Session()

    if owns_session:
        active_session.headers.update(
            {
                "User-Agent": (
                    "GrillAndMore-Sync/1.0 "
                    "(media library index)"
                ),
                "Accept": "application/json",
            }
        )

    try:
        response = request_media_page(
            page=page,
            session=active_session,
        )

        if response.status_code == 400:
            return [], 0

        payload = response.json()

        if not isinstance(payload, list):
            raise MediaIndexError(
                "Media Library API atgrieza neparedzētu datu formātu."
            )

        media_items = [
            item
            for item in payload
            if isinstance(item, dict)
            and item.get("media_type") == "image"
        ]

        total_pages = int(
            response.headers.get("X-WP-TotalPages", "1") or 1
        )

        return media_items, total_pages

    finally:
        if owns_session:
            active_session.close()


def build_media_index(
    *,
    verbose: bool = True,
) -> dict[str, int]:
    """
    Nolasa visu WordPress Media Library un izveido ātru indeksu.

    Indeksa formāts:
        {
            "81010004a": 22723,
            "81010004b": 22722,
        }

    Atslēga ir normalizēts faila pamats bez paplašinājuma.
    Ja Media Library ir vairāki faili ar vienādu atslēgu,
    tiek saglabāts ieraksts ar lielāko Media ID, jo tas parasti
    ir jaunākais ieraksts.
    """
    validate_configuration()

    media_index: dict[str, int] = {}
    duplicate_keys: dict[str, list[int]] = {}
    page = 1
    total_pages: int | None = None
    indexed_items = 0
    skipped_items = 0

    if verbose:
        print("Veido WordPress Media Library indeksu...")

    with requests.Session() as session:
        session.headers.update(
            {
                "User-Agent": (
                    "GrillAndMore-Sync/1.0 "
                    "(media library index)"
                ),
                "Accept": "application/json",
            }
        )

        while total_pages is None or page <= total_pages:
            items, reported_total_pages = fetch_media_page(
                page=page,
                session=session,
            )

            if total_pages is None:
                total_pages = reported_total_pages

            if not items:
                break

            page_indexed = 0

            for media in items:
                media_id = media.get("id")
                filename = media_filename(media)
                key = normalize_filename(filename)

                if not media_id or not key:
                    skipped_items += 1
                    continue

                normalized_id = int(media_id)
                previous_id = media_index.get(key)

                if previous_id is not None and previous_id != normalized_id:
                    duplicate_keys.setdefault(
                        key,
                        [previous_id],
                    ).append(normalized_id)

                    media_index[key] = max(
                        previous_id,
                        normalized_id,
                    )
                else:
                    media_index[key] = normalized_id

                indexed_items += 1
                page_indexed += 1

            if verbose:
                total_label = (
                    str(total_pages)
                    if total_pages is not None
                    else "?"
                )

                print(
                    f"  Lapa {page}/{total_label}: "
                    f"{page_indexed} attēli; "
                    f"indeksā {len(media_index)} unikālas atslēgas."
                )

            page += 1

    if verbose:
        print("Media Library indeksēšana pabeigta.")
        print(f"  Nolasīti attēlu ieraksti: {indexed_items}")
        print(f"  Unikālas atslēgas:        {len(media_index)}")
        print(f"  Izlaisti ieraksti:        {skipped_items}")
        print(f"  Dublētas atslēgas:        {len(duplicate_keys)}")

    return media_index


def find_media_id(
    media_index: dict[str, int],
    filename: Any,
) -> int | None:
    """Atrod Media ID pēc Brandfolder vai WordPress faila nosaukuma."""
    key = normalize_filename(filename)

    if not key:
        return None

    return media_index.get(key)


if __name__ == "__main__":
    index = build_media_index(verbose=True)

    print()
    print("Piemēra pārbaude:")
    print(
        "  81010004B.png -> "
        f"{find_media_id(index, '81010004B.png')}"
    )
