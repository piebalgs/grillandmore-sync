#!/usr/bin/env python3
"""Centralizēta GrillAndMore projekta konfigurācija."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


DEFAULT_RETRY_STATUS_CODES: Final[frozenset[int]] = frozenset(
    {
        429,
        500,
        502,
        503,
        504,
    }
)

DEFAULT_RETRY_DELAYS: Final[tuple[int, ...]] = (
    20,
    45,
    90,
)

DEFAULT_PRODUCT_UPDATE_PAUSE: Final[int] = 3
DEFAULT_MAX_IMAGES_PER_PRODUCT: Final[int] = 10


class ConfigurationError(RuntimeError):
    """Projekta konfigurācijas kļūda."""


def project_root() -> Path:
    """
    Atgriež projekta saknes mapi.

    Paredzētā faila atrašanās vieta:
        project/src/core/config.py
    """
    return Path(__file__).resolve().parents[2]


def env_file_path() -> Path:
    """Atgriež projekta .env faila ceļu."""
    return project_root() / ".env"


def load_environment(*, override: bool = False) -> Path:
    """
    Ielādē projekta .env failu.

    Atgriež izmantotā .env faila ceļu arī tad,
    ja pats fails neeksistē.
    """
    path = env_file_path()
    load_dotenv(path, override=override)
    return path


def _get_text(
    name: str,
    *,
    default: str = "",
    strip: bool = True,
) -> str:
    """Nolasa teksta vērtību no vides mainīgajiem."""
    value = os.getenv(name, default)

    if value is None:
        value = default

    return value.strip() if strip else value


def _get_compact_text(
    name: str,
    *,
    default: str = "",
) -> str:
    """
    Nolasa teksta vērtību un noņem visas atstarpes.

    Tas ir īpaši noderīgi WordPress Application Password,
    kuru WordPress mēdz attēlot grupās ar atstarpēm.
    """
    return "".join(
        _get_text(
            name,
            default=default,
        ).split()
    )


def _get_int(
    name: str,
    *,
    default: int,
    minimum: int | None = None,
) -> int:
    """Nolasa veselu skaitli un pārbauda minimālo vērtību."""
    raw_value = _get_text(
        name,
        default=str(default),
    )

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} jābūt veselam skaitlim, "
            f"saņemts: {raw_value!r}"
        ) from exc

    if minimum is not None and value < minimum:
        raise ConfigurationError(
            f"{name} jābūt vismaz {minimum}, "
            f"saņemts: {value}"
        )

    return value


def _get_int_tuple(
    name: str,
    *,
    default: tuple[int, ...],
    minimum: int | None = None,
) -> tuple[int, ...]:
    """
    Nolasa ar komatiem atdalītu veselu skaitļu sarakstu.

    Piemērs .env failā:
        RETRY_DELAYS=20,45,90
    """
    raw_value = _get_text(name)

    if not raw_value:
        return default

    parts = [
        part.strip()
        for part in raw_value.split(",")
        if part.strip()
    ]

    if not parts:
        return default

    values: list[int] = []

    for part in parts:
        try:
            value = int(part)
        except ValueError as exc:
            raise ConfigurationError(
                f"{name} satur nederīgu skaitli: {part!r}"
            ) from exc

        if minimum is not None and value < minimum:
            raise ConfigurationError(
                f"{name} vērtībām jābūt vismaz {minimum}, "
                f"saņemts: {value}"
            )

        values.append(value)

    return tuple(values)


def _get_int_set(
    name: str,
    *,
    default: frozenset[int],
    minimum: int | None = None,
) -> frozenset[int]:
    """Nolasa ar komatiem atdalītu unikālu skaitļu kopu."""
    values = _get_int_tuple(
        name,
        default=tuple(sorted(default)),
        minimum=minimum,
    )

    return frozenset(values)


@dataclass(frozen=True, slots=True)
class Settings:
    """Nemaināms GrillAndMore konfigurācijas objekts."""

    project_root: Path
    env_file: Path

    wc_url: str
    wc_consumer_key: str
    wc_consumer_secret: str

    wp_username: str
    wp_app_password: str

    retry_status_codes: frozenset[int]
    retry_delays: tuple[int, ...]
    product_update_pause: int
    max_images_per_product: int

    @property
    def wordpress_media_endpoint(self) -> str:
        """WordPress Media API bāzes adrese."""
        return f"{self.wc_url}/wp-json/wp/v2/media"

    @property
    def woocommerce_products_endpoint(self) -> str:
        """WooCommerce produktu API bāzes adrese."""
        return f"{self.wc_url}/wp-json/wc/v3/products"

    def missing_woocommerce_values(self) -> tuple[str, ...]:
        """Atgriež trūkstošos WooCommerce laukus."""
        missing: list[str] = []

        if not self.wc_url:
            missing.append("WC_URL")

        if not self.wc_consumer_key:
            missing.append("WC_CONSUMER_KEY")

        if not self.wc_consumer_secret:
            missing.append("WC_CONSUMER_SECRET")

        return tuple(missing)

    def missing_wordpress_values(self) -> tuple[str, ...]:
        """Atgriež trūkstošos WordPress laukus."""
        missing: list[str] = []

        if not self.wp_username:
            missing.append("WP_USERNAME")

        if not self.wp_app_password:
            missing.append("WP_APP_PASSWORD")

        return tuple(missing)

    def missing_image_sync_values(self) -> tuple[str, ...]:
        """Atgriež visus Image Sync darbam nepieciešamos laukus."""
        return (
            self.missing_woocommerce_values()
            + self.missing_wordpress_values()
        )

    def validate_woocommerce(self) -> None:
        """Pārbauda WooCommerce API konfigurāciju."""
        missing = self.missing_woocommerce_values()

        if missing:
            raise ConfigurationError(
                ".env failā trūkst: "
                + ", ".join(missing)
            )

    def validate_wordpress(self) -> None:
        """Pārbauda WordPress Media API konfigurāciju."""
        missing = self.missing_wordpress_values()

        if missing:
            raise ConfigurationError(
                ".env failā trūkst: "
                + ", ".join(missing)
            )

    def validate_image_sync(self) -> None:
        """Pārbauda visu Image Sync konfigurāciju."""
        missing = self.missing_image_sync_values()

        if missing:
            raise ConfigurationError(
                ".env failā trūkst: "
                + ", ".join(missing)
            )


def create_settings(
    *,
    reload_env: bool = False,
) -> Settings:
    """
    Izveido jaunu konfigurācijas objektu.

    reload_env=True ļauj testos atkārtoti ielādēt
    .env faila vērtības.
    """
    env_path = load_environment(
        override=reload_env,
    )
    root = project_root()

    return Settings(
        project_root=root,
        env_file=env_path,
        wc_url=_get_text("WC_URL").rstrip("/"),
        wc_consumer_key=_get_text(
            "WC_CONSUMER_KEY"
        ),
        wc_consumer_secret=_get_text(
            "WC_CONSUMER_SECRET"
        ),
        wp_username=_get_text(
            "WP_USERNAME"
        ),
        wp_app_password=_get_compact_text(
            "WP_APP_PASSWORD"
        ),
        retry_status_codes=_get_int_set(
            "RETRY_STATUS_CODES",
            default=DEFAULT_RETRY_STATUS_CODES,
            minimum=100,
        ),
        retry_delays=_get_int_tuple(
            "RETRY_DELAYS",
            default=DEFAULT_RETRY_DELAYS,
            minimum=0,
        ),
        product_update_pause=_get_int(
            "PRODUCT_UPDATE_PAUSE",
            default=DEFAULT_PRODUCT_UPDATE_PAUSE,
            minimum=0,
        ),
        max_images_per_product=_get_int(
            "MAX_IMAGES_PER_PRODUCT",
            default=DEFAULT_MAX_IMAGES_PER_PRODUCT,
            minimum=1,
        ),
    )


settings = create_settings()
