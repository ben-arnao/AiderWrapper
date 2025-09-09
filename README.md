# Aider Prompt UI

A small Tkinter-based interface for sending prompts to the [`aider`](https://github.com/paul-gauthier/aider) CLI.

## Features
- Dropdown to select model quality: **High** (`gpt-5`), **Medium** (`gpt-5-mini`, default), or **Low** (`gpt-5-nano`).
- Working directory chooser that shows the current path and remembers the last selection.
- Multiline text area for composing prompts.
- Startup check that validates the `OPENAI_API_KEY` via a test API call.
- Each request receives a unique identifier and is logged in a table that shows commit ids, total line and file changes, per-request cost, and any failure reason. The history view abbreviates IDs so the table remains compact.
- Failed runs record aider's exit code and last output line so troubleshooting is easier.
- The Send button has been removed—press **Enter** to dispatch a prompt.
- A boxed status bar sits between the prompt area and the output, showing detailed status for each request and whether we're waiting on aider or the user.
- After a successful commit, the status bar offers a **Test changes** link that builds and launches your Unity project via the command line. Configure the Unity Editor path via `config.ini` (`[build] build_cmd`), the `UNITY_PATH` environment variable, or let the app auto-detect a Unity Hub installation.
- Draggable divider lets the prompt area take space from the response area when needed.
- Successful commits highlight the status bar message in green.
- After a successful commit, starting a new request clears prior output so separate conversations don't mix.
- Each request records its cost in dollars and the total session spend is shown in the main window.

## Development Best Practices

- Add tests for functionality changes to verify new behavior.
- Break up and modularize code where possible to reduce merge conflicts.
- Utility helpers live in focused modules (e.g., `utils.text`, `utils.config`)
  so changes stay scoped to their domain.

## Author
Ben Arnao
