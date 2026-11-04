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
    "json": {
        "encoding": "utf-8",
        "record_path": "records",
    },
    "parquet": {},
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
    "json": {
        "encoding": "encoding",
        "record_path": "record_path",
    },
    "parquet": {},
}
 
Reader = Callable[[str | Path, dict[str, Any]], pd.DataFrame]


# Exceptions ---------------------------------------------------------------------
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

 # CSV-----------------------------------------------------------------------
def read_csv_records(
    file_path: str | Path, config: dict[str, Any]
) -> pd.DataFrame:
    """Read a delimited text file into canonical, uncast records."""
    path = _require_file(file_path)
    settings = _format_settings(config, "csv", path.name)
 
    try:
        text = path.read_text(encoding=settings["encoding"])
    except UnicodeDecodeError as exc:
        raise InvalidFileError(
            f"{path.name}: cannot decode as {settings['encoding']} ({exc})."
        ) from exc
    except LookupError as exc:
        raise ConfigError(
            f"Unknown CSV encoding {settings['encoding']!r}."
        ) from exc
 
    text = text.removeprefix("\ufeff").removeprefix("\u00ef\u00bb\u00bf")
 
    lines = text.split("\n")
    prefix = settings.get("comment_prefix")
    if prefix:
        lines = [ln for ln in lines if not ln.lstrip().startswith(prefix)]
 
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", pd.errors.ParserWarning)
            raw = pd.read_csv(
                io.StringIO("\n".join(lines)),
                sep=settings["delimiter"],
                dtype=object,
                keep_default_na=False,
                na_filter=False,
                index_col=False,
            )
    except pd.errors.EmptyDataError as exc:
        raise InvalidFileError(
            f"{path.name}: no header row after removing comment lines."
        ) from exc
    except (pd.errors.ParserError, pd.errors.ParserWarning) as exc:
        raise InvalidFileError(f"{path.name}: malformed CSV ({exc}).") from exc
 
    return _to_canonical_frame(
        raw, _column_mapping(config, "csv", path.name), path.name
    )


# JSON -----------------------------------------------------------------------
def _resolve_record_path(value: Any, path: str | Sequence[str]) -> Any:
    """Follow a dotted or list-style record path through nested JSON."""
    if isinstance(path, str):
        parts = [part for part in path.split(".") if part]
    else:
        parts = [part for part in path if part]

    current = value
    for part in parts:
        if isinstance(current, Mapping):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def read_json_records(
    file_path: str | Path, config: dict[str, Any]
) -> pd.DataFrame:
    """Read a JSON array/object of records into canonical, uncast records."""
    path = _require_file(file_path)
    settings = _format_settings(config, "json", path.name)

    try:
        with path.open(encoding=settings.get("encoding", "utf-8")) as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise InvalidFileError(f"{path.name}: cannot read JSON ({exc}).") from exc

    record_path = settings.get("record_path", "records")
    records = _resolve_record_path(payload, record_path)
    if records is None:
        raise InvalidFileError(
            f"{path.name}: JSON does not contain record path {record_path!r}."
        )
    if isinstance(records, Mapping):
        records = [records]
    if not isinstance(records, Sequence) or isinstance(
        records, (str, bytes, bytearray)
    ):
        raise InvalidFileError(
            f"{path.name}: JSON record path {record_path!r} is not a list of objects."
        )

    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise InvalidFileError(
                f"{path.name}: JSON record {index} is not an object."
            )
        row: dict[str, Any] = {}
        for section_name in ("identity", "measures"):
            section = record.get(section_name)
            if section is None:
                continue
            if not isinstance(section, Mapping):
                raise InvalidFileError(
                    f"{path.name}: JSON record {index} field {section_name!r} must be an object."
                )
            for key, value in section.items():
                row[f"{section_name}.{key}"] = value
        if not row:
            row = dict(record)
        rows.append(row)

    if not rows:
        raise InvalidFileError(f"{path.name}: JSON file contains no records.")

    raw = pd.DataFrame(rows, dtype=object)
    return _to_canonical_frame(
        raw, _column_mapping(config, "json", path.name), path.name
    )


# Parquet ---------------------------------------------------------------------
def read_parquet_records(
    file_path: str | Path, config: dict[str, Any]
) -> pd.DataFrame:
    """Read a parquet table into canonical, uncast records."""
    path = _require_file(file_path)
    _format_settings(config, "parquet", path.name)

    try:
        raw = pd.read_parquet(path)
    except (ImportError, ValueError, OSError) as exc:
        raise InvalidFileError(f"{path.name}: cannot read parquet ({exc}).") from exc

    if raw.empty:
        raise InvalidFileError(f"{path.name}: parquet file is empty.")

    return _to_canonical_frame(
        raw, _column_mapping(config, "parquet", path.name), path.name
    )


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def read_excel_records(
    file_path: str | Path, config: dict[str, Any]
) -> pd.DataFrame:
    """Read the observations sheet of an ``.xlsx`` workbook."""
    path = _require_file(file_path)
    settings = _format_settings(config, "excel", path.name)
 
    try:
        workbook = load_workbook(path, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException) as exc:
        raise InvalidFileError(
            f"{path.name}: not a valid .xlsx workbook."
        ) from exc
    try:
        sheet_name = _select_sheet(workbook.sheetnames, settings, path.name)
        rows = list(workbook[sheet_name].iter_rows(values_only=True))
    finally:
        workbook.close()
 
    if not rows:
        raise InvalidFileError(f"{path.name}: sheet {sheet_name!r} is empty.")
 
    headers = _unique_headers(rows[0])
    width = len(headers)
    data = [
        list(row[:width]) + [None] * (width - len(row))
        for row in rows[1:]
    ]
    raw = pd.DataFrame(data, columns=headers, dtype=object)
 
    return _to_canonical_frame(
        raw, _column_mapping(config, "excel", path.name), path.name
    )
 
 
def _select_sheet(
    sheet_names: Sequence[str], settings: Mapping[str, Any], source: str
) -> str:
    """Pick the observations sheet, ignoring the skipped sheets."""
    skip_setting = settings.get("skip_sheets", [])
    if isinstance(skip_setting, str):
        skip_setting = [skip_setting]
    skip = {_norm(name) for name in skip_setting}
    candidates = [name for name in sheet_names if _norm(name) not in skip]
 
    wanted = settings.get("sheet_name")
    if wanted:
        for name in candidates:
            if _norm(name) == _norm(wanted):
                return name
    if len(candidates) == 1:
        return candidates[0]
    raise InvalidFileError(
        f"{source}: cannot identify the observations sheet "
        f"(wanted {wanted!r}; usable sheets: {candidates or 'none'})."
    )
 
 
def _unique_headers(cells: Sequence[Any]) -> list[str]:
    """Turn header cells into unique strings (blank -> ``Unnamed: n``)."""
    seen: dict[str, int] = {}
    headers: list[str] = []
    for index, cell in enumerate(cells):
        text = "" if cell is None else str(cell).strip()
        name = text or f"Unnamed: {index}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        headers.append(name if count == 0 else f"{name}.{count}")
    return headers

# Dispatcher----------------------------------------------------------------
_READERS: dict[str, Reader] = {
    ".csv": read_csv_records,
    ".xlsx": read_excel_records,
    ".json": read_json_records,
    ".parquet": read_parquet_records,
}
 
 
def register_reader(extension: str, reader: Reader) -> None:
    """Register ``reader`` for ``extension``."""
    ext = extension.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension {extension!r}; "
            f"expected one of {SUPPORTED_EXTENSIONS}."
        )
    _READERS[ext] = reader
 
 
def read_file_by_format(
    file_path: str | Path, config: dict[str, Any]
) -> pd.DataFrame:
    """Read ``file_path`` with the reader matching its extension."""
    path = _require_file(file_path)
    ext = path.suffix.lower()
    reader = _READERS.get(ext)
    if reader is not None:
        return reader(path, config)
    if ext in SUPPORTED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"No reader registered for {ext!r} files "
            f"(see register_reader)."
        )
    shown = ext if ext else "(none)"
    raise UnsupportedFormatError(
        f"Unsupported file extension {shown!r} for {path.name}; "
        f"supported: {', '.join(SUPPORTED_EXTENSIONS)}."
    )