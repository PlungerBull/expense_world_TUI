"""Create forms — new hashtag / category / account.

A lightweight bar-cycle form (same look as Log): cycle fields with the input
bar, pick choices from a suggestion list, `ctrl+s` (or enter with no field
ahead that can change) POSTs. Reached with `n` on the Manage list screens.

New account covers both kinds: its first field is TYPE (`bank` / `person`,
prefilled `bank`), and both save with `POST /accounts`; the body carries
`kind: "bank"` or `kind: "person"` (contract: POST /v1/accounts, "Required"). Editing
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
from textual.widgets import Input

from expense import reads
from expense.dates import is_calendar_day, to_canonical_aware
from expense.errors import EngineError, format_error, key_field, key_index
from expense.formatting import format_cents
from expense.number_format import amounts_sentence, current_format
from expense.quickadd.money import amount_to_text, parse_amount
from expense.tui.screens._base import (
    ResourceListScreen,
    call_while_attached,
    not_done_line,
    screen_fetch_kwargs,
)
from expense.tui.screens._form import FormScreen, form_bindings, may_have_landed
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
#: A bank account's LAST 4 on New: optional, and `⏎` goes on to CURRENCIES.
LAST4_HINT = "optional · the card's last 4 digits · enter to go on"
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
#: Edit; a line the form does not have is passed over. A key under `currencies` is
#: read by `NewAccountScreen._line_named`.
_REFUSED_LINES = {
    "bank_code": "bank",
    "last4": "last4",
    "name": "name",
    "color": "color",
    "currencies": "currencies",
    "statement_code": "statement_code",
}


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


def opening_balance_body(cents: int, day: str) -> dict:
    """An opening balance's body, the one shape `POST /accounts` (inside a currency's entry)
    and `PUT /accounts/{id}` (a currency's set) share: a fresh `transaction_id`, the signed
    amount as typed, and the day in its wire form. The title is left out, so the engine
    names the row (contract: POST /v1/accounts, "Optional")."""
    return {
        "transaction_id": str(uuid.uuid4()),
        "amount_cents": cents,
        "date": to_canonical_aware(day),
    }


class NewAccountScreen(BarFormScreen):
    """New bank account *or* person — one form, one key, a TYPE field on top.

    TYPE is **prefilled to `bank`** — `n`, `enter`, … still adds an ordinary account
    without an extra decision (Why: docs/decisions.md "A settled person is folded, never
    hidden"). A bank account's lines are `type`, BANK, LAST 4, CURRENCIES, STATEMENT CODE and
    COLOR; a person's are `type`, NAME, CURRENCIES and COLOR. BANK, LAST 4 and STATEMENT CODE
    leave the form with TYPE on person and return holding what was typed. A bank account
    has no NAME line: the engine builds its name (contract: POST /v1/accounts, "The name").
    BANK picks from the engine's banks (`GET /banks`, in its order), required; LAST 4 is
    optional and the engine judges its shape.

    CURRENCIES takes one currency or more, picked as the Edit form's HASHTAGS picks
    hashtags: a typed code and `⏎` add the highlighted one and stay for another, an empty
    `⏎` goes on. After COLOR the form has a pair of optional lines per currency picked, in
    pick order, as the Edit form has (`PEN opening`, `PEN as of`).

    The save is one `POST /accounts` carrying everything: `kind`; on a bank account
    `bank_code` and `last4` only when typed (never `null`); on a person `name`; `currencies`
    in pick order, each `{currency_code}` and, when its amount was typed, `opening_balance`
    (contract: POST /v1/accounts, "Required") (contract: POST /v1/accounts, "Optional").
    STATEMENT CODE and COLOR, skipped, are left out of the body.

    A refusal reads in the engine's words and puts the cursor back on the line it names
    (`_line_named`), with what was typed; a key naming `currencies.<i>…` names the
    currency at place `i` of the body sent.
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
        Field("bank", "BANK", "choice", required=True),
        Field("last4", "LAST 4", hint=LAST4_HINT),
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

    def __init__(self, currencies: list[str], banks: list[str]) -> None:
        """`currencies`, `banks`: the engine's codes (`GET /currencies`, `GET /banks`), read
        by the list this form opens from, in the engine's order: what CURRENCIES and BANK
        offer."""
        super().__init__()
        offered = {
            "currencies": [(code, code) for code in currencies],
            "bank": [(code, code) for code in banks],
        }
        self.FIELDS = [
            _field_with_choices(f, offered[f.key]) if f.key in offered else f for f in self.FIELDS
        ]
        self._values["type"] = "bank"

    @property
    def _is_person(self) -> bool:
        return self._values.get("type") == "person"

    def _identity_lines(self) -> list[str]:
        """The lines after TYPE that name the account: a person's NAME, a bank account's
        BANK and LAST 4."""
        return ["name"] if self._is_person else ["bank", "last4"]

    def _sequence(self) -> list[str]:
        who = self._identity_lines()
        code = [] if self._is_person else ["statement_code"]
        pairs = [
            _pair_key(line, currency)
            for currency in self._values.get("currencies", ())
            for line in _PAIR_LINES
        ]
        return ["type", *who, "currencies", *code, "color", *pairs]

    def _field(self, key: str) -> Field:
        """The form's line `key`; a currency's pair lines are made as it is picked."""
        pair = _pair_line(key)
        if pair is None:
            return super()._field(key)
        line, code = pair
        if line == "opening":
            return Field(key, f"{code} OPENING")
        return Field(key, f"{code} AS OF", hint=AS_OF_HINT)

    def _required(self) -> tuple[str, ...]:
        return tuple(k for k in self._sequence() if self._field_required(self._field(k)))

    def _typed(self, key: str, text: str) -> str:
        return text.upper() if key == "statement_code" else text

    # ---- each currency's two lines -------------------------------------------
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
                    example = format_cents(-35000, grouped=False)
                    toast(
                        self,
                        f"{code} opening: a signed decimal, e.g. {example}. {amounts_sentence()}",
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

    # ---- submit ------------------------------------------------------------
    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("POST", f"/{self.RESOURCE}", self._payload(), "Creating…")

    def _saved_words(self) -> str:
        return "Person created." if self._is_person else "Account created."

    def _kind(self) -> str:
        return "Person" if self._is_person else "Account"

    def _shown_name(self) -> str:
        """A person's name as typed; a bank account has none typed (the engine builds its
        name), so none: the left-behind line reads `(unnamed)`."""
        return "" if not self._is_person else self._values["name"]

    def _done(self) -> None:
        toast(self, self._saved_words())
        self.dismiss()

    def _payload(self) -> dict:
        payload: dict = {"id": str(uuid.uuid4()), "kind": "person" if self._is_person else "bank"}
        if self._is_person:
            payload["name"] = self._values["name"]
        else:
            payload["bank_code"] = self._values["bank"]
            if self._values.get("last4"):
                payload["last4"] = self._values["last4"]
        payload["currencies"] = [self._currency_entry(code) for code in self._values["currencies"]]
        if self._values.get("color"):
            payload["color"] = self._values["color"]
        if not self._is_person and self._values.get("statement_code"):
            payload["statement_code"] = self._values["statement_code"]
        return payload

    def _currency_entry(self, code: str) -> dict:
        """One entry of the body's `currencies`: the code and, when its amount was typed,
        its opening balance."""
        entry: dict = {"currency_code": code}
        cents = self._values.get(_pair_key("opening", code))
        if cents is not None:
            entry["opening_balance"] = opening_balance_body(
                cents, str(self._values[_pair_key("as_of", code)])
            )
        return entry

    def _line_named(self, field: object) -> str | None:
        """The form line a refusal's `field` names: `_REFUSED_LINES`', and for a key under
        `currencies`, CURRENCIES, or a currency's pair line when it names that currency's
        opening balance: `date` is its `as of` line, any other part its `opening` line."""
        index = key_index(field, "currencies")
        if index is None:
            return _REFUSED_LINES.get(str(field))
        part = key_field(field, "currencies") or ""
        codes = self._values.get("currencies", ())
        if part.startswith("opening_balance.") and index < len(codes):
            line = "as_of" if part == "opening_balance.date" else "opening"
            return _pair_key(line, codes[index])
        return "currencies"

    def _refusal_text(self, exc: Exception) -> str:
        """The `error_text` of this form's writes: notes the form line the refusal
        names, for the failure callback to land on (the first in the form's order when
        it names several), then reads as every failed write does."""
        self._refused_line = None
        if isinstance(exc, EngineError):
            sequence = self._sequence()
            named = (
                self._line_named(field) for field in [*(exc.reasons or {}), *(exc.fields or {})]
            )
            lines = [line for line in named if line in sequence and line not in self._locked]
            if lines:
                self._refused_line = min(lines, key=sequence.index)
        return format_error(exc)


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


class EditAccountScreen(NewAccountScreen):
    """Edit an account — a bank account or a person — and its opening balances.

    The form opens on the account. CURRENCIES lists the currencies it holds,
    read-only, in the engine's order (contract: "Bank Accounts",
    "Per-currency order"), and the form ends with a pair of optional lines per
    currency after COLOR, built as New's are: `PEN opening` (the signed
    amount, taken as typed) and `PEN as of` (its day), then `USD opening` and
    `USD as of`. Under an `opening` line there is no hint; on its right a word
    follows what is typed: `debt` below zero, `credit` above it, nothing at
    zero or while empty, the same on a bank account and a person.

    A bank account has no NAME line: its name is the engine's, and a `name` sent
    for it is refused (contract: PUT /v1/accounts/{account_id}). A person's NAME
    opens holding its name. A bank account's STATEMENT CODE opens holding its code.

    Each currency's entry in the account's `currencies` names its opening
    balance by id, or `null` when it has none (contract: "Bank Accounts",
    "`currencies`"); the form reads each named row signed through
    `reads.fetch_transaction`, never from `transaction_type`
    (contract: "Base Conventions", "Sign convention — responses"). Until the
    reads land a save is held back, and a read that fails leaves that
    currency's pair read-only so the rest still saves.

    The save is one `PUT /accounts/{id}`, all or nothing
    (contract: PUT /v1/accounts/{account_id}). It carries the account's own fields
    only when they changed: a person's `name`, the `color`, and the
    `statement_code`, `null` when the line was emptied, which clears the code with
    no question. `opening_balances`, keyed by currency code, carries only the
    currencies whose pair changed: a currency with no opening balance gets a set
    (`transaction_id`, `amount_cents`, `date`); one that has it gets a change of
    only the `amount_cents` and/or `date` that changed; one whose amount was
    emptied gets `null`, after one question naming each currency it deletes, and
    only `y` sends. A form with nothing changed sends `{}`.

    A refusal names its line: `opening_balances.<code>.date` is that currency's
    `as of`, any other `opening_balances.<code>` key its `opening`. The typed
    values stay in the form; with several codes named the cursor goes to the
    first in the form's order. Saved, it dismisses with True so the list starts over.
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
        if f.key not in ("bank", "last4")
    ]

    def __init__(self, record: dict, currencies: list[str]) -> None:
        super().__init__(currencies, [])
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
        person = record.get("kind") == "person"
        self._values = {
            "type": "person" if person else "bank",
            "currencies": list(self._codes),
        }
        if person:
            self._values["name"] = self._was
        if record.get("color"):
            self._values["color"] = record["color"]
        self._original_color = record.get("color")
        self._original_code: str | None = record.get("statement_code")
        if self._original_code and not person:
            self._values["statement_code"] = self._original_code
        self.crumb = ("Manage", "Accounts", self._name, "Edit")
        self._openings: dict[str, _OpeningBalance] = {}
        for h in held:
            opening_id = h.get("opening_balance_transaction_id")
            self._openings[h["currency_code"]] = _OpeningBalance(
                opening_id, loading=opening_id is not None
            )

    @property
    def _openings_loading(self) -> bool:
        return any(o.loading for o in self._openings.values())

    def _identity_lines(self) -> list[str]:
        return ["name"] if self._is_person else []

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

    def _opening_entry(self, code: str) -> dict | None | bool:
        """`code`'s entry of the body's `opening_balances`: the set, the change, or
        `None` for a clear; False when the pair is as it was (nothing to send)."""
        amount_key = _pair_key("opening", code)
        if amount_key in self._locked:
            return False
        opening = self._openings[code]
        cents = self._values.get(amount_key)
        day = self._values.get(_pair_key("as_of", code))
        if opening.id is None:
            return False if cents is None else opening_balance_body(cents, str(day))
        if cents is None:
            return None
        changes: dict = {}
        if cents != opening.original.get("opening"):
            changes["amount_cents"] = cents
        if day != opening.original.get("as_of"):
            changes["date"] = to_canonical_aware(str(day))
        return changes or False

    def _line_named(self, field: object) -> str | None:
        """As New's, and `opening_balances.<code>.date` is that currency's `as of`
        line, any other `opening_balances.<code>…` key its `opening` line."""
        bits = str(field).split(".", 2)
        if bits[0] != "opening_balances" or len(bits) < 2:
            return super()._line_named(field)
        return _pair_key("as_of" if bits[2:] == ["date"] else "opening", bits[1])

    # ---- submit ------------------------------------------------------------
    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("PUT", f"/accounts/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        """The account's own fields that changed, and `opening_balances` for the
        currencies whose pair changed."""
        body: dict = {}
        if self._is_person and self._values["name"] != self._was:
            body["name"] = self._values["name"]
        if self._values.get("color") and self._values["color"] != self._original_color:
            body["color"] = self._values["color"]
        code = self._values.get("statement_code")
        if not self._is_person and code != self._original_code:
            body["statement_code"] = code
        openings = {
            code: entry for code in self._codes if (entry := self._opening_entry(code)) is not False
        }
        if openings:
            body["opening_balances"] = openings
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
        deleted = [code for code in self._codes if self._opening_entry(code) is None]
        if not deleted:
            self._send_save()
            return
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
                self._send_save()

        self.app.push_screen(ConfirmModal(title, f"{lines}\n{closing}"), answered)

    def _shown_name(self) -> str:
        return self._was

    def _saved_words(self) -> str:
        return "Saved."

    def _done(self) -> None:
        self.notify("Saved.")
        self.dismiss(True)
