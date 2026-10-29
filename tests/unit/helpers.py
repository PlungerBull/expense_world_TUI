"""Shared, importable helpers for tests/unit — the non-fixture half of the
test infrastructure (fixtures live in conftest.py).

Import style: `from tests.unit.helpers import FakeClient, wait_for, ...`.
Keep this module free of Textual imports at module level so the sheet-import
test files pay no TUI import cost.
"""

import asyncio
import functools
import io
import json
import re
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer
from rich.console import Console

from expense.errors import EngineError

ENGINE_URL = "https://api.example.com"


# ---------------------------------------------------------------------------
# Typer root wiring
# ---------------------------------------------------------------------------


def real_cli_app() -> typer.Typer:
    """The app `expense` actually runs — `expense.__main__.app`.

    Tests drive the real tree, so a rename of `import` or `sheet` fails them.
    The import is function-local so a test file pays for the entry point only
    when it uses it.
    """
    from expense.__main__ import app

    return app


# ---------------------------------------------------------------------------
# Typer output normalisation
# ---------------------------------------------------------------------------


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[mGKH]")


def strip_panel(output: str) -> str:
    """Flatten Typer/Rich error output to one plain, searchable line.

    Rich decides whether to colour by sniffing the environment, so the *same*
    error prints differently in CI than it does locally: GitHub Actions is
    treated as a terminal, which wraps usage errors in a box AND highlights the
    offending flag — splicing escape codes *inside* the token, so a plain
    ``"No such option: --include-deleted" in result.output`` finds nothing
    (`--include-deleted` arrives as `-` + `-include` + `-deleted`).

    Assert against this, never raw ``result.output``, whenever the expected text
    contains a flag name or could wrap at the panel edge.
    """
    no_ansi = _ANSI_ESCAPE_RE.sub("", output)
    no_box = "".join(c for c in no_ansi if c not in "│╭╮╰╯─\n\t")
    return " ".join(no_box.split())


# ---------------------------------------------------------------------------
# Rich rendering
# ---------------------------------------------------------------------------


def render_text(*renderables: object, width: int = 100, ansi: bool = False) -> str:
    """Print Rich renderables to a string with terminal detection turned OFF.

    `force_terminal` is passed explicitly in both directions, and that is the
    whole point. Left unset, Rich *sniffs the environment* — FORCE_COLOR, TERM,
    CI — so the same renderable comes back as plain text on one machine and as
    ANSI spans on another, which splits `-134.60 PEN` into separate spans and
    breaks a plain substring assertion that is not wrong about anything. An
    assertion that depends on the environment it runs in is the bug; this is
    the fix, so the suite needs no "never set FORCE_COLOR" instruction.

    `legacy_windows=False` is pinned for the same reason — box-drawing must not
    depend on the host OS.

    Pass `ansi=True` when the escape codes ARE the assertion (reverse-video
    cursor rows, colour-by-sign). That is the one case that wants a terminal,
    and saying so at the call site is what makes it readable as deliberate.
    """
    console = Console(file=io.StringIO(), width=width, force_terminal=ansi, legacy_windows=False)
    for renderable in renderables:
        console.print(renderable)
    return console.file.getvalue()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Engine envelopes
# ---------------------------------------------------------------------------
#
# The two wrappers every endpoint speaks. Written out by hand at every site, a
# change of shape would have to be chased through a dozen files. One definition
# each means a change is a single edit — and means a fixture cannot quietly
# disagree with its neighbours about what the engine sends.


def error_body(
    code: str, message: str = "boom", fields: object = None, reasons: object = None
) -> dict:
    """The engine's standard error envelope — see CLAUDE.md "Engine errors
    surface cleanly" and docs/runtime.md.

    `fields` defaults to None (the shape a non-validation refusal has); pass a
    dict for a 422, whose keys the engine names per row. `reasons` carries the
    same keys, each mapped to its reason code (contract: "Error reasons").
    """
    return {"error": {"code": code, "message": message, "fields": fields, "reasons": reasons}}


def error_response(
    status: int, code: str, message: str = "boom", fields: object = None, reasons: object = None
) -> httpx.Response:
    """`error_body` as a respx-ready response."""
    return httpx.Response(status, json=error_body(code, message, fields, reasons))


#: The engine's four refusals of a transaction's hashtag set, as
#: `(code, status, reason, the app's line under it or None)`: the pending
#: hashtag beside another, a user hashtag holding its name, its creation racing
#: another request, a hashtag deleted at the same moment
#: (contract: "Transactions (Ledger)", "Hashtags on a transaction")
#: (contract: "Hashtags", "When the engine creates it").
HASHTAG_REFUSALS = [
    ("VALIDATION_ERROR", 422, "PENDING_HASHTAG_NOT_ALONE", None),
    ("CONFLICT", 409, "RESERVED_NAME_HELD", None),
    ("CONFLICT", 409, "CONCURRENT_CHANGE", "It changed at the same moment: save again."),
    ("VALIDATION_ERROR", 422, "INVALID_REFERENCE", None),
]


def hashtag_refusal(code: str, status: int, reason: str, *, item: int | None = None) -> EngineError:
    """One of `HASHTAG_REFUSALS` as the engine sends it. The two `409`s are keyed
    `hashtag_ids` on every transaction route, a batch included; a `422` in a
    batch is keyed by its item, `transactions.<item>.hashtag_ids`."""
    key = "hashtag_ids" if item is None or status == 409 else f"transactions.{item}.hashtag_ids"
    return EngineError(
        code,
        f"Engine words for {reason}.",
        {key: "stand-in field words"},
        status,
        {},
        reasons={key: reason},
    )


#: The engine's words on each key a write on an archived account refuses, every
#: route alike (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts")
#: (contract: PUT /v1/statements/{statement_id}, "An archived holder").
ARCHIVED_FIELD_WORDS = "The account is archived. Unarchive it first."
#: The engine's message on a refused `PUT /transactions/{id}`.
ARCHIVED_PUT_WORDS = (
    "The transaction's account is archived: only its category, hashtags and description "
    "can change. Unarchive the account first."
)
#: The engine's message on a refused `PUT /statements/{id}`, as the practice engine
#: sends it (the contract does not print it).
ARCHIVED_STATEMENT_PUT_WORDS = "The statement's holder is archived. Unarchive it first."


def archived_words(verb: str, thing: str) -> str:
    """The engine's message on a refused delete of a transaction or a bank line:
    `Cannot <verb> a <thing> on an archived account. Unarchive the account first.`"""
    return f"Cannot {verb} a {thing} on an archived account. Unarchive the account first."


def archived_statement_words(verb: str) -> str:
    """The engine's message on a refused complete, revert or delete of a statement
    whose holder is archived, as the practice engine sends it (the contract does not
    print it): `Cannot <verb> a statement whose holder is archived. Unarchive the
    holder first.`"""
    return f"Cannot {verb} a statement whose holder is archived. Unarchive the holder first."


#: The engine's words on a delete of a bank line or a transaction in a completed
#: statement (`IN_COMPLETED_RECONCILIATION`), as the practice engine sends them; the
#: contract does not print them (contract: POST /v1/statements/{statement_id}/complete).
SEALED_LINE_WORDS = (
    "Cannot delete a bank line assigned to a completed statement. "
    "Revert the statement to draft first."
)
SEALED_TRANSACTION_WORDS = (
    "Cannot delete a transaction assigned to a completed statement. "
    "Revert the statement to draft first."
)
#: The field's words beside either, on `bank_line_id` or `transaction_id`.
SEALED_FIELD_WORDS = "Must not be assigned to a completed statement."


def archived_refusal(status: int, message: str, *keys: str) -> EngineError:
    """The engine's `ACCOUNT_ARCHIVED` refusal, naming each of `keys` with
    `ARCHIVED_FIELD_WORDS`: a `409 CONFLICT` on a delete, a complete or a
    revert, a `422 VALIDATION_ERROR` on a `PUT`
    (contract: DELETE /v1/transactions/{transaction_id})
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")
    (contract: POST /v1/statements/{statement_id}/complete, "An archived holder")."""
    code = "CONFLICT" if status == 409 else "VALIDATION_ERROR"
    fields = dict.fromkeys(keys, ARCHIVED_FIELD_WORDS)
    reasons = dict.fromkeys(keys, "ACCOUNT_ARCHIVED")
    body = error_body(code, message, fields, reasons)
    return EngineError(code, message, fields, status, body, reasons=reasons)


def refusal_text(err: EngineError, line: str | None) -> str:
    """What the app shows for `err`: the engine's words whole, then its line, if any."""
    fields = [f"  {k}: {v}" for k, v in (err.fields or {}).items()]
    words = "\n".join([f"{err.code} — {err.message}", *fields])
    return words if line is None else f"{words}\n\n{line}"


def whole(items: list) -> dict:
    """The whole-list envelope: accounts, categories, hashtags.
    No `total`, `limit` or `offset` — the engine returns every row and refuses
    both paging parameters."""
    return {"items": items}


def line_code_of(line: str) -> str:
    """The `line_code` a fixture's bank line `line` reads: `#` and six digits, the same
    on every part of one line and, in practice, different between lines
    (contract: "Transactions (Ledger)", "Bank lines"). Derived from the line's id so a
    fixture never has to keep a counter."""
    return f"#{zlib.crc32(line.encode()) % 999_999 + 1:06d}"


def import_part(
    tx_id: str,
    amount_cents: int,
    *,
    account_id: str = "sig-pen",
    line: str = "bl-1",
    day: str = "2026-09-07",
    title: str = "TOTTUS PORONGOCHE",
    category_id: str = "pend",
    hashtag_ids: tuple[str, ...] = ("h-pend",),
    description: str | None = None,
    statement_line: str | None = None,
    statement_place: int | None = None,
) -> dict:
    """One part of a bank line as the engine lists it, in a
    `POST /transactions/import` answer's unclaimed line or in the `parts` of
    `GET /bank-lines/{id}`: the whole transaction response
    (contract: POST /v1/transactions/import) (contract: GET /v1/bank-lines/{bank_line_id}),
    `amount_cents` a magnitude and the direction in `transaction_type`, 1 out
    and 2 in (contract: "Base Conventions", "Sign convention — responses").
    `amount_cents` is given signed here and written as the engine sends it.
    `statement_line` and `statement_place` are the line's, the same on every part:
    the engine builds the first from the account's statement code, the completed
    statement's month and the place (contract: "Transactions (Ledger)", "Bank lines")."""
    return {
        "id": tx_id,
        "user_id": "u-1",
        "title": title,
        "description": description,
        "amount_cents": abs(amount_cents),
        "transaction_type": 1 if amount_cents < 0 else 2,  # 1 outflow, 2 inflow
        "date": f"{day}T05:00:00Z",
        "account_id": account_id,
        "category_id": category_id,
        "statement_id": None,
        "bank_line_id": line,
        "line_code": line_code_of(line),
        "operation_code": None,
        "statement_line": statement_line,
        "statement_place": statement_place,
        "created_at": f"{day}T15:00:00Z",
        "updated_at": f"{day}T15:00:00Z",
        "version": 1,
        "deleted_at": None,
        "hashtag_ids": list(hashtag_ids),
    }


#: The sentence the engine sends beside each lock's reason in `edit_limits`, the
#: write's own words on that field (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields").
#: The fake engine's copy only: the app shows the sentence as sent and holds none of these.
#: The live suite fails when one differs from the engine's words
#: (tests/contract/test_bank_line_edit_limits.py).
LOCK_MESSAGES = {
    "LOCKED": "Locked by completed statement.",
    "ACCOUNT_ARCHIVED": "The account is archived. Unarchive it first.",
    "OPENING_BALANCE_ACCOUNT_FIXED": "Must not move an opening balance to another account.",
    "SPLIT_TOTAL_MISMATCH": "The parts must add up to the line's total.",
    "OPENING_BALANCE_CATEGORY_FIXED": (
        "Must not move an opening balance out of the opening-balance category."
    ),
    "OPENING_BALANCE_NOT_TAGGED": "Must be empty: an opening balance carries no hashtag.",
}


#: The engine's message on a transaction or bank line write refused by the field
#: lock, as the practice engine sends it; the contract prints only the field's
#: sentence, `LOCK_MESSAGES["LOCKED"]`
#: (contract: PUT /v1/transactions/{transaction_id}, "Field locking").
LOCKED_WORDS = "Transaction belongs to a completed statement. These fields are locked."


def _locks(reasons: dict[str, str]) -> dict[str, dict[str, str]]:
    """Each field's reason as the engine sends it: `{reason, message}`."""
    return {
        field: {"reason": reason, "message": LOCK_MESSAGES[reason]}
        for field, reason in reasons.items()
    }


def edit_limits(
    *,
    locked_fields: dict[str, str] | None = None,
    total_fixed: bool = False,
    parts_fixed: bool = False,
    locked_part_fields: dict[str, dict[str, str]] | None = None,
) -> dict:
    """A bank line's `edit_limits`, every key present: the line fields a write
    would refuse, whether the total and the parts are fixed, and per part id the
    part fields a write would refuse, each field named as `{reason, message}`
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). Callers give
    each field its reason; the message is the contract's sentence for it
    (`LOCK_MESSAGES`). The default is a line nothing closes."""
    return {
        "locked_fields": _locks(locked_fields or {}),
        "total_fixed": total_fixed,
        "parts_fixed": parts_fixed,
        "locked_part_fields": {k: _locks(v) for k, v in (locked_part_fields or {}).items()},
    }


def bank_line_row(
    line: str,
    parts: list[dict],
    *,
    net_cents: int,
    operation_code: str | None = None,
    account_id: str = "sig-pen",
    is_opening_balance: bool = False,
) -> dict:
    """One bank line as `GET /bank-lines` lists it and `GET /bank-lines/{id}`
    reads it: its `parts` (each an `import_part`), its `line_code`,
    `statement_line` and `statement_place` as its parts read them, the engine's
    signed `net_cents` and `part_count`, `is_opening_balance` (`true` only on an
    account's opening balance), and the `edit_limits` of a line nothing closes
    (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields")."""
    return {
        "id": line,
        "line_code": line_code_of(line),
        "account_id": account_id,
        "operation_code": operation_code,
        "statement_line": parts[0]["statement_line"] if parts else None,
        "statement_place": parts[0]["statement_place"] if parts else None,
        "net_cents": net_cents,
        "part_count": len(parts),
        "is_opening_balance": is_opening_balance,
        "parts": parts,
        "edit_limits": edit_limits(),
    }


def put_answer(named: dict, changed: list[dict], *, left: tuple[str, ...] = ()) -> dict:
    """A `PUT /transactions/{id}` answer: the part named, after the write, plus
    `changed_parts`, one entry per part in `changed` (each the part after the write,
    in the line's list order), `left_statement` true for the ids in `left`
    (contract: PUT /v1/transactions/{transaction_id}, "Response"). `changed` is `[]`
    for a body that changed no line field."""
    return {
        **named,
        "changed_parts": [
            {"transaction": part, "left_statement": part["id"] in left} for part in changed
        ],
    }


#: Every fixture builder that stands for an engine endpoint's answer, keyed by that
#: endpoint as the contract names it, `METHOD /v1/path`. scripts/check_fixture_drift.py
#: calls each with no arguments and reports any field the contract requires on that
#: answer that the bare answer leaves out. Mark a builder with `answer_of`.
ANSWER_BUILDERS: dict[str, Callable[..., dict]] = {}


def answer_of(method: str, path: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Mark a builder as standing for the answer of `method path`, in `ANSWER_BUILDERS`.

    The drift script checks the bare answer, `builder()`, so every call has to keep
    each of its keys: what a test passes is spread over it, never in place of it.
    The marked builder asserts that on every call, so a test cannot get an answer
    with fewer fields than the one the script checked."""

    def mark(builder: Callable[..., dict]) -> Callable[..., dict]:
        @functools.wraps(builder)
        def build(*args: Any, **kwargs: Any) -> dict:
            answer = builder(*args, **kwargs)
            dropped = sorted(set(builder()) - set(answer))
            assert not dropped, f"{builder.__name__} dropped {dropped} from its bare answer"
            return answer

        ANSWER_BUILDERS[f"{method} {path}"] = build
        return build

    return mark


#: The keys of an import answer's row that say what the engine did with it, each `None`
#: unless its outcome sets it (contract: POST /v1/transactions/import, "Response").
IMPORT_OUTCOME_KEYS = (
    "transaction_id",
    "rule",
    "bank_line_id",
    "backfill_code",
    "retitled",
    "redated",
    "redate_blocked_by",
    "sealed_by",
)


def import_row(
    row: int,
    amount_cents: int = -1000,
    *,
    outcome: str = "new",
    account_id: str = "sig-pen",
    day: str = "2026-09-07",
    title: str | None = "TOTTUS PORONGOCHE",
    operation_code: str | None = None,
    **set_keys: Any,
) -> dict:
    """One row of a `POST /transactions/import` answer, every key present: the row
    as the engine read it from the spreadsheet (`row` its row number, the first data
    row being 2) and what it did with it (contract: POST /v1/transactions/import,
    "Response"). `amount_cents` is given signed here and written as the engine sends
    it, a magnitude and `transaction_type` (1 out, 2 in); a row of `0` reads `0` and
    `null`. `set_keys` are the outcome's keys (`IMPORT_OUTCOME_KEYS`)."""
    unknown = set(set_keys) - set(IMPORT_OUTCOME_KEYS)
    assert not unknown, f"not an import row's key: {sorted(unknown)}"
    if amount_cents == 0:
        kind = None
    else:
        kind = 1 if amount_cents < 0 else 2
    return {
        "row": row,
        "account_id": account_id,
        "date": day,
        "amount_cents": abs(amount_cents),
        "transaction_type": kind,
        "title": title,
        "operation_code": operation_code,
        "outcome": outcome,
        **{key: set_keys.get(key) for key in IMPORT_OUTCOME_KEYS},
    }


def unclaimed_line(bank_line_id: str, parts: list[dict]) -> dict:
    """A ledger line no file row claimed, as an import answer's reported day holds it:
    its id, its `line_code`, the signed sum of its parts and the parts themselves, each
    an `import_part` (contract: POST /v1/transactions/import)."""
    net = sum(
        -p["amount_cents"] if p["transaction_type"] == 1 else p["amount_cents"] for p in parts
    )
    return {
        "bank_line_id": bank_line_id,
        "line_code": line_code_of(bank_line_id),
        "net_cents": net,
        "parts": parts,
    }


def import_day(
    day: str,
    file_net_cents: int,
    ledger_net_cents: int,
    *,
    account_id: str = "sig-pen",
    unmatched_rows: tuple[int, ...] = (),
    lines: tuple[dict, ...] = (),
) -> dict:
    """One `day_mismatches` entry of an import answer: the account and day, both
    signed totals, the spreadsheet rows on it that matched no line and the ledger
    lines no file row claimed (each an `unclaimed_line`)
    (contract: POST /v1/transactions/import)."""
    return {
        "account_id": account_id,
        "date": day,
        "file_net_cents": file_net_cents,
        "ledger_net_cents": ledger_net_cents,
        "unmatched_rows": list(unmatched_rows),
        "unclaimed_lines": list(lines),
    }


def import_counts(rows: list[dict]) -> dict:
    """An import answer's `counts` for `rows`, as the engine counts them."""
    outcomes = [r["outcome"] for r in rows]
    return {
        "new": outcomes.count("new"),
        "matched": outcomes.count("matched"),
        "sealed": outcomes.count("sealed"),
        "skipped": outcomes.count("skipped"),
        "backfilled": sum(1 for r in rows if r["backfill_code"]),
        "retitled": sum(1 for r in rows if r["retitled"]),
        "redated": sum(1 for r in rows if r["redated"]),
    }


@answer_of("POST", "/v1/transactions/import")
def import_answer(
    rows: list[dict] | None = None,
    *,
    dry_run: bool = True,
    day_mismatches: list[dict] | None = None,
    counts: dict | None = None,
) -> dict:
    """`POST /transactions/import`'s answer: `dry_run` echoed, one row per data row
    (each an `import_row`), the reported days (each an `import_day`, none by default)
    and `counts` (by default the rows counted) (contract: POST /v1/transactions/import,
    "Response"). The bare answer holds a row and a reported day with an unclaimed
    line, so the drift script checks each nested shape."""
    if rows is None:
        rows = [import_row(2)]
        if day_mismatches is None:
            part = import_part("t-bare", -1000)
            day_mismatches = [
                import_day("2026-09-07", -1000, -2000, lines=(unclaimed_line("bl-1", [part]),))
            ]
    return {
        "dry_run": dry_run,
        "rows": rows,
        "day_mismatches": list(day_mismatches or []),
        "counts": counts if counts is not None else import_counts(rows),
    }


def sheet_name_use(name: str, rows: int = 1, proposed_id: str | None = None, **currency) -> dict:
    """One name a sheet uses, as an import-sheet answer's `names` lists it: an account
    `{name, currency_code, rows, proposed_id}` (pass `currency_code=`), a category or
    hashtag `{name, rows, proposed_id}`
    (contract: POST /v1/transactions/import-sheet, "Response")."""
    assert set(currency) <= {"currency_code"}, sorted(currency)
    return {"name": name, **currency, "rows": rows, "proposed_id": proposed_id}


def sheet_row(
    row: int,
    amount_cents: int = -1250,
    *,
    day: str = "2026-03-05",
    title: str = "made-up lunch",
    account_id: str | None = None,
    outcome: str | None = None,
    is_opening_balance: bool | None = None,
    transaction_id: str | None = None,
    bank_line_id: str | None = None,
) -> dict:
    """One row of an import-sheet answer, every key present; `amount_cents` given
    signed and written as the engine sends it, a magnitude and `transaction_type`
    (1 out, 2 in; a zero row `0` and `null`). Its account, outcome and opening flag
    are `null` by default, as a dry run without `names` answers them
    (contract: POST /v1/transactions/import-sheet, "Response")."""
    kind = None if amount_cents == 0 else (1 if amount_cents < 0 else 2)
    return {
        "row": row,
        "account_id": account_id,
        "date": day,
        "amount_cents": abs(amount_cents),
        "transaction_type": kind,
        "title": title,
        "outcome": outcome,
        "is_opening_balance": is_opening_balance,
        "transaction_id": transaction_id,
        "bank_line_id": bank_line_id,
    }


def sheet_counts(rows: list[dict]) -> dict:
    """An import-sheet answer's `counts` for `rows`, the rows of each outcome and
    the opening balances; no split line, so no row in one."""
    outcomes = [r["outcome"] for r in rows]
    return {
        "new": outcomes.count("new"),
        "matched": outcomes.count("matched"),
        "sealed": outcomes.count("sealed"),
        "skipped": outcomes.count("skipped"),
        "opening_balances": sum(1 for r in rows if r["is_opening_balance"]),
        "split_lines": 0,
        "split_rows": 0,
    }


@answer_of("POST", "/v1/transactions/import-sheet")
def sheet_import_answer(
    *,
    accounts: list[dict] | None = None,
    categories: list[dict] | None = None,
    hashtags: list[dict] | None = None,
    rows: list[dict] | None = None,
    dry_run: bool = True,
    counts: dict | None = None,
) -> dict:
    """`POST /transactions/import-sheet`'s answer: `dry_run` echoed, every name the
    sheet uses (each a `sheet_name_use`), one row per data row (each a `sheet_row`)
    and `counts` (by default the rows counted)
    (contract: POST /v1/transactions/import-sheet, "Response"). The bare answer holds
    one name of each kind and a row, so the drift script checks each nested shape."""
    if rows is None:
        rows = [sheet_row(2)]
    return {
        "dry_run": dry_run,
        "names": {
            "accounts": (
                accounts
                if accounts is not None
                else [sheet_name_use("made-up acct", currency_code="PEN")]
            ),
            "categories": categories if categories is not None else [sheet_name_use("food")],
            "hashtags": hashtags if hashtags is not None else [sheet_name_use("tag")],
        },
        "rows": rows,
        "counts": counts if counts is not None else sheet_counts(rows),
    }


def statement_row(
    place: int,
    amount_cents: int = -1000,
    *,
    outcome: str = "matched",
    account_id: str = "sig-pen",
    currency: str = "PEN",
    day: str = "2026-10-02",
    description: str | None = "TAMBO MIRAFLORES",
    fee: bool = False,
    bank_line_id: str | None = None,
    transaction_id: str | None = None,
    redated: bool = False,
) -> dict:
    """One row of a `POST /statements/import` answer, every key present: the row as the
    engine read it from the paper (`place` its number on it, from 1) and what closing
    does with it (contract: POST /v1/statements/import, "Response").
    `amount_cents` is given signed here and written as the engine sends it, a magnitude
    and `transaction_type` (1 out, 2 in). A matched row's `bank_line_id` defaults to one
    of its own. `redated` is true on a matched row whose line moves to the row's day
    (contract: POST /v1/statements/import, "The bank's day wins")."""
    if outcome == "matched" and bank_line_id is None:
        bank_line_id = f"bl-{place}"
    return {
        "place": place,
        "account_id": account_id,
        "currency": currency,
        "processed_on": None if fee else day,
        "date": day,
        "description": description,
        "type": None,
        "fee": fee,
        "amount_cents": abs(amount_cents),
        "transaction_type": 2 if amount_cents > 0 else 1,
        "outcome": outcome,
        "bank_line_id": bank_line_id,
        "transaction_id": transaction_id,
        "redated": redated,
    }


#: One account's balances in a statement as `GET /statements/{id}` reads them, nothing
#: entered past the beginning: `difference_cents` is `null` while the ending balance is
#: (contract: "Statements", "`difference_cents` — the add-up check").
_BALANCE = {
    "account_id": "acc1",
    "beginning_balance_cents": 0,
    "ending_balance_cents": None,
    "difference_cents": None,
}
#: The close's notes `POST /statements/{id}/complete` adds to each balance: no warning,
#: no gap, no line flagged (contract: POST /v1/statements/{statement_id}/complete, "Response").
_CLOSE_NOTES = {"warnings": [], "coverage_gap": None, "review_lines": []}
#: A draft statement as `GET /statements/{id}` reads it, every field present, on a holder
#: of one account without a statement code, so its order counts are `null`
#: (contract: "Statements", "A statement's order"): what the statement answers below
#: spread a test's record over.
_STATEMENT = {
    "id": "s1",
    "user_id": "u-1",
    "holder_id": "h1",
    "name": "April 2026",
    "date_start": "2026-04-01",
    "date_end": "2026-04-30",
    "status": 1,
    "balances": [_BALANCE],
    "unplaced_count": None,
    "shared_place_count": None,
    "created_at": "2026-04-01T15:00:00Z",
    "updated_at": "2026-04-01T15:00:00Z",
    "version": 1,
    "deleted_at": None,
}
#: When a deleted statement's `deleted_at` reads.
_STATEMENT_DELETED_AT = "2026-05-02T15:00:00Z"


def _statement(record: dict | None, balance: dict) -> dict:
    """`record` spread over `_STATEMENT`, each of its `balances` spread over `balance`."""
    whole_record = {**_STATEMENT, **(record or {})}
    return {**whole_record, "balances": [{**balance, **b} for b in whole_record["balances"]]}


@answer_of("GET", "/v1/statements/{statement_id}")
def statement_record(record: dict | None = None) -> dict:
    """One statement as `GET /statements/{id}` reads it: `record` spread over a draft,
    each of its `balances` over an account's balances nothing entered past the beginning
    (contract: "Statements", "Statement response")."""
    return _statement(record, _BALANCE)


@answer_of("GET", "/v1/statements")
def statement_list(items: list[dict] | None = None) -> dict:
    """`GET /statements?holder_id=`'s answer, whole and unpaged: `{items}`, each item a
    `statement_record` of the record a test gives (one draft by default)
    (contract: GET /v1/statements)."""
    return whole([statement_record(item) for item in (items if items is not None else [{}])])


@answer_of("POST", "/v1/statements")
def statement_create_answer(sent: dict | None = None) -> dict:
    """`POST /statements`'s answer to `sent`, the request body: the draft it makes, each
    balance's `difference_cents` its ending minus its beginning, as nothing is assigned
    yet, `null` while the ending balance is (contract: POST /v1/statements, "Response")
    (contract: "Statements", "`difference_cents` — the add-up check")."""
    sent = sent or {}
    fields = ("id", "holder_id", "name", "date_start", "date_end", "balances")
    made = statement_record({key: sent[key] for key in fields if key in sent})
    for balance in made["balances"]:
        end = balance["ending_balance_cents"]
        balance["difference_cents"] = (
            None if end is None else end - balance["beginning_balance_cents"]
        )
    return made


@answer_of("PUT", "/v1/statements/{statement_id}")
def statement_put_answer(record: dict | None = None) -> dict:
    """`PUT /statements/{id}`'s answer: the statement as `GET /statements/{id}` reads it
    after the write, `record` spread over a draft (contract: PUT /v1/statements/{statement_id})."""
    return statement_record(record)


@answer_of("POST", "/v1/statements/{statement_id}/revert")
def statement_revert_answer(record: dict | None = None) -> dict:
    """`POST /statements/{id}/revert`'s answer: the statement as `GET /statements/{id}`
    reads it after the write, `record` spread over a draft, with no close notes
    (contract: POST /v1/statements/{statement_id}/revert)."""
    return statement_record(record)


@answer_of("DELETE", "/v1/statements/{statement_id}")
def statement_delete_answer(record: dict | None = None) -> dict:
    """`DELETE /statements/{id}`'s answer: the statement as it is after the delete,
    `record` spread over a draft, with `deleted_at` set and its lines unassigned, so both
    order counts read `0`, or `null` on a holder with no statement code
    (contract: DELETE /v1/statements/{statement_id})."""
    gone = statement_record(record)
    counts = ("unplaced_count", "shared_place_count")
    return {
        **gone,
        "deleted_at": _STATEMENT_DELETED_AT,
        **{key: 0 for key in counts if gone[key] is not None},
    }


@answer_of("POST", "/v1/statements/{statement_id}/complete")
def statement_complete_answer(record: dict | None = None) -> dict:
    """`POST /statements/{id}/complete`'s answer: the statement after the write, `record`
    spread over a completed one, each of its `balances` over an account's balances that
    add up (an ending balance and a `difference_cents` of `0`) carrying the close's notes,
    `warnings` (`[]`), `coverage_gap` (`None`) and `review_lines` (`[]`) unless the
    balance names them (contract: POST /v1/statements/{statement_id}/complete, "Response")."""
    completed = {"status": 2, "updated_at": "2026-05-02T15:00:00Z", "version": 2}
    added_up = {**_BALANCE, "ending_balance_cents": 0, "difference_cents": 0, **_CLOSE_NOTES}
    return _statement({**completed, **(record or {})}, added_up)


def upload_balance(
    account_id: str = "sig-pen",
    currency: str = "PEN",
    *,
    begin: int = -120410,
    end: int = -51230,
) -> dict:
    """One of a `POST /statements/import` answer's `balances`: its account and currency
    and the paper's balances (contract: POST /v1/statements/import, "Response")."""
    return {
        "account_id": account_id,
        "currency": currency,
        "beginning_balance_cents": begin,
        "ending_balance_cents": end,
    }


@answer_of("POST", "/v1/statements/import")
def statement_upload_answer(
    rows: list[dict] | None = None,
    *,
    dry_run: bool = False,
    creates: bool = True,
    statement_id: str = "s-paper",
    name: str = "SIG-202610",
    date_start: str = "2026-09-26",
    date_end: str = "2026-10-25",
    balances: list[dict] | None = None,
    taken_out: list[str] | None = None,
    review_lines: dict[str, list[str]] | None = None,
    counts: dict | None = None,
) -> dict:
    """`POST /statements/import`'s answer: `dry_run` echoed, `statement_id` (`None` on a
    dry run that creates the statement), `creates`, the statement's name and days, its
    `balances` (one `upload_balance` by default), `statement` (on an apply the completed
    statement as a complete answers it, each balance flagging the ids `review_lines`
    gives for its account; `None` on a dry run), one row per row of the paper (each a
    `statement_row`), `taken_out` and `counts` (by default the rows and the lines taken
    out counted) (contract: POST /v1/statements/import, "Response"). The bare answer is
    an apply holding a new row, so the drift script checks each nested shape."""
    if rows is None:
        rows = [statement_row(1, outcome="new")]
    paper = balances if balances is not None else [upload_balance()]
    flagged = review_lines or {}
    taken = list(taken_out or [])
    outcomes = [row["outcome"] for row in rows]
    closed = {
        "id": statement_id,
        "name": name,
        "date_start": date_start,
        "date_end": date_end,
        "unplaced_count": 0,
        "shared_place_count": 0,
        "balances": [
            {
                "account_id": b["account_id"],
                "beginning_balance_cents": b["beginning_balance_cents"],
                "ending_balance_cents": b["ending_balance_cents"],
                "review_lines": list(flagged.get(b["account_id"], [])),
            }
            for b in paper
        ],
    }
    return {
        "dry_run": dry_run,
        "statement_id": None if dry_run and creates else statement_id,
        "creates": creates,
        "name": name,
        "date_start": date_start,
        "date_end": date_end,
        "balances": paper,
        "statement": None if dry_run else statement_complete_answer(closed),
        "rows": rows,
        "taken_out": taken,
        "counts": counts
        if counts is not None
        else {
            "matched": outcomes.count("matched"),
            "new": outcomes.count("new"),
            "empty": outcomes.count("empty"),
            "taken_out": len(taken),
            "redated": sum(1 for row in rows if row["redated"]),
        },
    }


#: A holder as `GET /holders/{id}` reads it, every field present: one account, no
#: statement code (contract: "Holders", "Holder response").
_HOLDER = {
    "id": "h1",
    "user_id": "u-1",
    "name": "BCP Ahorros",
    "statement_code": None,
    "account_ids": ["acc1"],
    "is_archived": False,
    "sort_order": 1,
    "created_at": "2026-04-01T15:00:00Z",
    "updated_at": "2026-04-01T15:00:00Z",
    "version": 1,
    "deleted_at": None,
}


@answer_of("GET", "/v1/holders/{holder_id}")
def holder_record(record: dict | None = None) -> dict:
    """One holder as `GET /holders/{id}` reads it: `record` spread over a holder of one
    account with no statement code (contract: "Holders", "Holder response")."""
    return {**_HOLDER, **(record or {})}


@answer_of("GET", "/v1/holders")
def holder_list(items: list[dict] | None = None) -> dict:
    """`GET /holders`'s answer, whole and unpaged: `{items}`, each item a `holder_record`
    of the record a test gives (one holder by default) (contract: GET /v1/holders)."""
    return whole([holder_record(item) for item in (items if items is not None else [{}])])


#: An account as `GET /accounts/{id}` reads it, every field present: the one account
#: of `_HOLDER`, in soles, nothing recorded on it and no opening balance; the statement
#: code is its holder's, never the account's (contract: "Holders").
_ACCOUNT = {
    "id": "acc1",
    "user_id": "u-1",
    "name": "BCP Ahorros",
    "currency_code": "PEN",
    "is_person": False,
    "color": "#3b82f6",
    "holder_id": "h1",
    "current_balance_cents": 0,
    "current_balance_home_cents": 0,
    "opening_balance_transaction_id": None,
    "is_archived": False,
    "sort_order": 1,
    "created_at": "2026-04-01T15:00:00Z",
    "updated_at": "2026-04-01T15:00:00Z",
    "version": 1,
    "deleted_at": None,
}


@answer_of("GET", "/v1/accounts/{account_id}")
def account_record(base: dict | None = None, /, **fields: Any) -> dict:
    """One account as the engine reads it: `base` (another account, to vary one) and
    then `fields` spread over `_ACCOUNT` (contract: GET /v1/accounts/{account_id}).
    It is the shared account builder: no test file defines an account builder of its
    own. A person passes `is_person=True, holder_id=None`."""
    return {**_ACCOUNT, **(base or {}), **fields}


#: What `FakeClient` answers a write no `write_responses` entry names: a list of
#: `(method, path pattern, answer)`, one per write the fake answers in the engine's
#: shape, the pattern a regex matching the path FakeClient sees (the contract's path
#: without `/v1`, each `{name}` a named group). `answer(client, body, **path_params)`
#: builds it through the endpoint's `answer_of` builder, so the drift script checks
#: the bare shape every default answer keeps. Register one with `fake_answer`.
FAKE_ANSWERS: list[tuple[str, re.Pattern[str], Callable[..., dict]]] = []


def fake_answer(method: str, path: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Make `answer` FakeClient's default answer to `method path`, the endpoint as the
    contract names it (`/v1/...`, `{name}` for each path parameter). The endpoint must
    have an `answer_of` builder, which `answer` builds its answer through."""
    endpoint = f"{method} {path}"
    assert endpoint in ANSWER_BUILDERS, f"{endpoint} has no answer_of builder"
    pattern = re.compile(re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path.removeprefix("/v1")))

    def mark(answer: Callable[..., dict]) -> Callable[..., dict]:
        FAKE_ANSWERS.append((method, pattern, answer))
        return answer

    return mark


def _served_statement(client: "FakeClient", statement_id: str) -> dict:
    """The statement the path names, as the test serves `GET /statements/{id}` (its id
    alone when it serves none)."""
    return {"id": statement_id, **client.get_responses.get(f"/statements/{statement_id}", {})}


@fake_answer("POST", "/v1/statements")
def _statement_created(client: "FakeClient", body: Any) -> dict:
    return statement_create_answer(body)


@fake_answer("POST", "/v1/statements/{statement_id}/revert")
def _statement_reverted(client: "FakeClient", body: Any, statement_id: str) -> dict:
    return statement_revert_answer({**_served_statement(client, statement_id), "status": 1})


@fake_answer("POST", "/v1/statements/{statement_id}/complete")
def _statement_completed(client: "FakeClient", body: Any, statement_id: str) -> dict:
    return statement_complete_answer({**_served_statement(client, statement_id), "status": 2})


@fake_answer("DELETE", "/v1/statements/{statement_id}")
def _statement_deleted(client: "FakeClient", body: Any, statement_id: str) -> dict:
    return statement_delete_answer(_served_statement(client, statement_id))


#: `GET /accounts?include_people=true` in an order no client could derive:
#: not alphabetical (Z, A, M), not `sort_order` (3, 1, 2), and the person last,
#: the way the engine lists people after every real account (contract: GET
#: /v1/accounts). Every account list and picker must show exactly this order.
ENGINE_ORDER_ACCOUNTS = [
    account_record(id="acc-zeta", name="Zeta Ahorros", sort_order=3, current_balance_cents=500),
    account_record(
        id="acc-alfa",
        name="Alfa Corriente",
        currency_code="USD",
        holder_id="h2",
        sort_order=1,
        current_balance_cents=700,
    ),
    account_record(
        id="acc-medio",
        name="Medio Visa",
        holder_id="h3",
        sort_order=2,
        current_balance_cents=-300,
    ),
    account_record(
        id="per-ana",
        name="Ana",
        is_person=True,
        holder_id=None,
        sort_order=0,
        current_balance_cents=100,
    ),
]
#: The names as the engine orders them, people included and without them.
ENGINE_ORDER_NAMES = [a["name"] for a in ENGINE_ORDER_ACCOUNTS]
ENGINE_ORDER_BANK_NAMES = [a["name"] for a in ENGINE_ORDER_ACCOUNTS if not a["is_person"]]


def in_order(text: str, names: list[str]) -> bool:
    """Every name appears in the rendered `text`, each after the one before it."""
    at = [text.find(name) for name in names]
    return -1 not in at and at == sorted(at)


def cursor_page(items: list, *, next_cursor: str | None = None, limit: int = 50) -> dict:
    """The `GET /transactions` envelope — cursor-paged, so no `total` and no
    `offset`. `next_cursor=None` (the default) is the last page."""
    return {"items": items, "limit": limit, "next_cursor": next_cursor}


def fake_ledger(monkeypatch, rows: list, *, count_fails: bool = False) -> tuple[list, list]:
    """`fetch_transactions` + `count_transactions` over `rows`, the engine's way:
    it refuses `offset`, serves slices of the requested `limit`, and hands back
    `c<next index>` as the cursor. `rows` is read on every call, so a test can
    shrink it to play a write the engine applied. Returns the (reads, counts)
    call logs."""
    calls: list = []
    counts: list = []

    def fetch(_cfg=None, *, limit=None, after=None, **kw):
        assert "offset" not in kw, "the engine refuses offset"
        calls.append({"limit": limit, "after": after, **kw})
        start = int(after[1:]) if after else 0
        end = start + (limit or 50)
        nxt = f"c{end}" if end < len(rows) else None
        return cursor_page(rows[start:end], next_cursor=nxt, limit=limit or 50)

    def count(_cfg=None, **kw):
        counts.append(kw)
        if count_fails:
            raise RuntimeError("count unavailable")
        return len(rows)

    monkeypatch.setattr("expense.reads.fetch_transactions", fetch)
    monkeypatch.setattr("expense.reads.count_transactions", count)
    return calls, counts


# ---------------------------------------------------------------------------
# No request carries a read-only field
# ---------------------------------------------------------------------------

#: The keys no request body may hold, at any depth. The engine sets each one itself:
#: it gives every new line its `line_code`, builds `statement_line` on every read and sets
#: `statement_place` only through a statement's order, and each is in no request body, so
#: sending one is `422` `UNKNOWN_FIELD` (contract: "Transactions (Ledger)", "Bank lines").
READ_ONLY_FIELDS = ("line_code", "statement_line", "statement_place")

#: Every request a test sent with one of the keys in its body, as
#: "METHOD path sends <key> at <where>". `refuse_read_only_fields` adds to it; conftest's
#: autouse `_no_read_only_fields_in_requests` empties it before each test and fails the
#: test after it when it is not empty, so a leak the app catches and swallows still fails
#: the test that made it.
READ_ONLY_FIELD_LEAKS: list[str] = []


class ReadOnlyFieldLeak(AssertionError):
    """A request body holds a key of `READ_ONLY_FIELDS`."""


def read_only_field_paths(body: Any, where: str = "body") -> list[str]:
    """Every place `body` holds a key of `READ_ONLY_FIELDS`, at any depth:
    `body.line_code`, `body.transactions[2].statement_line`, `body.parts[0].statement_place`, …"""
    if isinstance(body, dict):
        found = [f"{where}.{key}" for key in READ_ONLY_FIELDS if key in body]
        for key, value in body.items():
            found += read_only_field_paths(value, f"{where}.{key}")
        return found
    if isinstance(body, list | tuple):
        return [
            p for i, item in enumerate(body) for p in read_only_field_paths(item, f"{where}[{i}]")
        ]
    return []


def refuse_read_only_fields(method: str, path: str, body: Any) -> None:
    """Record and raise `ReadOnlyFieldLeak` when `body` holds a key of
    `READ_ONLY_FIELDS` anywhere.

    Called before the request goes out, by every fake engine the suite has:
    `FakeClient` (and any function a test puts in place of its `post`/`put`),
    the real `httpx.Client.send` under respx (conftest), and test_batch_write's
    scripted client."""
    found = read_only_field_paths(body)
    if not found:
        return
    sends = ", ".join(f"{where.rsplit('.', 1)[1]} at {where}" for where in found)
    leak = f"{method} {path} sends {sends}"
    READ_ONLY_FIELD_LEAKS.append(leak)
    raise ReadOnlyFieldLeak(
        f"{leak}: the engine sets each and refuses it in every request body (422 UNKNOWN_FIELD)"
    )


def sent_json(request: httpx.Request) -> Any:
    """The JSON body of an outgoing httpx request, or None when it has none."""
    try:
        content = request.content
    except httpx.RequestNotRead:
        return None
    if not content:
        return None
    try:
        return json.loads(content)
    except ValueError:
        return None


def _refusing_read_only_fields(method: str, send: Callable) -> Callable:
    """`send` (a `post`/`put`), checked by `refuse_read_only_fields` before it runs.
    The body is the `json_body` argument, by keyword or second positional."""

    @functools.wraps(send)
    def checked(path: str, *args: Any, **kwargs: Any) -> Any:
        body = kwargs["json_body"] if "json_body" in kwargs else (args[0] if args else None)
        refuse_read_only_fields(method, path, body)
        return send(path, *args, **kwargs)

    return checked


# ---------------------------------------------------------------------------
# TUI fakes and waits
# ---------------------------------------------------------------------------


class FakeClient:
    """Instance-level recorder standing in for expense.http.ExpenseClient.

    Only intercepts LAZY imports (`from expense.http import ExpenseClient`
    inside a function) — all TUI write/read sites qualify. The sheet import
    binds ExpenseClient at module top; keep respx for it.

    Every request is recorded as (METHOD, path, body) in `calls`; the
    `requests`/`posts`/`puts`/`deletes` properties are filtered views. GETs
    answer from `get_responses` (miss → EngineError 404, matching the engine's
    not-provisioned behavior). Set `errors["POST"] = exc` to make a verb raise.

    A `post` or `put` answers `write_responses[path]` when the test sets it, exactly
    that; otherwise, as a `delete` always does, the endpoint's `FAKE_ANSWERS` entry
    when it has one, in the engine's shape, or else `{}`. `write_responses` is keyed by
    path alone, so `delete` never reads it: a PUT answer set for a path never comes
    back on a DELETE of it. `run_write`'s `on_response` reads the
    engine's own body (`complete` carries `warnings` and `review_lines` on each balance).
    A statement's create, revert, complete and delete have entries: the create answers
    what it was sent;
    the other three answer the statement the path names, as the test serves
    `GET /statements/{id}` (or its id alone), with its status after the write.

    `post` and `put` are read through `__getattribute__`, which hands back the
    method checked by `refuse_read_only_fields` — so a function a test assigns to
    `client.post` or `client.put` is checked too, before it runs.
    """

    def __getattribute__(self, name: str) -> Any:
        attr = object.__getattribute__(self, name)
        if name in ("post", "put"):
            return _refusing_read_only_fields(name.upper(), attr)
        return attr

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.get_responses: dict[str, Any] = {}
        self.write_responses: dict[str, Any] = {}
        self.errors: dict[str, Exception] = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _record(self, method: str, path: str, body: Any = None) -> None:
        self.calls.append((method, path, body))
        err = self.errors.get(method)
        if err is not None:
            raise err

    def get(self, path: str, *, auth: bool = True, params: dict | None = None) -> dict:
        self._record("GET", path, params)
        if path in self.get_responses:
            return self.get_responses[path]
        raise EngineError("NOT_FOUND", f"no fake response for GET {path}", None, 404, {})

    def _answer(self, method: str, path: str, body: Any = None) -> dict:
        if method != "DELETE" and path in self.write_responses:
            return self.write_responses[path]
        for verb, pattern, answer in FAKE_ANSWERS:
            match = pattern.fullmatch(path)
            if verb == method and match:
                return answer(self, body, **match.groupdict())
        return {}

    def post(self, path: str, json_body: dict | None = None) -> dict:
        self._record("POST", path, json_body)
        return self._answer("POST", path, json_body)

    def put(self, path: str, json_body: dict | None = None) -> dict:
        self._record("PUT", path, json_body)
        return self._answer("PUT", path, json_body)

    def delete(self, path: str) -> dict:
        self._record("DELETE", path)
        return self._answer("DELETE", path)

    @property
    def requests(self) -> list[tuple[str, str]]:
        return [(method, path) for method, path, _ in self.calls]

    @property
    def posts(self) -> list[tuple[str, Any]]:
        return [(path, body) for method, path, body in self.calls if method == "POST"]

    @property
    def puts(self) -> list[tuple[str, Any]]:
        return [(path, body) for method, path, body in self.calls if method == "PUT"]

    @property
    def deletes(self) -> list[str]:
        return [path for method, path, _ in self.calls if method == "DELETE"]


def run_app(
    body: Callable,
    *,
    size: tuple[int, int] | None = None,
    setup: bool = False,
    toasts: bool = False,
):
    """Run `body(pilot, app)` inside a live ExpenseApp and return its result.

    Every TUI test needs the same four lines — an app, `run_test`, a pilot, and
    an `asyncio.run` to drive it. A copy per test is not only repetition: it is
    an independent chance to boot the app slightly differently, and a
    suite-wide change (a default size, a fixture, an exception-handling
    wrapper) would have to be made in every one or not at all.

    `size` is passed through to `run_test` only when given, so the default stays
    Textual's rather than a number this helper invented. A screen that depends
    on a viewport says so at its own call site.

    `setup=True` opens the app on its setup screen, as `expense.tui.app.launch` does when
    there is no settings file it can use. The default is Home, whatever the
    (hermetic, missing) config file says, so a screen test never has to write one.

    `toasts=True` draws each toast on the screen, as the app does outside a
    test (`run_test` draws none unless asked), for a test that reads what a
    toast shows (`toasts_shown`).

    The ExpenseApp import is function-local: this module stays free of Textual
    at import time so the sheet-import tests do not pay for it (see the module
    docstring).
    """
    from expense.tui.app import ExpenseApp

    async def scenario():
        app = ExpenseApp(setup=setup)
        options: dict[str, Any] = dict(size=size) if size else {}
        if toasts:
            options["notifications"] = True
        async with app.run_test(**options) as pilot:
            return await body(pilot, app)

    return asyncio.run(scenario())


def toasts_shown(app) -> list[str]:
    """What each toast on the screen shows, its title and its message as drawn,
    oldest first. Needs `run_app(..., toasts=True)`.

    The toasts are found by their CSS type name, `Toast`, the selector Textual's
    own default CSS styles them by: the class itself lives in the private
    `textual.widgets._toast` and is not exported from `textual.widgets`."""
    return [toast.render().plain for toast in app.screen.query("Toast")]


def styled_stretches(markup: str) -> list[tuple[int, str, str]]:
    """Each styled stretch of content markup as drawn, in order: `(start, words,
    style)`, its words without the line break that may end it, since a line
    break shows no colour.

    The Content import is function-local: see the module docstring."""
    from textual.content import Content

    content = Content.from_markup(markup)
    return [
        (span.start, content.plain[span.start : span.end].rstrip("\n"), str(span.style))
        for span in content.spans
    ]


async def wait_for(
    pilot,
    predicate: Callable[[], object],
    *,
    timeout: float = 2.0,
    interval: float = 0.02,
    message: str | None = None,
) -> None:
    """Pause the pilot until predicate() is truthy.

    Fails the test on timeout — a timed-out wait should point at the wait
    site, not surface as a confusing assert a few lines later.
    """
    for _ in range(max(1, round(timeout / interval))):
        await pilot.pause(interval)
        if predicate():
            return
    pytest.fail(message or f"wait_for: condition still false after {timeout}s")


def section_settled(app) -> bool:
    """The active SectionScreen's load ran to its end: started, and its
    `section-load` worker finished.

    That worker hands its result to the UI thread with `call_from_thread`,
    which waits for the screen's `_show` (or `_error`) to return — the
    subclass's own tail included, such as focusing a list or setting a mode.
    So a finished worker means the screen settled. Seeing `#card` in the DOM
    does not: the card is queryable before its children are mounted, and a
    test that reads it then finds an empty card.
    """
    screen = app.screen
    if not getattr(screen, "_started", False):
        return False
    return not any(
        worker.node is screen and worker.group == "section-load" and not worker.is_finished
        for worker in app.workers
    )


async def wait_for_loaded(pilot, app) -> None:
    """Until the active SectionScreen resolved — its load settled, with #card
    (data) or .error mounted."""
    await wait_for(
        pilot,
        lambda: (
            section_settled(app)
            and (bool(app.screen.query("#card")) or bool(app.screen.query(".error")))
        ),
        message="SectionScreen never finished loading (no #card or .error mounted)",
    )


def list_ready(app) -> bool:
    """The active SectionScreen's load settled, its CursorList is there and its
    loader is gone.

    Exposed as a plain predicate, not only as the waiter below, so call sites
    that need an *extra* condition (a row count, a filtered legend) can write
    `list_ready(app) and ...` instead of re-open-coding the pair.
    """
    from expense.tui.widgets.cursor_list import CursorList  # local: see module docstring

    return (
        section_settled(app)
        and bool(app.screen.query(CursorList))
        and not app.screen.query("#content LoadingIndicator")
    )


async def wait_for_list(pilot, app) -> None:
    """Until the active SectionScreen's list is mounted and done loading."""
    await wait_for(
        pilot,
        lambda: list_ready(app),
        message="list never finished loading (no CursorList, or LoadingIndicator still up)",
    )


# ---- Home's month ---------------------------------------------------------------
#: Two months as `/reports/monthly` returns them. @Pendiente holds only rows still
#: waiting for a hashtag, which the engine groups under the built-in pending
#: hashtag `h-pend` like any other (contract: GET /v1/dashboard); WANTS holds two
#: hashtags, and HOGAR nothing in either month — so Home must not draw it. Ids
#: carry a hyphen so scripts/check_fixture_drift.py does not read the
#: hashtag-name map's keys as engine fields.
HOME_MONTHS = [
    {
        "month": {"year": 2026, "month": 8},
        "categories": [
            {
                "id": "c-pend",
                "name": "@Pendiente",
                "spent_home_cents": -26620,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": ["h-pend"], "spent_home_cents": -26620, "unconverted_count": 0}
                ],
            },
            {
                "id": "c-wants",
                "name": "WANTS",
                "spent_home_cents": -160843,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": ["h-sal"], "spent_home_cents": -64850, "unconverted_count": 0},
                    {"hashtag_ids": ["h-otr"], "spent_home_cents": -95993, "unconverted_count": 0},
                ],
            },
            {
                "id": "c-hogar",
                "name": "HOGAR",
                "spent_home_cents": 0,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
        ],
        "totals": {
            "inflow_home_cents": 0,
            "outflow_home_cents": 187463,
            "net_home_cents": -187463,
            "unconverted_count": 0,
        },
    },
    {
        "month": {"year": 2026, "month": 9},
        "categories": [
            {
                "id": "c-pend",
                "name": "@Pendiente",
                "spent_home_cents": -1148746,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {
                        "hashtag_ids": ["h-pend"],
                        "spent_home_cents": -1148746,
                        "unconverted_count": 0,
                    }
                ],
            },
            {
                "id": "c-wants",
                "name": "WANTS",
                "spent_home_cents": 0,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
            {
                "id": "c-hogar",
                "name": "HOGAR",
                "spent_home_cents": 0,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
        ],
        "totals": {
            "inflow_home_cents": 82288,
            "outflow_home_cents": 1231034,
            "net_home_cents": -1148746,
            "unconverted_count": 0,
        },
    },
]
HOME_DASHBOARD = {
    "month": {"year": 2026, "month": 9},
    "bank_accounts": [
        {"id": "a-pen", "name": "BCP PEN", "currency_code": "PEN", "current_balance_cents": 514582},
        {"id": "a-usd", "name": "BCP USD", "currency_code": "USD", "current_balance_cents": 130},
    ],
    "people": [],
    "categories": [],
    "totals": {"net_home_cents": -1148746, "unconverted_count": 0},
}
HOME_TAG_NAMES = dict([("h-sal", "SALIDAS"), ("h-otr", "OTROS"), ("h-pend", "Pendiente")])


def stub_home_month(monkeypatch, *, months=None, dashboard=None, names=None, calls=None):
    """Answer Home's worker from the fixtures above. `calls`, when given, records
    each range read's `(from_ym, to_ym)`."""

    def fake_range(cfg, *, from_ym, to_ym, **kw):
        if calls is not None:
            calls.append((from_ym, to_ym))
        return dict(months=HOME_MONTHS if months is None else months)

    monkeypatch.setattr(
        "expense.reads.fetch_dashboard",
        lambda *a, **k: HOME_DASHBOARD if dashboard is None else dashboard,
    )
    monkeypatch.setattr("expense.reads.fetch_range", fake_range)
    monkeypatch.setattr(
        "expense.tui.screens.home.load_hashtag_name_map",
        lambda: HOME_TAG_NAMES if names is None else names,
    )
    monkeypatch.setattr("expense.config.ensure_loaded", lambda: object())


# ---------------------------------------------------------------------------
# scripts/check_fixture_drift.py, loaded as a module
# ---------------------------------------------------------------------------

DRIFT_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_fixture_drift.py"


def load_drift_script():
    """Load scripts/check_fixture_drift.py without importing `scripts` as a package.

    The script is deliberately not a pytest file — it reads the engine's
    openapi.json, and tests/unit is hermetic. Loading it costs no network; a
    test that runs its `main` mocks the engine with respx. The loader is imported here,
    not at the top, so a test that copies this file into a tmp tree needs nothing more.
    """
    from tests.scripts_loader import load_script

    return load_script(DRIFT_SCRIPT.name)
