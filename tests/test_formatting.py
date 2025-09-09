import sys
from pathlib import Path
import re

# Add project root to path so the test can import the bookkeeping module.
sys.path.append(str(Path(__file__).resolve().parents[1]))
from bookkeeping.formatting import format_trade_metrics


def test_format_trade_metrics_precision_and_spacing():
    """Probabilities should have 15 decimals and spacing should be tight."""
    line = format_trade_metrics(
        trades=1348,
        pf_delta=0.000572,
        models=32,
        model_trades=28,
        ppt=0.0,
        avg_ppt=0.0,
        ppe=0.0,
    )

    # Verify there are no double spaces anywhere in the line.
    assert "  " not in line

    # Extract the probability fields and ensure they have exactly 15 decimals.
    probs = re.findall(r"(ppt|avg_ppt|ppe): ([0-9]+\.([0-9]+))", line)
    for _, _, decimals in probs:
        assert len(decimals) == 15

    # Check the overall formatted line matches our expectation exactly.
    assert (
        line
        == "trades: 1348 | pf_delta: 0.000572 | models: 32 | model_trades: 28 | "
        "ppt: 0.000000000000000 | avg_ppt: 0.000000000000000 | ppe: 0.000000000000000"
    )
