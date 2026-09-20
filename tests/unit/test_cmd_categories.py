"""Category commands that are *not* the shared CRUD contract.

The shared thirteen live in test_resource_crud_contract.py. Categories keep only
their two hints — the 403 on a system category, and the 409 that means the name
is taken by a deleted row you could restore instead.
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


@respx.mock
def test_delete_403_prints_system_hint(configured):
    respx.delete(f"{BASE}/v1/categories/sys").mock(
        return_value=error_response(403, "FORBIDDEN", "System category cannot be modified.", None)
    )
    result = runner.invoke(cli_app, ["categories", "delete", "sys", "--yes"])
    assert result.exit_code == 1
    assert "system category (@Opening)" in result.output
    assert "FORBIDDEN" in result.output


@respx.mock
def test_restore_409_prints_name_hint(configured):
    respx.post(f"{BASE}/v1/categories/abc/restore").mock(
        return_value=error_response(
            409, "CONFLICT", "An active category with this name already exists.", None
        )
    )
    result = runner.invoke(cli_app, ["categories", "restore", "abc"])
    assert result.exit_code == 1
    assert "Rename the existing one first" in result.output
    assert "CONFLICT" in result.output
