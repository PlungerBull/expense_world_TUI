# expense_CLI_menu

The Hands — a Python (Typer) CLI and Textual TUI over the `expense_world_engine` HTTP API (local, `http://127.0.0.1:8000`, set as `engine_url` in `~/.expense-config`). Every command is a thin wrapper around engine endpoints; zero business logic lives here.

See [CLAUDE.md](CLAUDE.md) for conventions, [docs/cli-spec.md](docs/cli-spec.md) for the command surface, [docs/tui.md](docs/tui.md) for the TUI, [docs/todo.md](docs/todo.md) for what is still open, and [docs/decisions.md](docs/decisions.md) for why the big calls went the way they did.

> **Checkout layout:** the engine repo is a sibling checkout; the tester starts and reseeds the practice engine from it ([docs/cli-runtime.md](docs/cli-runtime.md) "Working against the live engine"). The docs never link into it: the engine contract is read live from `GET /openapi.json` on a running engine ([CLAUDE.md](CLAUDE.md) "Key documentation").
>
> ```
> <anything>/
> ├── expense_world_CLI/      ← this repo
> └── expense_world_engine/   ← engine (the practice engine runs from here)
> ```

## Install (dev)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" -c constraints.txt
```

## Usage

```bash
expense --help    # flat commands
expense world     # interactive TUI
```
