"""
Unit tests for analytics.py 
Uses a hardcoded 12-row clean Gapminder DataFrame isolated from readers and validator.
"""

from pathlib import Path
import sys
import unittest
import numpy as np
import pandas as pd

# Point to the root folder where 'src' now lives
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analytics import (
    CANONICAL_COLS,
    build_asia_selected_year,
    build_country_history,
    build_population_index_matrix,
    compute_independent_asia_pop,
    verify_four_format_agreement,
)

class TestAnalytics(unittest.TestCase):
    """Test suite for pandas .loc analysis, NumPy 3x6 broadcasting, 4-format agreement, and missing keys."""

    def setUp(self) -> None:
        """Hardcode a clean 12-row Gapminder DataFrame from the actual dataset."""
        self.df = pd.DataFrame(
            [
                # Philippines across all 6 matrix years (1982-2007)
                ["Philippines", "Asia", 1982, 62.082, 53456774, 2603.273765],
                ["Philippines", "Asia", 1987, 64.151, 60017788, 2189.634995],
                ["Philippines", "Asia", 1992, 66.458, 67185766, 2279.324017],
                ["Philippines", "Asia", 1997, 68.564, 75012988, 2536.534925],
                ["Philippines", "Asia", 2002, 70.303, 82995088, 2650.921068],
                ["Philippines", "Asia", 2007, 71.688, 91077287, 3190.481016],
                # Indonesia (1982, 1997, 2007)
                ["Indonesia", "Asia", 1982, 56.359, 154942000, 1516.872988],
                ["Indonesia", "Asia", 1997, 66.041, 201356000, 3119.335603],
                ["Indonesia", "Asia", 2007, 70.650, 225878000, 3540.651564],
                # Thailand (1982, 1997, 2007 - tied lifeExp in 2007 at 70.650 to test method="min")
                ["Thailand", "Asia", 1982, 64.597, 48827160, 2393.219781],
                ["Thailand", "Asia", 1997, 67.500, 60216677, 5852.625497],
                ["Thailand", "Asia", 2007, 70.650, 65068149, 7458.396327],
            ],
            columns=CANONICAL_COLS,
        )

    def test_asia_selected_year_and_independent_pop(self) -> None:
        """Test .loc filtering, descending rank (method='min'), and independent Asian pop sum."""
        res_2007 = build_asia_selected_year(self.df, reporting_year=2007)
        self.assertEqual(list(res_2007["country"]), ["Philippines", "Indonesia", "Thailand"])
        self.assertEqual(list(res_2007["lifeExp_rank"]), [1, 2, 2])
        self.assertAlmostEqual(res_2007.loc[0, "pop_millions"], 91.077287, places=6)

        indep_pop = compute_independent_asia_pop(self.df, reporting_year=2007)
        self.assertEqual(indep_pop, int(res_2007["pop"].sum()))

        # Test dynamic reporting_year change to 1997
        res_1997 = build_asia_selected_year(self.df, reporting_year=1997)
        self.assertEqual(list(res_1997["country"]), ["Philippines", "Thailand", "Indonesia"])

    def test_country_history(self) -> None:
        """Test Philippine trend sorting, pop_millions, and lifeExp_change from first observed year."""
        ph = build_country_history(self.df, country="Philippines")
        self.assertEqual(len(ph), 6)
        self.assertEqual(list(ph["year"]), [1982, 1987, 1992, 1997, 2002, 2007])
        self.assertAlmostEqual(ph.loc[0, "lifeExp_change"], 0.0)
        self.assertAlmostEqual(ph.loc[5, "lifeExp_change"], 71.688 - 62.082, places=6)

    def test_numpy_broadcast_matrix_and_loop(self) -> None:
        """Test 3x6 NumPy broadcasting (1982=100), pre/post shapes, and loop agreement."""
        extra_rows = pd.DataFrame(
            [
                ["Indonesia", "Asia", 1987, 60.137, 171041000, 1748.356961],
                ["Indonesia", "Asia", 1992, 62.681, 186743000, 2383.140898],
                ["Indonesia", "Asia", 2002, 68.588, 213261000, 2873.912870],
                ["Thailand", "Asia", 1987, 66.084, 52910342, 2982.653773],
                ["Thailand", "Asia", 1992, 67.298, 56667095, 4616.896545],
                ["Thailand", "Asia", 2002, 68.564, 62806748, 5913.187529],
            ],
            columns=CANONICAL_COLS,
        )
        full_3x6_df = pd.concat([self.df, extra_rows], ignore_index=True)

        idx_df, info = build_population_index_matrix(full_3x6_df)
        self.assertEqual(info["shape_before"], ((3, 6), (3, 1)))
        self.assertEqual(info["shape_after"], (3, 6))
        self.assertLessEqual(info["max_loop_diff"], 1e-8)
        np.testing.assert_allclose(idx_df["1982"], [100.0, 100.0, 100.0], rtol=0, atol=1e-8)
        self.assertAlmostEqual(idx_df.loc[0, "2007"], (91077287 / 53456774) * 100.0, places=6)

    def test_four_format_agreement(self) -> None:
        """Test 4-format canonical agreement with reordered rows and 1e-8 float tolerance."""
        f1 = self.df.copy()
        f2 = self.df.iloc[::-1].reset_index(drop=True)
        f3 = self.df.sample(frac=1.0, random_state=1).reset_index(drop=True)
        f4 = self.df.copy()
        f4.loc[:, "lifeExp"] += 1e-9  # Within 1e-8 tolerance

        canon, checks = verify_four_format_agreement({"csv": f1, "xlsx": f2, "json": f3, "parquet": f4})
        self.assertEqual(len(canon), 12)
        self.assertTrue(all(c["pass"] for c in checks))

        # Float error beyond 1e-8 must fail
        f4_bad = self.df.copy()
        f4_bad.loc[0, "gdpPercap"] += 1e-4
        with self.assertRaises(ValueError):
            verify_four_format_agreement([f1, f2, f3, f4_bad])

    def test_missing_keys_raise_error(self) -> None:
        """Test that missing/empty keys or missing matrix years raise ValueError."""
        bad_df = self.df.copy()
        bad_df.loc[0, "country"] = ""
        with self.assertRaises(ValueError):
            verify_four_format_agreement([self.df, bad_df])

        # Default 3x6 matrix expects 1987, 1992, 2002 for all 3 countries, missing in 12-row df
        with self.assertRaises(ValueError):
            build_population_index_matrix(self.df)

if __name__ == "__main__":
    unittest.main()