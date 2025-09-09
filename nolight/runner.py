import subprocess
import time
from typing import Optional, List

import tkinter as tk
from tkinter import scrolledtext, ttk

from utils import (
    should_suppress,
    extract_commit_id,
    extract_cost,
    needs_user_input,
    get_commit_stats,
    build_and_launch_game,
)

# Track details for each user request so they can be shown in a history table.
request_history: List[dict] = []  # List of per-request summaries
current_request_id: Optional[str] = None  # UUID for the active request
request_active = False  # True while we're waiting on aider to finish
session_cost = 0.0  # Total dollars spent during this app session
session_cost_var: Optional[tk.StringVar] = None  # Label for displaying session cost


def record_request(
    request_id: str,
    commit_id: Optional[str],
    stats: Optional[dict] = None,
    failure_reason: Optional[str] = None,
    description: str = "",
    cost: Optional[float] = None,
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
    cost:
        Dollar amount reported by aider for this request, if any.
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
            "cost": cost,
            "failure_reason": failure_reason,
            "description": description,
        }
    )

    # Update the running session cost and reflect it in the UI label.
    global session_cost
    if cost is not None:
        session_cost += cost
        if session_cost_var is not None:
            session_cost_var.set(f"${session_cost:.2f} spent this session")


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
    root: tk.Tk,
) -> None:
    """Spawn the aider CLI and capture commit details.

    All output from aider is streamed into ``output_widget``. When a commit id
    is detected or a failure occurs, a summary of the request is appended to
    ``request_history`` so the user can review past actions.
    """

    global request_active
    # Remove any previous "test changes" link before starting a new request
    status_label.config(foreground="black", cursor="")
    status_label.unbind("<Button-1>")

    request_cost: Optional[float] = None  # Dollars reported by aider

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

        # Kick off the countdown updates using the Tk root from the caller.
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

            # Capture any cost reported by aider for this request.
            cost = extract_cost(line)
            if cost is not None:
                request_cost = cost

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
                record_request(request_id, commit_id, stats, cost=request_cost)
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
                record_request(
                    request_id,
                    commit_id,
                    failure_reason=f"stats error: {e}",
                    cost=request_cost,
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
            record_request(request_id, None, failure_reason=failure_reason, cost=request_cost)
            request_active = False
    except FileNotFoundError:
        output_widget.configure(state="normal")
        output_widget.insert(
            tk.END,
            "\n[error] Could not find 'aider'. Make sure it's installed and on your PATH.\n",
        )
        output_widget.configure(state="disabled")
        status_var.set("Failed to make commit due to missing 'aider'")
        record_request(request_id, None, failure_reason="aider not found", cost=request_cost)
        request_active = False
    finally:
        # Re-enable the input box so the user can type a follow-up or new request.
        txt_input.config(state="normal")
        txt_input.focus_set()
