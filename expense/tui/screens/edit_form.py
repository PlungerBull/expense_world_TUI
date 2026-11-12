"""Edit a bank line — the bar-cycle form with its parts.

One input bar cycles through the line's fields, then every part's; the summary
below shows them. On top, what every part shares: DATE › TITLE › ACCOUNT (the
"no statement" form adds OPERATION before ACCOUNT); below, the table of the parts,
one line each with its amount, category, hashtags and note (`parts_table.py`),
and, with two parts or more, the line adding them up against the line's total.
The bar moves from the shared fields to part 1's AMOUNT › CATEGORY › HASHTAGS
› NOTE, then part 2's; it names the part (`PART 1 AMOUNT`) and the table marks
it `▌ 1`. A part's NOTE hint reads `optional · enter to go on` while `⏎` goes
on to another line, and `optional · enter saves · (ctrl+s anytime)` on the
last.

**Edit only** — `+` opens the LOG bar ([log_bar.py](log_bar.py)). `⏎` and `s`
on a ledger row open this form on the row's bank line (`EditFormScreen`), on
the first line that can change, with every part of the line in the table
whichever part the row is;
`⏎` in the Statements screen's "no statement" list opens it on the line the list
holds (`BankLineEditFormScreen`). Entity fields (account, a part's category
and hashtags) show a live-filtered suggestion list — pick existing entities
only. Their bar opens empty, the list in its usual order; on ACCOUNT and
CATEGORY the highlight starts on the line's account or the part's category
whenever the bar is empty and the list holds it, so `⏎` with nothing typed
keeps it (`_recompute`). The category list is the one the ledger's bulk `c`
offers: @Pendiente is in it and @Opening never is (`reads.pickable_categories`).

**The form reads the line once and takes what is read-only from it alone.**
The ledger's form reads the row's line with one `GET /bank-lines/{id}`; the
"no statement" form has it from the list. The line's `edit_limits` says what a
write would refuse on it as it stands
(contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"): each line
field in `locked_fields` and each part field in `locked_part_fields` shows
`read-only`, dimmed, the bar skipping it, and the form opens on the first line
that can change; with `parts_fixed` there is no `^n Add part` and no `^x Drop
part`. Each locked field carries the engine's sentence for it, shown as sent: under the line
fields one dim line per sentence names the lines it covers
(`date, title, account: <sentence>`, `reason_lines`), and under the parts each
column's `read-only` line carries its sentences (`amount  read-only · <sentence>`,
`readonly_lines`). With the total fixed and the parts not (a completed
statement's line), a line of one part has its amount, the total,
read-only; once the table holds two parts or more, the amounts move between
the parts, so none is read-only. The form reads no statement and keeps no rule of its own on
what a line may change.

`^n` adds an empty part at the end and puts the bar on its AMOUNT; `^x`, on a
part's line while there are two or more, drops that part at once, the bar
moving to the same line on the part above. A part added and left empty is left
out of the save (`part_empty`).

**One save, one write.** `ctrl+s` (or `⏎` where no line after can change)
first keeps what is typed in the bar, as `⏎` would, then sends the line in
one `PUT /bank-lines/{id}` through `run_write` (one idempotency key, the same
on a retry), its body built by
[bank_line_write.py](../../bank_line_write.py) (contract: PUT /v1/bank-lines/{bank_line_id}):

- the line fields the owner changed, and only those, so a read-only one is
  never sent: `date`, `title`, `account_id` and `currency_code`, and on the
  "no statement" form `operation_code`, whose `null` clears it. The ACCOUNT line
  picks one account (one row each), the CURRENCY line after it one of the
  currencies that account holds (`_codes`); each starts on the line's own, and
  only the key that changed is sent: the account alone for the same currency on
  another account, the currency alone for another currency of the same account,
  both for another account's other currency, neither for what the line already
  has. An account holding one currency is not asked: the account goes alone and the
  engine moves the line to that currency, the amount as it is
  (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction"). A move of the
  account also sends `statement_id: null`, so it takes the line
  out of its statement; a move of the currency alone sends the statement the line is
  in, so it stays there (`unassign_on_move`)
  (contract: "Statements", "Assigning transactions"). CURRENCY is dim, with why, and the
  bar skips it while the account holds one currency; a change of account to one
  holding one currency shows it (`· was USD · not converted` when it is another than
  the line's) and sends the account alone, to one holding several empties it, and
  `ctrl+s` with none picked stops on the line, sending nothing;
- `parts`, the line's complete set: each part read from the line under its own
  id, with its current signed amount always and its category, note and
  hashtags only when changed (`kept_part`), a part added under a fresh id
  (`new_part`), a dropped part left out, so the engine deletes it
  (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts").

A save that changes nothing says `No changes to save.` and sends nothing.
Saved, the note says `Saved. It left its statement.` when the engine's
answer flags a part `left_statement`, and `Saved.` otherwise (`moved_parts`)
(contract: PUT /v1/bank-lines/{bank_line_id}, "Response"). A refused save
stays under the parts until something changes: the engine's words, each
`parts.<i>.<field>` key read as `part i+1 (field)`, the amounts a refusal
names in the error colour, `Nothing was saved.`, and the app's line for the
reason, if any (`refusal_lines`).

`⏎` on an emptied note empties it, sent as `description: ""`; an empty date bar
commits today, a date the save's reader (`to_canonical_aware`) cannot read is
refused at `⏎` with `Date: use YYYY-MM-DD.` and the cursor stays, an emptied
title is refused (`_title_given`), and an amount must be a non-zero signed
decimal. A hashtag set that names a real hashtag never carries the pending one
(`hashtags_to_send`).

While the date, title, operation, account or currency is under the bar on a line of two
parts or more, the hint adds `changes every part of the transaction`: the engine writes
the line fields onto every part (contract: "Transactions (Ledger)", "Bank lines").

`enter` keeps the field and moves on, and saves only on the last line that can
change (`FormScreen._advance`) · `tab` / `shift+tab` move between fields · `↑/↓`
move the suggestion highlight, or the field when there is no list · `ctrl+s`
submits. Sign explicit (− expense / + income); the currency is the one the ACCOUNT
line picks. The keymap is `form_bindings` in _form.py, with `^n` and `^x`.
"""

import copy
from collections.abc import Callable
from dataclasses import replace
from datetime import date as date_cls

from rich.console import Group, RenderableType
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Input, Static

from expense import reads
from expense.bank_line_write import kept_part, line_body, new_part
from expense.currencies import only_currency
from expense.dates import is_readable_date, to_canonical_aware
from expense.errors import format_error
from expense.formatting import (
    bank_line_columns,
    codes_and,
    resolve_name,
    signed_cents,
    title_or_untitled,
    whole_number,
)
from expense.number_format import amounts_are, current_format
from expense.quickadd.money import amount_to_text, parse_amount
from expense.reads import QuickAddRefs, hashtags_to_send, load_quickadd_refs
from expense.tui.screens._base import (
    LeftBehind,
    call_while_attached,
    not_saved_line,
    screen_fetch_kwargs,
)
from expense.tui.screens._form import FormScreen, form_bindings, open_it_again
from expense.tui.screens.log_bar import LOADING_HINT
from expense.tui.theme import ACCENT, PALETTE, TRANSACTION_RULE
from expense.tui.widgets.cells import amount_text
from expense.tui.widgets.parts_table import (
    ENGINE_FIELDS,
    FIELDS,
    NOTHING_SAVED,
    Part,
    count_line,
    flagged_parts,
    lock_message,
    part_empty,
    part_from_engine,
    parts_lines,
    readonly_lines,
    real_hashtags,
    reason_lines,
    refusal_lines,
    refusal_text,
)
from expense.tui.widgets.picker import matching, suggestion_list
from expense.tui.widgets.refusal import hanging, toast

_LABELS = {
    "date": "DATE",
    "title": "TITLE",
    "amount": "AMOUNT",
    "operation": "OPERATION",
    "account": "ACCOUNT",
    "currency": "CURRENCY",
    "category": "CATEGORY",
    "hashtags": "HASHTAGS",
    "note": "NOTE",
}
_HINTS = {
    "date": "YYYY-MM-DD · enter to accept, or type a date",
    "title": "free text · enter to go on",
    "amount": "signed decimal · − expense / + income · in the account's currency",
    "operation": "optional · the bank's operation number · empty clears it",
    "account": "pick an existing account · ↑↓ highlight · enter select",
    "category": "pick an existing category · ↑↓ highlight · enter select",
    "hashtags": "type a tag · ↑↓ highlight · enter adds & stays · empty enter = done (optional)",
}
#: A part's NOTE hint where `⏎` saves (the last line that can change), and where
#: it goes on to another line.
NOTE_SAVES = "optional · enter saves · (ctrl+s anytime)"
NOTE_GOES_ON = "optional · enter to go on"
#: TITLE's hint when no line after it can change, so `⏎` there saves.
TITLE_SAVES = "free text · enter to save"
#: The note when DATE holds what the save's reader cannot read; the words the
#: app's other dates use ("Date Start: use YYYY-MM-DD.", "As of: use YYYY-MM-DD.").
DATE_UNREADABLE = "Date: use YYYY-MM-DD."
#: The CURRENCY line's value while an account holding several has none picked.
NONE_PICKED = "— pick one"
# The fields every part of a line shares (only the "no statement" form has an
# OPERATION line), and what the hint adds on them while the line has two parts
# or more.
_EVERY_PART = {"date", "title", "operation", "account", "currency"}
EVERY_PART_NOTE = "changes every part of the transaction"
# The line fields' names in the whole-line write
# (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"). The ACCOUNT line holds
# an account and a currency, so it writes two of them (`_line_fields`).
_ENGINE_FIELD = {
    "date": "date",
    "title": "title",
    "operation": "operation_code",
    "account": "account_id",
    "currency": "currency_code",
}
_FORM_KEY = {engine: key for key, engine in _ENGINE_FIELD.items()}
# Each part field's attribute on `Part`.
_PART_ATTR = {
    "amount": "amount_cents",
    "category": "category_id",
    "hashtags": "hashtag_ids",
    "note": "note",
}


def part_key(index: int, field: str) -> str:
    """The form's key for a part's field: `0.amount` is part 1's AMOUNT."""
    return f"{index}.{field}"


def split_key(key: str) -> tuple[int, str] | None:
    """`(index, field)` of a part's key; None for a line field."""
    head, _, field = key.partition(".")
    return (int(head), field) if field and head.isdigit() else None


def unassign_on_move(payload: dict, record: dict, *, keep_on_currency_move: bool = False) -> None:
    """Make an account or currency move take the row out of its statement.

    A write that changes `account_id` or `currency_code` on a row assigned to a
    draft statement must say what happens to the assignment, or the engine
    refuses it (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules"). So a payload whose
    `account_id` or `currency_code` differs from the record's gains
    `statement_id: None` — the move unassigns. A key equal to the record's is
    not a move and gains nothing, so the row keeps its statement.

    With `keep_on_currency_move`, a move of the currency alone sends the record's own
    `statement_id` instead, so the row stays in its statement: the statement is the
    account's, and the account is the same.

    Whether a part did leave its statement is the engine's answer to say
    (`moved_parts`). Mutates `payload`; shared by the Edit form, whose record is
    the bank line (with the `statement_id` of its parts), and the ledger's bulk
    `b` and `m`, whose record is a transaction.
    """
    moved = [
        key
        for key in ("account_id", "currency_code")
        if key in payload and payload[key] != record.get(key)
    ]
    if moved:
        stays = keep_on_currency_move and moved == ["currency_code"]
        payload["statement_id"] = record.get("statement_id") if stays else None


def moved_parts(answers: list[dict]) -> tuple[int, int]:
    """(parts moved, parts that left their statement) across the answers
    of one or more writes, each part counted once by its id.

    Every answer lists in `changed_parts` each part of the bank line whose line
    field the write changed, and flags `left_statement` on a part that was
    in a statement before and is in none or another after
    (contract: PUT /v1/transactions/{transaction_id}, "Response")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Response"). Moving both
    parts of a line lists both in the first answer and none in the second, so
    the move counts 2. Shared by the ledger's bulk `b` (its receipt) and the
    Edit form (its note).
    """
    moved: set[object] = set()
    left: set[object] = set()
    for answer in answers:
        for entry in answer.get("changed_parts", []):
            key = entry["transaction"]["id"]
            moved.add(key)
            if entry["left_statement"]:
                left.add(key)
    return len(moved), len(left)


def saved_words(answer: dict) -> str:
    """What a saved Edit form says, decided from the engine's answer: the form's
    note, or the app's toast when the save answers after the form was left."""
    return "Saved. It left its statement." if moved_parts([answer])[1] > 0 else "Saved."


def part_payload(part: Part, held: dict | None, pending_hashtag_id: str | None) -> dict:
    """One entry of the save's `parts`: a part read from the line under its own
    id, against `held`, the part as the engine holds it (`kept_part`); a part
    added in the form under a fresh id, with what it holds (`new_part`)."""
    if held is None:
        return new_part(
            amount_cents=part.amount_cents,
            category_id=part.category_id,
            description=part.note,
            hashtag_ids=real_hashtags(part, pending_hashtag_id),
        )
    return kept_part(
        held,
        amount_cents=part.amount_cents,
        category_id=part.category_id,
        description=part.note,
        hashtag_ids=part.hashtag_ids,
        pending_hashtag_id=pending_hashtag_id,
    )


def _changes_nothing(entry: dict, held: dict | None) -> bool:
    """A kept part's entry that holds its id and its current amount alone."""
    if held is None or set(entry) - {"id", "amount_cents"}:
        return False
    return entry.get("amount_cents") == signed_cents(held)


class EditFormScreen(FormScreen):
    """The Edit form on the bank line of a ledger row, `record`: `⏎` and `s`.

    Dismisses with True once saved, so the ledger reads fresh; with None on
    `esc`."""

    BINDINGS = [
        *form_bindings("Save"),
        Binding("ctrl+n", "add_part", "Add part"),
        # the bar's own ctrl+x cuts text; on a part's line the drop comes first
        Binding("ctrl+x", "drop_part", "Drop part", priority=True),
    ]

    def __init__(
        self,
        *,
        record: dict,
        opener: Screen | None = None,
        reload: Callable[[], None] | None = None,
        shown: tuple[object, object] | None = None,
    ) -> None:
        """`opener` is the screen that opened the form and `reload` how it reads again
        after a save; a save that answers after the form was left calls `reload` if
        `opener` is the screen shown. `shown` is the (title, amount) the opener's list
        drew the line with, where that is not the record's own."""
        super().__init__()
        self._record = record
        self._opener, self._reload = opener, reload
        # the line as its list showed it, for a refusal shown after the form is left
        self._shown = shown or (record.get("title"), record.get("amount_cents"))
        self._picks: list = []
        # each account's currencies, in the order the engine lists them
        self._codes: dict[str, tuple[str, ...]] = {}
        self._categories: list = []
        self._hashtags: list = []
        self._acc_names: dict = {}
        self._pending_tag: str | None = None
        self._refs: QuickAddRefs | None = None
        self._line: dict | None = None
        self._parts: list[Part] = []
        # each part read from the line, as the engine holds it, by its id
        self._held: dict[str, dict] = {}
        self._limits: dict = {}
        # each read-only line field's sentence, as the engine sends it
        self._line_reasons: dict[str, str | None] = {}
        self._original: dict = {}
        self._refusal: Exception | None = None  # the engine's, until something changes
        self._saved = saved_words({})  # what the save's answer says
        self._pick_note: str | None = None  # a save stopped on the CURRENCY line with none picked

        self.crumb = ("Capture & ledger", "Transactions", "Edit")
        self._prefill(self._record)

    # ---- the line's own fields -------------------------------------------
    def _line_keys(self) -> list[str]:
        return ["date", "title", "account", "currency"]

    def _prefill(self, rec: dict) -> None:
        self._values = {}
        self._display = {}
        date = rec.get("day") or ""
        if date:
            self._values["date"] = self._display["date"] = date
        if rec.get("title"):
            self._values["title"] = self._display["title"] = rec["title"]
        if rec.get("account_id"):
            self._values["account"] = rec["account_id"]
            self._display["account"] = rec["account_id"][:8]  # resolved once entities load
        if rec.get("currency_code"):
            self._values["currency"] = self._display["currency"] = rec["currency_code"]
        if "operation" in self._line_keys() and rec.get("operation_code"):
            self._values["operation"] = self._display["operation"] = rec["operation_code"]
        # deep: the baseline never shares a value with `_values`
        self._original = copy.deepcopy(self._values)

    # ---- the line and its parts --------------------------------------------
    def _take_line(self, line: dict) -> None:
        """The line as the engine reads it: its parts in its order, each kept
        as held, its total and its `edit_limits`."""
        self._line = line
        items = [p for p in line.get("parts") or [] if isinstance(p, dict) and p.get("id")]
        self._held = {str(p["id"]): p for p in items}
        self._parts = [part_from_engine(p) for p in items]
        self._limits = line.get("edit_limits") or {}
        self._relock()

    def _take_refs(self, refs: QuickAddRefs) -> None:
        self._refs = refs
        accounts = refs.quickadd_accounts
        self._picks = [(account_id, name) for account_id, name, _codes in accounts]
        self._codes = {account_id: codes for account_id, _name, codes in accounts}
        self._categories = refs.pickable_categories
        self._hashtags = refs.hashtags
        self._acc_names = refs.account_names
        self._pending_tag = refs.pending_hashtag_id
        if "account" in self._values:
            self._display["account"] = resolve_name(self._values["account"], self._acc_names)

    @property
    def _ready(self) -> bool:
        """The line and the reference lists are in: the form takes input."""
        return self._line is not None and self._refs is not None

    @property
    def _total(self) -> int | None:
        return whole_number((self._line or {}).get("net_cents"))

    def _part_locks(self) -> dict[int, frozenset[str]]:
        """Each part's read-only fields (`FIELDS` words), by its place in the
        table: what `locked_part_fields` names for its id. With the total fixed
        and the parts not, an amount it names is the total held by a line of
        one part, so it holds only while the table has one part."""
        by_id = self._limits.get("locked_part_fields") or {}
        moving = (
            bool(self._limits.get("total_fixed"))
            and not self._limits.get("parts_fixed")
            and len(self._parts) > 1
        )
        out: dict[int, frozenset[str]] = {}
        for index, part in enumerate(self._parts):
            named = by_id.get(part.id) or {} if part.id else {}
            fields = {field for field, engine in ENGINE_FIELDS.items() if engine in named}
            if moving:
                fields.discard("amount")
            if fields:
                out[index] = frozenset(fields)
        return out

    def _part_reasons(self, locks: dict[int, frozenset[str]]) -> dict[int, dict[str, str | None]]:
        """Each part's read-only fields in `locks`, with the engine's sentence
        for each, as `locked_part_fields` sends it for the part's id."""
        by_id = self._limits.get("locked_part_fields") or {}
        out: dict[int, dict[str, str | None]] = {}
        for index, fields in locks.items():
            part_id = self._parts[index].id
            named = by_id.get(part_id) or {} if part_id else {}
            out[index] = {field: lock_message(named.get(ENGINE_FIELDS[field])) for field in fields}
        return out

    def _relock(self) -> None:
        """The read-only lines: each line field the line's `edit_limits` names, with the
        engine's sentence for it, each part field it names, and CURRENCY when the
        account holds one currency (dim, with its own reason, no sentence)."""
        keys = set(self._line_keys())
        named = self._limits.get("locked_fields") or {}
        self._line_reasons = {
            _FORM_KEY[field]: lock_message(entry)
            for field, entry in named.items()
            if _FORM_KEY.get(field) in keys
        }
        locked = set(self._line_reasons)
        if self._only_currency():
            locked.add("currency")
        for index, fields in self._part_locks().items():
            locked |= {part_key(index, field) for field in fields}
            self._parts[index] = self._as_read(self._parts[index], fields)
        self._locked = locked

    def _held_codes(self) -> tuple[str, ...]:
        """The currencies the line's account holds; none when the account is not in the
        pool (an archived one) or the reference lists are not in yet."""
        account = self._values.get("account")
        return self._codes.get(account, ()) if account is not None else ()

    def _only_currency(self) -> str | None:
        """The one currency the line's account holds, when it holds exactly one: the
        CURRENCY line then shows it dim and the bar skips it."""
        return only_currency(self._held_codes())

    def _dim_shown(self, key: str) -> bool:
        return key == "currency" and self._values.get("currency") is None

    def _locked_word(self, key: str) -> str:
        """`read-only` for what the engine locks; on CURRENCY of an account holding one
        currency, why it is skipped, and what the line held before a change of account."""
        if key != "currency" or key in self._line_reasons:
            return super()._locked_word(key)
        was = self._original.get("currency")
        if was and was != self._values.get("currency"):
            return f"· was {was} · not converted"
        return f"· {self._display.get('account', '')} holds only {self._only_currency()}"

    def _reason_lines(self) -> list[RenderableType]:
        """Under the shared fields, each sentence once, naming the read-only
        lines it covers in the form's order."""
        return reason_lines(
            [
                (self._summary_label(key), self._line_reasons[key])
                for key in self._line_keys()
                if key in self._line_reasons
            ]
        )

    def _as_read(self, part: Part, fields: frozenset[str]) -> Part:
        """`part` with each of its read-only `fields` back at the value read from
        the line, so a read-only cell shows and sends the line's own value: an
        amount edited while the table held two parts, then locked again by a
        drop, goes back to the one the line holds."""
        held = self._held.get(part.id) if part.id else None
        if held is None:
            return part
        read = part_from_engine(held)
        return replace(
            part, **{_PART_ATTR[field]: getattr(read, _PART_ATTR[field]) for field in fields}
        )

    @property
    def _parts_fixed(self) -> bool:
        return bool(self._limits.get("parts_fixed"))

    def _part_at(self, key: str) -> tuple[int, str, Part] | None:
        bits = split_key(key)
        if bits is None or bits[0] >= len(self._parts):
            return None
        return bits[0], bits[1], self._parts[bits[0]]

    def _set_part(self, index: int, part: Part) -> None:
        if part != self._parts[index]:
            self._parts[index] = part
            self._refusal = None  # something changed

    def _set_value(self, key: str, value: object, display: object = None) -> None:
        if value != self._values.get(key):
            self._refusal = None  # something changed
            self._pick_note = None
        if value is None:
            self._values[key] = None
            self._display.pop(key, None)
        else:
            self._values[key] = value
            self._display[key] = value if display is None else display

    # ---- field sequence --------------------------------------------------
    def _sequence(self) -> list[str]:
        return [
            *self._line_keys(),
            *(part_key(i, field) for i in range(len(self._parts)) for field in FIELDS),
        ]

    def _after_mount(self) -> None:
        self._load_entities()

    @work(thread=True, exclusive=True)
    def _load_entities(self) -> None:
        """The reference lists, then, when the form does not hold the line yet,
        the row's line in one `GET /bank-lines/{id}`
        (contract: GET /v1/bank-lines/{bank_line_id}). A failed read says why
        and leaves the form taking no input."""
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            kw = screen_fetch_kwargs(self.app)
            # the fetch + shaping is shared with the LOG bar
            refs = load_quickadd_refs(cfg, **kw)
            line = self._line
            if line is None:
                line = reads.fetch_bank_line(cfg, str(self._record["bank_line_id"]), **kw)
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            call_while_attached(self, toast, self, format_error(exc), severity="error")
            return
        call_while_attached(self, self._loaded, refs, line)

    def _loaded(self, refs: QuickAddRefs, line: dict) -> None:
        self._take_refs(refs)
        if self._line is not line:
            self._take_line(line)
        self._relock()  # the account's currencies are known now
        if self._key in self._locked:
            self._current = self._first_editable()
        self._refresh_bar()
        self._refresh_view()

    # ---- FormScreen hooks --------------------------------------------------
    def _label(self, key: str) -> str:
        bits = split_key(key)
        if bits is None:
            return _LABELS[key]
        return f"PART {bits[0] + 1} {_LABELS[bits[1]]}"

    def _hint_for(self, key: str) -> str:
        bits = split_key(key)
        field = bits[1] if bits else key
        if field == "note":
            return NOTE_GOES_ON if self._goes_on(key) else NOTE_SAVES
        if key == "title" and not self._goes_on(key):
            return TITLE_SAVES
        if key == "currency":
            name = self._display.get("account", "")
            return f"pick a currency {name} holds · ↑↓ highlight · enter select"
        return _HINTS.get(field, "")

    def _hint_line(self, key: str) -> Text:
        if not (len(self._parts) > 1 and key in _EVERY_PART):
            return super()._hint_line(key)
        return Text.assemble((f"{self._hint_for(key)} · ", "dim"), (EVERY_PART_NOTE, ACCENT))

    def _suggests(self, key: str) -> bool:
        bits = split_key(key)
        return key in ("account", "currency") or (
            bits is not None and bits[1] in ("category", "hashtags")
        )

    def _bar_value(self, key: str) -> str:
        at = self._part_at(key)
        if at is not None:
            _index, field, part = at
            if field == "amount" and part.amount_cents is not None:
                return amount_to_text(part.amount_cents)
            if field == "note":
                return part.note or ""
            return ""  # entity fields open empty; `_recompute` places the highlight
        if key in ("date", "title", "operation"):
            return str(self._values.get(key, "") or "")
        return ""

    def _refresh_bar(self) -> None:
        super()._refresh_bar()
        self.refresh_bindings()  # `^x` follows the bar onto and off a part's line

    # ---- suggestions -----------------------------------------------------
    def _recompute_suggestions(self, text: str) -> None:
        # historic name kept — test drivers (and muscle memory) call it directly
        self._recompute(text)

    def _recompute(self, text: str) -> None:
        key = self._key
        needle = text.strip()
        at = self._part_at(key)
        own: object = None
        if key == "account":
            pool = matching(self._picks, needle)
            own = self._values.get("account")
        elif key == "currency":
            pool = matching([(code, code) for code in self._held_codes()], needle)
            own = self._values.get("currency")
        elif at is not None and at[1] == "category":
            pool = matching(self._categories, needle)
            own = at[2].category_id
        elif at is not None and at[1] == "hashtags":
            pool = matching(self._hashtags, needle.lstrip("#"), chosen=set(at[2].hashtag_ids))
        else:
            pool = []
        self._suggestions = pool
        self._suggest_idx = 0
        if own is not None and not needle:
            # an empty bar starts on what the line or the part holds, so `⏎` keeps it
            ids = [ent[0] for ent in pool]
            if own in ids:
                self._suggest_idx = ids.index(own)

    def _picked(self):
        return self._suggestions[self._suggest_idx] if self._suggestions else None

    def _suggest_renderable(self) -> RenderableType:
        if not self._suggests(self._key):
            return Text("")
        labels = [f"{ent[1]}{'  ' + ent[2] if len(ent) > 2 else ''}" for ent in self._suggestions]
        return suggestion_list(labels, self._suggest_idx)

    # ---- commit ----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """`⏎`: keep what the bar holds and move on; on a part's HASHTAGS a
        typed name adds the hashtag and stays for another, and `⏎` with
        nothing typed moves on."""
        if not self._ready:
            return  # nothing to keep until the line is in
        bar = self.query_one("#bar", Input)
        text = bar.value.strip()
        at = self._part_at(self._key)
        if at is not None and at[1] == "hashtags" and text:
            if self._keep(text):
                bar.value = ""
                self._recompute("")
                self._refresh_view()
            return
        if at is not None and at[1] == "hashtags":
            self._advance()
        elif not self._keep(text):
            return
        else:
            self._advance()
        self._refresh_view()

    def _keep(self, text: str) -> bool:
        """Keep `text`, the bar's, on the line the bar is on. False, with a
        note saying why, when it cannot be kept; the bar then stays."""
        key = self._key
        at = self._part_at(key)
        if at is not None:
            return self._keep_part(*at, text)
        if key == "date":
            # read by the save's own reader, so ⏎ takes what `ctrl+s` can send
            if text and not is_readable_date(text):
                toast(self, DATE_UNREADABLE, severity="error")
                return False
            self._set_value("date", text or date_cls.today().isoformat())
        elif key == "title":
            if not self._title_given(text):
                return False
            self._set_value("title", text)
        elif key == "operation":
            self._set_value("operation", text or None)
        elif key == "account":
            picked = self._picked()
            if picked is None:
                toast(self, f"No account matches “{text}”.", severity="error")
                return False
            before = self._values.get("account")
            self._set_value("account", picked[0], picked[1])  # (account_id, name)
            if picked[0] != before:
                self._account_changed()
        elif key == "currency":
            picked = self._picked()
            if picked is None:
                toast(self, f"No currency matches “{text}”.", severity="error")
                return False
            self._set_value("currency", picked[0])
        return True

    def _account_changed(self) -> None:
        """The line's account is another: its currency follows the account. One held
        is shown, never sent (`_line_fields`: the engine moves the line to it); several
        empty it, and the bar goes on to CURRENCY to pick one. The summary and the lock
        follow."""
        codes = self._held_codes()
        if (only := only_currency(codes)) is not None:
            self._set_value("currency", only)
        elif codes:
            self._set_value("currency", None)
            self._display["currency"] = NONE_PICKED
        self._relock()

    def _keep_part(self, index: int, field: str, part: Part, text: str) -> bool:
        if field == "amount":
            cents = parse_amount(text, current_format())
            if cents is None:
                toast(self, f"can't read this amount: {amounts_are()}", severity="error")
                return False
            # Mid-form ergonomics guard; mirrors the engine's 422 on a zero
            # amount (contract: PUT /v1/bank-lines/{bank_line_id}, "The parts' rules").
            if cents == 0:
                self.notify("Amount must be non-zero.", severity="error")
                return False
            self._set_part(index, replace(part, amount_cents=cents))
        elif field in ("category", "hashtags"):
            picked = self._picked()
            if picked is None:
                name = "category" if field == "category" else "hashtag"
                toast(self, f"No {name} matches “{text}”.", severity="error")
                return False
            if field == "category":
                self._set_part(index, replace(part, category_id=picked[0]))
            else:
                # what the form lists is what the save sends: once a real
                # hashtag is in, the pending one leaves the part
                tags = hashtags_to_send([*part.hashtag_ids, picked[0]], self._pending_tag)
                self._set_part(index, replace(part, hashtag_ids=tuple(tags)))
        else:
            # an emptied bar empties the note; the save sends it as `""`
            self._set_part(index, replace(part, note=text or None))
        return True

    def _keep_typed(self) -> bool:
        """Before a save: keep what is typed in the bar, when it is not what the
        line under it already shows. False when it cannot be kept."""
        key = self._key
        bar = self.query_one("#bar", Input)
        if key in self._locked or bar.value == self._bar_value(key):
            return True
        if not self._keep(bar.value.strip()):
            return False
        at = self._part_at(key)
        if at is not None and at[1] == "hashtags":  # added: the bar empties for another
            bar.value = ""
            self._recompute("")
        return True

    # ---- adding and dropping parts -------------------------------------------
    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """`^n` only where the line's parts may change; `^x` too, and only on
        a part's line while there are two parts or more."""
        if action == "add_part":
            return self._ready and not self._parts_fixed
        if action == "drop_part":
            return (
                self._ready
                and not self._parts_fixed
                and self._part_at(self._key) is not None
                and len(self._parts) > 1
            )
        return True

    @property
    def active_bindings(self):
        """Textual's, with `^x` last, as the footer reads it: the bar's own
        `ctrl+x` (cut) comes first in the chain, and the priority binding that
        replaces it would take its place at the head of the footer."""
        bindings = super().active_bindings
        drop = bindings.pop("ctrl+x", None)
        if drop is not None:
            bindings["ctrl+x"] = drop
        return bindings

    def action_add_part(self) -> None:
        """`ctrl+n`: an empty part at the end, the bar on its AMOUNT."""
        if self._submitting or not self.check_action("add_part", ()):
            return
        self._parts.append(Part())
        self._refusal = None  # something changed
        self._relock()
        self._current = self._sequence().index(part_key(len(self._parts) - 1, "amount"))
        self._refresh_bar()
        self._refresh_view()

    def action_drop_part(self) -> None:
        """`ctrl+x`: drop the part the bar is on, at once; the bar moves to the
        same line on the part above (part 1's when the first is dropped)."""
        at = self._part_at(self._key)
        if self._submitting or at is None or not self.check_action("drop_part", ()):
            return
        index, field, _part = at
        del self._parts[index]
        self._refusal = None  # something changed
        self._relock()
        self._current = self._sequence().index(part_key(max(index - 1, 0), field))
        if self._key in self._locked:
            ahead = self._step(1)
            self._current = ahead if ahead != self._current else self._step(-1)
        self._refresh_bar()
        self._refresh_view()

    # ---- render ----------------------------------------------------------
    def _summary_renderable(self) -> RenderableType:
        table = self._summary_table(self._line_keys())
        reasons = self._reason_lines()
        refs = self._refs
        if not self._ready or refs is None:
            return Group(table, *reasons, Text(""), Text(LOADING_HINT, style="dim"))
        at = self._part_at(self._key)
        locks = self._part_locks()
        blocks: list[RenderableType] = [
            table,
            *reasons,
            Text(""),
            *parts_lines(
                self._parts,
                refs,
                editing=at[0] if at is not None else None,
                locked=locks,
                flagged=flagged_parts(self._refusal),
                palette=PALETTE,
            ),
            *readonly_lines(self._part_reasons(locks)),
        ]
        if len(self._parts) > 1:
            blocks += [Text(""), count_line(self._parts, self._total, palette=PALETTE)]
        if self._refusal is not None:
            blocks += [Text(""), *refusal_lines(self._refusal, palette=PALETTE)]
        if self._pick_note is not None:
            blocks += [
                Text(""),
                hanging(Text(self._pick_note, style=PALETTE.error)),
                Text(NOTHING_SAVED, style="dim"),
            ]
        return Group(*blocks)

    # ---- submit ----------------------------------------------------------
    def _line_fields(self) -> dict:
        """The line fields the owner changed, under their names in the write;
        a read-only one is never sent."""
        fields: dict = {}
        for key in self._line_keys():
            if key in self._line_reasons or self._values.get(key) == self._original.get(key):
                continue
            if key == "currency" and self._only_currency():
                continue  # the engine fills an account's only currency
            new = self._values.get(key)
            if key == "date":
                # never empty: an empty date bar commits today
                assert new is not None  # a line always carries its date
                fields["date"] = to_canonical_aware(new)
            elif key == "operation":
                # `null` clears the line's operation code
                # (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")
                fields["operation_code"] = new or None
            else:
                # only the key that moved: either account or currency alone keeps the other
                # as the line has it (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")
                fields[_ENGINE_FIELD[key]] = new
        return fields

    def _statement_id(self) -> str | None:
        """The statement the line is in, read from its parts (a line is in one whole)."""
        parts = (self._line or {}).get("parts") or []
        return next((p["statement_id"] for p in parts if p.get("statement_id")), None)

    def _currency_unpicked(self) -> bool:
        """The account holds several currencies and none is picked."""
        return (
            "currency" not in self._locked
            and self._values.get("currency") is None
            and bool(self._held_codes())
        )

    def _stop_on_currency(self) -> None:
        """A save with no currency picked sends nothing: the bar goes to CURRENCY and the
        note says what to pick from."""
        name = self._display.get("account", "")
        self._pick_note = f"! currency: pick one — {name} holds {codes_and(self._held_codes())}."
        self._current = self._sequence().index("currency")
        self._refresh_bar()
        self._refresh_view()

    def _submit_request(self) -> tuple[str, str, dict, str] | None:
        """The one `PUT /bank-lines/{id}`: the changed line fields and the
        line's whole set of parts, a part added and left empty left out. None,
        with `No changes to save.`, when it would change nothing."""
        line = self._line
        if line is None:
            return None
        if self._currency_unpicked():
            self._stop_on_currency()
            return None
        pending = self._pending_tag
        parts = [p for p in self._parts if not part_empty(p, pending)]
        entries = [part_payload(p, self._held.get(p.id) if p.id else None, pending) for p in parts]
        fields = self._line_fields()
        unassign_on_move(
            fields, {**line, "statement_id": self._statement_id()}, keep_on_currency_move=True
        )
        kept_ids = {p.id for p in parts if p.id}
        unchanged = set(self._held) == kept_ids and all(
            _changes_nothing(entry, self._held.get(str(entry["id"]))) for entry in entries
        )
        if not fields and unchanged:
            self.notify("No changes to save.")
            return None
        return ("PUT", f"/bank-lines/{line['id']}", line_body(entries, fields), "Saving…")

    def action_submit(self) -> None:
        """`ctrl+s`: keep what is typed in the bar first, then the one write."""
        if self._submitting or not self._ready or not self._keep_typed():
            return
        request = self._submit_request()
        if request is None:
            return
        method, path, payload, busy = request
        self._submitting = True
        self._refusal = None
        self.query_one("#hint", Static).update(Text(busy, style="dim"))
        self._refresh_view()
        self.run_write(
            method,
            path,
            json_body=payload,
            on_success=self._done,
            on_failure=self._refused,
            on_response=self._answered,
            error_text=refusal_text,
            left_behind=LeftBehind(not_saved_line(*self._shown), open_it_again, saved_words),
        )

    def _write_finished_after_leaving(self, app, item, error, *answer) -> None:
        """A save that answered once the form was gone: the app says how it ended
        (`EngineWriteMixin`), and the screen that opened the form, if it is the one
        shown, reads again as after a save."""
        super()._write_finished_after_leaving(app, item, error, *answer)
        if error is None and self._reload is not None and app.screen is self._opener:
            self._reload()

    def _answered(self, body: dict) -> None:
        # the note reads the engine's answer, never the line as read before the save
        self._saved = saved_words(body)

    def _refused(self, err: Exception) -> None:
        """The refusal stays under the parts, the form open as it was."""
        self._submitting = False
        self._refusal = err
        self._refresh_view()

    def _done(self) -> None:
        toast(self, self._saved)  # a fixed sentence, chosen from the answer by `saved_words`
        self.dismiss(True)  # a cancel dismisses with None: the caller reloads only on True


# ---- the Edit form on a line of "no statement": `⏎` there ---------------------
class BankLineEditFormScreen(EditFormScreen):
    """The Edit form on a line the "no statement" list holds: the same form,
    with OPERATION among the shared fields and, over the bar, the line as the
    list shows it, its title and its `net_cents` with the line's own currency.

    Every value comes from the line the list holds, its `edit_limits`
    included, so the form reads no line: the day and title off its first part,
    its `operation_code`, `account_id` and `currency_code`."""

    def __init__(
        self,
        *,
        line: dict,
        opener: Screen | None = None,
        reload: Callable[[], None] | None = None,
    ) -> None:
        first = (line.get("parts") or [{}])[0]
        record = {
            **first,
            "bank_line_id": line.get("id"),
            "account_id": line.get("account_id") or first.get("account_id"),
            "currency_code": line.get("currency_code") or first.get("currency_code"),
            "operation_code": line.get("operation_code"),
        }
        super().__init__(record=record, opener=opener, reload=reload)
        self.crumb = ("Capture & ledger", "Statements", "Edit")
        self._take_line(line)
        _day, title, _operation, net_cents = bank_line_columns(line)
        self._shown = (title, net_cents)

    def _line_keys(self) -> list[str]:
        return ["date", "title", "operation", "account", "currency"]

    def _heading(self) -> RenderableType:
        line = self._line or {}
        _day, title, _operation, net_cents = bank_line_columns(line)
        head = Text(title_or_untitled(title), style="bold")
        head.append("  ·  ", style="dim")
        head.append_text(amount_text(net_cents, PALETTE, TRANSACTION_RULE))
        if line.get("currency_code"):
            head.append(f" {line['currency_code']}", style="dim")
        return head
