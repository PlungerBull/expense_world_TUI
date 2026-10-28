"""FakeClient answers a reconciliation or statement write in the engine's shape, and
the statement and holder builders answer as the engine does.

A reconciliation's create, revert, complete and delete each answer the half the
write names plus `twin`, the statement's other half, `None` when it has none
(contract: POST /v1/reconciliations, "Response")
(contract: POST /v1/reconciliations/{reconciliation_id}/revert)
(contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response")
(contract: DELETE /v1/reconciliations/{reconciliation_id}, "Response").
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
    complete_answer,
    create_answer,
    delete_answer,
    holder_list,
    holder_record,
    revert_answer,
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

CREATE = "POST /v1/reconciliations"
REVERT = "POST /v1/reconciliations/{reconciliation_id}/revert"
COMPLETE = "POST /v1/reconciliations/{reconciliation_id}/complete"
DELETE = "DELETE /v1/reconciliations/{reconciliation_id}"
S_CREATE = "POST /v1/statements"
S_REVERT = "POST /v1/statements/{statement_id}/revert"
S_COMPLETE = "POST /v1/statements/{statement_id}/complete"
S_DELETE = "DELETE /v1/statements/{statement_id}"
S_READ = "GET /v1/statements/{statement_id}"

#: A one-account create, as the create form sends it.
SENT = {
    "id": "r-new",
    "account_id": "acc-bcp",
    "name": "Marzo 2026",
    "date_start": "2026-02-26",
    "date_end": "2026-03-25",
    "beginning_balance_cents": -124050,
    "ending_balance_cents": -38070,
}
#: A card statement's create: the twin's own id, account and balances, no end.
CARD = {**SENT, "twin": {"id": "r-usd", "account_id": "acc-usd", "beginning_balance_cents": -6012}}


def _keeps_the_bare_answer(endpoint: str, answer: dict) -> None:
    assert set(ANSWER_BUILDERS[endpoint]()) <= set(answer)


def test_each_write_with_a_default_answer_has_a_marked_builder():
    """The drift script checks every builder `answer_of` marks; each default answer
    the fake gives has one."""
    assert ANSWER_BUILDERS[CREATE] is create_answer
    assert ANSWER_BUILDERS[REVERT] is revert_answer
    assert ANSWER_BUILDERS[COMPLETE] is complete_answer
    assert ANSWER_BUILDERS[DELETE] is delete_answer
    assert ANSWER_BUILDERS[S_CREATE] is statement_create_answer
    assert ANSWER_BUILDERS[S_REVERT] is statement_revert_answer
    assert ANSWER_BUILDERS[S_COMPLETE] is statement_complete_answer
    assert ANSWER_BUILDERS[S_DELETE] is statement_delete_answer
    assert {(method, pattern.pattern) for method, pattern, _ in FAKE_ANSWERS} == {
        ("POST", "/reconciliations"),
        ("POST", "/reconciliations/(?P<reconciliation_id>[^/]+)/revert"),
        ("POST", "/reconciliations/(?P<reconciliation_id>[^/]+)/complete"),
        ("DELETE", "/reconciliations/(?P<reconciliation_id>[^/]+)"),
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


def test_a_create_answers_the_draft_it_was_sent():
    client = FakeClient()

    answer = client.post("/reconciliations", dict(SENT))

    _keeps_the_bare_answer(CREATE, answer)
    assert {key: answer[key] for key in SENT} == SENT
    assert (answer["status"], answer["deleted_at"], answer["twin"]) == (1, None, None)
    assert answer["twin_id"] is None
    # nothing assigned yet: the add-up check is ending minus beginning
    assert answer["difference_cents"] == -38070 - -124050


def test_a_create_left_without_an_end_answers_none_for_it():
    sent = {key: value for key, value in SENT.items() if key != "ending_balance_cents"}
    answer = FakeClient().post("/reconciliations", sent)

    assert (answer["ending_balance_cents"], answer["difference_cents"]) == (None, None)


def test_a_card_create_answers_both_halves_naming_each_other():
    answer = FakeClient().post("/reconciliations", dict(CARD))
    twin = answer["twin"]

    _keeps_the_bare_answer(CREATE, answer)
    assert set(create_answer()) - {"twin"} <= set(twin) and "twin" not in twin
    assert (answer["id"], answer["account_id"], answer["twin_id"]) == ("r-new", "acc-bcp", "r-usd")
    assert (twin["id"], twin["account_id"], twin["twin_id"]) == ("r-usd", "acc-usd", "r-new")
    # the twin takes the request's name and days, and its own balances
    assert [twin[key] for key in ("name", "date_start", "date_end")] == [
        "Marzo 2026",
        "2026-02-26",
        "2026-03-25",
    ]
    assert (twin["beginning_balance_cents"], twin["ending_balance_cents"]) == (-6012, None)
    assert (answer["difference_cents"], twin["difference_cents"]) == (-38070 - -124050, None)
    assert twin["status"] == 1
    # both on accounts holding a statement code: an ordered, empty statement each
    for half in (answer, twin):
        assert (half["unplaced_count"], half["shared_place_count"]) == (0, 0)


@pytest.mark.parametrize(
    ("verb", "path", "endpoint", "status"),
    [
        ("post", "/reconciliations/r7/revert", REVERT, 1),
        ("post", "/reconciliations/r7/complete", COMPLETE, 2),
        ("delete", "/reconciliations/r7", DELETE, 1),
    ],
)
def test_a_status_write_answers_the_half_its_path_names(verb, path, endpoint, status):
    answer = getattr(FakeClient(), verb)(path)

    _keeps_the_bare_answer(endpoint, answer)
    assert (answer["id"], answer["status"], answer["twin"]) == ("r7", status, None)
    assert (answer["deleted_at"] is not None) is (endpoint == DELETE)


def test_the_complete_answer_carries_its_warnings_envelope():
    answer = FakeClient().post("/reconciliations/r1/complete")

    assert (answer["warnings"], answer["coverage_gap"]) == ([], None)


def _card_client(status: int) -> FakeClient:
    """A card statement the test serves: r1 on soles, its twin r2 on dollars."""
    client = FakeClient()
    client.get_responses["/reconciliations/r1"] = {
        "id": "r1",
        "account_id": "acc-pen",
        "status": status,
        "twin_id": "r2",
        "unplaced_count": 0,
        "shared_place_count": 1,
    }
    client.get_responses["/reconciliations/r2"] = {
        "id": "r2",
        "account_id": "acc-usd",
        "status": status,
        "twin_id": "r1",
        "unplaced_count": 2,
        "shared_place_count": 0,
    }
    return client


def test_a_card_revert_answers_both_halves_as_drafts():
    answer = _card_client(2).post("/reconciliations/r1/revert")
    twin = answer["twin"]

    assert (answer["status"], answer["account_id"], answer["twin_id"]) == (1, "acc-pen", "r2")
    assert (twin["id"], twin["status"], twin["account_id"], twin["twin_id"]) == (
        "r2",
        1,
        "acc-usd",
        "r1",
    )
    assert set(revert_answer()) - {"twin"} <= set(twin) and "twin" not in twin


def test_a_card_complete_answers_both_halves_with_their_own_envelopes():
    answer = _card_client(1).post("/reconciliations/r1/complete")
    twin = answer["twin"]

    assert (answer["status"], twin["id"], twin["status"]) == (2, "r2", 2)
    assert (twin["warnings"], twin["coverage_gap"]) == ([], None)
    assert set(complete_answer()) - {"twin"} <= set(twin) and "twin" not in twin


def test_a_card_delete_answers_both_halves_deleted_and_unpaired():
    answer = _card_client(1).delete("/reconciliations/r1")
    twin = answer["twin"]

    assert twin["id"] == "r2"
    for half in (answer, twin):
        assert half["deleted_at"] is not None and half["twin_id"] is None
        assert (half["unplaced_count"], half["shared_place_count"]) == (0, 0)


def test_a_twin_the_test_does_not_serve_is_read_from_its_ids():
    client = FakeClient()
    client.get_responses["/reconciliations/r1"] = {"id": "r1", "twin_id": "r2"}

    twin = client.post("/reconciliations/r1/revert")["twin"]

    assert (twin["id"], twin["twin_id"], twin["unplaced_count"]) == ("r2", "r1", 0)


def test_a_half_without_a_statement_code_deletes_with_null_counts():
    answer = FakeClient().delete("/reconciliations/r1")

    assert (answer["unplaced_count"], answer["shared_place_count"]) == (None, None)


@pytest.mark.parametrize(
    ("verb", "path"),
    [
        ("post", "/reconciliations"),
        ("post", "/reconciliations/r1/revert"),
        ("post", "/reconciliations/r1/complete"),
        ("put", "/reconciliations/r1"),
    ],
)
def test_a_test_s_own_answer_is_given_exactly(verb, path):
    client = FakeClient()
    own = {"id": "mine"}
    client.write_responses[path] = own

    assert (
        getattr(client, verb)(
            path, dict(SENT) if verb == "put" or path == "/reconciliations" else None
        )
        is own
    )


def test_a_put_answer_set_for_a_path_never_comes_back_on_a_delete_of_it():
    """`write_responses` is keyed by path alone, so `delete` never reads it: a
    DELETE of a path whose PUT answer the test set still answers in the engine's
    shape, or `{}` where the fake has no default."""
    client = FakeClient()
    put_answer = {"id": "r1", "name": "saved"}
    client.write_responses["/reconciliations/r1"] = put_answer
    client.write_responses["/transactions/t1"] = {"id": "t1"}

    deleted = client.delete("/reconciliations/r1")

    assert deleted is not put_answer and deleted["deleted_at"] is not None
    _keeps_the_bare_answer(DELETE, deleted)
    assert client.delete("/transactions/t1") == {}
    assert client.put("/reconciliations/r1", {"name": "saved"}) is put_answer


def test_a_write_without_a_default_answer_still_answers_empty():
    client = FakeClient()

    assert client.put("/reconciliations/r1", {"name": "x"}) == {}
    assert client.post("/transactions", {"title": "x"}) == {}
    assert client.delete("/transactions/t1") == {}
    assert client.post("/reconciliations/r1/places", {"places": []}) == {}
    assert client.put("/statements/s1", {"name": "x"}) == {}
    assert client.post("/statements/import", {"dry_run": True}) == {}


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
    assert answer["counts"] == {"matched": 1, "new": 0, "empty": 1, "taken_out": 0}


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
