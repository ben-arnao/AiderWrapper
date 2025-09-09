"""Entry point for the Aider Prompt UI.

This thin wrapper delegates to the :mod:`nolight.app` module, which contains
all UI setup code. Keeping this file small helps avoid merge conflicts in the
main application logic.
"""

from nolight.app import main


if __name__ == "__main__":
    # Build the Tk interface and start the event loop.
    main()
