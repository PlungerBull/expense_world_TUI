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
version is its own step, refused unless the version is the first entry of the
contract's change log:

    python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002 --record-version

What a marked answer is checked for and what the check cannot see: docs/runtime.md
"Fixture drift". Exit code is 0 when the version matches, nothing retired is found and no
marked answer misses a required field or holds a key its endpoint lacks, 1 otherwise, so it also
works as a gate. It cannot tell a retired engine field from a key a test invented for
its own bookkeeping, so it prints the unknowns and leaves the judgement to a human —
see KNOWN_LOCAL for the ones already triaged.
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
        # the last row's key in the statement screen's paging test, a sample id like `acc1`
        "l12",
        # the key `STATEMENT_NOT_ORDERED` is refused on, printed in the complete
        # route's text as an error example, not as a response field of any schema
        "statement_order",
        # Textual widget geometry, faked by the adaptive-rows tests so
        # `fit_rows` can be measured without an event loop
        "content_size",
        "height",
        # keywords of Textual's `notify` call the TUI tests record and check
        # (`{"title": "Failed", "severity": "error", "markup": False}`, `markup=False`
        # being how refusal.py's toast shows the engine's words as text), not engine fields
        "severity",
        "markup",
        # client-side config file fields — never sent to the engine
        "engine_url",
        # the renames `expense import sheet` remembers per sheet account
        "sheet_account_names",
        # the sheet account names those renames are keyed by in the rename tests
        # (`{"BCP:PEN": ...}`, `{"bcp": ...}`), lower-cased sheet names, not fields
        "bcp",
        "caja",
        "nobody",
        "oro",
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
        # the OpenAPI document's own top-level keys, which the drift script's unit tests
        # build tiny stand-in documents from (`{"components": {"schemas": ...}}`)
        "components",
        "schemas",
        # the key of the C library's `localeconv()` answer, which the region tests fake
        "decimal_point",
        # the way the app is left (`how="esc"` or `how="quit"`), a test parameter's value
        "quit",
        # the Python keyword names a fake's call log records for
        # fetch_transactions / count_transactions (the wire names are
        # account_id, category_id, hashtag_id)
        "account",
        "category",
        "hashtag",
        # Home's own data dict: the month grid the app builds from the
        # dashboard's `months` (formatting.build_range_grid), not an engine field
        "grid",
        # a fake cursor value the paging tests hand back
        "c10",
        # Textual key names the import door's footer-binding asserts look up
        "enter",
        "escape",
        "down",
        # the list each xdist worker hands the controller for the error-shape
        # guard (tests/unit/conftest.py), not an engine field
        "error_tested",
        # the ways a line-read test leaves the ledger (`esc`, or another screen
        # over it), compared as `if how == "left":`, which reads like a dict key
        "covered",
        "left",
        # the QuickAddRefs field holding the account pool (expense/reads.py), set by
        # keyword in the fixtures that build refs; a client dataclass, not an engine field
        "picks",
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


def changelog(doc: dict) -> list | None:
    """The contract's `x-changelog`, which lists the released versions newest first, one
    entry each, its first entry being the current `info.version`; a version an engine
    running unreleased work serves is never listed
    (contract: "Base Conventions", "The contract"). None when the log is absent, empty
    or not a list; its entries are left to the caller to check."""
    log = doc.get("x-changelog")
    return log if isinstance(log, list) and log else None


def is_listed(doc: dict, engine: str) -> bool:
    """Whether the contract's change log lists `engine` anywhere, so it is a released version.

    False when the log is absent or malformed (any entry not an object with a string
    `version`), as well as when no entry is `engine`. Recording needs more: `is_current`."""
    log = changelog(doc)
    if log is None:
        return False
    if not all(isinstance(e, dict) and isinstance(e.get("version"), str) for e in log):
        return False
    return any(entry["version"] == engine for entry in log)


def is_current(doc: dict, engine: str) -> bool:
    """Whether `engine` is the change log's first entry, the only version that is recorded
    (contract: "Base Conventions", "The contract")."""
    return is_listed(doc, engine) and doc["x-changelog"][0]["version"] == engine


def changes_since(doc: dict, saved: str, engine: str) -> list[dict] | None:
    """The contract's change-log entries newer than `saved`, newest first.

    None means the whole contract is to be treated as changed: the log is absent or
    malformed, its first entry is not `engine`, or `saved` is not in it."""
    log = changelog(doc)
    if log is None:
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


def keyword_builders(helpers: Path) -> dict[str, set[str]]:
    """The builders in helpers.py that take `**fields`, each with its named parameters.

    Such a builder spreads the keywords a test adds into its answer, so a keyword that is
    not a named parameter is an answer key; a named one (`left=`, `parts=`) is a knob."""
    if not helpers.exists():
        return {}
    return _fields_builders(ast.parse(helpers.read_text()))


def _fields_builders(tree: ast.Module, kwarg: str | None = None) -> dict[str, set[str]]:
    """The module-level functions of `tree` that take `**fields` (any `**` name when
    `kwarg` is None), each with its named parameters."""
    named: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.args.kwarg:
            if kwarg and node.args.kwarg.arg != kwarg:
                continue
            args = node.args
            named[node.name] = {a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)}
    return named


def _keyword_sites(tree: ast.AST, builders: dict[str, set[str]]) -> list[tuple[str, int]]:
    """Each (key, line) a call passes by name to one of `builders` outside its parameters."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in builders:
            found += [
                (kw.arg, kw.value.lineno)
                for kw in node.keywords
                if kw.arg and kw.arg not in builders[name]
            ]
    return found


def scan_fixtures(known: set[str]) -> dict[str, list[str]]:
    """Map every unknown fixture key to the file:line sites that use it, whether written
    as a quoted `"key":` or passed by name to a `**fields` builder (`keyword_builders`),
    one defined in helpers.py or, named `**fields`, in the file itself."""
    sites: dict[str, list[str]] = defaultdict(list)
    shared = keyword_builders(UNIT_TESTS / "helpers.py")
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
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        builders = {**shared, **_fields_builders(tree, "fields")}
        for key, lineno in _keyword_sites(tree, builders):
            if key not in known and len(key) >= 3:
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


def _alternatives(doc: dict, schema: object, seen: frozenset[str] = frozenset()) -> list[dict]:
    """The resolved schemas `schema` is one of: itself when it is no union, else its
    members' alternatives, a union nested in a union (through `$ref` too) flattened."""
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    if isinstance(ref, str):
        if ref in seen:  # a union that contains itself
            return []
        seen = seen | {ref}
    schema = _resolve(doc, schema)
    members = _members(schema)
    if members is None:
        return [schema]
    return [alt for m in members for alt in _alternatives(doc, m, seen)]


def _is_object(schema: dict) -> bool:
    """Whether a resolved, non-union schema names an object: properties, required keys or
    a map schema (`additionalProperties` naming a schema)."""
    named = "properties" in schema or "required" in schema
    return named or isinstance(schema.get("additionalProperties"), dict)


def _objects(doc: dict, schema: object) -> list[dict]:
    """The object schemas `schema` is one of, nested unions flattened."""
    return [alt for alt in _alternatives(doc, schema) if _is_object(alt)]


def _object_schema(doc: dict, schema: object) -> dict | None:
    """The one object schema `schema` allows, through `$ref` and `anyOf`/`oneOf`
    (nested unions flattened), a map schema included; None when it allows none, or more
    than one, so the check never guesses between them."""
    objects = _objects(doc, schema)
    return objects[0] if len(objects) == 1 else None


def _list_items(doc: dict, schema: object) -> object | None:
    """The `items` schema of the one array schema `schema` allows, nested unions
    flattened as `_object_schema` does; None when it allows none, or more than one."""
    arrays = [alt for alt in _alternatives(doc, schema) if alt.get("type") == "array"]
    return arrays[0].get("items") if len(arrays) == 1 else None


def _answer_json(doc: dict, endpoint: str) -> object | None:
    """The schema of `endpoint`'s 2xx JSON answer, `endpoint` being `METHOD /v1/path`;
    None when the contract holds no such operation or answer."""
    method, _, path = endpoint.partition(" ")
    item = doc.get("paths", {}).get(path)
    op = item.get(method.lower()) if isinstance(item, dict) else None
    if not isinstance(op, dict):
        return None
    for code, response in sorted((op.get("responses") or {}).items()):
        if str(code).startswith("2") and isinstance(response, dict):
            content = (response.get("content") or {}).get("application/json") or {}
            if "schema" in content:
                return content["schema"]
    return None


def answer_schema(doc: dict, endpoint: str) -> dict | None:
    """The object schema of `endpoint`'s 2xx JSON answer, `endpoint` being `METHOD
    /v1/path`; None when the contract holds no such operation or answer, or the answer
    is not one object schema."""
    return _object_schema(doc, _answer_json(doc, endpoint))


def answered_in_many_shapes(doc: dict, endpoint: str) -> bool:
    """Whether `endpoint`'s 2xx JSON answer is a union of more than one object shape."""
    return len(_objects(doc, _answer_json(doc, endpoint))) > 1


def _checked(
    doc: dict, schema: dict, value: object, where: str = ""
) -> tuple[list[str], list[str]]:
    """What `value` leaves out of `schema` and what it holds beyond it, each a list of
    dotted paths (`coverage_gap.unfiled_count`, `items[0].id`), nested objects, list
    items and the values of a map (`additionalProperties` naming a schema) included
    wherever `value` holds one and the contract names one object schema for it."""
    if not isinstance(value, dict):
        return [], []
    prefix = f"{where}." if where else ""
    declared = schema.get("properties") or {}
    more = schema.get("additionalProperties")
    missing = [f"{prefix}{name}" for name in schema.get("required") or [] if name not in value]
    # `additionalProperties` true or any schema leaves the object open
    open_ = more is True or isinstance(more, dict)
    extra = [] if open_ or not declared else [f"{prefix}{k}" for k in value if k not in declared]
    for name, held in value.items():
        sub = declared.get(name, more if isinstance(more, dict) else None)
        if sub is not None:
            found = _descend(doc, sub, held, f"{prefix}{name}")
            missing += found[0]
            extra += found[1]
    return missing, extra


def _descend(doc: dict, sub: object, held: object, where: str) -> tuple[list[str], list[str]]:
    """`_checked` for a value held under the schema `sub`: an object, or a list of them."""
    if isinstance(held, dict):
        nested = _object_schema(doc, sub)
        return _checked(doc, nested, held, where) if nested is not None else ([], [])
    if isinstance(held, list):
        items = _list_items(doc, sub)
        missing: list[str] = []
        extra: list[str] = []
        for i, entry in enumerate(held if items is not None else ()):
            found = _descend(doc, items, entry, f"{where}[{i}]")
            missing += found[0]
            extra += found[1]
        return missing, extra
    return [], []


def missing_required(doc: dict, schema: dict, value: object) -> list[str]:
    """Each field `schema` requires that `value` leaves out, as a dotted path."""
    return _checked(doc, schema, value)[0]


def extra_keys(doc: dict, schema: dict, value: object) -> list[str]:
    """Each key `value` holds that `schema` does not declare, as a dotted path. An
    object whose schema declares no properties, or sets `additionalProperties` (true,
    `{}` or a schema), is open and has no extra key."""
    return _checked(doc, schema, value)[1]


def required_problems(doc: dict, builders: dict[str, Callable[[], object]]) -> list[str]:
    """One printable line per required field a marked answer leaves out, one per key
    it holds that its own endpoint does not declare, and one per marked endpoint the
    contract does not answer with one JSON object schema, saying whether it answers in
    more than one shape or holds no JSON answer."""
    problems: list[str] = []
    for endpoint, builder in sorted(builders.items()):
        name = getattr(builder, "__name__", repr(builder))
        schema = answer_schema(doc, endpoint)
        if schema is None:
            if answered_in_many_shapes(doc, endpoint):
                said = "the contract answers it in more than one shape"
            else:
                said = "the contract holds no JSON answer for it"
            problems.append(f"  {endpoint}: {said} ({name})")
            continue
        answer = builder()
        for field in missing_required(doc, schema, answer):
            problems.append(f"  {endpoint}: {field} ({name})")
        for key in extra_keys(doc, schema, answer):
            problems.append(f"  {endpoint}: {key} is not in its answer ({name})")
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
            "when it is the first entry of the contract's change log, and check nothing else"
        ),
    )
    args = parser.parse_args(argv)

    print(f"reading the engine's published contract from {args.engine_url} ...")
    doc = fetch_contract(args.engine_url)
    engine_version = contract_version(doc, args.engine_url)

    if args.record_version:
        saved = read_saved_version()
        if not is_current(doc, engine_version):
            why = (
                "lists it but not as its first entry, so it is not the engine's current release"
                if is_listed(doc, engine_version)
                else "does not list it, or the log is missing or unreadable, so it may be a "
                "draft that never shipped"
            )
            print(
                f"not recorded: the engine serves contract version {engine_version}, and the "
                f"contract's change log (x-changelog) {why}. "
                f"The saved version stays {saved or 'none'}."
            )
            return 1
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
        print("every marked answer matches its endpoint: nothing required left out, nothing extra.")
    else:
        print("\nwhere a marked answer differs from its endpoint's answer in the contract:")
        print("\n".join(required))
        print(
            "\nFix each in the builder named in brackets (tests/unit/helpers.py: add the "
            "field, or drop the key), or point its answer_of at the endpoint it stands for."
        )

    return 1 if problem or sites or required else 0


if __name__ == "__main__":
    raise SystemExit(main())
