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
def test_json_missing_columns():
    incomplete = dfjson.drop(columns=['pop'])

    with pytest.raises(ValueError):
        check_missing_columns(incomplete)

def test_parquet_missing_columns():
    incomplete = dfparquet.drop(columns=['country'])

    with pytest.raises(ValueError):
        check_missing_columns(incomplete)

def test_json_record_order():
    original = dfjson['country'].tolist()
    reordered = dfjson.iloc[::-1]['country'].tolist()

    assert reordered == original[::-1]

def test_parquet_record_order():
    original = dfparquet['country'].tolist()
    reordered = dfparquet.iloc[::-1]['country'].tolist()

    assert reordered == original[::-1]
