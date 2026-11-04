"""Automated unit tests for exports, round-trip reload, staging, and failure handling (Member 5)."""

from pathlib import Path
import unittest
import pandas as pd
from dsa4153_project.src.exporter import export_canonical_formats, reload_and_compare_exports, publish_staging_to_output

class TestExporterAndStaging(unittest.TestCase):

    def setUp(self):
        """Initializes isolated temporary workspace paths and baseline test dataset."""
        # Define relative workspace folder paths using pathlib.Path
        self.test_root = Path("test_temp_workspace")
        self.staging_dir = self.test_root / "staging"
        self.output_dir = self.test_root / "output"

        # Construct minimal valid sample DataFrame conforming to canonical schema
        self.sample_df = pd.DataFrame([
            {"country": "Philippines", "continent": "Asia", "year": 1982, "lifeExp": 62.082, "pop": 53456774, "gdpPercap": 2600.5},
            {"country": "Philippines", "continent": "Asia", "year": 1987, "lifeExp": 64.151, "pop": 60017788, "gdpPercap": 2800.2},
        ])

    def tearDown(self):
        """Cleans up temporary files and directories generated during test execution."""
        # Unlink files inside staging directory before removing folder
        if self.staging_dir.exists():
            for file_path in self.staging_dir.iterdir():
                file_path.unlink()
            self.staging_dir.rmdir()

        # Unlink files inside output directory before removing folder
        if self.output_dir.exists():
            for file_path in self.output_dir.iterdir():
                file_path.unlink()
            self.output_dir.rmdir()

        # Remove root temporary workspace folder
        if self.test_root.exists():
            self.test_root.rmdir()

def test_export_and_roundtrip_verification(self):
        """Verifies that all 4 formats export cleanly and pass round-trip reload comparisons."""
        # Execute multi-format export into staging directory
        export_canonical_formats(self.sample_df, self.staging_dir)

        # Reload all four formats and assert frame equality against pre-export sample data
        all_passed, records = reload_and_compare_exports(self.sample_df, self.staging_dir)

        # Assert round-trip validation overall status is True
        self.assertTrue(all_passed)

        # Assert validation records were generated for all 4 export formats
        self.assertEqual(len(records), 4)