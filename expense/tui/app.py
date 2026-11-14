"""The Textual app shell + the launch that `expense`, run alone, makes."""

import logging
import sys
from collections.abc import Callable

import typer
from textual import work
from textual.app import App
from textual.worker import WorkerFailed

from expense.context import get_verbose
from expense.import_.engine import SheetReview
from expense.region import apply_launch_format
from expense.tui.screens._base import pending_writes
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.import_sheet import ImportSheetScreen
from expense.tui.screens.modals import ConfirmModal
from expense.tui.screens.setup import SetupScreen
from expense.tui.theme import EXPENSE_ANSI
from expense.tui.widgets.header import Breadcrumb

log = logging.getLogger(__name__)


class ExpenseApp(App[str | None]):
    """Root app: registers the theme and hosts the screen stack.

    `verbose` is read off the typer context and handed to engine fetches
    (run in worker threads by each screen) so `expense --verbose` reaches
    every engine call the app makes.

    It also owns `rate_stale`, the one piece of app-wide state: whether today
    has an exchange rate of its own. It lives here rather than on a screen
    because the indicator is in every header and screens come and go — a screen
    pushed after the fetch landed must find the answer already waiting, and one
    read per launch is the whole cost. `RateAlert` renders it; see that widget
    for what the `!` means.
    """

    CSS_PATH = "app.tcss"
    # no app-level `q` — it would fire from inside ConfirmModal and every list
    # (letters bubble to the App). HomeScreen binds q; ctrl+q quits everywhere.
    # `?` is bound the same way, per screen root, via HelpBindingMixin.

    # The command palette is OFF. It offers five commands, four of
    # them Textual's own dev affordances (Quit — ^q already does it — Maximize,
    # Screenshot) and a theme picker over 21 built-in themes we never designed
    # against our one. Its fifth, the Keys panel, is what `?` replaces, curated
    # and themed. Turning it off also drops Textual's `^p palette` strip from
    # every footer, since Footer gates that key on this same flag.
    # Why: docs/decisions.md "The command palette is removed".
    ENABLE_COMMAND_PALETTE = False

    # None = not yet known (pre-fetch, offline, unconfigured). Never rendered as
    # an alert — "don't know" must look like silence, not like a warning.
    rate_stale: bool | None = None

    def __init__(
        self, *, verbose: bool = False, setup: bool = False, review: SheetReview | None = None
    ) -> None:
        # ansi_color=True makes Textual paint the terminal's OWN default
        # background (SGR 49) instead of a fixed hex, so the app fill and the
        # terminal's window padding are one continuous surface — no seam — on
        # whatever terminal it runs in. The *foreground* goes
        # through the terminal too: the theme is native-ANSI, every colour is a
        # slot the terminal fills in, and nothing is pinned back. That is what
        # makes the app readable on a light terminal without detecting one.
        # Rationale + the cost: docs/decisions.md "The terminal supplies the
        # palette".
        super().__init__(ansi_color=True)
        self._verbose = verbose
        # True opens SetupScreen over Home: `launch` passes it when there is
        # no settings file the app can use (`config.load_usable`). Setup is
        # pushed rather than made the default screen so that, once the engine
        # has accepted the settings, dismissing it lands on Home, which reads
        # afresh on resume.
        self._setup = setup
        # the import's review, pushed over Home (`expense import sheet <file>`)
        self._review = review

    _quit_question: ConfirmModal | None = None
    _after_quit_question: list[Callable[[], object]]

    @property
    def quit_question_open(self) -> bool:
        return self._quit_question is not None and self._quit_question in self.screen_stack

    def after_quit_question(self, leave: Callable[[], object]) -> None:
        """Run `leave` (a screen closing itself) now, or, while the quit question is on
        top, once it is answered: closing a screen pops the top one, which would be the
        question. Dropped when the answer is `y`."""
        if self.quit_question_open:
            self._after_quit_question.append(leave)
        else:
            leave()

    async def action_quit(self) -> None:
        """Quit at once, or, with saves still being sent, ask first: only `y` quits. The
        count is taken when asked; a second quit while the question is open adds none."""
        count = pending_writes(self)
        if count == 0:
            self.exit()
            return
        if self.quit_question_open:
            return
        one = count == 1
        title = (
            "1 save is still being sent. Quit anyway?"
            if one
            else f"{count} saves are still being sent. Quit anyway?"
        )
        message = "If you quit now, no screen will tell you whether " + (
            "it was saved." if one else "they were saved."
        )
        self._after_quit_question = []

        def answered(ok: bool | None) -> None:
            self._quit_question = None
            if ok:
                self.exit()
                return
            waiting, self._after_quit_question = self._after_quit_question, []
            for leave in waiting:
                leave()

        self._quit_question = ConfirmModal(title, message)
        self.push_screen(self._quit_question, answered)

    def get_default_screen(self) -> HomeScreen:
        return HomeScreen()

    def on_mount(self) -> None:
        self.register_theme(EXPENSE_ANSI)
        self.theme = EXPENSE_ANSI.name
        if self._setup:
            self.push_screen(SetupScreen())
            return  # no settings yet: the rate check runs once setup is done
        self.refresh_rate_status()
        if self._review is not None:
            self.push_screen(ImportSheetScreen(self._review))

    @work(thread=True, exclusive=True, group="rate-status")
    def refresh_rate_status(self) -> None:
        """One `GET /exchange-rates` per launch, off the UI thread.

        Failure-silent, exactly like the home stat cluster: offline, no config,
        or engine-down leaves `rate_stale` at None and the header shows nothing.
        An indicator that fires when it cannot reach the engine would be
        reporting on the connection, not on the rate.

        The target is the cached `main_currency` — the home currency the
        conversion actually goes to. With no cached value there is no question
        to ask, so the check is skipped rather than guessed at.
        """
        from expense import config as config_module
        from expense import reads

        try:
            cfg = config_module.ensure_loaded()
            target = getattr(cfg, "main_currency", None)
            if not target:
                return
            stale = reads.fetch_rate_staleness(cfg, target=target, verbose=self._verbose)
        except Exception:
            return
        self.call_from_thread(self._set_rate_stale, stale)

    def _handle_exception(self, error: Exception) -> None:
        # A crash: the traceback goes to the log, then Textual shows it and exits.
        # A failed worker arrives wrapped, without a traceback of its own.
        cause = error.error if isinstance(error, WorkerFailed) else error
        log.error("unhandled error", exc_info=cause)
        super()._handle_exception(error)

    def _set_rate_stale(self, stale: bool | None) -> None:
        self.rate_stale = stale
        # Repaint whatever header is on screen right now. Screens mounted later
        # read the value at render time and need no notification.
        # Every screen on the stack: `self.query` does not reach a pushed screen, the
        # top one included.
        for screen in self.screen_stack:
            for crumb in screen.query(Breadcrumb):
                crumb.refresh()
        # The home screen builds its own header instead of using Breadcrumb, so
        # it opts in by name. Named hook rather than poking a private method:
        # the app must not depend on how any screen paints itself.
        repaint = getattr(self.screen, "repaint_header", None)
        if callable(repaint):
            repaint()


def launch(ctx: typer.Context, review: SheetReview | None = None) -> str | None:
    """TTY guard + launch. The app is interactive-only. Returns the line the app ends
    with, if it ends with one (the import's review does)."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        typer.echo("Error: the app needs an interactive terminal.", err=True)
        raise typer.Exit(code=1)
    # Wipe the screen AND the terminal's scrollback before Textual enters the
    # alt screen: with mouse tracking off, wheel/scrollbar gestures go to the
    # terminal itself, and Terminal.app reveals scrollback ABOVE the running
    # app — pre-launch prompt text floating over the TUI. CSI 3J leaves
    # nothing to reveal; terminals without it ignore it harmlessly.
    # Why: docs/decisions.md "The app clears the terminal scrollback at launch".
    sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
    sys.stdout.flush()
    from expense import config as config_module
    from expense import reads

    # The one read of the settings file: the app holds the result, and every
    # screen and read uses it. No usable file → the app opens on Setup. A review
    # brings the settings its command read (a pipe gives its contents once).
    cfg = review.cfg if review is not None else config_module.load_usable()
    config_module.hold(cfg)
    setup = cfg is None
    # The account's pick wins; none, or no read, follows the machine's region.
    apply_launch_format(reads.fetch_number_format(cfg) if cfg is not None else None)
    # mouse=False: the TUI is keyboard-only. Textual otherwise enables terminal
    # mouse tracking on launch (clicks/scroll act on widgets AND the terminal's
    # native text-selection/copy is suppressed). Disabling it makes the app
    # ignore the mouse and restores native select-to-copy.
    # Why: docs/decisions.md "TUI is keyboard-only".
    try:
        return ExpenseApp(verbose=get_verbose(ctx), setup=setup, review=review).run(mouse=False)
    finally:
        config_module.release()
