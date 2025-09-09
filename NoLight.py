import re
import threading
import subprocess
import tkinter as tk
from tkinter import ttk
from tkinter import scrolledtext
import os
import sys

AIDER_WORKDIR = r"C:\Users\Ben\Desktop\unity\NoLight"

# Lines to quietly ignore from Aider when no TTY is attached
NO_TTY_PATTERNS = [
    r"^Can't initialize prompt toolkit: No Windows console found",
    r"^Terminal does not support pretty output",
]

NO_TTY_REGEXES = [re.compile(pat) for pat in NO_TTY_PATTERNS]

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
              use_external_console: bool):
    try:
        cmd_args = ["aider", "--model", "gpt-5", "--message", msg]

        output_widget.configure(state="normal")
        output_widget.insert(tk.END, f"\n> aider --model gpt-5 --message \"{msg}\"\n\n")
        output_widget.see(tk.END)
        output_widget.configure(state="disabled")

        if use_external_console:
            # Launch in a separate console so Aider has a real TTY
            # (no streamed output back to the app in this mode).
            subprocess.Popen(
                ["cmd.exe", "/c"] + cmd_args,
                cwd=AIDER_WORKDIR,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            output_widget.configure(state="normal")
            output_widget.insert(tk.END, "[opened in external console]\n")
            output_widget.insert(tk.END, "-"*60 + "\n")
            output_widget.configure(state="disabled")

        else:
            # Stream output back into the widget (no TTY; we filter noisy warnings)
            proc = subprocess.Popen(
                cmd_args,
                cwd=AIDER_WORKDIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Read line-by-line
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
            output_widget.insert(tk.END, "-"*60 + "\n")
            output_widget.see(tk.END)
            output_widget.configure(state="disabled")

    except FileNotFoundError:
        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            "\n[error] Could not find 'aider'. Make sure it's installed and on your PATH.\n"
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
    msg = sanitize(raw)

    # Lock while running
    send_btn.config(state="disabled")
    txt_input.config(state="disabled")

    t = threading.Thread(
        target=run_aider,
        args=(msg, output, send_btn, txt_input, ext_console_var.get()),
        daemon=True
    )
    t.start()

    # Clear for next prompt
    txt_input.config(state="normal")
    txt_input.delete("1.0", tk.END)

# ---- UI ----
root = tk.Tk()
root.title("Aider Prompt UI")

main = ttk.Frame(root, padding=8)
main.grid(row=0, column=0, sticky="nsew")
root.rowconfigure(0, weight=1)
root.columnconfigure(0, weight=1)

# Input label
lbl = ttk.Label(main, text="Message to Aider:")
lbl.grid(row=0, column=0, sticky="w")

# Multiline input (Shift+Enter for newline; Enter to send)
txt_input = scrolledtext.ScrolledText(main, width=100, height=6, wrap="word")
txt_input.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 8))
main.rowconfigure(1, weight=0)

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

# Options row
ext_console_var = tk.BooleanVar(value=False)
ext_chk = ttk.Checkbutton(main, text="Use external console (avoid TTY warnings)", variable=ext_console_var)
ext_chk.grid(row=2, column=0, sticky="w", pady=(0, 6))

send_btn = ttk.Button(main, text="Send (Enter)", command=on_send)
send_btn.grid(row=2, column=1, sticky="e", pady=(0, 6))

# Output area
output = scrolledtext.ScrolledText(main, width=100, height=24, wrap="word", state="disabled")
output.grid(row=3, column=0, columnspan=2, sticky="nsew")
main.rowconfigure(3, weight=1)

root.mainloop()
