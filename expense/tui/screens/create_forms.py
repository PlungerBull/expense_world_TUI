"""Create forms — new hashtag / category / account.

A lightweight bar-cycle form (same look as Log): cycle fields with the input
bar, pick choices from a suggestion list, `ctrl+s` (or enter with no field
ahead that can change) POSTs. Reached with `n` on the Manage list screens.

New account covers both kinds: its first field is TYPE (`bank` / `person`,
prefilled `bank`), and both save with `POST /accounts`; a `person` adds
`is_person: true` to the body (contract: POST /v1/accounts, "Optional"). Editing
cannot change it, so TYPE is locked read-only on the edit form. Its CURRENCIES
line picks one currency or more, as the Edit form's HASHTAGS line picks
hashtags.
"""

import dataclasses
import uuid

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.widgets import Input, Static

from expense import reads
from expense.dates import is_calendar_day, to_canonical_aware
from expense.errors import EngineError, format_error, key_index, next_step
from expense.formatting import format_cents
from expense.number_format import amounts_sentence, current_format
from expense.quickadd.money import amount_to_text, parse_amount
from expense.tui.screens._base import (
    LeftBehind,
    ReportedPart,
    ResourceListScreen,
    SaveReport,
    call_while_attached,
    not_done_line,
    screen_fetch_kwargs,
)
from expense.tui.screens._form import FormScreen, form_bindings, may_have_landed, open_it_again
from expense.tui.screens.modals import ConfirmModal
from expense.tui.theme import AMOUNT_RULE, PALETTE
from expense.tui.widgets.cells import amount_text
from expense.tui.widgets.picker import matching, suggestion_list
from expense.tui.widgets.refusal import toast

_PALETTE = [
    ("#4a90d9", "blue"),
    ("#5ab87a", "green"),
    ("#d96a5a", "red"),
    ("#b07cd9", "purple"),
    ("#d9a93a", "amber"),
    ("#5ab8a0", "teal"),
    ("#d9744a", "orange"),
    ("#8a8f98", "grey"),
]
#: The account's CURRENCIES on New: the hashtag line's picking, a code in place
#: of a tag.
CURRENCIES_HINT = "type a code · ↑↓ highlight · enter adds & stays · empty enter = done"
#: NAME's hint on Manage ▸ Accounts and Categories, New and Edit: `⏎` there goes
#: on to the next line, never saves.
NAME_HINT = "free text · enter to go on"
#: The account's COLOR, New and Edit: `⏎` keeps what the line holds — the
#: account's own colour on Edit, no colour on New.
ACCOUNT_COLOR_HINT = "optional · enter keeps it · ↑↓ another swatch"
#: The account's STATEMENT CODE on New: optional, and `⏎` goes on to COLOR.
STATEMENT_CODE_HINT = "optional · three capital letters, e.g. SIG · enter to go on"
#: The same line on Edit, where emptying it and saving clears the code.
STATEMENT_CODE_EDIT_HINT = (
    "optional · three capital letters, e.g. SIG · empty clears it · enter to go on"
)
#: A new category's COLOR, its last line: `⏎` there creates the category.
CATEGORY_COLOR_HINT = "optional · enter to save · ↑↓ another swatch"
# Bank first: it is the prefilled default, so `enter` on an untouched TYPE field
# keeps `bank` and adding an ordinary account still costs one keypress.
_ACCOUNT_TYPES = [("bank", "bank"), ("person", "person")]
#: The engine field a refusal names → the account form line it lands on, New or
#: Edit; a line the form does not have is passed over.
_REFUSED_LINES = {
    "name": "name",
    "color": "color",
    "currencies": "currencies",
    "amount_cents": "opening",
    "date": "as_of",
    "statement_code": "statement_code",
}


def _form_line_named(key: object) -> str | None:
    """The account form line a refusal's key names: `_REFUSED_LINES`', and
    CURRENCIES for any `currencies.<i>…` key."""
    if key_index(key, "currencies") is not None:
        return "currencies"
    return _REFUSED_LINES.get(str(key))


class Field:
    def __init__(self, key, label, kind="text", *, choices=None, required=False, hint=""):
        self.key = key
        self.label = label
        # "text" | "choice" | "color" | "picks" (one or more of `choices`, the
        # value a list of their values in the order picked)
        self.kind = kind
        self.choices = choices or []
        self.required = required
        self.hint = hint


class BarFormScreen(FormScreen):
    FIELDS: list = []
    NOUN = "item"
    NOT_DONE = "Not created"  # the first line of a refusal shown after the form was left

    # ---- FormScreen hooks (Field-driven) ----------------------------------
    def _sequence(self) -> list[str]:
        return [f.key for f in self.FIELDS]

    def _field(self, key: str) -> Field:
        return next(f for f in self.FIELDS if f.key == key)

    @property
    def _f(self) -> Field:
        return self._field(self._key)

    def _label(self, key: str) -> str:
        return self._field(key).label

    def _hint_for(self, key: str) -> str:
        return self._field(key).hint

    def _required(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.FIELDS if self._field_required(f))

    def _field_required(self, f: Field) -> bool:
        """Whether `f` is needed now — a form whose fields depend on each other
        overrides this (the account Edit form's AS OF, once there is an amount)."""
        return f.required

    def _value_text(self, key: str, value: object) -> str:
        """How a text field's value reads in the summary."""
        return str(value)

    def _value_cell(self, key: str, value: object) -> Text:
        """A text field's value as the summary draws it; `_value_text` unstyled."""
        return Text(self._value_text(key, value))

    def _suggests(self, key: str) -> bool:
        return self._field(key).kind in ("choice", "color", "picks")

    def _bar_value(self, key: str) -> str:
        f = self._field(key)
        return str(self._values.get(key, "")) if f.kind == "text" else ""

    def _recompute(self, text: str) -> None:
        f = self._f
        needle = text.strip()
        if f.kind == "picks":
            # the hashtag line's pool: what is left to pick, the first highlighted
            self._suggestions = matching(f.choices, needle, chosen=self._values.get(f.key, ()))
            self._suggest_idx = 0
            return
        if f.kind in ("choice", "color"):
            self._suggestions = matching(f.choices, needle, by_id=True)
        else:
            self._suggestions = []
        if needle:
            self._suggest_idx = 0
        elif f.kind == "color" and f.key in self._values:
            # A colour line starts on the colour it holds (on an Edit screen, the
            # row's own), so `enter` keeps it; a colour no swatch shows highlights
            # nothing, and `enter` keeps that too.
            held = self._values[f.key]
            self._suggest_idx = next(
                (i for i, (v, _) in enumerate(self._suggestions) if v == held), -1
            )
        else:
            # An optional line left empty highlights nothing: its `enter` skips, so
            # no swatch may look picked. Typing, or `↑`/`↓` into the list, highlights.
            self._suggest_idx = 0 if self._field_required(f) else -1

    # ---- commit ----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        f = self._f
        text = self.query_one("#bar", Input).value.strip()
        if f.kind == "text":
            if not text:
                if f.required:
                    toast(self, f"{f.label.title()} is required.", severity="error")
                    return
                self._values.pop(f.key, None)
            else:
                self._values[f.key] = text
            self._advance()
            return
        if f.kind == "picks":
            self._pick(f, text)
            return
        # choice / color
        if self._suggest_idx < 0:  # empty, nothing highlighted: keep what the line holds
            self._advance()
            return
        picked = self._suggestions[self._suggest_idx] if self._suggestions else None
        if picked is None:
            toast(self, f"Pick a {f.label.lower()}.", severity="error")
            return
        self._values[f.key] = picked[0]
        self._advance()

    def _pick(self, f: Field, text: str) -> None:
        """`⏎` on a picks line, as on the Edit form's HASHTAGS: a typed name adds
        the highlighted choice and the bar empties for another; `⏎` with nothing
        typed goes on."""
        if not text:
            self._advance()
            return
        self._add_pick(f, text)

    def _add_pick(self, f: Field, text: str) -> bool:
        """Add the highlighted choice for the typed `text` and empty the bar for
        another; False, with the refusal toast, when `text` matches none."""
        picked = self._suggestions[self._suggest_idx] if self._suggestions else None
        if picked is None:
            toast(self, f"No {f.label.lower()} match “{text}”.", severity="error")
            return False
        self._values[f.key] = [*self._values.get(f.key, ()), picked[0]]
        self.query_one("#bar", Input).value = ""
        self._recompute("")
        self._refresh_view()
        return True

    def action_submit(self) -> None:
        """`ctrl+s` keeps a name typed on a picks line but not yet added, as `⏎`
        adds it (the Edit form's HASHTAGS line does the same); one matching
        nothing is refused as `⏎` refuses it, and nothing is sent."""
        if self._submitting:
            return
        f = self._f
        text = self.query_one("#bar", Input).value.strip()
        if f.kind == "picks" and text and self._key not in self._locked:
            if not self._add_pick(f, text):
                return
        super().action_submit()

    # ---- render ----------------------------------------------------------
    def _suggest_renderable(self) -> RenderableType:
        f = self._f
        if f.kind == "picks":
            if not self._suggestions and len(self._values.get(f.key, ())) == len(f.choices):
                return Text("")  # every choice picked: nothing left to list
            return suggestion_list([ent[1] for ent in self._suggestions], self._suggest_idx)
        if f.kind not in ("choice", "color"):
            return Text("")
        if not self._suggestions:
            return Text("  no match", style="dim")
        rows = []
        for i, (value, display) in enumerate(self._suggestions):
            if f.kind == "color":
                line = Text.assemble(("  ", ""), ("██ ", value), (display, ""))
            else:
                line = Text(f"  {display}")
            if i == self._suggest_idx:
                line.stylize("reverse")
            rows.append(line)
        return Group(*rows)

    def _summary_renderable(self) -> RenderableType:
        t = Table(box=None, pad_edge=False, show_header=False)
        t.add_column("k")
        t.add_column("v")
        for f in (self._field(key) for key in self._sequence()):
            locked = f.key in self._locked
            if f.key in self._values:
                if f.kind == "color":
                    hex_ = self._values[f.key]
                    value = Text.assemble(("██ ", hex_), (self._color_name(hex_), ""))
                elif f.kind == "picks":
                    value = Text(" · ".join(self._values[f.key]) or "—")
                else:
                    value = self._value_cell(f.key, self._values[f.key])
            else:
                tag = "  *" if self._field_required(f) else "  (optional)"
                value = Text("—" + tag, style="dim")
            if locked:  # edit forms lock immutable fields (e.g. account currency)
                value.append("  read-only", style="dim")
            label = Text(self._summary_label(f.key), style="dim" if locked else "")
            if f.key == self._key and not locked:
                label.stylize("bold")
            t.add_row(label, value)
        return t

    @staticmethod
    def _color_name(hex_: str) -> str:
        return next((d for (v, d) in _PALETTE if v == hex_), hex_)

    # ---- submit ----------------------------------------------------------
    def _payload(self) -> dict:
        raise NotImplementedError

    def _saved_words(self) -> str:
        return f"{self.NOUN.title()} created."

    def _done(self) -> None:
        toast(self, self._saved_words())
        self.dismiss()

    def _shown_name(self) -> str:
        """The name `_left_behind` finds the thing by: as typed on New, as its list
        showed it before the edit on Edit."""
        return self._values["name"]

    def _kind(self) -> str:
        return self.NOUN.title()

    def _left_behind(self) -> str | None:
        return not_done_line(self.NOT_DONE, self._kind(), self._shown_name())

    def _landed_after_leaving(self, item, error, failure) -> bool:
        """Whether the answer just shown is the one after which the list reads again: the
        save landed, or its ending is not known (`may_have_landed`)."""
        return error is None or may_have_landed(failure)

    def _write_finished_after_leaving(self, app, item, error, body=None, failure=None) -> None:
        """A save that ended once the form was gone: the app says how it ended
        (`EngineWriteMixin`), and if it landed or its ending is not known and the
        screen now showing is this form's list, it reads again from its first page."""
        super()._write_finished_after_leaving(app, item, error, body, failure)
        shown = app.screen
        if self._landed_after_leaving(item, error, failure) and isinstance(
            shown, ResourceListScreen
        ):
            if shown.RESOURCE == self.RESOURCE:
                shown.start_over()


class NewHashtagScreen(BarFormScreen):
    crumb = ("Manage", "Hashtags", "New")
    RESOURCE = "hashtags"
    NOUN = "hashtag"
    FIELDS = [Field("name", "NAME", required=True, hint="lowercase, no “#” · enter creates")]

    def _payload(self) -> dict:
        return {"id": str(uuid.uuid4()), "name": self._values["name"].lstrip("#")}

    def _shown_name(self) -> str:
        return "#" + self._values["name"].lstrip("#")


class NewCategoryScreen(BarFormScreen):
    crumb = ("Manage", "Categories", "New")
    RESOURCE = "categories"
    NOUN = "category"
    # Colour is optional: a skipped colour is left out of the body, never sent as
    # null, and the engine gives its default (contract: POST /v1/categories).
    FIELDS = [
        Field("name", "NAME", required=True, hint=NAME_HINT),
        Field("color", "COLOR", "color", choices=_PALETTE, hint=CATEGORY_COLOR_HINT),
    ]

    def _payload(self) -> dict:
        payload = {"id": str(uuid.uuid4()), "name": self._values["name"]}
        if self._values.get("color"):
            payload["color"] = self._values["color"]
        return payload


class NewAccountScreen(BarFormScreen):
    """New bank account *or* person — one form, one key, a TYPE field on top.

    A person is a bank account with `is_person = true`, and the two take exactly
    the same fields; the only difference is `is_person: true` in the body. So the
    choice is a field (Why: docs/decisions.md "A settled person is folded, never
    hidden"), **prefilled to `bank`** — `n`, `enter`, name… still adds an
    ordinary account without an extra decision.

    CURRENCIES takes one currency or more, picked as the Edit form's HASHTAGS
    picks hashtags: a typed code and `⏎` add the highlighted one and stay for
    another, an empty `⏎` goes on. They go in as `currencies`, one
    `{currency_code}` each, in the order picked: the account and every currency
    in one write (contract: POST /v1/accounts, "Required").

    A bank account has one more line, STATEMENT CODE, after CURRENCIES: only a
    real account carries a code here, and a person's form has no such line
    (contract: "What an account is", "Statement code"). With TYPE on person the line
    leaves the form; back on bank it returns holding what was typed. Letters
    typed there show as capitals; the engine judges the shape. Skipped, the
    key is left out of the body (contract: POST /v1/accounts).

    A refusal that names one of the form's lines (`_REFUSED_LINES`; any
    `currencies.<i>…` key names CURRENCIES) reads in the engine's words and puts
    the cursor back on that line, with what was typed.
    """

    crumb = ("Manage", "Accounts", "New")
    RESOURCE = "accounts"
    NOUN = "account"
    FIELDS = [
        Field(
            "type",
            "TYPE",
            "choice",
            choices=_ACCOUNT_TYPES,
            required=True,
            hint="bank or person · enter keeps bank",
        ),
        Field("name", "NAME", required=True, hint=NAME_HINT),
        Field(
            "currencies",
            "CURRENCIES",
            "picks",
            required=True,
            hint=CURRENCIES_HINT,
        ),
        Field("statement_code", "STATEMENT CODE", hint=STATEMENT_CODE_HINT),
        Field("color", "COLOR", "color", choices=_PALETTE, hint=ACCOUNT_COLOR_HINT),
    ]

    def __init__(self, currencies: list[str]) -> None:
        """`currencies`: the engine's codes (`GET /currencies`), read by the list this
        form opens from, in the engine's order: what CURRENCIES offers."""
        super().__init__()
        self.FIELDS = [
            _field_with_choices(f, [(code, code) for code in currencies])
            if f.key == "currencies"
            else f
            for f in self.FIELDS
        ]
        self._values["type"] = "bank"
        self._refusal_says_next = False  # the last refusal carried its own next step

    @property
    def _is_person(self) -> bool:
        return self._values.get("type") == "person"

    def _sequence(self) -> list[str]:
        keys = super()._sequence()
        return [k for k in keys if k != "statement_code"] if self._is_person else keys

    def _typed(self, key: str, text: str) -> str:
        return text.upper() if key == "statement_code" else text

    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("POST", f"/{self.RESOURCE}", self._payload(), "Creating…")

    def _saved_words(self) -> str:
        return "Person created." if self._is_person else "Account created."

    def _kind(self) -> str:
        return "Person" if self._is_person else "Account"

    def _done(self) -> None:
        toast(self, self._saved_words())
        self.dismiss()

    def _payload(self) -> dict:
        payload = {
            "id": str(uuid.uuid4()),
            "name": self._values["name"],
            "currencies": [{"currency_code": code} for code in self._values["currencies"]],
        }
        if self._is_person:
            payload["is_person"] = True
        if self._values.get("color"):
            payload["color"] = self._values["color"]
        if not self._is_person and self._values.get("statement_code"):
            payload["statement_code"] = self._values["statement_code"]
        return payload

    def _line_named(self, field: object, currency: str | None) -> str | None:
        """The form line a refusal's `field` names (`_form_line_named`);
        `currency` is the currency whose write was refused, None for the
        account's own."""
        return _form_line_named(field)

    def _refusal_text(self, exc: Exception, currency: str | None = None) -> str:
        """The `error_text` of this form's writes: notes the form line the
        refusal names, for the failure callback to land on, then reads as every
        failed write does."""
        self._refused_line = None
        self._refusal_says_next = next_step(exc) is not None
        if isinstance(exc, EngineError):
            for field in [*(exc.reasons or {}), *(exc.fields or {})]:
                line = self._line_named(field, currency)
                if line in self._sequence() and line not in self._locked:
                    self._refused_line = line
                    break
        return format_error(exc)


def _set_again(refused: list[tuple[str, Exception | None]]) -> str | None:
    """The last line of a save's refusal message: what to set again, in the order sent.
    Only the parts refused clearly (`open_it_again`) are named, since any other may have
    landed; None when there are none."""
    clear = [name for name, failure in refused if open_it_again(failure) is not None]
    if not clear:
        return None
    names = f"{', '.join(clear[:-1])} and {clear[-1]}" if len(clear) > 1 else clear[0]
    return f"Open the account's Edit form to set {names} again."


def _edit_payload(values: dict, original_color: str | None) -> dict:
    """A Manage Edit form's body: the name, and the colour only when it is not
    the row's own, so a colour no swatch shows is never sent back."""
    payload = {"name": values["name"]}
    if values.get("color") and values["color"] != original_color:
        payload["color"] = values["color"]
    return payload


# --------------------------------------------------------------------------- #
# Edit forms — same bar-form, prefilled, PUT instead of POST. Reached with `e`
# on a Manage list row (ResourceListScreen). The account Edit form shows the
# currencies the account holds as a read-only summary row.
# Each declares `BINDINGS = form_bindings("Save")`: the footer names what
# `ctrl+s` does here, not the parent's `Create`.
# --------------------------------------------------------------------------- #
def _field_with_hint(f: Field, hint: str) -> Field:
    """`f` with another hint, its other parts the same."""
    return Field(f.key, f.label, f.kind, choices=f.choices, required=f.required, hint=hint)


def _field_with_choices(f: Field, choices: list) -> Field:
    """`f` with other choices, its other parts the same."""
    return Field(f.key, f.label, f.kind, choices=choices, required=f.required, hint=f.hint)


class EditHashtagScreen(NewHashtagScreen):
    BINDINGS = form_bindings("Save")
    NOT_DONE = "Not saved"

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._id = record["id"]
        self._was = record.get("name") or ""  # as the list shows it
        self._values = {"name": (record.get("name") or "").lstrip("#")}
        self.crumb = ("Manage", "Hashtags", record.get("name") or "—", "Edit")

    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("PUT", f"/hashtags/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        return {"name": self._values["name"].lstrip("#")}

    def _shown_name(self) -> str:
        return "#" + self._was.lstrip("#") if self._was else ""

    def _saved_words(self) -> str:
        return "Saved."

    def _done(self) -> None:
        toast(self, self._saved_words())
        self.dismiss(True)  # wrote: the list starts over (ResourceListScreen._edited)


class EditCategoryScreen(NewCategoryScreen):
    """Edit keeps a colour required: the category always has one, and an edit
    never sends `color: null` (contract: PUT /v1/categories/{category_id}).

    COLOR starts on the category's own colour, so `enter` keeps it; the save
    sends the colour only when another swatch was picked, so a colour no swatch
    shows stays as it is."""

    BINDINGS = form_bindings("Save")
    NOT_DONE = "Not saved"
    FIELDS = [
        NewCategoryScreen.FIELDS[0],
        Field("color", "COLOR", "color", choices=_PALETTE, required=True, hint="pick a swatch"),
    ]

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._id = record["id"]
        self._was = record.get("name") or ""  # as the list shows it
        self._values = {"name": self._was}
        if record.get("color"):
            self._values["color"] = record["color"]
        self.crumb = ("Manage", "Categories", record.get("name") or "—", "Edit")
        self._original_color = record.get("color")

    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("PUT", f"/categories/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        return _edit_payload(self._values, self._original_color)

    def _shown_name(self) -> str:
        return self._was

    def _saved_words(self) -> str:
        return "Saved."

    def _done(self) -> None:
        toast(self, self._saved_words())
        self.dismiss(True)  # wrote: the list starts over (ResourceListScreen._edited)


def opening_side(cents: int | None) -> str:
    """The word on an `opening` line's right, the same on every account, bank or
    person: `debt` below zero, `credit` above it, nothing at zero or with
    nothing readable typed."""
    if not cents:
        return ""
    return "debt" if cents < 0 else "credit"


#: An opening balance's two lines, `opening` and `as_of`; each currency of the
#: account has its own pair, keyed `<line>:<currency code>`.
_PAIR_LINES = {"opening": "opening", "as_of": "as of"}
#: An `as of` line's hint; an `opening` line has none.
AS_OF_HINT = "YYYY-MM-DD · the day the account held this"


def _pair_key(line: str, code: str) -> str:
    return f"{line}:{code}"


def _pair_line(key: str) -> tuple[str, str] | None:
    """`(line, currency code)` for a pair line's key; None for any other line."""
    line, _, code = key.partition(":")
    return (line, code) if code and line in _PAIR_LINES else None


@dataclasses.dataclass
class _OpeningBalance:
    """One currency's opening balance as the form knows it: the row's id
    (None while it has none), what it read or last saved (`opening` cents,
    `as_of` day), and whether its read is still out."""

    id: str | None
    original: dict = dataclasses.field(default_factory=dict)
    loading: bool = False


class EditAccountScreen(NewAccountScreen):
    """Edit an account — a bank account or a person — and its opening balances.

    The form opens on the account. CURRENCIES lists the currencies it holds,
    read-only, in the engine's order (contract: "Bank Accounts",
    "Per-currency order"), and the form ends with a pair of optional lines per
    currency after COLOR, each named by its currency: `PEN opening` (the signed
    amount, taken as typed) and `PEN as of` (its day), then `USD opening` and
    `USD as of`. Under an `opening` line there is no hint; on its right a word
    follows what is typed: `debt` below zero, `credit` above it, nothing at
    zero or while empty, the same on a bank account and a person. A person's opening
    balance is written as a bank account's is, with the currency's code
    (contract: POST /v1/accounts/{account_id}/opening-balance, "Required").

    A bank account's STATEMENT CODE opens holding its code. The account's own
    fields go in one `PUT /accounts/{id}`: the name, the colour when it changed,
    and the code only when it changed, `null` when the line was emptied, which
    clears the code with no question
    (contract: PUT /v1/accounts/{account_id}, "`statement_code`"). No currency
    rides in it. A person's form has no such line.

    Each currency's entry in the account's `currencies` names its opening
    balance by id, or `null` when it has none (contract: "Bank Accounts",
    "`currencies`"); the form reads each named row signed through
    `reads.fetch_transaction`, never from `transaction_type`
    (contract: "Base Conventions", "Sign convention — responses"). Until the
    reads land a save is held back, and a read that fails leaves that
    currency's pair read-only so the rest still saves.

    One save sends, in order, through `run_write`'s queue: the account's own
    changes (`PUT /accounts/{id}`), then one write per currency whose pair
    changed, in the pairs' order — `POST /accounts/{id}/opening-balance` with
    its `currency_code` when it has none, a `PUT /transactions/{id}` of only
    what changed, or, when the amount is emptied, a `DELETE
    /transactions/{id}` after one question naming each currency it deletes. A
    currency left as it was sends nothing. The account half is sent whenever
    it changed or no opening balance has anything to send. A refusal stops
    the writes behind it; it lands the cursor on its currency's line (the
    `as of` line for a date, the `opening` line otherwise), the typed values
    stay in the form, and the next save sends only what is still unsaved.
    When the account saved and an opening balance is refused, the note says
    which half went through. Saved, it dismisses with True so the list starts
    over; `esc` dismisses with True too once the account half went through.
    """

    BINDINGS = form_bindings("Save")
    NOT_DONE = "Not saved"
    # New's lines, CURRENCIES read-only, STATEMENT CODE's hint saying that
    # emptying it clears the code
    FIELDS = [
        Field("currencies", "CURRENCIES", "picks")
        if f.key == "currencies"
        else _field_with_hint(f, STATEMENT_CODE_EDIT_HINT)
        if f.key == "statement_code"
        else f
        for f in NewAccountScreen.FIELDS
    ]

    def __init__(self, record: dict, currencies: list[str]) -> None:
        super().__init__(currencies)
        self._id = record["id"]
        self._name = record.get("name") or "—"
        self._was = record.get("name") or ""  # as the list shows it
        # Both read-only here. The currencies change with their own keys on
        # Manage ▸ Accounts; `type` is no field of the account's update: it
        # changes with `t` there, which sends `make-person` or `make-account`
        # (contract: POST /v1/accounts/{account_id}/make-person)
        # (contract: POST /v1/accounts/{account_id}/make-account).
        self._locked = {"currencies", "type"}
        held = [h for _, _, h in reads.held_currencies([record])]
        self._codes: list[str] = [h["currency_code"] for h in held]
        self._values = {
            "type": "person" if record.get("is_person") else "bank",
            "name": record.get("name") or "",
            "currencies": list(self._codes),
        }
        if record.get("color"):
            self._values["color"] = record["color"]
        self._original_color = record.get("color")
        self._original_code: str | None = record.get("statement_code")
        if self._original_code and not record.get("is_person"):
            self._values["statement_code"] = self._original_code
        self.crumb = ("Manage", "Accounts", self._name, "Edit")
        # The account half as last saved: once it matches, a save sends only
        # the opening balances.
        self._account_sent = self._payload()
        self._wrote = False  # any write of the save landed: the list reloads
        self._refused_currency: str | None = None  # the currency of the last refused write
        self._openings: dict[str, _OpeningBalance] = {}
        for h in held:
            opening_id = h.get("opening_balance_transaction_id")
            self._openings[h["currency_code"]] = _OpeningBalance(
                opening_id, loading=opening_id is not None
            )
        self.FIELDS = [*self.FIELDS]
        for code in self._codes:
            self.FIELDS += [
                Field(_pair_key("opening", code), f"{code} OPENING"),
                Field(_pair_key("as_of", code), f"{code} AS OF", hint=AS_OF_HINT),
            ]

    # ---- each currency's two lines -------------------------------------------
    @property
    def _openings_loading(self) -> bool:
        return any(o.loading for o in self._openings.values())

    def _summary_label(self, key: str) -> str:
        pair = _pair_line(key)
        return f"{pair[1]} {_PAIR_LINES[pair[0]]}" if pair else super()._summary_label(key)

    def _required_note(self, key: str) -> str:
        if _pair_line(key):  # `PEN as of is required.`
            return f"{self._summary_label(key)} is required."
        return super()._required_note(key)

    def _field_required(self, f: Field) -> bool:
        pair = _pair_line(f.key)
        if pair and pair[0] == "as_of":
            return _pair_key("opening", pair[1]) in self._values  # an amount needs its day
        return f.required

    def _value_cell(self, key: str, value: object) -> Text:
        """An `opening` amount is drawn coloured by sign, as the ledger draws it."""
        pair = _pair_line(key)
        if pair and pair[0] == "opening":
            return amount_text(value, PALETTE, AMOUNT_RULE)
        return super()._value_cell(key, value)

    def _bar_value(self, key: str) -> str:
        pair = _pair_line(key)
        if pair and pair[0] == "opening":
            cents = self._values.get(key)
            return amount_to_text(cents) if cents is not None else ""
        return super()._bar_value(key)

    def _bar_word(self, key: str, text: str) -> str:
        pair = _pair_line(key)
        return (
            opening_side(parse_amount(text, current_format()))
            if pair and pair[0] == "opening"
            else ""
        )

    def _after_mount(self) -> None:
        if self._openings_loading:
            self._load_openings()

    @work(thread=True, exclusive=True)
    def _load_openings(self) -> None:
        """Read each currency's named opening balance, one row at a time."""
        from expense import config as config_module

        for code, opening in self._openings.items():
            if not opening.loading:
                continue
            try:
                cfg = config_module.ensure_loaded()
                body = reads.fetch_transaction(
                    cfg, str(opening.id), **screen_fetch_kwargs(self.app)
                )
            except Exception as exc:  # surface engine/config errors in-app, don't crash
                call_while_attached(self, self._opening_unread, code, format_error(exc))
                continue
            call_while_attached(self, self._opening_read, code, body)

    def _opening_read(self, code: str, body: dict) -> None:
        opening = self._openings[code]
        opening.loading = False
        cents = body.get("amount_cents") if isinstance(body, dict) else None
        day = (body.get("day") if isinstance(body, dict) else None) or ""
        if isinstance(cents, int):
            self._values[_pair_key("opening", code)] = opening.original["opening"] = cents
        if day:
            self._values[_pair_key("as_of", code)] = opening.original["as_of"] = day
        if _pair_line(self._key) in (("opening", code), ("as_of", code)):
            self._refresh_bar()
        self._refresh_view()

    def _opening_unread(self, code: str, message: str) -> None:
        self._openings[code].loading = False
        self._locked |= {_pair_key("opening", code), _pair_key("as_of", code)}
        if self._key in self._locked:
            self._current = self._first_editable()
            self._refresh_bar()
        self._refresh_view()
        toast(self, message, title="Failed", severity="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Textual calls the handler of every class in the MRO; this one calls the
        # bar form's itself, so the message stops here and `⏎` moves one line
        if event is not None:
            event.prevent_default()
        key = self._key
        pair = _pair_line(key)
        if pair is None:
            super().on_input_submitted(event)
            return
        line, code = pair
        amount_key = _pair_key("opening", code)
        text = self.query_one("#bar", Input).value.strip()
        if line == "opening":
            if not text:
                self._values.pop(key, None)
            else:
                cents = parse_amount(text, current_format())
                if cents is None:
                    toast(
                        self,
                        f"{code} opening: a signed decimal, e.g. -350.00. {amounts_sentence()}",
                        severity="error",
                    )
                    return
                self._values[key] = cents
        elif not text:
            if amount_key in self._values:
                toast(self, self._required_note(key), severity="error")
                return
            self._values.pop(key, None)
        elif not is_calendar_day(text):
            toast(self, f"{code} as of: use YYYY-MM-DD.", severity="error")
            return
        else:
            self._values[key] = text
        self._advance()

    def _opening_write(self, code: str) -> tuple[str, str, dict | None] | None:
        """`code`'s opening balance write for this save, or None."""
        amount_key = _pair_key("opening", code)
        if amount_key in self._locked:
            return None
        opening = self._openings[code]
        cents = self._values.get(amount_key)
        day = self._values.get(_pair_key("as_of", code))
        if opening.id is None:
            if cents is None:
                return None
            # The title is left out, so the engine names the row
            # (contract: POST /v1/accounts/{account_id}/opening-balance).
            body = {
                "transaction_id": str(uuid.uuid4()),
                "currency_code": code,
                "amount_cents": cents,
                "date": to_canonical_aware(str(day)),
            }
            return ("POST", f"/accounts/{self._id}/opening-balance", body)
        if cents is None:
            return ("DELETE", f"/transactions/{opening.id}", None)
        changes: dict = {}
        if cents != opening.original.get("opening"):
            changes["amount_cents"] = cents
        if day != opening.original.get("as_of"):
            changes["date"] = to_canonical_aware(str(day))
        if not changes:
            return None
        return ("PUT", f"/transactions/{opening.id}", changes)

    def _line_named(self, field: object, currency: str | None) -> str | None:
        """The pair lines a refusal names are its currency's own; the
        account's own write names none of them."""
        line = super()._line_named(field, currency)
        if line in _PAIR_LINES:
            return _pair_key(line, currency) if currency else None
        return line

    def _refusal_text(self, exc: Exception, currency: str | None = None) -> str:
        """As New's; a currency's refusal that names none of its lines lands
        on its `opening` line, so the cursor always says whose it was."""
        text = super()._refusal_text(exc, currency)
        self._refused_currency = currency
        if currency is not None and self._refused_line is None:
            line = _pair_key("opening", currency)
            if line not in self._locked:
                self._refused_line = line
        return text

    # ---- submit ------------------------------------------------------------
    def _submit_request(self) -> tuple[str, str, dict, str]:
        """The account half alone; `action_submit` adds the opening balances."""
        return ("PUT", f"/accounts/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        return self._account_body(self._values)

    def _account_body(self, values: dict) -> dict:
        """The account half's body from `values`: `_edit_payload`'s, and on a
        bank account the statement code when it is not the account's own,
        `null` when emptied."""
        body = _edit_payload(values, self._original_color)
        code = values.get("statement_code")
        if not self._is_person and code != self._original_code:
            body["statement_code"] = code
        return body

    def action_submit(self) -> None:
        if self._submitting:
            return
        if self._openings_loading:
            code = next(c for c in self._codes if self._openings[c].loading)
            toast(self, f"The {code} opening balance is still loading.", severity="error")
            return
        if not self._keep_bar() or not self._required_met():
            return
        account = self._payload()
        openings = [(code, w) for code in self._codes if (w := self._opening_write(code))]
        send_account = account != self._account_sent or not openings
        deleted = [code for code, (method, _, _) in openings if method == "DELETE"]
        if deleted:
            lines = "\n".join(
                " · ".join(
                    [
                        self._name,
                        code,
                        format_cents(self._openings[code].original.get("opening")),
                        str(self._openings[code].original.get("as_of") or "—"),
                    ]
                )
                for code in deleted
            )
            if len(deleted) == 1:
                title = "Delete this opening balance?"
                closing = "It leaves the account's balance, and no screen can bring it back."
            else:
                title = "Delete these opening balances?"
                closing = "They leave the account's balance, and no screen can bring them back."

            def answered(ok: bool | None) -> None:
                if ok:
                    self._send(account if send_account else None, openings)

            self.app.push_screen(ConfirmModal(title, f"{lines}\n{closing}"), answered)
            return
        self._send(account if send_account else None, openings)

    def _send(
        self, account: dict | None, openings: list[tuple[str, tuple[str, str, dict | None]]]
    ) -> None:
        self._submitting = True
        self.query_one("#hint", Static).update(Text("Saving…", style="dim"))
        report = SaveReport(
            len(openings) + (account is not None),
            not_done_line("Not all saved", self._kind(), self._shown_name()),
            self._left_behind() or "",
            _set_again,
        )
        if account is not None:
            account_part = report.part(
                "its changes",
                "The account's changes are saved.",
                "The account's changes are not saved:",
            )

            def account_saved() -> None:
                # the colour it sent is now the account's own: picking the old
                # one again is a change, and the next save sends it
                self._original_color = account.get("color", self._original_color)
                self._original_code = account.get("statement_code", self._original_code)
                self._account_sent = self._account_body(
                    {"statement_code": self._original_code, **account}
                )
                self._wrote = True
                account_part.record(None)
                if not openings:
                    self._done()

            self.run_write(
                "PUT",
                f"/accounts/{self._id}",
                json_body=account,
                on_success=account_saved,
                on_error=self._failed,
                error_text=self._refusal_text,
                left_behind=LeftBehind(account_part.refused, part=account_part),
            )
        for i, (code, (method, path, body)) in enumerate(openings):
            sent = {
                "opening": self._values.get(_pair_key("opening", code)),
                "as_of": self._values.get(_pair_key("as_of", code)),
            }
            deleted = method == "DELETE"
            part = report.part(
                code,
                f"The {code} opening balance is {'deleted' if deleted else 'saved'}.",
                f"The {code} opening balance is not{' deleted' if deleted else ''}:",
            )
            self.run_write(
                method,
                path,
                json_body=body,
                on_success=self._opening_saved(code, body, sent, part, last=i == len(openings) - 1),
                on_error=self._half_failed if account is not None else self._failed,
                error_text=lambda exc, code=code: self._refusal_text(exc, code),
                left_behind=LeftBehind(part.refused, part=part),
            )

    def _opening_saved(
        self, code: str, body: dict | None, sent: dict, part: ReportedPart, *, last: bool
    ):
        """The success callback of `code`'s write: the form now knows the row
        as saved, so a later refusal's next save sends only what is unsaved."""

        def saved() -> None:
            self._wrote = True
            part.record(None)
            opening = self._openings[code]
            if sent["opening"] is None:  # deleted
                opening.id, opening.original = None, {}
            else:
                if opening.id is None and body is not None:
                    opening.id = body["transaction_id"]
                opening.original = dict(sent)
            if last:
                self._done()

        return saved

    def _shown_name(self) -> str:
        return self._was

    def _landed_after_leaving(self, item, error, failure) -> bool:
        """The list reads again once, at the save's last answer, if any part landed or
        ended unknown; parts all refused clearly leave it be. A write with no part is one
        report of its own: it lands, or ends unknown, as any single save does."""
        behind = item.left_behind
        if behind is None or behind.part is None:
            return error is None or may_have_landed(failure)
        report = behind.part.report
        return report.complete and (
            report.landed or any(may_have_landed(f) for f in report.failures)
        )

    def _saved_words(self) -> str:
        return "Saved."

    def _half_failed(self, message: str) -> None:
        """The account saved, an opening balance was refused: say which is which.

        A refusal with a line of its own saying what to do (`errors.next_step`)
        ends the note with that line; any other ends it with the form's own."""
        self._land_on_refused_line()
        self._submitting = False
        closing = (
            "" if self._refusal_says_next else "\n\nIt is still in the form: fix it and save again."
        )
        saved = f"The account's changes are saved. The {self._refused_currency} opening balance"
        self._show_refusal(f"{saved} is not:\n{message}{closing}")
        self._refresh_view()

    def action_cancel(self) -> None:
        self.dismiss(True if self._wrote else None)

    def _done(self) -> None:
        self.notify("Saved.")
        self.dismiss(True)
