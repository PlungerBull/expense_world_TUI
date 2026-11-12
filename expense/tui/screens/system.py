"""System screens — Config and Auth & profile.

Config: read view of engine URL / token (masked) / main currency; `e` edits
the engine URL, `t` sets the token (both write ~/.expense-config). Auth &
profile: identity + settings from GET /auth/me; `b` bootstraps (provisions the
user record). The main currency is display-only — it is locked engine-side.

Activity and Rates have no screen (docs/decisions.md "Activity and
Rates leave the TUI").
"""

from rich import box
from rich.table import Table
from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static

from expense import region
from expense.errors import format_error
from expense.formatting import redact_token
from expense.number_format import NumberFormat, set_current_format
from expense.tui.screens._base import LeftBehind, SectionScreen
from expense.tui.screens.modals import PromptModal, QuestionLine, QuestionModal
from expense.tui.widgets.refusal import toast


def _redact_token(token: str | None) -> str:
    return "(none)" if not token else redact_token(token)


def _kv_table(rows: list[tuple[str, object]]) -> Table:
    t = Table(box=box.SIMPLE, pad_edge=False, show_header=False)
    t.add_column("k", style="dim")
    t.add_column("v")
    for key, value in rows:
        # a pre-styled Text passes through; the rest stringify
        cell = (
            value
            if isinstance(value, Text)
            else Text(str(value if value not in (None, "") else "—"))
        )
        t.add_row(key, cell)
    return t


class ConfigScreen(SectionScreen):
    crumb = ("System", "Config")
    CARD_WIDTH = 76
    BINDINGS = [
        ("e", "set_engine", "Engine URL"),
        ("t", "set_token", "Token"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = None

    def fetch(self) -> dict:
        from expense import config as config_module

        return {"cfg": config_module.current()}

    def build(self, data: dict) -> list[Widget]:
        self._cfg = data["cfg"]
        cfg = self._cfg
        rows = [
            ("engine url", getattr(cfg, "engine_url", None)),
            ("token", _redact_token(getattr(cfg, "token", None))),
            ("main currency", getattr(cfg, "main_currency", None)),
        ]
        return [
            Static(Text("Config — engine connection"), classes="section-title"),
            Static(_kv_table(rows)),
            Static(
                Text(
                    "e set engine url · t set token · token is a secret — never logged", style="dim"
                ),
                classes="legend",
            ),
        ]

    def action_set_engine(self) -> None:
        current = getattr(self._cfg, "engine_url", "") or ""

        def cb(value: str | None) -> None:
            if value:
                self._save(engine_url=value)

        self.app.push_screen(PromptModal("Engine URL", value=current), cb)

    def action_set_token(self) -> None:
        def cb(value: str | None) -> None:
            if value:
                self._save(token=value)

        self.app.push_screen(
            PromptModal("Token", "PAT (ewe_pat_…) — hidden as you type", password=True), cb
        )

    def _save(self, **updates) -> None:
        from expense import config as config_module
        from expense.errors import ConfigInvalidError

        if not self._cfg:
            self.notify("No config loaded.", severity="error")
            return
        if "engine_url" in updates:
            # the save-time validation first-time setup uses too: a
            # scheme-less URL would save fine and fail every later call with
            # a generic connection error
            try:
                config_module.validate_engine_url(updates["engine_url"])
            except ConfigInvalidError as exc:
                toast(self, str(exc), title="Invalid URL", severity="error")
                return
        try:
            config_module.save(self._cfg.model_copy(update=updates))
        except Exception as exc:
            toast(self, format_error(exc), title="Couldn't save", severity="error")
            return
        self.notify("Config saved.")
        self._load()


def _format_cell(setting: NumberFormat | None, region_format: NumberFormat, name: str | None):
    """`1.234,56  · your setting`, or the Mac's format and `· follows this Mac (<region>)`."""
    if setting is not None:
        return Text.assemble(setting.example, ("  · your setting", "dim"))
    follows = "  · follows this Mac" + (f" ({name})" if name else "")
    return Text.assemble(region_format.example, (follows, "dim"))


class AuthScreen(SectionScreen):
    crumb = ("System", "Auth & profile")
    CARD_WIDTH = 76
    BINDINGS = [
        ("b", "bootstrap", "Bootstrap"),
        ("f", "number_format", "Number format"),
    ]
    _CHOICE_WIDTH = 21

    def __init__(self) -> None:
        super().__init__()
        # (the account's pick, the machine's format): None until provisioned
        self._format_state: tuple[NumberFormat | None, NumberFormat] | None = None

    def fetch(self) -> dict:
        from expense import config as config_module
        from expense import reads
        from expense.errors import EngineError
        from expense.http import ExpenseClient

        cfg = config_module.ensure_loaded()
        try:
            # The shared path is what caches `main_currency`, which the
            # header's stale-rate check targets. Reading /auth/me here
            # directly would leave no cached currency and so no warning, ever.
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                body = reads.fetch_me(cfg, client=client)
        except EngineError as exc:
            if exc.status == 404:
                return {"provisioned": False}
            raise
        return {
            "provisioned": True,
            "user": body.get("user", {}) or {},
            "settings": body.get("settings", {}) or {},
            "region_format": region.read_region_format(),
            "region_name": region.read_region_name(),
        }

    def build(self, data: dict) -> list[Widget]:
        if not data.get("provisioned"):
            return [
                Static(Text("Auth & profile"), classes="section-title"),
                Static(
                    Text("No user record yet — press b to bootstrap (provision) it.", style="dim"),
                    classes="legend",
                ),
            ]
        user = data["user"]
        settings = data["settings"]
        setting = NumberFormat.from_example(settings.get("number_format"))
        self._format_state = (setting, data["region_format"])
        self.refresh_bindings()
        rows = [
            ("display name", user.get("display_name")),
            ("user id", user.get("id")),
            ("main currency", settings.get("main_currency")),
            ("timezone", settings.get("display_timezone") or user.get("timezone")),
            ("number format", _format_cell(setting, data["region_format"], data["region_name"])),
        ]
        return [
            Static(Text("Auth & profile — your identity & settings"), classes="section-title"),
            Static(_kv_table([(k, v) for k, v in rows if v is not None])),
            Static(
                Text("b bootstrap (provision)", style="dim"),
                classes="legend",
            ),
        ]

    def action_bootstrap(self) -> None:
        # The name goes out exactly as typed, blank included: the engine trims it
        # and refuses an empty one (contract: POST /v1/auth/bootstrap). Only `esc`
        # (None) sends nothing.
        def cb(name: str | None) -> None:
            if name is not None:
                self._bootstrap(name)

        self.app.push_screen(
            PromptModal("Bootstrap", "your display name — creates your user record", verbatim=True),
            cb,
        )

    def _bootstrap(self, display_name: str) -> None:
        from expense import dates

        # Resolve before run_write: an undetectable timezone must notify, not
        # crash the app through Textual's message pump.
        try:
            timezone = dates.detect_timezone()
        except dates.TimezoneDetectionError:
            self.notify(
                "Could not read this Mac's time zone. Set it in System Settings, "
                "then press b again.",
                title="Bootstrap failed",
                severity="error",
            )
            return
        self.run_write(
            "POST",
            "/auth/bootstrap",
            json_body={"display_name": display_name, "timezone": timezone},
            success="Provisioned.",
            on_success=lambda: self._done("Provisioned."),
            on_error=lambda m: toast(self, m, title="Bootstrap failed", severity="error"),
            left_behind=LeftBehind("Not provisioned"),
        )

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "number_format" and self._format_state is None:
            return False  # not provisioned: the key leaves the footer
        return True

    def action_number_format(self) -> None:
        """`f`: ask which format, then `PUT /auth/settings` with it, or `null` for Follow
        this Mac. The engine judges the value (contract: PUT /v1/auth/settings): a refusal
        shows under the question in its words and nothing changes.
        Saved, the session format follows at once (`set_current_format`); a screen already
        drawn takes it at its next load."""
        if self._format_state is None:
            return
        setting, region_format = self._format_state
        width = self._CHOICE_WIDTH
        dot, comma = NumberFormat.DOT_DECIMAL, NumberFormat.COMMA_DECIMAL
        options: dict[str, NumberFormat | None] = {
            f"{'Follow this Mac':<{width}}{region_format.example} now": None,
            f"{dot.example:<{width}}dot for decimals": dot,
            f"{comma.example:<{width}}comma for decimals": comma,
        }
        choices = tuple(options)
        line = QuestionLine(
            "number_format",
            "",
            choices,
            start=list(options.values()).index(setting),
        )

        saved = "Number format saved."

        def apply(chosen: NumberFormat | None) -> None:
            set_current_format(chosen or region_format)

        def written(chosen: NumberFormat | None) -> None:
            apply(chosen)
            if modal.is_attached:
                modal.dismiss()
            toast(self, saved)
            self._load()

        def written_after_leaving(chosen: NumberFormat | None) -> str:
            apply(chosen)  # the screen is gone: the format still follows, the app says so
            return saved

        def failed(failure: Exception) -> None:
            if modal.is_attached:
                modal.refuse("number_format", format_error(failure))
            else:
                toast(self, format_error(failure), title="Failed", severity="error")

        def send(values: dict[str, str]) -> None:
            chosen = options[values["number_format"]]
            self.run_write(
                "PUT",
                "/auth/settings",
                json_body={"number_format": chosen.example if chosen else None},
                on_success=lambda: written(chosen),
                on_failure=failed,
                left_behind=LeftBehind(
                    "Not saved · Number format",
                    success_from=lambda _body: written_after_leaving(chosen),
                ),
            )

        modal = QuestionModal("Number format", [line], "⏎ Save  esc Cancel", send)
        self.app.push_screen(modal)

    def _done(self, message: str) -> None:
        toast(self, message)
        self._load()
