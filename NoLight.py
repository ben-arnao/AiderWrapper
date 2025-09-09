import threading
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import os
import time  # Track elapsed time when waiting for commit id
import uuid  # Generate a unique id for each request
from typing import Optional, List

from utils import (
    sanitize,
    should_suppress,
    verify_api_key,
    load_timeout,
    save_timeout,
    extract_commit_id,
    needs_user_input,
    load_working_dir,
    save_working_dir,
    get_commit_stats,  # Compute line/file counts for commits
    load_usage_days,  # Read how far back to query billing data
    fetch_usage_data,  # Retrieve spending/credit information
    build_and_launch_game,  # Build and run the Unity project on demand
)

# Map human-friendly names to actual model identifiers
MODEL_OPTIONS = {
    "High": "gpt-5",
    "Medium": "gpt-5-mini",
    "Low": "gpt-5-nano",
}

# Always start with the medium model; the choice isn't persisted between runs.
DEFAULT_CHOICE = "Medium"

# Track details for each user request so they can be shown in a history table.
request_history: List[dict] = []  # List of per-request summaries
current_request_id: Optional[str] = None  # UUID for the active request
request_active = False  # True while we're waiting on aider to finish


def run_aider(
    msg: str,
    output_widget: scrolledtext.ScrolledText,
    txt_input: tk.Text,
    work_dir: str,
    model: str,
    timeout_minutes: int,
    status_var: tk.StringVar,
    status_label: ttk.Label,
    request_id: str,
):
    """Spawn the aider CLI and capture commit details.

    All output from aider is streamed into ``output_widget``. When a commit id
    is detected or a failure occurs, a summary of the request is appended to
    ``request_history`` so the user can review past actions.
    """

    global request_active
    # Remove any previous "test changes" link before starting a new request
    status_label.config(foreground="black", cursor="")
    status_label.unbind("<Button-1>")

    try:
        # Automatically answer "yes" to any prompts so the UI never hangs.
        cmd_args = ["aider", "--yes-always", "--model", model, "--message", msg]

        # Let the user know we're waiting on aider and start a simple countdown
        # so they can see when a timeout will occur.
        status_var.set(
            f"Waiting on aider's response... {timeout_minutes * 60} seconds to timeout"
        )

        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END, f"\n> aider --model {model} --message \"{msg}\"\n\n"
        )
        output_widget.see(tk.END)
        output_widget.configure(state="disabled")

        # Stream output back into the widget (no TTY; filter noisy warnings).
        proc = subprocess.Popen(
            cmd_args,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )

        start_time = time.time()
        commit_id: Optional[str] = None
        failure_reason: Optional[str] = None
        waiting_on_user = False  # Set when aider asks for more information

        def update_countdown() -> None:
            """Refresh the status bar every second with remaining time."""

            elapsed = time.time() - start_time
            remaining = int(timeout_minutes * 60 - elapsed)
            # Stop updating once we have a result or are waiting on the user.
            if commit_id or failure_reason or waiting_on_user or remaining < 0:
                return
            status_var.set(
                f"Waiting on aider's response... {remaining} seconds to timeout"
            )
            root.after(1000, update_countdown)

        # Kick off the countdown updates.
        root.after(1000, update_countdown)

        # Read line-by-line so the UI stays responsive.
        for line in proc.stdout:
            if should_suppress(line):
                continue
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, line)
            output_widget.see(tk.END)
            output_widget.configure(state="disabled")

            # Try to extract a commit hash from the stream.
            cid = extract_commit_id(line)
            if cid:
                commit_id = cid

            # If aider is asking for more information, stop the process and let
            # the user reply instead of timing out.
            if needs_user_input(line):
                waiting_on_user = True
                status_var.set("Aider is waiting on our input")
                proc.kill()
                break

            # Stop waiting if timeout elapsed without a commit id.
            if (
                commit_id is None
                and not waiting_on_user
                and time.time() - start_time > timeout_minutes * 60
            ):
                failure_reason = "Timed out waiting for commit id"
                status_var.set("Failed to make commit due to timeout")
                proc.kill()
                break

        proc.wait()

        if commit_id:
            try:
                # Query git for stats about the commit so we can store them.
                stats = get_commit_stats(commit_id, work_dir)
                # Store a simple summary of how many lines and files changed.
                lines_total = stats["lines_changed"]
                files_total = (
                    stats["files_changed"]
                    + stats["files_added"]
                    + stats["files_removed"]
                )
                request_history.append(
                    {
                        "request_id": request_id,
                        "commit_id": commit_id,
                        "lines": lines_total,
                        "files": files_total,
                        "failure_reason": None,
                        "description": stats["description"],
                    }
                )
                status_var.set(
                    f"Successfully made changes with commit id {commit_id}. Click to test changes"
                )
                # Make the status label look and behave like a hyperlink that
                # builds and launches the user's game when clicked
                status_label.config(foreground="blue", cursor="hand2")
                status_label.bind(
                    "<Button-1>", lambda _e: build_and_launch_game()
                )
            except Exception as e:
                # If stats collection fails, record the error but keep running.
                request_history.append(
                    {
                        "request_id": request_id,
                        "commit_id": commit_id,
                        "lines": 0,
                        "files": 0,
                        "failure_reason": f"stats error: {e}",
                        "description": "",
                    }
                )
                status_var.set(
                    f"Made commit {commit_id} but failed to gather stats"
                )
            request_active = False
        elif waiting_on_user:
            # No commit hash yet because aider needs more input. Leave the
            # request active so the next message is treated as part of it.
            pass
        else:
            if failure_reason is None:
                failure_reason = "No commit id found"
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, f"\n[error] {failure_reason}\n")
            output_widget.insert(tk.END, f"[exit code: {proc.returncode}]\n")
            output_widget.insert(tk.END, "-" * 60 + "\n")
            output_widget.configure(state="disabled")
            status_var.set(f"Failed to make commit due to {failure_reason}")
            request_history.append(
                {
                    "request_id": request_id,
                    "commit_id": None,
                    "lines": 0,
                    "files": 0,
                    "failure_reason": failure_reason,
                    "description": "",
                }
            )
            request_active = False
    except FileNotFoundError:
        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            "\n[error] Could not find 'aider'. Make sure it's installed and on your PATH.\n",
        )
        output_widget.configure(state="disabled")
        status_var.set("Failed to make commit due to missing 'aider'")
        request_history.append(
            {
                "request_id": request_id,
                "commit_id": None,
                "lines": 0,
                "files": 0,
                "failure_reason": "aider not found",
                "description": "",
            }
        )
        request_active = False
    finally:
        # Re-enable the input box so the user can type a follow-up or new request.
        txt_input.config(state="normal")
        txt_input.focus_set()


def on_send(event=None):
    """Handle the Enter key by sending the message to aider."""
    global request_active, current_request_id
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
    if not request_active:
        current_request_id = str(uuid.uuid4())
        request_active = True
    req_id = current_request_id

    model = MODEL_OPTIONS[model_var.get()]
    t = threading.Thread(
        target=run_aider,
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
        ),
        daemon=True,
    )
    t.start()
    txt_input.delete("1.0", tk.END)


# ---- UI ----
root = tk.Tk()
root.title("Aider Prompt UI")

main = ttk.Frame(root, padding=8)
main.grid(row=0, column=0, sticky="nsew")
root.rowconfigure(0, weight=1)
root.columnconfigure(0, weight=1)

# Default timeout pulled from config file and saved back when modified
timeout_var = tk.IntVar(value=load_timeout())


def on_timeout_change(*args):
    save_timeout(timeout_var.get())


timeout_var.trace_add("write", on_timeout_change)

# Make the second column expandable so labels sit directly next to buttons
for col in range(4):
    main.columnconfigure(col, weight=1 if col == 1 else 0)

# API key status label
api_status_label = ttk.Label(main, text="API key: checking...", foreground="orange")
# Span first three columns so a settings button can live in the fourth
api_status_label.grid(row=0, column=0, columnspan=3, sticky="w")


def open_settings():
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
settings_btn = ttk.Button(main, text="⚙", width=3, command=open_settings)
settings_btn.grid(row=0, column=3, sticky="e")

# Project directory selector
work_dir_var = tk.StringVar(value="")
# Separate variable used only for displaying the path or an error message
dir_path_var = tk.StringVar(value="")


def choose_dir():
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


dir_btn = ttk.Button(main, text="Select Working Directory", command=choose_dir)
dir_btn.grid(row=1, column=0, sticky="w", pady=(4, 0))

# Displays the currently selected working directory or an error message
dir_path_label = ttk.Label(main, textvariable=dir_path_var)
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
model_label = ttk.Label(main, text="Model:")
# Place label near the right edge with minimal padding to be close to combo
model_label.grid(row=2, column=2, sticky="e", pady=(4, 0), padx=(0, 3))
model_combo = ttk.Combobox(
    main,
    textvariable=model_var,
    values=list(MODEL_OPTIONS.keys()),
    state="readonly",
    width=10,  # Slightly narrower selection box
)
model_combo.grid(row=2, column=3, sticky="w", pady=(4, 0))

# Input label
lbl = ttk.Label(main, text="What can I do for you today?")
lbl.grid(row=3, column=0, sticky="w", pady=(4, 0))

# Multiline input (Shift+Enter for newline; Enter to send)
txt_input = scrolledtext.ScrolledText(main, width=100, height=6, wrap="word")
txt_input.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(4, 0))
main.rowconfigure(4, weight=0)


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
status_frame = ttk.Frame(main, borderwidth=1, relief="solid")
status_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=0)
status_label = ttk.Label(status_frame, textvariable=status_var)
# Expand label to fill the frame horizontally.
status_label.pack(fill="x", padx=2, pady=2)

# Output area where aider output is streamed
output = scrolledtext.ScrolledText(
    main, width=100, height=24, wrap="word", state="disabled"
)
# Attach the output area directly below the status frame with no spacing.
output.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(0, 0))
main.rowconfigure(6, weight=1)


def show_history():
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
    for rec in request_history:
        tree.insert(
            "",
            tk.END,
            values=(
                rec.get("request_id"),
                rec.get("commit_id", ""),
                rec.get("lines", 0),
                rec.get("files", 0),
                rec.get("failure_reason", ""),
                rec.get("description", ""),
            ),
        )
    tree.pack(fill="both", expand=True)


def show_api_usage():
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
    avg_cost = stats["total_spent"] / len(request_history) if request_history else 0

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
history_btn = ttk.Button(main, text="History", command=show_history)
history_btn.grid(row=7, column=0, sticky="w", pady=(6, 0))

# Button to display API usage information
usage_btn = ttk.Button(main, text="API usage", command=show_api_usage)
usage_btn.grid(row=7, column=3, sticky="e", pady=(6, 0))


def open_env_settings(event=None):
    """Open the system environment variable settings on Windows."""
    if os.name == "nt":
        subprocess.Popen(["rundll32.exe", "sysdm.cpl,EditEnvironmentVariables"])


def check_api_key():
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
