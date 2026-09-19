"""The one place the CLI turns a value into JSON.

`--json` is the promise this tool makes to anything that isn't a person, so
the bytes on the other end should not depend on which command produced them.
They used to: thirty-one `json.dumps` calls spelled the same thing out by
hand, and three of them — the bank importer's — passed `ensure_ascii=False`
while the rest did not. So `expense import bank --json` wrote `Café` and
`expense accounts list --json` wrote `Caf\\u00e9`, for the same account, on a
ledger whose names are mostly Spanish.

`ensure_ascii=False` won that argument: the escaped form is valid JSON that no
parser minds and no human can read, and every consumer here is UTF-8. The
error envelope goes through `json_text` too — an error is machine-readable
output like any other, and it carries engine messages with the same accents.
"""

import json
from typing import Any

import typer


def json_text(value: Any, *, sort_keys: bool = False) -> str:
    """Serialise for `--json`: two-space indent, real UTF-8, no key sorting.

    Keys stay in insertion order by default, because for most commands that is
    the engine's own order and re-sorting it would hide the shape the engine
    sent. `expense config show` sorts, since its keys are a settings list with
    no meaningful order of its own.
    """
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=sort_keys)


def emit_json(value: Any, *, sort_keys: bool = False) -> None:
    """Write one JSON document to stdout."""
    typer.echo(json_text(value, sort_keys=sort_keys))
