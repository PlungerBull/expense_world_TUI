#!/usr/bin/env python3
"""Check the engine's contract version and report fixtures the engine no longer serves.

Why this exists: `pytest tests/unit` is respx-mocked, so it validates the app
against fixtures *we* wrote, not against the engine. It can stay green while
pinning deleted fields — green means "the app agrees with itself". This closes
that gap mechanically: the engine publishes its whole contract at
`/openapi.json`, so a fixture key that appears in no engine schema is either
drift or a test-local key.

Deliberately NOT a pytest file. tests/unit is hermetic — `tests/unit/conftest.py`
blocks real sockets on purpose — and that rule is worth more than the convenience
of folding this in. Run it by hand after any engine change:

    python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002

The default target is the practice engine, `http://127.0.0.1:8002`; the flag only
makes the target explicit.

CONTRACT VERSION. Every run also compares the engine's `info.version` with the one
saved in `scripts/engine-contract-version`, fails when they differ and prints what
moved; the rules live in docs/runtime.md "Contract version". Saving a new
version is its own step:

    python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002 --record-version

REQUIRED FIELDS. A fixture builder in tests/unit/helpers.py marked with
`answer_of(METHOD, PATH)` declares the endpoint whose answer it stands for, and lands
in `ANSWER_BUILDERS`. Every run calls each one with no arguments and reports each
field the contract marks `required` on that endpoint's 2xx JSON answer that the
bare answer leaves out, inside nested objects and list items too wherever the
answer holds one and the contract names a single object schema for it. An endpoint
the contract no longer holds, or holds without a JSON answer, is reported as well.
The marker asserts on every call that a test's answer keeps every key of the bare
one, so what the script checked is what each test gets.

Exit code is 0 when the version matches, nothing retired is found and no marked
answer misses a required field, 1 otherwise, so it also works as a gate. It cannot
tell a retired engine field from a key a test invented for its own bookkeeping, so
it prints the unknowns and leaves the judgement to a human — see KNOWN_LOCAL for the
ones already triaged.

KNOWN LIMITATION — the unknown-key scan unions every schema rather than checking
each fixture against the one endpoint it mocks, so a field that is real *somewhere*
passes everywhere: a field real on a transaction but absent from another response
passes. Only the builders marked with `answer_of` are tied to an endpoint, and for
them only the required fields are checked, not unknown keys; a fixture no marked
builder makes (a dict written in a test, `FakeClient`'s `{}`) is checked for
neither. A nested object or list is checked only where the bare answer holds one,
so a value a test passes in place of a `None` (a `twin`, a `coverage_gap`) is not.
So a clean run means "no field is dead everywhere, and every marked answer carries
what its endpoint requires", not "every fixture matches its endpoint".
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import httpx

DEFAULT_ENGINE_URL = "http://127.0.0.1:8002"
REPO = Path(__file__).resolve().parent.parent
UNIT_TESTS = REPO / "tests" / "unit"
#: The contract version this repo was last checked against: one line, nothing else.
SAVED_VERSION_FILE = Path(__file__).resolve().parent / "engine-contract-version"

# Envelope keys the engine returns that are not schema properties: the list
# envelopes (whole `{items}`, cursor `{items, limit, next_cursor}`), the error envelope
# (docs/runtime.md "Engine errors surface cleanly"), and the auth/bootstrap
# wrapper.
ENVELOPE_KEYS = frozenset(
    {
        "items",
        "limit",
        "next_cursor",
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

# Keys that are test-local bookkeeping, not engine fields.
# Each is a dict key a fixture invents for itself: TUI header stat names, sample
# ids used as dict keys, client-side config fields, query-param assertions.
#
# An entry here only earns its place while some fixture still writes that key:
# a dead one silently widens the exemption for whatever key is next to reuse the
# name. tests/unit/test_suite_hygiene.py::test_known_local_exemptions_still_match
# is the guard — it needs no engine, so it runs with the hermetic suite.
KNOWN_LOCAL = frozenset(
    {
        "cents",
        "unconverted",
        # sample ids used as dict keys in name-map fixtures
        "acc1",
        "acc2",
        "acc3",  # third account in the LOG bar's name-map fixture (quick-add)
        "cat1",
        "cat2",
        "pend",  # the pending category's sample id in the ledger-filter name map
        # the delete tests' table of management screens, keyed by screen name
        "accounts",
        "hashtags",
        # the launch tests' record of whether the app opened on the setup screen
        "setup",
        # `expense import sheet --json` plan keys: the plan is client-composed (it
        # aggregates many engine calls), so its shape is ours, not the engine's.
        # `source_name` is the raw sheet CUENTA behind a derived account name.
        "source_name",
        # a `skipped` entry's sheet line number and why the row was left out
        # (`bad-amount`, ...); the import's own row checks write them, not the engine
        "line",
        "reason",
        # Textual widget geometry, faked by the adaptive-rows tests so
        # `fit_rows` can be measured without an event loop
        "content_size",
        "height",
        # a keyword of Textual's `notify` call the TUI tests record and check
        # (`{"title": "Failed", "severity": "error"}`), not an engine field
        "severity",
        # client-side config file fields — never sent to the engine
        "engine_url",
        # the renames `expense import sheet` remembers per sheet account
        "sheet_account_names",
        # a config key no Config field holds: the stale-config load test
        # writes it on purpose to prove an unknown key loads and is dropped
        "bank_files",
        "client_id",
        "future_field",
        "verbose",
        # query-param / flag assertions, not response bodies
        "debit_as_negative",
        "date_from",
        "currency",
        # 422 `fields` payload keys and respx route names
        "user_settings",
        "count",
        "dashboard",
        "delete",
        "unexpected",
        "mouse",
        # the Python keyword names a fake's call log records for
        # fetch_transactions / count_transactions (the wire names are
        # account_id, category_id, hashtag_id)
        "account",
        "category",
        "hashtag",
        # the reconciliation form's internal value key for the beginning balance
        "begin",
        # Home's own data dict: the month grid the app builds from the
        # dashboard's `months` (formatting.build_range_grid), not an engine field
        "grid",
        # a fake cursor value the paging tests hand back
        "c10",
        # Textual key names the import door's footer-binding asserts look up
        "enter",
        "escape",
        # the list each xdist worker hands the controller for the error-shape
        # guard (tests/unit/conftest.py), not an engine field
        "error_tested",
        # the ways a line-read test leaves the ledger (`esc`, or another screen
        # over it), compared as `if how == "left":`, which reads like a dict key
        "covered",
        "left",
    }
)

# Unit-test files whose dicts are not engine fixtures, so the scan skips them.
# test_claude_hooks.py builds Claude Code hook payloads (`tool_name`, `tool_input`,
# `cwd`, ...) for the repo's guard hooks; none of them mocks the engine.
NOT_FIXTURES = frozenset({"test_claude_hooks.py"})

# A quoted dict key: `"some_key":`. Three chars minimum skips `"id":`-style noise
# that is universally valid anyway.
KEY_RE = re.compile(r'"([a-z][a-z0-9_]{2,})"\s*:')


def fetch_contract(engine_url: str) -> dict:
    """The engine's published contract, `GET /openapi.json`."""
    url = engine_url.rstrip("/") + "/openapi.json"
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        doc = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        sys.exit(
            f"could not read {url}: {exc}\n"
            'Is the engine running? See docs/runtime.md "Working against the live engine"'
        )
    if not isinstance(doc, dict):
        sys.exit(f"{url} did not return a JSON object — wrong host?")
    return doc


def contract_version(doc: dict, engine_url: str) -> str:
    """`info.version` of the contract; a contract without one is not the engine's."""
    info = doc.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(version, str) or not version.strip():
        sys.exit(f"{engine_url} published no info.version — wrong host?")
    return version.strip()


def read_saved_version() -> str | None:
    """The saved contract version, or None when none is recorded."""
    try:
        text = SAVED_VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return None
    return text or None


def version_problem(doc: dict, saved: str | None, engine: str, engine_url: str) -> str | None:
    """What differs between the saved and the engine's version; None when they match.

    A moved version carries the contract's change-log entries newer than `saved`."""
    record = f"python scripts/check_fixture_drift.py --engine-url {engine_url} --record-version"
    if saved is None:
        return (
            f"no saved contract version: scripts/{SAVED_VERSION_FILE.name} is missing or "
            f"empty (the engine reports {engine}).\n"
            f"Record one with: {record}"
        )
    if saved != engine:
        return (
            f"the engine's contract version has changed: saved {saved}, engine {engine}.\n"
            f"{changes_report(doc, saved, engine)}\n"
            f"Once the change is handled, record the new version with: {record}"
        )
    return None


def changes_since(doc: dict, saved: str, engine: str) -> list[dict] | None:
    """The contract's change-log entries newer than `saved`, newest first.

    Reads `x-changelog`, which lists the released versions newest first, one entry
    each, its first entry being the current `engine` version; a listed version is
    never removed, and a version an engine serves might never be listed
    (contract: "Base Conventions", "The contract"). None means the whole contract
    is to be treated as changed: the log is absent or malformed, its first entry
    is not `engine`, or `saved` is not in it."""
    log = doc.get("x-changelog")
    if not isinstance(log, list) or not log:
        return None
    if not isinstance(log[0], dict) or log[0].get("version") != engine:
        return None
    newer: list[dict] = []
    for entry in log:
        if not isinstance(entry, dict) or not isinstance(entry.get("version"), str):
            return None
        if entry["version"] == saved:
            return newer
        changes = entry.get("changes")
        if not isinstance(entry.get("date"), str) or not isinstance(changes, list):
            return None
        for change in changes:
            if not isinstance(change, dict) or not all(
                isinstance(change.get(k), str) for k in ("kind", "text")
            ):
                return None
        newer.append(entry)
    return None


def changes_report(doc: dict, saved: str, engine: str) -> str:
    """What the contract's own change log says moved since `saved`, as printable text."""
    entries = changes_since(doc, saved, engine)
    if entries is None:
        return (
            f"the contract's change log (x-changelog) is missing, unreadable, does not start "
            f"at engine version {engine}, or does not list saved version {saved}, so the "
            "whole contract changed."
        )
    lines = [f"what the contract changed since {saved}, newest first:"]
    for entry in entries:
        lines.append(f"  {entry['version']}  {entry['date']}")
        lines += [f"    {change['kind']}: {change['text']}" for change in entry["changes"]]
    return "\n".join(lines)


def engine_field_names(doc: dict, engine_url: str) -> set[str]:
    """Every field name the engine declares across all published schemas, plus
    every query-parameter name it declares on any path.

    The parameters are there because the tests also assert on what a request
    *sent* (`params["sort"]`, a fake's call log), and those dict keys are engine
    names too. Reading them from the contract, instead of listing them by hand,
    means a parameter the engine drops is reported like a dropped field."""
    names: set[str] = set()
    for schema in doc.get("components", {}).get("schemas", {}).values():
        names |= set((schema.get("properties") or {}).keys())
    if not names:
        sys.exit(f"{engine_url} published no schema properties — wrong host?")
    return names | _query_parameter_names(doc)


def _query_parameter_names(doc: dict) -> set[str]:
    """`parameters[].name` for every `in: query` parameter, path- or operation-level."""
    shared = doc.get("components", {}).get("parameters", {})
    names: set[str] = set()
    for item in doc.get("paths", {}).values():
        groups = [item.get("parameters") or []]
        groups += [op.get("parameters") or [] for op in item.values() if isinstance(op, dict)]
        for group in groups:
            for param in group:
                if "$ref" in param:  # `#/components/parameters/<name>`
                    param = shared.get(param["$ref"].rsplit("/", 1)[-1], {})
                if param.get("in") == "query" and param.get("name"):
                    names.add(param["name"])
    return names


def _prose_spans(source: str) -> tuple[set[int], dict[int, int]]:
    """Where a file *talks about* keys rather than writing them.

    `KEY_RE` reads text, not syntax, so a docstring or comment that mentions a
    fixture key (`... a key like "name": ...`) would be reported as a fixture
    claiming that field.

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
        if path.name in NOT_FIXTURES:
            continue
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


def answer_builders() -> dict[str, Callable[[], object]]:
    """The builders tests/unit/helpers.py marks with `answer_of`, keyed `METHOD /v1/path`."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from tests.unit import helpers

    return dict(helpers.ANSWER_BUILDERS)


def _resolve(doc: dict, schema: object) -> dict:
    """`schema` with its `$ref` (`#/components/schemas/<name>`) followed; {} when unusable."""
    if not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if isinstance(ref, str):
        found = doc.get("components", {}).get("schemas", {}).get(ref.rsplit("/", 1)[-1])
        return found if isinstance(found, dict) else {}
    return schema


def _members(schema: dict) -> list | None:
    """The `anyOf` or `oneOf` members of a resolved schema; None when it has neither."""
    members = schema.get("anyOf") or schema.get("oneOf")
    return members if isinstance(members, list) else None


def _object_schema(doc: dict, schema: object) -> dict | None:
    """The one object schema `schema` allows, through `$ref` and `anyOf`/`oneOf`; None
    when it allows none, or more than one, so the check never guesses between them."""
    schema = _resolve(doc, schema)
    members = _members(schema)
    if members is not None:
        objects = [found for m in members if (found := _object_schema(doc, m)) is not None]
        return objects[0] if len(objects) == 1 else None
    return schema if "properties" in schema or "required" in schema else None


def _list_items(doc: dict, schema: object) -> object | None:
    """The `items` schema of the one array schema `schema` allows; None when none."""
    schema = _resolve(doc, schema)
    members = _members(schema)
    if members is not None:
        arrays = [found for m in members if (found := _list_items(doc, m)) is not None]
        return arrays[0] if len(arrays) == 1 else None
    return schema.get("items") if schema.get("type") == "array" else None


def answer_schema(doc: dict, endpoint: str) -> dict | None:
    """The object schema of `endpoint`'s 2xx JSON answer, `endpoint` being `METHOD
    /v1/path`; None when the contract holds no such operation or answer."""
    method, _, path = endpoint.partition(" ")
    item = doc.get("paths", {}).get(path)
    op = item.get(method.lower()) if isinstance(item, dict) else None
    if not isinstance(op, dict):
        return None
    for code, response in sorted((op.get("responses") or {}).items()):
        if str(code).startswith("2") and isinstance(response, dict):
            content = (response.get("content") or {}).get("application/json") or {}
            if "schema" in content:
                return _object_schema(doc, content["schema"])
    return None


def missing_required(doc: dict, schema: dict, value: object, where: str = "") -> list[str]:
    """Each field `schema` requires that `value` leaves out, as a dotted path
    (`coverage_gap.unfiled_count`, `items[0].id`), nested objects and list items
    included wherever `value` holds one and the contract names one object schema."""
    if not isinstance(value, dict):
        return []
    prefix = f"{where}." if where else ""
    missing = [f"{prefix}{name}" for name in schema.get("required") or [] if name not in value]
    for name, sub in (schema.get("properties") or {}).items():
        held = value.get(name)
        if isinstance(held, dict):
            nested = _object_schema(doc, sub)
            if nested is not None:
                missing += missing_required(doc, nested, held, f"{prefix}{name}")
        elif isinstance(held, list):
            nested = _object_schema(doc, _list_items(doc, sub))
            if nested is not None:
                for i, entry in enumerate(held):
                    missing += missing_required(doc, nested, entry, f"{prefix}{name}[{i}]")
    return missing


def required_problems(doc: dict, builders: dict[str, Callable[[], object]]) -> list[str]:
    """One printable line per required field a marked answer leaves out, and one per
    marked endpoint the contract does not answer with a JSON object."""
    problems: list[str] = []
    for endpoint, builder in sorted(builders.items()):
        name = getattr(builder, "__name__", repr(builder))
        schema = answer_schema(doc, endpoint)
        if schema is None:
            problems.append(f"  {endpoint}: the contract holds no JSON answer for it ({name})")
            continue
        for field in missing_required(doc, schema, builder()):
            problems.append(f"  {endpoint}: {field} ({name})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--engine-url",
        default=DEFAULT_ENGINE_URL,
        help=f"engine to read the contract from (default: {DEFAULT_ENGINE_URL})",
    )
    parser.add_argument(
        "--record-version",
        action="store_true",
        help=(
            f"save the engine's current contract version to scripts/{SAVED_VERSION_FILE.name} "
            "and check nothing else"
        ),
    )
    args = parser.parse_args(argv)

    print(f"reading the engine's published contract from {args.engine_url} ...")
    doc = fetch_contract(args.engine_url)
    engine_version = contract_version(doc, args.engine_url)

    if args.record_version:
        saved = read_saved_version()
        SAVED_VERSION_FILE.write_text(engine_version + "\n")
        print(f"recorded contract version {engine_version} (was {saved or 'none'}).")
        return 0

    problem = version_problem(doc, read_saved_version(), engine_version, args.engine_url)
    if problem:
        print(f"\n{problem}")

    known = engine_field_names(doc, args.engine_url) | ENVELOPE_KEYS | KNOWN_LOCAL
    sites = scan_fixtures(known)

    if not sites:
        print("\nno fixture claims a field the engine does not serve.")
    else:
        print("\nfields the tests still expect, that the engine no longer has:")
        for key in sorted(sites):
            for i, site in enumerate(sorted(sites[key])):
                label = key if i == 0 else ""
                print(f"  {label:<30} {site}")
        print(
            "\nEach is either engine drift (fix the fixture) or a test-local key "
            "(add it to KNOWN_LOCAL, with a note on what it is)."
        )

    required = required_problems(doc, answer_builders())
    if not required:
        print("no marked answer leaves out a field its endpoint requires.")
    else:
        print("\nfields the contract requires on an answer, that its fixture leaves out:")
        print("\n".join(required))
        print(
            "\nAdd each to the builder named in brackets (tests/unit/helpers.py), "
            "or point its answer_of at the endpoint it stands for."
        )

    return 1 if problem or sites or required else 0


if __name__ == "__main__":
    raise SystemExit(main())
