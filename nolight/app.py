import threading
import subprocess
import tkinter as tk
# Import common Tk widgets used throughout the UI
from tkinter import ttk, filedialog
import os
import uuid
import traceback

# Import helpers from the modular utils package so unrelated changes touch
# fewer files and reduce merge conflicts.
from utils.text import sanitize
from utils.api import verify_api_key
from utils.config import (
    load_working_dir,
    save_working_dir,
    load_usage_days,
    build_and_launch_game,
)
from utils.git import format_history_row, HISTORY_COL_WIDTHS, history_records_to_tsv

from nolight import runner

# Map human-friendly names to actual model identifiers
MODEL_OPTIONS = {
    "High": "gpt-5",
    "Medium": "gpt-5-mini",
    "Low": "gpt-5-nano",
}

DEFAULT_CHOICE = "Medium"


def show_build_error(msg: str) -> None:
    """Show a scrollable dialog containing the build failure ``msg``."""
    # Create a new top-level window so the user can move and resize it.
    win = tk.Toplevel()
    win.title("Build failed")
    # Allow the text widget to expand with the window.
    win.rowconfigure(0, weight=1)
    win.columnconfigure(0, weight=1)

    # Text widget displays the stack trace while the scrollbar enables
    # navigation through long traces.
    txt = tk.Text(win, wrap="word")
    scroll = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=scroll.set)
    txt.insert("1.0", msg)
    # Disable editing but still allow text selection for easy copying.
    txt.config(state="disabled")
    txt.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")


def launch_game(project_path: str) -> None:
    """Build and start the Unity project located at ``project_path``."""
    try:
        # Pass the user-selected working directory to the builder so Unity
        # knows which project to compile.
        build_and_launch_game(project_path=project_path)
    except Exception:
        # Show the full stack trace so the user can scroll and copy it.
        show_build_error(traceback.format_exc())


def build_ui(root: tk.Tk):
    """Create all widgets for the main window and return key components."""

    main_frame = ttk.Frame(root, padding=8)
    main_frame.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    # Make the second column expandable so labels sit directly next to buttons
    for col in range(4):
        main_frame.columnconfigure(col, weight=1 if col == 1 else 0)

    # API key status label sits on the left while the build button uses the
    # rightmost column. The label spans three columns so it does not overlap
    # the new button.
    api_status_label = ttk.Label(main_frame, text="API key: checking...", foreground="orange")
    api_status_label.grid(row=0, column=0, columnspan=3, sticky="w")

    # Button in the top-right corner lets the user build and run the game at
    # any time for quick testing of changes. The selected working directory is
    # forwarded so Unity knows which project to compile.
    build_btn = ttk.Button(
        main_frame,
        text="Build & Run",
        command=lambda: launch_game(work_dir_var.get()),
    )
    build_btn.grid(row=0, column=3, sticky="e")

    # Project directory selector
    work_dir_var = tk.StringVar(value="")
    # Separate variable used only for displaying the path or an error message
    dir_path_var = tk.StringVar(value="")

    def choose_dir() -> None:
        """Prompt the user for a working directory and remember it."""
        path = filedialog.askdirectory()
        if path:
            work_dir_var.set(path)
            dir_path_var.set(path)
            save_working_dir(path)
        else:
            work_dir_var.set("")
            dir_path_var.set("No directory selected")
            save_working_dir("")

    dir_btn = ttk.Button(main_frame, text="Select Working Directory", command=choose_dir)
    dir_btn.grid(row=1, column=0, sticky="w", pady=(4, 0))

    # Displays the currently selected working directory or an error message
    dir_path_label = ttk.Label(main_frame, textvariable=dir_path_var)
    dir_path_label.grid(row=1, column=1, columnspan=3, sticky="w", pady=(4, 0), padx=(8, 0))

    # Load any previously cached working directory
    cached_dir = load_working_dir()
    if cached_dir and os.path.isdir(cached_dir):
        work_dir_var.set(cached_dir)
        dir_path_var.set(cached_dir)
    elif cached_dir:
        dir_path_var.set("Cached path missing")

    # Model selection dropdown aligned to the left under the directory button
    model_var = tk.StringVar(value=DEFAULT_CHOICE)
    model_label = ttk.Label(main_frame, text="Model:")
    model_label.grid(row=2, column=0, sticky="w", pady=(4, 0))
    model_combo = ttk.Combobox(
        main_frame,
        textvariable=model_var,
        values=list(MODEL_OPTIONS.keys()),
        state="readonly",
        width=10,
    )
    model_combo.grid(row=2, column=1, sticky="w", pady=(4, 0))
    # Previously a toggle allowed "ask only" mode, but it has been removed
    # because aider no longer supports running without commits.

    # Spacer row adds a blank line before the prompt label for readability
    ttk.Label(main_frame, text="").grid(row=3, column=0)

    # Input label introduces the text entry area
    lbl = ttk.Label(main_frame, text="What can I do for you today?")
    lbl.grid(row=4, column=0, sticky="w", pady=(4, 0))

    # Paned window lets the user resize input and output areas
    paned = ttk.PanedWindow(main_frame, orient="vertical")
    paned.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(4, 0))
    main_frame.rowconfigure(5, weight=1)

    # --- Input area -----------------------------------------------------------
    input_frame = ttk.Frame(paned)
    # Text widget where the user enters prompts; scrollbar keeps it tidy
    txt_input = tk.Text(input_frame, wrap="word")
    input_scroll = ttk.Scrollbar(input_frame, orient="vertical", command=txt_input.yview)
    txt_input.configure(yscrollcommand=input_scroll.set)
    txt_input.grid(row=0, column=0, sticky="nsew")
    input_scroll.grid(row=0, column=1, sticky="ns")
    input_frame.rowconfigure(0, weight=1)
    input_frame.columnconfigure(0, weight=1)
    paned.add(input_frame, weight=1)

    # Track total dollars spent in this session and display it to the user
    session_cost_var = tk.StringVar(value="Total credits this session: $0.0000")

    def on_send(event=None) -> None:
        """Handle the Enter key by sending the message to aider."""
        raw = txt_input.get("1.0", tk.END)
        if not raw.strip():
            return
        if not work_dir_var.get():
            output.configure(state="normal")
            output.insert(tk.END, "[error] Select a working directory first\n")
            output.configure(state="disabled")
            return
        msg = sanitize(raw)
        # Remove old output if the last request finished with a commit.
        runner.maybe_clear_output(output)
        # Remove the user's prompt so the box is ready for the next message.
        txt_input.delete("1.0", tk.END)
        # Disable input until aider responds so duplicate requests can't be sent.
        txt_input.config(state="disabled")
        # Generate a new request id only if we're starting a fresh request.
        if not runner.request_active:
            runner.current_request_id = str(uuid.uuid4())
            runner.request_active = True
        req_id = runner.current_request_id

        model = MODEL_OPTIONS[model_var.get()]
        # Spawn a thread to call the runner so the UI stays responsive.
        t = threading.Thread(
            target=runner.run_aider,
            args=(
                msg,
                output,
                txt_input,
                work_dir_var.get(),
                model,
                status_var,
                status_label,
                req_id,
                session_cost_var,
            ),
            daemon=True,
        )
        t.start()

    def on_return(event):
        on_send()
        return "break"

    def on_shift_return(event):
        return

    txt_input.bind("<Return>", on_return)
    txt_input.bind("<Shift-Return>", on_shift_return)
    txt_input.focus_set()

    # --- Response area --------------------------------------------------------
    response_frame = ttk.Frame(paned)

    # Status bar communicates whether we're waiting on aider or user input
    status_var = tk.StringVar(value="Aider is waiting on our input")
    # Border around status bar helps it stand out from the output text
    status_frame = ttk.Frame(response_frame, borderwidth=1, relief="solid")
    status_frame.grid(row=0, column=0, sticky="ew")
    status_label = ttk.Label(status_frame, textvariable=status_var)
    # Expand label to fill the frame horizontally.
    status_label.pack(fill="x", padx=2, pady=2)

    # Output area where aider output is streamed back to the user
    output = tk.Text(response_frame, wrap="word", state="disabled")
    output_scroll = ttk.Scrollbar(response_frame, orient="vertical", command=output.yview)
    output.configure(yscrollcommand=output_scroll.set)
    output.grid(row=1, column=0, sticky="nsew")
    output_scroll.grid(row=1, column=1, sticky="ns")
    response_frame.rowconfigure(1, weight=1)
    response_frame.columnconfigure(0, weight=1)

    # Give the response area more room than the input by default
    paned.add(response_frame, weight=3)

    def show_history() -> None:
        """Open a window displaying a table of previous requests."""
        win = tk.Toplevel(root)
        win.title("History")
        cols = (
            "request_id",
            "commit_id",
            "lines",
            "files",
            "cost",
            "failure_reason",
            "description",
        )
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for col in cols:
            tree.heading(col, text=col.replace("_", " ").title())
            # Keep IDs and counts narrow but give text fields extra room.
            anchor = "e" if col in {"lines", "files", "cost"} else "w"
            tree.column(col, width=HISTORY_COL_WIDTHS[col], anchor=anchor)
        for idx, rec in enumerate(runner.request_history):
            # Use ``idx`` as the item id so we can map back to the record later.
            tree.insert("", tk.END, iid=str(idx), values=format_history_row(rec))

        def copy_selected(event=None) -> None:
            """Copy selected history rows to the clipboard."""
            # ``selection`` returns the item ids for the highlighted rows.
            sel = tree.selection()
            if not sel:
                return
            # Fetch the underlying records using the stored indices.
            rows = [runner.request_history[int(i)] for i in sel]
            # Convert to tab-separated text and push to the clipboard.
            txt = history_records_to_tsv(rows)
            win.clipboard_clear()
            win.clipboard_append(txt)

        # Allow standard Ctrl+C copying of the selected rows.
        tree.bind("<Control-c>", copy_selected)
        tree.pack(fill="both", expand=True)

    # Simple button to pop up the history table
    history_btn = ttk.Button(main_frame, text="History", command=show_history)
    history_btn.grid(row=6, column=0, sticky="w", pady=(6, 0))

    # Show how much money has been spent in the current session
    session_cost_label = ttk.Label(main_frame, textvariable=session_cost_var)
    session_cost_label.grid(row=6, column=3, sticky="e", pady=(6, 0))

    def open_env_settings(event=None) -> None:
        """Open the system environment variable settings on Windows."""
        if os.name == "nt":
            subprocess.Popen(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])

    def check_api_key() -> None:
        """Validate the OPENAI_API_KEY and report the result to the user."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            # Provide a clickable hint to open the environment variable settings
            api_status_label.config(
                text="Env var OPENAI_API_KEY is not set. Click here to set it.",
                foreground="red",
                cursor="hand2",
            )
            api_status_label.bind("<Button-1>", open_env_settings)
            txt_input.config(state="disabled")
            return

        try:
            verify_api_key(api_key)
            api_status_label.config(
                text="✓ OpenAI API key verified",
                foreground="green",
                cursor="",
            )
            api_status_label.unbind("<Button-1>")
            txt_input.config(state="normal")
        except Exception as e:
            # Show the failure reason from verify_api_key so the user can fix it
            api_status_label.config(
                text=f"API key: ✗ ({e})", foreground="red", cursor=""
            )
            api_status_label.unbind("<Button-1>")
            txt_input.config(state="disabled")

    widgets = {
        "model_label": model_label,
        "model_combo": model_combo,
        "prompt_label": lbl,
        # Return the input widget so tests can simulate user typing.
        "txt_input": txt_input,
        # Expose the working directory variable for test configuration.
        "work_dir_var": work_dir_var,
    }

    return widgets, check_api_key


def main() -> None:
    """Create the Tkinter UI and start the main event loop."""

    root = tk.Tk()
    root.title("Aider Prompt UI")
    _, check_api = build_ui(root)
    root.after(0, check_api)
    root.mainloop()

