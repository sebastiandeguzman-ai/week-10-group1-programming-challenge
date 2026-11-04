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