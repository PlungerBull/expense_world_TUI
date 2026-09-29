"""Category commands that are *not* the shared CRUD contract.

The shared tests live in test_resource_crud_contract.py. Categories keep only
their hint — the 403 on a system category.
"""

import respx
from typer.testing import CliRunner

from expense.commands.categories_cmd import app as categories_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app

cli_app = make_cli_app(categories_app, "categories")

runner = CliRunner()


CATEGORY_RESPONSE = {
    "id": "22222222-2222-2222-2222-222222222222",
    "user_id": "u1",
    "name": "Food",
    "color": "#00FF00",
    "sort_order": 1,
    "is_system": False,
    "system_key": None,
    "deleted_at": None,
    "version": 1,
    "created_at": "2026-04-24T10:00:00Z",
    "updated_at": "2026-04-24T10:00:00Z",
}

LIST_RESPONSE = [CATEGORY_RESPONSE]


PENDIENTE_ID = "33333333-3333-3333-3333-333333333333"


@respx.mock
def test_delete_403_on_pendiente_prints_system_hint(configured):
    """@Pendiente is a system category: the 403 prints the engine error plus the hint.

    The engine message here shares no words with the hint, so the hint is
    chosen by the 403 status alone.
    """
    respx.delete(f"{BASE}/v1/categories/{PENDIENTE_ID}").mock(
        return_value=error_response(403, "FORBIDDEN", "Operation not allowed.", None)
    )
    result = runner.invoke(cli_app, ["categories", "delete", PENDIENTE_ID, "--yes"])
    assert result.exit_code == 1
    assert "FORBIDDEN" in result.output
    assert "Operation not allowed." in result.output
    assert "Hint: System categories can be renamed but not deleted." in result.output.splitlines()
