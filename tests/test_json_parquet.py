import pytest
import pandas as pd

from src.readers_json_parquet import (
    dfjson,
    dfparquet,
    check_missing_columns,
    REQUIRED_COLUMNS
)

def test_json_required_columns():
    assert all(
        col in dfjson.columns
        for col in REQUIRED_COLUMNS
    )

def test_parquet_required_columns():
    assert all(
        col in dfparquet.columns
        for col in REQUIRED_COLUMNS
    )
