"""System screens — Config and Auth & profile.

Config: read view of engine URL / token (masked) / main currency; `e` edits
the engine URL, `t` sets the token (both write ~/.expense-config). Auth &
profile: identity + settings from GET /auth/me; `b` bootstraps (provisions the
user record). The main currency is display-only — it is locked engine-side.

Activity and Rates are flat commands only (docs/decisions.md "Activity and
Rates leave the TUI").
"""

from rich import box
from rich.table import Table
from rich.text import Text
from textual.widget import Widget
from textual.widgets import Static

from expense.commands._resource import redact_token
from expense.errors import format_error
from expense.tui.screens._base import SectionScreen
from expense.tui.screens.modals import PromptModal


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

        return {"cfg": config_module.load()}

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
            # same save-time validation as the CLI's `config set`: a
            # scheme-less URL would save fine and fail every later call with
            # a generic connection error
            try:
                config_module.validate_engine_url(updates["engine_url"])
            except ConfigInvalidError as exc:
                self.notify(str(exc), title="Invalid URL", severity="error")
                return
        try:
            config_module.save(self._cfg.model_copy(update=updates))
        except Exception as exc:
            self.notify(format_error(exc), title="Couldn't save", severity="error")
            return
        self.notify("Config saved.")
        self._load()


class AuthScreen(SectionScreen):
    crumb = ("System", "Auth & profile")
    CARD_WIDTH = 76
    BINDINGS = [
        ("b", "bootstrap", "Bootstrap"),
    ]

    def fetch(self) -> dict:
        from expense import config as config_module
        from expense.commands import auth_cmd
        from expense.errors import EngineError
        from expense.http import ExpenseClient

        cfg = config_module.ensure_loaded()
        try:
            # Shared with `expense auth me` — and the shared path is what
            # caches `main_currency`, which the header's stale-rate check
            # targets. Reading /auth/me here directly left a TUI-only user
            # with no cached currency and so no warning, ever.
            with ExpenseClient(cfg, verbose=self.app._verbose) as client:
                body = auth_cmd.fetch_me(cfg, client=client)
        except EngineError as exc:
            if exc.status == 404:
                return {"provisioned": False}
            raise
        return {
            "provisioned": True,
            "user": body.get("user", {}) or {},
            "settings": body.get("settings", {}) or {},
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
        rows = [
            ("display name", user.get("display_name")),
            ("user id", user.get("id")),
            ("main currency", settings.get("main_currency")),
            ("timezone", settings.get("display_timezone") or user.get("timezone")),
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
        def cb(name: str | None) -> None:
            if name:
                self._bootstrap(name)

        self.app.push_screen(
            PromptModal("Bootstrap", "your display name — creates your user record"), cb
        )

    def _bootstrap(self, display_name: str) -> None:
        from expense import dates

        # Resolve before run_write: an undetectable timezone must notify, not
        # crash the app through Textual's message pump.
        try:
            timezone = dates.detect_timezone()
        except dates.TimezoneDetectionError:
            self.notify(
                "Could not detect your timezone. Set the TZ environment variable and "
                "relaunch, or run 'expense auth bootstrap --timezone <zone>' from the CLI.",
                title="Bootstrap failed",
                severity="error",
            )
            return
        self.run_write(
            "POST",
            "/auth/bootstrap",
            json_body={"display_name": display_name, "timezone": timezone},
            on_success=lambda: self._done("Provisioned."),
            on_error=lambda m: self.notify(m, title="Bootstrap failed", severity="error"),
        )

    def _done(self, message: str) -> None:
        self.notify(message)
        self._load()
