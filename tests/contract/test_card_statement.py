"""Contract: a card statement is one statement, its two halves written as one.

A card is a soles and a dollar account under one statement code, and its statement is
their two reconciliations over exactly the same days, each the other's twin
(contract: "Bank Accounts", "One statement per code per month"). Every reconciliation
names its twin and counts how far its statement is from ordered; one create makes both
halves, and complete, revert, delete, rename and moving the days act on both from either
half, while a balance stays its own half's (contract: "Reconciliations", "A statement's order").
The card statement screens are built on exactly these answers, so only the engine can
say them. Pinned here:

  · the reads: `twin_id` naming the other half on both, `unplaced_count` and
    `shared_place_count` the same on both and moving as lines are assigned and placed (a
    line counted once whatever its parts, an opening balance never), a code with no twin
    counting its own lines, all three `null` without a code, and two halves ordered apart
    and joined by a move of the days holding one place twice;
  · complete and revert from either half writing both in one write, the answer's `twin`
    the other half; a half already completed, or already a draft, left as it is; every
    half already a draft a no-op;
  · their refusals, each naming every half it fails on (`twin.` for the other) and
    writing nothing: `ACCOUNT_ARCHIVED`, then `ENDING_BALANCE_REQUIRED`, then
    `NO_TRANSACTIONS_ASSIGNED`, then `UNASSIGNED_IN_PERIOD`, then `STATEMENT_NOT_ORDERED`,
    never prefixed;
  · one create making both halves, the twin under the request's name and days and its
    own balances; a half created alone over the other half's days becoming its twin;
  · the create's refusals one check at a time, in the contract's order, nothing written;
  · a delete from either half deleting both, its refusals naming each half;
  · a rename and a move from either half writing both, a balance only the half named,
    and the update's refusals naming each half.

Each test builds its own accounts under codes no account of the practice user holds, and
undoes everything (conftest.py `scratch`). Gating, target and the real-ledger guard:
conftest.py.
"""

from uuid import uuid4

from expense.errors import EngineError
from tests.contract.conftest import (
    assert_refusal,
    assert_refusals,
    free_statement_codes,
    reconciliation_body,
    refused,
)

MARCH = ("2026-03-01", "2026-03-31")
ANSWER_ONLY = ("twin", "warnings", "coverage_gap")


def _read(client, recon: str) -> dict:
    return client.get(f"/reconciliations/{recon}")


def _listed(client, account: str) -> list[dict]:
    return client.get("/reconciliations", params={"account_id": account})["items"]


def _order_state(client, recon: str) -> tuple[str | None, int | None, int | None]:
    read = _read(client, recon)
    return read["twin_id"], read["unplaced_count"], read["shared_place_count"]


def _send(client, recon: str, places: list[str | None]) -> dict:
    return client.put(f"/reconciliations/{recon}/statement-order", json_body={"places": places})


def _as_read(answer: dict) -> dict:
    """A write's answer without what only an answer carries, to compare with a read."""
    return {key: value for key, value in answer.items() if key not in ANSWER_ONLY}


def _assert_answers(client, answer: dict, recon: str, twin: str) -> None:
    """The answer is `recon` as its read gives it after the write, and its `twin` is
    `twin` as its read gives it, with no `twin` of its own."""
    assert _as_read(answer) == _read(client, recon)
    assert answer["twin"] is not None and "twin" not in answer["twin"]
    assert _as_read(answer["twin"]) == _read(client, twin)


def _refused_writing_nothing(client, call, *recons: str) -> EngineError:
    """`call` is refused, and every reconciliation in `recons` reads as before it."""
    before = [_read(client, recon) for recon in recons]
    err = refused(call)
    assert [_read(client, recon) for recon in recons] == before
    return err


def _gone(client, recon: str) -> bool:
    try:
        _read(client, recon)
    except EngineError as err:
        return err.status == 404
    return False


# ---- each half names the other, and both count the statement --------------------


def test_each_half_names_the_other_and_both_count_the_statement(client, scratch):
    """Every reconciliation carries `twin_id`, `unplaced_count` and
    `shared_place_count`, on its read and on each item of its account's list
    (contract: "Reconciliations", "Every reconciliation says its statement's other
    half and whether the statement is ordered") (contract: GET /v1/reconciliations):
    each half of a card names the other, and both count the whole statement's lines,
    a line once whatever its parts, never an opening balance; the counts follow every
    line assigned and every list sent
    (contract: "Reconciliations", "Nothing renumbers on its own"). With a code and no
    twin they count the reconciliation's own lines; without a code all three are
    `null` (contract: "Reconciliations", "On an account without a statement code, all
    three are `null`"). Two halves ordered apart become twins when a move gives one
    the other's days, the move's answer naming the other half unwritten, and both read
    place 1 held twice (contract: PUT /v1/reconciliations/{reconciliation_id}, "Response")."""
    code, lone_code, joined_code = free_statement_codes(client, 3)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)
    for recon, twin, account in ((rs, rd, soles), (rd, rs, dollars)):
        read = _read(client, recon)
        assert "twin" not in read
        assert _listed(client, account) == [read]
        assert _order_state(client, recon) == (twin, 0, 0)

    scratch.opening_balance(soles, "2026-02-15", rs)
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    d1 = scratch.line(dollars, "2026-03-06", -300, -200, recon=rd)
    assert _order_state(client, rs) == (rd, 2, 0)
    assert _order_state(client, rd) == (rs, 2, 0)
    _send(client, rd, [d1, s1])
    assert _order_state(client, rs) == (rd, 0, 0)
    late = scratch.line(dollars, "2026-03-20", -400, recon=rd)
    assert _order_state(client, rs) == (rd, 1, 0)
    assert _order_state(client, rd) == (rs, 1, 0)
    _send(client, rs, [d1, s1, late])
    assert _order_state(client, rd) == (rs, 0, 0)

    lone = scratch.account("PEN", lone_code)
    lone_recon = scratch.reconciliation(lone, *MARCH)
    scratch.line(lone, "2026-03-05", -1000, recon=lone_recon)
    assert _order_state(client, lone_recon) == (None, 1, 0)
    plain = scratch.account("PEN")
    plain_recon = scratch.reconciliation(plain, *MARCH)
    scratch.line(plain, "2026-03-05", -1000, recon=plain_recon)
    assert _order_state(client, plain_recon) == (None, None, None)

    js = scratch.account("PEN", joined_code)
    jd = scratch.account("USD", joined_code)
    march = scratch.reconciliation(js, *MARCH)
    april = scratch.reconciliation(jd, "2026-04-01", "2026-04-30")
    _send(client, march, [scratch.line(js, "2026-03-05", -1000, recon=march)])
    _send(client, april, [scratch.line(jd, "2026-03-06", -300, recon=april)])
    assert _order_state(client, march) == (None, 0, 0)
    before = _read(client, march)
    moved = client.put(
        f"/reconciliations/{april}", json_body={"date_start": MARCH[0], "date_end": MARCH[1]}
    )
    assert (moved["twin_id"], moved["unplaced_count"], moved["shared_place_count"]) == (
        march,
        0,
        1,
    )
    assert moved["twin"]["version"] == before["version"]
    _assert_answers(client, moved, april, march)
    assert _order_state(client, march) == (april, 0, 1)


# ---- complete and revert: the whole statement, from either half ------------------


def test_complete_and_revert_act_on_both_halves_from_either(client, scratch):
    """Completing from either half completes both in one write, each bumping its own
    `version`, the answer the half the path names plus `twin`, the other half with its
    own `warnings` and `coverage_gap`
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Atomicity")
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response"), and
    both currencies' lines read one statement's codes. Reverting from either half
    reverts both, its answer carrying `twin` and neither `warnings` nor `coverage_gap`;
    reverting a statement whose every half is a draft writes nothing
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert, "Response")
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert, "Revert requires nothing")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    d1 = scratch.line(dollars, "2026-03-06", -300, recon=rd)
    _send(client, rs, [s1, d1])

    versions = {recon: _read(client, recon)["version"] for recon in (rs, rd)}
    done = client.post(f"/reconciliations/{rd}/complete")
    _assert_answers(client, done, rd, rs)
    for half in (done, done["twin"]):
        assert half["status"] == 2
        assert half["version"] == versions[half["id"]] + 1
        assert {"warnings", "coverage_gap"} <= set(half)
    assert client.get(f"/bank-lines/{s1}")["statement_line"] == f"{code}-202603-001"
    assert client.get(f"/bank-lines/{d1}")["statement_line"] == f"{code}-202603-002"

    back = client.post(f"/reconciliations/{rs}/revert")
    _assert_answers(client, back, rs, rd)
    for half in (back, back["twin"]):
        assert half["status"] == 1
        assert half["version"] == versions[half["id"]] + 2
        assert not {"warnings", "coverage_gap"} & set(half)

    drafts = [_read(client, recon) for recon in (rs, rd)]
    again = client.post(f"/reconciliations/{rd}/revert")
    assert (again["status"], again["twin"]["status"]) == (1, 1)
    assert [_read(client, recon) for recon in (rs, rd)] == drafts


def _completed_then_twinned(client, scratch, soles: str, dollars: str, days) -> tuple:
    """A soles reconciliation over `days`, its one line placed and completed alone, then
    a dollar draft made alone over the same days, which becomes its twin; the two ids
    and the soles line's."""
    completed = scratch.reconciliation(soles, *days)
    line = scratch.line(soles, days[0], -1000, recon=completed)
    _send(client, completed, [line])
    client.post(f"/reconciliations/{completed}/complete")
    draft = scratch.reconciliation(dollars, *days)
    assert (_read(client, completed)["status"], _read(client, draft)["status"]) == (2, 1)
    assert _order_state(client, draft) == (completed, 0, 0)
    return completed, draft, line


def test_a_half_already_completed_or_already_a_draft_is_left_as_it_is(client, scratch):
    """A half created alone over the days of a completed reconciliation on the other
    account holding the code becomes its twin while that one stays completed
    (contract: POST /v1/reconciliations, "Without `twin`, the create makes this one
    reconciliation alone"). Completing that statement, from either half, completes the
    draft half and leaves the completed one as it is, no `version` bump; the completed
    half's lines are judged with it, the draft's opening balance taking no place
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Atomicity").
    Meanwhile the completed half's lines read their statement lines and the draft
    half's read `null` (contract: "Transactions (Ledger)", "Bank lines"), and no list is
    taken from the draft half (`RECONCILIATION_NOT_DRAFT`)
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order, "Refusals").
    Reverting such a statement, from either half, reverts the completed half and leaves
    the draft as it is (contract: POST /v1/reconciliations/{reconciliation_id}/revert)."""
    code, other_code = free_statement_codes(client, 2)
    pairs = [(scratch.account("PEN", c), scratch.account("USD", c)) for c in (code, other_code)]

    # Completed from each half in turn: the dollar draft holds its opening balance only,
    # one per account, so each direction takes its own card.
    for (soles, dollars), from_completed in zip(pairs, (False, True), strict=True):
        completed, draft, _ = _completed_then_twinned(client, scratch, soles, dollars, MARCH)
        scratch.opening_balance(dollars, MARCH[0], draft)
        kept, draft_version = _read(client, completed), _read(client, draft)["version"]
        named, other = (completed, draft) if from_completed else (draft, completed)
        done = client.post(f"/reconciliations/{named}/complete")
        _assert_answers(client, done, named, other)
        assert _read(client, completed) == kept
        assert _read(client, draft)["status"] == 2
        assert _read(client, draft)["version"] == draft_version + 1

    soles, dollars = pairs[0]
    april = ("2026-04-01", "2026-04-30")
    completed, draft, line = _completed_then_twinned(client, scratch, soles, dollars, april)
    loose = scratch.line(dollars, april[0], -300, recon=draft)
    assert client.get(f"/bank-lines/{line}")["statement_line"] == f"{code}-202604-001"
    assert client.get(f"/bank-lines/{loose}")["statement_line"] is None
    err = _refused_writing_nothing(
        client, lambda: _send(client, draft, [line, loose]), completed, draft
    )
    assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "RECONCILIATION_NOT_DRAFT")

    # Reverted from each half in turn: April's from its completed half, May's from its
    # draft.
    may = _completed_then_twinned(client, scratch, soles, dollars, ("2026-05-01", "2026-05-31"))
    for done, waiting, from_completed in ((completed, draft, True), (*may[:2], False)):
        kept, draft_version = _read(client, done), _read(client, waiting)["version"]
        named, other = (done, waiting) if from_completed else (waiting, done)
        back = client.post(f"/reconciliations/{named}/revert")
        _assert_answers(client, back, named, other)
        assert _read(client, waiting)["version"] == draft_version
        reverted = _read(client, done)
        assert (reverted["status"], reverted["version"]) == (1, kept["version"] + 1)


def test_complete_and_revert_refusals_name_each_half(client, scratch):
    """Each check runs on both halves before the next, the first that fails answering
    for every half it failed on, a key with `twin.` in front naming the other half, and
    nothing is written
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Which half a
    refusal names")
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation"): an
    archived account, `409` `ACCOUNT_ARCHIVED` on `reconciliation_id` or
    `twin.reconciliation_id` or both, refused on a revert too, a draft included
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert); then no ending
    balance (`ENDING_BALANCE_REQUIRED`); then no transaction assigned
    (`NO_TRANSACTIONS_ASSIGNED`); then a transaction dated inside the period left
    unassigned (`UNASSIGNED_IN_PERIOD`); then the statement not ordered
    (`STATEMENT_NOT_ORDERED` on `statement_order`, never prefixed: the order is the
    whole statement's). Each answers alone while the checks after it would refuse too."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)

    def complete(recon: str):
        return lambda: client.post(f"/reconciliations/{recon}/complete")

    def revert(recon: str):
        return lambda: client.post(f"/reconciliations/{recon}/revert")

    # From here on every later check would refuse too: the soles half has no ending
    # balance, neither half a transaction, and a dollar line in the period is
    # unassigned; each step below answers alone, so it comes before all of those.
    loose = scratch.line(dollars, "2026-03-07", -200)
    client.put(f"/reconciliations/{rs}", json_body={"ending_balance_cents": None})
    client.post(f"/accounts/{dollars}/archive")
    for call, key in (
        (complete(rs), "twin.reconciliation_id"),
        (complete(rd), "reconciliation_id"),
        (revert(rs), "twin.reconciliation_id"),
        (revert(rd), "reconciliation_id"),
    ):
        err = _refused_writing_nothing(client, call, rs, rd)
        assert_refusal(err, 409, "CONFLICT", key, "ACCOUNT_ARCHIVED")
    client.post(f"/accounts/{soles}/archive")
    both = {"reconciliation_id": "ACCOUNT_ARCHIVED", "twin.reconciliation_id": "ACCOUNT_ARCHIVED"}
    for call in (complete(rs), revert(rd)):
        assert_refusals(_refused_writing_nothing(client, call, rs, rd), 409, "CONFLICT", both)
    client.post(f"/accounts/{soles}/unarchive")
    client.post(f"/accounts/{dollars}/unarchive")

    client.put(f"/reconciliations/{rd}", json_body={"ending_balance_cents": None})
    err = _refused_writing_nothing(client, complete(rs), rs, rd)
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {
            "ending_balance_cents": "ENDING_BALANCE_REQUIRED",
            "twin.ending_balance_cents": "ENDING_BALANCE_REQUIRED",
        },
    )
    client.put(f"/reconciliations/{rs}", json_body={"ending_balance_cents": 0})
    # The path's half has no transaction, but the ending balance is checked first.
    err = _refused_writing_nothing(client, complete(rs), rs, rd)
    assert_refusal(
        err, 422, "VALIDATION_ERROR", "twin.ending_balance_cents", "ENDING_BALANCE_REQUIRED"
    )
    client.put(f"/reconciliations/{rd}", json_body={"ending_balance_cents": 0})

    err = _refused_writing_nothing(client, complete(rd), rs, rd)
    none = "NO_TRANSACTIONS_ASSIGNED"
    assert_refusals(err, 422, "VALIDATION_ERROR", {"transactions": none, "twin.transactions": none})
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    # The dollar half has no transaction and an unassigned line in its period.
    for recon, key in ((rd, "transactions"), (rs, "twin.transactions")):
        err = _refused_writing_nothing(client, complete(recon), rs, rd)
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "NO_TRANSACTIONS_ASSIGNED")

    d1 = scratch.line(dollars, "2026-03-06", -300, recon=rd)
    for recon, key in ((rs, "twin.transactions"), (rd, "transactions")):
        err = _refused_writing_nothing(client, complete(recon), rs, rd)
        assert_refusal(err, 422, "VALIDATION_ERROR", key, "UNASSIGNED_IN_PERIOD")
    loose_part = client.get(f"/bank-lines/{loose}")["parts"][0]["id"]
    client.put(f"/transactions/{loose_part}", json_body={"reconciliation_id": rd})

    for recon in (rs, rd):
        err = _refused_writing_nothing(client, complete(recon), rs, rd)
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_order", "STATEMENT_NOT_ORDERED")
    _send(client, rd, [s1, d1, loose])
    assert client.post(f"/reconciliations/{rs}/complete")["twin"]["status"] == 2


# ---- one create, both halves ------------------------------------------------------


def test_one_create_makes_both_halves(client, scratch, statuses):
    """`POST /reconciliations` with `twin` creates both halves as drafts in one write,
    the twin under the request's name and days and its own balances, an omitted
    ending balance `null`; each names the other as `twin_id` in the answer and on every
    read, the answer's `twin` being the other half
    (contract: POST /v1/reconciliations, "Both halves of a card statement in one write: `twin`")
    (contract: POST /v1/reconciliations, "Response"). Without `twin`, a half created
    over exactly the days of one on the other account holding the code is that one's
    twin from then on, the answer's `twin` being it, unwritten; one with no other half
    answers `twin: null`, and one on an account without a code all three `null`
    (contract: POST /v1/reconciliations, "Without `twin`, the create makes this one
    reconciliation alone")."""
    code, lone_code = free_statement_codes(client, 2)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    body = reconciliation_body(soles, *MARCH, twin=dollars)
    body["twin"]["beginning_balance_cents"] = 1500
    del body["twin"]["ending_balance_cents"]
    rs, rd = body["id"], body["twin"]["id"]
    scratch.reconciliations.extend((rs, rd))

    made = client.post("/reconciliations", json_body=body)
    assert statuses[-1] == 201
    _assert_answers(client, made, rs, rd)
    twin = made["twin"]
    assert (made["twin_id"], twin["twin_id"]) == (rd, rs)
    for half, account in ((made, soles), (twin, dollars)):
        assert half["account_id"] == account
        assert (half["name"], half["date_start"], half["date_end"], half["status"]) == (
            body["name"],
            *MARCH,
            1,
        )
        assert _listed(client, account) == [_as_read(half)]
    assert (made["beginning_balance_cents"], made["ending_balance_cents"]) == (0, 0)
    assert (twin["beginning_balance_cents"], twin["ending_balance_cents"]) == (1500, None)

    april = scratch.reconciliation(soles, "2026-04-01", "2026-04-30")
    before = _read(client, april)
    alone = reconciliation_body(dollars, "2026-04-01", "2026-04-30")
    scratch.reconciliations.append(alone["id"])
    joined = client.post("/reconciliations", json_body=alone)
    _assert_answers(client, joined, alone["id"], april)
    assert joined["twin_id"] == april
    assert joined["twin"]["twin_id"] == alone["id"]
    assert joined["twin"]["version"] == before["version"]

    lone = scratch.account("PEN", lone_code)
    for account, state in ((lone, (None, 0, 0)), (scratch.account("PEN"), (None, None, None))):
        single = reconciliation_body(account, *MARCH)
        scratch.reconciliations.append(single["id"])
        answer = client.post("/reconciliations", json_body=single)
        assert answer["twin"] is None
        assert (answer["twin_id"], answer["unplaced_count"], answer["shared_place_count"]) == state


def test_the_card_create_refuses_one_check_at_a_time(client, scratch):
    """A create with `twin` judges both halves one check at a time and answers with the
    first that refuses, naming every half it refused, nothing written
    (contract: POST /v1/reconciliations, "Order")
    (contract: POST /v1/reconciliations, "One check at a time")
    (contract: POST /v1/reconciliations, "Which half a refusal names"): what the request
    alone shows (`EMPTY` on `name`, `RANGE_INVERTED` on `date_end`, `DUPLICATE_IN_REQUEST`
    on `twin.id`, `UNKNOWN_FIELD` inside `twin`)
    (contract: POST /v1/reconciliations, "The same id twice"); then a taken id (`409`
    `ID_EXISTS` on `id`, `twin.id`, or both); then the accounts, the twin's judged as
    the account is and both in one answer (`INVALID_REFERENCE`, `PERSON_ACCOUNT`); then
    the twin's account as the other account holding the code (`NOT_STATEMENT_PARTNER`)
    (contract: POST /v1/reconciliations, "`twin.account_id` is first judged as
    `account_id` is")
    (contract: POST /v1/reconciliations, "`twin.account_id` must be the other live
    account holding the statement code of `account_id`"); then an overlapping period
    (`PERIOD_OVERLAPS`); then the statement month (`STATEMENT_MONTH_TAKEN`)
    (contract: POST /v1/reconciliations, "One statement per code per month")."""
    (code, other_code) = free_statement_codes(client, 2)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    other_coded = scratch.account("USD", other_code)
    plain = scratch.account("USD")
    person = scratch.person("USD")
    archived = scratch.account("USD")
    client.post(f"/accounts/{archived}/archive")
    soles_jan, dollars_jan = scratch.card(soles, dollars, "2026-01-01", "2026-01-31")
    dollars_feb = scratch.reconciliation(dollars, "2026-02-20", "2026-03-15")
    accounts = (soles, dollars, other_coded, plain)
    lists = {account: _listed(client, account) for account in accounts}

    def card(start: str = "2026-05-01", end: str = "2026-05-31", **change) -> dict:
        body = reconciliation_body(soles, start, end, twin=dollars)
        twin_change = {k[5:]: change.pop(k) for k in list(change) if k.startswith("twin_")}
        body.update(change)
        body["twin"].update(twin_change)
        for recon in (body["id"], body["twin"]["id"]):
            if recon not in (soles_jan, dollars_jan):
                scratch.reconciliations.append(recon)
        return body

    def answer(body: dict) -> EngineError:
        err = refused(lambda: client.post("/reconciliations", json_body=body))
        for recon in (body["id"], body["twin"]["id"]):
            assert recon in (soles_jan, dollars_jan) or _gone(client, recon), recon
        return err

    duplicated = card()
    duplicated["twin"]["id"] = duplicated["id"]
    taken_twice = card(id=soles_jan)
    taken_twice["twin"]["id"] = soles_jan
    unknown = card()
    unknown["twin"]["bogus"] = 1

    vague = "VALIDATION_ERROR"
    for body, status, error, reasons in (
        # 1. What the request alone shows, before a taken id.
        (card(name="   "), 422, vague, {"name": "EMPTY"}),
        (card("2026-05-31", "2026-05-01"), 422, vague, {"date_end": "RANGE_INVERTED"}),
        (duplicated, 422, vague, {"twin.id": "DUPLICATE_IN_REQUEST"}),
        (taken_twice, 422, vague, {"twin.id": "DUPLICATE_IN_REQUEST"}),
        (unknown, 422, vague, {"twin.bogus": "UNKNOWN_FIELD"}),
        # 2. A taken id, before the account.
        (card(id=soles_jan), 409, "CONFLICT", {"id": "ID_EXISTS"}),
        (card(twin_id=dollars_jan), 409, "CONFLICT", {"twin.id": "ID_EXISTS"}),
        (
            card(id=soles_jan, twin_id=dollars_jan),
            409,
            "CONFLICT",
            {"id": "ID_EXISTS", "twin.id": "ID_EXISTS"},
        ),
        (card(id=soles_jan, account_id=archived), 409, "CONFLICT", {"id": "ID_EXISTS"}),
        # 3a. Each half's account, judged alike, before the code's partner.
        (card(account_id=str(uuid4())), 422, vague, {"account_id": "INVALID_REFERENCE"}),
        (card(account_id=archived), 422, vague, {"account_id": "INVALID_REFERENCE"}),
        (card(account_id=person), 422, vague, {"account_id": "PERSON_ACCOUNT"}),
        (card(twin_account_id=str(uuid4())), 422, vague, {"twin.account_id": "INVALID_REFERENCE"}),
        (card(twin_account_id=archived), 422, vague, {"twin.account_id": "INVALID_REFERENCE"}),
        (card(twin_account_id=person), 422, vague, {"twin.account_id": "PERSON_ACCOUNT"}),
        (
            card(account_id=archived, twin_account_id=person),
            422,
            vague,
            {"account_id": "INVALID_REFERENCE", "twin.account_id": "PERSON_ACCOUNT"},
        ),
        (
            card(account_id=archived, twin_account_id=plain),
            422,
            vague,
            {"account_id": "INVALID_REFERENCE"},
        ),
        # 3b. The twin's account as the other account holding the code, before an overlap.
        (card(twin_account_id=soles), 422, vague, {"twin.account_id": "NOT_STATEMENT_PARTNER"}),
        (card(twin_account_id=plain), 422, vague, {"twin.account_id": "NOT_STATEMENT_PARTNER"}),
        (
            card(twin_account_id=other_coded),
            422,
            vague,
            {"twin.account_id": "NOT_STATEMENT_PARTNER"},
        ),
        (
            card(account_id=plain, twin_account_id=dollars),
            422,
            vague,
            {"twin.account_id": "NOT_STATEMENT_PARTNER"},
        ),
        (
            card("2026-01-15", "2026-01-20", twin_account_id=plain),
            422,
            vague,
            {"twin.account_id": "NOT_STATEMENT_PARTNER"},
        ),
        # 3c. An overlapping period, on each half it overlaps, before the month.
        (
            card("2026-01-15", "2026-02-10"),
            422,
            vague,
            {"date_start": "PERIOD_OVERLAPS", "twin.date_start": "PERIOD_OVERLAPS"},
        ),
        (card("2026-03-10", "2026-03-31"), 422, vague, {"twin.date_start": "PERIOD_OVERLAPS"}),
        # 3d. The statement month, which the dollar half's February period holds.
        (
            card("2026-03-20", "2026-03-31"),
            422,
            vague,
            {"date_end": "STATEMENT_MONTH_TAKEN", "twin.date_end": "STATEMENT_MONTH_TAKEN"},
        ),
    ):
        assert_refusals(answer(body), status, error, reasons)

    assert {account: _listed(client, account) for account in accounts} == lists
    assert _order_state(client, dollars_feb) == (None, 0, 0)


# ---- a delete takes both halves ---------------------------------------------------


def test_a_delete_from_either_half_deletes_both(client, scratch):
    """`DELETE /reconciliations/{id}` deletes the whole statement from either half, in
    one write: both halves deleted, every line of both unassigned with its place
    cleared, the answer's `twin` the other half, both reading `twin_id: null` and
    counts `0` (contract: DELETE /v1/reconciliations/{reconciliation_id}, "Response").
    Refused, naming every half it fails on (one or both) and writing nothing: an
    archived account (`409` `ACCOUNT_ARCHIVED`), checked before a completed half
    (`RECONCILIATION_NOT_DRAFT`)
    (contract: DELETE /v1/reconciliations/{reconciliation_id}, "Which half a refusal
    names")
    (contract: DELETE /v1/reconciliations/{reconciliation_id}, "Validation")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)

    for start, end, sent_from in (
        ("2026-03-01", "2026-03-31", "dollars"),
        ("2026-04-01", "2026-04-30", "soles"),
    ):
        rs, rd = scratch.card(soles, dollars, start, end)
        s1 = scratch.line(soles, start, -1000, recon=rs)
        d1 = scratch.line(dollars, start, -300, recon=rd)
        _send(client, rs, [s1, d1])
        named, other = (rd, rs) if sent_from == "dollars" else (rs, rd)

        if sent_from == "soles":
            client.post(f"/reconciliations/{rs}/complete")
            err = _refused_writing_nothing(
                client, lambda rs=rs: client.delete(f"/reconciliations/{rs}"), rs, rd
            )
            assert_refusals(
                err,
                409,
                "CONFLICT",
                {
                    "reconciliation_id": "RECONCILIATION_NOT_DRAFT",
                    "twin.reconciliation_id": "RECONCILIATION_NOT_DRAFT",
                },
            )
            client.post(f"/accounts/{dollars}/archive")
            for recon, key in ((rs, "twin.reconciliation_id"), (rd, "reconciliation_id")):
                err = _refused_writing_nothing(
                    client, lambda recon=recon: client.delete(f"/reconciliations/{recon}"), rs, rd
                )
                assert_refusal(err, 409, "CONFLICT", key, "ACCOUNT_ARCHIVED")
            client.post(f"/accounts/{soles}/archive")
            err = _refused_writing_nothing(
                client, lambda rd=rd: client.delete(f"/reconciliations/{rd}"), rs, rd
            )
            archived = "ACCOUNT_ARCHIVED"
            assert_refusals(
                err,
                409,
                "CONFLICT",
                {"reconciliation_id": archived, "twin.reconciliation_id": archived},
            )
            client.post(f"/accounts/{soles}/unarchive")
            client.post(f"/accounts/{dollars}/unarchive")
            client.post(f"/reconciliations/{rd}/revert")

        gone = client.delete(f"/reconciliations/{named}")
        assert gone["id"] == named and gone["twin"]["id"] == other
        assert "twin" not in gone["twin"]
        for half in (gone, gone["twin"]):
            assert half["deleted_at"] is not None
            assert (half["twin_id"], half["unplaced_count"], half["shared_place_count"]) == (
                None,
                0,
                0,
            )
        assert _gone(client, rs) and _gone(client, rd)
        for line in (s1, d1):
            read = client.get(f"/bank-lines/{line}")
            assert read["statement_place"] is None
            assert {part["reconciliation_id"] for part in read["parts"]} == {None}

    # One half completed, the other a draft: only the completed half is named.
    may = ("2026-05-01", "2026-05-31")
    completed, draft, _ = _completed_then_twinned(client, scratch, soles, dollars, may)
    for recon, key in ((draft, "twin.reconciliation_id"), (completed, "reconciliation_id")):
        err = _refused_writing_nothing(
            client, lambda r=recon: client.delete(f"/reconciliations/{r}"), completed, draft
        )
        assert_refusal(err, 409, "CONFLICT", key, "RECONCILIATION_NOT_DRAFT")


# ---- a rename and a move take both halves, a balance one --------------------------


def test_a_rename_and_a_move_change_both_halves_and_a_balance_one(client, scratch):
    """`PUT /reconciliations/{id}` sending `name`, `date_start` or `date_end` writes them
    to both halves in one write, each bumping its own `version`, the halves still each
    other's twin with every line and place kept; a balance is written to the half the
    path names alone, the other half not written and its account not checked
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "A card statement is
    renamed and moved as one")
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "Response"). Refused,
    naming every half it fails on and writing nothing
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "Which half a refusal names"):
    an empty name and an inverted period once, unprefixed; the twin's archived account
    on `twin.<field>` (`ACCOUNT_ARCHIVED`)
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "Archived accounts"),
    checked before the days of a completed statement (`LOCKED` on both halves, while
    its name is still written whole)
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "Field locking on COMPLETED");
    and a move onto days another period of the twin's account holds (`PERIOD_OVERLAPS`
    on `twin.date_start`)
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "Period validation")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    d1 = scratch.line(dollars, "2026-03-06", -300, recon=rd)
    _send(client, rd, [d1, s1])
    places = {line: client.get(f"/bank-lines/{line}")["statement_place"] for line in (s1, d1)}

    def put(recon: str, body: dict) -> dict:
        return client.put(f"/reconciliations/{recon}", json_body=body)

    def versions() -> tuple[int, int]:
        return _read(client, rs)["version"], _read(client, rd)["version"]

    start = versions()
    renamed = put(rs, {"name": "contract card March"})
    _assert_answers(client, renamed, rs, rd)
    assert (renamed["name"], renamed["twin"]["name"]) == ("contract card March",) * 2
    assert versions() == (start[0] + 1, start[1] + 1)

    moved = put(rd, {"date_start": "2026-03-02", "date_end": "2026-03-30"})
    _assert_answers(client, moved, rd, rs)
    for half in (moved, moved["twin"]):
        assert (half["date_start"], half["date_end"]) == ("2026-03-02", "2026-03-30")
    assert (moved["twin_id"], moved["twin"]["twin_id"]) == (rs, rd)
    assert versions() == (start[0] + 2, start[1] + 2)
    back = put(rs, {"date_start": MARCH[0], "date_end": MARCH[1]})
    _assert_answers(client, back, rs, rd)
    for half in (back, back["twin"]):
        assert (half["date_start"], half["date_end"]) == MARCH
    assert versions() == (start[0] + 3, start[1] + 3)
    for line, recon in ((s1, rs), (d1, rd)):
        read = client.get(f"/bank-lines/{line}")
        assert read["statement_place"] == places[line]
        assert {part["reconciliation_id"] for part in read["parts"]} == {recon}
    assert _order_state(client, rs) == (rd, 0, 0)

    other = _read(client, rd)
    balanced = put(rs, {"ending_balance_cents": 1234})
    _assert_answers(client, balanced, rs, rd)
    assert balanced["ending_balance_cents"] == 1234
    assert _read(client, rd) == other
    both = put(rd, {"name": "contract card", "beginning_balance_cents": 99})
    assert (both["name"], both["twin"]["name"]) == ("contract card",) * 2
    assert (both["beginning_balance_cents"], both["twin"]["beginning_balance_cents"]) == (99, 0)
    same = _read(client, rs), _read(client, rd)
    noop = put(rs, {})
    _assert_answers(client, noop, rs, rd)
    assert (_read(client, rs), _read(client, rd)) == same

    for body, reasons in (
        ({"name": "  "}, {"name": "EMPTY"}),
        ({"date_start": "2026-03-31", "date_end": "2026-03-01"}, {"date_end": "RANGE_INVERTED"}),
    ):
        err = _refused_writing_nothing(client, lambda body=body: put(rd, body), rs, rd)
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)

    scratch.reconciliation(dollars, "2026-05-01", "2026-05-31")
    err = _refused_writing_nothing(
        client, lambda: put(rs, {"date_start": "2026-04-15", "date_end": "2026-05-05"}), rs, rd
    )
    assert_refusal(err, 422, "VALIDATION_ERROR", "twin.date_start", "PERIOD_OVERLAPS")

    client.post(f"/accounts/{soles}/archive")
    err = _refused_writing_nothing(
        client, lambda: put(rd, {"name": "x", "date_end": "2026-03-29"}), rs, rd
    )
    assert_refusals(
        err,
        422,
        "VALIDATION_ERROR",
        {"twin.name": "ACCOUNT_ARCHIVED", "twin.date_end": "ACCOUNT_ARCHIVED"},
    )
    err = _refused_writing_nothing(client, lambda: put(rs, {"name": "x"}), rs, rd)
    assert_refusal(err, 422, "VALIDATION_ERROR", "name", "ACCOUNT_ARCHIVED")
    assert put(rd, {"ending_balance_cents": 5})["ending_balance_cents"] == 5
    client.post(f"/accounts/{soles}/unarchive")

    client.post(f"/reconciliations/{rs}/complete")
    err = _refused_writing_nothing(client, lambda: put(rs, {"date_start": "2026-03-03"}), rs, rd)
    assert_refusals(
        err, 422, "VALIDATION_ERROR", {"date_start": "LOCKED", "twin.date_start": "LOCKED"}
    )
    client.post(f"/accounts/{soles}/archive")
    err = _refused_writing_nothing(client, lambda: put(rd, {"date_start": "2026-03-03"}), rs, rd)
    assert_refusal(err, 422, "VALIDATION_ERROR", "twin.date_start", "ACCOUNT_ARCHIVED")
    client.post(f"/accounts/{soles}/unarchive")
    closed = put(rd, {"name": "contract card closed"})
    assert (closed["name"], closed["twin"]["name"]) == ("contract card closed",) * 2
    assert (closed["status"], closed["twin"]["status"]) == (2, 2)
