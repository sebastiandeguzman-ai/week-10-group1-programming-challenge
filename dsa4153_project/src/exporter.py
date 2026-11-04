"""Export, round-trip reload verification, staging, and audit logging module (Member 5)."""

from pathlib import Path
import json
import numpy as np
import pandas as pd


# Canonical schema contract mapping column names to target pandas dtypes
SCHEMA = {
    "country": "string",
    "continent": "string",
    "year": "int64",
    "lifeExp": "float64",
    "pop": "int64",
    "gdpPercap": "float64"
}

# Standard canonical column ordering required across all output formats
CANONICAL_COLUMNS = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]

def log_audit_entry(audit_list, step, source_file, operation, rule, rows_before, rows_after):
    """
    Appends a structured audit record tracking dataset row counts and pipeline steps.
    
    Parameters:
        audit_list (list): Master list storing audit log entries.
        step (int): Sequential pipeline execution step number.
        source_file (str/Path): File path evaluated during step.
        operation (str): Processing description (e.g., 'export', 'quarantine').
        rule (str): Applied rule or constraint.
        rows_before (int): Row count prior to operation.
        rows_after (int): Row count retained after operation.
    """
    audit_list.append({
        "step": step,
        "source_file": str(source_file),
        "operation": operation,
        "rule": rule,
        "rows_before": rows_before,
        "rows_after": rows_after
    })


def export_canonical_formats(df, target_dir):
    """
    Exports clean canonical dataset into four file formats: CSV, XLSX, JSON, and Parquet.
    
    Parameters:
        df (pd.DataFrame): Cleaned 1,704 canonical Gapminder records.
        target_dir (str/Path): Staging destination folder path.
        
    Returns:
        dict: Mapping of format keys to written Path objects.
    """
    target_path = Path(target_dir)
    # Create target staging directory if it does not exist
    target_path.mkdir(parents=True, exist_ok=True)

    # Map output file paths using Path division syntax
    paths = {
        "csv": target_path / "canonical.csv",
        "xlsx": target_path / "canonical.xlsx",
        "json": target_path / "canonical.json",
        "parquet": target_path / "canonical.parquet",
    }

    # 1. Export CSV without row index using standard UTF-8 encoding
    df.to_csv(paths["csv"], index=False, encoding="utf-8")

    # 2. Export Excel workbook with sheet name 'observations' via openpyxl
    with pd.ExcelWriter(paths["xlsx"], engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="observations", index=False)

    # 3. Export JSON formatted as a list of record objects (orient='records')
    df.to_json(paths["json"], orient="records", indent=2)

    # 4. Export Parquet binary format using pyarrow engine
    df.to_parquet(paths["parquet"], engine="pyarrow", index=False)

    return paths

def reapply_schema(df):
    """
    Re-applies canonical column ordering and strict dtypes upon reloading exported files.
    
    Parameters:
        df (pd.DataFrame): Raw reloaded dataset dataframe.
        
    Returns:
        pd.DataFrame: Schema-compliant dataframe with enforced column types.
    """
    # Enforce strict column order selection
    df_clean = df.loc[:, CANONICAL_COLUMNS].copy()
    # Cast dataframe columns to target SCHEMA dictionary dtypes
    return df_clean.astype(SCHEMA)


def reload_and_compare_exports(df_canonical, staging_dir, abs_tol=1e-8):
    """
    Reloads exported files, re-applies schema, and asserts equality against pre-export table.
    
    Parameters:
        df_canonical (pd.DataFrame): Baseline canonical dataframe prior to export.
        staging_dir (str/Path): Staging directory containing exported files.
        abs_tol (float): Absolute tolerance for floating point comparisons (1e-8).
        
    Returns:
        tuple: (all_passed: bool, validation_records: list of dicts)
    """
    staging_path = Path(staging_dir)
    validation_records = []
    all_passed = True
    
    # Establish baseline expected dataframe with reapplied schema
    df_expected = reapply_schema(df_canonical)

    # Define format loaders using pathlib Path objects
    loaders = {
        "csv_roundtrip": lambda: pd.read_csv(staging_path / "canonical.csv", encoding="utf-8"),
        "xlsx_roundtrip": lambda: pd.read_excel(staging_path / "canonical.xlsx", sheet_name="observations", engine="openpyxl"),
        "json_roundtrip": lambda: pd.read_json(staging_path / "canonical.json", orient="records"),
        "parquet_roundtrip": lambda: pd.read_parquet(staging_path / "canonical.parquet", engine="pyarrow"),
    }

    # Execute round-trip reload validation across all four file formats
    for check_name, load_fn in loaders.items():
        try:
            # Reload raw data and re-apply schema contract
            reloaded_raw = load_fn()
            reloaded_df = reapply_schema(reloaded_raw)

            # Assert strict frame equality with 1e-8 absolute tolerance and 0 relative tolerance
            pd.testing.assert_frame_equal(
                df_expected, 
                reloaded_df, 
                check_exact=False, 
                atol=abs_tol, 
                rtol=0
            )

            # Append successful validation check result
            validation_records.append({
                "check": f"roundtrip_{check_name}",
                "expected": f"Exact match within tolerance {abs_tol}",
                "actual": "Matched pre-export canonical table",
                "tolerance": abs_tol,
                "pass": True
            })
        except Exception as error:
            # Flag failure if reloaded data violates tolerance or schema match
            all_passed = False
            validation_records.append({
                "check": f"roundtrip_{check_name}",
                "expected": f"Exact match within tolerance {abs_tol}",
                "actual": f"Mismatch error: {str(error)}",
                "tolerance": abs_tol,
                "pass": False
            })

    return all_passed, validation_records