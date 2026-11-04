
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
 
import pandas as pd
from openpyxl import Workbook
 
# Point to the root folder where 'src' lives
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
 
from src import readers_csv_excel as rce
from src.readers_csv_excel import (
    CANONICAL_COLUMNS,
    SOURCE_RECORD_COLUMN,
    ConfigError,
    InvalidFileError,
    MissingColumnError,
    ReaderError,
    UnsupportedFormatError,
    get_input_path,
    load_config,
    read_csv_records,
    read_excel_records,
    read_file_by_format,
    read_json_records,
    read_parquet_records,
    register_reader,
)
 
try:
    import pyarrow  # noqa: F401
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False
 
EXPECTED_COLUMNS = list(CANONICAL_COLUMNS) + [SOURCE_RECORD_COLUMN]
HEADER = "country;continent;year;lifeExp;pop;gdpPercap"
 
CSV_TEXT = (
    "# Sample country records\n"
    "# generated for tests\n"
    "country;continent;year;life_expectancy;pop;gdpPercap;export_note\n"
    "Côte d'Ivoire;Africa;2007;54.5;19000000;1800.5;\"note; with delimiter\"\n"
    "Brazil;Americas;2007;72.4;190010647;9065.8;x\n"
    ";;;;;;\n"
    "Japan;Asia;2007;82.6;127467972;31656.1;x\n"
    "# trailing comment\n"
    "Chad;Africa;1952;;3000000;1100;x\n"
)
CSV_CONFIG = {"column_mappings": {"csv": {"life_expectancy": "lifeExp"}}}
 
XLSX_HEADER = ["country", "continent", "year", "lifeExp", "pop", "GDP per capita"]
XLSX_ROWS = [
    ["Côte d'Ivoire", "Africa", 2007, 54.5, 19000000, 1800.5],
    ["Brazil", "Americas", 2007, 72.4, 190010647, 9065.8],
    [None, None, None, None, None, None],
    ["Chad", "Africa", 1952, None, 3000000, 1100],
]
XLSX_CONFIG = {"column_mappings": {"excel": {"GDP per capita": "gdpPercap"}}}
 
JSON_MAPPING = {
    "identity.country": "country",
    "identity.continent": "continent",
    "identity.year": "year",
    "measures.lifeExp": "lifeExp",
    "measures.pop": "pop",
    "measures.gdpPercap": "gdpPercap",
}
JSON_CONFIG = {"column_mappings": {"json": JSON_MAPPING}}
 