import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.validator import (  # noqa: E402
    DEFAULT_RULES,
    CANONICAL_COLUMNS,
    ConflictingKeyError,
    MissingColumnError,
    build_rules,
    check_conflicts,
    process_table,
    remove_duplicates,
    validate_record,
    validate_table,
)

RULES = build_rules({})  # defaults: 1952-2007 step 5, five continents, lifeExp <= 120


def raw(**overrides) -> dict:
    base = {"country": "Philippines", "continent": "Asia", "year": "2007",
            "lifeExp": "71.688", "pop": "91077287", "gdpPercap": "3190.481016"}
    base.update(overrides)
    return base


def frame(*records: dict) -> pd.DataFrame:
    return pd.DataFrame(list(records), columns=list(CANONICAL_COLUMNS))


class ValidateRecordTests(unittest.TestCase):

    def test_valid_record_is_typed_and_trimmed(self):
        clean, reason = validate_record(raw(country="  Philippines  ", continent=" Asia "), RULES)
        self.assertIsNone(reason)
        self.assertEqual(clean["country"], "Philippines")
        self.assertEqual(clean["continent"], "Asia")
        self.assertIsInstance(clean["year"], int)
        self.assertIsInstance(clean["pop"], int)
        self.assertEqual(clean["pop"], 91077287)
        self.assertAlmostEqual(clean["lifeExp"], 71.688, places=9)

    def test_whole_number_written_as_float_is_accepted(self):
        clean, reason = validate_record(raw(year="1997.0", pop="1000.0"), RULES)
        self.assertIsNone(reason)
        self.assertEqual((clean["year"], clean["pop"]), (1997, 1000))

    def test_unparseable_numbers(self):
        for field in ("year", "lifeExp", "pop", "gdpPercap"):
            with self.subTest(field=field):
                clean, reason = validate_record(raw(**{field: "abc"}), RULES)
                self.assertIsNone(clean)
                self.assertEqual(reason, f"unparseable_number:{field}")

    def test_fractional_year_and_population(self):
        self.assertEqual(validate_record(raw(year="1997.5"), RULES)[1], "fractional:year")
        self.assertEqual(validate_record(raw(pop="100.5"), RULES)[1], "fractional:pop")
        self.assertEqual(validate_record(raw(pop=100.5), RULES)[1], "fractional:pop")

    def test_non_finite_values(self):
        for text in ("inf", "-inf", "nan", "Infinity"):
            with self.subTest(text=text):
                self.assertEqual(validate_record(raw(lifeExp=text), RULES)[1], "non_finite:lifeExp")
        self.assertEqual(validate_record(raw(gdpPercap="1e999"), RULES)[1], "non_finite:gdpPercap")
        self.assertEqual(validate_record(raw(year="inf"), RULES)[1], "non_finite:year")

    def test_out_of_range_values(self):
        cases = {
            "out_of_range:pop": raw(pop="-1"),
            "out_of_range:year": raw(year="1900"),
            "out_of_range:lifeExp": raw(lifeExp="150"),
            "invalid_continent": raw(continent="Atlantis"),
            "out_of_range:gdpPercap": raw(gdpPercap="0"),
        }
        for expected, record in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(validate_record(record, RULES)[1], expected)
        self.assertEqual(validate_record(raw(pop="0"), RULES)[1], "out_of_range:pop")
        self.assertEqual(validate_record(raw(lifeExp="0"), RULES)[1], "out_of_range:lifeExp")
        # boundary: exactly 120 is allowed
        self.assertIsNone(validate_record(raw(lifeExp="120"), RULES)[1])
        # a year in range but not an allowed five-year step is rejected
        self.assertEqual(validate_record(raw(year="1953"), RULES)[1], "out_of_range:year")

    def test_empty_or_missing_values(self):
        self.assertEqual(validate_record(raw(country=""), RULES)[1], "missing_value:country")
        self.assertEqual(validate_record(raw(country="   "), RULES)[1], "missing_value:country")
        self.assertEqual(validate_record(raw(continent=None), RULES)[1], "missing_value:continent")
        self.assertEqual(validate_record(raw(pop=None), RULES)[1], "missing_value:pop")
        self.assertEqual(validate_record(raw(lifeExp=float("nan")), RULES)[1], "missing_value:lifeExp")

    def test_rules_come_from_config_not_code(self):
        """Changing the rules dict changes the outcome (no hard-coded answers)."""
        strict = build_rules({"allowed_years": [2007], "allowed_continents": ["Asia"], "life_exp_max": 70})
        self.assertEqual(validate_record(raw(year="1997"), strict)[1], "out_of_range:year")
        self.assertEqual(validate_record(raw(continent="Europe"), strict)[1], "invalid_continent")
        self.assertEqual(validate_record(raw(lifeExp="71.688"), strict)[1], "out_of_range:lifeExp")


class ValidateTableTests(unittest.TestCase):

    def test_source_record_is_one_based_and_not_renumbered(self):
        df = frame(
            raw(year="1952"),                  # record 1: valid
            raw(year="1957", pop="abc"),       # record 2: rejected
            raw(year="1962"),                  # record 3: valid
            raw(year="1967", lifeExp="500"),   # record 4: rejected
        )
        result = validate_table(df, "demo.csv", RULES)
        self.assertEqual([q["source_record"] for q in result.quarantine], [2, 4])
        self.assertEqual([c["source_record"] for c in result.clean], [1, 3])
        self.assertEqual(result.counts(), {"raw": 4, "rejected": 2, "duplicates_removed": 0, "clean": 2})

    def test_quarantine_keeps_original_values_and_columns(self):
        bad = raw(country="  Albania ", year="not-a-year", pop="100.5")
        result = validate_table(frame(bad), "demo.csv", RULES)
        q = result.quarantine_frame()
        self.assertEqual(
            list(q.columns),
            ["source_file", "source_record", "reason", *CANONICAL_COLUMNS],
        )
        row = q.iloc[0]
        self.assertEqual(row["source_file"], "demo.csv")
        self.assertEqual(row["source_record"], 1)
        self.assertEqual(row["reason"], "unparseable_number:year")
        self.assertEqual(row["country"], "  Albania ")       # NOT trimmed: original value
        self.assertEqual(row["year"], "not-a-year")
        self.assertEqual(row["pop"], "100.5")

    def test_index_is_ignored_and_input_not_modified(self):
        df = frame(raw(year="1952"), raw(year="1957", pop="x"))
        df.index = [10, 99]
        before = df.copy(deep=True)
        result = validate_table(df, "demo.csv", RULES)
        self.assertEqual(result.quarantine[0]["source_record"], 2)
        pd.testing.assert_frame_equal(df, before)

    def test_reader_supplied_source_record_is_used(self):
        df = frame(raw(year="1952", pop="oops"))
        df["source_record"] = [7]
        result = validate_table(df, "demo.csv", RULES)
        self.assertEqual(result.quarantine[0]["source_record"], 7)

    def test_missing_required_column_is_file_level_error(self):
        with self.assertRaises(MissingColumnError):
            validate_table(frame(raw()).drop(columns="pop"), "demo.csv", RULES)

    def test_non_string_inputs_from_json_style_readers(self):
        df = pd.DataFrame([{"country": "Philippines", "continent": "Asia", "year": 2007,
                            "lifeExp": 71.688, "pop": 91077287, "gdpPercap": 3190.48}])
        result = validate_table(df, "demo.json", RULES)
        self.assertEqual(len(result.clean), 1)
        self.assertEqual(result.clean[0]["pop"], 91077287)


class DuplicateTests(unittest.TestCase):

    def test_exact_duplicates_are_removed_and_logged(self):
        df = frame(raw(year="1952"), raw(year="1957"), raw(year="1952"), raw(year="1952"))
        result = process_table(df, "demo.csv", RULES)
        self.assertEqual(len(result.clean), 2)
        self.assertEqual(len(result.quarantine), 0)       # duplicates are not rejects
        self.assertEqual(len(result.duplicates), 2)
        self.assertEqual([d["source_record"] for d in result.duplicates], [3, 4])
        self.assertTrue(all(d["kept_source_record"] == 1 for d in result.duplicates))
        self.assertTrue(result.reconciles())

    def test_remove_duplicates_keeps_first_copy(self):
        recs = [dict(c, source_record=n) for n, c in
                ((1, validate_record(raw(), RULES)[0]), (2, validate_record(raw(), RULES)[0]))]
        unique, removed = remove_duplicates(recs, "demo.csv")
        self.assertEqual([u["source_record"] for u in unique], [1])
        self.assertEqual(removed[0]["source_record"], 2)

    def test_same_values_written_differently_are_still_exact_duplicates(self):
        df = frame(raw(pop="1000"), raw(pop="1000.0", country=" Philippines "))
        result = process_table(df, "demo.csv", RULES)
        self.assertEqual((len(result.clean), len(result.duplicates)), (1, 1))

    def test_duplicate_log_frame_columns(self):
        df = frame(raw(), raw())
        cols = list(process_table(df, "demo.csv", RULES).duplicates_frame().columns)
        self.assertEqual(cols[:3], ["source_file", "source_record", "kept_source_record"])
        self.assertEqual(cols[3:], list(CANONICAL_COLUMNS))


class ConflictTests(unittest.TestCase):

    def test_conflicting_keys_raise(self):
        df = frame(raw(), raw(pop="91077288"))
        with self.assertRaises(ConflictingKeyError) as ctx:
            process_table(df, "demo.csv", RULES)
        self.assertIn("Philippines", str(ctx.exception))

    def test_conflict_is_found_even_with_an_exact_duplicate_present(self):
        df = frame(raw(), raw(), raw(lifeExp="72.0"))
        with self.assertRaises(ConflictingKeyError):
            process_table(df, "demo.csv", RULES)

    def test_check_conflicts_accepts_distinct_keys(self):
        recs = [validate_record(raw(year=y), RULES)[0] | {"source_record": i}
                for i, y in enumerate(("1952", "1957"), start=1)]
        check_conflicts(recs)  # must not raise

    def test_invalid_row_sharing_a_key_is_quarantined_not_a_conflict(self):
        df = frame(raw(), raw(pop="-5"))
        result = process_table(df, "demo.csv", RULES)
        self.assertEqual(len(result.clean), 1)
        self.assertEqual(len(result.quarantine), 1)


class PipelineTests(unittest.TestCase):

    def test_reconciliation_raw_equals_rejected_plus_duplicates_plus_clean(self):
        df = frame(
            raw(country="Zambia", continent="Africa", year="1952"),
            raw(country="Albania", continent="Europe", year="1957"),
            raw(country="Albania", continent="Europe", year="1952"),
            raw(country="Albania", continent="Europe", year="1957"),   # exact duplicate
            raw(country="", year="1962"),                              # rejected
            raw(year="1997.5"),                                        # rejected
            raw(country="Peru", continent="Americas", year="1962"),
            raw(country="Peru", continent="Americas", year="1967"),
        )
        result = process_table(df, "demo.csv", RULES)
        self.assertEqual(result.counts(),
                         {"raw": 8, "rejected": 2, "duplicates_removed": 1, "clean": 5})
        self.assertTrue(result.reconciles())

    def test_sorted_by_country_then_year_with_canonical_types(self):
        df = frame(
            raw(country="Zambia", continent="Africa", year="1957"),
            raw(country="Albania", continent="Europe", year="1962"),
            raw(country="Albania", continent="Europe", year="1952"),
            raw(country="Zambia", continent="Africa", year="1952"),
        )
        clean = process_table(df, "demo.csv", RULES).clean_frame()
        self.assertEqual(list(clean.columns), list(CANONICAL_COLUMNS))
        self.assertEqual(list(zip(clean["country"], clean["year"])),
                         [("Albania", 1952), ("Albania", 1962), ("Zambia", 1952), ("Zambia", 1957)])
        self.assertEqual(str(clean["year"].dtype), "int64")
        self.assertEqual(str(clean["pop"].dtype), "int64")
        self.assertEqual(str(clean["lifeExp"].dtype), "float64")
        self.assertEqual(str(clean["country"].dtype), "string")

    def test_empty_result_still_has_schema(self):
        result = process_table(frame(raw(pop="abc")), "demo.csv", RULES)
        self.assertEqual(len(result.clean_frame()), 0)
        self.assertEqual(list(result.clean_frame().columns), list(CANONICAL_COLUMNS))

    def test_default_rules_are_sets(self):
        self.assertIsInstance(DEFAULT_RULES["allowed_years"], set)
        self.assertIsInstance(DEFAULT_RULES["allowed_continents"], set)


if __name__ == "__main__":
    unittest.main(verbosity=2)
