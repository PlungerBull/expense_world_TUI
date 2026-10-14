import typer

from expense import config as config_module
from expense.commands._resource import YES_OPT, require_yes
from expense.config import Config
from expense.errors import ConfigInvalidError, handle_errors
from expense.formatting import redact_token
from expense.jsonout import emit_json

app = typer.Typer(help="Manage ~/.expense-config", no_args_is_help=True)


def _validate_engine_url(url: str) -> None:
    # Validation lives in expense.config (shared with the TUI);
    # BadParameter keeps the CLI's usage-error rendering (exit 2, param hint).
    try:
        config_module.validate_engine_url(url)
    except ConfigInvalidError as exc:
        raise typer.BadParameter(str(exc), param_hint="--engine-url") from exc


@app.command("set")
@handle_errors
def set_cmd(
    engine_url: str | None = typer.Option(None, "--engine-url", help="Base URL of the engine."),
    token: str | None = typer.Option(None, "--token", help="PAT (prefix ewe_pat_) or JWT."),
    main_currency: str | None = typer.Option(
        None,
        "--main-currency",
        help="Cached main currency. Usually set automatically by `auth me`.",
    ),
) -> None:
    """Set one or more fields in ~/.expense-config. Creates the file on first run.

    Example: expense config set --token ewe_pat_xxx --engine-url https://expense-world-engine.onrender.com
    """
    if engine_url is not None:
        _validate_engine_url(engine_url)

    existing = config_module.load()

    if existing is None:
        if not engine_url:
            raise typer.BadParameter("--engine-url is required on first run.")
        new = Config(
            engine_url=engine_url,
            token=token,
            main_currency=main_currency,
        )
    else:
        # Copy-and-update, never a field-by-field rebuild: naming the fields
        # drops every one this command has no flag for, such as
        # `sheet_account_names` (the renames `import sheet` writes). A new
        # Config field must not need an edit here to survive.
        updates: dict[str, object] = {}
        if engine_url:
            updates["engine_url"] = engine_url
        if token is not None:
            updates["token"] = token
        if main_currency is not None:
            updates["main_currency"] = main_currency
        new = existing.model_copy(update=updates)

    if new.token and not new.token.startswith("ewe_pat_"):
        typer.echo(
            "Warning: token does not start with 'ewe_pat_'; "
            "assuming JWT (will work but PAT is recommended for long-lived use).",
            err=True,
        )

    config_module.save(new)
    typer.echo(f"Config saved to {config_module.config_path()}")


def _redact_token(token: str | None) -> str | None:
    return None if token is None else redact_token(token)


@app.command("get")
@handle_errors
def get_cmd(
    show_token: bool = typer.Option(
        False, "--show-token", help="Reveal the token (default: redacted)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Print the current config. Token is redacted unless --show-token is passed.

    Example: expense config get
    """
    cfg = config_module.ensure_loaded()
    data = cfg.model_dump(mode="json")
    if not show_token:
        data["token"] = _redact_token(cfg.token)

    if json_output:
        emit_json(data, sort_keys=True)
    else:
        for key, value in sorted(data.items()):
            display = value if value is not None else "(not set)"
            typer.echo(f"{key}: {display}")


@app.command("clear")
def clear_cmd(
    yes: bool = YES_OPT,
) -> None:
    """Remove ~/.expense-config.

    Example: expense config clear --yes
    """
    path = config_module.config_path()
    if not path.exists():
        typer.echo("No config file to clear.")
        return

    require_yes(yes, f"Remove {path}?")

    config_module.clear()
    typer.echo(f"Config removed: {path}")
