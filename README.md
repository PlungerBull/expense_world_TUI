# expense_world_TUI

The Hands — a Textual TUI over the `expense_world_engine` HTTP API (local, `http://127.0.0.1:8000`, set as `engine_url` in `~/.expense-config`), plus one typed command for the owner's spreadsheet. Every screen is a thin wrapper around engine endpoints; zero business logic lives here.

See [CLAUDE.md](CLAUDE.md) for conventions, [docs/commands.md](docs/commands.md) for the typed surface, and [docs/README.md](docs/README.md) for the index of every other doc.

> **Checkout layout:** the engine repo is a sibling checkout, and the practice engine runs from it ([docs/runtime.md](docs/runtime.md) "Working against the live engine"). No agent reads a file in it and the docs never link into it: the engine contract is read live from `GET /openapi.json` on a running engine ([CLAUDE.md](CLAUDE.md) "Key documentation", "Stay inside this repo").
>
> ```
> <anything>/
> ├── expense_world_TUI/      ← this repo
> └── expense_world_engine/   ← engine (the practice engine runs from here)
> ```

## Install (the owner's app)

The app the owner types is a release, installed from the live folder, never the folder agents edit. What each release holds is in [CHANGELOG.md](CHANGELOG.md).

One time:

1. Create `develop` from `main` and push it, in the work folder.
2. Clone the repo into `~/Library/Application Support/expense_world/tui`, on `main`.
3. `pipx uninstall expense-cli-menu`
4. In the live folder, `python3 scripts/release.py`: the first release.

After that, `python3 scripts/release.py` releases, `… back` goes to the previous release and `… latest` returns. The docstring of [scripts/release.py](scripts/release.py) says what each does and refuses.

## Install (dev)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
```

## Usage

```bash
expense                       # the app (asks for the engine address and key the first time)
expense import sheet <file>   # the spreadsheet import (a dry run; --create-names, then --apply)
```
