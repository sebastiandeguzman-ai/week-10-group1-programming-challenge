"""
Main Execution Script for Data Pipeline.

Integrates readers, validator, analytics, and exporter modules to generate:
1. canonical.csv, .xlsx, .json, .parquet
2. asia_selected_year.csv
3. country_history.csv
4. population_index.csv
5. validation.csv
6. audit_log.csv
"""

from pathlib import Path
import sys
import pandas as pd

from src.readers import (
    load_config,
    get_input_path,
    read_file_by_format,
    ConfigError,
    ReaderError,
)
from src.validator import (
    build_rules,
    process_table,
    remove_duplicates,
    check_conflicts,
    sort_records,
)
from src.analytics import run_all_analytics, verify_four_format_agreement, make_check
from src.exporter import (
    export_canonical_formats,
    reload_and_compare_exports,
    publish_staging_to_output,
    log_audit_entry,
    CANONICAL_COLUMNS,
    SCHEMA,
)

def run_pipeline(config_path: str = "config.json") -> int:
    """Execute the complete data processing pipeline and export all required deliverables."""
    print("=" * 60)
    print("STARTING DATA INGESTION & ANALYTICS PIPELINE")
    print("=" * 60)

    audit_log = []
    validation_master_list = []
    step_counter = 1

    # Setup directories
    staging_dir = Path("staging")
    output_dir = Path("output")
    staging_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. LOAD CONFIGURATION & BUILD RULES
    # -------------------------------------------------------------------------
    cfg_path = Path(config_path)
    if not cfg_path.exists():
        print(f"[!] Warning: Config file '{config_path}' not found. Operating with default settings.")
        config = {"files": {}, "formats": {}, "column_mappings": {}}
    else:
        print(f"[+] Loading configuration from '{cfg_path.resolve()}'...")
        config = load_config(cfg_path)

    rules = build_rules(config)
    log_audit_entry(
        audit_log,
        step=step_counter,
        source_file=str(cfg_path),
        operation="load_config",
        rule="parse_manifest_and_rules",
        rows_before=0,
        rows_after=0,
    )
    step_counter += 1