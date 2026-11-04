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
