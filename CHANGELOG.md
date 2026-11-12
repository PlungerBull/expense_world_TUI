# Changelog

The format is in scripts/prepare_release.py's docstring.

## Unreleased

Upgrading: the engine must serve contract 3a4ff8dac458cf83 first.
- A statement PDF, or a close, refused for lines in no statement on the days it would close opens a screen listing them: fix a line, put it in the statement, or delete it, then try again.
- Several cash accounts: the New account form always offers cash and the engine names each one `CASH-0001`, `CASH-0002`, …; an empty one can be deleted, and Home lists each under its name.
- `expense` is a release: installed from its own folder with every package at the version CI tested, `scripts/release.py` installs the next one, `back` returns to the previous one and `latest` comes forward again.
