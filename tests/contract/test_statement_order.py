"""Contract: a statement's order, and the statement line its completion builds.

A statement is a reconciliation on an account with a statement code, together with its
twin for a card: the soles and dollar halves over exactly the same days. The client sends
its lines top to bottom as one list, both currencies mixed, an empty slot for a paper
line the ledger lacks; completing needs that order, and a completed line reads
`<CODE>-<YYYYMM>-<NNN>` (contract: "Reconciliations", "A statement's order"). The
statement-order screen is built on these two routes and the completion refusal, so only
the engine can say what they read, take and refuse. Pinned here:

  · the read: the statement's reconciliations, its places (an empty slot `null`) and
    its unplaced lines, the opening balance always among them;
  · completing is `422` `STATEMENT_NOT_ORDERED` on `statement_order` until every line
    holds its own place: lines with none, a line assigned after the list, and two
    separately ordered halves joined into one card, whose place 1 is held twice;
  · the write: a list replaces the last one, and on a draft only; each line's place is
    its position from 1, and it answers the statement as the read gives it;
  · each refusal of the write, nothing written: `404`, `INVALID_FORMAT` on a non-UUID
    id, `ACCOUNT_ARCHIVED` (before `NO_STATEMENT_CODE`), `NO_STATEMENT_CODE` on the read
    too, `RECONCILIATION_NOT_DRAFT`, and in one `422` `TRAILING_EMPTY_SLOT`,
    `DUPLICATE_IN_REQUEST`, `LINE_NOT_IN_STATEMENT`, `OPENING_BALANCE_NOT_PLACED` and
    `STATEMENT_LINES_MISSING`; the body's own `OUT_OF_RANGE`, `INVALID_FORMAT` and
    `UNKNOWN_FIELD` (`statement_place` beside `places`);
  · the statement line: built on completion on the line and every part, `null` on a
    revert with the place kept, the same again on completing again without a new list,
    and following a change or clearing of the account's code;
  · a card: one list over both currencies sent from either half, read the same from
    either, each half's lines numbered once that half completes; and a code change that
    would join a completed half is `422` `COMPLETED_STATEMENT_JOINED`, nothing written,
    until that half is reverted, after which the whole statement is ordered again.

Each test builds its own accounts under codes no account of the practice user holds, and
undoes everything (conftest.py `scratch`). Gating, target and the real-ledger guard:
conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import assert_refusal, free_statement_codes, refused


def _order(client, recon: str) -> dict:
    return client.get(f"/reconciliations/{recon}/statement-order")


def _send(client, recon: str, places: list[str | None]) -> dict:
    return client.put(f"/reconciliations/{recon}/statement-order", json_body={"places": places})


def _places(order: dict) -> list[tuple[int, str | None]]:
    """Each place and the id of the line it holds, `None` for an empty slot; a line's
    own `statement_place` is the place it is listed under."""
    out = []
    for entry in order["places"]:
        line = entry["bank_line"]
        if line is not None:
            assert line["statement_place"] == entry["place"]
        out.append((entry["place"], None if line is None else line["id"]))
    return out


def _unplaced(order: dict) -> set[str]:
    for line in order["unplaced"]:
        assert line["statement_place"] is None
    return {line["id"] for line in order["unplaced"]}


def _numbered(client, line_id: str) -> tuple[str | None, int | None]:
    """The line's statement line and place, the same on every part of it."""
    line = client.get(f"/bank-lines/{line_id}")
    for part in line["parts"]:
        read = client.get(f"/transactions/{part['id']}")
        assert (read["statement_line"], read["statement_place"]) == (
            line["statement_line"],
            line["statement_place"],
        )
    return line["statement_line"], line["statement_place"]


def _status(client, recon: str) -> tuple[int, int]:
    read = client.get(f"/reconciliations/{recon}")
    return read["status"], read["version"]


def _assert_not_ordered(client, recon: str) -> str:
    """Completing is refused as not ordered, and the reconciliation stays a draft at
    its `version`; the field text, which names what is wrong."""
    before = _status(client, recon)
    err = refused(lambda: client.post(f"/reconciliations/{recon}/complete"))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_order", "STATEMENT_NOT_ORDERED")
    assert _status(client, recon) == before == (1, before[1])
    return err.fields["statement_order"]


# ---- one account -------------------------------------------------------------


def test_a_statement_is_ordered_completed_and_numbered(client, scratch):
    """The read lists the statement: its reconciliation, no places yet, and every line
    unplaced, the opening balance included
    (contract: GET /v1/reconciliations/{reconciliation_id}/statement-order, "Response").
    Completing on an account with a code is refused until every line holds its own
    place (contract: "Reconciliations", "Completing needs the order")
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation"),
    and a line assigned after the list holds none until a new list replaces it
    (contract: "Reconciliations", "Nothing renumbers on its own")
    (contract: "Reconciliations", "A new list replaces the old one"). Each listed line's
    place is its position from 1, an empty slot takes a number and holds no line, the
    opening balance takes none
    (contract: "Reconciliations", "The client sends the statement's lines top to
    bottom, as one list")
    (contract: "Reconciliations", "An empty slot")
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order, "On success (atomic)").
    Completed, every line and part reads `<CODE>-<YYYYMM>-<NNN>` from the code, the
    month of the end day and the place
    (contract: "Reconciliations", "The place becomes the line's statement line")
    (contract: "Transactions (Ledger)", "Bank lines"); a revert makes it `null` and
    keeps the place, completing again brings the same codes back, and a change or
    clearing of the account's code changes or clears them all
    (contract: POST /v1/reconciliations/{reconciliation_id}/revert)
    (contract: "Bank Accounts", "Statement code")."""
    code, other = free_statement_codes(client, 2)
    account = scratch.account("PEN", code)
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    opening = scratch.opening_balance(account, "2026-02-15", recon)
    single = scratch.line(account, "2026-03-05", -1000, recon=recon)
    grouped = scratch.line(account, "2026-03-10", -600, -400, recon=recon)
    income = scratch.line(account, "2026-03-15", 2500, recon=recon)

    order = _order(client, recon)
    assert set(order) == {"reconciliation_ids", "places", "unplaced"}
    assert order["reconciliation_ids"] == [recon]
    assert order["places"] == []
    assert _unplaced(order) == {opening, single, grouped, income}
    _assert_not_ordered(client, recon)

    sent = _send(client, recon, [grouped, None, single, income])
    assert _places(sent) == [(1, grouped), (2, None), (3, single), (4, income)]
    assert _unplaced(sent) == {opening}
    assert _order(client, recon) == sent
    late = scratch.line(account, "2026-03-20", -300, recon=recon)
    assert _unplaced(_order(client, recon)) == {opening, late}
    assert "1 line(s)" in _assert_not_ordered(client, recon)
    sent = _send(client, recon, [grouped, None, single, income, late])
    assert _numbered(client, grouped) == (None, 1)

    expected = {grouped: 1, single: 3, income: 4, late: 5}
    assert client.post(f"/reconciliations/{recon}/complete")["status"] == 2
    for line, place in expected.items():
        assert _numbered(client, line) == (f"{code}-202603-{place:03d}", place)
    assert _numbered(client, opening) == (None, None)

    client.post(f"/reconciliations/{recon}/revert")
    for line, place in expected.items():
        assert _numbered(client, line) == (None, place)

    client.post(f"/reconciliations/{recon}/complete")
    for line, place in expected.items():
        assert _numbered(client, line) == (f"{code}-202603-{place:03d}", place)

    client.put(f"/accounts/{account}", json_body={"statement_code": other})
    for line, place in expected.items():
        assert _numbered(client, line) == (f"{other}-202603-{place:03d}", place)
    client.put(f"/accounts/{account}", json_body={"statement_code": None})
    for line, place in expected.items():
        assert _numbered(client, line) == (None, place)


def test_the_order_list_refusals(client, scratch):
    """Every problem with the list comes in one `422`, each entry keyed `places.<i>`
    from 0: a last entry that is an empty slot (`TRAILING_EMPTY_SLOT`), a line listed
    again (`DUPLICATE_IN_REQUEST`, on the later entry), an id naming no live line of
    this statement, whether no line, one of another reconciliation or one of none
    (`LINE_NOT_IN_STATEMENT`), an opening balance (`OPENING_BALANCE_NOT_PLACED`), and
    on `places` the lines left out (`STATEMENT_LINES_MISSING`, the message counting
    and naming them); the body itself takes 1 to 999 entries (`OUT_OF_RANGE`), each a
    UUID or `null` (`INVALID_FORMAT`), and no other field (`UNKNOWN_FIELD`, as
    `statement_place` is in no request body but this list's)
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order, "Refusals")
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order, "Body")
    (contract: "Reconciliations", "The list names every line of the statement once")
    (contract: "Reconciliations", "At most 999 places")
    (contract: "Transactions (Ledger)", "Bank lines"). Nothing is written: no line
    gains a place or a `version`."""
    (code,) = free_statement_codes(client, 1)
    account = scratch.account("PEN", code)
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    opening = scratch.opening_balance(account, "2026-02-15", recon)
    first = scratch.line(account, "2026-03-05", -1000, recon=recon)
    left_out = scratch.line(account, "2026-03-06", -2000, recon=recon)
    april = scratch.reconciliation(account, "2026-04-01", "2026-04-30")
    elsewhere = scratch.line(account, "2026-04-05", -3000, recon=april)
    unassigned = scratch.line(account, "2026-05-05", -4000)
    lines = (opening, first, left_out, elsewhere, unassigned)
    versions = {line: client.get(f"/bank-lines/{line}")["parts"][0]["version"] for line in lines}
    before = _order(client, recon)

    sent = [first, first, elsewhere, unassigned, opening, str(uuid4()), None]
    err = refused(lambda: _send(client, recon, sent))
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    assert err.reasons == {
        "places.1": "DUPLICATE_IN_REQUEST",
        "places.2": "LINE_NOT_IN_STATEMENT",
        "places.3": "LINE_NOT_IN_STATEMENT",
        "places.4": "OPENING_BALANCE_NOT_PLACED",
        "places.5": "LINE_NOT_IN_STATEMENT",
        "places.6": "TRAILING_EMPTY_SLOT",
        "places": "STATEMENT_LINES_MISSING",
    }
    assert left_out in err.fields["places"]
    assert first not in err.fields["places"]

    for body, key, reason in (
        ({"places": []}, "places", "OUT_OF_RANGE"),
        ({"places": [first, *[None] * 998, left_out]}, "places", "OUT_OF_RANGE"),
        ({"places": ["not-a-uuid", first, left_out]}, "places.0", "INVALID_FORMAT"),
        ({"places": [first, left_out], "statement_place": 1}, "statement_place", "UNKNOWN_FIELD"),
    ):
        err = refused(
            lambda body=body: client.put(
                f"/reconciliations/{recon}/statement-order", json_body=body
            )
        )
        assert_refusal(err, 422, "VALIDATION_ERROR", key, reason)

    assert _order(client, recon) == before
    for line in lines:
        assert client.get(f"/bank-lines/{line}")["parts"][0]["version"] == versions[line]
        assert client.get(f"/bank-lines/{line}")["statement_place"] is None


def test_the_order_routes_refuse_a_reconciliation_they_cannot_order(client, scratch):
    """Both routes answer `404` for an id naming no live reconciliation of the caller's
    (none, or a deleted one) and `422` `INVALID_FORMAT` on `reconciliation_id` for a
    non-UUID, and `409` on `reconciliation_id` (`NO_STATEMENT_CODE`) on an account
    without a code (contract: GET /v1/reconciliations/{reconciliation_id}/statement-order).
    The write is refused, in its order and writing nothing, on an archived account
    (`ACCOUNT_ARCHIVED`, before `NO_STATEMENT_CODE`) and on a completed statement
    (`RECONCILIATION_NOT_DRAFT`), whose order the read still gives
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order, "Refusals")
    (contract: "Reconciliations", "On an archived account the order cannot be set or changed")."""
    (code,) = free_statement_codes(client, 1)
    plain = scratch.account("PEN")
    plain_recon = scratch.reconciliation(plain, "2026-03-01", "2026-03-31")
    plain_line = scratch.line(plain, "2026-03-05", -1000, recon=plain_recon)
    deleted = scratch.reconciliation(plain, "2026-04-01", "2026-04-30")
    client.delete(f"/reconciliations/{deleted}")

    for recon in (str(uuid4()), deleted):
        for call in (
            lambda recon=recon: _order(client, recon),
            lambda recon=recon: _send(client, recon, [plain_line]),
        ):
            err = refused(call)
            assert (err.status, err.code) == (404, "NOT_FOUND")
    for call in (
        lambda: client.get("/reconciliations/not-a-uuid/statement-order"),
        lambda: _send(client, "not-a-uuid", [plain_line]),
    ):
        assert_refusal(
            refused(call), 422, "VALIDATION_ERROR", "reconciliation_id", "INVALID_FORMAT"
        )

    for call in (
        lambda: _order(client, plain_recon),
        lambda: _send(client, plain_recon, [plain_line]),
    ):
        err = refused(call)
        assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "NO_STATEMENT_CODE")

    client.post(f"/accounts/{plain}/archive")
    err = refused(lambda: _send(client, plain_recon, [plain_line]))
    assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "ACCOUNT_ARCHIVED")
    client.post(f"/accounts/{plain}/unarchive")
    assert client.get(f"/bank-lines/{plain_line}")["statement_place"] is None

    coded = scratch.account("PEN", code)
    recon = scratch.reconciliation(coded, "2026-03-01", "2026-03-31")
    line = scratch.line(coded, "2026-03-05", -1000, recon=recon)
    other = scratch.line(coded, "2026-03-06", -2000, recon=recon)
    _send(client, recon, [line, other])
    client.post(f"/accounts/{coded}/archive")
    err = refused(lambda: _send(client, recon, [other, line]))
    assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "ACCOUNT_ARCHIVED")
    client.post(f"/accounts/{coded}/unarchive")

    client.post(f"/reconciliations/{recon}/complete")
    err = refused(lambda: _send(client, recon, [other, line]))
    assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "RECONCILIATION_NOT_DRAFT")
    assert _places(_order(client, recon)) == [(1, line), (2, other)]


# ---- a card: two halves, one statement --------------------------------------


def test_a_card_statement_is_one_order_across_both_currencies(client, scratch):
    """A card is a soles and a dollar account under one code, its statement their two
    reconciliations over exactly the same days
    (contract: "Bank Accounts", "Shared only across currencies")
    (contract: "Reconciliations", "A statement's order"). Either half reads the same
    statement, its `reconciliation_ids` in the accounts' order
    (contract: GET /v1/reconciliations/{reconciliation_id}/statement-order, "Response");
    neither half completes until both halves' lines hold places, and a list leaving out
    the other half's lines is `STATEMENT_LINES_MISSING`; one list from either half
    numbers both currencies mixed, an empty slot between them
    (contract: "Reconciliations", "The client sends the statement's lines top to
    bottom, as one list").
    A completed half's lines read their codes while the draft half's read `null`
    (contract: "Transactions (Ledger)", "Bank lines"), and no list is taken while
    either half is completed (`RECONCILIATION_NOT_DRAFT`)
    (contract: PUT /v1/reconciliations/{reconciliation_id}/statement-order, "Refusals")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    soles_half = scratch.reconciliation(soles, "2026-02-26", "2026-03-25")
    dollar_half = scratch.reconciliation(dollars, "2026-02-26", "2026-03-25")
    s1 = scratch.line(soles, "2026-02-28", -1000, recon=soles_half)
    s2 = scratch.line(soles, "2026-03-20", -2000, recon=soles_half)
    d1 = scratch.line(dollars, "2026-03-01", -300, recon=dollar_half)

    from_soles = _order(client, soles_half)
    assert from_soles == _order(client, dollar_half)
    assert from_soles["reconciliation_ids"] == [soles_half, dollar_half]
    assert _unplaced(from_soles) == {s1, s2, d1}
    _assert_not_ordered(client, soles_half)
    _assert_not_ordered(client, dollar_half)

    err = refused(lambda: _send(client, dollar_half, [s1, s2]))
    assert_refusal(err, 422, "VALIDATION_ERROR", "places", "STATEMENT_LINES_MISSING")
    assert d1 in err.fields["places"]
    assert _order(client, soles_half) == from_soles

    sent = _send(client, dollar_half, [s1, d1, None, s2])
    assert _places(sent) == [(1, s1), (2, d1), (3, None), (4, s2)]
    assert _unplaced(sent) == set()
    assert _order(client, soles_half) == sent

    client.post(f"/reconciliations/{soles_half}/complete")
    assert _numbered(client, s1) == (f"{code}-202603-001", 1)
    assert _numbered(client, s2) == (f"{code}-202603-004", 4)
    assert _numbered(client, d1) == (None, 2)
    err = refused(lambda: _send(client, dollar_half, [d1, s1, s2]))
    assert_refusal(err, 409, "CONFLICT", "reconciliation_id", "RECONCILIATION_NOT_DRAFT")

    client.post(f"/reconciliations/{dollar_half}/complete")
    assert _numbered(client, d1) == (f"{code}-202603-002", 2)


def test_two_ordered_halves_joined_by_their_days_hold_one_place_twice(client, scratch):
    """Two reconciliations ordered apart become one card statement when one is moved
    onto the other's days, and a place both their lines hold is listed once per line
    (contract: GET /v1/reconciliations/{reconciliation_id}/statement-order, "Response");
    completing is refused while two lines hold one place
    (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "Validation"),
    and one new list over both settles it."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    dollars = scratch.account("USD", code)
    march = scratch.reconciliation(soles, "2026-03-01", "2026-03-31")
    later = scratch.reconciliation(dollars, "2026-04-01", "2026-04-30")
    s1 = scratch.line(soles, "2026-03-05", -1000, recon=march)
    d1 = scratch.line(dollars, "2026-03-10", -300, recon=later)
    _send(client, march, [s1])
    _send(client, later, [d1])

    client.put(
        f"/reconciliations/{later}",
        json_body={"date_start": "2026-03-01", "date_end": "2026-03-31"},
    )
    order = _order(client, march)
    assert order["reconciliation_ids"] == [march, later]
    assert sorted(_places(order), key=str) == sorted([(1, s1), (1, d1)], key=str)
    named = _assert_not_ordered(client, later).lower()
    assert "place(s) 1 " in named
    assert "line(s)" not in named

    _send(client, later, [d1, s1])
    client.post(f"/reconciliations/{march}/complete")
    client.post(f"/reconciliations/{later}/complete")
    assert _numbered(client, d1) == (f"{code}-202603-001", 1)
    assert _numbered(client, s1) == (f"{code}-202603-002", 2)


def test_a_code_change_never_joins_a_completed_half(client, scratch):
    """`PUT /accounts/{id}` giving a code that would make one of the account's
    reconciliations the twin of a completed one on the other account holding the code
    is `422` on `statement_code` (`COMPLETED_STATEMENT_JOINED`), nothing written
    (contract: "Bank Accounts", "A code change never joins a completed half")
    (contract: PUT /v1/accounts/{account_id}, "`statement_code`"). Reverted, the two
    drafts join; the joined statement lists the new half's line unplaced, so neither
    half completes until the whole statement's order is sent again
    (contract: "Reconciliations", "Completing needs the order")."""
    (code,) = free_statement_codes(client, 1)
    soles = scratch.account("PEN", code)
    soles_half = scratch.reconciliation(soles, "2026-02-26", "2026-03-25")
    s1 = scratch.line(soles, "2026-03-02", -1000, recon=soles_half)
    _send(client, soles_half, [s1])
    client.post(f"/reconciliations/{soles_half}/complete")
    dollars = scratch.account("USD")
    dollar_half = scratch.reconciliation(dollars, "2026-02-26", "2026-03-25")
    d1 = scratch.line(dollars, "2026-03-03", -300, recon=dollar_half)

    version = client.get(f"/accounts/{dollars}")["version"]
    err = refused(lambda: client.put(f"/accounts/{dollars}", json_body={"statement_code": code}))
    assert_refusal(err, 422, "VALIDATION_ERROR", "statement_code", "COMPLETED_STATEMENT_JOINED")
    after = client.get(f"/accounts/{dollars}")
    assert (after["statement_code"], after["version"]) == (None, version)
    assert _numbered(client, s1) == (f"{code}-202603-001", 1)

    client.post(f"/reconciliations/{soles_half}/revert")
    client.put(f"/accounts/{dollars}", json_body={"statement_code": code})
    order = _order(client, dollar_half)
    assert order["reconciliation_ids"] == [soles_half, dollar_half]
    assert (_places(order), _unplaced(order)) == ([(1, s1)], {d1})
    _assert_not_ordered(client, soles_half)

    _send(client, dollar_half, [d1, s1])
    client.post(f"/reconciliations/{soles_half}/complete")
    client.post(f"/reconciliations/{dollar_half}/complete")
    assert _numbered(client, d1) == (f"{code}-202603-001", 1)
    assert _numbered(client, s1) == (f"{code}-202603-002", 2)
