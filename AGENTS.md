# Project Rules

- Always read `README.md` before modifying any code.
- After code changes, ensure the README remains accurate. Update it only for high-level goals or design choices.
- Every code change must include meaningful unit tests focusing on core functionality. Avoid low-value tests (e.g., logging or plotting).
- Run the full test suite with coverage (`pytest --cov=. --cov-report=term-missing`). Tests must pass before committing.
- Add inline comments in code and tests explaining behavior in plain English.
- Organize code into sensible modules. Don't create files with only one or two functions unless necessary.
- Use `config.ini` for experiment-related variables (not paths or filenames) and organize them into granular sections.
- Ensure long-running loops handle iteration failures gracefully without terminating the entire process.
- For new or changed behavior, prefer raising explicit exceptions over silent fallbacks.
- Place metrics and plotting utilities in bookkeeping-specific modules or folders.
- When external dependencies are missing, install them so tests run successfully.
