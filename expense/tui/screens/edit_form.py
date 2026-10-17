"""Edit a transaction — the bar-cycle form.

One input bar cycles through fields; a summary fills below. Entity fields
(account/category/hashtags) show a live-filtered suggestion list — pick
existing entities only.

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
A hashtag set that names a real hashtag never carries the pending one: the
moment a real hashtag is added, the pending one leaves the `hashtags` line, and
the save sends only the real hashtags (`hashtags_to_send`, the same helper for
both); an emptied set sends `[]`, which the engine files under the pending
hashtag (contract: PUT /v1/transactions/{transaction_id}).

On an opening balance (a row filed under @Opening) account and category show
read-only and are never sent: the engine keeps such a row on its account and in
@Opening (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put").
The form knows the row once the reference lists load (`QuickAddRefs.opening`).

`enter` saves & advances · `tab` / `shift+tab` move between fields · `↑/↓`
move the suggestion highlight, or the field when there is no list · `ctrl+s`
submits. Sign explicit (− expense / + income); currency derived from the
account. The keymap is `form_bindings` in _form.py.
"""

import copy
from datetime import date as date_cls

from rich.console import RenderableType
from rich.text import Text
from textual import work
from textual.widgets import Input

from expense.dates import to_canonical_aware
from expense.errors import format_error
from expense.formatting import format_cents, resolve_name
from expense.quickadd.money import amount_to_text, parse_amount
from expense.quickadd.names import matches
from expense.reads import hashtags_to_send, load_quickadd_refs
from expense.tui.screens._base import screen_fetch_kwargs
from expense.tui.screens._form import FormScreen, form_bindings
from expense.tui.widgets.picker import suggestion_list

_LABELS = {
    "date": "DATE",
    "title": "TITLE",
    "amount": "AMOUNT",
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
    "account": "pick an existing account · ↑↓ highlight · enter select",
    "category": "pick an existing category · ↑↓ highlight · enter select",
    "hashtags": "type a tag · ↑↓ highlight · enter adds & stays · empty enter = done (optional)",
    "note": "optional · enter saves · (ctrl+s anytime)",
}
# engine field name for each form key
_ENGINE_FIELD = {
    "date": "date",
    "title": "title",
    "amount": "amount_cents",
    "account": "account_id",
    "category": "category_id",
    "hashtags": "hashtag_ids",
    "note": "description",
}


def unassign_on_move(payload: dict, record: dict) -> bool:
    """Make an account move take the row out of its reconciliation.

    A PUT that changes `account_id` on a row assigned to a draft reconciliation
    must say what happens to the assignment, or the engine refuses it
    (contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id}).
    So a payload whose `account_id` differs from the row's gains
    `reconciliation_id: None` — the move unassigns. An `account_id` equal to the
    row's is not a move and gains nothing, so the row keeps its reconciliation.
    A row in a completed reconciliation is still refused as `LOCKED`.

    Returns True when the row was assigned and this write takes it out — the
    caller's note says so. Mutates `payload`; shared by the edit form and the
    ledger's bulk `b`.
    """
    if "account_id" not in payload or payload["account_id"] == record.get("account_id"):
        return False
    payload["reconciliation_id"] = None
    return record.get("reconciliation_id") is not None


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
        self._leaves_reconciliation = False

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
        # (not reliably detectable from the row). The one client lock is an
        # opening balance's account and category, set in `_set_entities`.

    # ---- field sequence --------------------------------------------------
    def _sequence(self) -> list[str]:
        return ["date", "title", "amount", "account", "category", "hashtags", "note"]

    def _after_mount(self) -> None:
        self._load_entities()

    @work(thread=True, exclusive=True)
    def _load_entities(self) -> None:
        from expense import config as config_module

        try:
            cfg = config_module.ensure_loaded()
            # the fetch + shaping is shared with the LOG bar, so both
            # quick-add surfaces suggest from exactly the same pool
            refs = load_quickadd_refs(cfg, **screen_fetch_kwargs(self.app))
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            self.app.call_from_thread(self.notify, format_error(exc), severity="error")
            return
        maps = (refs.account_names, refs.category_names, refs.hashtag_names)
        self.app.call_from_thread(
            self._set_entities,
            refs.accounts,
            refs.categories,
            refs.hashtags,
            maps,
            refs.opening,
            refs.pending_hashtag_id,
        )

    def _set_entities(
        self, accounts, categories, hashtags, maps, opening=None, pending_tag=None
    ) -> None:
        self._accounts, self._categories, self._hashtags = accounts, categories, hashtags
        self._pending_tag = pending_tag
        self._acc_names, self._cat_names, self._tag_names_map = maps
        if opening is not None and self._record.get("category_id") == opening:
            # an opening balance: the two fields it can never change show
            # read-only, and `_edit_payload` skips locked fields
            self._locked |= {"account", "category"}
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

    # ---- FormScreen hooks --------------------------------------------------
    def _label(self, key: str) -> str:
        return _LABELS[key]

    def _hint_for(self, key: str) -> str:
        return _HINTS.get(key, "")

    def _suggests(self, key: str) -> bool:
        return key in _ENTITY

    def _bar_value(self, key: str) -> str:
        if key in _AMOUNTS and key in self._values:
            return amount_to_text(self._values[key])
        if key in ("date", "title", "note"):
            return str(self._values.get(key, "") or "")
        return ""  # entity fields re-pick from scratch

    # ---- suggestions -----------------------------------------------------
    def _recompute_suggestions(self, text: str) -> None:
        # historic name kept — test drivers (and muscle memory) call it directly
        self._recompute(text)

    def _recompute(self, text: str) -> None:
        key = self._key
        needle = text.strip()
        if key == "account":
            pool = [(i, n, c) for (i, n, c) in self._accounts if matches(needle, n)]
        elif key == "category":
            pool = [(i, n) for (i, n) in self._categories if matches(needle, n)]
        elif key == "hashtags":
            needle = needle.lstrip("#")
            chosen = set(self._values.get("hashtags", []))
            pool = [(i, n) for (i, n) in self._hashtags if matches(needle, n) and i not in chosen]
        else:
            pool = []
        self._suggestions = pool
        self._suggest_idx = 0

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
            if not text:
                self.notify("Title is required.", severity="error")
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
            if text:
                self._values["note"] = self._display["note"] = text
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
        self._leaves_reconciliation = unassign_on_move(payload, self._record)
        return ("PUT", f"/{self._resource}/{self._record['id']}", payload, "Saving…")

    def _edit_payload(self) -> dict:
        payload: dict = {}
        for key, engine_field in _ENGINE_FIELD.items():
            if key in self._locked or self._values.get(key) == self._original.get(key):
                continue
            new = self._values.get(key)
            if key == "date":
                payload["date"] = to_canonical_aware(new) if new else None
            elif key == "note":
                payload["description"] = new or None
            elif key == "hashtags":
                tags = hashtags_to_send(new or [], self._pending_tag)
                if tags != (self._original.get("hashtags") or []):
                    payload["hashtag_ids"] = tags
            else:
                payload[engine_field] = new
        return payload

    def _done(self) -> None:
        left = self._leaves_reconciliation
        self.notify("Saved. It left its reconciliation." if left else "Saved.")
        self.dismiss(True)  # a cancel dismisses with None: the caller reloads only on True
