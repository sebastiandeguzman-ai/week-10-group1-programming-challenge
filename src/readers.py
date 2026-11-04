from __future__ import annotations

import io
import json
import warnings
import zipfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

__all__ = [
    "CANONICAL_COLUMNS",
    "SOURCE_RECORD_COLUMN",
    "SUPPORTED_EXTENSIONS",
    "ConfigError",
    "InvalidFileError",
    "MissingColumnError",
    "ReaderError",
    "UnsupportedFormatError",
    "get_input_path",
    "load_config",
    "read_csv_records",
    "read_excel_records",
    "read_file_by_format",
    "register_reader",
]

CANONICAL_COLUMNS: tuple[str, ...] = (
    "country",
    "continent",
    "year",
    "lifeExp",
    "pop",
    "gdpPercap",
)
SOURCE_RECORD_COLUMN: str = "source_record"
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".csv",
    ".xlsx",
    ".json",
    ".parquet",
)

DEFAULT_FORMAT_SETTINGS: dict[str, dict[str, Any]] = {
    "csv": {
        "encoding": "cp1252",
        "delimiter": ";",
        "comment_prefix": "#",
    },
    "excel": {
        "sheet_name": "observations",
        "skip_sheets": ["Readme"],
    },
}

Reader = Callable[[str | Path, dict[str, Any]], pd.DataFrame]


# Exceptions ----------------------------------------------------
class ReaderError(Exception):
    """Base class for all errors raised by the readers."""


class ConfigError(ReaderError):
    """Raised when the configuration file is unreadable or malformed."""


class UnsupportedFormatError(ReaderError):
    """Raised when no reader exists for a file's extension."""


class InvalidFileError(ReaderError):
    """Raised when a file exists but cannot be parsed as its format."""


class MissingColumnError(ReaderError, ValueError):
    """Raised when a required canonical column is absent (file-level)."""


# Configuration---------------------------------------------------------------
def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load ``config.json`` / ``manifest.json`` into a dictionary.

    The returned dictionary gets an extra ``"_config_dir"`` entry (the
    absolute folder of the config file) so relative paths can be resolved
    by :func:`get_input_path`.

    Raises:
        FileNotFoundError: The config file does not exist.
        ConfigError: The file is not valid UTF-8 JSON or not an object.
    """
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    try:
        with path.open(encoding="utf-8-sig") as handle:
            config = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError(f"{path.name} must contain a JSON object.")
    config["_config_dir"] = str(path.resolve().parent)
    return config


def get_input_path(config: Mapping[str, Any], name: str) -> Path:
    """Resolve ``config["files"][name]`` relative to the config folder.

    Raises:
        ConfigError: ``name`` is not listed under ``"files"``.
    """
    files = _get_section(config, "files")
    if name not in files:
        raise ConfigError(f"Config has no entry {name!r} under 'files'.")
    path = Path(str(files[name]))
    base_dir = config.get("_config_dir")
    if not path.is_absolute() and base_dir:
        path = Path(str(base_dir)) / path
    return path


def _get_section(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return ``config[key]`` as a mapping (empty if absent)."""
    section = config.get(key, {})
    if not isinstance(section, Mapping):
        raise ConfigError(f"Config entry {key!r} must be a JSON object.")
    return section


def _format_settings(
    config: Mapping[str, Any], fmt: str
) -> dict[str, Any]:
    """Merge user settings for ``fmt`` over the built-in defaults."""
    user = _get_section(config, "formats").get(fmt, {})
    if not isinstance(user, Mapping):
        raise ConfigError(f"Config entry 'formats.{fmt}' must be an object.")
    return {**DEFAULT_FORMAT_SETTINGS[fmt], **user}


def _column_mapping(config: Mapping[str, Any], fmt: str) -> dict[str, str]:
    """Return the raw-name -> canonical-name mapping for ``fmt``."""
    section = _get_section(config, "column_mappings")
    mapping: dict[str, str] = {
        raw: canon for raw, canon in section.items()
        if isinstance(canon, str)
    }
    specific = section.get(fmt, {})
    if not isinstance(specific, Mapping):
        raise ConfigError(
            f"Config entry 'column_mappings.{fmt}' must be an object."
        )
    mapping.update(specific)
    unknown = {
        raw: canon for raw, canon in mapping.items()
        if canon not in CANONICAL_COLUMNS
    }
    if unknown:
        raise ConfigError(
            f"Column mapping targets unknown canonical names: {unknown}. "
            f"Valid names: {', '.join(CANONICAL_COLUMNS)}."
        )
    return mapping

