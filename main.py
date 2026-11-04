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
    
    # -------------------------------------------------------------------------
    # 2. INGESTION & VALIDATION PHASE
    # -------------------------------------------------------------------------
    files_to_process = []
    files_config = config.get("files", {})

    if isinstance(files_config, list):
        for entry in files_config:
            if isinstance(entry, dict) and "file" in entry:
                files_to_process.append(get_input_path(config, entry["file"]))
    elif isinstance(files_config, dict):
        for key in files_config:
            files_to_process.append(get_input_path(config, key))

    if not files_to_process:
        data_dir = Path("data")
        if data_dir.exists():
            files_to_process = [
                p for p in data_dir.iterdir()
                if p.suffix.lower() in [".csv", ".xlsx", ".json", ".parquet"]
            ]

    if not files_to_process:
        print("[!] Error: No input files specified in config or found in 'data/' directory.")
        return 1

    print(f"\n[+] Processing {len(files_to_process)} input file(s)...")

    all_clean_records = []
    quarantine_frames = []
    total_raw_rows = 0

    for file_path in files_to_process:
        print(f"  --> Reading: {file_path}")
        try:
            raw_df = read_file_by_format(file_path, config)
            val_result = process_table(raw_df, str(file_path), rules)

            total_raw_rows += val_result.raw_count
            all_clean_records.extend(val_result.clean)

            if val_result.quarantine:
                quarantine_frames.append(val_result.quarantine_frame())

            # Row reconciliation check
            reconciles = val_result.reconciles()
            validation_master_list.append(
                make_check(
                    name=f"reconciliation_{Path(file_path).name}",
                    expected=val_result.raw_count,
                    actual=len(val_result.clean) + len(val_result.quarantine) + len(val_result.duplicates),
                    tol=0.0,
                    passed=reconciles,
                )
            )

            log_audit_entry(
                audit_log,
                step=step_counter,
                source_file=str(file_path),
                operation="ingest_and_validate",
                rule="type_and_range_check",
                rows_before=val_result.raw_count,
                rows_after=len(val_result.clean),
            )
            step_counter += 1

            counts = val_result.counts()
            print(f"      Raw: {counts['raw']} | Clean: {counts['clean']} | Quarantined: {counts['rejected']} | Duplicates: {counts['duplicates_removed']}")

        except (ReaderError, Exception) as exc:
            print(f"      [!] Error processing {file_path}: {exc}")
            continue

    if not all_clean_records:
        print("[!] Error: No valid records passed validation across all input files.")
        return 1

# -------------------------------------------------------------------------
    # 3. DEDUPLICATION & CONFLICT RESOLUTION
    # -------------------------------------------------------------------------
    print("\n[+] Performing cross-source deduplication & conflict resolution...")
    rows_before_dedup = len(all_clean_records)
    unique_records, _ = remove_duplicates(all_clean_records, source_file="aggregate")
    
    try:
        check_conflicts(unique_records)
    except Exception as conf_err:
        print(f"[!] Critical Conflict Error: {conf_err}")
        return 1

    sorted_clean = sort_records(unique_records)
    canonical_df = pd.DataFrame(sorted_clean)
    canonical_df = canonical_df.loc[:, CANONICAL_COLUMNS].astype(SCHEMA).reset_index(drop=True)

    log_audit_entry(
        audit_log,
        step=step_counter,
        source_file="cross_source_aggregate",
        operation="deduplicate_and_sort",
        rule="remove_exact_duplicates_and_sort",
        rows_before=rows_before_dedup,
        rows_after=len(canonical_df),
    )
    step_counter += 1

    print(f"    Total Canonical Dataset: {len(canonical_df)} rows")

# -------------------------------------------------------------------------
    # 4. EXPORT CANONICAL FORMATS & ROUND-TRIP VERIFICATION
    # -------------------------------------------------------------------------
    print(f"\n[+] Exporting canonical formats to staging ('{staging_dir}')...")
    export_canonical_formats(canonical_df, staging_dir)
    publish_staging_to_output(staging_dir, output_dir)

    print("[+] Running 1e-8 round-trip verification...")
    all_passed, roundtrip_checks = reload_and_compare_exports(canonical_df, staging_dir, abs_tol=1e-8)
    validation_master_list.extend(roundtrip_checks)

    # Four format agreement check
    reloaded_tables = {
        "csv": pd.read_csv(output_dir / "canonical.csv"),
        "xlsx": pd.read_excel(output_dir / "canonical.xlsx", sheet_name="observations"),
        "json": pd.read_json(output_dir / "canonical.json"),
        "parquet": pd.read_parquet(output_dir / "canonical.parquet"),
    }
    _, agreement_checks = verify_four_format_agreement(reloaded_tables)
    validation_master_list.extend(agreement_checks)

    # -------------------------------------------------------------------------
    # 5. RUN ANALYTICS & SAVE ANALYTICAL TABLES
    # -------------------------------------------------------------------------
    print("\n[+] Running Analytics & generating analytical tables...")
    analytics_output = run_all_analytics(canonical_df, reporting_year=2007, audit_log=audit_log)
    validation_master_list.extend(analytics_output["validation_checks"])

    # Export asia_selected_year.csv
    asia_csv_path = output_dir / "asia_selected_year.csv"
    analytics_output["asia_selected_year"].to_csv(asia_csv_path, index=False)
    print(f"    --> Saved: {asia_csv_path}")

    # Export country_history.csv
    ph_csv_path = output_dir / "country_history.csv"
    analytics_output["country_history"].to_csv(ph_csv_path, index=False)
    print(f"    --> Saved: {ph_csv_path}")

    # Export population_index.csv
    pop_idx_csv_path = output_dir / "population_index.csv"
    analytics_output["population_index"].to_csv(pop_idx_csv_path, index=False)
    print(f"    --> Saved: {pop_idx_csv_path}")