from collections.abc import Hashable, Mapping
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

import typer

from expense.jsonout import json_text


class EngineError(Exception):
    """An engine error envelope `{ error: { code, message, fields, reasons } }`.

    `fields` maps each refused field to its message; `reasons` maps the same keys to
    the engine's reason code (contract: "Error reasons"). Both are `None` when the
    engine sends null. `raw_body` is the response body as sent, for `--json`.
    """

    def __init__(
        self,
        code: str,
        message: str,
        fields: dict[str, Any] | None,
        status: int,
        raw_body: dict[str, Any],
        reasons: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields
        self.reasons = reasons
        self.status = status
        self.raw_body = raw_body


class EngineConnectionError(Exception):
    def __init__(self, url: str, original: Exception):
        super().__init__(str(original))
        self.url = url
        self.original = original


class ConfigMissingError(Exception):
    pass


class ConfigInvalidError(Exception):
    pass


# The engine's code for a user whose settings do not exist yet (contract: "Error codes").
# Both rate reads list it among the codes they can return
# (contract: GET /v1/exchange-rates) (contract: GET /v1/exchange-rates/history).
SETTINGS_MISSING = "SETTINGS_MISSING"

# The reason a create that needs a new bank line is refused once every line code
# up to `#999999` has been given (contract: "Transactions (Ledger)", "Bank lines").
LINE_CODES_EXHAUSTED = "LINE_CODES_EXHAUSTED"


def refuses_every_write(err: Exception) -> bool:
    """True for a refusal that every further write of the run would draw too.

    Two do. `SETTINGS_MISSING` is about the account, not the request: it holds
    until first-time setup runs, and is matched on the error code alone.
    `LIMIT_REACHED` with `LINE_CODES_EXHAUSTED` holds for good: every line code
    has been given, so no create that needs a new bank line can land, and it is
    matched on the code and that reason under any key
    (contract: POST /v1/transactions/batch, "Line groups")
    (contract: POST /v1/accounts/{account_id}/opening-balance). A run of several
    writes stops on either and reports it once.
    """
    if not isinstance(err, EngineError):
        return False
    if err.code == SETTINGS_MISSING:
        return True
    return err.code == "LIMIT_REACHED" and LINE_CODES_EXHAUSTED in (err.reasons or {}).values()


def engine_words(err: EngineError) -> str:
    """The engine's own answer: `CODE — message`, then one line per refused field.

    `format_error` adds the app's lines under this; the sheet import prints these
    words alone (`engine_text`), and the setup screen shows a refused key in them
    with its own line under them saying what to do.
    """
    lines = [f"{err.code} — {err.message}"]
    if err.fields:
        for field, message in err.fields.items():
            lines.append(f"  {field}: {message}")
    return "\n".join(lines)


#: What joins two refused fields of one row on its line: each `field: words`
#: pair ends in the engine's own full stop, so a mark between them keeps the
#: pairs apart where a comma or a semicolon would run into it.
ROW_FIELD_JOINER = " · "


def row_words(err: EngineError) -> str:
    """The engine's words for one refused row of a batch, as a line of refusals
    grouped by kind shows them: each refused field's name, then its words whole,
    `category_id: Must not be null.`, two fields joined by ` · ` in the engine's
    order. The key is the field alone, as the row's refusal holds it (a row's
    place in a send is no place of the row's). The top-level message only when
    the refusal names no field, since a refusal naming several rows gives their
    count there, not words for one row."""
    pairs = [f"{key}: {text}" for key, text in (err.fields or {}).items()]
    return ROW_FIELD_JOINER.join(pairs) if pairs else err.message


def is_keyed_refusal(err: EngineError) -> bool:
    """True for a `409`/`422` that names what it refused by key, in `fields` or
    `reasons`: the only refusal a row's words (`row_words`) can say. Any other
    (a `401`, `403`, `404`, `5xx`, or a refusal naming no key) reads whole, its
    code and message first (`format_error`)."""
    return err.status in (409, 422) and bool(err.fields or err.reasons)


def row_note(err: EngineError) -> str:
    """What a refused row of several writes shows, as a line of refusals grouped
    by kind holds it: the engine's words for the row (`row_words`), then the
    app's lines under them (`app_lines`), one per line. The LOG bar's rows and
    the ledger's bulk edit both say a refused row this way."""
    return "\n".join([row_words(err), *app_lines(err)])


def refusal_kind(err: EngineError) -> Hashable:
    """Two refusals of one kind read the same for their rows, so a line of
    refusals grouped by kind says them once: the same code, `fields` and
    `reasons`, each keyed by field. The top-level message is left out of it,
    since a refusal naming several items gives their count there."""
    return (
        err.code,
        tuple(sorted((str(k), str(v)) for k, v in (err.fields or {}).items())),
        tuple(sorted((str(k), str(v)) for k, v in (err.reasons or {}).items())),
    )


#: The codes whose refusals always name the rule that fired: `fields` and
#: `reasons` are never null on them, keyed by the thing refused
#: (contract: "Base Conventions", "`fields` and `reasons` semantics").
#: Not read by `next_step` (the table's (code, reason) key already picks the
#: line); it is the source the table guard in tests/unit/test_errors.py checks
#: every `NEXT_STEPS` row against, the `VALIDATION_ERROR` ones aside.
REFUSAL_CODES = frozenset({"CONFLICT", "FORBIDDEN", "LIMIT_REACHED"})


@dataclass(frozen=True)
class NextStep:
    """The app's one line under a refusal, saying what to do next.

    `line` is the line on every screen. `on_list` replaces it on a list, where
    `r` reads the list again; elsewhere (a form, the LOG bar, the bank import)
    saving again is the retry. `by_key` picks the line by the reason's key, for
    a reason two resources share (contract: "Error reasons") or a line that suits
    one key alone; with no `line`, every other key draws none. A key in
    `no_line_on` draws no line at all.
    """

    line: str | None = None
    on_list: str | None = None
    by_key: Mapping[str, str] = field(default_factory=dict)
    no_line_on: frozenset[str] = frozenset()

    def pick(self, key: str, *, on_list: bool) -> str | None:
        if key in self.no_line_on:
            return None
        if key in self.by_key:
            return self.by_key[key]
        if on_list and self.on_list is not None:
            return self.on_list
        return self.line


#: The line under a refused delete of a system category, and the Categories
#: list's legend: a system category keeps its name and stays
#: (contract: PUT /v1/categories/{category_id}, "A system category keeps its name").
SYSTEM_HINT = "System categories cannot be renamed or deleted."

_APP_FAULT = (
    "Not your mistake: the app sent it wrong and nothing was saved. "
    "Try again; if it happens again, report it."
)

#: Every refusal the app can meet that has a line of its own, keyed by the
#: engine's `code` and reason, never by HTTP status, route or wording —
#: docs/decisions.md "Hints are chosen by the engine's reasons, never its wording".
#: The reasons are the contract's (contract: "Error reasons"). Left out on purpose:
#: `IN_COMPLETED_RECONCILIATION`, whose message already says to revert the
#: reconciliation to draft first (contract: DELETE /v1/transactions/{transaction_id})
#: (contract: DELETE /v1/bank-lines/{bank_line_id}),
#: `ACCOUNT_ARCHIVED`, whose words already say to unarchive the account first
#: (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts")
#: (contract: PUT /v1/reconciliations/{reconciliation_id}, "Archived accounts")
#: (contract: POST /v1/accounts/{account_id}/make-person),
#: `KIND_UNCHANGED`, whose words already say the account is of that kind
#: (contract: POST /v1/accounts/{account_id}/make-person)
#: (contract: POST /v1/accounts/{account_id}/make-account),
#: `HAS_STATEMENT_CODE`, whose message already names the code and says to clear it
#: first (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"),
#: `PERSON_ACCOUNT`, whose words already say a person cannot have it
#: (contract: POST /v1/reconciliations, "A person account never has reconciliations"),
#: `STATEMENT_MONTH_TAKEN` and `COMPLETED_STATEMENT_JOINED` on a statement code,
#: whose words already name the reconciliations and say what to do
#: (contract: "Bank Accounts", "Statement code"),
#: and `SECRET_NOT_REPLAYABLE`, which only creating a sign-in key can draw
#: (contract: POST /v1/auth/pat), and the app never creates one.
NEXT_STEPS: dict[tuple[str, str], NextStep] = {
    ("CONFLICT", "HAS_TRANSACTIONS"): NextStep(
        by_key={
            "account_id": "To retire it instead, archive it: press a.",
            "category_id": "Move its transactions to another category first.",
        }
    ),
    ("FORBIDDEN", "SYSTEM_CATEGORY"): NextStep(SYSTEM_HINT),
    # The built-in pending hashtag is never deleted (contract: DELETE /v1/hashtags/{hashtag_id})
    # and keeps its name (contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps
    # its name"); Manage ▸ Hashtags offers neither, so this is met only rarely.
    ("FORBIDDEN", "SYSTEM_HASHTAG"): NextStep("The pending hashtag cannot be renamed or deleted."),
    ("CONFLICT", "NAME_EXISTS"): NextStep("That name is taken: pick another."),
    # Two live accounts share a statement code only when their currencies differ;
    # a deleted one does not hold its code (contract: "Bank Accounts", "Statement code").
    ("CONFLICT", "STATEMENT_CODE_EXISTS"): NextStep(
        "Another account in this currency has this code: pick another, or clear it there first."
    ),
    ("LIMIT_REACHED", "CAP_REACHED"): NextStep("Delete one first."),
    ("CONFLICT", "OPERATION_CODE_EXISTS"): NextStep(
        "That account already has a row with this operation number: look there for a duplicate."
    ),
    ("CONFLICT", "CONCURRENT_CHANGE"): NextStep(
        "It changed at the same moment: save again.",
        on_list="It changed at the same moment: press r, then try again.",
    ),
    # On `hashtag_ids` (a transaction write) and `hashtag_id` (a hashtag
    # delete) a user hashtag holds the pending hashtag's name, and the engine's
    # message already names the remedy, so the category line stays off
    # (contract: "Hashtags", "When the engine creates it").
    ("CONFLICT", "RESERVED_NAME_HELD"): NextStep(
        "One of your categories has a built-in category's name: "
        "rename it on Manage ▸ Categories, then save again.",
        no_line_on=frozenset({"hashtag_ids", "hashtag_id"}),
    ),
    ("CONFLICT", "OPENING_BALANCE_EXISTS"): NextStep(
        "It got one meanwhile: close the form and open it again to change it."
    ),
    # A person carries no opening balance, so `t` on Manage ▸ Accounts cannot
    # turn an account that has one (contract: POST /v1/accounts/{account_id}/make-person);
    # emptying its opening line on the Edit form deletes it.
    ("CONFLICT", "HAS_OPENING_BALANCE"): NextStep("Press e and empty its opening balance first."),
    # A person never has reconciliations, so `t` cannot turn an account with
    # one, draft or completed, until each is deleted, a completed one after its
    # revert (contract: POST /v1/accounts/{account_id}/make-person, "Refusals").
    ("CONFLICT", "HAS_RECONCILIATION"): NextStep(
        "On Reconciliations, press d on each of its reconciliations; a completed one needs u first."
    ),
    ("CONFLICT", "RECONCILIATION_NOT_DRAFT"): NextStep("Press u to revert it, then d again."),
    ("CONFLICT", "ID_EXISTS"): NextStep(_APP_FAULT),
    ("CONFLICT", "IDEMPOTENCY_KEY_REUSED"): NextStep(_APP_FAULT),
    # An opening balance stays on its account and in @Opening; the refusal is a
    # validation error naming the field (contract: PUT /v1/transactions/{transaction_id},
    # "Opening balances stay put").
    ("VALIDATION_ERROR", "OPENING_BALANCE_ACCOUNT_FIXED"): NextStep(
        "To move an opening balance, set it on the other account's Edit form."
    ),
    ("VALIDATION_ERROR", "OPENING_BALANCE_CATEGORY_FIXED"): NextStep(
        "An opening balance always stays in @Opening."
    ),
    # A reconciliation completes only with its ending balance entered (contract:
    # POST /v1/reconciliations/{reconciliation_id}/complete, "The ending balance must be
    # entered"); `c` on the batch screen asks for it when the screen reads it as empty.
    ("VALIDATION_ERROR", "ENDING_BALANCE_REQUIRED"): NextStep(
        "Press c again: the app asks for it first."
    ),
    # A system row's name is not for a user row: a user category, new or
    # renamed, cannot be named like `@Opening` or `@Pendiente`
    # (contract: POST /v1/categories, "Reserved names")
    # (contract: PUT /v1/categories/{category_id}), and a user
    # hashtag, new or renamed, cannot take the pending hashtag's name, in any
    # letter case (contract: "Hashtags", "The built-in pending hashtag"). One line
    # for both.
    ("VALIDATION_ERROR", "RESERVED_NAME"): NextStep(
        "That name belongs to a system row: pick another."
    ),
    # A system category and the pending hashtag keep their names
    # (contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
    # (contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name").
    ("VALIDATION_ERROR", "SYSTEM_NAME_FIXED"): NextStep(
        "Built-in names never change: press esc to leave it as it is."
    ),
    # An opening balance carries no hashtag, not even the pending one. The line
    # shows on a transaction write's `hashtag_ids`
    # (contract: PUT /v1/transactions/{transaction_id}): the ledger's bulk `h`
    # over a selection holding one. The Edit form's whole-line write names the
    # part's `parts.<i>.hashtag_ids` (contract: PUT /v1/bank-lines/{bank_line_id},
    # "A line holding an opening balance keeps its parts"), where no line shows:
    # the engine's words alone.
    ("VALIDATION_ERROR", "OPENING_BALANCE_NOT_TAGGED"): NextStep(
        by_key={"hashtag_ids": "Leave the opening balance out of the selection."}
    ),
}


def next_step(err: Exception, *, on_list: bool = False) -> str | None:
    """The line saying what to do after `err`, or None when it has none.

    Chosen by the error's `code` and `reasons` alone, as a pair: the same
    reason under another code has no line. The first refused key with a line
    wins. `on_list` is for a refusal met on a list screen.
    """
    if not isinstance(err, EngineError):
        return None
    for key, reason in (err.reasons or {}).items():
        step = NEXT_STEPS.get((err.code, str(reason)))
        if step is not None:
            line = step.pick(str(key), on_list=on_list)
            if line is not None:
                return line
    return None


def is_own_id_replay(err: Exception, key: str) -> bool:
    """True when the engine refused a create only because the id it carries,
    under `key`, is already taken: the app's own write, sent before and landed.

    Ids are minted by the app and reused on every attempt, so this is the one
    `409` that means "already saved"; any other reason, on any other key, is a
    refusal. A taken client-chosen id is `ID_EXISTS` keyed by the field that
    carries it: `id` on a create (contract: "Base Conventions", "Client-supplied
    UUIDs"), `transaction_id` on an opening balance
    (contract: POST /v1/accounts/{account_id}/opening-balance), `transactions.<i>.id`
    in a batch (contract: POST /v1/transactions/batch), which the batch writer
    reads per item, as `id`. A create sent again answers it alone, before any
    other refusal (contract: "Base Conventions", "Which refusal comes first on a create").
    """
    return (
        isinstance(err, EngineError)
        and err.code == "CONFLICT"
        and err.reasons == {key: "ID_EXISTS"}
    )


def engine_text(err: Exception) -> str:
    """The engine's words alone, with no line of the app's: what the sheet
    import prints. Anything that is not an engine error reads as in
    `format_error`."""
    if isinstance(err, EngineError):
        return engine_words(err)
    return format_error(err)


def app_lines(err: EngineError, *, on_list: bool = False) -> list[str]:
    """The app's lines `format_error` puts under the engine's words, each after
    a blank line: `next_step`'s line (`on_list` on a list screen), then a hint
    chosen by the status or the error code. Empty when the refusal has none. A
    screen that lays the engine's words out itself (the Edit form, under its
    parts) adds these under them."""
    lines: list[str] = []
    step = next_step(err, on_list=on_list)
    if step is not None:
        lines.append(step)
    if err.status == 401:
        lines.append(
            "Hint: the key is missing or not valid. Set a fresh one on System ▸ Config (press t)."
        )
    if err.code == SETTINGS_MISSING:
        lines.append(
            "Hint: First-time setup is not done yet. Open System ▸ Auth & profile and press b."
        )
    return lines


def key_index(key: object, collection: str) -> int | None:
    """The item a refusal's key names in a list the request sent, from 0:
    `<collection>.<i>` or `<collection>.<i>.<field>` gives `i`; any other key
    gives None. One reader for every screen that names a refused item by its
    place: the bank import's `rows`, the split's `parts`."""
    bits = str(key).split(".", 2)
    if len(bits) >= 2 and bits[0] == collection and bits[1].isdigit():
        return int(bits[1])
    return None


def key_field(key: object, collection: str) -> str | None:
    """The field a refusal's key names on an item of a list the request sent:
    `<collection>.<i>.<field>` gives `field`; `<collection>.<i>`, which names the
    item alone, and any other key give None. The one reader of an item key's
    field, beside `key_index` for its place."""
    if key_index(key, collection) is None:
        return None
    bits = str(key).split(".", 2)
    return bits[2] if len(bits) == 3 else None


def format_error(err: Exception, *, on_list: bool = False) -> str:
    """Human-readable error text for the app's toasts, notes and banners.

    The engine's words, then, after a blank line, the app's line saying what to
    do: `next_step`'s for a refusal (`on_list` on a list screen), or a hint
    chosen by the status or the error code, never by `message` or the `fields`
    texts. The sheet import prints `engine_text` instead.
    """
    if isinstance(err, EngineError):
        return "\n\n".join([engine_words(err), *app_lines(err, on_list=on_list)])
    if isinstance(err, EngineConnectionError):
        return f"could not reach engine at {err.url} (is it running?)"
    # ConfigMissing/ConfigInvalid render as their message, same as any other
    # exception — one fallback covers both.
    return str(err)


# The shared-envelope error families: {ExcType: (envelope code, exit code)}.
# EngineError stays a dedicated branch in render() — its --json output is the
# engine's raw body passed through verbatim, not a client-composed envelope.
_ENVELOPE_ERRORS: dict[type[Exception], tuple[str, int]] = {
    EngineConnectionError: ("CONNECTION_ERROR", 6),
    ConfigMissingError: ("CONFIG_MISSING", 3),
    ConfigInvalidError: ("CONFIG_INVALID", 3),
}

# Everything handle_errors catches — registering a type in _ENVELOPE_ERRORS
# is the single step that makes it render cleanly.
_HANDLED_ERRORS: tuple[type[Exception], ...] = (EngineError, *_ENVELOPE_ERRORS)


def render(err: Exception, *, json_mode: bool) -> tuple[str, int, bool]:
    """Render an error.

    Returns (output_text, exit_code, use_stderr).
    JSON mode writes to stdout so output is pipe-friendly; human mode writes to
    stderr, in the engine's words alone (`engine_text`).
    """
    if isinstance(err, EngineError):
        if json_mode:
            return json_text(err.raw_body), 1, False
        return "Error: " + engine_text(err), 1, True

    for exc_type, (code, exit_code) in _ENVELOPE_ERRORS.items():
        if isinstance(err, exc_type):
            if json_mode:
                envelope = {
                    "error": {"code": code, "message": str(err), "fields": None, "reasons": None}
                }
                return json_text(envelope), exit_code, False
            return "Error: " + engine_text(err), exit_code, True

    raise err


def handle_errors(fn):
    """Wrap a Typer command so engine/connection/config errors exit cleanly."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        json_mode = bool(kwargs.get("json_output", False))
        try:
            return fn(*args, **kwargs)
        except _HANDLED_ERRORS as err:
            output, exit_code, use_stderr = render(err, json_mode=json_mode)
            typer.echo(output, err=use_stderr)
            raise typer.Exit(code=exit_code) from err

    return wrapper
