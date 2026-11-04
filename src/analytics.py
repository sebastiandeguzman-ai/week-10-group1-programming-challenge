"""
Analytics module 

"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

CANONICAL_COLS: List[str] = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]
ATOL: float = 1e-8
RTOL: float = 0.0
MATRIX_COUNTRIES: List[str] = ["Philippines", "Indonesia", "Thailand"]
MATRIX_YEARS: List[int] = [1982, 1987, 1992, 1997, 2002, 2007]


def make_check(name: str, expected: Any, actual: Any, tol: float = 0.0, passed: bool = True) -> Dict[str, Any]:
    """Create a standardized validation check record for validation.csv."""
    return {"check": name, "expected": expected, "actual": actual, "tolerance": tol, "pass": bool(passed)}


def verify_four_format_agreement(
    tables: Union[Dict[str, pd.DataFrame], List[pd.DataFrame]],
    atol: float = ATOL,
    rtol: float = RTOL,
) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    """Sort cleaned tables by (country, year) and verify exact key/text/int and 1e-8 float agreement."""
    if isinstance(tables, list):
        tables = {f"format_{i+1}": df for i, df in enumerate(tables)}
    if len(tables) < 2:
        raise ValueError("Need at least two tables to verify agreement.")

    sorted_dfs: Dict[str, pd.DataFrame] = {}
    for name, df in tables.items():
        if not set(CANONICAL_COLS).issubset(df.columns):
            raise ValueError(f"'{name}' is missing required canonical columns.")
        if df["country"].isna().any() or df["year"].isna().any() or (df["country"].astype(str).str.strip() == "").any():
            raise ValueError(f"'{name}' has missing or empty (country, year) keys.")

        sorted_dfs[name] = df.loc[:, CANONICAL_COLS].sort_values(["country", "year"]).reset_index(drop=True)

    names = list(sorted_dfs.keys())
    ref_name, ref_df = names[0], sorted_dfs[names[0]]
    ref_keys = set(zip(ref_df["country"], ref_df["year"]))
    if len(ref_keys) != len(ref_df):
        raise ValueError(f"'{ref_name}' contains duplicate (country, year) keys.")

    checks: List[Dict[str, Any]] = []
    for name in names[1:]:
        cur_df = sorted_dfs[name]
        cur_keys = set(zip(cur_df["country"], cur_df["year"]))
        if len(cur_df) != len(ref_df) or cur_keys != ref_keys:
            raise ValueError(f"Key mismatch between '{ref_name}' and '{name}'.")

        exact_ok = (
            ref_df.isna().equals(cur_df.isna())
            and (ref_df[["country", "continent"]].values == cur_df[["country", "continent"]].values).all()
            and np.array_equal(ref_df[["year", "pop"]].to_numpy(dtype=np.int64), cur_df[["year", "pop"]].to_numpy(dtype=np.int64))
        )
        ref_floats = ref_df[["lifeExp", "gdpPercap"]].to_numpy(dtype=float)
        cur_floats = cur_df[["lifeExp", "gdpPercap"]].to_numpy(dtype=float)
        max_diff = float(np.max(np.abs(ref_floats - cur_floats))) if len(ref_df) else 0.0
        float_ok = np.allclose(ref_floats, cur_floats, rtol=rtol, atol=atol)

        passed = bool(exact_ok and float_ok)
        checks.append(make_check(f"agreement_{ref_name}_vs_{name}", 0.0, max_diff, atol, passed))
        if not passed:
            raise ValueError(f"Agreement failed between '{ref_name}' and '{name}' (max_diff={max_diff}).")

    return ref_df.copy(), checks


def build_asia_selected_year(df: pd.DataFrame, reporting_year: int = 2007) -> pd.DataFrame:
    """Select Asia and reporting_year using .loc; add pop_millions and descending lifeExp rank."""
    out = df.loc[(df["continent"] == "Asia") & (df["year"] == int(reporting_year)), CANONICAL_COLS].copy()
    out.loc[:, "pop_millions"] = out["pop"] / 1e6
    out.loc[:, "lifeExp_rank"] = out["lifeExp"].rank(ascending=False, method="min").astype(np.int64)
    return out.sort_values(["lifeExp_rank", "country"]).reset_index(drop=True)


def compute_independent_asia_pop(df: pd.DataFrame, reporting_year: int = 2007) -> int:
    """Compute selected-year Asian population total via Python loop independent of pandas summary."""
    return sum(
        int(pop)
        for cont, yr, pop in zip(df["continent"], df["year"], df["pop"])
        if cont == "Asia" and int(yr) == int(reporting_year)
    )


def build_country_history(df: pd.DataFrame, country: str = "Philippines") -> pd.DataFrame:
    """Select all rows for a country sorted by year; add pop_millions and lifeExp change from first year."""
    out = df.loc[df["country"] == country, CANONICAL_COLS].sort_values("year").reset_index(drop=True)
    if out.empty:
        raise ValueError(f"No records found for '{country}'.")
    out.loc[:, "pop_millions"] = out["pop"] / 1e6
    out.loc[:, "lifeExp_change"] = out["lifeExp"] - float(out.loc[0, "lifeExp"])
    return out


def build_population_index_matrix(
    df: pd.DataFrame,
    countries: Optional[List[str]] = None,
    years: Optional[List[int]] = None,
    baseline_year: int = 1982,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Build 3x6 NumPy population index matrix (1982=100) via broadcasting and verify against a loop."""
    countries = countries or MATRIX_COUNTRIES
    years = years or MATRIX_YEARS
    if baseline_year not in years:
        raise ValueError(f"Baseline year {baseline_year} must be in {years}.")

    sub = df.loc[df["country"].isin(countries) & df["year"].isin(years), ["country", "year", "pop"]]
    expected_keys = {(c, int(y)) for c in countries for y in years}
    actual_keys = set(zip(sub["country"], sub["year"].astype(int)))
    if expected_keys - actual_keys:
        raise ValueError(f"Missing keys for population matrix: {sorted(expected_keys - actual_keys)}")

    pop_matrix = sub.pivot(index="country", columns="year", values="pop").loc[countries, years].to_numpy(dtype=float)
    base_idx = years.index(baseline_year)
    base_col = pop_matrix[:, base_idx : base_idx + 1]  # Shape (3, 1) for broadcasting

    # Broadcast 1982 baseline so 1982 = 100
    index_matrix = (pop_matrix / base_col) * 100.0

    # Independent loop calculation for verification
    loop_matrix = np.zeros_like(pop_matrix)
    for r in range(pop_matrix.shape[0]):
        for c in range(pop_matrix.shape[1]):
            loop_matrix[r, c] = (pop_matrix[r, c] / pop_matrix[r, base_idx]) * 100.0

    max_diff = float(np.max(np.abs(index_matrix - loop_matrix)))
    if not np.allclose(index_matrix, loop_matrix, rtol=RTOL, atol=ATOL):
        raise ValueError(f"Broadcast vs loop mismatch: {max_diff}")

    # Boolean selection and aggregation
    mask_gt_120 = index_matrix >= 120.0
    result_df = pd.DataFrame(index_matrix, columns=[str(y) for y in years])
    result_df.insert(0, "country", countries)

    info = {
        "shape_before": (pop_matrix.shape, base_col.shape),
        "shape_after": index_matrix.shape,
        "max_loop_diff": max_diff,
        "bool_count_ge_120": int(np.sum(mask_gt_120)),
        "bool_mean_ge_120": float(np.mean(index_matrix[mask_gt_120])) if np.any(mask_gt_120) else 0.0,
    }
    return result_df, info


def run_all_analytics(
    canonical_df: pd.DataFrame,
    reporting_year: int = 2007,
    audit_log: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run all pandas/NumPy analyses and return tables, diagnostics, and validation check rows."""
    asia_df = build_asia_selected_year(canonical_df, reporting_year)
    indep_asia_pop = compute_independent_asia_pop(canonical_df, reporting_year)
    ph_df = build_country_history(canonical_df, "Philippines")
    pop_idx_df, numpy_info = build_population_index_matrix(canonical_df)

    checks = [
        make_check(f"asia_pop_{reporting_year}", indep_asia_pop, int(asia_df["pop"].sum()), 0.0, indep_asia_pop == int(asia_df["pop"].sum())),
        make_check("numpy_broadcast_vs_loop", 0.0, numpy_info["max_loop_diff"], ATOL, numpy_info["max_loop_diff"] <= ATOL),
    ]
    if int(reporting_year) == 2007 and len(asia_df) == 33:
        ph_2007 = int(ph_df.loc[ph_df["year"] == 2007, "pop"].iloc[0])
        checks.append(make_check("asia_2007_expected_pop", 3_811_953_827, indep_asia_pop, 0.0, indep_asia_pop == 3_811_953_827))
        checks.append(make_check("ph_2007_expected_pop", 91_077_287, ph_2007, 0.0, ph_2007 == 91_077_287))

    if audit_log is not None:
        for step, out_df in [("asia_selected_year", asia_df), ("country_history", ph_df), ("population_index", pop_idx_df)]:
            audit_log.append({
                "step": step, "source_file": "canonical", "operation": "analytics",
                "rule": f"year={reporting_year}", "rows_before": len(canonical_df), "rows_after": len(out_df),
            })

    return {
        "asia_selected_year": asia_df,
        "country_history": ph_df,
        "population_index": pop_idx_df,
        "numpy_info": numpy_info,
        "validation_checks": checks,
    }
