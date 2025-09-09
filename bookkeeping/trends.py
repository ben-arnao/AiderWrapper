"""Utilities for summarizing time-series trends."""

import configparser
import math
from pathlib import Path
from statistics import NormalDist, mean
from typing import Iterable, Tuple, Dict

# Load configuration for default parameters
_config = configparser.ConfigParser()
_config.read(Path(__file__).resolve().parents[1] / "config.ini")
DEFAULT_HORIZON = _config.getint("trends", "forecast_horizon", fallback=10)
DEFAULT_CONFIDENCE = _config.getfloat("trends", "confidence_level", fallback=0.95)


def summarize_trend(
    values: Iterable[float],
    horizon: int = DEFAULT_HORIZON,
    confidence: float = DEFAULT_CONFIDENCE,
) -> Dict[str, Tuple[float, Tuple[float, float]]]:
    """Summarize where a numeric trend is now and its chance of improvement.

    Args:
        values: Ordered numeric observations representing the trend.
        horizon: How many steps into the future to project the value.
        confidence: Confidence level for the current value interval.

    Returns:
        Dictionary with the current estimate (and its CI), probability the slope is
        positive, and probability the value will be above zero at ``horizon``.
    """
    data = list(values)
    n = len(data)
    if n < 2:
        raise ValueError("At least two data points are required to assess a trend.")

    x_values = list(range(n))
    x_mean = (n - 1) / 2  # mean of 0..n-1
    y_mean = mean(data)

    # Compute slope and intercept of the best-fit line using simple linear regression
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, data)) / denominator
    intercept = y_mean - slope * x_mean

    # Calculate residual standard error to quantify noise around the fit
    fitted = [intercept + slope * x for x in x_values]
    residuals = [y - f for y, f in zip(data, fitted)]
    s_err = math.sqrt(sum(r ** 2 for r in residuals) / (n - 2))

    # Standard error of the slope for probabilistic reasoning
    slope_se = s_err / math.sqrt(denominator)

    # Estimate current value (last point) and its standard error
    current_x = x_values[-1]
    current_mean = intercept + slope * current_x
    current_se = s_err * math.sqrt(1 / n + (current_x - x_mean) ** 2 / denominator)
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    current_ci = (
        current_mean - z * current_se,
        current_mean + z * current_se,
    )

    # Probability that the slope is positive
    if slope_se == 0:
        # With no observed noise, the sign of the slope is deterministic
        p_slope_positive = 1.0 if slope > 0 else 0.0
    else:
        p_slope_positive = 1 - NormalDist(mu=slope, sigma=slope_se).cdf(0)

    # Forecast ``horizon`` steps ahead and compute probability it is above zero
    future_x = current_x + horizon
    future_mean = intercept + slope * future_x
    future_se = s_err * math.sqrt(1 / n + (future_x - x_mean) ** 2 / denominator)
    if future_se == 0:
        # Deterministic prediction when residual error is zero
        p_future_positive = 1.0 if future_mean > 0 else 0.0
    else:
        p_future_positive = 1 - NormalDist(mu=future_mean, sigma=future_se).cdf(0)

    return {
        "current": (current_mean, current_ci),
        "p_slope_positive": p_slope_positive,
        "p_above_zero_future": p_future_positive,
    }
