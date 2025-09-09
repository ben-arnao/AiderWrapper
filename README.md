# Aider Prompt UI

A small Tkinter-based interface for sending prompts to the [`aider`](https://github.com/paul-gauthier/aider) CLI.

## Features
- Dropdown to select model quality: **High** (`gpt-5`), **Medium** (`gpt-5-mini`, default), or **Low** (`gpt-5-nano`).
- Working directory chooser that shows the current path and remembers the last selection.
- Multiline text area for composing prompts.
- Startup check that validates the `OPENAI_API_KEY` via a test API call.
- Timeout for detecting the commit ID is adjustable (default 5 minutes) via a gear-icon settings dialog.
- Each request receives a unique identifier and is logged in a table that shows commit ids, total line and file changes, and any failure reason. The history view abbreviates IDs so the table remains compact.
- Timeout preference is saved to a small config file, but the model always defaults to **Medium** on startup.
- The Send button has been removed—press **Enter** to dispatch a prompt.
- A boxed status bar sits between the prompt area and the output, reporting whether we're waiting on aider or the user.
- After a successful commit, the status bar offers a **Test changes** link that builds and launches your Unity project via the command line. Ensure the Unity CLI is installed and available on your `PATH` so the build step can run.
- Output from previous requests remains visible so the full conversation can be reviewed.
- Each request's cost is tracked by parsing aider's output, with a running total shown in the UI.

## Development Best Practices

- Add tests for functionality changes to verify new behavior.
- Break up and modularize code where possible to reduce merge conflicts.

## Author
Ben Arnao
