"""Contract: the whole-line write, `PUT /v1/bank-lines/{bank_line_id}`.

One write gives a bank line its fields and its complete set of parts: a kept part keeps
its id, a new id makes a new part, and a part left out is deleted
(contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). The Edit form saves through
it, its body built by expense/bank_line_write.py, so only the engine can say what it
keeps, takes and refuses. Pinned here:

  · a part kept, one added and one dropped in one write: the kept part keeps its id
    and is updated in place, the new one is created on the line with the line's
    fields, the dropped one is deleted, and the answer is the line as read plus
    `created_part_ids` and `deleted_part_ids`;
  · a line taken back to one part, the other deleted;
  · the total: outside a completed reconciliation the parts may add up to a new
    total and the account's balance moves by the difference; inside one the parts
    may be redistributed, mixing directions, a part created there joining it and a
    part dropped there deleted, while a set that misses the line's total is
    `SPLIT_TOTAL_MISMATCH` on `parts` and every `parts.<i>.amount_cents`, beside
    `SEALED_PERIOD` on the `parts.<i>.id` of a part it would create, nothing written;
  · the locked line fields on a line in a completed reconciliation: each of `title`,
    `date`, `account_id`, `operation_code` and `reconciliation_id` sent is `LOCKED`,
    at its current value too, every one named when sent together, and the parts'
    refusal answered beside the lock; an empty `operation_code` may be filled once;
  · a kept part's hashtags: a part sent with every value as held and no
    `hashtag_ids` is not written, one sent with its own `hashtag_ids` unchanged is,
    `[]` puts it on the pending hashtag, and the app's own `kept_part` sends the
    hashtags only when the set changed;
  · a replay under the same idempotency key answers exactly as the first send and
    writes once; the same key with another body is `409` `IDEMPOTENCY_KEY_REUSED`.

Elsewhere: `statement_line` and `statement_place` refused in its body
(test_line_codes_and_statement_lines.py), `ID_EXISTS` on a taken part id
(test_create_sent_again.py), an opening balance's line, an archived account's line and
`edit_limits` (test_bank_line_edit_limits.py, and an archived account's rows under the
transaction routes in test_resources_lifecycle.py), the pending hashtag beside another
(test_pending_hashtag.py) and the Edit form's own path (test_bank_lines.py).

Each test builds its own accounts and undoes everything (conftest.py `scratch`). Gating,
target and the real-ledger guard: conftest.py.
"""

from types import SimpleNamespace
from uuid import uuid4

from expense import http as http_module
from expense.bank_line_write import kept_part, line_body
from expense.errors import EngineError
from expense.formatting import signed_cents
from expense.reads import pending_hashtag_of
from tests.contract.conftest import read_signed, refused

#: The keys the write's answer adds to the line as `GET /bank-lines/{id}` reads it
#: (contract: PUT /v1/bank-lines/{bank_line_id}, "Response").
ANSWER_EXTRAS = {"changed_parts", "created_part_ids", "deleted_part_ids"}


def _line(client, line_id: str) -> dict:
    return client.get(f"/bank-lines/{line_id}")


def _versions(client, line_id: str) -> dict[str, int]:
    return {p["id"]: p["version"] for p in _line(client, line_id)["parts"]}


def _write(client, line_id: str, body: dict) -> dict:
    return client.put(f"/bank-lines/{line_id}", json_body=body)


def _new_id(scratch) -> str:
    """A fresh part id, kept for cleanup before any write can create it."""
    new_id = str(uuid4())
    scratch.transactions.append(new_id)
    return new_id


def test_one_write_keeps_a_part_adds_one_and_drops_one(client, scratch):
    """The kept part keeps its id and takes the values sent, the new id is created on
    the line with the line's title, date, account, operation code and line code, and
    the part left out is deleted; the answer is the line as `GET /bank-lines/{id}`
    reads it after the write, plus the ids created and deleted, and no kept part's line
    fields changed (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-05", -6000, -4000)
    kept, dropped = scratch.transactions[-2:]
    before = {p["id"]: p for p in _line(client, line)["parts"]}
    added = _new_id(scratch)

    answer = _write(
        client,
        line,
        {
            "parts": [
                {"id": kept, "amount_cents": -5000, "description": "kept"},
                {"id": added, "amount_cents": -5000},
            ]
        },
    )
    assert answer["created_part_ids"] == [added]
    assert answer["deleted_part_ids"] == [dropped]
    assert answer["changed_parts"] == []
    assert {k: v for k, v in answer.items() if k not in ANSWER_EXTRAS} == _line(client, line)
    assert (answer["id"], answer["line_code"]) == (line, before[kept]["line_code"])
    assert (answer["net_cents"], answer["part_count"]) == (-10000, 2)
    assert {p["id"] for p in answer["parts"]} == {kept, added}

    mine = read_signed(client, kept)
    assert (mine["amount_cents"], mine["description"]) == (-5000, "kept")
    assert mine["version"] == before[kept]["version"] + 1
    new = read_signed(client, added)
    assert new["amount_cents"] == -5000
    for key in ("bank_line_id", "line_code", "title", "date", "account_id", "operation_code"):
        assert new[key] == before[kept][key], key
    err = refused(lambda: client.get(f"/transactions/{dropped}"))
    assert err.status == 404


def test_a_line_goes_back_to_one_part(client, scratch):
    """A two-part line sent one part, at the line's whole total, keeps that part and
    deletes the other: the line stays, one row under its own id
    (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part not sent is deleted")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-06", -6000, -4000)
    kept, dropped = scratch.transactions[-2:]

    answer = _write(client, line, {"parts": [{"id": kept, "amount_cents": -10000}]})
    assert (answer["created_part_ids"], answer["deleted_part_ids"]) == ([], [dropped])
    assert (answer["id"], answer["part_count"], answer["net_cents"]) == (line, 1, -10000)
    assert [p["id"] for p in answer["parts"]] == [kept]
    listed = client.get("/transactions", params={"bank_line_id": line})["items"]
    assert [t["id"] for t in listed] == [kept]


def test_outside_a_completed_reconciliation_the_total_may_change(client, scratch):
    """In a draft the parts may add up to a new total: the line takes it, and the
    account's balance moves by the difference
    (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")."""
    account = scratch.account()
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    line = scratch.line(account, "2026-03-07", -6000, -4000, recon=recon)
    one, two = scratch.transactions[-2:]
    balance = client.get(f"/accounts/{account}")["current_balance_cents"]

    answer = _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -7000}, {"id": two, "amount_cents": -5000}]},
    )
    assert answer["net_cents"] == -12000
    assert client.get(f"/accounts/{account}")["current_balance_cents"] == balance - 2000
    assert {p["reconciliation_id"] for p in answer["parts"]} == {recon}


def test_inside_a_completed_reconciliation_the_total_is_kept(client, scratch):
    """Inside a completed reconciliation the parts' signed sum must equal the line's
    total: redistributed amounts are taken, directions may mix, a part created there
    joins the reconciliation and a part dropped there is deleted. A set that misses the
    total is `422` `SPLIT_TOTAL_MISMATCH` on `parts` and every `parts.<i>.amount_cents`,
    the message stating both totals, and a part it would create is `SEALED_PERIOD` on
    its `parts.<i>.id`, in the same answer; nothing is written
    (contract: PUT /v1/bank-lines/{bank_line_id}, "The total")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Sealed periods")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Refusals, in order")."""
    account = scratch.account()
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    line = scratch.line(account, "2026-03-08", -6000, -4000, recon=recon)
    one, two = scratch.transactions[-2:]
    client.post(f"/reconciliations/{recon}/complete")

    def amounts() -> dict[str, int]:
        return {p["id"]: signed_cents(p) for p in _line(client, line)["parts"]}

    _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -7000}, {"id": two, "amount_cents": -3000}]},
    )
    assert amounts() == {one: -7000, two: -3000}
    _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -12000}, {"id": two, "amount_cents": 2000}]},
    )
    assert amounts() == {one: -12000, two: 2000}

    added = _new_id(scratch)
    answer = _write(
        client,
        line,
        {"parts": [{"id": one, "amount_cents": -5000}, {"id": added, "amount_cents": -5000}]},
    )
    assert (answer["created_part_ids"], answer["deleted_part_ids"]) == ([added], [two])
    assert client.get(f"/transactions/{added}")["reconciliation_id"] == recon
    assert _line(client, line)["net_cents"] == -10000

    before = _line(client, line)
    err = refused(
        lambda: _write(
            client,
            line,
            {
                "parts": [
                    {"id": one, "amount_cents": -8000},
                    {"id": added, "amount_cents": -3000},
                ]
            },
        )
    )
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    assert err.reasons == {
        "parts": "SPLIT_TOTAL_MISMATCH",
        "parts.0.amount_cents": "SPLIT_TOTAL_MISMATCH",
        "parts.1.amount_cents": "SPLIT_TOTAL_MISMATCH",
    }
    assert "-10000" in err.fields["parts"] and "-11000" in err.fields["parts"]

    extra = _new_id(scratch)
    err = refused(
        lambda: _write(
            client,
            line,
            {
                "parts": [
                    {"id": one, "amount_cents": -5000},
                    {"id": added, "amount_cents": -5000},
                    {"id": extra, "amount_cents": -1000},
                ]
            },
        )
    )
    assert (err.status, err.code) == (422, "VALIDATION_ERROR")
    assert err.reasons["parts"] == "SPLIT_TOTAL_MISMATCH"
    assert err.reasons["parts.2.id"] == "SEALED_PERIOD"
    assert _line(client, line) == before


def test_a_line_in_a_completed_reconciliation_keeps_its_line_fields(client, scratch):
    """On a line in a completed reconciliation every line field sent is `422`
    `LOCKED` on its key, at its current value too, and all of them are named when sent
    together; with `parts` the parts' refusal is answered beside the lock. A
    `null` `operation_code` may be filled, and once set it is locked like the rest.
    Nothing is written on a refusal
    (contract: PUT /v1/transactions/{transaction_id}, "Field locking")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Rules")."""
    account = scratch.account()
    other = scratch.account()
    recon = scratch.reconciliation(account, "2026-03-01", "2026-03-31")
    line = scratch.line(account, "2026-03-09", -6000, -4000, recon=recon)
    one, two = scratch.transactions[-2:]
    client.post(f"/reconciliations/{recon}/complete")
    title = _line(client, line)["parts"][0]["title"]

    code = f"OP-{uuid4().hex[:10]}"
    filled = _write(client, line, {"operation_code": code})
    assert filled["operation_code"] == code
    before = _line(client, line)

    sent_alone = [
        ({"title": title}, "title"),
        ({"title": "renamed"}, "title"),
        ({"date": scratch.noon("2026-03-10")}, "date"),
        ({"account_id": other}, "account_id"),
        ({"operation_code": code}, "operation_code"),
        ({"operation_code": None}, "operation_code"),
        ({"reconciliation_id": recon}, "reconciliation_id"),
        ({"reconciliation_id": None}, "reconciliation_id"),
    ]
    for body, key in sent_alone:
        err = refused(lambda body=body: _write(client, line, body))
        assert (err.status, err.code) == (422, "VALIDATION_ERROR"), body
        assert err.reasons == {key: "LOCKED"}, (body, err.reasons)

    together = {
        "title": "renamed",
        "date": scratch.noon("2026-03-10"),
        "account_id": other,
        "operation_code": f"{code}-b",
        "reconciliation_id": None,
    }
    err = refused(lambda: _write(client, line, together))
    assert err.reasons == dict.fromkeys(together, "LOCKED")

    beside = {
        "title": "renamed",
        "parts": [{"id": one, "amount_cents": -8000}, {"id": two, "amount_cents": -3000}],
    }
    err = refused(lambda: _write(client, line, beside))
    assert err.reasons == {
        "title": "LOCKED",
        "parts": "SPLIT_TOTAL_MISMATCH",
        "parts.0.amount_cents": "SPLIT_TOTAL_MISMATCH",
        "parts.1.amount_cents": "SPLIT_TOTAL_MISMATCH",
    }
    assert _line(client, line) == before


def test_a_kept_parts_hashtags_are_written_whenever_sent(client, scratch):
    """A kept part sent with every value it holds and no `hashtag_ids` is not
    written; sent with `hashtag_ids`, even its own set, it is written, the other part
    not; `[]` puts it on the pending hashtag. So the app's `kept_part` leaves the
    hashtags out of a part whose set did not change, and that write changes nothing
    (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").
    """
    account = scratch.account()
    line = scratch.line(account, "2026-03-11", -6000, -4000)
    one, two = scratch.transactions[-2:]
    tag = str(uuid4())
    client.post("/hashtags", json_body={"id": tag, "name": f"contract-line-{tag[:8]}"})
    try:
        client.put(f"/transactions/{one}", json_body={"hashtag_ids": [tag]})
        pending = pending_hashtag_of(client.get("/hashtags")["items"])
        assert pending is not None
        pending_id = pending[0]

        as_held = [{"id": one, "amount_cents": -6000}, {"id": two, "amount_cents": -4000}]
        versions = _versions(client, line)
        _write(client, line, {"parts": as_held})
        assert _versions(client, line) == versions

        _write(client, line, {"parts": [{**as_held[0], "hashtag_ids": [tag]}, as_held[1]]})
        assert _versions(client, line) == {one: versions[one] + 1, two: versions[two]}
        assert client.get(f"/transactions/{one}")["hashtag_ids"] == [tag]

        _write(client, line, {"parts": [{**as_held[0], "hashtag_ids": []}, as_held[1]]})
        assert client.get(f"/transactions/{one}")["hashtag_ids"] == [pending_id]

        # The app's body: hashtags only when the set changed.
        def app_body(hashtags: dict[str, list[str]]) -> dict:
            held = {p["id"]: p for p in _line(client, line)["parts"]}
            return line_body(
                [
                    kept_part(
                        held[part_id],
                        amount_cents=signed_cents(held[part_id]),
                        category_id=None,
                        description=None,
                        hashtag_ids=hashtags.get(part_id, held[part_id]["hashtag_ids"]),
                        pending_hashtag_id=pending_id,
                    )
                    for part_id in (one, two)
                ]
            )

        unchanged = app_body({})
        assert all("hashtag_ids" not in part for part in unchanged["parts"])
        versions = _versions(client, line)
        _write(client, line, unchanged)
        assert _versions(client, line) == versions

        changed = app_body({one: [tag]})
        assert [("hashtag_ids" in part) for part in changed["parts"]] == [True, False]
        _write(client, line, changed)
        assert _versions(client, line) == {one: versions[one] + 1, two: versions[two]}
        assert client.get(f"/transactions/{one}")["hashtag_ids"] == [tag]
    finally:
        try:
            client.delete(f"/hashtags/{tag}")
        except EngineError:
            pass


def test_a_replay_answers_the_same_and_writes_once(client, scratch, monkeypatch):
    """A write sent again under the same idempotency key answers exactly as the first
    send did, and the line is written once: the kept part's `version` up by one, the
    new part created once, the dropped part deleted once. The same key with another
    body is `409` on `X-Idempotency-Key` (`IDEMPOTENCY_KEY_REUSED`)
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Response")
    (contract: "Base Conventions", "Idempotency")."""
    account = scratch.account()
    line = scratch.line(account, "2026-03-12", -6000, -4000)
    kept, dropped = scratch.transactions[-2:]
    versions = _versions(client, line)
    added = _new_id(scratch)
    body = {"parts": [{"id": kept, "amount_cents": -7000}, {"id": added, "amount_cents": -3000}]}

    key = uuid4()
    monkeypatch.setattr(http_module, "uuid", SimpleNamespace(uuid4=lambda: key))
    try:
        first = _write(client, line, body)
        replayed = _write(client, line, body)
        other = {"parts": [{"id": kept, "amount_cents": -10000}]}
        err = refused(lambda: _write(client, line, other))
    finally:
        monkeypatch.undo()

    assert replayed == first
    assert (first["created_part_ids"], first["deleted_part_ids"]) == ([added], [dropped])
    assert _versions(client, line) == {kept: versions[kept] + 1, added: 1}
    assert (err.status, err.code) == (409, "CONFLICT")
    assert err.reasons == {"X-Idempotency-Key": "IDEMPOTENCY_KEY_REUSED"}
