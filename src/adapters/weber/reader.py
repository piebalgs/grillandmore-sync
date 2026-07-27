"""Weber Digital Premium CSV/TSV failu nolasīšana."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class WeberReaderError(Exception):
    """Pamata kļūda Weber failu nolasīšanas laikā."""


class WeberFileNotFoundError(WeberReaderError):
    """Norādītais Weber fails nav atrasts."""


class WeberEmptyFileError(WeberReaderError):
    """Weber fails ir tukšs vai nesatur datu rindas."""


class WeberInvalidFileError(WeberReaderError):
    """Weber faila struktūra nav derīga."""


@dataclass(slots=True, frozen=True)
class WeberSourceFile:
    """Informācija par nolasīto Weber avota failu."""

    path: Path
    name: str
    category: str
    encoding: str
    delimiter: str
    columns: tuple[str, ...]
    row_count: int


@dataclass(slots=True)
class WeberReadResult:
    """Weber faila nolasīšanas rezultāts."""

    source: WeberSourceFile
    rows: list[dict[str, str]]


def clean_column_name(value: str) -> str:
    """
    Normalizē kolonnas nosaukumu.

    Tiek noņemta UTF BOM zīme, rindu pārnesumi un liekās atstarpes.
    """

    return " ".join(
        value.replace("\ufeff", "")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
        .split()
    )


def clean_cell_value(value: Any) -> str:
    """Pārvērš šūnas vērtību tīrā teksta virknē."""

    if value is None:
        return ""

    return str(value).replace("\ufeff", "").strip()


def detect_weber_category(file_path: str | Path) -> str:
    """Nosaka Weber produktu kategoriju pēc faila nosaukuma."""

    filename = Path(file_path).stem.lower()

    category_aliases = {
        "spare parts": "spare_parts",
        "spare_parts": "spare_parts",
        "accessories": "accessories",
        "bbq kitchen": "bbq_kitchen",
        "bbq_kitchen": "bbq_kitchen",
        "griddles": "griddles",
        "electric": "electric",
        "wood": "wood",
        "gas": "gas",
        "charcoal": "charcoal",
    }

    for fragment, category in category_aliases.items():
        if fragment in filename:
            return category

    return "unknown"


def row_has_content(row: dict[str, str]) -> bool:
    """Pārbauda, vai rindā ir vismaz viena netukša vērtība."""

    return any(value.strip() for value in row.values())


def normalise_row(
    row: dict[str | None, Any],
    columns: tuple[str, ...],
) -> dict[str, str]:
    """
    Normalizē vienu CSV/TSV rindu.

    Nezināmas vai nenosauktas kolonnas tiek ignorētas.
    """

    normalised: dict[str, str] = {}

    for raw_key, raw_value in row.items():
        if raw_key is None:
            continue

        key = clean_column_name(raw_key)

        if not key or key not in columns:
            continue

        normalised[key] = clean_cell_value(raw_value)

    for column in columns:
        normalised.setdefault(column, "")

    return normalised


def read_weber_file(
    file_path: str | Path,
    *,
    encoding: str = "utf-16",
    delimiter: str = "\t",
) -> WeberReadResult:
    """
    Nolasa vienu Weber Digital Premium failu.

    Weber faili parasti ir UTF-16 kodējumā un izmanto tabulāciju
    kā kolonnu atdalītāju, lai gan faila paplašinājums ir `.csv`.
    """

    path = Path(file_path).expanduser().resolve()

    if not path.exists():
        raise WeberFileNotFoundError(
            f"Weber fails nav atrasts: {path}"
        )

    if not path.is_file():
        raise WeberInvalidFileError(
            f"Norādītais ceļš nav fails: {path}"
        )

    if path.stat().st_size == 0:
        raise WeberEmptyFileError(
            f"Weber fails ir tukšs: {path.name}"
        )

    try:
        with path.open(
            mode="r",
            encoding=encoding,
            newline="",
        ) as file_handle:
            reader = csv.DictReader(
                file_handle,
                delimiter=delimiter,
            )

            if reader.fieldnames is None:
                raise WeberInvalidFileError(
                    f"Failā nav atrasta galvenes rinda: {path.name}"
                )

            columns = tuple(
                column
                for column in (
                    clean_column_name(name)
                    for name in reader.fieldnames
                    if name is not None
                )
                if column
            )

            if not columns:
                raise WeberInvalidFileError(
                    f"Failā nav derīgu kolonnu: {path.name}"
                )

            rows: list[dict[str, str]] = []

            for raw_row in reader:
                row = normalise_row(raw_row, columns)

                if row_has_content(row):
                    rows.append(row)

    except UnicodeError as error:
        raise WeberInvalidFileError(
            f"Neizdevās nolasīt failu ar kodējumu "
            f"{encoding!r}: {path.name}"
        ) from error
    except csv.Error as error:
        raise WeberInvalidFileError(
            f"Neizdevās apstrādāt Weber failu: {path.name}"
        ) from error

    if not rows:
        raise WeberEmptyFileError(
            f"Weber fails nesatur produktu rindas: {path.name}"
        )

    source = WeberSourceFile(
        path=path,
        name=path.name,
        category=detect_weber_category(path),
        encoding=encoding,
        delimiter=delimiter,
        columns=columns,
        row_count=len(rows),
    )

    return WeberReadResult(
        source=source,
        rows=rows,
    )


def iter_weber_rows(
    file_path: str | Path,
    *,
    encoding: str = "utf-16",
    delimiter: str = "\t",
) -> Iterator[dict[str, str]]:
    """
    Atgriež Weber faila rindas pa vienai.

    Šī funkcija vēlāk būs noderīga lielu katalogu apstrādei,
    lai visi dati nebūtu obligāti jāglabā vienlaikus atmiņā.
    """

    result = read_weber_file(
        file_path,
        encoding=encoding,
        delimiter=delimiter,
    )

    yield from result.rows


def read_weber_files(
    file_paths: list[str | Path],
) -> list[WeberReadResult]:
    """Nolasa vairākus Weber failus vienā izsaukumā."""

    return [
        read_weber_file(file_path)
        for file_path in file_paths
    ]