from __future__ import annotations

"""Utility functions for formatting trade metrics for logs and displays."""


def format_trade_metrics(
    trades: int,
    pf_delta: float,
    models: int,
    model_trades: int,
    ppt: float,
    avg_ppt: float,
    ppe: float,
) -> str:
    """Return a compact, human-readable summary line.

    The function ensures columns are separated by a single space on either
    side of the ``|`` character and that probability values are formatted
    with fifteen digits after the decimal point.
    """

    # Format probabilities with 15 decimal places and pf_delta with six.
    return (
        f"trades: {trades} | "
        f"pf_delta: {pf_delta:.6f} | "
        f"models: {models} | "
        f"model_trades: {model_trades} | "
        f"ppt: {ppt:.15f} | "
        f"avg_ppt: {avg_ppt:.15f} | "
        f"ppe: {ppe:.15f}"
    )
