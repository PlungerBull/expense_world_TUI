"""SetupScreen — first-time setup: the engine address and the key, then a profile.

The app opens on this screen, pushed over Home, when there is no settings file
it can use: none at all, or one that cannot be read (`config.load_usable`,
decided in `run_world`). Drawn like every other bar form (FormScreen): one question on the
bar, the answers listed under it. Screens in
docs/mockups/expense-world-first-time-setup.html.

1. **ENGINE ADDRESS** starts filled with the local engine's address
   (`config.LOCAL_ENGINE_URL`); `⏎` accepts it, typing replaces it. An answer
   that is not a full http(s) URL is refused in place, before anything is sent.
2. **KEY**, hidden as it is typed. `⏎` (or `^s Connect` on any field) asks the
   engine two questions with the address and key given, before anything is
   saved:
   - `GET /health`, which needs no key, tells "no engine answers at this address"
     apart from "the engine refuses the key" (contract: "Base Conventions",
     "Authentication");
   - `GET /auth/me`: 200 means the key works and has a profile; `401
     UNAUTHORIZED` means the key is missing, unknown or revoked; `404 NOT_FOUND`
     means the key is fine but has no profile yet (contract: GET /v1/auth/me).
     Branched on the error code, never on the message.
3. **YOUR NAME**, only on that `404`, then **TIME ZONE**: read from this Mac and
   shown read-only, or asked as one more question when it cannot be read.
   `⏎` on the last question (or `^s Create`) sends `POST /auth/bootstrap` with
   `{display_name, timezone}`; the name goes exactly as typed — the engine trims
   it and refuses an empty one (`EMPTY`) or an unknown zone
   (`UNSUPPORTED_VALUE`), writing nothing (contract: POST /v1/auth/bootstrap).

**Nothing is written to the settings file until setup is done**: the engine has
accepted the address and key, and the profile exists. Then the file is saved
(chmod 600, `config.save`) with the home currency the engine named, and this
screen closes onto Home, which `ExpenseApp` opened it over. A failure at any
step leaves the reason in red where the hint was, the cursor on the answer to
fix, and no file.
"""

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.widgets import Input, Static

from expense.config import LOCAL_ENGINE_URL, Config, validate_engine_url
from expense.errors import (
    ConfigInvalidError,
    EngineConnectionError,
    EngineError,
    engine_words,
    format_error,
)
from expense.formatting import redact_token
from expense.tui.screens._form import FormScreen, form_bindings
from expense.tui.theme import PALETTE

#: The bar label per question. "ENGINE ADDRESS" is the longest label of any
#: form, so app.tcss's `#field` width is set from it (test_tui_field_width.py).
LABELS = {
    "address": "ENGINE ADDRESS",
    "key": "KEY",
    "name": "YOUR NAME",
    "timezone": "TIME ZONE",
}
#: The same questions as the list under the bar names them.
_SUMMARY_LABELS = {
    "address": "address",
    "key": "key",
    "name": "name",
    "timezone": "time zone",
}
_HINTS = {
    "address": "where your engine runs · enter to accept, or type another address",
    "key": "the key your engine gave you · starts with ewe_pat_ · hidden as you type",
    "name": "the engine has no profile for this key yet · your name creates one",
    "timezone": "this Mac's time zone could not be read · type yours",
}
ASKING = "asking the engine…"
UNREACHABLE_NEXT = "nothing was saved · start the engine or fix the address, then enter"
REFUSED_NEXT = "nothing was saved · type the key again, then enter"
FAILED_NEXT = "nothing was saved · enter to try again"

# The engine's codes this screen branches on (contract: GET /v1/auth/me).
_KEY_REFUSED = "UNAUTHORIZED"
_NO_PROFILE = "NOT_FOUND"


def _setup_bindings() -> list[Binding | tuple[str, str, str]]:
    """The bar-form keymap with `esc Quit`, and a second `^s` that reads `Create`
    once the engine asks for a profile — `check_action` shows one at a time."""
    bindings = form_bindings("Connect", cancel_desc="Quit")
    bindings.insert(2, Binding("ctrl+s", "create", "Create"))
    return bindings


def _refusal_words(exc: Exception) -> str:
    """How a refused profile creation reads: the engine's own words, without the
    shared text's hints — they point at System screens Setup cannot reach."""
    return engine_words(exc) if isinstance(exc, EngineError) else format_error(exc)


def _is_url(text: str) -> bool:
    try:
        validate_engine_url(text.strip())
    except ConfigInvalidError:
        return False
    return True


class SetupScreen(FormScreen):
    crumb = ("Setup",)
    BINDINGS = _setup_bindings()

    def __init__(self) -> None:
        super().__init__()
        # The bar text per question; the address starts with the local engine's.
        self._text: dict[str, str] = {"address": LOCAL_ENGINE_URL}
        # The questions answered with ⏎ (or sent with ^s).
        self._accepted: set[str] = set()
        # The engine accepted the key and has no profile for it: name + zone.
        self._profile = False
        # (red lines, dim line under them) in the hint's place, or None.
        self._error: tuple[str, str | None] | None = None
        # The address and key the engine was asked with — saved only at the end.
        self._cfg: Config | None = None
        self._settings: dict = {}

    # ---- FormScreen hooks ----------------------------------------------------
    def _sequence(self) -> list[str]:
        if self._profile:
            return ["address", "key", "name", "timezone"]
        return ["address", "key"]

    def _label(self, key: str) -> str:
        return LABELS[key]

    def _hint_for(self, key: str) -> str:
        return _HINTS[key]

    def _required(self) -> tuple[str, ...]:
        return tuple(self._sequence())

    def _bar_value(self, key: str) -> str:
        return self._text.get(key, "")

    def _refresh_bar(self) -> None:
        self.query_one("#bar", Input).password = self._key == "key"
        super()._refresh_bar()

    def _refresh_view(self) -> None:
        super()._refresh_view()
        self.query_one("#hint", Static).update(self._hint_renderable())

    # ---- keys ------------------------------------------------------------------
    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "submit":
            return not self._profile
        if action == "create":
            return self._profile
        return True

    def _stash(self) -> None:
        """Keep what the bar holds as the current question's text."""
        self._text[self._key] = self.query_one("#bar", Input).value

    def _move(self, index: int) -> None:
        self._current = index
        self._refresh_bar()
        self._refresh_view()

    def action_field(self, delta: int) -> None:
        if self._submitting:
            return
        self._stash()
        self._error = None
        super().action_field(delta)

    def action_cancel(self) -> None:
        if not self._submitting:
            self.app.exit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._submitting:
            return
        self._stash()
        self._error = None
        key = self._key
        if key == "address":
            if self._accept_address():
                self._move(self._step(1))
            else:
                self._refresh_view()
            return
        self._accepted.add(key)
        if key == "key":
            self._connect()
            return
        following = self._step(1)
        if following != self._current:
            self._move(following)
        else:
            self._create()

    def action_submit(self) -> None:
        """`^s Connect`, from any field before the engine asks for a profile."""
        if self._submitting:
            return
        self._stash()
        self._error = None
        self._accepted.add(self._key)
        self._connect()

    def action_create(self) -> None:
        """`^s Create`, once the engine asks for a profile."""
        if self._submitting:
            return
        self._stash()
        self._error = None
        self._accepted.add(self._key)
        self._create()

    # ---- address and key -------------------------------------------------------
    def _accept_address(self) -> bool:
        """Accept the address if it is a full http(s) URL; else say why, in place."""
        try:
            validate_engine_url(self._text["address"].strip())
        except ConfigInvalidError as exc:
            self._accepted.discard("address")
            self._error = (str(exc), None)
            return False
        self._accepted.add("address")
        return True

    def _connect(self) -> None:
        if not self._accept_address():
            self._move(0)
            return
        self._accepted.add("key")
        token = self._text.get("key", "").strip()
        self._cfg = Config(engine_url=self._text["address"].strip(), token=token or None)
        self._set_busy(True)
        self._check(self._cfg)

    @work(thread=True, exclusive=True, group="setup-check")
    def _check(self, cfg: Config) -> None:
        outcome, words = self._ask(cfg)
        self.app.call_from_thread(self._checked, outcome, words)

    def _ask(self, cfg: Config) -> tuple[str, str]:
        """Ask the engine about `cfg`; save it only when there is nothing left to ask.

        Returns (outcome, words to show): `connected`, `unreachable`, `refused`,
        `profile` (the key works, no profile yet) or `failed`. Worker thread.
        """
        # Function-local imports: the test fixtures patch these module attributes.
        from expense import config as config_module
        from expense import reads
        from expense.http import ExpenseClient

        try:
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                try:
                    client.get("/health", auth=False)
                except Exception as exc:
                    return "unreachable", format_error(exc)
                try:
                    body = reads.fetch_me(cfg, client=client)
                except EngineConnectionError as exc:
                    return "unreachable", format_error(exc)
                except EngineError as exc:
                    if exc.code == _KEY_REFUSED:
                        return "refused", engine_words(exc)
                    if exc.code == _NO_PROFILE:
                        return "profile", ""
                    return "failed", format_error(exc)
            config_module.save(self._with_currency(cfg, body.get("settings") or {}))
        except Exception as exc:
            return "failed", format_error(exc)
        return "connected", ""

    def _set_busy(self, busy: bool) -> None:
        """While the engine is asked, no key does anything: the bar is disabled
        (typing goes nowhere) and every action returns early on `_submitting`."""
        self._submitting = busy
        bar = self.query_one("#bar", Input)
        bar.disabled = busy
        if not busy:
            bar.focus()
        self._refresh_view()

    def _checked(self, outcome: str, words: str) -> None:
        self._set_busy(False)
        if outcome == "connected":
            self._finish()
            return
        if outcome == "profile":
            self._start_profile()
            return
        if outcome == "unreachable":
            # Back to the address; the key typed is kept.
            self._accepted.discard("address")
            self._error = (words, UNREACHABLE_NEXT)
            self._move(0)
        elif outcome == "refused":
            # Back to an empty key line.
            self._accepted.discard("key")
            self._text["key"] = ""
            self._error = (words, REFUSED_NEXT)
            self._move(1)
        else:
            self._error = (words, FAILED_NEXT)
            self._move(1)

    # ---- profile ---------------------------------------------------------------
    def _start_profile(self) -> None:
        from expense import dates

        self._profile = True
        # The engine accepted these two; changing them now would need asking again.
        self._locked = {"address", "key"}
        try:
            self._text["timezone"] = dates.detect_timezone()
        except dates.TimezoneDetectionError:
            pass
        else:
            self._locked.add("timezone")
            self._accepted.add("timezone")
        self.refresh_bindings()
        self._move(self._sequence().index("name"))

    def _create(self) -> None:
        self._set_busy(True)
        self.run_write(
            "POST",
            "/auth/bootstrap",
            json_body={
                "display_name": self._text.get("name", ""),
                "timezone": self._text.get("timezone", "").strip(),
            },
            config=self._cfg,
            on_response=self._bootstrapped,
            on_success=self._save_and_finish,
            on_error=self._create_refused,
            error_text=_refusal_words,
        )

    def _bootstrapped(self, body: dict) -> None:
        self._settings = body.get("settings") or {}

    def _create_refused(self, message: str) -> None:
        self._set_busy(False)
        self._error = (message, None)
        self._refresh_bar()
        self._refresh_view()

    def _save_and_finish(self) -> None:
        from expense import config as config_module

        assert self._cfg is not None
        try:
            config_module.save(self._with_currency(self._cfg, self._settings))
        except Exception as exc:
            self._create_refused(format_error(exc))
            return
        self._finish()

    @staticmethod
    def _with_currency(cfg: Config, settings: dict) -> Config:
        """`cfg` with the home currency the engine named, for the rate check."""
        currency = settings.get("main_currency") or cfg.main_currency
        return cfg.model_copy(update={"main_currency": currency})

    def _finish(self) -> None:
        # Home is under this screen and reads afresh when it comes back.
        self.dismiss()
        self.app.notify("Connected.")
        refresh = getattr(self.app, "refresh_rate_status", None)
        if callable(refresh):
            refresh()

    # ---- render ----------------------------------------------------------------
    def _hint_renderable(self) -> RenderableType:
        if self._submitting:
            return Text(ASKING, style="dim")
        if self._error is not None:
            words, then = self._error
            lines = [Text(line, style=f"bold {PALETTE.error}") for line in words.splitlines()]
            if then:
                lines.append(Text(then, style="dim"))
            return Group(*lines)
        return Text(self._hint_for(self._key), style="dim")

    def _summary_value(self, key: str) -> Text:
        text = self._text.get(key, "")
        if key == "timezone" and key in self._locked:
            return Text(f"{text}  read-only", style="dim")
        if key in self._accepted and text.strip():
            if key == "key":
                return Text(redact_token(text.strip()))
            return Text(text.strip() if key == "address" else text)
        if key == "address" and _is_url(text):
            # Offered (or tried and not answered), not yet accepted.
            value = Text(text.strip())
            value.append("  *", style="dim")
            return value
        return Text("—  *", style="dim")

    def _summary_renderable(self) -> RenderableType:
        t = Table(box=None, pad_edge=False, show_header=False, expand=False)
        t.add_column("k")
        t.add_column("v")
        current = self._key
        for key in self._sequence():
            read_only = key == "timezone" and key in self._locked
            label = Text(_SUMMARY_LABELS[key], style="dim" if read_only else "")
            if key == current and key not in self._locked:
                label.stylize("bold")
            t.add_row(label, self._summary_value(key))
        return t
