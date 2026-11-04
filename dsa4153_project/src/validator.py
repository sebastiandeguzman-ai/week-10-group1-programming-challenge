"""Row validation, quarantine, duplicate removal and conflict detection."""

from __future__ import annotations

import math
import numbers
from decimal import Decimal, InvalidOperation

import pandas as pd

CANONICAL_COLUMNS: tuple[str, ...] = (
    "country", "continent", "year", "lifeExp", "pop", "gdpPercap",
)
TEXT_FIELDS: tuple[str, ...] = ("country", "continent")
INT_FIELDS: tuple[str, ...] = ("year", "pop")
FLOAT_FIELDS: tuple[str, ...] = ("lifeExp", "gdpPercap")
KEY_FIELDS: tuple[str, ...] = ("country", "year")
SCHEMA: dict[str, str] = {
    "country": "string", "continent": "string", "year": "int64",
    "lifeExp": "float64", "pop": "int64", "gdpPercap": "float64",
}

# Fallback rule values. Real runs build the rules from manifest.json.
DEFAULT_RULES: dict = {
    "allowed_continents": {"Africa", "Americas", "Asia", "Europe", "Oceania"},
    "allowed_years": set(range(1952, 2008, 5)),
    "life_exp_max": 120.0,
}


class ConflictingKeyError(Exception):
    

class MissingColumnError(ValueError):


class ValidationResult:

    def __init__(self, source_file: str) -> None:
        self.source_file: str = source_file
        self.raw_count: int = 0
        self.clean: list[dict] = []        # valid records (typed values)
        self.quarantine: list[dict] = []   # rejected records (original values)
        self.duplicates: list[dict] = []   # removed exact duplicate copies

    def add_quarantine(self, source_record: int, reason: str, original: dict) -> None:
        entry = {
            "source_file": self.source_file,
            "source_record": source_record,
            "reason": reason,
        }
        entry.update({col: _original_text(original.get(col)) for col in CANONICAL_COLUMNS})
        self.quarantine.append(entry)

    def counts(self) -> dict[str, int]:
        return {
            "raw": self.raw_count,
            "rejected": len(self.quarantine),
            "duplicates_removed": len(self.duplicates),
            "clean": len(self.clean),
        }

    def reconciles(self) -> bool:
        c = self.counts()
        return c["raw"] == c["rejected"] + c["duplicates_removed"] + c["clean"]

    def clean_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(
            [{col: rec[col] for col in CANONICAL_COLUMNS} for rec in self.clean],
            columns=list(CANONICAL_COLUMNS),
        )
        return frame.astype(SCHEMA).reset_index(drop=True)

    def quarantine_frame(self) -> pd.DataFrame:
        columns = ["source_file", "source_record", "reason", *CANONICAL_COLUMNS]
        return pd.DataFrame(self.quarantine, columns=columns)

    def duplicates_frame(self) -> pd.DataFrame:
        columns = ["source_file", "source_record", "kept_source_record", *CANONICAL_COLUMNS]
        return pd.DataFrame(self.duplicates, columns=columns)


# ----------------------------------------------------------------- rules --

def build_rules(manifest: dict) -> dict:
    rules = {
        "allowed_continents": set(manifest.get("allowed_continents", DEFAULT_RULES["allowed_continents"])),
        "allowed_years": {int(y) for y in manifest.get("allowed_years", DEFAULT_RULES["allowed_years"])},
        "life_exp_max": float(manifest.get("life_exp_max", DEFAULT_RULES["life_exp_max"])),
    }
    return rules


# --------------------------------------------------------------- helpers --

def _is_missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _original_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) and _is_missing(value):
        return ""
    return str(value)


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not a number")
    if isinstance(value, str):
        text = value.strip()
        if "_" in text:  # Python would accept '1_000'; a data file should not
            raise ValueError("underscore in number")
        try:
            return Decimal(text)
        except InvalidOperation as error:
            raise ValueError(f"cannot parse {value!r}") from error
    if isinstance(value, numbers.Integral):
        return Decimal(int(value))
    if isinstance(value, numbers.Real):
        return Decimal(repr(float(value)))
    raise ValueError(f"unsupported type {type(value).__name__}")


def _parse_number(field: str, value: object) -> tuple[Decimal | None, str | None]:
    if _is_missing(value):
        return None, f"missing_value:{field}"
    try:
        number = _to_decimal(value)
    except ValueError:
        return None, f"unparseable_number:{field}"
    if not number.is_finite():
        return None, f"non_finite:{field}"
    return number, None


# ------------------------------------------------------------ validation --

def validate_record(raw: dict, rules: dict) -> tuple[dict | None, str | None]:
    clean: dict = {}

    # text fields: trim, then reject empty
    for field in TEXT_FIELDS:
        value = raw.get(field)
        if _is_missing(value):
            return None, f"missing_value:{field}"
        clean[field] = str(value).strip()
    if clean["continent"] not in rules["allowed_continents"]:
        return None, "invalid_continent"

    # numeric fields, in canonical order
    for field in CANONICAL_COLUMNS[2:]:
        number, reason = _parse_number(field, raw.get(field))
        if reason:
            return None, reason

        if field in INT_FIELDS:
            if number != number.to_integral_value():      # e.g. 1997.5, 100.5
                return None, f"fractional:{field}"
            as_int = int(number)                           # safe: whole number
            if field == "year" and as_int not in rules["allowed_years"]:
                return None, "out_of_range:year"
            if field == "pop" and as_int <= 0:
                return None, "out_of_range:pop"
            clean[field] = as_int
        else:
            as_float = float(number)
            if not math.isfinite(as_float):                # e.g. 1e999 overflow
                return None, f"non_finite:{field}"
            if field == "lifeExp" and not 0 < as_float <= rules["life_exp_max"]:
                return None, "out_of_range:lifeExp"
            if field == "gdpPercap" and as_float <= 0:
                return None, "out_of_range:gdpPercap"
            clean[field] = as_float

    return clean, None


def validate_table(df: pd.DataFrame, source_file: str, rules: dict) -> ValidationResult:
    missing = set(CANONICAL_COLUMNS) - set(df.columns)   # set difference
    if missing:
        raise MissingColumnError(f"{source_file}: missing required columns {sorted(missing)}")

    result = ValidationResult(source_file)
    result.raw_count = len(df)
    has_positions = "source_record" in df.columns

    for position, row in enumerate(df.to_dict("records"), start=1):
        source_record = int(row["source_record"]) if has_positions else position
        clean, reason = validate_record(row, rules)
        if reason:
            result.add_quarantine(source_record, reason, row)
        else:
            clean["source_record"] = source_record
            result.clean.append(clean)
    return result


# ------------------------------------------------- duplicates / conflicts --

def _values(record: dict) -> tuple:
    return tuple(record[col] for col in CANONICAL_COLUMNS)


def remove_duplicates(clean: list[dict], source_file: str) -> tuple[list[dict], list[dict]]:
    first_seen: dict[tuple, int] = {}
    seen: set[tuple] = set()
    unique: list[dict] = []
    removed: list[dict] = []
    for record in clean:
        values = _values(record)
        if values in seen:
            entry = {
                "source_file": source_file,
                "source_record": record["source_record"],
                "kept_source_record": first_seen[values],
            }
            entry.update(dict(zip(CANONICAL_COLUMNS, values)))
            removed.append(entry)
        else:
            seen.add(values)
            first_seen[values] = record["source_record"]
            unique.append(record)
    return unique, removed


def check_conflicts(clean: list[dict]) -> None:
    by_key: dict[tuple, dict] = {}
    for record in clean:
        key = (record["country"], record["year"])
        earlier = by_key.get(key)
        if earlier is None:
            by_key[key] = record
        elif _values(earlier) != _values(record):
            raise ConflictingKeyError(
                f"Conflicting key {key}: source records "
                f"{earlier['source_record']} and {record['source_record']} disagree "
                f"({_values(earlier)} vs {_values(record)})"
            )


def sort_records(clean: list[dict]) -> list[dict]:
    return sorted(clean, key=lambda rec: (rec["country"], rec["year"]))


# -------------------------------------------------------------- pipeline --

def process_table(df: pd.DataFrame, source_file: str, rules: dict) -> ValidationResult:
    result = validate_table(df, source_file, rules)
    unique, removed = remove_duplicates(result.clean, source_file)
    check_conflicts(unique)          # stops the run; never keeps "the first row"
    result.clean = sort_records(unique)
    result.duplicates = removed
    return result
