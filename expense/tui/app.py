"""The Textual app shell + the launch that `expense`, run alone, makes."""

import sys

import typer
from textual import work
from textual.app import App

from expense.context import get_verbose
from expense.tui.screens.home import HomeScreen
from expense.tui.screens.setup import SetupScreen
from expense.tui.theme import EXPENSE_ANSI
from expense.tui.widgets.header import Breadcrumb


class ExpenseApp(App):
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

    def __init__(self, *, verbose: bool = False, setup: bool = False) -> None:
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

    def get_default_screen(self) -> HomeScreen:
        return HomeScreen()

    def on_mount(self) -> None:
        self.register_theme(EXPENSE_ANSI)
        self.theme = EXPENSE_ANSI.name
        if self._setup:
            self.push_screen(SetupScreen())
            return  # no settings yet: the rate check runs once setup is done
        self.refresh_rate_status()

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

    def _set_rate_stale(self, stale: bool | None) -> None:
        self.rate_stale = stale
        # Repaint whatever header is on screen right now. Screens mounted later
        # read the value at render time and need no notification.
        for crumb in self.query(Breadcrumb).results(Breadcrumb):
            crumb.refresh()
        # The home screen builds its own header instead of using Breadcrumb, so
        # it opts in by name. Named hook rather than poking a private method:
        # the app must not depend on how any screen paints itself.
        repaint = getattr(self.screen, "repaint_header", None)
        if callable(repaint):
            repaint()


def launch(ctx: typer.Context) -> None:
    """TTY guard + launch. The app is interactive-only."""
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

    # No settings file, or one that cannot be read → the app opens on Setup.
    setup = config_module.load_usable() is None
    # mouse=False: the TUI is keyboard-only. Textual otherwise enables terminal
    # mouse tracking on launch (clicks/scroll act on widgets AND the terminal's
    # native text-selection/copy is suppressed). Disabling it makes the app
    # ignore the mouse and restores native select-to-copy.
    # Why: docs/decisions.md "TUI is keyboard-only".
    ExpenseApp(verbose=get_verbose(ctx), setup=setup).run(mouse=False)
