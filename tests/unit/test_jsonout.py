"""`--json` emits one shape, from every command.

The regression these guard: thirty-one hand-written `json.dumps` calls, three
of which (the bank importer's) passed `ensure_ascii=False` while the rest did
not — so the same Spanish account name came out readable from one command and
escaped from the next.
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from expense.commands.accounts_cmd import app as accounts_app
from expense.jsonout import emit_json, json_text
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import make_cli_app

runner = CliRunner()
cli_app = make_cli_app(accounts_app, "accounts")

ACCENTED = "Ahorro Café · Préstamo Ñ"


def test_json_text_keeps_utf8_instead_of_escaping_it():
    assert ACCENTED in json_text({"name": ACCENTED})
    assert "\\u00e9" not in json_text({"name": ACCENTED})


def test_json_text_keeps_insertion_order_unless_asked_to_sort():
    payload = {"b": 1, "a": 2}
    assert list(json.loads(json_text(payload))) == ["b", "a"]
    assert list(json.loads(json_text(payload, sort_keys=True))) == ["a", "b"]


def test_emit_json_writes_one_parseable_document(capsys):
    emit_json({"name": ACCENTED})
    assert json.loads(capsys.readouterr().out)["name"] == ACCENTED


@respx.mock
def test_a_list_command_emits_accents_the_way_the_bank_importer_always_did(configured):
    respx.get(f"{BASE}/v1/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [{"id": "a1", "name": ACCENTED, "currency_code": "PEN"}],
                "total": 1,
                "limit": 20,
                "offset": 0,
            },
        )
    )
    result = runner.invoke(cli_app, ["accounts", "list", "--json"])
    assert result.exit_code == 0, result.output
    assert ACCENTED in result.output
    assert json.loads(result.output)["items"][0]["name"] == ACCENTED
