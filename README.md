# Aider Wrapper UI

This simple Tkinter interface provides a text box for sending prompts to
[aider](https://github.com/paul-gauthier/aider) and displays the tool's
streamed output.

## Features

- Adjustable timeout (default 5 minutes) for detecting the commit ID produced by
  aider. The timeout is stored in `config.ini` and can be modified from the UI.
- When a commit ID is detected in aider's output, the console is cleared and the
  commit hash is recorded in a history box.
- If no commit ID is found before the timeout expires, an error message is
  displayed so failures are obvious.
