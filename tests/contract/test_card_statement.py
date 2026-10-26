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
    half already a draft a no-op on a revert, and every half already completed a no-op
    on a complete, no version bump and no activity entry;
  · their refusals, each naming every half it fails on (`twin.` for the other) and
    writing nothing: `ACCOUNT_ARCHIVED`, then `ENDING_BALANCE_REQUIRED`, then
    `NO_TRANSACTIONS_ASSIGNED`, then `STATEMENT_NOT_ORDERED`, never prefixed; a line in
    no reconciliation refusing none of them;
  · the lines a close flags for review (`review_lines`), each half its own account's,
    oldest first, from the previous statement's last day to the half's last day, from
    either half: a line in a draft never, a half already completed none, and nothing
    written on a flagged line;
  · one create making both halves, the twin under the request's name and days and its
    own balances; a half created alone over the other half's days becoming its twin;
  · the create's refusals one check at a time, in the contract's order, nothing written;
  · a delete from either half deleting both, its refusals naming each half;
  · a rename and a move from either half writing both, a balance only the half named,
    and the update's refusals naming each half;
  · the list of a whole card from either card account (`statement_of`): both halves of
    every month and a month with one half, in the stated order, each `twin_id` naming
    another item of the answer; and its refusals, `REQUIRED` on both keys with neither
    parameter;
  · one save writing both halves' balances through `twin`, and its refusals writing
    neither half: `NO_TWIN`, a `twin.id` not the current other half (a stale read
    included) `CONCURRENT_CHANGE`, and a `twin` with no balance.

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
    send_order,
)

MARCH = ("2026-03-01", "2026-03-31")
ANSWER_ONLY = ("twin", "warnings", "coverage_gap", "review_lines")


def _read(client, recon: str) -> dict:
    return client.get(f"/reconciliations/{recon}")


def _listed(client, account: str) -> list[dict]:
    return client.get("/reconciliations", params={"account_id": account})["items"]


def _order_state(client, recon: str) -> tuple[str | None, int | None, int | None]:
    read = _read(client, recon)
    return read["twin_id"], read["unplaced_count"], read["shared_place_count"]


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
    send_order(client, rd, [d1, s1])
    assert _order_state(client, rs) == (rd, 0, 0)
    late = scratch.line(dollars, "2026-03-20", -400, recon=rd)
    assert _order_state(client, rs) == (rd, 1, 0)
    assert _order_state(client, rd) == (rs, 1, 0)
    send_order(client, rs, [d1, s1, late])
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
    send_order(client, march, [scratch.line(js, "2026-03-05", -1000, recon=march)])
    send_order(client, april, [scratch.line(jd, "2026-03-06", -300, recon=april)])
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
    own `warnings`, `coverage_gap` and `review_lines`, `[]` on both with no line left
    out (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Atomicity")
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response"), and
    both currencies' lines read one statement's codes. Reverting from either half
    reverts both, its answer carrying `twin` and none of `warnings`, `coverage_gap` and
    `review_lines`;
    reverting a statement whose every half is a draft writes nothing
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert, "Response")
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert, "Revert requires nothing")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    d1 = scratch.line(dollars, "2026-03-06", -300, recon=rd)
    send_order(client, rs, [s1, d1])

    versions = {recon: _read(client, recon)["version"] for recon in (rs, rd)}
    done = client.post(f"/reconciliations/{rd}/complete")
    _assert_answers(client, done, rd, rs)
    for half in (done, done["twin"]):
        assert half["status"] == 2
        assert half["version"] == versions[half["id"]] + 1
        assert {"warnings", "coverage_gap"} <= set(half)
        assert half["review_lines"] == []
    assert client.get(f"/bank-lines/{s1}")["statement_line"] == f"{code}-202603-001"
    assert client.get(f"/bank-lines/{d1}")["statement_line"] == f"{code}-202603-002"

    back = client.post(f"/reconciliations/{rs}/revert")
    _assert_answers(client, back, rs, rd)
    for half in (back, back["twin"]):
        assert half["status"] == 1
        assert half["version"] == versions[half["id"]] + 2
        assert not {"warnings", "coverage_gap", "review_lines"} & set(half)

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
    send_order(client, completed, [line])
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
    Only the half it completes flags its leftover lines: the completed half answers
    `review_lines` `[]` though a line in no reconciliation lies on its last day, which
    stays open, and the draft half its own account's line
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response").
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
        scratch.line(soles, MARCH[1], -50)
        waiting = scratch.line(dollars, "2026-03-10", -70)
        kept, draft_version = _read(client, completed), _read(client, draft)["version"]
        named, other = (completed, draft) if from_completed else (draft, completed)
        done = client.post(f"/reconciliations/{named}/complete")
        _assert_answers(client, done, named, other)
        flagged = {half["id"]: half["review_lines"] for half in (done, done["twin"])}
        assert flagged == {completed: [], draft: [waiting]}
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
        client, lambda: send_order(client, draft, [line, loose]), completed, draft
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


def _entries(client, *resources: str) -> list[list[str]]:
    """The ids of each resource's activity entries, newest first (contract: GET /v1/activity)."""
    return [
        [entry["id"] for entry in client.get("/activity", params={"resource_id": rid})["items"]]
        for rid in resources
    ]


def test_completing_a_statement_already_completed_writes_nothing(client, scratch):
    """A complete sent, from either half, on a card whose halves are both completed is a
    silent no-op: it answers both halves as they read, the half named and its `twin`,
    each with its own `warnings` and `coverage_gap`, and writes nothing, no `version`
    bump on either half or on a line's part and no activity entry
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation")
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Atomicity")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    d1 = scratch.line(dollars, "2026-03-06", -300, recon=rd)
    send_order(client, rs, [s1, d1])
    client.post(f"/reconciliations/{rs}/complete")
    parts = [part["id"] for line in (s1, d1) for part in client.get(f"/bank-lines/{line}")["parts"]]

    halves = [_read(client, recon) for recon in (rs, rd)]
    assert [half["status"] for half in halves] == [2, 2]
    lines = [client.get(f"/bank-lines/{line}") for line in (s1, d1)]
    entries = _entries(client, rs, rd, *parts)
    assert all(entries)
    for named, other in ((rs, rd), (rd, rs)):
        again = client.post(f"/reconciliations/{named}/complete")
        _assert_answers(client, again, named, other)
        for half in (again, again["twin"]):
            assert {"warnings", "coverage_gap"} <= set(half)
        assert [_read(client, recon) for recon in (rs, rd)] == halves
        assert [client.get(f"/bank-lines/{line}") for line in (s1, d1)] == lines
        assert _entries(client, rs, rd, *parts) == entries


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
    (`NO_TRANSACTIONS_ASSIGNED`); then the statement not ordered
    (`STATEMENT_NOT_ORDERED` on `statement_order`, never prefixed: the order is the
    whole statement's). Each answers alone while the checks after it would refuse too.
    A line dated inside the period and left in no reconciliation refuses none of them:
    the complete goes through and flags it on its half's `review_lines`."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)

    def complete(recon: str):
        return lambda: client.post(f"/reconciliations/{recon}/complete")

    def revert(recon: str):
        return lambda: client.post(f"/reconciliations/{recon}/revert")

    # From here on every later check would refuse too: the soles half has no ending
    # balance, and neither half a transaction nor an order; each step below answers
    # alone, so it comes before all of those. The dollar line left in no reconciliation
    # refuses nothing.
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
    for recon in (rs, rd):
        err = _refused_writing_nothing(client, complete(recon), rs, rd)
        assert_refusal(err, 422, "VALIDATION_ERROR", "statement_order", "STATEMENT_NOT_ORDERED")
    send_order(client, rd, [s1, d1])
    done = client.post(f"/reconciliations/{rs}/complete")
    assert (done["status"], done["twin"]["status"]) == (2, 2)
    assert (done["review_lines"], done["twin"]["review_lines"]) == ([], [loose])


def test_a_close_flags_each_halfs_leftover_lines_from_either_half(client, scratch):
    """A complete goes through with lines left in no reconciliation, and flags them for
    review: each half's `review_lines` are its own account's live lines in no
    reconciliation dated from the previous statement's last day to the half's last day,
    oldest first, `review_lines` for the half the path names and `twin.review_lines`
    for the other, from either half. A line on the previous statement's last day is
    flagged, one before it is not, nor one in a draft, nor one after the half's days;
    with no previous statement only the half's own days count. The engine changes
    nothing on a flagged line
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Response")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    february = scratch.reconciliation(soles, "2026-02-01", "2026-02-28")
    rs, rd = scratch.card(soles, dollars, *MARCH)
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=rs)
    d1 = scratch.line(dollars, "2026-03-06", -300, recon=rd)
    send_order(client, rs, [s1, d1])
    s10 = scratch.line(soles, "2026-03-10", -150)
    edge = scratch.line(soles, "2026-02-28", -120)
    d12 = scratch.line(dollars, "2026-03-12", -250)
    d11 = scratch.line(dollars, "2026-03-11", -200)
    # Never flagged: a soles line before February's last day, one in February's draft
    # though dated in March, one after March, and a dollar line in February, where the
    # dollar account has no statement.
    scratch.line(soles, "2026-02-27", -110)
    scratch.line(soles, "2026-03-09", -130, recon=february)
    scratch.line(soles, "2026-04-02", -140)
    scratch.line(dollars, "2026-02-28", -160)
    flagged = {rs: [edge, s10], rd: [d11, d12]}
    lines = [client.get(f"/bank-lines/{line}") for line in (edge, s10, d11, d12)]

    for named, other in ((rs, rd), (rd, rs)):
        done = client.post(f"/reconciliations/{named}/complete")
        assert (done["status"], done["twin"]["status"]) == (2, 2)
        assert done["review_lines"] == flagged[named]
        assert done["twin"]["review_lines"] == flagged[other]
        assert [client.get(f"/bank-lines/{line}") for line in (edge, s10, d11, d12)] == lines
        client.post(f"/reconciliations/{named}/revert")


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
        send_order(client, rs, [s1, d1])
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
    send_order(client, rd, [d1, s1])
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


# ---- the list of a whole card -----------------------------------------------------


def _whole_card(client, account: str) -> list[dict]:
    return client.get("/reconciliations", params={"statement_of": account})["items"]


def test_the_list_reads_a_whole_card_from_either_account(client, scratch):
    """`GET /reconciliations?statement_of=<account>` lists the reconciliations of every
    live account holding that account's statement code: a card's two halves of every
    month, a month with one half on either account included, the same items in the
    same order from either card account, an archived card account included, each
    item exactly its read; every non-null `twin_id` names another item of the same
    answer (contract: GET /v1/reconciliations). They come by `date_start` ascending,
    then by account in the order of `GET /accounts`, then creation time, oldest first
    (contract: "Reconciliations", "Ordering"). On an account with a code and no
    partner, or with none, it lists that account's own, as `?account_id=` does; an id
    naming no account of the caller's lists none. Exactly one of `account_id` and
    `statement_of`: neither is `REQUIRED` on both, both `CONFLICTING_PARAMETERS` on
    `statement_of`, and a non-UUID `INVALID_FORMAT` on its parameter."""
    code, lone_code = free_statement_codes(client, 2)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    april_s = scratch.reconciliation(soles, "2026-04-01", "2026-04-30")
    march = scratch.card(dollars, soles, *MARCH)
    jan_d = scratch.reconciliation(dollars, "2026-01-01", "2026-01-31")
    feb = scratch.card(soles, dollars, "2026-02-01", "2026-02-28")

    listed = client.get("/accounts", params={"include_archived": "true"})["items"]
    rank = {item["id"]: at for at, item in enumerate(listed)}
    first, second = sorted((soles, dollars), key=rank.__getitem__)

    def by_account(pair: tuple[str, str], accounts: tuple[str, str]) -> list[str]:
        on = dict(zip(accounts, pair, strict=True))
        return [on[first], on[second]]

    expected = [
        jan_d,
        *by_account(feb, (soles, dollars)),
        *by_account(march, (dollars, soles)),
        april_s,
    ]
    for account in (soles, dollars):
        items = _whole_card(client, account)
        assert [item["id"] for item in items] == expected, account
        assert items == [_read(client, recon) for recon in expected]
        ids = {item["id"] for item in items}
        for item in items:
            assert item["twin_id"] in ids - {item["id"]} | {None}, item["id"]
        halves = {item["id"]: item["twin_id"] for item in items}
        assert (halves[jan_d], halves[april_s]) == (None, None)
        assert halves[feb[0]] == feb[1] and halves[march[1]] == march[0]

    scratch.archive(dollars)
    assert [item["id"] for item in _whole_card(client, soles)] == expected
    client.post(f"/accounts/{dollars}/unarchive")

    lone = scratch.account("PEN", lone_code)
    plain = scratch.account("PEN")
    for account in (lone, plain):
        scratch.reconciliation(account, *MARCH)
        assert _whole_card(client, account) == _listed(client, account), account
    assert _whole_card(client, str(uuid4())) == []

    for params, reasons in (
        ({}, {"account_id": "REQUIRED", "statement_of": "REQUIRED"}),
        ({"account_id": soles, "statement_of": soles}, {"statement_of": "CONFLICTING_PARAMETERS"}),
        ({"statement_of": "not-a-uuid"}, {"statement_of": "INVALID_FORMAT"}),
        ({"account_id": "not-a-uuid"}, {"account_id": "INVALID_FORMAT"}),
    ):
        err = refused(lambda params=params: client.get("/reconciliations", params=params))
        assert_refusals(err, 422, "VALIDATION_ERROR", reasons)


# ---- one save writes both halves' balances ----------------------------------------


def test_one_save_writes_both_halves_balances(client, scratch):
    """`PUT /reconciliations/{id}` with `twin`, its `id` the `twin_id` read, writes
    the other half's balances in the same write as the half the path names, each half
    bumping its own `version`; beside a name, one request renames the statement and
    sets both halves' balances; `twin` alone leaves the path's half unwritten
    (contract: PUT /v1/reconciliations/{reconciliation_id}, "Both halves' balances in
    one write: `twin`"). Refused, writing neither half: a half with no other half
    (`NO_TWIN` on `twin`), a `twin.id` that is not its current other half, a stale read
    of one since replaced, the path's own or another reconciliation's (`409`
    `CONCURRENT_CHANGE` on `twin.id`), and a `twin` with no balance in it
    (`NOTHING_TO_UPDATE` on `twin`, and `REQUIRED` on `twin.id` for `{}`), each sent
    beside a balance of the path's half."""
    code, lone_code = free_statement_codes(client, 2)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    rs, rd = scratch.card(soles, dollars, *MARCH)

    def put(recon: str, body: dict) -> dict:
        return client.put(f"/reconciliations/{recon}", json_body=body)

    def state() -> list[tuple[int, int, int | None]]:
        return [
            (read["version"], read["beginning_balance_cents"], read["ending_balance_cents"])
            for read in (_read(client, rs), _read(client, rd))
        ]

    (vs, _, _), (vd, _, _) = state()
    twin = _read(client, rs)["twin_id"]
    assert twin == rd
    saved = put(
        rs, {"beginning_balance_cents": 1500, "twin": {"id": twin, "ending_balance_cents": 77}}
    )
    _assert_answers(client, saved, rs, rd)
    assert state() == [(vs + 1, 1500, 0), (vd + 1, 0, 77)]

    named = put(
        rd,
        {
            "name": "contract card balances",
            "ending_balance_cents": 10,
            "twin": {"id": rs, "beginning_balance_cents": 0, "ending_balance_cents": None},
        },
    )
    _assert_answers(client, named, rd, rs)
    assert (named["name"], named["twin"]["name"]) == ("contract card balances",) * 2
    assert state() == [(vs + 2, 0, None), (vd + 2, 0, 10)]

    put(rs, {"twin": {"id": rd, "beginning_balance_cents": 5}})
    assert state() == [(vs + 2, 0, None), (vd + 3, 5, 10)]

    lone_month = scratch.reconciliation(soles, "2026-04-01", "2026-04-30")
    plain_recon = scratch.reconciliation(scratch.account("PEN"), *MARCH)
    lone_recon = scratch.reconciliation(scratch.account("PEN", lone_code), *MARCH)
    for recon in (lone_month, plain_recon, lone_recon):
        err = _refused_writing_nothing(
            client,
            lambda recon=recon: put(
                recon, {"ending_balance_cents": 1, "twin": {"id": rd, "ending_balance_cents": 1}}
            ),
            recon,
            rd,
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", "twin", "NO_TWIN")

    for body, status, error, reasons in (
        ({"id": rs, "ending_balance_cents": 1}, 409, "CONFLICT", {"twin.id": "CONCURRENT_CHANGE"}),
        (
            {"id": lone_month, "ending_balance_cents": 1},
            409,
            "CONFLICT",
            {"twin.id": "CONCURRENT_CHANGE"},
        ),
        ({"id": rd}, 422, "VALIDATION_ERROR", {"twin": "NOTHING_TO_UPDATE"}),
        ({}, 422, "VALIDATION_ERROR", {"twin.id": "REQUIRED"}),
    ):
        err = _refused_writing_nothing(
            client,
            lambda body=body: put(rs, {"ending_balance_cents": 1, "twin": body}),
            rs,
            rd,
        )
        assert_refusals(err, status, error, reasons)

    # A stale read: the other half read here is replaced by another account's, which
    # takes the code and the same days.
    june = ("2026-06-01", "2026-06-30")
    js, stale = scratch.card(soles, dollars, *june)
    client.put(f"/accounts/{dollars}", json_body={"statement_code": None})
    current = scratch.reconciliation(scratch.account("USD", code), *june)
    assert _read(client, js)["twin_id"] == current
    err = _refused_writing_nothing(
        client,
        lambda: put(
            js, {"ending_balance_cents": 1, "twin": {"id": stale, "ending_balance_cents": 1}}
        ),
        js,
        stale,
        current,
    )
    assert_refusal(err, 409, "CONFLICT", "twin.id", "CONCURRENT_CHANGE")
