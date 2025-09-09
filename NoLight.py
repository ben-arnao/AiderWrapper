import re
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import os
import sys
import time  # Used to track timeout for aider runs
import configparser  # Persist simple settings like timeout
from pathlib import Path  # Resolve path to config file

AIDER_WORKDIR = r"C:\Users\Ben\Desktop\unity\NoLight"

# Path to the config file that stores user adjustable settings
CONFIG_PATH = Path(__file__).with_name("config.ini")

# Lines to quietly ignore from Aider when no TTY is attached
NO_TTY_PATTERNS = [
    r"^Can't initialize prompt toolkit: No Windows console found",
    r"^Terminal does not support pretty output",
]

NO_TTY_REGEXES = [re.compile(pat) for pat in NO_TTY_PATTERNS]

# Regex used to pull a commit hash out of aider's output
COMMIT_RE = re.compile(r"(?:Committed|commit) ([0-9a-f]{7,40})", re.IGNORECASE)


def load_timeout(config_path: Path = CONFIG_PATH) -> int:
    """Return timeout (in minutes) from config file or default to 5."""
    config = configparser.ConfigParser()
    if config_path.exists():
        config.read(config_path)
    # Default timeout is 5 minutes if the setting is missing
    return config.getint("ui", "timeout_minutes", fallback=5)


def save_timeout(value: int, config_path: Path = CONFIG_PATH) -> None:
    """Persist timeout value to the config file."""
    config = configparser.ConfigParser()
    config["ui"] = {"timeout_minutes": str(value)}
    with open(config_path, "w") as fh:
        config.write(fh)


def extract_commit_id(text: str) -> str | None:
    """Return the first commit hash found in the provided text."""
    match = COMMIT_RE.search(text)
    return match.group(1) if match else None

def sanitize(text: str) -> str:
    # Remove newlines & quotes, collapse whitespace
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = text.replace('"', '').replace("'", "")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def should_suppress(line: str) -> bool:
    return any(rx.search(line) for rx in NO_TTY_REGEXES)

def run_aider(msg: str,
              output_widget: scrolledtext.ScrolledText,
              send_btn: ttk.Button,
              txt_input: tk.Text,
              use_external_console: bool,
              timeout_minutes: int,
              commit_frame: ttk.Frame):
    """Run aider and capture the commit id or report a failure."""

    try:
        cmd_args = ["aider", "--model", "gpt-5", "--message", msg]

        output_widget.configure(state="normal")
        output_widget.insert(tk.END, f"\n> aider --model gpt-5 --message \"{msg}\"\n\n")
        output_widget.see(tk.END)
        output_widget.configure(state="disabled")

        if use_external_console:
            # In external console mode we cannot capture aider output,
            # so commit id detection is impossible.
            subprocess.Popen(
                ["cmd.exe", "/c"] + cmd_args,
                cwd=AIDER_WORKDIR,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, "[opened in external console]\n")
            output_widget.insert(tk.END, "[error] Cannot determine commit id in external console mode.\n")
            output_widget.insert(tk.END, "-" * 60 + "\n")
            output_widget.configure(state="disabled")
            return

        # Stream output back into the widget (no TTY; we filter noisy warnings)
        proc = subprocess.Popen(
            cmd_args,
            cwd=AIDER_WORKDIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        start_time = time.time()
        commit_id: str | None = None
        failure_reason: str | None = None

        # Read line-by-line
        for line in proc.stdout:
            if should_suppress(line):
                continue

            output_widget.configure(state="normal")
            output_widget.insert(tk.END, line)
            output_widget.see(tk.END)
            output_widget.configure(state="disabled")

            # Try to find a commit hash in each line
            cid = extract_commit_id(line)
            if cid:
                commit_id = cid

            # Abort if timeout expires without a commit id
            if commit_id is None and time.time() - start_time > timeout_minutes * 60:
                failure_reason = "Timed out waiting for commit id"
                proc.kill()
                break

        proc.wait()

        if commit_id:
            # Clear previous output for this request
            output_widget.configure(state="normal")
            output_widget.delete("1.0", tk.END)
            output_widget.configure(state="disabled")

            # Display commit id in the commit history box
            lbl = ttk.Label(commit_frame, text=f"Commit: {commit_id}")
            lbl.pack(anchor="w")
        else:
            if failure_reason is None:
                failure_reason = "No commit id found"
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, f"\n[error] {failure_reason}\n")
            output_widget.insert(tk.END, f"[exit code: {proc.returncode}]\n")
            output_widget.insert(tk.END, "-" * 60 + "\n")
            output_widget.configure(state="disabled")

    except FileNotFoundError:
        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            "\n[error] Could not find 'aider'. Make sure it's installed and on your PATH.\n",
        )
        output_widget.configure(state="disabled")
    finally:
        send_btn.config(state="normal")
        txt_input.config(state="normal")
        txt_input.focus_set()


def build_ui() -> None:
    """Construct and run the Tkinter UI."""

    root = tk.Tk()
    root.title("Aider Prompt UI")

    main = ttk.Frame(root, padding=8)
    main.grid(row=0, column=0, sticky="nsew")
    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    # Default timeout pulled from config file and stored in a Tk variable
    timeout_var = tk.IntVar(value=load_timeout())

    # Persist timeout whenever the user tweaks the value in the UI
    def on_timeout_change(*args):
        save_timeout(timeout_var.get())

    timeout_var.trace_add("write", on_timeout_change)

    # Allow the main text input column to stretch while others stay fixed
    main.columnconfigure(0, weight=1)
    main.columnconfigure(1, weight=0)
    main.columnconfigure(2, weight=0)
    main.columnconfigure(3, weight=0)

    # Input label
    lbl = ttk.Label(main, text="Message to Aider:")
    lbl.grid(row=0, column=0, sticky="w")

    # Multiline input (Shift+Enter for newline; Enter to send)
    txt_input = scrolledtext.ScrolledText(main, width=100, height=6, wrap="word")
    txt_input.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(4, 8))
    main.rowconfigure(1, weight=0)

    # Options row
    ext_console_var = tk.BooleanVar(value=False)
    ext_chk = ttk.Checkbutton(main, text="Use external console (avoid TTY warnings)", variable=ext_console_var)
    ext_chk.grid(row=2, column=0, sticky="w", pady=(0, 6))

    # User-adjustable timeout in minutes
    timeout_lbl = ttk.Label(main, text="Timeout (min):")
    timeout_lbl.grid(row=2, column=1, sticky="e")

    timeout_spin = ttk.Spinbox(main, from_=1, to=60, textvariable=timeout_var, width=5)
    timeout_spin.grid(row=2, column=2, sticky="w")

    # Output area where aider output is streamed
    output = scrolledtext.ScrolledText(main, width=100, height=24, wrap="word", state="disabled")
    output.grid(row=3, column=0, columnspan=4, sticky="nsew")
    main.rowconfigure(3, weight=1)

    # Box that collects commit ids for each request
    commit_frame = ttk.LabelFrame(main, text="Commit History")
    commit_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(6, 0))

    def on_send(event=None):
        raw = txt_input.get("1.0", tk.END)
        if not raw.strip():
            return
        msg = sanitize(raw)

        # Lock while running
        send_btn.config(state="disabled")
        txt_input.config(state="disabled")

        t = threading.Thread(
            target=run_aider,
            args=(
                msg,
                output,
                send_btn,
                txt_input,
                ext_console_var.get(),
                timeout_var.get(),  # Minutes to wait for commit id
                commit_frame,
            ),
            daemon=True,
        )
        t.start()

        # Clear for next prompt
        txt_input.config(state="normal")
        txt_input.delete("1.0", tk.END)

    def on_return(event):
        # Enter to send; prevent newline
        on_send()
        return "break"

    def on_shift_return(event):
        # Allow newline with Shift+Enter
        return

    txt_input.bind("<Return>", on_return)
    txt_input.bind("<Shift-Return>", on_shift_return)
    txt_input.focus_set()

    send_btn = ttk.Button(main, text="Send (Enter)", command=on_send)
    send_btn.grid(row=2, column=3, sticky="e", pady=(0, 6))

    root.mainloop()


if __name__ == "__main__":
    build_ui()
