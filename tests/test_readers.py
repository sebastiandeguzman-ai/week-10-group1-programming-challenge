
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

  
def json_record(country="Chad", year=1952):
    return {
        "identity": {"country": country, "continent": "Africa", "year": year},
        "measures": {"lifeExp": 38.1, "pop": 3000000, "gdpPercap": 1100.0},
    }
 
 
class TempDirTestCase(unittest.TestCase):
    """Gives each test a fresh temporary folder and small file writers."""
 
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
 
    def write_csv(self, name, text, encoding="cp1252") -> Path:
        path = self.tmp / name
        path.write_bytes(text.encode(encoding))
        return path
 
    def write_xlsx(self, name, sheets) -> Path:
        wb = Workbook()
        wb.remove(wb.active)
        for title, rows in sheets.items():
            ws = wb.create_sheet(title)
            for row in rows:
                ws.append(row)
        path = self.tmp / name
        wb.save(path)
        return path
 
    def write_json(self, name, payload) -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
 
 
class TestConfig(TempDirTestCase):
    """load_config, get_input_path and config validation."""
 
    def test_load_config_adds_config_dir(self) -> None:
        path = self.tmp / "config.json"
        path.write_text(json.dumps({"files": {"a": "a.csv"}}), encoding="utf-8")
        cfg = load_config(path)
        self.assertEqual(cfg["files"]["a"], "a.csv")
        self.assertEqual(Path(cfg["_config_dir"]), path.resolve().parent)
 
    def test_load_config_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_config(self.tmp / "nope.json")
 
    def test_load_config_invalid_json_and_non_object(self) -> None:
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "not valid JSON"):
            load_config(bad)
        lst = self.tmp / "list.json"
        lst.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "JSON object"):
            load_config(lst)
 
    def test_load_config_tolerates_utf8_bom(self) -> None:
        path = self.tmp / "bom.json"
        path.write_bytes(b"\xef\xbb\xbf" + b'{"files": {}}')
        self.assertEqual(load_config(path)["files"], {})
 
    def test_get_input_path_dict_layout(self) -> None:
        cfg = {"files": {"x": "data/a.csv"}, "_config_dir": str(self.tmp)}
        self.assertEqual(get_input_path(cfg, "x"), self.tmp / "data" / "a.csv")
        absolute = self.tmp / "abs.csv"
        cfg = {"files": {"x": str(absolute)}, "_config_dir": "/elsewhere"}
        self.assertEqual(get_input_path(cfg, "x"), absolute)
 
    def test_get_input_path_manifest_list_layout(self) -> None:
        cfg = {"files": [{"file": "country_records.csv"}], "_config_dir": str(self.tmp)}
        self.assertEqual(
            get_input_path(cfg, "country_records.csv"), self.tmp / "country_records.csv"
        )
 
    def test_get_input_path_unknown_name(self) -> None:
        with self.assertRaisesRegex(ConfigError, "no entry"):
            get_input_path({"files": {"a": "a.csv"}}, "b")
        with self.assertRaisesRegex(ConfigError, "no entry"):
            get_input_path({"files": [{"file": "a.csv"}]}, "b.csv")
 
    def test_files_section_must_be_object_or_list(self) -> None:
        with self.assertRaisesRegex(ConfigError, "JSON object"):
            get_input_path({"files": "a.csv"}, "a")
 
    def test_malformed_sections_rejected(self) -> None:
        path = self.write_csv("a.csv", f"{HEADER}\nChad;Africa;1952;1;2;3\n")
        for bad in (
            {"formats": []},
            {"formats": {"csv": "utf-8"}},
            {"column_mappings": {"csv": []}},
            {"column_mappings": {"csv": {"x": "notAColumn"}}},
        ):
            with self.subTest(config=bad):
                with self.assertRaises(ConfigError):
                    read_csv_records(path, bad)
 
    def test_exception_hierarchy(self) -> None:
        for exc in (ConfigError, UnsupportedFormatError, InvalidFileError, MissingColumnError):
            self.assertTrue(issubclass(exc, ReaderError))
        self.assertTrue(issubclass(MissingColumnError, ValueError))
 
 
class TestCsvReader(TempDirTestCase):
    """Comment stripping, mapping, source_record, uncast strings, errors."""
 
    def test_sample_file(self) -> None:
        df = read_csv_records(self.write_csv("s.csv", CSV_TEXT), CSV_CONFIG)
        self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
        self.assertEqual(list(df["country"]), ["Côte d'Ivoire", "Brazil", "Japan", "Chad"])
        self.assertEqual(list(df[SOURCE_RECORD_COLUMN]), [1, 2, 3, 4])
        self.assertEqual(str(df[SOURCE_RECORD_COLUMN].dtype), "int64")
 
    def test_values_are_uncast_strings(self) -> None:
        df = read_csv_records(self.write_csv("s.csv", CSV_TEXT), CSV_CONFIG)
        self.assertEqual(df["year"].iloc[1], "2007")
        self.assertIsInstance(df["year"].iloc[1], str)
        self.assertEqual(df["pop"].iloc[1], "190010647")
        self.assertEqual(df["lifeExp"].iloc[3], "")  # empty stays ""
 
    def test_extra_columns_dropped(self) -> None:
        df = read_csv_records(self.write_csv("s.csv", CSV_TEXT), CSV_CONFIG)
        self.assertNotIn("export_note", df.columns)
 
    def test_header_matching_ignores_case_and_whitespace(self) -> None:
        text = " COUNTRY ;Continent;YEAR;Life  Expectancy;Pop;GdpPercap\nChad;Africa;1952;38.1;3;4\n"
        cfg = {"column_mappings": {"csv": {"life expectancy": "lifeExp"}}}
        df = read_csv_records(self.write_csv("a.csv", text), cfg)
        self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
 
    def test_flat_mapping_applies_to_csv(self) -> None:
        text = "country;continent;year;le;pop;gdpPercap\nChad;Africa;1952;38.1;3;4\n"
        cfg = {"column_mappings": {"le": "lifeExp"}}
        df = read_csv_records(self.write_csv("a.csv", text), cfg)
        self.assertEqual(df["lifeExp"].iloc[0], "38.1")
 
    def test_custom_settings(self) -> None:
        text = "// note\ncountry,continent,year,lifeExp,pop,gdpPercap\nCôte,Africa,2007,1,2,3\n"
        cfg = {"formats": {"csv": {"encoding": "utf-8", "delimiter": ",", "comment_prefix": "//"}}}
        df = read_csv_records(self.write_csv("a.csv", text, "utf-8"), cfg)
        self.assertEqual(df["country"].iloc[0], "Côte")
 
    def test_bom_removed(self) -> None:
        body = f"{HEADER}\nChad;Africa;1952;1;2;3\n"
        for encoding in ("utf-8", "cp1252"):
            with self.subTest(encoding=encoding):
                path = self.tmp / f"bom_{encoding}.csv"
                path.write_bytes(b"\xef\xbb\xbf" + body.encode(encoding))
                df = read_csv_records(path, {"formats": {"csv": {"encoding": encoding}}})
                self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
 
    def test_crlf_and_whitespace_rows(self) -> None:
        text = f"# c\r\n{HEADER}\r\nChad;Africa;1952;1;2;3\r\n  ;  ;  ;  ;  ;  \r\nJapan;Asia;2007;1;2;3\r\n"
        df = read_csv_records(self.write_csv("a.csv", text), {})
        self.assertEqual(list(df[SOURCE_RECORD_COLUMN]), [1, 2])
 
    def test_values_not_stripped(self) -> None:
        df = read_csv_records(self.write_csv("a.csv", f"{HEADER}\n Chad ;Africa;1952;1;2;3\n"), {})
        self.assertEqual(df["country"].iloc[0], " Chad ")
 
    def test_missing_column(self) -> None:
        text = "country;continent;year;lifeExp;gdpPercap\nChad;Africa;1952;1;3\n"
        with self.assertRaisesRegex(MissingColumnError, "pop"):
            read_csv_records(self.write_csv("a.csv", text), {})
 
    def test_duplicate_mapping_target(self) -> None:
        text = "country;continent;year;lifeExp;le;pop;gdpPercap\nChad;Africa;1952;1;2;3;4\n"
        cfg = {"column_mappings": {"csv": {"le": "lifeExp"}}}
        with self.assertRaisesRegex(InvalidFileError, "lifeExp"):
            read_csv_records(self.write_csv("a.csv", text), cfg)
 
    def test_undecodable_and_unknown_encoding(self) -> None:
        path = self.write_csv("a.csv", f"{HEADER}\nCôte;Africa;1;2;3;4\n")
        with self.assertRaises(InvalidFileError):
            read_csv_records(path, {"formats": {"csv": {"encoding": "utf-8"}}})
        with self.assertRaises(ConfigError):
            read_csv_records(path, {"formats": {"csv": {"encoding": "no-such-codec"}}})
 
    def test_only_comments_raises_invalid_file(self) -> None:
        with self.assertRaises(InvalidFileError):
            read_csv_records(self.write_csv("a.csv", "# only\n# comments\n"), {})
 
    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_csv_records(self.tmp / "missing.csv", {})
 
 
class TestExcelReader(TempDirTestCase):
    """Sheet selection, native types, mapping, errors."""
 
    def make(self, name="a.xlsx", sheets=None) -> Path:
        sheets = sheets or {
            "Readme": [["Readme"], ["not data"]],
            "observations": [XLSX_HEADER, *XLSX_ROWS],
        }
        return self.write_xlsx(name, sheets)
 
    def test_sample_file(self) -> None:
        df = read_excel_records(self.make(), XLSX_CONFIG)
        self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
        self.assertEqual(list(df["country"]), ["Côte d'Ivoire", "Brazil", "Chad"])
        self.assertEqual(list(df[SOURCE_RECORD_COLUMN]), [1, 2, 3])
 
    def test_native_types_preserved(self) -> None:
        row = read_excel_records(self.make(), XLSX_CONFIG).iloc[0]
        self.assertIsInstance(row["year"], int)
        self.assertIsInstance(row["lifeExp"], float)
        self.assertIsInstance(row["pop"], int)
        self.assertEqual(row["gdpPercap"], 1800.5)
 
    def test_empty_cell_is_missing(self) -> None:
        df = read_excel_records(self.make(), XLSX_CONFIG)
        self.assertTrue(pd.isna(df["lifeExp"].iloc[2]))
 
    def test_sheet_selection(self) -> None:
        one = [XLSX_HEADER, XLSX_ROWS[0]]
        cases = {
            "order": ({"observations": one, "Readme": [["x"]]}, XLSX_CONFIG),
            "case": ({"README": [["x"]], "Observations": one, "Other": [["y"]]}, XLSX_CONFIG),
            "only_remaining": ({"Readme": [["x"]], "Sheet1": one}, XLSX_CONFIG),
        }
        for label, (sheets, cfg) in cases.items():
            with self.subTest(case=label):
                df = read_excel_records(self.make(f"{label}.xlsx", sheets), cfg)
                self.assertEqual(len(df), 1)
 
    def test_configured_sheet_and_string_skip(self) -> None:
        sheets = {"Notes": [["x"]], "data": [XLSX_HEADER, XLSX_ROWS[0]], "other": [["y"]]}
        cfg = {
            "formats": {"excel": {"sheet_name": "data", "skip_sheets": "Notes"}},
            "column_mappings": {"excel": {"GDP per capita": "gdpPercap"}},
        }
        self.assertEqual(len(read_excel_records(self.make("c.xlsx", sheets), cfg)), 1)
 
    def test_ambiguous_or_only_skipped_sheets(self) -> None:
        one = [XLSX_HEADER, XLSX_ROWS[0]]
        for sheets in ({"A": one, "B": one}, {"Readme": [["x"]]}):
            with self.subTest(sheets=list(sheets)):
                with self.assertRaises(InvalidFileError):
                    read_excel_records(self.make("amb.xlsx", sheets), XLSX_CONFIG)
 
    def test_missing_column(self) -> None:
        path = self.make("m.xlsx", {"observations": [["country", "continent", "year"], ["Chad", "Africa", 1952]]})
        with self.assertRaisesRegex(MissingColumnError, "lifeExp"):
            read_excel_records(path, {})
 
    def test_extra_and_blank_headers_tolerated(self) -> None:
        header = XLSX_HEADER + [None, "notes"]
        row = XLSX_ROWS[0] + [None, "hello"]
        df = read_excel_records(self.make("e.xlsx", {"observations": [header, row]}), XLSX_CONFIG)
        self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
 
    def test_corrupt_workbook(self) -> None:
        bad = self.tmp / "bad.xlsx"
        bad.write_bytes(b"this is not a zip archive")
        with self.assertRaises(InvalidFileError):
            read_excel_records(bad, {})
 
    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_excel_records(self.tmp / "missing.xlsx", {})
 
 
class TestJsonReader(TempDirTestCase):
    """Nested identity/measures records, record_path, errors."""
 
    def test_nested_records_flattened_and_mapped(self) -> None:
        payload = {"metadata": {"note": "not a record"},
                   "records": [json_record("Chad", 1952), json_record("Japan", 2007)]}
        df = read_json_records(self.write_json("a.json", payload), JSON_CONFIG)
        self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
        self.assertEqual(list(df["country"]), ["Chad", "Japan"])
        self.assertEqual(list(df[SOURCE_RECORD_COLUMN]), [1, 2])
 
    def test_native_types_preserved(self) -> None:
        df = read_json_records(self.write_json("a.json", {"records": [json_record()]}), JSON_CONFIG)
        self.assertEqual(df["year"].iloc[0], 1952)
        self.assertEqual(df["lifeExp"].iloc[0], 38.1)
 
    def test_custom_record_path(self) -> None:
        payload = {"data": {"rows": [json_record()]}}
        cfg = {**JSON_CONFIG, "formats": {"json": {"record_path": "data.rows"}}}
        self.assertEqual(len(read_json_records(self.write_json("a.json", payload), cfg)), 1)
 
    def test_flat_records_without_sections(self) -> None:
        flat = {"country": "Chad", "continent": "Africa", "year": 1952,
                "lifeExp": 38.1, "pop": 3, "gdpPercap": 4.0}
        df = read_json_records(self.write_json("a.json", {"records": [flat]}), {})
        self.assertEqual(df["country"].iloc[0], "Chad")
 
    def test_error_cases(self) -> None:
        bad_text = self.tmp / "bad.json"
        bad_text.write_text("{nope", encoding="utf-8")
        cases = {
            "invalid_json": bad_text,
            "missing_path": self.write_json("p.json", {"other": []}),
            "empty_records": self.write_json("e.json", {"records": []}),
            "non_object_record": self.write_json("n.json", {"records": [1, 2]}),
            "string_records": self.write_json("s.json", {"records": "abc"}),
        }
        for label, path in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(InvalidFileError):
                    read_json_records(path, JSON_CONFIG)
 
    def test_missing_column(self) -> None:
        record = json_record()
        del record["measures"]["pop"]
        with self.assertRaisesRegex(MissingColumnError, "pop"):
            read_json_records(self.write_json("a.json", {"records": [record]}), JSON_CONFIG)
 
    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_json_records(self.tmp / "missing.json", {})
 
 @unittest.skipUnless(HAS_PYARROW, "pyarrow is not installed")
class TestParquetReader(TempDirTestCase):
    """String-typed parquet columns mapped to canonical names."""
 
    CONFIG = {"column_mappings": {"parquet": {
        "COUNTRY": "country", "CONTINENT": "continent", "YEAR": "year",
        "LIFE_EXP": "lifeExp", "POPULATION": "pop", "GDP_PER_CAPITA": "gdpPercap"}}}
 
    def test_reads_and_maps(self) -> None:
        raw = pd.DataFrame({
            "COUNTRY": ["Chad", "Japan"], "CONTINENT": ["Africa", "Asia"],
            "YEAR": ["1952", "2007"], "LIFE_EXP": ["38.1", "82.6"],
            "POPULATION": ["3000000", "127467972"], "GDP_PER_CAPITA": ["1100", "31656.1"],
        })
        path = self.tmp / "a.parquet"
        raw.to_parquet(path)
        df = read_parquet_records(path, self.CONFIG)
        self.assertEqual(list(df.columns), EXPECTED_COLUMNS)
        self.assertEqual(df["year"].iloc[0], "1952")  # not cast
        self.assertEqual(list(df[SOURCE_RECORD_COLUMN]), [1, 2])
 
    def test_corrupt_and_missing(self) -> None:
        bad = self.tmp / "bad.parquet"
        bad.write_bytes(b"not parquet")
        with self.assertRaises(InvalidFileError):
            read_parquet_records(bad, {})
        with self.assertRaises(FileNotFoundError):
            read_parquet_records(self.tmp / "missing.parquet", {})
 
 
class TestManifestLayout(TempDirTestCase):
    """A manifest entry overrides formats / mappings for its own file only."""
 
    def test_entry_overrides_global_settings(self) -> None:
        text = "# c\nA,B,C,D,E,F\nChad,Africa,1952,38.1,3,4\n"
        path = self.write_csv("listed.csv", text.replace(",", ";"))
        cfg = {
            "formats": {"csv": {"encoding": "utf-8", "delimiter": ","}},  # would break listed.csv
            "files": [{
                "file": "listed.csv", "encoding": "cp1252", "separator": ";",
                "comment_prefix": "#",
                "source_to_canonical": dict(zip("ABCDEF", CANONICAL_COLUMNS)),
            }],
        }
        df = read_csv_records(path, cfg)
        self.assertEqual(df["country"].iloc[0], "Chad")
 
    def test_unlisted_file_uses_global_formats(self) -> None:
        text = "country,continent,year,lifeExp,pop,gdpPercap\nChad,Africa,1952,1,2,3\n"
        path = self.write_csv("other.csv", text, "utf-8")
        cfg = {
            "formats": {"csv": {"encoding": "utf-8", "delimiter": ",", "comment_prefix": ""}},
            "files": [{"file": "listed.csv", "separator": ";"}],
        }
        self.assertEqual(len(read_csv_records(path, cfg)), 1)
 
    def test_bad_source_to_canonical(self) -> None:
        path = self.write_csv("listed.csv", f"{HEADER}\nChad;Africa;1952;1;2;3\n")
        for value in ({"x": "notAColumn"}, ["x"]):
            with self.subTest(value=value):
                cfg = {"files": [{"file": "listed.csv", "source_to_canonical": value}]}
                with self.assertRaises(ConfigError):
                    read_csv_records(path, cfg)
 
 
class TestDispatch(TempDirTestCase):
    """read_file_by_format and register_reader."""
 
    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.dict(rce._READERS, clear=False)  # restored after each test
        patcher.start()
        self.addCleanup(patcher.stop)
 
    def test_dispatch_by_extension(self) -> None:
        csv_path = self.write_csv("a.csv", CSV_TEXT)
        xlsx_path = self.write_xlsx("a.xlsx", {"observations": [XLSX_HEADER, XLSX_ROWS[0]]})
        json_path = self.write_json("a.json", {"records": [json_record()]})
        self.assertEqual(len(read_file_by_format(csv_path, CSV_CONFIG)), 4)
        self.assertEqual(len(read_file_by_format(xlsx_path, XLSX_CONFIG)), 1)
        self.assertEqual(len(read_file_by_format(json_path, JSON_CONFIG)), 1)
 
    def test_extension_case_insensitive(self) -> None:
        upper = self.write_csv("UPPER.CSV", CSV_TEXT)
        self.assertEqual(len(read_file_by_format(upper, CSV_CONFIG)), 4)
 
    def test_unsupported_extensions(self) -> None:
        for name in ("a.txt", "a.docx", "noextension"):
            with self.subTest(name=name):
                path = self.tmp / name
                path.write_text("x", encoding="utf-8")
                with self.assertRaisesRegex(UnsupportedFormatError, "Unsupported file extension"):
                    read_file_by_format(path, {})
 
    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_file_by_format(self.tmp / "missing.csv", {})
 
    def test_unregistered_supported_extension(self) -> None:
        del rce._READERS[".json"]
        path = self.write_json("a.json", {"records": []})
        with self.assertRaisesRegex(UnsupportedFormatError, "No reader registered"):
            read_file_by_format(path, {})
 
    def test_register_reader(self) -> None:
        register_reader(".JSON", lambda p, c: pd.DataFrame({"replaced": [True]}))
        path = self.write_json("a.json", {"records": []})
        self.assertIn("replaced", read_file_by_format(path, {}).columns)
 
    def test_register_reader_rejects_unknown_extension(self) -> None:
        with self.assertRaises(ValueError):
            register_reader(".txt", lambda p, c: pd.DataFrame())