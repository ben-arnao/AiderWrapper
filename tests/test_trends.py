import sys
from pathlib import Path

import pytest

# Ensure the repository root is on the import path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from bookkeeping.trends import summarize_trend


def test_summarize_trend_positive():
    """Increasing data should show high confidence in a positive trend."""
    data = [1, 2, 3, 4, 5]
    summary = summarize_trend(data, horizon=1)
    current, ci = summary["current"]
    # Current value should lie within its confidence interval
    assert ci[0] <= current <= ci[1]
    assert summary["p_slope_positive"] > 0.9
    assert summary["p_above_zero_future"] > 0.9


def test_summarize_trend_negative():
    """Decreasing data should show low probability of staying positive."""
    data = [5, 4, 3, 2, 1]
    summary = summarize_trend(data, horizon=5)
    assert summary["p_slope_positive"] < 0.1
    assert summary["p_above_zero_future"] < 0.1


def test_summarize_trend_crosses_zero():
    """Upward trend in negative values should likely cross zero."""
    data = [-3, -2, -1]
    summary = summarize_trend(data, horizon=2)
    assert summary["p_slope_positive"] > 0.9
    assert summary["p_above_zero_future"] > 0.5


def test_summarize_trend_requires_points():
    """Less than two data points should raise an error."""
    with pytest.raises(ValueError):
        summarize_trend([1])
