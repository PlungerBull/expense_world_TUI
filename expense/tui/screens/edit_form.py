"""Edit a transaction — the bar-cycle form.

One input bar cycles through fields; a summary fills below. Entity fields
(account/category/hashtags) show a live-filtered suggestion list — pick
existing entities only. Their bar opens empty, the list in its usual order;
on ACCOUNT and CATEGORY the highlight starts on the line's own account or
category whenever the bar is empty and the list holds it, so `⏎` with nothing
typed keeps it and stepping through the form changes nothing (`_recompute`).
The category list is the one the ledger's bulk `c` offers, in the engine's
order: @Pendiente is in it, so a row in @Pendiente starts on it and a row can
be sent back there; @Opening never is (`reads.pickable_categories`).
Typing filters the list and highlights its first match; `↑↓` choose another.

**Edit only** — `+` opens the LOG bar ([log_bar.py](log_bar.py)); this screen
is reached by `⏎` on an existing row. Why the edit form stays: an
existing row has an id, a version and possibly a completed reconciliation
freezing four of its fields, so the write is a PUT of just what changed; most
rows — every one the xlsx importer made — were never a typed line and have
nothing to round-trip; and retyping a line to fix one number is more work, not
less.

Reached by `⏎` on a row in Transactions. Sequence:
Date › Title › Amount › Account › Category › Hashtags › Note. `ctrl+s` PUTs
only the changed fields; a changed account also sends `reconciliation_id: null`,
so the move takes the row out of its reconciliation (`unassign_on_move`).
Saved, the note says `Saved. It left its reconciliation.` when the engine's
answer flags a part of the line as leaving one, and `Saved.` otherwise
(`moved_parts`) (contract: PUT /v1/transactions/{transaction_id}, "Response").
A hashtag set that names a real hashtag never carries the pending one: the
moment a real hashtag is added, the pending one leaves the `hashtags` line, and
the save sends only the real hashtags (`hashtags_to_send`, the same helper for
both); an emptied set sends `[]`, which the engine files under the pending
hashtag (contract: PUT /v1/transactions/{transaction_id}).

`⏎` on an emptied note empties it, and the save sends `description: ""`: the
engine stores `""` as an empty note and refuses `null` there as `NOT_NULL`
(contract: PUT /v1/transactions/{transaction_id}). Every field the form sends
is a value, never `null`, except `operation_code`, which `null` clears, and the
`reconciliation_id: null` a move adds; an empty date bar commits today, and an
emptied title is refused (`_title_given`).

On an opening balance (a row filed under @Opening) account, category and
hashtags show read-only and are never sent: the engine keeps such a row on its
account and in @Opening
(contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put"),
and it carries no hashtag, not even the pending one
(contract: PUT /v1/transactions/{transaction_id}). The form knows the row once
the reference lists load (`QuickAddRefs.opening`).

On a transaction whose account is archived only its categorisation changes
(contract: PUT /v1/transactions/{transaction_id}, "Archived accounts"): date,
title, amount and account show read-only and are never sent, at their current
value either, and the form opens on the first field left, category. A title that
is still empty stays editable, and its first value is sent once
(contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled");
reopened once filled, it is read-only like the rest. The form knows the account
is archived from the same accounts read (`QuickAddRefs.archived_accounts`); a
failed read leaves the form as on any row, and the engine judges the save.

On a part of a split transaction, the hint under the bar adds `changes every
part of the transaction` while the cursor is on date, title or account: the
engine writes those three onto every part of the bank line, in one go
(contract: "Transactions (Ledger)", "Bank lines"). The form knows the row is a
part from one `GET /v1/bank-lines/{bank_line_id}` read as it opens, the engine's
`part_count` above 1 (contract: GET /v1/bank-lines/{bank_line_id}). A failed
read leaves the hints as on any row; the save is the engine's either way.

`BankLineEditFormScreen` is this form on a bank line, `⏎` in the
reconciliations' "no batch" list: the bank's columns only. Date › Title ›
Operation › Amount › Account on a line never split; on a split line the amount
gives way to a read-only `Parts` section under the summary, each part's amount
and the line's total. The save is the same diffed PUT on one part; the engine
writes date, title, operation and account onto every part
(contract: PUT /v1/transactions/{transaction_id}, "Line fields"). On an archived
account's line every field is read-only except an empty title or operation
code, filled once, as above.

`enter` saves & advances · `tab` / `shift+tab` move between fields · `↑/↓`
move the suggestion highlight, or the field when there is no list · `ctrl+s`
submits. Sign explicit (− expense / + income); currency derived from the
account. The keymap is `form_bindings` in _form.py.
"""

import copy
from datetime import date as date_cls

from rich.console import Group, RenderableType
from rich.text import Text
from textual import work
from textual.widgets import Input

from expense import reads
from expense.dates import to_canonical_aware
from expense.errors import format_error
from expense.formatting import (
    bank_line_columns,
    bank_line_part_count,
    format_cents,
    resolve_name,
    signed_cents,
)
from expense.quickadd.money import amount_to_text, parse_amount
from expense.reads import hashtags_to_send, load_quickadd_refs
from expense.tui.screens._base import call_while_attached, screen_fetch_kwargs
from expense.tui.screens._form import FormScreen, form_bindings
from expense.tui.theme import ACCENT, AMOUNT_RULE, PALETTE
from expense.tui.widgets.cells import amount_cell
from expense.tui.widgets.picker import matching, suggestion_list

_LABELS = {
    "date": "DATE",
    "title": "TITLE",
    "amount": "AMOUNT",
    "operation": "OPERATION",
    "account": "ACCOUNT",
    "category": "CATEGORY",
    "hashtags": "HASHTAGS",
    "note": "NOTE",
}
_ENTITY = {"account", "category", "hashtags"}
_AMOUNTS = {"amount"}
_HINTS = {
    "date": "YYYY-MM-DD · enter to accept, or type a date",
    "title": "free text · enter to save",
    "amount": "signed decimal · − expense / + income · in the account's currency",
    "operation": "optional · the bank's operation number · empty clears it",
    "account": "pick an existing account · ↑↓ highlight · enter select",
    "category": "pick an existing category · ↑↓ highlight · enter select",
    "hashtags": "type a tag · ↑↓ highlight · enter adds & stays · empty enter = done (optional)",
    "note": "optional · enter saves · (ctrl+s anytime)",
}
# The fields a part of a split transaction shares with every other part, and
# what the hint adds on them.
_EVERY_PART = {"date", "title", "account"}
EVERY_PART_NOTE = "changes every part of the transaction"
# The fields an archived account's transaction never changes, and of them the
# two that may be filled while empty
# (contract: PUT /v1/transactions/{transaction_id}, "Archived accounts").
_FROZEN_ON_ARCHIVED = {"date", "title", "amount", "operation", "account"}
_FILLED_ONCE = {"title", "operation"}
# engine field name for each form key
_ENGINE_FIELD = {
    "date": "date",
    "title": "title",
    "amount": "amount_cents",
    "operation": "operation_code",
    "account": "account_id",
    "category": "category_id",
    "hashtags": "hashtag_ids",
    "note": "description",
}


def unassign_on_move(payload: dict, record: dict) -> None:
    """Make an account move take the row out of its reconciliation.

    A PUT that changes `account_id` on a row assigned to a draft reconciliation
    must say what happens to the assignment, or the engine refuses it
    (contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id}).
    So a payload whose `account_id` differs from the row's gains
    `reconciliation_id: None` — the move unassigns. An `account_id` equal to the
    row's is not a move and gains nothing, so the row keeps its reconciliation.
    A row in a completed reconciliation is still refused as `LOCKED`.

    Whether a part did leave its reconciliation is the engine's answer to say
    (`moved_parts`). Mutates `payload`; shared by the edit form and the ledger's
    bulk `b`.
    """
    if "account_id" in payload and payload["account_id"] != record.get("account_id"):
        payload["reconciliation_id"] = None


def moved_parts(answers: list[dict]) -> tuple[int, int]:
    """(parts moved, parts that left their reconciliation) across the answers
    of one or more `PUT /transactions/{id}`, each part counted once by its id.

    Every answer lists in `changed_parts` each part of the bank line whose line
    field the write changed, and flags `left_reconciliation` on a part that was
    in a reconciliation before and is in none or another after
    (contract: PUT /v1/transactions/{transaction_id}, "Response"). Moving both
    parts of a line lists both in the first answer and none in the second, so the
    move counts 2. Shared by the ledger's bulk `b` (its receipt) and the edit
    form (its note).
    """
    moved: set[object] = set()
    left: set[object] = set()
    for answer in answers:
        for entry in answer.get("changed_parts", []):
            key = entry["transaction"]["id"]
            moved.add(key)
            if entry["left_reconciliation"]:
                left.add(key)
    return len(moved), len(left)


class EditFormScreen(FormScreen):
    BINDINGS = form_bindings("Save")

    def __init__(self, *, record: dict, resource: str = "transactions") -> None:
        super().__init__()
        self._resource = resource
        self._record = record
        self._accounts: list = []
        self._categories: list = []
        self._hashtags: list = []
        self._pending_tag: str | None = None
        self._original: dict = {}
        self._left_reconciliation = False  # the save's answer flags a part as leaving
        self._split_part = False  # the engine reads this row's bank line as > 1 part

        self.crumb = ("Capture & ledger", "Transactions", "Edit")
        self._prefill(self._record)

    # ---- edit pre-fill ---------------------------------------------------
    def _prefill(self, rec: dict) -> None:
        self._values = {}
        self._display = {}
        date = (rec.get("date") or "")[:10]
        if date:
            self._values["date"] = self._display["date"] = date
        if rec.get("title"):
            self._values["title"] = self._display["title"] = rec["title"]
        if rec.get("amount_cents") is not None:
            self._values["amount"] = rec["amount_cents"]
            self._display["amount"] = format_cents(rec["amount_cents"])
        if rec.get("account_id"):
            self._values["account"] = rec["account_id"]
            self._display["account"] = rec["account_id"][:8]  # resolved once entities load
        if rec.get("category_id"):
            self._values["category"] = rec["category_id"]
            self._display["category"] = rec["category_id"][:8]
        tags = rec.get("hashtag_ids") or []
        if tags:
            self._values["hashtags"] = list(tags)
            # resolve_name: short-id placeholder until entities load, and a
            # null id renders "—" instead of TypeError-ing
            self._display["hashtags"] = " ".join("#" + resolve_name(t, {}) for t in tags)
        if rec.get("description"):
            self._values["note"] = self._display["note"] = rec["description"]
        # deep: the baseline never shares a list with `_values`, or a list changed
        # in place would change both and the edit diff would never see it.
        self._original = copy.deepcopy(self._values)
        # no client-side reconciliation locks: they rely on the engine's 422
        # (not reliably detectable from the row). The client locks are an
        # opening balance's account, category and hashtags, and an archived
        # account's frozen fields, both set in `_set_entities`.

    # ---- field sequence --------------------------------------------------
    def _sequence(self) -> list[str]:
        return ["date", "title", "amount", "account", "category", "hashtags", "note"]

    def _after_mount(self) -> None:
        self._load_entities()
        if self._record.get("bank_line_id"):
            self._load_bank_line()

    @work(thread=True, exclusive=True, group="bank_line")
    def _load_bank_line(self) -> None:
        """One read of the row's bank line, for the every-part note. Any failure
        leaves the form as on an unsplit row: the note is a hint, not a guard."""
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            line = reads.fetch_bank_line(
                cfg, self._record["bank_line_id"], **screen_fetch_kwargs(self.app)
            )
        except Exception:
            return
        if bank_line_part_count(line) > 1:
            call_while_attached(self, self._set_split_part)

    def _set_split_part(self) -> None:
        self._split_part = True
        self._refresh_view()  # a save in flight keeps its busy hint (`_refresh_view`)

    @work(thread=True, exclusive=True)
    def _load_entities(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            # the fetch + shaping is shared with the LOG bar; CATEGORY offers
            # the pick list, @Pendiente in it, as the ledger's bulk `c` does
            refs = load_quickadd_refs(cfg, **screen_fetch_kwargs(self.app))
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            self.app.call_from_thread(self.notify, format_error(exc), severity="error")
            return
        maps = (refs.account_names, refs.category_names, refs.hashtag_names)
        self.app.call_from_thread(
            self._set_entities,
            refs.accounts,
            refs.pickable_categories,
            refs.hashtags,
            maps,
            refs.opening,
            refs.pending_hashtag_id,
            refs.archived_accounts,
        )

    def _set_entities(
        self,
        accounts,
        categories,
        hashtags,
        maps,
        opening=None,
        pending_tag=None,
        archived=frozenset(),
    ) -> None:
        self._accounts, self._categories, self._hashtags = accounts, categories, hashtags
        self._pending_tag = pending_tag
        self._acc_names, self._cat_names, self._tag_names_map = maps
        if opening is not None and self._record.get("category_id") == opening:
            # an opening balance: the three fields it can never change show
            # read-only, and `_edit_payload` skips locked fields
            self._locked |= {"account", "category", "hashtags"}
        if self._record.get("account_id") in archived:
            self._locked |= self._frozen_on_archived()
        if self._key in self._locked:
            self._current = self._first_editable()
            self._refresh_bar()
        # resolve pre-filled ids → names.
        # resolve_name (shared) renders a null reference as "—" instead of
        # crashing on None[:8]
        if "account" in self._values:
            self._display["account"] = resolve_name(self._values["account"], self._acc_names)
        if "category" in self._values:
            self._display["category"] = resolve_name(self._values["category"], self._cat_names)
        if self._values.get("hashtags"):
            self._display["hashtags"] = " ".join(
                "#" + resolve_name(t, self._tag_names_map) for t in self._values["hashtags"]
            )
        self._recompute(self.query_one("#bar", Input).value)
        self._refresh_view()

    def _frozen_on_archived(self) -> set[str]:
        """The fields of this form an archived account's transaction keeps as
        they are: every frozen one, but a title or operation code still empty
        (`_original` holds no value for it), which may be filled once."""
        return {
            key
            for key in self._sequence()
            if key in _FROZEN_ON_ARCHIVED
            and not (key in _FILLED_ONCE and not self._original.get(key))
        }

    # ---- FormScreen hooks --------------------------------------------------
    def _label(self, key: str) -> str:
        return _LABELS[key]

    def _hint_for(self, key: str) -> str:
        return _HINTS.get(key, "")

    def _hint_line(self, key: str) -> Text:
        if not (self._split_part and key in _EVERY_PART):
            return super()._hint_line(key)
        return Text.assemble((f"{self._hint_for(key)} · ", "dim"), (EVERY_PART_NOTE, ACCENT))

    def _suggests(self, key: str) -> bool:
        return key in _ENTITY

    def _bar_value(self, key: str) -> str:
        if key in _AMOUNTS and key in self._values:
            return amount_to_text(self._values[key])
        if key in ("date", "title", "note"):
            return str(self._values.get(key, "") or "")
        return ""  # entity fields open empty; `_recompute` places the highlight

    # ---- suggestions -----------------------------------------------------
    def _recompute_suggestions(self, text: str) -> None:
        # historic name kept — test drivers (and muscle memory) call it directly
        self._recompute(text)

    def _recompute(self, text: str) -> None:
        key = self._key
        needle = text.strip()
        if key == "account":
            pool = matching(self._accounts, needle)
        elif key == "category":
            pool = matching(self._categories, needle)
        elif key == "hashtags":
            chosen = set(self._values.get("hashtags", []))
            pool = matching(self._hashtags, needle.lstrip("#"), chosen=chosen)
        else:
            pool = []
        self._suggestions = pool
        self._suggest_idx = 0
        if key in ("account", "category") and not needle:
            # an empty bar starts on what the line holds, so `⏎` keeps it
            ids = [ent[0] for ent in pool]
            if self._values.get(key) in ids:
                self._suggest_idx = ids.index(self._values[key])

    def _picked(self):
        return self._suggestions[self._suggest_idx] if self._suggestions else None

    # ---- commit ----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        key = self._key
        text = self.query_one("#bar", Input).value.strip()

        if key == "date":
            self._values["date"] = text or date_cls.today().isoformat()
            self._display["date"] = self._values["date"]
            self._advance()
        elif key == "title":
            if not self._title_given(text):
                return
            self._values["title"] = self._display["title"] = text
            self._advance()
        elif key == "amount":
            cents = parse_amount(text)
            if cents is None:
                self.notify("Amount: a signed decimal, e.g. -99.92", severity="error")
                return
            # Mid-form ergonomics guard; mirrors the engine's 422 on a zero
            # amount_cents (contract: POST /v1/transactions, "Validation").
            # Deliberately kept client-side.
            if cents == 0:
                self.notify("Amount must be non-zero.", severity="error")
                return
            self._values["amount"] = cents
            self._display["amount"] = format_cents(cents)
            self._advance()
        elif key in ("account", "category"):
            picked = self._picked()
            if picked is None:
                self.notify(f"No {key} matches “{text}”.", severity="error")
                return
            self._values[key] = picked[0]
            self._display[key] = picked[1]
            self._advance()
        elif key == "hashtags":
            self._commit_hashtag(text)
            return
        elif key == "note":
            # an emptied bar empties the note; the save sends it as `""`
            if text:
                self._values["note"] = self._display["note"] = text
            else:
                self._values.pop("note", None)
                self._display.pop("note", None)
            self.action_submit()  # note is last → enter submits
            return
        self._refresh_view()

    def _commit_hashtag(self, text: str) -> None:
        if not text:
            self._advance()
            self._refresh_view()
            return
        picked = self._picked()
        if picked is None:
            self.notify(f"No hashtag matches “{text}”.", severity="error")
            return
        # what the form lists is what the save sends: once a real hashtag is
        # in, the pending one leaves the list
        picked_ids = [*self._values.get("hashtags", []), picked[0]]
        self._values["hashtags"] = hashtags_to_send(picked_ids, self._pending_tag)
        self._display["hashtags"] = " ".join("#" + n for n in self._tag_display_names())
        self.query_one("#bar", Input).value = ""
        self._recompute("")
        self._refresh_view()

    def _tag_display_names(self) -> list[str]:
        names = getattr(self, "_tag_names_map", {}) or dict(self._hashtags)
        return [resolve_name(i, names) for i in self._values.get("hashtags", [])]

    # ---- render ----------------------------------------------------------
    def _suggest_renderable(self) -> RenderableType:
        if self._key not in _ENTITY:
            return Text("")
        labels = [f"{ent[1]}{'  ' + ent[2] if len(ent) > 2 else ''}" for ent in self._suggestions]
        return suggestion_list(labels, self._suggest_idx)

    # ---- submit ----------------------------------------------------------
    def _submit_request(self) -> tuple[str, str, dict, str] | None:
        payload = self._edit_payload()
        if not payload:
            self.notify("No changes to save.")
            return None
        unassign_on_move(payload, self._record)
        return ("PUT", f"/{self._resource}/{self._record['id']}", payload, "Saving…")

    def _edit_payload(self) -> dict:
        payload: dict = {}
        for key, engine_field in _ENGINE_FIELD.items():
            if key in self._locked or self._values.get(key) == self._original.get(key):
                continue
            new = self._values.get(key)
            if key == "date":
                # never empty: an empty date bar commits today
                payload["date"] = to_canonical_aware(new)
            elif key == "note":
                # `""` empties the note; `null` is refused as `NOT_NULL`
                # (contract: PUT /v1/transactions/{transaction_id})
                payload["description"] = new or ""
            elif key == "operation":
                # `null` clears the line's operation code
                # (contract: PUT /v1/transactions/{transaction_id})
                payload["operation_code"] = new or None
            elif key == "hashtags":
                tags = hashtags_to_send(new or [], self._pending_tag)
                if tags != (self._original.get("hashtags") or []):
                    payload["hashtag_ids"] = tags
            else:
                payload[engine_field] = new
        return payload

    def _answered(self, body: dict) -> None:
        # the note reads the engine's answer, never the row as read before the save
        self._left_reconciliation = moved_parts([body])[1] > 0

    def _done(self) -> None:
        left = self._left_reconciliation
        self.notify("Saved. It left its reconciliation." if left else "Saved.")
        self.dismiss(True)  # a cancel dismisses with None: the caller reloads only on True


# ---- the Edit form on a bank line: `⏎` in "no batch" ----------------------
#: The line under a split line's total, as pane 2e C2 draws it.
PARTS_NOTE = "the parts must add up to the total · s in the ledger splits it again to change them"


def parts_section(line: dict) -> Group:
    """A split line's `Parts`, read-only: each part's amount, signed by
    `signed_cents`, then a rule and the line's own `net_cents` as the total
    (`bank_line_columns`); the app adds nothing up. The amounts are
    right-aligned under one another, the rule as wide as the widest plus one,
    and `total` sits at the left of the total's line."""
    parts = [p for p in (line.get("parts") or []) if isinstance(p, dict)]
    amounts = [format_cents(signed_cents(p)) for p in parts]
    total = format_cents(bank_line_columns(line)[3])
    widest = max(len(a) for a in [*amounts, total])
    width = widest + 12
    lines = [Text.assemble(("Parts", "bold"), ("  read-only", "dim"))]
    lines += [Text(a.rjust(width), style="dim") for a in amounts]
    lines.append(Text(("─" * (widest + 1)).rjust(width), style="dim"))
    lines.append(Text("total" + total.rjust(width - len("total")), style="dim"))
    lines.append(Text(PARTS_NOTE, style="dim"))
    return Group(*lines)


class BankLineEditFormScreen(EditFormScreen):
    """The Edit form on a bank line in the "no batch" list: the bank's columns
    only (pane 2e C2 of expense-world-bank-lines-whole.html).

    Every value comes from the line the list already holds, so the form reads
    no line: the day and title off its first part, its `operation_code` and
    `account_id`, and on a line never split its one part's amount, signed by
    `signed_cents`. The heading is the line as the list shows it, its title and
    its `net_cents` with the account's currency. A split line (`part_count`
    above 1) shows no amount field: its parts' amounts and the total stand
    read-only under the summary (`parts_section`). No category, hashtags or
    note: those are the ledger's.

    The save is the Edit form's: one PUT on the line's first part, carrying
    only the fields changed; date, title, operation and account reach every
    part (contract: PUT /v1/transactions/{transaction_id}, "Line fields").
    """

    def __init__(self, *, line: dict, currency: str | None = None) -> None:
        self._line = line
        self._currency = currency
        self._split = bank_line_part_count(line) > 1
        first = (line.get("parts") or [{}])[0]
        record = {
            **first,
            "amount_cents": signed_cents(first),
            "account_id": line.get("account_id") or first.get("account_id"),
            "operation_code": line.get("operation_code"),
        }
        super().__init__(record=record)
        self.crumb = ("Capture & ledger", "Reconciliations", "Edit")

    def _prefill(self, rec: dict) -> None:
        super()._prefill(rec)
        shown = set(self._sequence())
        self._values = {k: v for k, v in self._values.items() if k in shown}
        self._display = {k: v for k, v in self._display.items() if k in shown}
        if rec.get("operation_code"):
            self._values["operation"] = self._display["operation"] = rec["operation_code"]
        self._original = copy.deepcopy(self._values)

    def _sequence(self) -> list[str]:
        if self._split:
            return ["date", "title", "operation", "account"]
        return ["date", "title", "operation", "amount", "account"]

    def _after_mount(self) -> None:
        self._load_entities()  # the line is in hand: no bank-line read

    def _heading(self) -> RenderableType:
        _day, title, _operation, net_cents = bank_line_columns(self._line)
        head = Text(title or "(untitled)", style="bold")
        head.append("  ·  ", style="dim")
        figure = amount_cell(net_cents, PALETTE, AMOUNT_RULE)
        head.append_text(figure if isinstance(figure, Text) else Text(str(figure)))
        if self._currency:
            head.append(f" {self._currency}", style="dim")
        return head

    def _bar_value(self, key: str) -> str:
        if key == "operation":
            return str(self._values.get("operation") or "")
        return super()._bar_value(key)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Textual calls the handler of every class in the MRO; this one calls the
        # Edit form's itself, so the message stops here and `⏎` moves one line
        if event is not None:
            event.prevent_default()
        if self._key != "operation":
            super().on_input_submitted(event)
            return
        text = self.query_one("#bar", Input).value.strip()
        self._values["operation"] = text or None
        if text:
            self._display["operation"] = text
        else:
            self._display.pop("operation", None)
        self._advance()

    def _summary_renderable(self) -> RenderableType:
        summary = super()._summary_renderable()
        if not self._split:
            return summary
        return Group(summary, Text(""), parts_section(self._line))
