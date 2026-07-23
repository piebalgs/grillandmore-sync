#!/usr/bin/env python3
"""Koplietojama GrillAndMore žurnālfailu konfigurācija."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO


DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def project_root() -> Path:
    """
    Atgriež GrillAndMore projekta saknes mapi.

    Paredzētā faila atrašanās vieta:
        project/src/core/logger.py
    """
    return Path(__file__).resolve().parents[2]


def build_log_path(
    *,
    logger_name: str,
    logs_dir: Path,
    timestamp: datetime | None = None,
) -> Path:
    """Izveido unikālu žurnālfaila ceļu konkrētai palaišanai."""
    current_time = timestamp or datetime.now()

    safe_name = "".join(
        character
        if character.isalnum() or character in {"-", "_"}
        else "_"
        for character in logger_name.strip()
    ).strip("_")

    if not safe_name:
        safe_name = "grillandmore"

    filename = (
        f"{safe_name}_"
        f"{current_time.strftime('%Y-%m-%d_%H%M%S')}.log"
    )

    return logs_dir / filename


def configure_logging(
    logger_name: str,
    *,
    verbose: bool = False,
    logs_dir: Path | str | None = None,
    console_stream: TextIO | None = None,
    create_file: bool = True,
) -> tuple[logging.Logger, Path | None]:
    """
    Konfigurē loggeri terminālim un žurnālfailam.

    Parametri:
        logger_name:
            Logera nosaukums, piemēram, "image_sync".

        verbose:
            Ja True, terminālī rāda arī DEBUG līmeņa ierakstus.

        logs_dir:
            Žurnālfailu mape. Pēc noklusējuma project/logs.

        console_stream:
            Termināļa izvades plūsma. Pēc noklusējuma sys.stdout.

        create_file:
            Ja False, žurnālfails netiek izveidots.

    Atgriež:
        tuple:
            konfigurētais loggeris;
            izveidotā žurnālfaila ceļš vai None.

    Funkcija ir idempotenta: atkārtots izsaukums tam pašam
    loggerim neveido dublētus handlerus.
    """
    logger = logging.getLogger(logger_name)

    logger.setLevel(
        logging.DEBUG if verbose else DEFAULT_LOG_LEVEL
    )
    logger.propagate = False

    if getattr(logger, "_grillandmore_configured", False):
        log_path = getattr(
            logger,
            "_grillandmore_log_path",
            None,
        )
        return logger, log_path

    formatter = logging.Formatter(
        fmt=DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
    )

    stream_handler = logging.StreamHandler(
        console_stream or sys.stdout
    )
    stream_handler.setLevel(
        logging.DEBUG if verbose else DEFAULT_LOG_LEVEL
    )
    stream_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)

    log_path: Path | None = None

    if create_file:
        resolved_logs_dir = (
            Path(logs_dir).expanduser().resolve()
            if logs_dir is not None
            else project_root() / "logs"
        )

        resolved_logs_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        log_path = build_log_path(
            logger_name=logger_name,
            logs_dir=resolved_logs_dir,
        )

        file_handler = logging.FileHandler(
            log_path,
            encoding="utf-8",
        )

        # Failā vienmēr saglabājam arī DEBUG ierakstus.
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    setattr(
        logger,
        "_grillandmore_configured",
        True,
    )
    setattr(
        logger,
        "_grillandmore_log_path",
        log_path,
    )

    return logger, log_path


def get_logger(
    logger_name: str,
    *,
    verbose: bool = False,
    logs_dir: Path | str | None = None,
    create_file: bool = True,
) -> logging.Logger:
    """Atgriež konfigurētu GrillAndMore loggeri."""
    logger, _ = configure_logging(
        logger_name,
        verbose=verbose,
        logs_dir=logs_dir,
        create_file=create_file,
    )

    return logger


def get_log_path(
    logger: logging.Logger,
) -> Path | None:
    """Atgriež konkrētajam loggerim izveidotā faila ceļu."""
    log_path = getattr(
        logger,
        "_grillandmore_log_path",
        None,
    )

    return log_path if isinstance(log_path, Path) else None
