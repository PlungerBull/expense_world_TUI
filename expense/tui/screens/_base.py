"""SectionScreen — the shared base for every data-backed section screen.

Owns the breadcrumb header, the bounded content card, the worker-backed fetch
(so the UI never blocks), and loading/error states. Subclasses supply only:

    crumb  : tuple[str, ...]          # breadcrumb trail after EXPENSE WORLD
    fetch()                           # runs in a worker thread, returns data
    build(data) -> list[Widget]       # the widgets to show inside the card

`r` refreshes; `escape` pops back to the menu.
"""

import asyncio
import weakref
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.types import NoActiveAppError
from textual.widget import Widget
from textual.widgets import LoadingIndicator, Static
from textual.worker import get_current_worker

from expense.errors import format_error
from expense.formatting import (
    bank_line_columns,
    bank_line_part_count,
    format_cents_with_plus,
    format_short_date,
    name_or_unnamed,
    title_or_untitled,
)
from expense.reads import DEFAULT_PAGE_ROWS
from expense.tui.screens.help import HelpBindingMixin
from expense.tui.screens.modals import ConfirmModal
from expense.tui.widgets.footer import FittingFooter
from expense.tui.widgets.header import Breadcrumb
from expense.tui.widgets.refusal import as_markup, toast

if TYPE_CHECKING:
    from expense.config import Config


def screen_fetch_kwargs(app) -> dict:
    """The standard TUI read kwargs: verbosity off the app."""
    return dict(verbose=app._verbose)


def relabel(screen: Screen, key: str, description: str, action: str | None = None) -> None:
    """Give one of the screen's own bindings a footer word decided at run time
    (`Cancel both`, `Import 9 rows`, the LOG bar's `Upload`). The screen's
    binding map is its own copy, so this touches no other screen. With `action`, only
    the binding of that action on the key is relabelled."""
    bindings = screen._bindings.key_to_bindings.get(key)
    if bindings:
        screen._bindings.key_to_bindings[key] = [
            replace(b, description=description) if action in (None, b.action) else b
            for b in bindings
        ]
        screen.refresh_bindings()


def still_attached(node: Widget) -> bool:
    """On the UI thread: `node` is still in a running app. `is_attached` is False once
    the app is exiting or the node is unlinked, and `_pruning` is set on a node and all
    its children the moment their removal starts — the same pair Textual's own `Widget`
    checks before touching a node it may be removing. A hand-back that is a coroutine
    asks this again after every `await` (the lock, a removal, a mount) that work on the
    node's widgets follows, since the screen can be popped or the app can quit while it
    waits, and returns when it is False: the work after the wait is dropped, an error
    raised while the node is still here is not."""
    return node.is_attached and not node._pruning


def call_while_attached(
    node: Widget,
    callback: Callable,
    *args,
    if_left: Callable[[], None] | None = None,
    app: "App | None" = None,
    **kwargs,
) -> None:
    """From a thread worker of `node`: run `callback(*args, **kwargs)` on the UI thread,
    unless `node` has left the app by the time it would run (then the answer is
    dropped, or, when `if_left` is given, `if_left()` runs instead on the UI thread:
    it must not touch `node`'s widgets; only a write's ending uses it, and passes
    `app` too, since a node that has left cannot name it). The TUI's workers hand
    back only through this, besides the app's own rate check
    (guard: tests/unit/test_suite_hygiene.py).

    A thread worker cannot be interrupted, so a read that was in flight when
    its screen was popped, or when the app quit, still lands. Textual cancels
    a node's workers only on its Unmount, which comes *after* its children are
    pruned, so neither `is_cancelled` nor a check made in the worker thread
    closes the gap: the callback would query widgets that are already gone
    (`NoMatches`). The check (`still_attached`) runs on the UI thread, at the moment
    the callback would; a coroutine callback asks it again after each of its own waits.
    """

    if app is None:
        try:
            app = node.app
        except NoActiveAppError:
            return  # a node that has left the app cannot name it: nothing to hand to

    def guarded():
        if still_attached(node):
            return callback(*args, **kwargs)
        # `is_attached` is also False once the app is quitting (Textual's private
        # `_exit`, the one flag it checks itself): then nothing is shown or sent.
        if if_left is not None and not app._exit:
            if_left()
        return None

    app.call_from_thread(guarded)


class NewestReadMixin:
    """Anything that starts reads which can overlap: each read starts with `_start_read`,
    and its hand-backs run on the UI thread through `_if_newest` (or check `_is_newest`
    themselves, when they are coroutines), so a read a newer one replaced paints
    nothing and changes no state."""

    _load_generation = 0

    def _start_read(self) -> int:
        """The generation of a read that is starting; every older one is now stale."""
        self._load_generation += 1
        return self._load_generation

    def _is_newest(self, generation: int) -> bool:
        return generation == self._load_generation

    def _if_newest(self, generation: int, hand_back: Callable, *args, **kwargs) -> None:
        """UI thread: a hand-back of a read a newer one has replaced is dropped."""
        if self._is_newest(generation):
            hand_back(*args, **kwargs)


@dataclass(frozen=True)
class LeftBehind:
    """How a write is finished if its screen has left before the engine answers
    (`EngineWriteMixin`): `first_line` is a refusal's first line, what did not
    happen; `note` ends that refusal with one more line, dim: a string, or a function
    of the failure (None: no line); `success_from` makes the success words of the
    engine's answer, where they depend on it (None from it: a success that shows nothing);
    `part` makes the write one of several
    that a `SaveReport` reports as one message, in place of its own. Touches no widget."""

    first_line: str
    note: "str | Callable[[Exception | None], str | None] | None" = None
    success_from: Callable[[dict], str | None] | None = None
    part: "ReportedPart | None" = None  # set: the write is one part of a `SaveReport`


class SaveReport:
    """One message for a save that is several writes, shown when the last answers after
    its screen has left. Each write is a `part` (`SaveReport.part`, its `LeftBehind.part`)
    and each answer, from before the screen left or after, is recorded in the order sent.
    Saved whole, the message is `saved`; else an error toast of 10 seconds, titled
    `all_refused` when every part was refused and `some_refused` when not, one line per
    part (its words, then the engine's words under a refused one), and a dim last line
    from `closing`, given each refused part's `name` and the failure that refused it
    (None from it: no last line). Touches no widget."""

    def __init__(
        self,
        parts: int,
        some_refused: str,
        all_refused: str,
        closing: Callable[[list[tuple[str, Exception | None]]], str | None],
        saved: str = "Saved.",
    ) -> None:
        self.parts = parts
        self._titles = (some_refused, all_refused)
        self._closing = closing
        self._saved = saved
        self._answers: list[tuple[ReportedPart, str | None, Exception | None]] = []

    def part(self, name: str, saved: str, refused: str) -> "ReportedPart":
        """A write of this save: `name` is what a refusal leaves to do again, `saved` and
        `refused` the lines for its two endings."""
        return ReportedPart(self, name, saved, refused)

    @property
    def complete(self) -> bool:
        return len(self._answers) >= self.parts

    @property
    def landed(self) -> bool:
        """At least one part was saved."""
        return any(error is None for _, error, _ in self._answers)

    @property
    def failures(self) -> list[Exception | None]:
        """The failure of each part that did not save."""
        return [failure for _, error, failure in self._answers if error is not None]

    def record(self, part: "ReportedPart", error: str | None, failure: Exception | None) -> None:
        """One write's answer: None when it was saved, else the engine's words and its failure."""
        self._answers.append((part, error, failure))

    def show(self, app: "App") -> None:
        refused = [
            (part.name, failure) for part, error, failure in self._answers if error is not None
        ]
        if not refused:
            toast(app, self._saved)
            return
        lines: list[tuple[str, str]] = []
        for part, error, _ in self._answers:
            if error is None:
                lines.append((part.saved, ""))
            else:
                lines += [(part.refused, ""), (error, "")]
        closing = self._closing(refused)
        if closing is not None:
            lines.append((closing, "dim"))
        app.notify(
            as_markup(lines),
            title=self._titles[len(refused) == self.parts],
            severity="error",
            timeout=10,
            markup=True,
        )


@dataclass(frozen=True)
class ReportedPart:
    """One write of a `SaveReport`; `record` is called with its answer: None when it
    was saved, else the engine's words and the failure they came from."""

    report: SaveReport
    name: str
    saved: str
    refused: str

    def record(self, error: str | None, failure: Exception | None = None) -> None:
        self.report.record(self, error, failure)


@dataclass
class _QueuedWrite:
    method: str
    path: str
    json_body: dict | None
    success: str
    on_success: Callable[[], None] | None
    on_error: Callable[[str], None] | None
    on_response: Callable[[dict], None] | None = None
    config: "Config | None" = None
    error_text: Callable[[Exception], str] = format_error
    on_failure: Callable[[Exception], None] | None = None
    left_behind: LeftBehind | None = None  # set: finished and shown if the screen has left


def app_writers(app: "App") -> "weakref.WeakSet[EngineWriteMixin]":
    """The screens that have sent a write through `run_write` on this app, left ones
    included (a screen that has left is not in the app's screen stack). Weak: a screen
    with a write in flight is held by its worker, an open one by the stack."""
    # `setdefault` on the instance dict creates the set atomically, as `counted_save`
    # needs from a worker thread
    return app.__dict__.setdefault("_write_screens", weakref.WeakSet())


@contextmanager
def counted_save(app: "App") -> Iterator[None]:
    """From a thread worker that writes without `run_write` (a batch, a run of PUTs, an
    import's apply): the whole run is one save in `pending_writes` while the block runs,
    whatever screen it was started from. The block holds the worker's hand-backs too (they
    block the thread until they have run), so the save is counted until its ending is
    shown. Held only for the block, so nothing is kept."""
    token = object()
    saves = app.__dict__.setdefault("_counted_saves", set())
    saves.add(token)
    try:
        yield
    finally:
        saves.discard(token)


def pending_writes(app: "App") -> int:
    """The one count of the saves on this app that are sent and not answered, or waiting
    to be sent, across every screen, left ones included (`EngineWriteMixin.saves_pending`),
    and the runs that joined through `counted_save`. A save of several writes (a
    `SaveReport`, a batch, a run of PUTs) counts once."""
    saves: set[int] = set()
    for screen in list(app_writers(app)):
        saves.update(id(save) for save in screen.saves_pending())
    return len(saves) + len(app.__dict__.get("_counted_saves", ()))


class EngineWriteMixin:
    """Engine writes off the UI thread — one at a time, in order, per screen.

    Shared by SectionScreen and the bar-cycle form screens (which subclass
    plain Screen). `run_write` appends to a per-screen FIFO and exactly one
    request is in flight at any moment: thread workers cancel cooperatively,
    so `exclusive=True` alone never serialized overlapping writes.
    Success/error callbacks land on the UI thread; without
    callbacks, errors notify a "Failed" toast and success runs `_after_write`.
    Idempotency + error envelope come from the client. The `engine-write`
    worker group keeps loads/theme changes from ever cancelling a write.

    A failed write **drops the queued remainder** — those intents were decided
    against a screen state the engine just contradicted; the error callback
    typically resyncs. Why, with the rejected alternatives: docs/decisions.md
    "TUI writes: FIFO queue in EngineWriteMixin, error drops the queue".

    **After the screen has left.** A write that carries `left_behind` (a
    `LeftBehind`: the refused message's first line and more) is still answered
    once its screen is gone:
    success toasts `success`, a refusal toasts `error_text`'s words titled
    its `first_line` for 10 seconds, both on the app, touching no widget of the
    left screen. The writes still queued behind it are then sent in order, each
    ending shown the same way, a refusal stopping none of them (the screen that
    would have resynced is gone). Textual refuses to start a worker of an
    unmounted node, so those sends run as thread workers of the *app*
    (`App.run_worker`, same `engine-write` group); the queue itself is plain
    state on the screen object, which outlives its mount. Writes that are parts of a
    `SaveReport` show no message of their own: the report's, when the last answers. A write with no
    `left_behind` is dropped when its answer lands after the screen has left,
    and nothing queued behind it is sent.
    """

    _write_queue: deque[_QueuedWrite] | None = None  # lazily created; UI-thread only
    _write_inflight: bool = False
    _write_current: _QueuedWrite | None = None  # the write in flight; UI-thread only
    _writes_answered = 0  # writes answered so far; a read stamps the count it started at

    def run_write(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        success: str = "Done.",
        on_success: Callable[[], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_response: Callable[[dict], None] | None = None,
        config: "Config | None" = None,
        error_text: Callable[[Exception], str] = format_error,
        on_failure: Callable[[Exception], None] | None = None,
        left_behind: LeftBehind | None = None,
    ) -> _QueuedWrite:
        """Queue one engine write and return it. `on_response` receives the engine's own body
        (before `on_success`) for the callers that need it: a `complete`
        carries a `warnings` envelope nothing else can reconstruct. Opt-in, so
        the callbackless callsites are untouched — decisions.md "The TUI sees
        the response body only where it asks for it".

        `config` sends the write with that engine address and key instead of the
        saved settings file — the setup screen's, whose settings are not saved
        until the engine has accepted them. `error_text` turns a failure into
        the words `on_error` (or the toast) gets; the shared `format_error`
        unless a screen needs the engine's words without its hints.
        `on_failure` receives the failure itself instead of `on_error`'s words,
        for a screen that lays a refusal out by its keys (the Edit form
        names each refused part by its number). `left_behind` opts the write in
        to being finished after its screen has left (`LeftBehind`, class docstring)."""
        if self._write_queue is None:
            self._write_queue = deque()
        app_writers(self.app).add(self)  # type: ignore[attr-defined]
        item = _QueuedWrite(
            method,
            path,
            json_body,
            success,
            on_success,
            on_error,
            on_response,
            config,
            error_text,
            on_failure,
            left_behind,
        )
        self._write_queue.append(item)
        self._pump_writes()
        return item

    def saves_pending(self) -> list[object]:
        """What this screen has sent and not had answered, or has queued: one entry per
        write, or one per `SaveReport` for the writes that are its parts. On a screen
        that has left, only the writes carrying a `LeftBehind` count, up to the first
        that does not: it and every write behind it are dropped."""
        writes = self.writes_unanswered()
        if not (self.is_attached and not self._pruning):  # type: ignore[attr-defined]
            kept = []
            for write in writes:
                if write.left_behind is None:
                    break
                kept.append(write)
            writes = kept
        return [
            w.left_behind.part.report if w.left_behind and w.left_behind.part else w for w in writes
        ]

    def dismiss(self, result: Any = None) -> Any:
        """Close this screen; while the quit question is on top, once it is answered."""
        close = super().dismiss  # type: ignore[misc]
        app = self.app  # type: ignore[attr-defined]
        if app.quit_question_open:
            app.after_quit_question(lambda: close(result))
            return None
        return close(result)

    def _pump_writes(self) -> None:
        if self._write_inflight or not self._write_queue:
            return
        self._write_inflight = True
        self._write_current = self._write_queue.popleft()
        self._execute_write(self._write_current)

    def writes_unanswered(self) -> list[_QueuedWrite]:
        """The write in flight, then every queued one, in order: the one
        source of truth for what this screen has sent or will send. A write is
        out of it before its callbacks run."""
        current = [self._write_current] if self._write_current is not None else []
        return [*current, *(self._write_queue or ())]

    def _writes_dropped(self, failed: _QueuedWrite, dropped: list[_QueuedWrite]) -> None:
        """Hook: `failed` was refused and `dropped` (maybe empty) were the
        writes queued behind it, now never sent. Runs after `failed`'s own
        callback. A screen whose list showed a dropped write before it was
        sent reads that list again here."""

    @work(thread=True, group="engine-write")
    def _execute_write(self, item: _QueuedWrite) -> None:
        self._send_write(item, self.app)

    def _send_write(self, item: _QueuedWrite, app: "App") -> None:
        """Thread side: send `item`, then hand the answer to the UI thread. `app` is
        named by the caller: a screen that has left cannot name it."""
        # Imports stay function-local: the test fixtures patch these module
        # attributes, and only a lazy lookup sees the patch.
        from expense import config as config_module
        from expense.http import ExpenseClient

        error: str | None = None
        body: dict | None = None
        failure: Exception | None = None
        try:
            cfg = item.config or config_module.ensure_loaded()
            with ExpenseClient(cfg, verbose=app._verbose) as client:
                if item.method == "POST":
                    body = client.post(item.path, json_body=item.json_body)
                elif item.method == "PUT":
                    body = client.put(item.path, json_body=item.json_body)
                elif item.method == "DELETE":
                    body = client.delete(item.path)
                else:
                    raise ValueError(f"unsupported write method: {item.method}")
        except Exception as exc:
            error = item.error_text(exc)
            failure = exc
        call_while_attached(
            self,
            self._write_finished,
            item,
            error,
            body,
            failure,
            app=app,
            if_left=(
                None
                if item.left_behind is None
                else lambda: self._write_finished_after_leaving(app, item, error, body, failure)
            ),
        )

    def _write_finished_after_leaving(
        self,
        app: "App",
        item: _QueuedWrite,
        error: str | None,
        body: dict | None = None,
        failure: Exception | None = None,
    ) -> None:
        """UI thread, the screen gone: show how `item` ended on the app, then send
        the next queued write (and so on). A queued write with no `left_behind`
        is never sent, and nothing behind it."""
        self._writes_answered += 1
        self._write_inflight = False
        self._write_current = None
        behind = item.left_behind
        assert behind is not None  # only a write that opted in is finished here
        if behind.part is not None:  # one message for the whole save, at its last answer
            behind.part.record(error, failure)
            if behind.part.report.complete:
                behind.part.report.show(app)
            self._send_next_after_leaving(app)
            return
        note = behind.note
        if callable(note):
            note = note(failure)
        if error is None:
            words = (
                behind.success_from(body or {}) if behind.success_from is not None else item.success
            )
            if words is not None:
                toast(app, words)
        elif note is None:
            toast(app, error, title=behind.first_line, severity="error", timeout=10)
        else:
            # the engine's words and the app's last line, the words set inside the markup
            app.notify(
                as_markup([(error, ""), (note, "dim")]),
                title=behind.first_line,
                severity="error",
                timeout=10,
                markup=True,
            )
        self._send_next_after_leaving(app)

    def _send_next_after_leaving(self, app: "App") -> None:
        queue = self._write_queue
        if not queue:
            return
        if queue[0].left_behind is None:
            queue.clear()
            return
        self._write_inflight = True
        self._write_current = queue.popleft()
        app.run_worker(
            partial(self._send_write, self._write_current, app),
            thread=True,
            group="engine-write",
            exit_on_error=False,
        )

    def _write_finished(
        self,
        item: _QueuedWrite,
        error: str | None,
        body: dict | None = None,
        failure: Exception | None = None,
    ) -> None:
        # UI thread: report the outcome, then pump the next write.
        self._writes_answered += 1
        self._write_inflight = False
        self._write_current = None
        if error is not None:
            dropped = list(self._write_queue or ())
            if self._write_queue:
                self._write_queue.clear()
            if item.on_failure is not None and failure is not None:
                item.on_failure(failure)
            elif item.on_error is not None:
                item.on_error(error)
            else:
                toast(self, error, title="Failed", severity="error")
            self._writes_dropped(item, dropped)
        else:
            # Before on_success: a screen that reads the body typically repaints
            # in on_success, and the repaint has to see what the body said.
            if item.on_response is not None and isinstance(body, dict):
                item.on_response(body)
            if item.on_success is not None:
                item.on_success()
            else:
                self._after_write(item.success)
        if self._write_queue:
            self._pump_writes()

    def _after_write(self, message: str) -> None:
        toast(self, message)

    def confirm_delete(
        self,
        resource: str,
        record_id: object,
        title: str,
        message: str,
        *,
        done: str,
        after: Callable[[], None] | None = None,
        left_behind: LeftBehind | None = None,
    ) -> None:
        """`d` on a row: ask with `ConfirmModal` (only `y` deletes), then send
        `DELETE /{resource}/{id}` through `run_write` — the client's idempotency
        key and error envelope with it. Any other answer sends nothing.

        Deleted, the screen notifies `done` and reloads: through `_after_write`
        by default, or `after` for a list that reloads its own way. Refused, the
        "Failed" note carries the engine's words and, for the refusals that have
        one, the line saying what to do instead (`list_refusal_text`). With
        `left_behind`, the delete is finished and shown even if the screen has
        been left before the engine answers (`EngineWriteMixin`)."""

        def answered(ok: bool | None) -> None:
            if not ok:
                return
            on_success = None
            if after is not None:

                def on_success() -> None:
                    toast(self, done)
                    after()

            self.run_write(
                "DELETE",
                f"/{resource}/{record_id}",
                success=done,
                on_success=on_success,
                error_text=list_refusal_text,
                left_behind=left_behind,
            )

        self.app.push_screen(ConfirmModal(title, message), answered)


def list_refusal_text(exc: Exception) -> str:
    """The `error_text` of a write sent from a list screen (a delete): the
    shared `format_error`, with the line for a list where a refusal's line
    depends on the screen (`errors.NextStep.on_list`: `r` reads the list again)."""
    return format_error(exc, on_list=True)


def delete_row_line(title: object, amount_cents: object, day: str, account_name: str) -> str:
    """The row a delete question names, one line: `TITLE · AMOUNT · DAY · ACCOUNT`,
    an income with its `+` as the lists draw it. Shared by the question for a
    single transaction and the one for a whole split bank line."""
    amount = format_cents_with_plus(amount_cents)
    return f"{title_or_untitled(title)} · {amount} · {day} · {account_name}"


def _transaction_words(title: object, amount_cents: object) -> str:
    """`TITLE · AMOUNT`, the amount as every list of transactions draws it
    (`TRANSACTION_RULE`: a `+` before income)."""
    return f"{title_or_untitled(title)} · {format_cents_with_plus(amount_cents)}"


def not_done_transaction_line(not_done: str, title: object, amount_cents: object) -> str:
    """The first line of a refused write on a transaction shown after its screen has
    left: `Not ticked · TITLE · AMOUNT`, the transaction as its list showed it."""
    return f"{not_done} · {_transaction_words(title, amount_cents)}"


def not_deleted_line(title: object, amount_cents: object) -> str:
    """The first line of a refused delete shown after its screen has left:
    `Not deleted · TITLE · AMOUNT`."""
    return not_done_transaction_line("Not deleted", title, amount_cents)


def not_saved_line(title: object, amount_cents: object) -> str:
    """The first line of a refused save of a transaction shown after its form has
    been left: `Not saved · TITLE · AMOUNT`, the line as its list showed it."""
    return not_done_transaction_line("Not saved", title, amount_cents)


def dated_transaction_line(title: object, amount_cents: object, date: object) -> str:
    """A transaction as the ledger showed it, to name it where its list is gone:
    `DAY · TITLE · AMOUNT`."""
    return f"{format_short_date(date)} · {_transaction_words(title, amount_cents)}"


def not_done_line(not_done: str, kind: str, name: object) -> str:
    """The first line of a refused write shown after its screen has left, for a
    write on a named thing: `Not archived · Account BCP`. `name` is as the list
    shows it; a blank one reads `(unnamed)`."""
    return f"{not_done} · {kind} {name_or_unnamed(name)}"


def transaction_delete_message(record: dict, account_name: str) -> str:
    """The body of "Delete this transaction?" — the ledger's and the "no statement"
    pane's, word for word: the row, then why a delete is final."""
    row = delete_row_line(
        record.get("title"),
        record.get("amount_cents"),
        format_short_date(record.get("date")),
        account_name,
    )
    return f"{row}\nIt leaves every balance and report, and no screen can bring it back."


def bank_line_delete_question(line: dict) -> str:
    """The title of the question before a split bank line is deleted whole,
    naming how many parts go."""
    return f"Delete this transaction and its {bank_line_part_count(line)} parts?"


def bank_line_delete_message(line: dict, account_name: str) -> str:
    """The body of "Delete this transaction and its N parts?": the bank line,
    its day, title and signed total exactly as every statement list shows
    them (`bank_line_columns`), then why a delete is final."""
    day, title, _operation, net_cents = bank_line_columns(line)
    row = delete_row_line(title, net_cents, day, account_name)
    return f"{row}\nNo screen can bring it back."


class ContentSwapLockMixin:
    """Serializes every remove/mount pair on a screen's content container.

    Two repaints can land near-simultaneously (e.g. a manual refresh while a
    write's post-refresh reload is in flight); each swap suspends between
    remove and mount, and interleaved swaps would mount duplicate content
    (DuplicateIds on SectionScreen's '#card', stacked checklists on the
    statement detail screen).
    """

    _swap_lock: asyncio.Lock | None = None

    def _content_lock(self) -> asyncio.Lock:
        if self._swap_lock is None:  # lazily created; only ever touched on the UI thread
            self._swap_lock = asyncio.Lock()
        return self._swap_lock


class LogTransactionMixin:
    """Adds `+` — jump straight to the LOG bar.

    Logging is the thing you do most, so it is a key, not a menu row.
    Bound on Home and Transactions — the screens where "and now
    write one down" is the obvious next thought.

    **It opens the LOG bar, not the bar-cycle form**: one typed line, a staged
    batch, one save. The form keeps its
    *edit* door — `⏎` on an existing row — and lost only its create door.
    `+` still means one thing
    everywhere it is bound: it logs a posted transaction, and a line too
    sparse to post is refused by the grammar in place — never parked
    somewhere by which screen you happened to be standing on.

    **Plain `+`, no modifier, deliberately.** `shift++` was considered and is not
    bindable: for a printable key the shift is already baked into the character
    the terminal sends (on a US layout the main-row `+` *is* shift+`=`), so there
    is no modifier left to report — Textual says as much in `keys.py`
    (`key_to_character`: "Keys with modifiers don't come from printable keys").
    Plain `+` costs nothing anyway: the numpad key and the main-row key send the
    same byte, so one binding catches both, and none of the three screens has a
    text input for a stray `+` to land in.

    `key_display` is set because Textual renders the key name (`plus`) otherwise.

    Like `HelpBindingMixin`, the BINDINGS have to be splatted into each host —
    Textual does not merge BINDINGS from a plain mixin.
    """

    BINDINGS = [Binding("plus", "log_transaction", "Add", key_display="+")]

    def action_log_transaction(self) -> None:
        # imported here, not at module scope: log_bar imports EngineWriteMixin
        # from this module.
        from expense.tui.screens.log_bar import LogBarScreen

        self.app.push_screen(LogBarScreen(), self._after_log)

    def _after_log(self, _result=None) -> None:
        """Hook for hosts that must react once the form closes. Home refreshes
        its stat cluster on resume already; the list screens override this to
        reload, so a transaction you just wrote appears without pressing `r`."""


class AdaptiveRowsMixin:
    """How many rows a list may ask for, given the room it actually has.

    Adaptive rows (cap 20): the page IS the screenful, so every list measures
    its container before fetching and re-measures on a terminal resize.

    Every screen measures through here, never a copy: Transactions raises
    `PAGE_ROWS_CAP`, and a copied measurement would silently ignore that.
    """

    # Lines a CursorList spends on chrome rather than rows:
    #
    #     section rule            1
    #     blank edge              1   Rich's box.SIMPLE
    #     column header           1
    #     header rule             1
    #     blank edge              1
    #     page-status line        1
    #
    # Checked against the render by `test_the_frame_costs_exactly_LIST_FRAME_LINES`;
    # a miscount here overflows every fitted list and clips its page status.
    LIST_FRAME_LINES = 6
    # One more line for a list that keeps a caption. Exactly one list does —
    # the Statements pane — but the asymmetry is named here rather
    # than buried as a literal in that screen's arithmetic.
    CAPTION_LINES = 1
    # Lower bound on the page size we ASK for — not a clipping guard. It cannot
    # make the viewport show five rows: below a ~18-line terminal the extra rows
    # are fetched and then clipped off the bottom (h=20). Measured
    # boundaries and the decision not to guard them: docs/decisions.md "A terminal
    # too small is the user's to fix", docs/tui.md §5.
    PAGE_ROWS_FLOOR = 5
    # Upper bound on the page size. DEFAULT_PAGE_ROWS (20) app-wide — pages stay
    # stable across window sizes and short lists keep a tidy card. Transactions
    # overrides it to grow with the terminal; its cap is
    # the engine's own `limit` ceiling, so the fetch contract can't be broken by
    # a tall window. See docs/decisions.md "The ledger fills the window".
    PAGE_ROWS_CAP = DEFAULT_PAGE_ROWS

    def list_extra_lines(self) -> int:
        """Lines the screen renders around its list inside #content (legends…)."""
        return 0

    def fit_rows(
        self,
        container: str = "#content",
        *,
        chrome: int = 0,
        lines_per_row: int = 1,
        floor: int | None = None,
    ) -> int:
        """Rows that fit `container`, clamped to this screen's limits.

        `chrome` is what the container spends on anything but rows (borders,
        headers, a legend); `lines_per_row` is how many physical lines one row
        costs — two for a pane that splits its room with a sibling. Pre-layout or unmeasurable → the
        20-row default, since a page size of 0 would fetch nothing. `floor` replaces
        `PAGE_ROWS_FLOOR` for a pane that has to give room to a sibling.
        """
        try:
            avail = self.query_one(container).content_size.height
        except Exception:
            return DEFAULT_PAGE_ROWS
        if avail <= 0:
            return DEFAULT_PAGE_ROWS
        rows = (avail - chrome) // lines_per_row
        return max(self.PAGE_ROWS_FLOOR if floor is None else floor, min(self.PAGE_ROWS_CAP, rows))

    def measure_list_rows(self) -> int:
        """The standard case: one list filling #content."""
        return self.fit_rows(chrome=self.LIST_FRAME_LINES + self.list_extra_lines())


class SectionScreen(
    HelpBindingMixin,
    EngineWriteMixin,
    ContentSwapLockMixin,
    AdaptiveRowsMixin,
    Screen,
):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "reload", "Refresh"),
        *HelpBindingMixin.BINDINGS,
    ]
    crumb: tuple[str, ...] = ()
    CARD_WIDTH: int | None = 64  # cap the content card; None = fill width
    _started: bool = False  # first load ran (it waits for the first layout pass)
    _read_started: int | None = None  # writes answered when the read being built began

    def compose(self) -> ComposeResult:
        yield Breadcrumb(self.crumb, id="crumb")
        yield VerticalScroll(LoadingIndicator(), id="content")
        yield FittingFooter()

    def on_mount(self) -> None:
        # First load waits for the first layout pass: adaptive page sizing
        # (measure_list_rows) reads #content's height, which is 0 at mount.
        self.call_after_refresh(self._start_load)

    def _start_load(self) -> None:
        if self._started:
            return
        self._started = True
        self._load()

    def on_resize(self, _event) -> None:
        # The initial layout fires Resize too; adaptive re-windowing only makes
        # sense once the first load measured this same geometry.
        if self._started:
            self._viewport_resized()

    def _viewport_resized(self) -> None:
        """Hook — adaptive-list screens re-window when the terminal size changes."""

    async def action_reload(self) -> None:
        async with self._content_lock():
            content = self.query_one("#content", VerticalScroll)
            await content.remove_children()
            await content.mount(LoadingIndicator())
        self._load()

    # Own group: loads may cancel stale loads, but never a run_write worker.
    @work(thread=True, exclusive=True, group="section-load")
    def _load(self) -> None:
        # Cancellation is cooperative: a newer exclusive load only flags this
        # worker, so check before painting or a superseded load can clobber
        # (or race) the fresh one's content swap.
        worker = get_current_worker()
        started = self._writes_answered  # writes answered before this read began
        try:
            data = self.fetch()
        except Exception as exc:  # surface engine/config errors in-app, don't crash
            if not worker.is_cancelled:
                call_while_attached(self, self._error, format_error(exc))
            return
        if worker.is_cancelled:
            return
        call_while_attached(self, self._show, data, started)

    async def _show(self, data: object, started: int | None = None) -> None:
        content = self.query_one("#content", VerticalScroll)
        async with self._content_lock():
            if not still_attached(self):
                return
            await content.remove_children()
            if not still_attached(self):
                return
            self._read_started = started  # inside the lock: `build` reads its own read's stamp
            card = Vertical(*self.build(data), id="card")
            if self.CARD_WIDTH is not None:
                card.styles.max_width = self.CARD_WIDTH
            await content.mount(card)

    async def _error(self, message: str) -> None:
        content = self.query_one("#content", VerticalScroll)
        async with self._content_lock():
            if not still_attached(self):
                return
            await content.remove_children()
            if not still_attached(self):
                return
            banner = Group(Text("Could not load.", style="bold"), Text(message))
            await content.mount(Static(banner, classes="error"))

    # ---- shared write helpers ----------------------------------------------
    def selected_key(self) -> object | None:
        """The key of the list row under the cursor: the record's id, or whatever
        key the screen's rows carry."""
        from expense.tui.widgets.cursor_list import CursorList

        try:
            return self.query_one(CursorList).cursor_key
        except Exception:
            return None

    def selected_record(self) -> dict | None:
        """The record under the list cursor (screens keep `_by_id`)."""
        return getattr(self, "_by_id", {}).get(self.selected_key())

    def _after_write(self, message: str) -> None:
        toast(self, message)
        self._load()  # re-fetch; content swaps are lock-serialized, no card clash

    # ---- subclass hooks --------------------------------------------------
    def fetch(self) -> object:
        """Fetch data in a worker thread. Raise to surface an in-app error."""
        raise NotImplementedError

    def build(self, data: object) -> list[Widget]:
        """Return the widgets to mount inside the card (runs on the UI thread)."""
        raise NotImplementedError


#: `d Delete` — the last key in a list screen's footer. Each screen splats it at
#: the end of its own BINDINGS: Textual merges a base class's keys ahead of a
#: subclass's, so declared on `ResourceListScreen` it would sit before Accounts'
#: `a Archive`.
DELETE_KEY = Binding("d", "delete", "Delete")


class ResourceListScreen(SectionScreen):
    """Scaffold for the simple manage lists (Accounts / Categories / Hashtags):
    quiet fetch → title + CursorList of rows (+ optional legend). `n` pushes
    the new-record form; `e` the prefilled edit form for the cursor row; `d`
    deletes the cursor row after `confirm_delete`'s question, and the list
    reloads from its first row. Neither `e` nor `d` is offered on a row
    `is_fixed` names. `enter` is a no-op here. The `a` archive toggle
    lives on AccountsScreen only (docs/decisions.md "Archive is a prompt-free
    toggle").

    Subclasses set the class attrs and five hooks, plus `is_fixed` where some
    rows offer neither `e` nor `d`. Row builders stay pure
    module functions (they have direct unit tests).
    """

    TITLE: str = ""
    HEADERS: list[str] = []
    EMPTY: str = "(empty)"
    LEGEND: str | None = None
    ALIGN_RIGHT: set[int] = set()
    RESOURCE: str = ""  # engine collection, e.g. "accounts"
    BINDINGS = [
        ("n", "new", "New"),
        ("e", "edit", "Edit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict = {}
        self._restore_key: object | None = None  # cursor row to re-select after a reload
        # One guarded write at a time (Accounts' a, t, c, x): set when it is sent, lifted by
        # the first list build whose read began after it was answered, or by its refusal.
        self._toggle_busy = False
        self._guarded: _QueuedWrite | None = None  # the guarded write, until it is answered
        self._guard_from = 0  # answered-count a read must have started at to lift the guard

    # ---- hooks ------------------------------------------------------------
    def fetch_items(self, cfg, **kw) -> object:
        """Call the shared fetch_* for this resource (worker thread)."""
        raise NotImplementedError

    def rows(self, items: list) -> list:
        """items → the pure row builder's (id, cells, style) rows."""
        raise NotImplementedError

    def index_items(self, items: list) -> dict:
        """Row key → the record the row stands for; the key is the one `rows` gives
        each row (a record's id unless the screen's rows differ)."""
        return {it.get("id"): it for it in items}

    def edit_screen(self, item: dict):
        """The prefilled edit form for `e` on a row."""
        raise NotImplementedError

    def new_screen(self):
        """The create-form screen for `n`."""
        raise NotImplementedError

    def delete_question(self, item: dict) -> tuple[str, str, str]:
        """`(title, message, done note)` for `d` on `item`."""
        raise NotImplementedError

    def not_deleted(self, item: dict) -> str:
        """The first line of a refused delete of `item` shown after the list has
        left (`not_done_line`)."""
        raise NotImplementedError

    def is_fixed(self, item: dict) -> bool:
        """True for a row with nothing to edit or delete (a built-in row):
        `e` and `d` leave the footer while the cursor is on it."""
        return False

    # ---- the one-guarded-write-at-a-time guard -----------------------------
    def run_guarded_write(self, method: str, path: str, **kwargs: Any) -> None:
        """`run_write`, setting `_toggle_busy` until the write's own aftermath is done:
        its refusal (`clear_guard`, by the caller's `on_error`), or the first list build
        from a read that began after it was answered. A reload that lands earlier, or
        another write's refusal, neither lifts nor holds it."""
        self._toggle_busy = True
        self._guarded = self.run_write(method, path, **kwargs)

    def clear_guard(self) -> None:
        self._guarded = None
        self._toggle_busy = False

    def _write_finished(self, item, error, body=None, failure=None) -> None:
        if item is self._guarded:
            self._guarded = None
            self._guard_from = self._writes_answered + 1  # the count once this answer is counted
        super()._write_finished(item, error, body, failure)

    def _writes_dropped(self, failed, dropped) -> None:
        if self._guarded in dropped:  # never sent: nothing to wait for
            self.clear_guard()
        super()._writes_dropped(failed, dropped)

    # ---- binding availability ----------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action not in ("edit", "archive", "delete"):
            return True
        item = self.selected_record()
        if item is None:
            return None  # empty list → nothing to act on
        if action in ("edit", "delete") and self.is_fixed(item):
            return False  # a built-in row: the keys leave the footer
        return True

    def on_cursor_list_highlighted(self, event) -> None:
        self.refresh_bindings()  # re-check e/a for the row the cursor just landed on

    # ---- adaptive window ---------------------------------------------------
    def list_extra_lines(self) -> int:
        return 2 if self.LEGEND else 0  # legend Static: margin-top 1 + one text line

    def _viewport_resized(self) -> None:
        from expense.tui.widgets.cursor_list import CursorList

        try:
            cursor_list = self.query_one(CursorList)
        except Exception:
            return  # not built yet (loading/error state)
        cursor_list.set_page_size(self.measure_list_rows())

    # ---- scaffold ----------------------------------------------------------
    def fetch(self) -> list:
        from expense import config as config_module
        from expense.reads import items_of

        cfg = config_module.ensure_loaded()
        return items_of(self.fetch_items(cfg, **screen_fetch_kwargs(self.app)))

    def build(self, items: list) -> list[Widget]:
        from expense.tui.widgets.cursor_list import CursorList

        self._by_id = self.index_items(items)
        cursor_list = CursorList(
            self.HEADERS,
            self.rows(items),
            align_right=self.ALIGN_RIGHT,
            empty=self.EMPTY,
            page_size=self.measure_list_rows(),  # adaptive window
        )
        # Re-select the acted-on row: _show mounts a fresh CursorList each load,
        # so without this an archive toggle would snap the cursor back to row 0
        # and "press `a` again to undo" would hit the wrong record.
        if self._restore_key is not None:
            cursor_list.set_cursor(cursor_list.index_of(self._restore_key))
            self._restore_key = None
        if self._guarded is None and (self._read_started or 0) >= self._guard_from:
            self._toggle_busy = False
        self.call_after_refresh(self.refresh_bindings)
        widgets: list[Widget] = [cursor_list]
        if self.LEGEND:
            widgets.append(Static(Text(self.LEGEND), classes="legend"))
        return widgets

    def action_new(self) -> None:
        self.app.push_screen(self.new_screen(), lambda _result: self._load())

    def action_edit(self) -> None:
        item = self.selected_record()
        if not item or self.is_fixed(item):
            return
        self._restore_key = self.selected_key()
        self.app.push_screen(self.edit_screen(item), self._edited)

    def _edited(self, saved: object = None) -> None:
        """An edit form closed. One that dismisses with True wrote to the
        engine, so the list starts over like after a delete: first page, cursor
        on row 1. Any other close keeps the edited row selected."""
        if saved is True:
            self.start_over()
        else:
            self._load()

    def action_delete(self) -> None:
        item = self.selected_record()
        if not item or self.is_fixed(item):
            return
        title, message, done = self.delete_question(item)
        self.confirm_delete(
            self.RESOURCE,
            item.get("id"),
            title,
            message,
            done=done,
            after=self._deleted,
            left_behind=LeftBehind(self.not_deleted(item)),
        )

    def _deleted(self) -> None:
        """A delete starts the list over, first page and cursor on row 1: no row
        is re-selected by the reload. Cleared here, not on `d`, so a cancelled
        question leaves an archive toggle's re-selection in place."""
        self.start_over()

    def start_over(self) -> None:
        """Read the list again from its first page, the cursor on row 1: after a
        delete, and after a form's save that answered once the form was gone."""
        self._restore_key = None
        self._load()
