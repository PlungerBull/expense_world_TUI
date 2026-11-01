"""Contract: an account is made with its currencies in one write, against a real engine.

`POST /accounts` takes `{id, name, currencies: [{currency_code}, ...]}` and makes the
account and every currency at once, all or nothing
(contract: POST /v1/accounts). Manage ▸ Accounts sends it, so only the engine can say what
it answers and in which order it refuses.

What it pins:

1. A bank account and a person (`is_person: true`), each holding soles and dollars, are `201`
   in one write: the currencies read in `currency_code` order whatever order they were sent
   in, each at `current_balance_cents` `0` with no opening balance, `version` `1`, the default
   colour, no statement code, listed where their kind is listed (contract: POST /v1/accounts,
   "Response").
2. `currency_code` and `holder_id` on the body are `UNKNOWN_FIELD`, and an unknown field in an
   entry of `currencies` is `UNKNOWN_FIELD` keyed `currencies.<i>.<field>`.
3. The refusals in the engine's order (contract: POST /v1/accounts, "Validation"), each step
   proven against the next by one body breaking both, and every refusal leaving every
   account the caller has as it was (`refused_writing_nothing`):
   the request's shape, answered alone (`currencies` `null`, empty or over ten entries, an
   unknown field, a malformed `statement_code`); then in one answer `name` `EMPTY`, `color`
   `INVALID_FORMAT` and `DUPLICATE_CURRENCY` on the later entry; then `ID_EXISTS` on `id`; then
   `LIMIT_REACHED` on `id`; then `UNSUPPORTED_VALUE` on every such entry; then `NAME_EXISTS`
   on `name` (either kind, ignoring case); then `STATEMENT_CODE_EXISTS`.
4. An account at the cap of 100 (contract: "Base Conventions", "Create caps"): the cap counts
   archived accounts, a deleted one frees a place, and it answers after `ID_EXISTS` and before
   the rules that follow it.

What it leaves out:

  · `ID_EXISTS` for an id that was once a currency's own record: no response carries such an
    id any more, and the practice user holds no older activity entry that names one
    (contract: GET /v1/activity, "Older and restored entries"): its `currency` entries carry no
    record id of their own and it has no `account` entry of a currency, so a test would have
    to guess an id. A deleted account's id is tested instead, and a live account's.
  · An account's `id` another user holds, answered only after every other refusal: the suite
    has one shared practice user, and the reserved-names one is for the tests that draw
    `RESERVED_NAME_HELD` alone (docs/decisions.md), so no test holds an id as a second user.
  · Two creates sent at the same moment: a live test cannot land two requests together.

Every account is fresh per run (named by its UUID) and removed by the `scratch` fixture.
Gating, target resolution and the real-ledger guard live in conftest.py.
"""

from uuid import uuid4

from tests.contract.conftest import (
    account_body,
    all_accounts,
    assert_refusal,
    assert_refusals,
    free_statement_codes,
    refused_writing_nothing,
)

CAP = 100
_BLUE = "#3b82f6"


def _post(client, scratch, body: dict) -> dict:
    """Sends `body`, which `scratch` removes after the test whatever the answer."""
    scratch.accounts.append(body["id"])
    return client.post("/accounts", json_body=body)


def _refused(client, scratch, body: dict):
    """The refusal of `body`, with every account the caller has read the same after."""
    scratch.accounts.append(body["id"])
    return refused_writing_nothing(client, lambda: client.post("/accounts", json_body=body))


def _validation(err, reasons: dict[str, str]) -> None:
    assert_refusals(err, 422, "VALIDATION_ERROR", reasons)


def _currencies_of(account: dict) -> list[tuple[str, int, object]]:
    return [
        (c["currency_code"], c["current_balance_cents"], c["opening_balance_transaction_id"])
        for c in account["currencies"]
    ]


def test_a_bank_account_and_a_person_are_made_with_their_currencies_in_one_write(
    client, statuses, scratch
):
    """Soles and dollars, sent in either order, are one `201` each: the currencies read PEN
    before USD at `0` with no opening balance, the account at `version` `1`, with the
    default colour and no code, and the read of the account is the answer. The bank account
    is listed without `include_people` and in the dashboard's `bank_accounts`, the person only
    with it and in `people`, its currencies in its row
    (contract: POST /v1/accounts, "Response")."""
    bank = account_body("PEN", "USD", code=free_statement_codes(client, 1)[0])
    person = account_body("USD", "PEN", is_person=True)
    before = {a["id"] for a in all_accounts(client)}

    made_bank = _post(client, scratch, bank)
    made_person = _post(client, scratch, person)
    assert statuses[-2:] == [201, 201]

    for made, body, is_person in ((made_bank, bank, False), (made_person, person, True)):
        assert made["id"] == body["id"]
        assert made["name"] == body["name"]
        assert made["is_person"] is is_person
        assert made["version"] == 1
        assert made["color"] == _BLUE
        assert made["is_archived"] is False
        assert _currencies_of(made) == [("PEN", 0, None), ("USD", 0, None)]
        assert client.get(f"/accounts/{body['id']}") == made
    assert made_bank["statement_code"] == bank["statement_code"]
    assert made_person["statement_code"] is None

    assert {a["id"] for a in all_accounts(client)} == before | {bank["id"], person["id"]}
    listed = {a["id"] for a in client.get("/accounts")["items"]}
    assert bank["id"] in listed
    assert person["id"] not in listed
    with_people = client.get("/accounts", params={"include_people": "true"})["items"]
    assert person["id"] in {a["id"] for a in with_people}
    dashboard = client.get("/dashboard")
    rows = {row["id"]: row for key in ("bank_accounts", "people") for row in dashboard[key]}
    assert bank["id"] in {row["id"] for row in dashboard["bank_accounts"]}
    assert person["id"] in {row["id"] for row in dashboard["people"]}
    for account_id in (bank["id"], person["id"]):
        assert [c["currency_code"] for c in rows[account_id]["currencies"]] == ["PEN", "USD"]


def test_a_currency_code_or_a_holder_on_the_body_is_an_unknown_field(client, scratch):
    """The old per-currency names are refused on the body, and so is an unknown field in an
    entry of `currencies`, keyed by its index, whichever entry holds it
    (contract: POST /v1/accounts, "Forbidden")."""
    for field in ("currency_code", "holder_id"):
        err = _refused(client, scratch, account_body("PEN", **{field: "PEN"}))
        assert_refusal(err, 422, "VALIDATION_ERROR", field, "UNKNOWN_FIELD")

    body = account_body("PEN", "USD")
    body["currencies"][1]["bogus"] = 1
    err = _refused(client, scratch, body)
    assert_refusal(err, 422, "VALIDATION_ERROR", "currencies.1.bogus", "UNKNOWN_FIELD")

    body = account_body("PEN", "USD")
    body["currencies"][0]["holder_id"] = str(uuid4())
    err = _refused(client, scratch, body)
    assert_refusal(err, 422, "VALIDATION_ERROR", "currencies.0.holder_id", "UNKNOWN_FIELD")


def test_the_requests_shape_is_answered_alone_before_anything_it_shares_a_body_with(
    client, scratch
):
    """Each body here also breaks a later rule (an empty name, a held name or code), and the
    answer names the shape alone: `currencies` empty or longer than ten `OUT_OF_RANGE`,
    `null` `INVALID_FORMAT`, an unknown field, a malformed `statement_code`
    (contract: POST /v1/accounts, "Validation")."""
    held = scratch.account("PEN")
    held_name = client.get(f"/accounts/{held}")["name"]
    broken = {"name": "   ", "color": "red"}

    err = _refused(client, scratch, account_body(**broken, currencies=[]))
    _validation(err, {"currencies": "OUT_OF_RANGE"})

    eleven = [{"currency_code": "PEN"}] * 11
    err = _refused(client, scratch, account_body(**broken, currencies=eleven))
    _validation(err, {"currencies": "OUT_OF_RANGE"})

    err = _refused(client, scratch, account_body(**broken, currencies=None))
    _validation(err, {"currencies": "INVALID_FORMAT"})

    err = _refused(client, scratch, account_body("PEN", **broken, bogus=1))
    _validation(err, {"bogus": "UNKNOWN_FIELD"})

    err = _refused(client, scratch, account_body("PEN", name=held_name.upper(), code="sig"))
    _validation(err, {"statement_code": "INVALID_FORMAT"})

    err = _refused(client, scratch, account_body("PEN", name="   ", code="sig"))
    _validation(err, {"statement_code": "INVALID_FORMAT"})


def test_an_empty_name_a_malformed_colour_and_a_repeated_currency_are_answered_together(
    client, scratch
):
    """Past the shape, the three rules that read the request alone are answered in one
    answer naming each: `name` `EMPTY`, `color` `INVALID_FORMAT`, and the later entry of a
    repeated currency `DUPLICATE_CURRENCY`; each also alone, and a repeated currency that
    is also unsupported is answered as repeated, the later rule not reached
    (contract: POST /v1/accounts, "Validation")."""
    err = _refused(client, scratch, account_body("PEN", "PEN", name="   ", color="red"))
    _validation(
        err,
        {
            "name": "EMPTY",
            "color": "INVALID_FORMAT",
            "currencies.1.currency_code": "DUPLICATE_CURRENCY",
        },
    )

    err = _refused(client, scratch, account_body("PEN", "USD", "USD"))
    _validation(err, {"currencies.2.currency_code": "DUPLICATE_CURRENCY"})

    err = _refused(client, scratch, account_body("EUR", "EUR"))
    _validation(err, {"currencies.1.currency_code": "DUPLICATE_CURRENCY"})

    err = _refused(client, scratch, account_body("PEN", name=""))
    _validation(err, {"name": "EMPTY"})

    err = _refused(client, scratch, account_body("PEN", color="#12345"))
    _validation(err, {"color": "INVALID_FORMAT"})


def test_a_taken_id_is_refused_before_every_rule_after_the_requests_shape(client, scratch):
    """A live account's id sent again, and a deleted account's id, are `409` `ID_EXISTS` on
    `id` even when the body also holds an unsupported currency, the name and the code of the
    live account; the same id with an empty name is answered `EMPTY`, the request's own rule
    first (contract: POST /v1/accounts, "Validation")."""
    code = free_statement_codes(client, 1)[0]
    live = account_body("PEN", "USD", code=code)
    _post(client, scratch, live)

    again = {**live, "currencies": [{"currency_code": "EUR"}]}
    err = _refused(client, scratch, again)
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")

    err = _refused(client, scratch, {**live, "name": " "})
    _validation(err, {"name": "EMPTY"})

    gone = account_body("PEN")
    _post(client, scratch, gone)
    client.delete(f"/accounts/{gone['id']}")
    assert gone["id"] not in {a["id"] for a in all_accounts(client)}
    err = _refused(client, scratch, {**gone, "currencies": [{"currency_code": "EUR"}]})
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")
    err = _refused(client, scratch, gone)
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")


def test_the_account_cap_counts_archived_accounts_and_answers_after_a_taken_id(client, scratch):
    """With 100 accounts, a deleted one not counting and an archived one counting, a new id
    is `422` `LIMIT_REACHED` on `id` (reason `CAP_REACHED`) though its name, its code and its
    currency would be refused later, while a live account's id sent again is `ID_EXISTS` and an
    empty name is `EMPTY`, both first; a deleted account makes room for exactly one
    (contract: "Base Conventions", "Create caps")."""
    code = free_statement_codes(client, 1)[0]
    held = account_body("PEN", code=code)
    _post(client, scratch, held)
    for _ in range(CAP - len(all_accounts(client))):
        _post(client, scratch, account_body("PEN"))
    everyone = all_accounts(client)
    assert len(everyone) == CAP

    scratch.archive(held["id"])
    over = account_body("EUR", name=held["name"].upper(), code=code)
    err = _refused(client, scratch, over)
    assert_refusal(err, 422, "LIMIT_REACHED", "id", "CAP_REACHED")

    err = _refused(client, scratch, {**held, "currencies": [{"currency_code": "EUR"}]})
    assert_refusal(err, 409, "CONFLICT", "id", "ID_EXISTS")
    err = _refused(client, scratch, account_body("PEN", name=" "))
    _validation(err, {"name": "EMPTY"})

    spare = next(i for i in scratch.accounts if i != held["id"])
    client.delete(f"/accounts/{spare}")
    assert len(all_accounts(client)) == CAP - 1
    made = _post(client, scratch, account_body("USD"))
    assert len(all_accounts(client)) == CAP
    assert [c["currency_code"] for c in made["currencies"]] == ["USD"]
    err = _refused(client, scratch, account_body("PEN"))
    assert_refusal(err, 422, "LIMIT_REACHED", "id", "CAP_REACHED")


def test_an_unsupported_currency_is_named_on_every_entry_before_a_held_name_or_code(
    client, scratch
):
    """`EUR` and a lower-case `usd` are each `UNSUPPORTED_VALUE` on their own entry, every
    such entry named in one answer, a supported one beside them not; the answer comes before
    a name and a code the caller's accounts already hold
    (contract: POST /v1/accounts, "Validation")."""
    code = free_statement_codes(client, 1)[0]
    held = scratch.account("PEN", code=code)
    held_name = client.get(f"/accounts/{held}")["name"]

    err = _refused(client, scratch, account_body("EUR"))
    _validation(err, {"currencies.0.currency_code": "UNSUPPORTED_VALUE"})

    err = _refused(client, scratch, account_body("EUR", "PEN", "GBP"))
    _validation(
        err,
        {
            "currencies.0.currency_code": "UNSUPPORTED_VALUE",
            "currencies.2.currency_code": "UNSUPPORTED_VALUE",
        },
    )

    err = _refused(client, scratch, account_body("usd"))
    _validation(err, {"currencies.0.currency_code": "UNSUPPORTED_VALUE"})

    err = _refused(client, scratch, account_body("EUR", name=held_name, code=code))
    _validation(err, {"currencies.0.currency_code": "UNSUPPORTED_VALUE"})


def test_a_held_name_is_refused_in_either_kind_ignoring_case_before_a_held_code(client, scratch):
    """A name a bank account holds is `409` `NAME_EXISTS` on `name` for a bank account and for
    a person, and a person's for a bank account, upper or lower case; the answer comes before
    a held `statement_code`, which alone is `STATEMENT_CODE_EXISTS` on `statement_code`
    whatever the other's kind; a deleted account's name and code are free again
    (contract: POST /v1/accounts, "Validation")."""
    bank_code, person_code = free_statement_codes(client, 2)
    bank = scratch.account("PEN", code=bank_code)
    person = scratch.account("PEN", "USD", person=True, code=person_code)
    bank_name = client.get(f"/accounts/{bank}")["name"]
    person_name = client.get(f"/accounts/{person}")["name"]

    for held_name in (bank_name, bank_name.upper(), person_name, person_name.upper()):
        for is_person in (False, True):
            body = account_body("USD", name=held_name, is_person=is_person)
            err = _refused(client, scratch, body)
            assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")

    both = account_body("PEN", name=bank_name.upper(), code=person_code)
    err = _refused(client, scratch, both)
    assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")

    for held_code in (bank_code, person_code):
        for is_person in (False, True):
            body = account_body("PEN", code=held_code, is_person=is_person)
            err = _refused(client, scratch, body)
            assert_refusal(err, 409, "CONFLICT", "statement_code", "STATEMENT_CODE_EXISTS")

    client.delete(f"/accounts/{bank}")
    client.delete(f"/accounts/{person}")
    again = _post(client, scratch, account_body("PEN", name=bank_name, code=bank_code))
    assert again["name"] == bank_name
    assert again["statement_code"] == bank_code
    err = _refused(client, scratch, account_body("PEN", name=bank_name))
    assert_refusal(err, 409, "CONFLICT", "name", "NAME_EXISTS")
