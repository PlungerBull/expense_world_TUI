"""Create forms — new hashtag / category / account.

A lightweight bar-cycle form (same look as Log): cycle fields with the input
bar, pick choices from a suggestion list, `ctrl+s` (or enter on the last field)
POSTs. Reached with `n` on the Manage list screens.

New account covers both kinds: its first field is TYPE (`bank` / `person`,
prefilled `bank`), and a `person` picks `POST /people` instead of
`POST /accounts` — the People API. `is_person`
is never sent as a field; it is a 422 on both routes, and the endpoint is the
flag. Editing cannot change it, so TYPE is locked read-only on the edit form.
"""

import uuid

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.widgets import Input, Static

from expense import reads
from expense.currencies import SUPPORTED_CURRENCIES
from expense.dates import is_calendar_day, to_canonical_aware
from expense.errors import EngineError, format_error, next_step
from expense.formatting import format_cents
from expense.quickadd.money import amount_to_text, parse_amount
from expense.quickadd.names import matches
from expense.tui.screens._base import screen_fetch_kwargs
from expense.tui.screens._form import FormScreen, form_bindings
from expense.tui.screens.modals import ConfirmModal

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
_CURRENCIES = [(c, c) for c in SUPPORTED_CURRENCIES]
# Bank first: it is the prefilled default, so `enter` on an untouched TYPE field
# keeps `bank` and adding an ordinary account still costs one keypress.
_ACCOUNT_TYPES = [("bank", "bank"), ("person", "person")]


class Field:
    def __init__(self, key, label, kind="text", *, choices=None, required=False, hint=""):
        self.key = key
        self.label = label
        self.kind = kind  # "text" | "choice" | "color"
        self.choices = choices or []
        self.required = required
        self.hint = hint


class BarFormScreen(FormScreen):
    FIELDS: list = []
    NOUN = "item"

    # ---- FormScreen hooks (Field-driven) ----------------------------------
    def _sequence(self) -> list[str]:
        return [f.key for f in self.FIELDS]

    def _field(self, key: str) -> Field:
        return next(f for f in self.FIELDS if f.key == key)

    @property
    def _f(self) -> Field:
        return self.FIELDS[self._current]

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

    def _suggests(self, key: str) -> bool:
        return self._field(key).kind in ("choice", "color")

    def _bar_value(self, key: str) -> str:
        f = self._field(key)
        return str(self._values.get(key, "")) if f.kind == "text" else ""

    def _recompute(self, text: str) -> None:
        f = self._f
        needle = text.strip()
        if f.kind in ("choice", "color"):
            self._suggestions = [
                (v, d) for (v, d) in f.choices if matches(needle, d) or matches(needle, v)
            ]
        else:
            self._suggestions = []
        self._suggest_idx = 0

    # ---- commit ----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        f = self._f
        text = self.query_one("#bar", Input).value.strip()
        if f.kind == "text":
            if not text:
                if f.required:
                    self.notify(f"{f.label.title()} is required.", severity="error")
                    return
                self._values.pop(f.key, None)
            else:
                self._values[f.key] = text
            self._advance()
            return
        # choice / color
        if not text and not f.required:
            self._values.pop(f.key, None)
            self._advance()
            return
        picked = self._suggestions[self._suggest_idx] if self._suggestions else None
        if picked is None:
            self.notify(f"Pick a {f.label.lower()}.", severity="error")
            return
        self._values[f.key] = picked[0]
        self._advance()

    # ---- render ----------------------------------------------------------
    def _suggest_renderable(self) -> RenderableType:
        f = self._f
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
        for i, f in enumerate(self.FIELDS):
            locked = f.key in self._locked
            if f.key in self._values:
                if f.kind == "color":
                    hex_ = self._values[f.key]
                    value = Text.assemble(("██ ", hex_), (self._color_name(hex_), ""))
                else:
                    value = Text(self._value_text(f.key, self._values[f.key]))
            else:
                tag = "  *" if self._field_required(f) else "  (optional)"
                value = Text("—" + tag, style="dim")
            if locked:  # edit forms lock immutable fields (e.g. account currency)
                value.append("  read-only", style="dim")
            label = Text(f.label.lower(), style="dim" if locked else "")
            if i == self._current and not locked:
                label.stylize("bold")
            t.add_row(label, value)
        return t

    @staticmethod
    def _color_name(hex_: str) -> str:
        return next((d for (v, d) in _PALETTE if v == hex_), hex_)

    # ---- submit ----------------------------------------------------------
    def _payload(self) -> dict:
        raise NotImplementedError

    def _done(self) -> None:
        self.notify(f"{self.NOUN.title()} created.")
        self.dismiss()


class NewHashtagScreen(BarFormScreen):
    crumb = ("Manage", "Hashtags", "New")
    RESOURCE = "hashtags"
    NOUN = "hashtag"
    FIELDS = [Field("name", "NAME", required=True, hint="lowercase, no “#” · enter creates")]

    def _payload(self) -> dict:
        return {"id": str(uuid.uuid4()), "name": self._values["name"].lstrip("#")}


class NewCategoryScreen(BarFormScreen):
    crumb = ("Manage", "Categories", "New")
    RESOURCE = "categories"
    NOUN = "category"
    FIELDS = [
        Field("name", "NAME", required=True, hint="enter to save"),
        Field("color", "COLOR", "color", choices=_PALETTE, required=True, hint="pick a swatch"),
    ]

    def _payload(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "name": self._values["name"],
            "color": self._values["color"],
        }


class NewAccountScreen(BarFormScreen):
    """New bank account *or* person — one form, one key, a TYPE field on top.

    A person is a bank account with `is_person = true`, and the two take exactly
    the same fields; the only difference is which endpoint the save goes to
    (`POST /accounts` vs `POST /people`). So the choice is a field (Why:
    docs/decisions.md "A settled person is folded, never hidden"), **prefilled
    to `bank`** — `n`, `enter`, name… still adds an ordinary account
    without an extra decision.

    `is_person` is never sent in the body: `POST /accounts` rejects it and
    `POST /people` implies it, so on either route the field is a 422. The endpoint
    *is* the flag.
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
        Field("name", "NAME", required=True, hint="enter to save"),
        Field(
            "currency", "CURRENCY", "choice", choices=_CURRENCIES, required=True, hint="PEN or USD"
        ),
        Field("color", "COLOR", "color", choices=_PALETTE, hint="optional · empty enter to skip"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._values["type"] = "bank"

    @property
    def _is_person(self) -> bool:
        return self._values.get("type") == "person"

    def _submit_request(self) -> tuple[str, str, dict, str]:
        # The one place the TYPE field is read. `/people` is the only people
        # route there is — everything after creation is an account route.
        resource = "people" if self._is_person else self.RESOURCE
        return ("POST", f"/{resource}", self._payload(), "Creating…")

    def _done(self) -> None:
        self.notify("Person created." if self._is_person else "Account created.")
        self.dismiss()

    def _payload(self) -> dict:
        payload = {
            "id": str(uuid.uuid4()),
            "name": self._values["name"],
            "currency_code": self._values["currency"],
        }
        if self._values.get("color"):
            payload["color"] = self._values["color"]
        return payload


# --------------------------------------------------------------------------- #
# Edit forms — same bar-form, prefilled, PUT instead of POST. Reached with `e`
# on a Manage list row (ResourceListScreen). Currency is immutable
# (engine rejects it), so account edit locks it to a read-only summary row.
# Each declares `BINDINGS = form_bindings("Save")`: the footer names what
# `ctrl+s` does here, not the parent's `Create`.
# --------------------------------------------------------------------------- #
class EditHashtagScreen(NewHashtagScreen):
    BINDINGS = form_bindings("Save")

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._id = record["id"]
        self._values = {"name": (record.get("name") or "").lstrip("#")}
        self.crumb = ("Manage", "Hashtags", record.get("name") or "—", "Edit")

    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("PUT", f"/hashtags/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        return {"name": self._values["name"].lstrip("#")}

    def _done(self) -> None:
        self.notify("Saved.")
        self.dismiss(True)  # wrote: the list starts over (ResourceListScreen._edited)


class EditCategoryScreen(NewCategoryScreen):
    BINDINGS = form_bindings("Save")

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._id = record["id"]
        self._values = {"name": record.get("name") or ""}
        if record.get("color"):
            self._values["color"] = record["color"]
        self.crumb = ("Manage", "Categories", record.get("name") or "—", "Edit")

    def _submit_request(self) -> tuple[str, str, dict, str]:
        return ("PUT", f"/categories/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        payload = {"name": self._values["name"]}
        if self._values.get("color"):
            payload["color"] = self._values["color"]
        return payload

    def _done(self) -> None:
        self.notify("Saved.")
        self.dismiss(True)  # wrote: the list starts over (ResourceListScreen._edited)


#: The engine field a refusal names → the account Edit form line it lands on.
_REFUSED_LINES = {
    "name": "name",
    "color": "color",
    "amount_cents": "opening",
    "date": "as_of",
}


class EditAccountScreen(NewAccountScreen):
    """Edit an account — and, on a bank account, its opening balance.

    A bank account's form ends with two optional lines after COLOR: OPENING
    (the signed amount, in the account's currency, taken as typed) and AS OF
    (its day). A person has neither: what you owe each other comes only from
    the rows you record.

    The account names its opening balance by id, or `null` when it has none
    (contract: "Bank Accounts", "Opening balance"); the form reads that row
    signed through `reads.fetch_transaction`, never from `transaction_type`
    (contract: "Base Conventions", "Sign convention — responses"). Until the
    read lands a save is held back, and a read that fails leaves the two lines
    read-only so the account itself still saves.

    One save may send two writes, in order, through `run_write`'s queue: the
    account's own changes (`PUT /accounts/{id}`), then the opening balance —
    `POST /accounts/{id}/opening-balance` when there is none, a `PUT
    /transactions/{id}` of only what changed, or, when the amount is emptied,
    a `DELETE /transactions/{id}` after a question. The account half is sent
    whenever it changed or the opening balance has nothing to send. When the
    account saves and the opening balance is refused, the note says which half
    went through, the typed values stay in the form, and the next save sends
    only the opening balance. Saved, it dismisses with True so the list starts
    over; `esc` dismisses with True too once the account half went through.
    """

    BINDINGS = form_bindings("Save")

    def __init__(self, record: dict) -> None:
        super().__init__()
        self._id = record["id"]
        self._name = record.get("name") or "—"
        # Both immutable after creation. `currency` the engine rejects outright;
        # `type` has no update path at all — `is_person` is settable only at the
        # moment of creation, which is the entire reason `POST /people` exists.
        self._locked = {"currency", "type"}
        self._values = {
            "type": "person" if record.get("is_person") else "bank",
            "name": record.get("name") or "",
            "currency": record.get("currency_code") or "",
        }
        if record.get("color"):
            self._values["color"] = record["color"]
        self.crumb = ("Manage", "Accounts", self._name, "Edit")
        # The account half as last saved: once it matches, a save sends only
        # the opening balance.
        self._account_sent = self._payload()
        self._account_saved = False
        self._has_opening = not record.get("is_person")
        self._opening_id: str | None = record.get("opening_balance_transaction_id")
        self._opening_original: dict = {}  # {"opening": cents, "as_of": day} once read
        self._opening_loading = False
        self._refused_line: str | None = None
        self._refusal_says_next = False  # the last refusal carried its own next step
        if self._has_opening:
            currency = record.get("currency_code") or "?"
            self.FIELDS = [
                *NewAccountScreen.FIELDS,
                Field(
                    "opening",
                    "OPENING",
                    hint=(
                        "signed · 350.00 is money you have · -350.00 is money you owe"
                        f" · in {currency} · optional"
                    ),
                ),
                Field("as_of", "AS OF", hint="YYYY-MM-DD · the day the account held this"),
            ]
            self._opening_loading = self._opening_id is not None

    # ---- the opening balance's two lines ---------------------------------
    def _field_required(self, f: Field) -> bool:
        if f.key == "as_of":
            return "opening" in self._values  # an amount needs its day
        return f.required

    def _value_text(self, key: str, value: object) -> str:
        return format_cents(value) if key == "opening" else str(value)

    def _bar_value(self, key: str) -> str:
        if key == "opening":
            cents = self._values.get("opening")
            return amount_to_text(cents) if cents is not None else ""
        return super()._bar_value(key)

    def _after_mount(self) -> None:
        if self._opening_loading:
            self._load_opening()

    @work(thread=True, exclusive=True)
    def _load_opening(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            body = reads.fetch_transaction(
                cfg, str(self._opening_id), **screen_fetch_kwargs(self.app)
            )
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            self.app.call_from_thread(self._opening_unread, format_error(exc))
            return
        self.app.call_from_thread(self._opening_read, body)

    def _opening_read(self, body: dict) -> None:
        self._opening_loading = False
        cents = body.get("amount_cents") if isinstance(body, dict) else None
        day = ((body.get("date") if isinstance(body, dict) else None) or "")[:10]
        if isinstance(cents, int):
            self._values["opening"] = self._opening_original["opening"] = cents
        if day:
            self._values["as_of"] = self._opening_original["as_of"] = day
        if self._key in ("opening", "as_of"):
            self._refresh_bar()
        self._refresh_view()

    def _opening_unread(self, message: str) -> None:
        self._opening_loading = False
        self._locked |= {"opening", "as_of"}
        if self._key in self._locked:
            self._current = self._first_editable()
            self._refresh_bar()
        self._refresh_view()
        self.notify(message, title="Failed", severity="error")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        key = self._key
        if key not in ("opening", "as_of"):
            super().on_input_submitted(event)
            return
        text = self.query_one("#bar", Input).value.strip()
        if key == "opening":
            if not text:
                self._values.pop("opening", None)
            else:
                cents = parse_amount(text)
                if cents is None:
                    self.notify("Opening: a signed decimal, e.g. -350.00", severity="error")
                    return
                self._values["opening"] = cents
        elif not text:
            if "opening" in self._values:
                self.notify(f"{self._label('as_of').title()} is required.", severity="error")
                return
            self._values.pop("as_of", None)
        elif not is_calendar_day(text):
            self.notify("As of: use YYYY-MM-DD.", severity="error")
            return
        else:
            self._values["as_of"] = text
        self._advance()

    def _opening_write(self) -> tuple[str, str, dict | None] | None:
        """The opening balance's one write for this save, or None."""
        if not self._has_opening or "opening" in self._locked:
            return None
        cents = self._values.get("opening")
        day = self._values.get("as_of")
        if self._opening_id is None:
            if cents is None:
                return None
            # The title is left out, so the engine names the row
            # (contract: POST /v1/accounts/{account_id}/opening-balance).
            body = {
                "transaction_id": str(uuid.uuid4()),
                "amount_cents": cents,
                "date": to_canonical_aware(str(day)),
            }
            return ("POST", f"/accounts/{self._id}/opening-balance", body)
        if cents is None:
            return ("DELETE", f"/transactions/{self._opening_id}", None)
        changes: dict = {}
        if cents != self._opening_original.get("opening"):
            changes["amount_cents"] = cents
        if day != self._opening_original.get("as_of"):
            changes["date"] = to_canonical_aware(str(day))
        if not changes:
            return None
        return ("PUT", f"/transactions/{self._opening_id}", changes)

    # ---- submit ------------------------------------------------------------
    def _submit_request(self) -> tuple[str, str, dict, str]:
        """The account half alone; `action_submit` adds the opening balance."""
        return ("PUT", f"/accounts/{self._id}", self._payload(), "Saving…")

    def _payload(self) -> dict:
        payload = {"name": self._values["name"]}
        if self._values.get("color"):
            payload["color"] = self._values["color"]
        return payload

    def action_submit(self) -> None:
        if self._submitting:
            return
        if self._opening_loading:
            self.notify("The opening balance is still loading.", severity="error")
            return
        if not self._required_met():
            return
        account = self._payload()
        opening = self._opening_write()
        send_account = account != self._account_sent or opening is None
        if opening is not None and opening[0] == "DELETE":
            line = " · ".join(
                [
                    self._name,
                    format_cents(self._opening_original.get("opening")),
                    str(self._opening_original.get("as_of") or "—"),
                ]
            )

            def answered(ok: bool | None) -> None:
                if ok:
                    self._send(account if send_account else None, opening)

            self.app.push_screen(
                ConfirmModal(
                    "Delete this opening balance?",
                    f"{line}\nIt leaves the account's balance, and no screen can bring it back.",
                ),
                answered,
            )
            return
        self._send(account if send_account else None, opening)

    def _refusal_text(self, exc: Exception) -> str:
        """The `error_text` of this form's writes: notes the form line the
        refusal names, for the failure callback to land on, then reads as every
        failed write does."""
        self._refused_line = None
        self._refusal_says_next = next_step(exc) is not None
        if isinstance(exc, EngineError):
            for field in [*(exc.reasons or {}), *(exc.fields or {})]:
                line = _REFUSED_LINES.get(field)
                if line in self._sequence() and line not in self._locked:
                    self._refused_line = line
                    break
        return format_error(exc)

    def _land_on_refused_line(self) -> None:
        """Put the cursor on the line the refusal named, with what was typed in
        the bar; a refusal that names none of the form's lines leaves it where
        it was."""
        line, self._refused_line = self._refused_line, None
        if line is not None:
            self._current = self._sequence().index(line)
            self._refresh_bar()

    def _failed(self, message: str) -> None:
        self._land_on_refused_line()
        super()._failed(message)

    def _send(self, account: dict | None, opening: tuple[str, str, dict | None] | None) -> None:
        self._submitting = True
        self.query_one("#hint", Static).update(Text("Saving…", style="dim"))
        if account is not None:

            def account_saved() -> None:
                self._account_sent = account
                self._account_saved = True
                if opening is None:
                    self._done()

            self.run_write(
                "PUT",
                f"/accounts/{self._id}",
                json_body=account,
                on_success=account_saved,
                on_error=self._failed,
                error_text=self._refusal_text,
            )
        if opening is not None:
            method, path, body = opening
            self.run_write(
                method,
                path,
                json_body=body,
                on_success=self._done,
                on_error=self._half_failed if account is not None else self._failed,
                error_text=self._refusal_text,
            )

    def _half_failed(self, message: str) -> None:
        """The account saved, the opening balance was refused: say which is which.

        A refusal with a line of its own saying what to do (`errors.next_step`)
        ends the note with that line; any other ends it with the form's own."""
        self._land_on_refused_line()
        self._submitting = False
        closing = (
            "" if self._refusal_says_next else "\n\nIt is still in the form: fix it and save again."
        )
        self.notify(
            f"The account's changes are saved. The opening balance is not:\n{message}{closing}",
            title="Failed",
            severity="error",
        )
        self._refresh_view()

    def action_cancel(self) -> None:
        self.dismiss(True if self._account_saved else None)

    def _done(self) -> None:
        self.notify("Saved.")
        self.dismiss(True)
