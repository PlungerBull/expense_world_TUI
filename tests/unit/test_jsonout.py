"""`--json` emits one shape: real UTF-8, two-space indent, keys in insertion order.

The ledger's names are mostly Spanish; an escaped `Caf\\u00e9` is valid JSON no
human can read.
"""

import json

from expense.jsonout import emit_json, json_text

ACCENTED = "Ahorro Café · Préstamo Ñ"


def test_json_text_keeps_utf8_instead_of_escaping_it():
    assert ACCENTED in json_text({"name": ACCENTED})
    assert "\\u00e9" not in json_text({"name": ACCENTED})


def test_json_text_keeps_insertion_order():
    assert list(json.loads(json_text({"b": 1, "a": 2}))) == ["b", "a"]


def test_emit_json_writes_one_parseable_document(capsys):
    emit_json({"name": ACCENTED})
    assert json.loads(capsys.readouterr().out)["name"] == ACCENTED
