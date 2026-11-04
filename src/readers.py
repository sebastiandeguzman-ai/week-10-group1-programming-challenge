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
  
 