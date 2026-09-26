#!/usr/bin/env python3
"""Report unit-test fixtures that still expect fields the engine no longer serves.

Why this exists: `pytest tests/unit` is respx-mocked, so it validates the CLI
against fixtures *we* wrote, not against the engine. After the 2026-08 rework it
stayed green while pinning several deleted fields — green meant "the CLI agrees
with itself". This closes that gap mechanically: the engine publishes every field
it serves in `openapi.json` (guaranteed since the 2026-08-07 shapes fix), so a
fixture key that appears in no engine schema is either drift or a test-local key.

Deliberately NOT a pytest file. tests/unit is hermetic — `tests/unit/conftest.py`
blocks real sockets on purpose — and that rule is worth more than the convenience
of folding this in. Run it by hand after any engine change:

    python scripts/check_fixture_drift.py
    python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8001

Exit code is 0 when nothing retired is found, 1 otherwise, so it also works as a
gate. It cannot tell a retired engine field from a key a test invented for its own
bookkeeping, so it prints the unknowns and leaves the judgement to a human — see
KNOWN_LOCAL for the ones already triaged.

KNOWN LIMITATION — it unions every schema rather than checking each fixture against
the one endpoint it mocks, so a field that is real *somewhere* passes everywhere.
That is exactly how `cleared` on the inbox fixture survived this check on
2026-08-16: it is real on a transaction, absent from `InboxResponse`, and was found
by reading schemas side by side instead. Tightening this means mapping each fixture
to its endpoint, which the flat `MODULE_RESPONSE = {...}` layout does not encode
today. Until then: a clean run means "no field is dead everywhere", not "every
fixture matches its endpoint".
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

DEFAULT_ENGINE_URL = "http://127.0.0.1:8000"
UNIT_TESTS = Path(__file__).resolve().parent.parent / "tests" / "unit"

# Envelope keys the engine returns that are not schema properties: pagination,
# the error envelope (docs/cli-runtime.md "Engine errors surface cleanly"), and
# the auth/bootstrap wrapper.
ENVELOPE_KEYS = frozenset(
    {
        "items",
        "total",
        "limit",
        "offset",
        "has_more",
        "error",
        "code",
        "message",
        "fields",
        "detail",
        "warnings",
        "user",
        "settings",
        "token",
    }
)

# Keys that are test-local bookkeeping, not engine fields — triaged 2026-08-16.
# Each is a dict key a fixture invents for itself: TUI header stat names, sample
# ids used as dict keys, CLI-side config fields, query-param assertions.
#
# An entry here only earns its place while some fixture still writes that key:
# a dead one silently widens the exemption for whatever key is next to reuse the
# name. tests/unit/test_suite_hygiene.py::test_known_local_exemptions_still_match
# is the guard — it needs no engine, so it runs with the hermetic suite. Eight
# entries had already rotted when it was added on 2026-09-19, one of them citing
# a file deleted on 2026-09-12.
KNOWN_LOCAL = frozenset(
    {
        "cents",
        "unconverted",
        # sample ids used as dict keys in name-map fixtures
        "jan",
        "acc1",
        "acc2",
        "acc3",  # third account in the LOG bar's name-map fixture (quick-add)
        "cat1",
        "cat2",
        "amt",
        # `expense import --json` plan keys: the plan is client-composed (it
        # aggregates many engine calls), so its shape is ours, not the engine's.
        # `source_name` is the raw sheet CUENTA behind a derived account name.
        "source_name",
        # Textual widget geometry, faked by the adaptive-rows tests so
        # `fit_rows` can be measured without an event loop
        "content_size",
        "height",
        # CLI-side config file fields — never sent to the engine
        "engine_url",
        # `expense import bank`'s file→account memory, written into the
        # config file so a second run of the same download needs no --account
        "bank_files",
        "client_id",
        "future_field",
        "verbose",
        # query-param / flag assertions, not response bodies
        "debit_as_negative",
        "hashtag_id",
        "date_from",
        "date_to",
        "to_month",
        "search",
        "currency",
        # 422 `fields` payload keys and respx route names
        "user_settings",
        "count",
        "flag",
        "text",
        "note",
        "dashboard",
        "whoami",
        "ping",
        "log",
        "delete",
        "unexpected",
        "mouse",
        "actor_type",
    }
)

# A quoted dict key: `"some_key":`. Three chars minimum skips `"id":`-style noise
# that is universally valid anyway.
KEY_RE = re.compile(r'"([a-z][a-z0-9_]{2,})"\s*:')


def engine_field_names(engine_url: str) -> set[str]:
    """Every field name the engine declares across all published schemas."""
    url = engine_url.rstrip("/") + "/openapi.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            doc = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        sys.exit(
            f"could not read {url}: {exc}\n"
            "Is the engine running? See ../expense_world_engine/deploy/local/README.md"
        )

    names: set[str] = set()
    for schema in doc.get("components", {}).get("schemas", {}).values():
        names |= set((schema.get("properties") or {}).keys())
    if not names:
        sys.exit(f"{url} published no schema properties — wrong host?")
    return names


def _prose_spans(source: str) -> tuple[set[int], dict[int, int]]:
    """Where a file *talks about* keys rather than writing them.

    `KEY_RE` reads text, not syntax, so a docstring or comment that mentions a
    fixture key (`... a key like "name": ...`) used to be reported as a fixture
    claiming that field. Two showed up the moment the tests grew explanatory
    module docstrings (2026-09-19).

    Returns the doc-comment line numbers to skip outright, plus a per-line
    column where an inline comment starts, so only the comment half of a line
    like `{"name": "x"},  # the "color" key went away` is ignored.

    Narrow on purpose: only a **statement** string is prose. A dict key is a
    string constant too, and skipping those would blind the script to every
    fixture in the suite — which is the whole thing it reads.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(), {}  # a file that will not parse has bigger problems
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                lines |= set(range(node.lineno, (node.value.end_lineno or node.lineno) + 1))

    comment_at: dict[int, int] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                row, col = tok.start
                comment_at[row] = min(col, comment_at.get(row, col))
    except (tokenize.TokenError, IndentationError):
        pass
    return lines, comment_at


def scan_fixtures(known: set[str]) -> dict[str, list[str]]:
    """Map every unknown fixture key to the file:line sites that use it."""
    sites: dict[str, list[str]] = defaultdict(list)
    for path in sorted(UNIT_TESTS.glob("*.py")):
        source = path.read_text()
        prose, comment_at = _prose_spans(source)
        for lineno, line in enumerate(source.splitlines(), 1):
            if lineno in prose:
                continue
            code = line[: comment_at[lineno]] if lineno in comment_at else line
            for key in KEY_RE.findall(code):
                if key not in known:
                    sites[key].append(f"{path.name}:{lineno}")
    return sites


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--engine-url",
        default=DEFAULT_ENGINE_URL,
        help=f"engine to read the contract from (default: {DEFAULT_ENGINE_URL})",
    )
    args = parser.parse_args()

    print(f"reading the engine's own published field list from {args.engine_url} ...")
    known = engine_field_names(args.engine_url) | ENVELOPE_KEYS | KNOWN_LOCAL
    sites = scan_fixtures(known)

    if not sites:
        print("\nno fixture claims a field the engine does not serve.")
        return 0

    print("\nfields the tests still expect, that the engine no longer has:")
    for key in sorted(sites):
        for i, site in enumerate(sorted(sites[key])):
            label = key if i == 0 else ""
            print(f"  {label:<30} {site}")
    print(
        "\nEach is either engine drift (fix the fixture) or a test-local key "
        "(add it to KNOWN_LOCAL, with a note on what it is)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
