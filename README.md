# Aider Prompt UI

A small Tkinter-based interface for sending prompts to the [`aider`](https://github.com/paul-gauthier/aider) CLI.

## Features
- Dropdown to select model quality: **High** (`gpt-5`), **Medium** (`gpt-5-mini`, default), or **Low** (`gpt-5-nano`).
- Project directory chooser with basic Unity project verification.
- Multiline text area for composing prompts.
- Startup check that validates the `AIDER_OPENAI_API_KEY` via a test API call.
- Adjustable timeout (default 5 minutes) for detecting the commit ID produced by aider. The timeout is stored in `config.ini` and can be modified from the UI.
- When a commit ID is detected in aider's output, the console is cleared and the commit hash is recorded in a history box so previous runs are easy to review.
