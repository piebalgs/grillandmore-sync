from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


VAT_RATE = Decimal("0.21")
MONEY_PRECISION = Decimal("0.01")


def to_decimal(value: Any) -> Decimal:
    """
    Droši pārvērš vērtību par Decimal.

    Atbalsta:
    - Decimal
    - int
    - float
    - str ar punktu vai komatu
    """
    if isinstance(value, Decimal):
        return value

    text = str(value if value is not None else "").strip().replace(",", ".")

    if not text:
        raise ValueError("Cena nedrīkst būt tukša.")

    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Nederīga cenas vērtība: {value!r}") from exc


def round_money(value: Any) -> Decimal:
    """
    Noapaļo cenu līdz divām zīmēm aiz komata,
    izmantojot komerciālo ROUND_HALF_UP noapaļošanu.
    """
    return to_decimal(value).quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )


def calculate_gross_price(
    net_price: Any,
    vat_rate: Any = VAT_RATE,
) -> Decimal:
    """
    Aprēķina bruto cenu no neto cenas.

    Piemērs:
        27.05 × 1.21 = 32.73
    """
    net = to_decimal(net_price)
    vat = to_decimal(vat_rate)

    if net < 0:
        raise ValueError("Neto cena nedrīkst būt negatīva.")

    if vat < 0:
        raise ValueError("PVN likme nedrīkst būt negatīva.")

    gross = net * (Decimal("1") + vat)

    return round_money(gross)


def prices_are_equal(
    first_price: Any,
    second_price: Any,
) -> bool:
    """
    Salīdzina divas cenas pēc noapaļošanas līdz divām zīmēm.
    """
    return round_money(first_price) == round_money(second_price)


def format_price(value: Any) -> str:
    """
    Sagatavo cenu WooCommerce formātā.

    Vienmēr atgriež tekstu ar divām zīmēm aiz komata,
    piemēram: '32.73'.
    """
    return format(round_money(value), ".2f")


def prepare_price_update(gross_price: Any) -> dict[str, str]:
    """
    Sagatavo WooCommerce REST API payload cenas atjaunināšanai.
    """
    return {
        "regular_price": format_price(gross_price),
    }
