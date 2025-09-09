# Aider Prompt UI

A small Tkinter-based interface for sending prompts to the [`aider`](https://github.com/paul-gauthier/aider) CLI.

## Features
- Dropdown to select model quality: **High** (`gpt-5`), **Medium** (`gpt-5-mini`, default), or **Low** (`gpt-5-nano`).
- Working directory chooser that shows the current path and remembers the last selection.
- Multiline text area for composing prompts.
- Startup check that validates the `OPENAI_API_KEY` via a test API call.
- Timeout for detecting the commit ID is adjustable (default 5 minutes) via a gear-icon settings dialog.
- Each request receives a unique identifier and is logged in a table that shows commit ids, total line and file changes, and any failure reason.
- Timeout preference is saved to a small config file, but the model always defaults to **Medium** on startup.
- The Send button has been removed—press **Enter** to dispatch a prompt.
- A boxed status bar sits between the prompt area and the output, reporting whether we're waiting on aider or the user.
- After a successful commit, the status bar offers a **Test changes** link that builds and launches your Unity project via the command line.
- Output from previous requests remains visible so the full conversation can be reviewed.
- An **API usage** button displays recent spending and remaining credits using the OpenAI billing API.

## Author
Ben Arnao
