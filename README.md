# Aider Prompt UI

A small Tkinter-based interface for sending prompts to the [`aider`](https://github.com/paul-gauthier/aider) CLI.

## Features
- Dropdown to select model quality: **High** (`gpt-5`), **Medium** (`gpt-5-mini`, default), or **Low** (`gpt-5-nano`).
- Working directory chooser that shows the current path and remembers the last selection.
- Multiline text area for composing prompts.
- Startup check that validates the `OPENAI_API_KEY` via a test API call.
- Timeout for detecting the commit ID is adjustable (default 5 minutes) via a gear-icon settings dialog.
- When a commit ID is detected in aider's output, the console is cleared and the commit hash is recorded in a history box so previous runs are easy to review.
- Model and timeout preferences are saved to a small config file so selections persist between sessions.
- A status bar keeps you informed whether the app is waiting on aider's response or for more input, and reports commit outcomes.

## Author
Ben Arnao
