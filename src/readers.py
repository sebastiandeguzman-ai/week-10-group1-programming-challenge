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
 
# Manifest entry key -> reader setting name, per format.
_MANIFEST_SETTING_KEYS: dict[str, dict[str, str]] = {
    "csv": {
        "encoding": "encoding",
        "separator": "delimiter",
        "delimiter": "delimiter",
        "comment_prefix": "comment_prefix",
    },
    "excel": {
        "sheet_name": "sheet_name",
        "skip_sheets": "skip_sheets",
    },
}
 
Reader = Callable[[str | Path, dict[str, Any]], pd.DataFrame]

 
 # Exceptions---------------------------------------------------------------------------
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


# Configuration------------------------------------------------------------------------
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
    """Resolve an input file relative to the config folder.
 
    ``name`` is a key of ``config["files"]`` (dictionary layout) or the
    ``"file"`` value of a manifest entry (list layout).
 
    Raises:
        ConfigError: ``name`` is not listed under ``"files"``.
    """
    files = config.get("files", {})
    if isinstance(files, list):
        entry = _find_manifest_entry(files, name)
        if entry is None:
            raise ConfigError(f"Config has no entry {name!r} under 'files'.")
        raw_path = entry["file"]
    else:
        files = _get_section(config, "files")
        if name not in files:
            raise ConfigError(f"Config has no entry {name!r} under 'files'.")
        raw_path = files[name]
    path = Path(str(raw_path))
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
 
 
def _find_manifest_entry(
    files: Sequence[Any], name: str
) -> Mapping[str, Any] | None:
    """Return the manifest entry whose ``"file"`` matches ``name``."""
    wanted = Path(str(name)).name.casefold()
    for entry in files:
        if isinstance(entry, Mapping) and "file" in entry:
            if Path(str(entry["file"])).name.casefold() == wanted:
                return entry
    return None
 
 
def _manifest_entry(
    config: Mapping[str, Any], file_name: str | None
) -> Mapping[str, Any]:
    """Return the manifest entry for ``file_name`` (empty if none)."""
    files = config.get("files")
    if file_name is None or not isinstance(files, list):
        return {}
    return _find_manifest_entry(files, file_name) or {}
 
 
def _format_settings(
    config: Mapping[str, Any], fmt: str, file_name: str | None = None
) -> dict[str, Any]:
    """Merge defaults, ``formats.<fmt>`` and the file's manifest entry."""
    user = _get_section(config, "formats").get(fmt, {})
    if not isinstance(user, Mapping):
        raise ConfigError(f"Config entry 'formats.{fmt}' must be an object.")
    settings = {**DEFAULT_FORMAT_SETTINGS[fmt], **user}
    entry = _manifest_entry(config, file_name)
    for source_key, setting in _MANIFEST_SETTING_KEYS[fmt].items():
        if source_key in entry:
            settings[setting] = entry[source_key]
    return settings
 
 
def _column_mapping(
    config: Mapping[str, Any], fmt: str, file_name: str | None = None
) -> dict[str, str]:
    """Return the raw-name -> canonical-name mapping for ``fmt``.
 
    A manifest entry's ``source_to_canonical`` for ``file_name`` is merged
    last, so it wins over the format-wide mappings.
    """
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
    from_manifest = _manifest_entry(config, file_name).get(
        "source_to_canonical", {}
    )
    if not isinstance(from_manifest, Mapping):
        raise ConfigError(
            f"'source_to_canonical' for {file_name!r} must be an object."
        )
    mapping.update(from_manifest)
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

# helpers-------------------------------------------------------------------------
def _require_file(file_path: str | Path) -> Path:
    """Return ``file_path`` as a ``Path`` or raise if it is not a file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")
    return path
 
 
def _norm(name: Any) -> str:
    """Normalise a header for matching (trim, collapse spaces, casefold)."""
    return " ".join(str(name).lstrip("\ufeff").split()).casefold()
 
 
def _build_header_map(
    raw_columns: Sequence[str], mapping: Mapping[str, str], source: str
) -> dict[str, str]:
    """Map raw headers to canonical names; ignore all other headers."""
    lookup = {_norm(col): col for col in CANONICAL_COLUMNS}
    lookup.update({_norm(raw): canon for raw, canon in mapping.items()})
    header_map: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for raw in raw_columns:
        canon = lookup.get(_norm(raw))
        if canon is None:
            continue
        if canon in claimed:
            raise InvalidFileError(
                f"{source}: columns {claimed[canon]!r} and {raw!r} "
                f"both map to {canon!r}."
            )
        claimed[canon] = raw
        header_map[raw] = canon
    return header_map
 
 
def _to_canonical_frame(
    raw: pd.DataFrame, mapping: Mapping[str, str], source: str
) -> pd.DataFrame:
    """Drop empty rows, map and select columns, add ``source_record``."""
    blank = raw.isna() | raw.astype(str).apply(
        lambda col: col.str.strip().eq("")
    )
    raw = raw.loc[~blank.all(axis=1)]
 
    header_map = _build_header_map(list(raw.columns), mapping, source)
    missing = [c for c in CANONICAL_COLUMNS if c not in header_map.values()]
    if missing:
        raise MissingColumnError(
            f"{source}: missing required column(s): {', '.join(missing)}. "
            f"Found: {', '.join(map(str, raw.columns))}."
        )
 
    frame = raw[list(header_map)].rename(columns=header_map)
    frame = frame[list(CANONICAL_COLUMNS)].reset_index(drop=True)
    frame[SOURCE_RECORD_COLUMN] = np.arange(1, len(frame) + 1, dtype="int64")
    return frame
 