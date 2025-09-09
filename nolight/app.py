import threading
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import os
import uuid

from utils import (
    sanitize,
    verify_api_key,
    load_timeout,
    save_timeout,
    load_working_dir,
    save_working_dir,
    load_usage_days,
    fetch_usage_data,
    format_history_row,
    HISTORY_COL_WIDTHS,
)

from nolight import runner

# Map human-friendly names to actual model identifiers
MODEL_OPTIONS = {
    "High": "gpt-5",
    "Medium": "gpt-5-mini",
    "Low": "gpt-5-nano",
}

# Always start with the medium model; the choice isn't persisted between runs.
DEFAULT_CHOICE = "Medium"


def main() -> None:
    """Create the Tkinter UI and start the main event loop."""

    root = tk.Tk()
    root.title("Aider Prompt UI")

    main_frame = ttk.Frame(root, padding=8)
    main_frame.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    # Default timeout pulled from config file and saved back when modified
    timeout_var = tk.IntVar(value=load_timeout())

    def on_timeout_change(*_args):
        save_timeout(timeout_var.get())

    timeout_var.trace_add("write", on_timeout_change)

    # Make the second column expandable so labels sit directly next to buttons
    for col in range(4):
        main_frame.columnconfigure(col, weight=1 if col == 1 else 0)

    # API key status label
    api_status_label = ttk.Label(main_frame, text="API key: checking...", foreground="orange")
    # Span first three columns so a settings button can live in the fourth
    api_status_label.grid(row=0, column=0, columnspan=3, sticky="w")

    def open_settings() -> None:
        """Pop up a small window to house UI-related settings."""
        win = tk.Toplevel(root)
        win.title("Settings")

        ttk.Label(win, text="Timeout (min):").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        # The spinbox shares the same variable used in the main UI so changes
        # automatically persist via the trace handler.
        ttk.Spinbox(win, from_=1, to=60, textvariable=timeout_var, width=5).grid(
            row=0, column=1, padx=8, pady=8, sticky="w"
        )

    # Simple gear icon button that opens the settings window
    settings_btn = ttk.Button(main_frame, text="⚙", width=3, command=open_settings)
    settings_btn.grid(row=0, column=3, sticky="e")

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

    # Model selection dropdown (right-aligned for a cleaner look)
    model_var = tk.StringVar(value=DEFAULT_CHOICE)
    model_label = ttk.Label(main_frame, text="Model:")
    # Place label near the right edge with minimal padding to be close to combo
    model_label.grid(row=2, column=2, sticky="e", pady=(4, 0), padx=(0, 3))
    model_combo = ttk.Combobox(
        main_frame,
        textvariable=model_var,
        values=list(MODEL_OPTIONS.keys()),
        state="readonly",
        width=10,  # Slightly narrower selection box
    )
    model_combo.grid(row=2, column=3, sticky="w", pady=(4, 0))

    # Input label
    lbl = ttk.Label(main_frame, text="What can I do for you today?")
    lbl.grid(row=3, column=0, sticky="w", pady=(4, 0))

    # Multiline input (Shift+Enter for newline; Enter to send)
    txt_input = scrolledtext.ScrolledText(main_frame, width=100, height=6, wrap="word")
    txt_input.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(4, 0))
    main_frame.rowconfigure(4, weight=0)

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
        # Disable input until aider responds so duplicate requests can't be sent.
        txt_input.config(state="disabled")
        # Generate a new request id only if we're starting a fresh request.
        if not runner.request_active:
            runner.current_request_id = str(uuid.uuid4())
            runner.request_active = True
        req_id = runner.current_request_id

        model = MODEL_OPTIONS[model_var.get()]
        t = threading.Thread(
            target=runner.run_aider,
            args=(
                msg,
                output,
                txt_input,
                work_dir_var.get(),
                model,
                timeout_var.get(),  # Minutes to wait for commit id
                status_var,
                status_label,
                req_id,
                root,
            ),
            daemon=True,
        )
        t.start()
        txt_input.delete("1.0", tk.END)

    def on_return(event):
        on_send()
        return "break"

    def on_shift_return(event):
        return

    txt_input.bind("<Return>", on_return)
    txt_input.bind("<Shift-Return>", on_shift_return)
    txt_input.focus_set()

    # Status bar communicates whether we're waiting on aider or user input
    status_var = tk.StringVar(value="Aider is waiting on our input")
    # Frame with a border so the status bar looks visually distinct and "boxed".
    status_frame = ttk.Frame(main_frame, borderwidth=1, relief="solid")
    status_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=0)
    status_label = ttk.Label(status_frame, textvariable=status_var)
    # Expand label to fill the frame horizontally.
    status_label.pack(fill="x", padx=2, pady=2)

    # Output area where aider output is streamed
    output = scrolledtext.ScrolledText(
        main_frame, width=100, height=24, wrap="word", state="disabled"
    )
    # Attach the output area directly below the status frame with no spacing.
    output.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(0, 0))
    main_frame.rowconfigure(6, weight=1)

    def show_history() -> None:
        """Open a window displaying a table of previous requests."""
        win = tk.Toplevel(root)
        win.title("History")
        # We only show total line and file counts for brevity.
        cols = (
            "request_id",
            "commit_id",
            "lines",
            "files",
            "failure_reason",
            "description",
        )
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for col in cols:
            tree.heading(col, text=col.replace("_", " ").title())
            # Keep IDs and counts narrow but give text fields extra room.
            anchor = "e" if col in {"lines", "files"} else "w"
            tree.column(col, width=HISTORY_COL_WIDTHS[col], anchor=anchor)
        for rec in runner.request_history:
            # Abbreviate IDs before inserting so the table stays compact.
            tree.insert("", tk.END, values=format_history_row(rec))
        tree.pack(fill="both", expand=True)

    def show_api_usage() -> None:
        """Open a window displaying recent API spending and credit details."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            # Fail fast if the key is missing so the user knows why we cannot query.
            messagebox.showerror("API Usage", "Env var OPENAI_API_KEY is not set")
            return

        # Read how far back to look for usage statistics from the config file.
        days = load_usage_days()
        try:
            stats = fetch_usage_data(api_key, days=days)
        except Exception as exc:
            # Surface any API errors so the user can investigate.
            messagebox.showerror("API Usage", str(exc))
            return

        # Average cost is approximated using the number of requests we have tracked.
        avg_cost = stats["total_spent"] / len(runner.request_history) if runner.request_history else 0

        win = tk.Toplevel(root)
        win.title("API Usage")
        msg = (
            f"Amount spent (last {days} days): ${stats['total_spent']:.2f}\n"
            f"Average cost per request: ${avg_cost:.2f}\n"
            f"Credits remaining: ${stats['credits_remaining']:.2f} of ${stats['credits_total']:.2f}\n"
            f"Percent credits used: {stats['pct_credits_used']:.2f}%"
        )
        ttk.Label(win, text=msg, justify="left").pack(padx=10, pady=10)

    # Simple button to pop up the history table
    history_btn = ttk.Button(main_frame, text="History", command=show_history)
    history_btn.grid(row=7, column=0, sticky="w", pady=(6, 0))

    # Button to display API usage information
    usage_btn = ttk.Button(main_frame, text="API usage", command=show_api_usage)
    usage_btn.grid(row=7, column=3, sticky="e", pady=(6, 0))

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

    root.after(0, check_api_key)
    root.mainloop()
