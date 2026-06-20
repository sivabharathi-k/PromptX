"""
Unit tests for the aggregation engine in visualization_preparation_service.py.

Tests cover all 6 aggregation types (sum, avg, count, min, max, median) against:
  - Integers, decimals, negative numbers
  - Null / empty / NaN values
  - Mixed valid + invalid data
  - Grouped (multi-category) datasets
  - Large datasets (10k rows)
"""

import math
import sys
import os
import unittest

import pandas as pd
import numpy as np

# ── Allow running from any working directory ────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.visualization_preparation_service import (
    _aggregate_data,
    _safe_float,
    VisualizationPreparationService,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _agg(rows, agg_name):
    """Run _aggregate_data on a two-column DataFrame with a single group 'A'."""
    df = pd.DataFrame({"x": ["A"] * len(rows), "y": rows})
    result = _aggregate_data(df, "x", "y", agg_name)
    val = result.loc[result["x"] == "A", "_value_"].values
    assert len(val) == 1, f"Expected 1 row for group A, got {len(val)}"
    return val[0]


def _grouped_agg(data_dict, agg_name):
    """Run _aggregate_data on a multi-group dataset.

    data_dict: {category: [values...]}
    Returns a dict {category: aggregated_value}.
    """
    rows = []
    for cat, vals in data_dict.items():
        for v in vals:
            rows.append({"x": cat, "y": v})
    df = pd.DataFrame(rows)
    result = _aggregate_data(df, "x", "y", agg_name)
    return dict(zip(result["x"], result["_value_"]))


# ─────────────────────────────────────────────────────────────────────────────
# _safe_float
# ─────────────────────────────────────────────────────────────────────────────

class TestSafeFloat(unittest.TestCase):
    def test_normal_int(self):       self.assertEqual(_safe_float(42), 42.0)
    def test_normal_float(self):     self.assertAlmostEqual(_safe_float(3.14), 3.14)
    def test_nan_returns_zero(self): self.assertEqual(_safe_float(float("nan")), 0.0)
    def test_inf_returns_zero(self): self.assertEqual(_safe_float(float("inf")), 0.0)
    def test_neg_inf(self):          self.assertEqual(_safe_float(float("-inf")), 0.0)
    def test_string_number(self):    self.assertAlmostEqual(_safe_float("7.5"), 7.5)
    def test_invalid_string(self):   self.assertEqual(_safe_float("abc"), 0.0)
    def test_none(self):             self.assertEqual(_safe_float(None), 0.0)
    def test_negative(self):         self.assertAlmostEqual(_safe_float(-99.9), -99.9)


# ─────────────────────────────────────────────────────────────────────────────
# SUM
# ─────────────────────────────────────────────────────────────────────────────

class TestSumAggregation(unittest.TestCase):
    def test_basic_integers(self):
        self.assertAlmostEqual(_agg([10, 20, 30], "sum"), 60)

    def test_single_value(self):
        self.assertAlmostEqual(_agg([42], "sum"), 42)

    def test_decimals(self):
        self.assertAlmostEqual(_agg([1.5, 2.5, 3.0], "sum"), 7.0)

    def test_negative_numbers(self):
        self.assertAlmostEqual(_agg([-10, -20, 30], "sum"), 0)

    def test_all_negative(self):
        self.assertAlmostEqual(_agg([-5, -10, -15], "sum"), -30)

    def test_nulls_ignored(self):
        # null values must NOT be counted as 0
        self.assertAlmostEqual(_agg([10, None, 20, None, 30], "sum"), 60)

    def test_empty_strings_ignored(self):
        df = pd.DataFrame({"x": ["A"] * 4, "y": ["10", "", "20", ""]})
        r = _aggregate_data(df, "x", "y", "sum")
        self.assertAlmostEqual(r.loc[r["x"] == "A", "_value_"].values[0], 30)

    def test_invalid_strings_ignored(self):
        df = pd.DataFrame({"x": ["A"] * 4, "y": ["100", "abc", "200", "xyz"]})
        r = _aggregate_data(df, "x", "y", "sum")
        self.assertAlmostEqual(r.loc[r["x"] == "A", "_value_"].values[0], 300)

    def test_large_dataset(self):
        vals = list(range(1, 10001))   # 1..10000, sum = 50,005,000
        expected = sum(vals)
        self.assertAlmostEqual(_agg(vals, "sum"), expected)

    def test_grouped_sum(self):
        result = _grouped_agg({"India": [100, 200], "USA": [300, 500]}, "sum")
        self.assertAlmostEqual(result["India"], 300)
        self.assertAlmostEqual(result["USA"],   800)


# ─────────────────────────────────────────────────────────────────────────────
# AVG
# ─────────────────────────────────────────────────────────────────────────────

class TestAvgAggregation(unittest.TestCase):
    def test_basic_integers(self):
        self.assertAlmostEqual(_agg([10, 20, 30], "avg"), 20)

    def test_even_count(self):
        self.assertAlmostEqual(_agg([10, 20, 30, 40], "avg"), 25)

    def test_decimals(self):
        self.assertAlmostEqual(_agg([1.0, 3.0], "avg"), 2.0)

    def test_negative_numbers(self):
        self.assertAlmostEqual(_agg([-10, 10], "avg"), 0)

    def test_nulls_excluded_from_denominator(self):
        # [10, null, 20, null, 30] → avg of valid = (10+20+30)/3 = 20, NOT 60/5=12
        self.assertAlmostEqual(_agg([10, None, 20, None, 30], "avg"), 20)

    def test_single_valid(self):
        self.assertAlmostEqual(_agg([None, None, 42], "avg"), 42)

    def test_grouped_avg(self):
        result = _grouped_agg({"India": [100, 200], "USA": [300, 500]}, "avg")
        self.assertAlmostEqual(result["India"], 150)
        self.assertAlmostEqual(result["USA"],   400)


# ─────────────────────────────────────────────────────────────────────────────
# COUNT
# ─────────────────────────────────────────────────────────────────────────────

class TestCountAggregation(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_agg([10, 20, 30], "count"), 3)

    def test_nulls_not_counted(self):
        self.assertEqual(_agg([10, None, 20, None, 30], "count"), 3)

    def test_all_nulls(self):
        result = _agg([None, None, None], "count")
        self.assertEqual(result, 0)

    def test_text_column(self):
        # COUNT should work on text Y columns too
        df = pd.DataFrame({"x": ["A", "A", "A", "A"], "y": ["cat", "dog", None, "bird"]})
        r = _aggregate_data(df, "x", "y", "count")
        self.assertEqual(r.loc[r["x"] == "A", "_value_"].values[0], 3)

    def test_mixed_types(self):
        # Numeric + text — count non-null values
        df = pd.DataFrame({"x": ["A"] * 5, "y": [1, "hello", None, 0, ""]})
        r = _aggregate_data(df, "x", "y", "count")
        # Non-null: 1, "hello", 0 (not None, not "")
        self.assertEqual(r.loc[r["x"] == "A", "_value_"].values[0], 3)

    def test_grouped_count(self):
        result = _grouped_agg({"India": [100, 200], "USA": [300, 500]}, "count")
        self.assertEqual(result["India"], 2)
        self.assertEqual(result["USA"],   2)

    def test_large_dataset(self):
        vals = [i if i % 2 == 0 else None for i in range(1000)]  # 500 valid
        self.assertEqual(_agg(vals, "count"), 500)


# ─────────────────────────────────────────────────────────────────────────────
# MAX
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxAggregation(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(_agg([10, 20, 30], "max"), 30)

    def test_negative_numbers(self):
        self.assertAlmostEqual(_agg([-30, -10, -20], "max"), -10)

    def test_mixed_sign(self):
        self.assertAlmostEqual(_agg([-100, 0, 50, 25], "max"), 50)

    def test_decimals(self):
        self.assertAlmostEqual(_agg([1.1, 2.2, 0.5], "max"), 2.2)

    def test_nulls_ignored(self):
        self.assertAlmostEqual(_agg([10, None, 200, None], "max"), 200)

    def test_grouped_max(self):
        result = _grouped_agg({"India": [100, 200], "USA": [300, 500]}, "max")
        self.assertAlmostEqual(result["India"], 200)
        self.assertAlmostEqual(result["USA"],   500)


# ─────────────────────────────────────────────────────────────────────────────
# MIN
# ─────────────────────────────────────────────────────────────────────────────

class TestMinAggregation(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(_agg([10, 20, 30], "min"), 10)

    def test_negative_numbers(self):
        self.assertAlmostEqual(_agg([-30, -10, -20], "min"), -30)

    def test_mixed_sign(self):
        self.assertAlmostEqual(_agg([-5, 0, 100], "min"), -5)

    def test_decimals(self):
        self.assertAlmostEqual(_agg([1.1, 2.2, 0.5], "min"), 0.5)

    def test_nulls_not_treated_as_zero(self):
        # [100, 200, null] → min should be 100, NOT 0
        self.assertAlmostEqual(_agg([100, 200, None], "min"), 100)

    def test_grouped_min(self):
        result = _grouped_agg({"India": [100, 200], "USA": [300, 500]}, "min")
        self.assertAlmostEqual(result["India"], 100)
        self.assertAlmostEqual(result["USA"],   300)


# ─────────────────────────────────────────────────────────────────────────────
# MEDIAN
# ─────────────────────────────────────────────────────────────────────────────

class TestMedianAggregation(unittest.TestCase):
    def test_odd_count(self):
        self.assertAlmostEqual(_agg([10, 20, 30], "median"), 20)

    def test_even_count(self):
        # (20 + 30) / 2 = 25
        self.assertAlmostEqual(_agg([10, 20, 30, 40], "median"), 25)

    def test_single_value(self):
        self.assertAlmostEqual(_agg([42], "median"), 42)

    def test_two_values(self):
        self.assertAlmostEqual(_agg([10, 30], "median"), 20)

    def test_unsorted_input(self):
        self.assertAlmostEqual(_agg([30, 10, 20], "median"), 20)

    def test_negative_numbers(self):
        self.assertAlmostEqual(_agg([-30, -10, -20], "median"), -20)

    def test_decimals(self):
        self.assertAlmostEqual(_agg([1.5, 2.5, 3.5], "median"), 2.5)

    def test_includes_real_zeros(self):
        # Zero is a valid numeric value and must be included in median
        self.assertAlmostEqual(_agg([0, 0, 6], "median"), 0)

    def test_nulls_excluded(self):
        # [10, null, 30] → median of [10, 30] = 20
        self.assertAlmostEqual(_agg([10, None, 30], "median"), 20)

    def test_grouped_median(self):
        result = _grouped_agg({"India": [100, 200], "USA": [300, 500]}, "median")
        self.assertAlmostEqual(result["India"], 150)
        self.assertAlmostEqual(result["USA"],   400)


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end chart spec tests (via VisualizationPreparationService)
# ─────────────────────────────────────────────────────────────────────────────

class TestBarChartSpec(unittest.TestCase):
    def _make_df(self):
        return pd.DataFrame({
            "Country": ["India", "India", "USA", "USA"],
            "Sales":   [100,     200,     300,   500],
        })

    def _profile(self):
        return {"columns": {
            "Country": {"kind": "categorical"},
            "Sales":   {"kind": "numeric"},
        }}

    def _spec(self, agg):
        svc = VisualizationPreparationService()
        return svc.render_with_axes(
            df=self._make_df(), chart_type="bar", profile=self._profile(),
            x_column="Country", y_column="Sales", aggregation=agg,
        )

    def _val(self, spec, label):
        labels = spec["series"][0]["labels"]
        data   = spec["series"][0]["data"]
        idx    = labels.index(label)
        return data[idx]

    def test_sum(self):
        spec = self._spec("sum")
        self.assertAlmostEqual(self._val(spec, "India"), 300)
        self.assertAlmostEqual(self._val(spec, "USA"),   800)

    def test_avg(self):
        spec = self._spec("avg")
        self.assertAlmostEqual(self._val(spec, "India"), 150)
        self.assertAlmostEqual(self._val(spec, "USA"),   400)

    def test_count(self):
        spec = self._spec("count")
        self.assertAlmostEqual(self._val(spec, "India"), 2)
        self.assertAlmostEqual(self._val(spec, "USA"),   2)

    def test_max(self):
        spec = self._spec("max")
        self.assertAlmostEqual(self._val(spec, "India"), 200)
        self.assertAlmostEqual(self._val(spec, "USA"),   500)

    def test_min(self):
        spec = self._spec("min")
        self.assertAlmostEqual(self._val(spec, "India"), 100)
        self.assertAlmostEqual(self._val(spec, "USA"),   300)

    def test_median(self):
        spec = self._spec("median")
        self.assertAlmostEqual(self._val(spec, "India"), 150)
        self.assertAlmostEqual(self._val(spec, "USA"),   400)

    def test_no_nan_in_output(self):
        """No chart data value should be NaN or Inf (not JSON-serializable)."""
        for agg in ("sum", "avg", "count", "min", "max", "median"):
            spec = self._spec(agg)
            for v in spec["series"][0]["data"]:
                self.assertFalse(math.isnan(v),  f"{agg}: NaN found")
                self.assertFalse(math.isinf(v),  f"{agg}: Inf found")

    def test_nulls_in_y_column(self):
        """Null Y values must be ignored, not treated as 0."""
        df = pd.DataFrame({
            "Country": ["India", "India", "India"],
            "Sales":   [100,     200,     None],
        })
        svc = VisualizationPreparationService()
        spec = svc.render_with_axes(
            df=df, chart_type="bar", profile=self._profile(),
            x_column="Country", y_column="Sales", aggregation="avg",
        )
        # avg = (100 + 200) / 2 = 150  (NOT 100 which would be 300/3)
        self.assertAlmostEqual(spec["series"][0]["data"][0], 150)

    def test_min_not_pulled_down_by_nulls(self):
        """null rows must not make MIN return 0."""
        df = pd.DataFrame({
            "Country": ["A", "A", "A"],
            "Sales":   [100, 200, None],
        })
        svc = VisualizationPreparationService()
        spec = svc.render_with_axes(
            df=df, chart_type="bar", profile=self._profile(),
            x_column="Country", y_column="Sales", aggregation="min",
        )
        self.assertAlmostEqual(spec["series"][0]["data"][0], 100)

    def test_large_dataset(self):
        """10k rows should aggregate without error."""
        n = 10000
        df = pd.DataFrame({
            "Category": ["A"] * (n // 2) + ["B"] * (n // 2),
            "Value":    list(range(n)),
        })
        profile = {"columns": {"Category": {"kind": "categorical"}, "Value": {"kind": "numeric"}}}
        svc = VisualizationPreparationService()
        spec = svc.render_with_axes(
            df=df, chart_type="bar", profile=profile,
            x_column="Category", y_column="Value", aggregation="sum",
        )
        self.assertEqual(len(spec["series"][0]["data"]), 2)


class TestPieChartSpec(unittest.TestCase):
    def test_sum(self):
        df = pd.DataFrame({"Cat": ["A", "A", "B", "B"], "Val": [10, 20, 30, 40]})
        profile = {"columns": {"Cat": {"kind": "categorical"}, "Val": {"kind": "numeric"}}}
        svc = VisualizationPreparationService()
        spec = svc.render_with_axes(
            df=df, chart_type="pie", profile=profile,
            x_column="Cat", y_column="Val", aggregation="sum",
        )
        labels = spec["labels"]
        data   = spec["series"][0]["data"]
        idx_a  = labels.index("A")
        idx_b  = labels.index("B")
        self.assertAlmostEqual(data[idx_a], 30)
        self.assertAlmostEqual(data[idx_b], 70)


if __name__ == "__main__":
    unittest.main(verbosity=2)
