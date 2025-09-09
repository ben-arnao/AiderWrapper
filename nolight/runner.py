import subprocess
from typing import Optional, List

import tkinter as tk
from tkinter import ttk

from utils import (
    should_suppress,
    extract_commit_id,
    needs_user_input,
    update_status,
    get_commit_stats,
)

# Track details for each user request so they can be shown in a history table.
request_history: List[dict] = []  # List of per-request summaries
current_request_id: Optional[str] = None  # UUID for the active request
request_active = False  # True while we're waiting on aider to finish


def record_request(
    request_id: str,
    commit_id: Optional[str],
    stats: Optional[dict] = None,
    failure_reason: Optional[str] = None,
    description: str = "",
) -> None:
    """Append a summary of the request to ``request_history``.

    Parameters
    ----------
    request_id:
        Identifier used to link follow-up messages to the same request.
    commit_id:
        Hash of the commit created by aider, or ``None`` if no commit occurred.
    stats:
        Dictionary returned by :func:`utils.get_commit_stats` describing the
        commit. When ``None`` the lines and files counts default to zero.
    failure_reason:
        Text explaining why the request failed, if applicable.
    description:
        Short commit message suitable for display in the history table.
    """

    # Compute totals from stats when available; otherwise fall back to zero.
    lines_total = stats["lines_changed"] if stats else 0
    files_total = 0
    if stats:
        files_total = (
            stats["files_changed"]
            + stats["files_added"]
            + stats["files_removed"]
        )
        description = stats.get("description", description)

    # Store all relevant details so the UI can present them to the user later.
    request_history.append(
        {
            "request_id": request_id,
            "commit_id": commit_id,
            "lines": lines_total,
            "files": files_total,
            "failure_reason": failure_reason,
            "description": description,
        }
    )


def run_aider(
    msg: str,
    output_widget: tk.Text,
    txt_input: tk.Text,
    work_dir: str,
    model: str,
    status_var: tk.StringVar,
    status_label: ttk.Label,
    request_id: str,
) -> None:
    """Spawn the aider CLI and capture commit details.

    All output from aider is streamed into ``output_widget``. When a commit id
    is detected or a failure occurs, a summary of the request is appended to
    ``request_history`` so the user can review past actions.
    """

    global request_active
    # Ensure the status bar is reset for each new request by removing any
    # previous click handlers and cursor styling.
    status_label.config(cursor="")
    status_label.unbind("<Button-1>")

    try:
        # Automatically answer "yes" to any prompts so the UI never hangs.
        cmd_args = ["aider", "--yes-always", "--model", model, "--message", msg]

        # Notify the user that we're awaiting aider's response.
        update_status(status_var, status_label, "Waiting on aider's response...", "black")

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

        commit_id: Optional[str] = None
        failure_reason: Optional[str] = None
        waiting_on_user = False  # Set when aider asks for more information

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

            # If aider asks for more details, stop the process so the user can reply.
            if needs_user_input(line):
                waiting_on_user = True
                update_status(status_var, status_label, "Aider is waiting on our input", "orange")
                proc.kill()
                break

        proc.wait()

        if commit_id:
            try:
                # Query git for stats about the commit so we can store them.
                stats = get_commit_stats(commit_id, work_dir)
                record_request(request_id, commit_id, stats)
                update_status(
                    status_var,
                    status_label,
                    f"Successfully made changes with commit id {commit_id}",
                    "green",
                )
            except Exception as e:
                # If stats collection fails, record the error but keep running.
                record_request(
                    request_id,
                    commit_id,
                    failure_reason=f"stats error: {e}",
                )
                update_status(
                    status_var,
                    status_label,
                    f"Made commit {commit_id} but failed to gather stats",
                    "red",
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
            update_status(
                status_var,
                status_label,
                f"Failed to make commit due to {failure_reason}",
                "red",
            )
            record_request(request_id, None, failure_reason=failure_reason)
            request_active = False
    except FileNotFoundError:
        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            "\n[error] Could not find 'aider'. Make sure it's installed and on your PATH.\n",
        )
        output_widget.configure(state="disabled")
        update_status(
            status_var,
            status_label,
            "Failed to make commit due to missing 'aider'",
            "red",
        )
        record_request(request_id, None, failure_reason="aider not found")
        request_active = False
    finally:
        # Re-enable the input box so the user can type a follow-up or new request.
        txt_input.config(state="normal")
        txt_input.focus_set()

