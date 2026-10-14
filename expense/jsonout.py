"""The one place a value becomes JSON for the terminal.

`expense import sheet --json` and the error envelope both go through here, so
the bytes do not depend on which path produced them.

`ensure_ascii=False` is the choice: the escaped form is valid JSON that no
parser minds and no human can read, and every consumer here is UTF-8. The
error envelope goes through `json_text` too — an error is machine-readable
output like any other, and it carries engine messages with the same accents
on a ledger whose names are mostly Spanish.
"""

import json
from typing import Any

import typer


def json_text(value: Any) -> str:
    """Serialise for `--json`: two-space indent, real UTF-8, keys in insertion order."""
    return json.dumps(value, indent=2, ensure_ascii=False)


def emit_json(value: Any) -> None:
    """Write one JSON document to stdout."""
    typer.echo(json_text(value))
