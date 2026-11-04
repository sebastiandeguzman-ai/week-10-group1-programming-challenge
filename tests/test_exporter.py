"""Automated unit tests for exports, round-trip reload, staging, and failure handling (Member 5)."""

import sys
from pathlib import Path

# Add project root directory to sys.path so 'src' can be imported reliably
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
import pandas as pd
from src.exporter import export_canonical_formats, reload_and_compare_exports, publish_staging_to_output


class TestExporterAndStaging(unittest.TestCase):

    def setUp(self):
        """Initializes isolated temporary workspace paths and baseline test dataset."""
        self.test_root = Path("test_temp_workspace")
        self.staging_dir = self.test_root / "staging"
        self.output_dir = self.test_root / "output"

        self.sample_df = pd.DataFrame([
            {"country": "Philippines", "continent": "Asia", "year": 1982, "lifeExp": 62.082, "pop": 53456774, "gdpPercap": 2600.5},
            {"country": "Philippines", "continent": "Asia", "year": 1987, "lifeExp": 64.151, "pop": 60017788, "gdpPercap": 2800.2},
        ])

    def tearDown(self):
        """Cleans up temporary files and directories generated during test execution."""
        if self.staging_dir.exists():
            for file_path in self.staging_dir.iterdir():
                file_path.unlink()
            self.staging_dir.rmdir()

        if self.output_dir.exists():
            for file_path in self.output_dir.iterdir():
                file_path.unlink()
            self.output_dir.rmdir()

        if self.test_root.exists():
            self.test_root.rmdir()

    def test_export_and_roundtrip_verification(self):
        """Verifies that all 4 formats export cleanly and pass round-trip reload comparisons."""
        export_canonical_formats(self.sample_df, self.staging_dir)
        all_passed, records = reload_and_compare_exports(self.sample_df, self.staging_dir)
        self.assertTrue(all_passed)
        self.assertEqual(len(records), 4)

    def test_staging_publish_isolation(self):
        """Verifies that verified files copy from staging to output directory."""
        export_canonical_formats(self.sample_df, self.staging_dir)
        publish_staging_to_output(self.staging_dir, self.output_dir)
        self.assertTrue((self.output_dir / "canonical.csv").is_file())
        self.assertTrue((self.output_dir / "canonical.xlsx").is_file())
        self.assertTrue((self.output_dir / "canonical.json").is_file())
        self.assertTrue((self.output_dir / "canonical.parquet").is_file())

    def test_corrupted_export_fails_verification(self):
        """Verifies that altered export file values fail round-trip validation."""
        export_canonical_formats(self.sample_df, self.staging_dir)
        csv_path = self.staging_dir / "canonical.csv"

        df_corrupt = pd.read_csv(csv_path)
        df_corrupt.loc[0, "gdpPercap"] = 999999.99
        df_corrupt.to_csv(csv_path, index=False)

        all_passed, records = reload_and_compare_exports(self.sample_df, self.staging_dir)
        self.assertFalse(all_passed)


if __name__ == "__main__":
    unittest.main()