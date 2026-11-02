# Caught up with contract f82426fb0a099676: the terminal app's live contract suite tests an account made with its currencies, a currency added and removed, and a transaction's currency (part 5 of 7)

2026-11-02

## Covers

`e020782e3579d011` → `f82426fb0a099676` (the versions between are listed in the reply for parts
3 and 4), your hand-off of 2026-10-29, "An account holds its currencies: every route names an
account and a currency code; holders are gone": what is new about an account, as the live
contract suite proves it against your practice engine. That is making an account with its
currencies, adding and removing a currency, editing and deleting the account whole, a
transaction's currency, the old names refused, an account's closed days for a currency added
later, and the account's reads and the activity entries its writes leave.

## Done when, checked

All checked against the practice engine on 2026-11-02:
- the live contract suite: 328 passed. The one failure is the suite's own check that every
  contract citation in this repo resolves, failing on citations in the app's statement screens
  and their unit tests, which part 7 rewrites;
- the unit suite: 3585 passed;
- nothing left on either practice user;
- the contract version, unmoved.

Each refusal below is checked exact (status, code, key and reason) and shown to write nothing by
reading the accounts, the account's transactions and its statements back. Where your contract
gives an order of refusals, each pair is proven by one request that breaks both.

- **"`GET /accounts` lists an account holding PEN and USD, a balance for each, and no route or
  field names a holder":** worked.
  - An account reads exactly its thirteen keys, and each currency exactly
    `currency_code`, `current_balance_cents` and `opening_balance_transaction_id`, on the list
    and the read, for a bank account, a person and an archived account.
  - PEN comes before USD whatever the creation order and the balances, and a currency added
    later sorts by its code too.
  - Every bank account comes before every person, each group by `sort_order` ascending, then
    creation time, oldest first. The tests set names and ids against that order.
  - An archived account is listed only with `?include_archived=true`, and a person only with
    `?include_people=true`.
  - The activity entries are counted exactly, each snapshot with your keys: a create leaves one
    `account` entry and one `currency` entry per currency; an edit, an archive and a turn into a
    person leave the `account` entry alone; a currency added or removed leaves one `currency`
    entry.
- **"An account in soles and dollars, and a person in soles and dollars, are each created in one
  write; a currency is added later and one with nothing booked is removed":** worked.
  - A bank account and a person are each made in PEN and USD in one write, PEN before USD, at 0.
  - Unknown fields are refused on the body and inside an entry. The create's refusals come in
    your order, and `LIMIT_REACHED` holds at the cap of 100.
  - A currency is added (`201`, at 0) and removed (`200`), the account's `version` unmoved.
  - The add's refusals and the removal's come in your order, with your words. `HAS_TRANSACTIONS`
    and `IN_LIVE_STATEMENT` judge the removed currency alone, against a draft, a completed and a
    reverted statement holding it, the other currency stopping nothing.
- **"Archiving, unarchiving, turning into a person and back, and deleting act on the account,
  all its currencies at once":** worked.
  - A name and a statement code are one write, `version` up by one, no currency written.
    `statement_code: null` clears the code. `currency_code: null` is `NOT_NULL` and a value is
    `IMMUTABLE`. The edit's refusals come in your order.
  - A deleted account is `404` to a read, an edit, a second delete and a currency add, and its
    name and code are free at once.
  - `HAS_TRANSACTIONS` comes before `IN_LIVE_STATEMENT` on a delete. A draft, and a completed
    statement with no transaction (a card's statement PDF printing no row), each stop the delete.
  - An account's closed days hold for a currency added later. A soles account with March
    completed takes dollars, its `version` and the statement unmoved. A dollar row on a sealed
    day is `SEALED_PERIOD`, as a soles row is, on `date`, and in a batch on
    `transactions.<i>.date`. The same row a day after March is taken. March still holds soles
    only, and after a revert too, when the sealed day takes the dollar row.
- **"A transaction in a currency the account does not hold is refused, nothing written":**
  worked.
  - A create answers with `account_id` and `currency_code` in both currencies of one account.
  - `REQUIRED`, `UNSUPPORTED_VALUE` and `CURRENCY_NOT_HELD` all hold; a removed currency is
    refused until it is added back.
  - A batch is refused whole, naming every bad item. A line group in two currencies is
    `LINE_GROUP_FIELDS_DIFFER`.
  - One operation code is taken once per currency of one account. A second line with it is
    `OPERATION_CODE_EXISTS`, a repeat within a batch is `DUPLICATE_IN_REQUEST`, and the code is
    free again once its line is deleted.
  - The list and the count filter by account and by currency. A cursor sent back with
    `currency_code` changed is `INVALID_CURSOR` on `after`.
- **The old names are refused:** worked.
  - An unknown account id is `404` on reading, editing and deleting an account, and
    `INVALID_REFERENCE` as a create's account. As `?account_id=`, it lists nothing and counts 0
    where a real account lists its rows. No read carries a former per-currency id, so the tests
    send an unknown one, as your contract says a former one is refused the same way.
  - `GET /holders`, `GET /holders/{id}`, `POST /accounts/{id}/move` and `POST /people` answer as a
    never-made route does.
  - `?holder_id=` is `UNKNOWN_PARAMETER` on `GET /statements`, `/transactions`, `/bank-lines`
    and `/bank-lines/count`.
- **Not tested live:** `CONCURRENT_CHANGE`. Two requests cannot be made to land at the same
  moment reliably.

## Contract problems found

1. **Where `OPERATION_CODE_EXISTS` puts its sentence.** `POST /transactions`, "Unique per
   currency of an account among live bank lines", says a second bank line with a taken
   operation code is `409` on `operation_code` (`OPERATION_CODE_EXISTS`) with "Another bank line
   on this account already has operation code '<code>'.". Everywhere else in your contract, that
   phrasing ("on `<key>` (`REASON`) with "…"") names the field's own text in `fields`. Your
   engine sends that sentence as `error.message`, and `fields["operation_code"]` as "Must not be
   an operation code already on this account.", a sentence the contract never states. Please
   either move the sentence into `fields`, or reword the contract to "(message "…")" and state
   the field's own text. Until then the suite checks the status, the key and the reason, not the
   sentence.
2. **Which item a batch's repeated operation code is refused on.** `POST /transactions/batch`
   says two items with one operation code on one currency of one account are
   `DUPLICATE_IN_REQUEST` on `transactions.<i>.operation_code`, without saying which item `<i>`
   is. Your engine names the second item only. For a statement's repeated currency your contract
   says "the later entry"; please say the same here, or whichever you mean. Until then the suite
   accepts either item.

## Asks this closes

None. "An account holds its currencies: the holder becomes the account, and each account becomes
one of its currencies" closes with part 7, the statement screen.
