# Changelog

The format is in scripts/prepare_release.py's docstring.

## Unreleased

Upgrading: the engine must serve contract 3.1 first.
- A statement PDF, or a close, refused for lines in no statement on the days it would close opens a screen listing them: fix a line, put it in the statement, or delete it, then try again.
- Several cash accounts: the New account form always offers cash and the engine names each one `CASH-0001`, `CASH-0002`, …; an empty one can be deleted, and Home lists each under its name.
- `expense import sheet <file>` opens the app on the import's review: each account the sheet names that you lack, filled from the engine's suggestion and set on the New account form, archived or not; `ctrl+s` asks with the engine's count, and only `y` makes the accounts, categories and hashtags and imports the rows in one write. The app then stays on Home, saying what was imported. `--create-names`, `--apply`, `--account-name` and `--json` are gone, and the sheet names `--account-name` saved are no longer read.
- A bank account's BANK is a code you type and its last 4 is required; the statement code line shows only for a bank whose statement PDFs the engine reads.
- `expense` is a release: installed from its own folder with every package at the version CI tested, `scripts/release.py` installs the next one, `back` returns to the previous one and `latest` comes forward again.

