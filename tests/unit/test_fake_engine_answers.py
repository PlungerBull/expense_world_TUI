"""FakeClient answers a statement write in the engine's shape, and the statement and
holder builders answer as the engine does.

A statement's reads and writes each answer the whole statement, one balance per
account of its holder (contract: "Statements", "Statement response").
Each default answer is built by the endpoint's `answer_of` builder, the one
scripts/check_fixture_drift.py checks against the contract's required fields.
"""

import pytest

from tests.unit import helpers
from tests.unit.helpers import (
    ANSWER_BUILDERS,
    FAKE_ANSWERS,
    FakeClient,
    account_record,
    holder_list,
    holder_record,
    statement_complete_answer,
    statement_create_answer,
    statement_delete_answer,
    statement_list,
    statement_put_answer,
    statement_record,
    statement_revert_answer,
    statement_row,
    statement_upload_answer,
    upload_balance,
)

S_CREATE = "POST /v1/statements"
S_REVERT = "POST /v1/statements/{statement_id}/revert"
S_COMPLETE = "POST /v1/statements/{statement_id}/complete"
S_DELETE = "DELETE /v1/statements/{statement_id}"
S_READ = "GET /v1/statements/{statement_id}"

#: A card's statement create: its two accounts, the dollar one with no ending yet.
STATEMENT_SENT = {
    "id": "s-new",
    "holder_id": "h-visa",
    "name": "Marzo 2026",
    "date_start": "2026-02-26",
    "date_end": "2026-03-25",
    "balances": [
        {
            "account_id": "acc-pen",
            "beginning_balance_cents": -124050,
            "ending_balance_cents": -38070,
        },
        {"account_id": "acc-usd", "beginning_balance_cents": -6012},
    ],
}


def _keeps_the_bare_answer(endpoint: str, answer: dict) -> None:
    assert set(ANSWER_BUILDERS[endpoint]()) <= set(answer)


def test_each_write_with_a_default_answer_has_a_marked_builder():
    """The drift script checks every builder `answer_of` marks; each default answer
    the fake gives has one, and the fake answers no reconciliation route."""
    assert ANSWER_BUILDERS[S_CREATE] is statement_create_answer
    assert ANSWER_BUILDERS[S_REVERT] is statement_revert_answer
    assert ANSWER_BUILDERS[S_COMPLETE] is statement_complete_answer
    assert ANSWER_BUILDERS[S_DELETE] is statement_delete_answer
    assert not [endpoint for endpoint in ANSWER_BUILDERS if "/reconciliations" in endpoint]
    assert {(method, pattern.pattern) for method, pattern, _ in FAKE_ANSWERS} == {
        ("POST", "/statements"),
        ("POST", "/statements/(?P<statement_id>[^/]+)/revert"),
        ("POST", "/statements/(?P<statement_id>[^/]+)/complete"),
        ("DELETE", "/statements/(?P<statement_id>[^/]+)"),
    }


def test_each_statement_and_holder_read_and_write_has_a_marked_builder():
    """The routes the app reads and writes statements and holders on each have the
    builder the drift script checks."""
    assert ANSWER_BUILDERS["GET /v1/statements"] is statement_list
    assert ANSWER_BUILDERS[S_READ] is statement_record
    assert ANSWER_BUILDERS["PUT /v1/statements/{statement_id}"] is statement_put_answer
    assert ANSWER_BUILDERS["POST /v1/statements/import"] is statement_upload_answer
    assert ANSWER_BUILDERS["GET /v1/holders"] is holder_list
    assert ANSWER_BUILDERS["GET /v1/holders/{holder_id}"] is holder_record


def test_a_default_answer_needs_a_marked_builder():
    with pytest.raises(AssertionError, match="POST /v1/things has no answer_of builder"):
        helpers.fake_answer("POST", "/v1/things")


@pytest.mark.parametrize(
    ("verb", "path"),
    [
        ("post", "/statements"),
        ("post", "/statements/s1/revert"),
        ("post", "/statements/s1/complete"),
        ("put", "/statements/s1"),
    ],
)
def test_a_test_s_own_answer_is_given_exactly(verb, path):
    client = FakeClient()
    own = {"id": "mine"}
    client.write_responses[path] = own

    sent = dict(STATEMENT_SENT) if verb == "put" or path == "/statements" else None
    assert getattr(client, verb)(path, sent) is own


def test_a_put_answer_set_for_a_path_never_comes_back_on_a_delete_of_it():
    """`write_responses` is keyed by path alone, so `delete` never reads it: a
    DELETE of a path whose PUT answer the test set still answers in the engine's
    shape, or `{}` where the fake has no default."""
    client = FakeClient()
    put_answer = {"id": "s1", "name": "saved"}
    client.write_responses["/statements/s1"] = put_answer
    client.write_responses["/transactions/t1"] = {"id": "t1"}

    deleted = client.delete("/statements/s1")

    assert deleted is not put_answer and deleted["deleted_at"] is not None
    _keeps_the_bare_answer(S_DELETE, deleted)
    assert client.delete("/transactions/t1") == {}
    assert client.put("/statements/s1", {"name": "saved"}) is put_answer


def test_a_write_without_a_default_answer_still_answers_empty():
    client = FakeClient()

    assert client.post("/transactions", {"title": "x"}) == {}
    assert client.delete("/transactions/t1") == {}
    assert client.put("/statements/s1", {"name": "x"}) == {}
    assert client.post("/statements/import", {"dry_run": True}) == {}


def test_a_statement_create_answers_the_draft_it_was_sent():
    answer = FakeClient().post("/statements", STATEMENT_SENT)

    _keeps_the_bare_answer(S_CREATE, answer)
    assert {key: answer[key] for key in STATEMENT_SENT if key != "balances"} == {
        key: value for key, value in STATEMENT_SENT.items() if key != "balances"
    }
    assert (answer["status"], answer["deleted_at"]) == (1, None)
    pen, usd = answer["balances"]
    # nothing assigned yet: each account's add-up check is its ending minus its beginning
    assert (pen["account_id"], pen["difference_cents"]) == ("acc-pen", -38070 - -124050)
    assert (usd["account_id"], usd["ending_balance_cents"], usd["difference_cents"]) == (
        "acc-usd",
        None,
        None,
    )


@pytest.mark.parametrize(
    ("verb", "path", "endpoint", "status"),
    [
        ("post", "/statements/s7/revert", S_REVERT, 1),
        ("post", "/statements/s7/complete", S_COMPLETE, 2),
        ("delete", "/statements/s7", S_DELETE, 1),
    ],
)
def test_a_statement_status_write_answers_the_statement_its_path_names(
    verb, path, endpoint, status
):
    answer = getattr(FakeClient(), verb)(path)

    _keeps_the_bare_answer(endpoint, answer)
    assert (answer["id"], answer["status"]) == ("s7", status)
    assert (answer["deleted_at"] is not None) is (endpoint == S_DELETE)


def _card_statement_client(status: int) -> FakeClient:
    """A card's statement the test serves: s1 holding a soles and a dollar account."""
    client = FakeClient()
    client.get_responses["/statements/s1"] = statement_record(
        {
            "id": "s1",
            "holder_id": "h-visa",
            "status": status,
            "unplaced_count": 1,
            "shared_place_count": 2,
            "balances": [
                {"account_id": "acc-pen", "ending_balance_cents": 100, "difference_cents": 0},
                {"account_id": "acc-usd", "ending_balance_cents": 0, "difference_cents": 0},
            ],
        }
    )
    return client


def test_a_statement_complete_adds_the_close_notes_to_each_balance():
    answer = _card_statement_client(1).post("/statements/s1/complete")

    assert (answer["status"], answer["holder_id"]) == (2, "h-visa")
    assert [b["account_id"] for b in answer["balances"]] == ["acc-pen", "acc-usd"]
    for balance in answer["balances"]:
        assert (balance["warnings"], balance["coverage_gap"], balance["review_lines"]) == (
            [],
            None,
            [],
        )
    assert answer["balances"][0]["ending_balance_cents"] == 100


def test_a_statement_complete_keeps_the_notes_a_balance_names():
    flagged = statement_complete_answer({"balances": [{"review_lines": ["bl-9"]}]})

    assert flagged["balances"][0]["review_lines"] == ["bl-9"]
    assert flagged["balances"][0]["warnings"] == []


def test_a_statement_revert_answers_it_as_a_draft_with_no_close_notes():
    answer = _card_statement_client(2).post("/statements/s1/revert")

    assert (answer["status"], answer["holder_id"]) == (1, "h-visa")
    assert all("review_lines" not in b for b in answer["balances"])


@pytest.mark.parametrize(
    ("served", "counts"),
    [({"unplaced_count": 1, "shared_place_count": 2}, (0, 0)), ({}, (None, None))],
    ids=["holder with a statement code", "holder without one"],
)
def test_a_statement_delete_unassigns_its_lines(served, counts):
    """Its lines unassigned, both counts read `0`, or `null` on a holder with no
    statement code (contract: DELETE /v1/statements/{statement_id})."""
    client = FakeClient()
    client.get_responses["/statements/s1"] = statement_record(served)

    answer = client.delete("/statements/s1")

    assert (answer["unplaced_count"], answer["shared_place_count"]) == counts
    assert answer["deleted_at"] is not None


def test_a_statement_read_and_put_spread_a_test_s_record_over_the_whole_shape():
    bare = set(statement_record())
    listed = statement_list([{"id": "s2", "balances": [{"account_id": "acc-usd"}]}])
    put = statement_put_answer({"name": "Abril"})

    (item,) = listed["items"]
    assert set(item) == bare and set(put) == bare
    assert (item["id"], put["name"]) == ("s2", "Abril")
    assert set(item["balances"][0]) == set(statement_record()["balances"][0])
    assert item["balances"][0]["account_id"] == "acc-usd"
    assert [i["id"] for i in statement_list()["items"]] == ["s1"]


def test_a_statement_upload_apply_answers_the_completed_statement():
    paper = [upload_balance("acc-pen", "PEN"), upload_balance("acc-usd", "USD", begin=0, end=0)]
    answer = statement_upload_answer(
        [statement_row(1, account_id="acc-pen"), statement_row(2, outcome="empty")],
        balances=paper,
        review_lines={"acc-usd": ["bl-flag"]},
    )
    closed = answer["statement"]

    assert (answer["statement_id"], answer["creates"], answer["balances"]) == (
        "s-paper",
        True,
        paper,
    )
    assert (closed["id"], closed["status"], closed["name"]) == ("s-paper", 2, "SIG-202610")
    assert [(b["account_id"], b["review_lines"]) for b in closed["balances"]] == [
        ("acc-pen", []),
        ("acc-usd", ["bl-flag"]),
    ]
    assert (closed["unplaced_count"], closed["shared_place_count"]) == (0, 0)
    assert answer["counts"] == {"matched": 1, "new": 0, "empty": 1, "taken_out": 0, "redated": 0}


@pytest.mark.parametrize(("creates", "statement_id"), [(True, None), (False, "s-paper")])
def test_a_statement_upload_dry_run_answers_no_statement(creates, statement_id):
    """`statement_id` is `null` on a dry run that would create the statement, the
    draft's when it fills one; `statement` is `null` on every dry run
    (contract: POST /v1/statements/import, "Response")."""
    answer = statement_upload_answer(dry_run=True, creates=creates)

    assert (answer["dry_run"], answer["statement_id"], answer["statement"]) == (
        True,
        statement_id,
        None,
    )


def test_a_holder_read_spreads_a_test_s_record_over_the_whole_shape():
    card = holder_record({"id": "h-visa", "statement_code": "SIG", "account_ids": ["a", "b"]})
    listed = holder_list([{"id": "h-pen"}, card])

    assert set(card) == set(holder_record())
    assert (card["statement_code"], card["account_ids"]) == ("SIG", ["a", "b"])
    assert [h["id"] for h in listed["items"]] == ["h-pen", "h-visa"]
    assert set(listed["items"][0]) == set(holder_record())


def test_a_holder_read_is_a_bank_holder_by_default():
    """`is_person` tells a bank holder from a person holder (contract: GET /v1/holders):
    the base holder is a bank's."""
    assert holder_record()["is_person"] is False
    assert holder_list()["items"][0]["is_person"] is False


def test_an_account_is_on_a_holder_and_carries_no_statement_code_of_its_own():
    """The statement code is the holder's: an account names its holder and nothing
    else of a statement (contract: "Holders"); a test's fields and a base account
    spread over the whole shape."""
    bare = account_record()
    usd = account_record(id="acc-usd", currency_code="USD")
    person = account_record(usd, name="Ana", is_person=True, holder_id=None)

    assert bare["holder_id"] == holder_record()["id"] == "h1"
    assert {"statement_code", "statement_partner_id"}.isdisjoint(bare)
    assert set(usd) == set(person) == set(bare)
    assert (person["id"], person["currency_code"], person["holder_id"]) == ("acc-usd", "USD", None)
