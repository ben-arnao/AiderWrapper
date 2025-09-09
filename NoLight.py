import threading
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import os
import time  # Track elapsed time when waiting for commit id

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
    load_default_model,
    save_default_model,
)

# Map human-friendly names to actual model identifiers
MODEL_OPTIONS = {
    "High": "gpt-5",
    "Medium": "gpt-5-mini",
    "Low": "gpt-5-nano",
}

# Read default model from config.ini using helper that falls back gracefully
DEFAULT_MODEL = load_default_model()
DEFAULT_CHOICE = next((k for k, v in MODEL_OPTIONS.items() if v == DEFAULT_MODEL), "Medium")


def run_aider(
    msg: str,
    output_widget: scrolledtext.ScrolledText,
    send_btn: ttk.Button,
    txt_input: tk.Text,
    work_dir: str,
    model: str,
    timeout_minutes: int,
    commit_frame: ttk.Frame,
    status_var: tk.StringVar,
):
    """Spawn the aider CLI and record the commit hash it produces."""

    try:
        # Automatically answer "yes" to any prompts so the UI never hangs
        cmd_args = ["aider", "--yes-always", "--model", model, "--message", msg]

        # Indicate that we're waiting on aider to respond and start a simple
        # countdown so the user knows when a timeout will occur.
        status_var.set(
            f"Waiting on aider's response... {timeout_minutes * 60} seconds to timeout"
        )

        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            f"\n> aider --model {model} --message \"{msg}\"\n\n",
        )
        output_widget.see(tk.END)
        output_widget.configure(state="disabled")

        # Stream output back into the widget (no TTY; filter noisy warnings)
        proc = subprocess.Popen(
            cmd_args,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",  # Avoid garbled characters on Windows
            errors="replace",  # Replace any undecodable bytes with '?' to keep output readable
        )

        start_time = time.time()
        commit_id: str | None = None
        failure_reason: str | None = None
        waiting_on_user = False  # Set when aider asks for more information

        def update_countdown():
            """Refresh the status bar every second with remaining time."""

            elapsed = time.time() - start_time
            remaining = int(timeout_minutes * 60 - elapsed)
            # Stop updating once we have a result or are waiting on the user
            if commit_id or failure_reason or waiting_on_user or remaining < 0:
                return
            status_var.set(
                f"Waiting on aider's response... {remaining} seconds to timeout"
            )
            root.after(1000, update_countdown)

        # Kick off the countdown updates
        root.after(1000, update_countdown)

        # Read line-by-line so the UI stays responsive
        for line in proc.stdout:
            if should_suppress(line):
                continue
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, line)
            output_widget.see(tk.END)
            output_widget.configure(state="disabled")

            # Try to extract a commit hash from the stream
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

            # Stop waiting if timeout elapsed without a commit id
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
            # Clear previous console output for readability
            output_widget.configure(state="normal")
            output_widget.delete("1.0", tk.END)
            output_widget.configure(state="disabled")

            # Record commit hash in the history box
            lbl = ttk.Label(commit_frame, text=f"Commit: {commit_id}")
            lbl.pack(anchor="w")
            status_var.set(f"Successfully made changes with commit id {commit_id}")
        elif waiting_on_user:
            # No commit hash yet because aider needs more input. We already
            # updated the status, so just exit without marking an error.
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
    except FileNotFoundError:
        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            "\n[error] Could not find 'aider'. Make sure it's installed and on your PATH.\n",
        )
        output_widget.configure(state="disabled")
        status_var.set("Failed to make commit due to missing 'aider'")
    finally:
        send_btn.config(state="normal")
        txt_input.config(state="normal")
        txt_input.focus_set()


def on_send(event=None):
    raw = txt_input.get("1.0", tk.END)
    if not raw.strip():
        return
    if not work_dir_var.get():
        output.configure(state="normal")
        output.insert(tk.END, "[error] Select a working directory first\n")
        output.configure(state="disabled")
        return
    msg = sanitize(raw)

    send_btn.config(state="disabled")
    txt_input.config(state="disabled")

    model = MODEL_OPTIONS[model_var.get()]
    t = threading.Thread(
        target=run_aider,
        args=(
            msg,
            output,
            send_btn,
            txt_input,
            work_dir_var.get(),
            model,
            timeout_var.get(),  # Minutes to wait for commit id
            commit_frame,
            status_var,
        ),
        daemon=True,
    )
    t.start()

    txt_input.config(state="normal")
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


def on_model_change(*args):
    """Persist model choice whenever the user selects a different option."""
    save_default_model(MODEL_OPTIONS[model_var.get()])


model_var.trace_add("write", on_model_change)

# Input label
lbl = ttk.Label(main, text="What can I do for you today?")
lbl.grid(row=3, column=0, sticky="w", pady=(4, 0))

# Multiline input (Shift+Enter for newline; Enter to send)
txt_input = scrolledtext.ScrolledText(main, width=100, height=6, wrap="word")
txt_input.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(4, 8))
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
status_label = ttk.Label(main, textvariable=status_var)
status_label.grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 6))

# Options row with send button on the right
send_btn = ttk.Button(main, text="Send (Enter)", command=on_send)
send_btn.grid(row=5, column=3, sticky="e", pady=(0, 6))

# Output area where aider output is streamed
output = scrolledtext.ScrolledText(
    main, width=100, height=24, wrap="word", state="disabled"
)
output.grid(row=6, column=0, columnspan=4, sticky="nsew")
main.rowconfigure(6, weight=1)

# Box that collects commit ids for each request
commit_frame = ttk.LabelFrame(main, text="Commit History")
commit_frame.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(6, 0))


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
        send_btn.config(state="disabled")
        return

    try:
        verify_api_key(api_key)
        api_status_label.config(
            text="✓ OpenAI API key verified",
            foreground="green",
            cursor="",
        )
        api_status_label.unbind("<Button-1>")
        send_btn.config(state="normal")
    except Exception as e:
        # Show the failure reason from verify_api_key so the user can fix it
        api_status_label.config(
            text=f"API key: ✗ ({e})", foreground="red", cursor=""
        )
        api_status_label.unbind("<Button-1>")
        send_btn.config(state="disabled")


root.after(0, check_api_key)
root.mainloop()
