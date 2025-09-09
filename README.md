# Aider Prompt UI

A small Tkinter-based interface for sending prompts to the [`aider`](https://github.com/paul-gauthier/aider) CLI.

## Features
- Dropdown to select model quality: **High** (`gpt-5`), **Medium** (`gpt-5-mini`, default), or **Low** (`gpt-5-nano`).
- Project directory chooser with basic Unity project verification.
- Multiline text area for composing prompts.
- Startup check that validates the `AIDER_OPENAI_API_KEY` via a test API call.
