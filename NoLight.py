import threading
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
import os
import configparser

from utils import sanitize, should_suppress, verify_unity_project, verify_api_key

# Map human-friendly names to actual model identifiers
MODEL_OPTIONS = {
    "High": "gpt-5",
    "Medium": "gpt-5-mini",
    "Low": "gpt-5-nano",
}

# Read default model from config.ini
config = configparser.ConfigParser()
config.read("config.ini")
DEFAULT_MODEL = config.get("aider", "default_model", fallback="gpt-5-mini")
DEFAULT_CHOICE = next((k for k, v in MODEL_OPTIONS.items() if v == DEFAULT_MODEL), "Medium")


def run_aider(
    msg: str,
    output_widget: scrolledtext.ScrolledText,
    send_btn: ttk.Button,
    txt_input: tk.Text,
    use_external_console: bool,
    project_dir: str,
    model: str,
):
    """Spawn the aider CLI and stream output back into the UI."""
    try:
        cmd_args = ["aider", "--model", model, "--message", msg]

        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            f"\n> aider --model {model} --message \"{msg}\"\n\n",
        )
        output_widget.see(tk.END)
        output_widget.configure(state="disabled")

        if use_external_console:
            # Launch in a separate console so Aider has a real TTY
            subprocess.Popen(
                ["cmd.exe", "/c"] + cmd_args,
                cwd=project_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, "[opened in external console]\n")
            output_widget.insert(tk.END, "-" * 60 + "\n")
            output_widget.configure(state="disabled")
        else:
            # Stream output back into the widget (no TTY; filter noisy warnings)
            proc = subprocess.Popen(
                cmd_args,
                cwd=project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Read line-by-line so the UI stays responsive
            for line in proc.stdout:
                if should_suppress(line):
                    continue
                output_widget.configure(state="normal")
                output_widget.insert(tk.END, line)
                output_widget.see(tk.END)
                output_widget.configure(state="disabled")

            proc.wait()
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, f"\n[exit code: {proc.returncode}]\n")
            output_widget.insert(tk.END, "-" * 60 + "\n")
            output_widget.see(tk.END)
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


def on_send(event=None):
    raw = txt_input.get("1.0", tk.END)
    if not raw.strip():
        return
    if not project_dir_var.get():
        output.configure(state="normal")
        output.insert(tk.END, "[error] Select a Unity project first\n")
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
            ext_console_var.get(),
            project_dir_var.get(),
            model,
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

# API key status label
api_status_label = ttk.Label(main, text="API key: checking...", foreground="orange")
api_status_label.grid(row=0, column=0, columnspan=2, sticky="w")

# Project directory selector
project_dir_var = tk.StringVar(value="")

def choose_dir():
    path = filedialog.askdirectory()
    if path:
        if verify_unity_project(path):
            project_dir_var.set(path)
            dir_status_label.config(text="✓", foreground="green")
        else:
            project_dir_var.set("")
            dir_status_label.config(text="✗", foreground="red")

dir_btn = ttk.Button(main, text="Select Unity Project", command=choose_dir)

dir_btn.grid(row=1, column=0, sticky="w", pady=(4, 0))

dir_status_label = ttk.Label(main, text="", width=2)
dir_status_label.grid(row=1, column=1, sticky="w", pady=(4, 0))

# Model selection dropdown
model_var = tk.StringVar(value=DEFAULT_CHOICE)
model_label = ttk.Label(main, text="Model:")
model_label.grid(row=2, column=0, sticky="e", pady=(4, 0))
model_combo = ttk.Combobox(
    main,
    textvariable=model_var,
    values=list(MODEL_OPTIONS.keys()),
    state="readonly",
)
model_combo.grid(row=2, column=1, sticky="w", pady=(4, 0))

# Input label
lbl = ttk.Label(main, text="Message to Aider:")
lbl.grid(row=3, column=0, sticky="w", pady=(4, 0))

# Multiline input (Shift+Enter for newline; Enter to send)
txt_input = scrolledtext.ScrolledText(main, width=100, height=6, wrap="word")
txt_input.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(4, 8))
main.rowconfigure(4, weight=0)


def on_return(event):
    on_send()
    return "break"


def on_shift_return(event):
    return


txt_input.bind("<Return>", on_return)
txt_input.bind("<Shift-Return>", on_shift_return)
txt_input.focus_set()

# Options row
ext_console_var = tk.BooleanVar(value=False)
ext_chk = ttk.Checkbutton(
    main,
    text="Use external console (avoid TTY warnings)",
    variable=ext_console_var,
)
ext_chk.grid(row=5, column=0, sticky="w", pady=(0, 6))

send_btn = ttk.Button(main, text="Send (Enter)", command=on_send)
send_btn.grid(row=5, column=1, sticky="e", pady=(0, 6))

# Output area
output = scrolledtext.ScrolledText(
    main, width=100, height=24, wrap="word", state="disabled"
)
output.grid(row=6, column=0, columnspan=2, sticky="nsew")
main.rowconfigure(6, weight=1)


def check_api_key():
    try:
        verify_api_key(os.environ.get("AIDER_OPENAI_API_KEY"))
        api_status_label.config(text="API key: ✓", foreground="green")
    except Exception:
        api_status_label.config(text="API key: ✗", foreground="red")
        send_btn.config(state="disabled")


root.after(0, check_api_key)
root.mainloop()
