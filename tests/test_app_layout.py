import pytest
import tkinter as tk
import sys
from pathlib import Path

# Ensure project root is on the import path so ``nolight`` can be resolved
sys.path.append(str(Path(__file__).resolve().parents[1]))
from nolight import app


def test_model_selection_left_justified_and_spacing():
    """Model selector should sit under the directory button and prompt label is spaced."""
    try:
        root = tk.Tk()
        root.withdraw()  # Hide main window during the test
    except tk.TclError:
        pytest.skip("Tkinter display not available")

    widgets, _ = app.build_ui(root)
    model_label = widgets["model_label"]
    model_combo = widgets["model_combo"]
    prompt_label = widgets["prompt_label"]
    # Ask-only toggle was removed, so it should not appear in the widget map.
    assert "ask_mode_check" not in widgets

    # Model label and dropdown should occupy the first two columns
    assert model_label.grid_info()["column"] == 0
    assert model_combo.grid_info()["column"] == 1
    assert "w" in model_label.grid_info().get("sticky", "")
    assert "w" in model_combo.grid_info().get("sticky", "")

    # Prompt label should be two rows below the model selector (blank row added)
    assert prompt_label.grid_info()["row"] - model_combo.grid_info()["row"] == 2

    root.destroy()
