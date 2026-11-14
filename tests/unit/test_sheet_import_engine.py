"""The sheet import through the engine: what is sent, the names table, what the review
makes, and each step's calls (contract: POST /v1/transactions/import-sheet).

Every answer is built by the fake engine's own builders in tests/unit/helpers.py
(`sheet_import_answer`), shaped from the contract's response schema; every
refusal is the envelope the practice engine sent for the same case. The real
HTTP client runs under respx, so each write's idempotency key is seen.
"""

import base64
import json

import httpx
import pytest
import respx

from expense import config as config_module
from expense.bank_import.engine import file_field
from expense.errors import EngineError
from expense.import_.engine import (
    ACCOUNT,
    CATEGORY,
    HASHTAG,
    NameEntry,
    Suggestion,
    account_entry,
    create_refusals,
    import_sheet,
    missing_accounts,
    missing_names,
    names_table,
    new_ids,
    request_body,
    review_create,
    review_names,
    table_body,
)
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import (
    error_body,
    sheet_import_answer,
    sheet_name_use,
    sheet_row,
)

DATA = b"PK\x03\x04 a made-up workbook"
IMPORT = f"{BASE}/v1/transactions/import-sheet"

#: The refusal as the practice engine sent it on 2026-10-26, for a made-up sheet.
INVALID_REFERENCE = error_body(
    "VALIDATION_ERROR",
    "Import validation failed.",
    {"names.accounts.0.account_id": "Must reference an active, non-archived account."},
    {"names.accounts.0.account_id": "INVALID_REFERENCE"},
)


def _cfg():
    return config_module.ensure_loaded()


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


#: A sheet using one account name in two currencies, which you lack; a category you have
#: and one you do not; a hashtag you do not.
DRY = sheet_import_answer(
    accounts=[sheet_name_use("BCP Oro", 5, None, currencies=["PEN", "USD"])],
    categories=[sheet_name_use("food", 4, "cat-food"), sheet_name_use("travel", 1)],
    hashtags=[sheet_name_use("trip", 5)],
    rows=[sheet_row(r) for r in range(2, 7)],
)

#: The same sheet once every name is yours.
ALL_YOURS = sheet_import_answer(
    accounts=[sheet_name_use("BCP Oro", 5, "acc-oro", currencies=["PEN", "USD"])],
    categories=[sheet_name_use("food", 4, "cat-food"), sheet_name_use("travel", 1, "cat-trv")],
    hashtags=[sheet_name_use("trip", 5, "tag-trip")],
    rows=[sheet_row(r) for r in range(2, 7)],
)


def _engine(first: dict | httpx.Response = DRY):
    """The import route answers `first`."""
    reply = first if isinstance(first, httpx.Response) else httpx.Response(200, json=first)
    return respx.post(IMPORT).mock(return_value=reply)


# ---- what is sent ------------------------------------------------------------------
def test_the_body_is_the_file_whole_in_base64_and_dry_run():
    """`dry_run` and the workbook's bytes, encoded as the bank import encodes a
    download; `names` only when given (contract: POST /v1/transactions/import-sheet, "Body")."""
    data = bytes(range(256)) * 50
    body = request_body(data, dry_run=True)
    assert set(body) == {"dry_run", "file"}
    assert body["file"] == file_field(data)
    assert base64.b64decode(body["file"], validate=True) == data
    names = {"accounts": [], "categories": [], "hashtags": []}
    assert request_body(data, dry_run=False, names=names) == {
        "dry_run": False,
        "file": file_field(data),
        "names": names,
    }


# ---- the names table ---------------------------------------------------------------
def _goes(table: list[NameEntry]) -> list[tuple]:
    return [(e.kind, e.name, e.currencies, e.target_id) for e in table]


def test_each_name_goes_to_its_proposal_else_it_is_missing():
    """An account used in two currencies is one name, one entry holding both
    currencies in the engine's order."""
    table = names_table(DRY)
    assert _goes(table) == [
        (ACCOUNT, "BCP Oro", ("PEN", "USD"), None),
        (CATEGORY, "food", (), "cat-food"),
        (CATEGORY, "travel", (), None),
        (HASHTAG, "trip", (), None),
    ]
    assert [e.rows for e in table] == [5, 4, 1, 5]


def test_an_account_carries_the_engines_suggestion_and_a_proposed_one_none():
    answer = sheet_import_answer(
        accounts=[
            sheet_name_use(
                "BCP 5678",
                2,
                suggestion={
                    "kind": "bank",
                    "bank_code": "BCP",
                    "last4": "5678",
                    "currencies": ["PEN"],
                },
                currencies=["PEN"],
            ),
            sheet_name_use("ALEJO", 2, currencies=["PEN"]),
            sheet_name_use("BCP-1234", 2, "acc-1", currencies=["PEN"]),
        ],
    )
    suggested, unsure, proposed = [e.suggestion for e in names_table(answer)[:3]]
    assert suggested == Suggestion("bank", "BCP", "5678")
    assert unsure == Suggestion(None, None, None)
    assert proposed is None


def test_missing_names_are_the_categories_and_hashtags_one_per_name_the_engine_holds_as_one():
    """`Travel` and `travel` are two names to the sheet but one category to the
    engine, which would refuse the second create as taken; an account is never
    among the names to create."""
    answer = sheet_import_answer(
        accounts=[
            sheet_name_use("BCP", 1, currencies=["PEN"]),
            sheet_name_use("bcp", 1, currencies=["USD", "PEN"]),
        ],
        categories=[sheet_name_use("Travel"), sheet_name_use("travel"), sheet_name_use("Food")],
        hashtags=[sheet_name_use("trip", 1, "tag-trip")],
    )
    table = names_table(answer)
    assert [(e.kind, e.name) for e in missing_names(table)] == [
        (CATEGORY, "Travel"),
        (CATEGORY, "Food"),
    ]
    assert [e.name for e in missing_accounts(table)] == ["BCP", "bcp"]


def test_the_table_sent_gives_every_name_its_id_and_an_account_no_currency():
    """One `{name, account_id}` per account name, however many currencies it holds."""
    assert table_body(names_table(ALL_YOURS)) == {
        "accounts": [{"name": "BCP Oro", "account_id": "acc-oro"}],
        "categories": [
            {"name": "food", "category_id": "cat-food"},
            {"name": "travel", "category_id": "cat-trv"},
        ],
        "hashtags": [{"name": "trip", "hashtag_id": "tag-trip"}],
    }
    with pytest.raises(ValueError, match="BCP Oro"):
        table_body(names_table(DRY))


# ---- what the review makes ---------------------------------------------------------
#: A sheet of an account to make, a proposed account, a category to make in two spellings
#: and a hashtag to make.
REVIEWED = sheet_import_answer(
    accounts=[
        sheet_name_use("BCP 5678", 3, currencies=["PEN", "USD"]),
        sheet_name_use("BCP-1234", 2, "acc-have", currencies=["PEN"]),
    ],
    categories=[
        sheet_name_use("Travel"),
        sheet_name_use("travel"),
        sheet_name_use("food", 1, "c1"),
    ],
    hashtags=[sheet_name_use("trip")],
)
SET = {"type": "bank", "bank": "BCP", "last4": "5678", "archive": "yes", "name": "BCP 5678"}


def test_the_review_makes_an_id_once_for_each_thing_it_creates():
    table = names_table(REVIEWED)
    ids = new_ids(table)
    assert set(ids) == {
        (ACCOUNT, "BCP 5678"),
        (CATEGORY, "travel"),
        (HASHTAG, "trip"),
    }
    assert len(set(ids.values())) == 3


def test_create_lists_what_is_missing_and_names_points_every_name_at_an_id():
    """The proposed account is in `names` with its proposed id and out of `create`; the two
    spellings of one category are two names at one made id."""
    table = names_table(REVIEWED)
    ids = new_ids(table)
    acc, cat, tag = ids[(ACCOUNT, "BCP 5678")], ids[(CATEGORY, "travel")], ids[(HASHTAG, "trip")]
    assert review_create(table, ids, {"BCP 5678": SET}) == {
        "accounts": [
            {
                "id": acc,
                "kind": "bank",
                "bank_code": "BCP",
                "last4": "5678",
                "currencies": ["PEN", "USD"],
                "archived": True,
            }
        ],
        "categories": [{"id": cat, "name": "Travel"}],
        "hashtags": [{"id": tag, "name": "trip"}],
    }
    assert review_names(table, ids) == {
        "accounts": [
            {"name": "BCP 5678", "account_id": acc},
            {"name": "BCP-1234", "account_id": "acc-have"},
        ],
        "categories": [
            {"name": "Travel", "category_id": cat},
            {"name": "travel", "category_id": cat},
            {"name": "food", "category_id": "c1"},
        ],
        "hashtags": [{"name": "trip", "hashtag_id": tag}],
    }


@pytest.mark.parametrize(
    ("values", "entry"),
    [
        (
            {
                "type": "bank",
                "bank": "BCP",
                "last4": "5678",
                "statement_code": "SIG",
                "archive": "no",
            },
            {"bank_code": "BCP", "last4": "5678", "statement_code": "SIG", "archived": False},
        ),
        (
            {"type": "person", "name": "ALEJO", "archive": "no"},
            {"name": "ALEJO", "archived": False},
        ),
        ({"type": "cash", "name": "Caja", "bank": "BCP", "archive": "yes"}, {"archived": True}),
    ],
    ids=["bank", "person", "cash"],
)
def test_an_account_entry_carries_only_what_its_kind_takes(values, entry):
    assert account_entry("id-1", ("PEN",), values) == {
        "id": "id-1",
        "kind": values["type"],
        "currencies": ["PEN"],
        **entry,
    }


def test_a_refusal_keyed_create_names_its_list_place_and_field():
    err = EngineError(
        "VALIDATION_ERROR",
        "Invalid.",
        {
            "create.accounts.1.last4": "taken",
            "create.hashtags.0.name": "bad",
            "create.accounts.2": "x",
        },
        422,
        {},
    )
    assert [tuple(r) for r in create_refusals(err)] == [
        ("accounts", 1, "last4", "taken"),
        ("hashtags", 0, "name", "bad"),
        ("accounts", 2, None, "x"),
    ]


@pytest.mark.parametrize("key", ["rows.2.title", "names.accounts.0.account_id", "file", "create"])
def test_a_refusal_with_a_key_of_anything_else_is_no_create_refusal(key):
    fields = {"create.accounts.0.last4": "a", key: "b"}
    err = EngineError("VALIDATION_ERROR", "Invalid.", fields, 422, {})
    assert create_refusals(err) == []
    assert create_refusals(ValueError("x")) == []


# ---- the run -----------------------------------------------------------------------
@respx.mock
def test_the_command_sends_the_first_dry_run_alone_and_keeps_its_names(configured):
    route = _engine(ALL_YOURS)
    result = import_sheet(_cfg(), DATA)
    assert route.call_count == 1
    assert _body(route.calls[0].request) == {"dry_run": True, "file": file_field(DATA)}
    assert (result.error, len(result.table), len(result.rows)) == (None, 4, 5)


@respx.mock
def test_a_refused_sheet_is_kept_whole(configured):
    _engine(httpx.Response(422, json=INVALID_REFERENCE))
    result = import_sheet(_cfg(), DATA)
    assert isinstance(result.error, EngineError)
    assert (result.error.raw_body, result.answer, result.table) == (INVALID_REFERENCE, None, [])


def test_two_accounts_differing_only_in_case_are_made_under_two_ids():
    """Accounts are kept by the name as listed; the engine refuses the second as taken, but the
    review sends each its own id, while the two spellings of a category share the one."""
    answer = sheet_import_answer(
        accounts=[
            sheet_name_use("BCP Soles", 1, currencies=["PEN"]),
            sheet_name_use("bcp soles", 1, currencies=["PEN"]),
        ],
        categories=[sheet_name_use("Travel"), sheet_name_use("travel")],
    )
    table = names_table(answer)
    ids = new_ids(table)
    entries = review_create(table, ids, {"BCP Soles": SET, "bcp soles": SET})["accounts"]
    assert entries[0]["id"] != entries[1]["id"]
    sent = review_names(table, ids)
    assert sent["categories"][0]["category_id"] == sent["categories"][1]["category_id"]
