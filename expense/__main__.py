"""The `expense` command: alone it opens the app; `expense import sheet` reads the sheet.

Those are the only two typed entry points (docs/decisions.md "The TUI is the only
surface"); everything else is done in the app.
"""

import typer

from expense.commands import import_cmd
from expense.context import AppContext
from expense.tui import open_app

app = typer.Typer(
    help="Run `expense` alone to open the app.",
    invoke_without_command=True,
    add_completion=False,
)


@app.callback()
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Print HTTP request/response to stderr (Authorization redacted).",
    ),
) -> None:
    """Run `expense` alone to open the app."""
    ctx.obj = AppContext(verbose=verbose)
    if ctx.invoked_subcommand is None:
        open_app(ctx)


import_app = typer.Typer(help="Bring rows in from a spreadsheet.", no_args_is_help=True)
import_app.command("sheet")(import_cmd.run_import)
app.add_typer(import_app, name="import")


if __name__ == "__main__":
    app()
