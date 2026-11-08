# A client picks no currency it has no choice about, saves an account form in one write, reads the supported currencies from the engine, the contract says what the engine does, every amount has a stated largest value, every transaction carries the calendar day it is counted on, a statement PDF's preview names the lines the close will flag, the shared practice user always holds an account, an account carries its bank and its card numbers over time, its name built from them, and a statement PDF is checked against the account's number

Shipped 2026-11-08 · ⚠️ breaking · contract `f82426fb0a099676` → `1002f105c6bacdf1` (twenty versions: `385b112ad7f34bb8`, `b7c5772dbcc8b811`, `2105213d3035b4d4`, `edbafcc162850075`, `14fb4741b9db37b8`, `11ab349bdfc38647`, `5278888de6fdb51a`, `21bba425e1f9a489`, `f3ee39cdc9d602e5`, `ce7749236717b163`, `47052c552a977fa0`, `e7198a911ef00e01`, `347d15e7e9ce0fec`, `c15bc09f1132d6e8`, `9f70c770a824832d`, `d9bd079557801740`, `8b9824e76593ec1e`, `be127df8432341a1`, `9dc0e6c4a5c83bcb`, `1002f105c6bacdf1`)

Answers: "A read lists the supported currencies" (raised 2026-10-29); "Say whether an account can hold no currency, and what a client does with one" (raised 2026-10-30); "An account's only currency is taken when a write names none" (raised 2026-10-31); "An account and its opening balances save in one write" (raised 2026-10-31) and its edit half, "Save an account's changes and its opening balances in one write, whole or not at all" (raised 2026-11-06); "Removing a currency names the currency in every refusal" (raised 2026-10-31); "Say whether a zero-amount row dated earlier stops a sheet row being the opening balance" (raised 2026-11-03); "State the largest amount the engine takes, and refuse past it everywhere" (raised 2026-11-05); "Send each transaction's calendar day with it" (raised 2026-11-05); "A statement PDF's dry run names the lines the close will flag" (raised 2026-11-05); "Give the shared practice user an account that every reseed keeps" (raised 2026-11-05); "An account carries its bank and its card numbers over time, and a PDF is checked against them" (raised 2026-11-03), its points 1, 2 and 4 to 7; and the eleven caught-up notices (the replies for `592f2467fa3df75a`, `95e8fea031ba6bd1`, `e020782e3579d011`, `e7393dd869963db1` in two parts, and `f82426fb0a099676` parts 1, 2, 4, 5, 6 and 7).

Every route below takes `Authorization: Bearer <key>` and, on a write, `X-Idempotency-Key: <uuid>`, as every route does. In the examples, `visa-…` is a card account holding PEN and USD, and `savings-…` an account holding PEN only.

## Each ask

1. **"A read lists the supported currencies":** done, differently in two ways. `GET /currencies` answers `{"items": [{"currency_code": "PEN"}, {"currency_code": "USD"}]}`, wrapped in `items` like every unpaged list, not a bare array. It carries no number of decimals: every amount is in cents and both currencies have two decimals; a currency with other decimals would change what `amount_cents` means, and would add the field then.
2. **"Say whether an account can hold no currency":** answered. No live account ever holds none, and the `currencies` rule says so. Drop your handling of `currencies: []`.
3. **"An account's only currency is taken when a write names none":** done as asked, both halves. A move between currencies never converts the amount.
4. **"An account and its opening balances save in one write"**, and its edit half, **"Save an account's changes and its opening balances in one write, whole or not at all"** (2026-11-06): done, with two differences from the 2026-11-06 ask:
   - The answer names each currency's opening balance by its id (`opening_balance_transaction_id`). Its amount and date are read from that transaction, never repeated beside the id.
   - The check ran on two currencies, not three, since the engine takes only `PEN` and `USD`.
5. **"Removing a currency names the currency in every refusal":** done as asked.
6. **"Say whether a zero-amount row dated earlier stops a sheet row being the opening balance":** answered: it does not. The engine used to count it; it now skips it.
7. **"State the largest amount the engine takes, and refuse past it everywhere":** done, with one point answered differently. The bound, every typed field and every file are done as asked. "No answer ever carries an amount past the bound" is answered instead with: a total is never capped. A balance or a month's figure adds many amounts, so it can exceed the bound on any one of them; capping it would refuse a valid write because of other rows. Every figure the engine answers is a whole number of cents a client holds exactly (a total stays far inside what a browser counts exactly, about 9 quadrillion cents, 90 trillion in currency units).
8. **"Send each transaction's calendar day with it":** done, as `day`, with one point answered differently. Every answer carrying a transaction's `date` carries `day`, and `date` stays as it is, in UTC. An activity entry's snapshots do not carry it: a snapshot is stored as the write left it, so a day saved there would be the day in the zone of that moment and would go stale when `display_timezone` changes. To show an entry's day, read the transaction itself.
9. **"A statement PDF's dry run names the lines the close will flag":** done, with two additions. The preview carries all three of the close's notes per currency (`review_lines`, `warnings` and `coverage_gap`), so an uncovered stretch shows before the month is completed too. A line the upload takes out of the draft (`taken_out`) is flagged on the preview when its day is reviewed, exactly as the apply flags it, so "a line in the draft is never flagged" holds for every draft line but those.
10. **"Give the shared practice user an account that every reseed keeps":** done as asked. The account is named **`BCP-0000`** (bank `BCP`, number `0000`): a bank account's name is now built by the engine (ask 12), so `Practice account` can no longer exist. No contract version moves for it: it is the practice seed, not a route.
11. **The eleven caught-up notices:** recorded; your read marker is `f82426fb0a099676`. The nine contract problems they found are fixed in the contract, and in the engine where noted (section 7 of *What changed*). The tenth, `is_person` taking `"yes"`, `"true"`, `1` and `0` as booleans, is left with the engine's owner: it is about every request boolean, not this one field.
12. **"An account carries its bank and its card numbers over time, and a PDF is checked against them":** points 1, 2 and 4 to 7 done; point 3 declined.
   - **Point 1 (the bank, from a list):** done as asked, as `GET /banks`.
   - **Point 2 (the numbers over time):** done as asked, with the end days set by the engine. A replacement, a start day or a removal that would change which number covers a day of a completed statement is refused, naming the statement.
   - **Point 3 (an alias):** declined by the engine's owner. No account has an alias. A bank account's name is its bank and its current number's last 4, `BCP-5678`, or `BCP` with no number, never typed. A person keeps a typed name.
   - **Point 4 (the name to show):** done, as the account's own `name`, on the account's own reads only. A transaction, statement or bank line keeps `account_id` alone.
   - **Point 5 (every route that takes an account's name):** done. `POST /accounts` and the two kind changes take the new rules. The sheet import flags a sheet name that matches several accounts instead of picking one.
   - **Point 6 (the PDF checked against the number):** done, with one difference from the ask: on a card replaced during or after a cycle, the header may print a card that starts after the statement's last day, and the number above each group of purchases is checked too (section 13).
   - **Point 7 (the statement code stays):** done as asked: `statement_code` is unchanged.

## What changed

### 1. `GET /currencies` ➕

The currencies the engine takes, by `currency_code` ascending, the same for every user:

```json
{"items": [{"currency_code": "PEN"}, {"currency_code": "USD"}]}
```

Every refusal for an unsupported currency (`UNSUPPORTED_VALUE` on a `currency_code`) now points at it instead of naming PEN and USD in prose, and so do the contract's overview and the descriptions of `UNSUPPORTED_VALUE` and `CURRENCY_NOT_HELD`.

### 2. A live account always holds a currency

The account response's `currencies` rule now says a live account always lists at least one: an account is created with at least one, its last currency is never removed (`LAST_CURRENCY`), and it is deleted whole. `GET /accounts`, `GET /accounts/{id}` and `/dashboard` read an account and its currencies at one moment, so an account deleted while you read it is never answered live with no currencies.

### 3. Removing a currency names it ⚠️

On `DELETE /accounts/{id}/currencies/{currency_code}`, `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` moved from `account_id` to `currency_code`, and their messages name the code. `ACCOUNT_ARCHIVED` stays on `account_id`. `DELETE /accounts/{id}` is unchanged.

Before (`f82426fb0a099676`), removing USD from the Visa with a dollar purchase on it:

```json
{"error": {"code": "CONFLICT", "message": "…",
  "fields": {"account_id": "Must not be used by any active transaction."},
  "reasons": {"account_id": "HAS_TRANSACTIONS"}}}
```

Now:

```json
{"error": {"code": "CONFLICT", "message": "…",
  "fields": {"currency_code": "Must not be used by any active transaction in USD."},
  "reasons": {"currency_code": "HAS_TRANSACTIONS"}}}
```

`IN_LIVE_STATEMENT` reads `"Must be a currency no live statement holds in USD, draft or completed: delete the statement first."` on `currency_code`.

### 4. A new transaction takes a one-currency account's currency ➕

`currency_code` is optional on `POST /transactions` and on each item of `POST /transactions/batch`:

- **Omitted, on an account holding one currency:** the transaction is in that currency, and the answer's `currency_code` says which. `{"account_id": "savings-…", "amount_cents": -2500, "date": "…"}` answers `"currency_code": "PEN"`.
- **Omitted, on an account holding several:** `422` on `currency_code` (in a batch `transactions.<i>.currency_code`), `"Must be one of the account's currencies: PEN, USD."`, reason `REQUIRED`. It needs the account read, so it falls in the third step of *Which refusal comes first on a create*, with the account's other refusals. A taken `id` still answers `ID_EXISTS` first, and an unknown account answers `INVALID_REFERENCE` on `account_id`, never `REQUIRED`.
- **Explicit `null`:** still `422` on `currency_code` (`INVALID_FORMAT`). Leave the key out instead.
- **In a batch,** a line group's currencies are compared after each item's currency is settled, at the third step. One item sending `PEN` and one leaving it out on a soles-only account are one line. One item sending `USD` and one leaving it out on a soles-only account: the `USD` item is `CURRENCY_NOT_HELD` and the other `LINE_GROUP_FIELDS_DIFFER`, both on `currency_code`. A repeated operation code is judged on the settled currency the same way.

### 5. A move by account alone takes a one-currency account's currency ⚠️

On `PUT /transactions/{id}` and `PUT /bank-lines/{id}` sending `account_id` and no `currency_code`:

- **The new account holds the line's currency:** the line keeps it, as before.
- **The new account holds exactly one other currency:** the line moves to it, the amount as it is. This used to be `422 CURRENCY_NOT_HELD` on `account_id`; it now succeeds. It is exactly the move the request would make sending that `currency_code`, with every rule of that move (a locked line, an archived account, an opening balance staying put, the statement assignment, a sealed day, the operation code's uniqueness), each refusal keyed on `account_id`, the key you sent.
- **The new account holds several, none the line's:** `CURRENCY_NOT_HELD` on `account_id`, the message now naming its currencies: `"The account holds no USD: it holds EUR, PEN."`. While only PEN and USD exist, this cannot happen.

**A move between currencies never converts the amount:** a $100.00 purchase moved this way is a S/ 100.00 purchase. Read `currency_code` from the answer: it can change on an account-only move.

### 6. An account and its opening balances in one write ➕

**Create.** Each entry of `POST /accounts`' `currencies` may carry `opening_balance`, the body of `POST /accounts/{id}/opening-balance` without `currency_code` (the entry's own):

```json
{"id": "…", "name": "Visa", "currencies": [
  {"currency_code": "PEN", "opening_balance": {"transaction_id": "…", "amount_cents": 50000, "date": "2026-01-01T00:00:00-05:00"}},
  {"currency_code": "USD", "opening_balance": {"transaction_id": "…", "amount_cents": -4550, "date": "2026-01-01T00:00:00-05:00", "title": "Saldo inicial"}}]}
```

- Each opening balance is judged by the separate route's rules (a zero amount, a future date, a taken `transaction_id`, line codes used up).
- Refusals are keyed `currencies.<i>.opening_balance.<field>`. Missing settings stay on `user_settings`.
- All or nothing: a refusal of any part writes nothing, the account included.
- A taken-id `409 ID_EXISTS` names every taken id in one answer, the account's `id` and each `transaction_id` among them. A plain create sent again still answers `ID_EXISTS` on `id` alone.
- The answer is the account, each currency's `opening_balance_transaction_id` set. The activity log adds one `created` entry per opening balance.
- The contract states the create's whole refusal order.

**Edit.** `PUT /accounts/{id}` takes `opening_balances`, keyed by currency code, beside `name`, `color`, `sort_order` and `statement_code`:

```json
{"name": "Visa Infinite", "opening_balances": {
  "USD": {"transaction_id": "…", "amount_cents": -2500, "date": "2026-01-01T00:00:00-05:00"},
  "PEN": {"amount_cents": 20000, "date": "2026-01-02T00:00:00-05:00"}}}
```

- **Set** (the currency has none): `transaction_id`, `amount_cents` and `date` required, `title` optional. Judged as `POST /accounts/{id}/opening-balance`.
- **Change** (it has one): `amount_cents`, `date` and `title`, each optional. Judged as `PUT /transactions/{id}` judges it (a completed statement's `LOCKED`, a sealed day, zero, future). A `transaction_id` sent on a change is `422 UNKNOWN_FIELD`.
- **Clear:** `null`. Judged as `DELETE /transactions/{id}`. Clearing a currency with none is `422` on `opening_balances.<code>`, the new reason `NO_OPENING_BALANCE`.
- **Codes:** a code the account does not hold is `CURRENCY_NOT_HELD` on `opening_balances.<code>`; one `GET /currencies` does not list is `UNSUPPORTED_VALUE`.
- **Keys:** refusals are keyed `opening_balances.<code>.<field>`, or `opening_balances.<code>` for the whole entry.
- **All or nothing,** the name and code included.
- **Version:** the account's `version` and its `updated` entry move only when one of its own fields is sent. Each opening balance logs its own `created`, `updated` or `deleted` entry.
- **An archived account:** each part is refused as its own route refuses it. A set is `INVALID_REFERENCE` on `opening_balances.<code>`, a change `ACCOUNT_ARCHIVED` on each field sent, a clear `409 ACCOUNT_ARCHIVED` on `opening_balances.<code>`. The engine's owner may make these one answer later; it is an open question.
- **The answer** is the account as it stands after every write, each currency's `opening_balance_transaction_id`. The contract states the edit's whole refusal order.

`POST /accounts/{id}/opening-balance` stays.

### 7. The contract says what the engine does

- **`POST /transactions/import-sheet`, *Opening balances*:** a row of zero amount (`skipped`) never counts as a row dated before a `SALDO INICIAL` row. A PEN `SALDO INICIAL` of `0.00` on 2 January and one of `1,000.00` on 5 January give a PEN opening balance of 1,000.00 dated 5 January; it used to be an ordinary row. If that leaves two non-zero `SALDO INICIAL` rows on the first day, both are refused (`DUPLICATE_IN_REQUEST`), as before.
- **`POST /statements/import`, the card layout:** any label on an undated line that carries an amount is read as one entry on the statement's last day, in the direction printed, not only the labels the section names.
- **`POST /statements/import`, *Concurrency*:**
  - It names the `409 CONCURRENT_CHANGE` on `category_id` or `hashtag_ids`, when the pending category or hashtag is deleted while a created row is filed under it.
  - It states that only a write creating a statement in the paper's month, or moving one into it, between the upload's read and its write reaches `STATEMENT_MONTH_TAKEN`: a `POST /statements`, a `PUT /statements/{id}` changing the days, or another upload's apply.
- **`GET /statements/samples` gains `card-soles-only`** ➕: a soles-only card's made-up paper whose dollars print at zero with no row. Uploaded onto an account holding soles alone, it closes the month in soles only, on a dry run and an apply. Its `balances` hold soles only. A sample's `balances` now leave out a currency the paper shows at zero with no row, as the upload does.
- **`GET /bank-lines/{id}`, `is_opening_balance`:** no longer mentions a `PUT` of a statement's order, a route that does not exist.
- **`POST /accounts/{id}/make-account`:** no longer declares `HAS_RECONCILIATION`. No person ever holds a statement, so it was never sent. `make-person` keeps it.
- **`OPERATION_CODE_EXISTS`:** `error.message` is `"Another bank line on this account already has operation code '<code>'."` and the field's text is `"Must not be an operation code already on this account."`, on every route that sends it.
- **`POST /transactions/batch`, a repeated operation code (`DUPLICATE_IN_REQUEST`):** it is refused on every item of the later line; the first keeps its place.
- ***Client-supplied UUIDs*:** the list of keys a taken id (`ID_EXISTS`) lands on names `currencies.<i>.opening_balance.transaction_id` (`POST /accounts`) and `opening_balances.<code>.transaction_id` (`PUT /accounts/{id}`).

### 8. The largest amount the engine takes ⚠️ (contract `47052c552a977fa0`)

*Base Conventions* → *Money amounts* states it once: **99,999,999,999 cents** (999,999,999.99), in either direction, in every currency. It bounds every amount sent in or read from a file, never a total the engine answers.

- **Every request money field** carries it in `GET /openapi.json` as integer `maximum: 99999999999` / `minimum: -99999999999`. These are `amount_cents` on `POST /transactions`, each item of `POST /transactions/batch` and `PUT /transactions/{id}`; each part's `amount_cents` on `PUT /bank-lines/{id}`; `amount_cents` on `POST /accounts/{id}/opening-balance`, on each `currencies.<i>.opening_balance` of `POST /accounts` and on each entry of `opening_balances` on `PUT /accounts/{id}`; and `beginning_balance_cents` and `ending_balance_cents` on `POST /statements` and `PUT /statements/{id}`. Read the bound from the contract; keep no copy of it.
- **One cent past is `422 OUT_OF_RANGE` on the field**, keyed as the route keys that field (`transactions.<i>.amount_cents` in a batch, `parts.<i>.amount_cents`, `balances.<i>.<field>`, `currencies.<i>.opening_balance.amount_cents`, `opening_balances.<code>.amount_cents`). Nothing is written. The message is `"Input should be less than or equal to 99999999999"` (or `greater than or equal to -99999999999`). Match on `reasons`, not on the text.
- **Far past the bound is still `422`, never `500`.** A whole number of any size is `OUT_OF_RANGE`, and so is a decimal or exponent form up to about `9.2e18` (such as `1e18`). Past that (`1e19`, `1e30`, `1e5000`) it is `INVALID_FORMAT`. Before, such an amount was taken, or answered `500`.
- **Files.** On `POST /transactions/import` (the bank download) and `POST /transactions/import-sheet` (the owner's sheet), a row past the bound is `422 OUT_OF_RANGE` on `rows.<row>.amount_cents`: `"Row 3: Monto 1000000000.00 is past the largest amount, 99,999,999,999 cents."`. This is judged before whole cents. `NOT_WHOLE_CENTS` now means only an amount within the bound that is not whole cents. Before, an amount of 10,000,000,000,000 or more in the file's currency was `NOT_WHOLE_CENTS`, and one past the bound below that was taken. On `POST /statements/import` a line past the bound is `rows.<place>.amount_cents`. A printed previous or closing balance past it is on `file` (a balance is no row), naming the balance and its currency: `"The paper's previous balance (PEN) is past …"`. These come after the refusals of the paper as a whole, so a paper that does not add up is still `TOTALS_MISMATCH`. Every file refusal answers the same on the dry run and the apply, with nothing written. A card paper's columns are too narrow to print such a figure, so in practice only a savings paper can reach it.
- **`OUT_OF_RANGE`'s description** names the money bound among its bounds.

Before, sending `"amount_cents": 100000000000` to `POST /transactions` gave `201`. Now:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "…",
  "fields": {"amount_cents": "Input should be less than or equal to 99999999999"},
  "reasons": {"amount_cents": "OUT_OF_RANGE"}}}
```

### 9. Every transaction carries its calendar day ➕ (contract `e7198a911ef00e01`)

Every transaction an answer carries now also carries **`day`**: a bare `YYYY-MM-DD`, never `null`, the calendar day of `date` in the user's `display_timezone` at the time of the request. It is the day every day filter, sealed period, statement window and report counts the transaction on. `date` is unchanged, an instant in UTC.

```json
{"id": "…", "date": "2026-11-05T04:30:00Z", "day": "2026-11-04", "amount_cents": 2500, "…": "…"}
```

That is a purchase at 23:30 on 4 November for a user in `America/Lima`. The first ten characters of `date` read `2026-11-05`, which is the wrong day; read `day`.

- **Where:** `GET /transactions`, `GET /transactions/{id}`, `POST /transactions`, each created row of `POST /transactions/batch`, `PUT /transactions/{id}` (the transaction and each of `changed_parts`), `DELETE /transactions/{id}`, `POST /accounts/{id}/opening-balance`; each part of a bank line on `GET /bank-lines`, `GET /bank-lines/{id}`, `PUT /bank-lines/{id}` (the line and each of `changed_parts`) and `DELETE /bank-lines/{id}`; every line's parts on `GET /statements/{id}/statement-order`; and each part of an `unclaimed_lines` entry of `POST /transactions/import`, on the dry run and the apply.
- **Not on** the rows of `POST /transactions/import-sheet` or `POST /statements/import`: their `date` is already a bare day read from the file. Not on an activity entry's snapshots (*Each ask*, 8).
- **Read-only:** sending `day` on a write is `422` on `day` (`UNKNOWN_FIELD`).
- **Computed on every read, never stored:** change `display_timezone` and the next read shows the new day, with no write, no new `version` and no activity entry. A replayed write (the same `X-Idempotency-Key`) answers exactly what it answered the first time, `day` included.
- **Settings:** `GET`, `PUT` and `DELETE` on `/transactions/{id}` and on `/bank-lines/{id}`, and `GET /statements/{id}/statement-order`, now answer `422 SETTINGS_MISSING` (`NOT_PROVISIONED`, on `user_settings`) before bootstrap, right after the `404` on the path id. On `PUT /bank-lines/{id}` a taken part id (`ID_EXISTS`) still answers before both. A bootstrapped user never sees it.
### 10. A statement PDF's preview names the lines the close will flag ➕ (contract `c15bc09f1132d6e8`)

On `POST /statements/import`, each entry of the top-level `balances` now also carries the close's notes for its currency: `warnings`, `coverage_gap` and `review_lines`, shaped exactly as `statement.balances[]` carries them. The answer also carries a top-level **`not_covered`**: one `{currency_code, warnings, coverage_gap, review_lines}` per live currency of the account the statement holds no balances for, as `statement.not_covered[]` carries them, `[]` when none. Both are always present, on a dry run and an apply alike.

```json
{"dry_run": true, "statement": null, "…": "…",
 "balances": [{"currency_code": "PEN", "beginning_balance_cents": 250000, "ending_balance_cents": 516445,
   "warnings": [], "coverage_gap": null, "review_lines": [{"id": "…", "…": "…"}]}],
 "not_covered": [{"currency_code": "USD", "warnings": [], "coverage_gap": null, "review_lines": [{"id": "…", "…": "…"}]}]}
```

- **On a dry run** they are what the apply's close would answer, worked out over the ledger as the upload would leave it: a line matched to a row is filed and not flagged; a line moved to its row's day counts on that day; a line the statement holds that the paper does not print (`taken_out`) is flagged when its day is reviewed. When the upload creates the statement, the previous statement is the one before the paper's first day. The dry run still writes nothing.
- **On an apply** they equal the ones in `statement`.
- Every other key of the answer is unchanged.
### 11. The shared practice user holds `BCP-0000` (no contract change)

Every run of the practice seed that seeds the TUI's two users (the run that prints `EXPENSE_PAT`, with or without `--force`) now leaves the shared practice user holding exactly one live, active bank account named **`BCP-0000`** (bank `BCP`, number `0000`), holding `PEN` and `USD`, and prints its id on every run, beside the key when a key is issued:

```
EXPENSE_PRACTICE_ACCOUNT_ID=b2ba9fd2-b790-4874-bae5-943d9c04046f
```

- **Missing or deleted:** a new one is created, with a **new id**; a deleted account is never brought back. Read the id from the seed's output each time, never keep it.
- **Archived:** it is unarchived, same id.
- **Lost a currency:** the missing one is added back; nothing else changes.
- **Already in place:** left exactly as it is, its transactions included.
- **A person under that name** (a check converted it), **or two live accounts under it:** nothing is touched, and the seed says so and fails.
- The name is matched ignoring case and surrounding spaces, as the engine's own name rule is. It starts with neither `contract-` nor `freshman-`, so your cleaner leaves it alone. No real card's number is `0000`, so no account your checks create takes its name unless a check gives one that number.
- It is put in place through the engine's own routes, as the shared user, so each change is in its activity log. The other practice users, and the shared user's other accounts and transactions, are never changed.
- The shared user gets one extra key per seed run, used only to put the account in place and revoked before the run ends (or at the start of the next run, if a run is stopped mid-step). It never counts as the user's key and never replaces yours.

### 12. An account's bank, its numbers over time, and its built name ⚠️ (contract `d9bd079557801740`)

The contract's `x-changelog` entry for `d9bd079557801740` lists every rule; in short:

- **`GET /banks`** ➕: `{"items": [{"code": "BCP", "name": "Banco de Crédito del Perú"}]}`, in the order a picker shows it. `BCP` is the only bank.
- **Every account answer** ➕ carries `bank_code` (`"BCP"`, `null` exactly for a person) and `numbers`, oldest first, each `{last4, start_date, end_date}`. `start_date` is `null` for the first number; `end_date` is the day before the next number's start, `null` for the current one; `[]` for a person and for a bank account with no number. A number has no `id`. `/dashboard`'s account rows keep `{id, name, currencies}`, with the built name.
  ```json
  {"name": "BCP-9012", "bank_code": "BCP", "numbers": [
    {"last4": "5678", "start_date": null, "end_date": "2026-04-09"},
    {"last4": "9012", "start_date": "2026-04-10", "end_date": null}]}
  ```
- **A bank account's `name` is built** ⚠️: its bank and its current number's last 4, `BCP-5678`, or `BCP` with no number. Names are judged on each write, unique among the user's live accounts, people included, case-insensitively, `409 NAME_EXISTS` otherwise. Accounts that already share a name keep it: every bank account made before this change reads `BCP` until it is given a number.
- **`POST /accounts`** ⚠️. Before: `{"id": "…", "name": "Visa", "currencies": [{"currency_code": "PEN"}]}`. Now a bank account sends its bank and, optionally, its first number, and no name:
  ```json
  {"id": "…", "bank_code": "BCP", "last4": "5678", "currencies": [{"currency_code": "PEN"}]}
  ```
  It answers `"name": "BCP-5678"`. A `name` sent for a bank account is `422 NAME_BUILT` on `name`. `bank_code` missing or `null` is `REQUIRED`; one `GET /banks` does not list is `UNSUPPORTED_VALUE`; a `last4` that is not exactly four digits is `INVALID_FORMAT`. A taken built name is `409 NAME_EXISTS` on `last4` (or on `bank_code` when no number was sent). A person sends `{"is_person": true, "name": "ALEJO", …}`, and `bank_code` or `last4` sent for one is `422 PERSON_HAS_NO_BANK` on each.
- **`PUT /accounts/{id}`** ⚠️. Before, `{"name": "Visa Infinite"}` renamed a bank account; now it is `422 NAME_BUILT`, `null` included (a person's `name` is unchanged). Only the current number is ever written:
  - `{"current_number": {"last4": "5678"}}` writes the first number of an account with none, or fixes the current number's digits. `{"current_number": {"start_date": "…"}}` moves its start day; the first number has no start day (`FIRST_NUMBER_HAS_NO_START`), and a later one starts later than the one before it (`NUMBER_START_NOT_LATER`).
  - `{"current_number": null}` removes the current number; the one before it is current again, and with none left the name is `BCP`.
  - `{"new_number": {"last4": "9012", "start_date": "2026-04-10"}}` adds a replacement.
  - `NO_NUMBER` when there is no number to remove or replace. Both keys in one request are `422 CONFLICTING_PARAMETERS` on `new_number`. `bank_code` sets the bank. On a person, each of the three is `PERSON_HAS_NO_BANK`.
  - **A completed statement's days keep their number:** a write that would change which number covers any day of a completed statement is `409 NUMBER_IN_COMPLETED_STATEMENT` on `new_number` or `current_number`, naming it: `"The statement 'March 2026' (2026-03-01 to 2026-03-31) is completed, and this would change which number covers its days. Revert it first."`. Fixing digits and writing a first number are never refused by it. It is judged last, after the opening balances.
  - Each write builds the name again (`NAME_EXISTS` keyed on the field that changed it), moves `version` once and logs one `updated` entry whose snapshots carry `bank_code` and `numbers` before and after.
- **`POST /accounts/{id}/make-person`** ⚠️ now takes `{"name": "Mamá"}`, and **`POST /accounts/{id}/make-account`** ⚠️ takes `{"bank_code": "BCP", "last4": "4321"}` (`last4` optional, `null` meaning no number; a `name` is `NAME_BUILT`). Before, both took no body; now no body is `422`, judged before an unknown id's `404`. `make-person` drops the bank and the numbers. `make-account` builds the name and drops the typed one. Both can answer `409 NAME_EXISTS`.
- **`POST /transactions/import-sheet`** ➕: each `names.accounts[]` entry carries `ambiguous`, `true` when several live accounts have the sheet's name (`BCP`, for one). `proposed_id` is then `null`: name the account you mean in the `names` table by its `id`.
- **New reasons:** `NAME_BUILT`, `PERSON_HAS_NO_BANK`, `NO_NUMBER`, `FIRST_NUMBER_HAS_NO_START`, `NUMBER_START_NOT_LATER`, `NUMBER_IN_COMPLETED_STATEMENT`. `CONFLICTING_PARAMETERS` is new on `PUT /accounts/{id}`.
- **The account snapshot** in the activity log carries `bank_code` and `numbers`; older entries lack them.

### 13. A statement PDF is checked against the account's number ⚠️ (contracts `8b9824e76593ec1e`, `be127df8432341a1`, `9dc0e6c4a5c83bcb`)

- **The paper must print its number** ⚠️ (`8b9824e76593ec1e`). A savings paper prints its account code under `CODIGO DE CUENTA` in the header (`191-12345678-0-17`); a card paper its masked number under `Número de tarjeta` (`4280-76XX-XXXX-1234`), both the same on every page, and a card paper the number unbroken (`428076XXXXXX1234`) on a line above each group of purchases (a new card's first statement may print none). A header with no number, a number that does not read or pages that disagree is `422` on `file`, `UNEXPECTED_LAYOUT`. The samples print made-up numbers: savings `000-00000000-0-00`, cards `0000-00XX-XXXX-0000` and `000000XXXXXX0000`.
- **The number is checked** ⚠️ (`be127df8432341a1`), by its last 4 digits (a savings code's last 4 digits with the dashes removed: `191-12345678-0-17` → `8017`):
  - the header's number must be the account's number on the statement's last day, or a number the account starts after that day (a card issued after the cut);
  - on a card paper, each number above a group of purchases must be one the account had on some day of the statement. On a replaced card's paper the header prints the new card and the purchases are grouped under the old one; both pass when the account holds both numbers with their start days.
  - A number that does not fit is `422` on `account_id`, reason `STATEMENT_NUMBER_MISMATCH`: `"The paper prints the number ending 5678, and the account's number on 2026-10-25 ends 8017."`, or for a group `"The paper lists purchases under the number ending 1234, and the account's numbers from 2026-09-28 to 2026-10-25 end 5678."`. An account with no number is `422` on `account_id`, `ACCOUNT_HAS_NO_NUMBER`. Both on a dry run and an apply, nothing written, after `NO_STATEMENT_CODE` and before the currencies are judged.
  - Before: a card paper uploaded to the savings account was read into it. Now it is refused, naming both numbers.
  - A sample uploads only to an account holding a number ending `0000`.
- **The paper's layout** ➕ (`9dc0e6c4a5c83bcb`): a card row's type may hold dots between letters (`DISP.EFECT`, a cash withdrawal), read like any other row; trailing pages with no text are skipped when the numbered pages are complete.
- **Concurrency** (`be127df8432341a1`, `9dc0e6c4a5c83bcb`): the apply judges the numbers and the account's currencies again under the account's locks. A number written to the account mid-apply that no longer fits is `422 STATEMENT_NUMBER_MISMATCH`; a currency that joins or leaves mid-apply is `409` on `account_id` (`CONCURRENT_CHANGE`). Nothing is written in either case.
- **New reasons:** `STATEMENT_NUMBER_MISMATCH`, `ACCOUNT_HAS_NO_NUMBER`.

## How it was checked

The full suite passed (3,393 tests for sections 1–7; 3,494 for section 8; 3,512 for section 9; 3,518 for section 10; 3,532 for section 11; 3,640 for section 12; 3,690 for section 13), and each check below ran against the practice engine as the engine's own practice user. The live engine serves `1002f105c6bacdf1` (wording only after `9dc0e6c4a5c83bcb`); the engine's owner applied section 12's ledger update before it shipped, and section 13 needs none. `347d15e7e9ce0fec` is wording only (*Settings preconditions* repeated in three route sections), and so is `9f70c770a824832d` (*Warnings channel* and the complete's `not_covered` now name the upload too).

| Done when | Result |
|---|---|
| One read returns the supported currencies, in a stated order, and the contract describes it | pass: `{"items":[{"currency_code":"PEN"},{"currency_code":"USD"}]}`; `401` without a key |
| The refusals that speak of "a supported currency" point at that read | pass: every route's `UNSUPPORTED_VALUE`, plus the overview and the two reason descriptions |
| The `currencies` rule and "an account always holds at least one currency" agree | pass: no `[]` wording left; removing a one-currency account's PEN is `409 LAST_CURRENCY` |
| The currency removal's `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` are keyed on `currency_code` and name the currency; the contract's list says so | pass: both on `currency_code`, both messages name `USD` |
| A transaction on a one-currency account with no `currency_code` lands in that currency, single and batch; on two currencies `REQUIRED`, naming them | pass: `201` in PEN, single and batch; `422 REQUIRED` with `"Must be one of the account's currencies: PEN, USD."`, single and on `transactions.1.currency_code` |
| A line moved by `account_id` alone onto a one-currency account in another currency lands in that currency, the amount unchanged | pass, both routes: a $100.00 Visa dollar purchase moved to a soles-only savings account reads `currency_code` `PEN`, `amount_cents` `10000`. The Visa's dollar balance rose by 10000 and the savings' soles balance fell by 10000. |
| The contract states both rules, and where the `REQUIRED` falls | pass |
| One request creates an account with its currencies and each one's opening balance, all or nothing | pass. A create whose dollar opening balance is dated tomorrow answers `FUTURE_DATE` on `currencies.1.opening_balance.date`, and writes no account and no soles opening balance. |
| One request changes the name and sets, changes and removes opening balances, and a read shows all of it (two currencies here) | pass: rename + set USD + change PEN; rename + set USD + remove PEN |
| The same request with one opening balance dated in the future is refused on that currency's date, nothing changed | pass: `FUTURE_DATE` on `opening_balances.USD.date`; name, version, every opening balance and the activity unchanged |
| Replaying with the same idempotency key changes nothing more | pass: same answer, no new write |
| Each refusal names the currency and field; the contract describes both requests, their order and answers | pass |
| "Opening balances" says whether a zero row dated earlier stops a later `SALDO INICIAL` | pass. On a dry run and an apply, the 2 January `0.00` / 5 January `1,000.00` sheet gives a PEN opening balance of 1,000.00 dated 5 January. |
| Each contract problem from the caught-up notices reads as stated; the dollars-at-zero sample closes a soles-only month in soles alone | pass. `card-soles-only` uploaded onto a soles-only card account: dry run `200`, PEN only; apply completed in PEN alone. |
| `GET /openapi.json` names the bound in one place, and every money field's schema carries it as `maximum` / `minimum` | pass: *Money amounts* in *Base Conventions*; all 11 request money fields carry `99999999999` / `-99999999999` as JSON integers |
| A transaction, a part, a statement balance and an opening balance one cent past the bound are each refused with `OUT_OF_RANGE` on that field; at the bound itself they are accepted | pass, both signs, on every route in section 8 (the three opening-balance routes, both statement balances on create and edit, the batch keyed `transactions.1.amount_cents`); each refusal wrote nothing |
| A spreadsheet, a bank download and a statement PDF with one row past the bound are refused, naming that row, on the dry run and on the apply, and nothing is written | pass: `rows.3.amount_cents` on both workbooks (also at `-cap-1`, `2000000000.005`, `10000000000000`, `-1E+30`); `rows.2` and `rows.3` on a paper with two such lines; a printed previous or closing balance on `file`; at the bound each file is taken |
| An amount far past what the engine stores is `422`, never `500` | pass: `10**30`, `2^63`, `1e18` → `OUT_OF_RANGE`; `1e19`, `1e400`, `1e5000` → `INVALID_FORMAT`, on every request money field of section 8 |
| A total is never capped | pass: two inflows at the bound give `current_balance_cents` `199999999998` and a month's `inflow_home_cents` `199999999998` |
| A transaction dated `2026-11-04T23:30:00-05:00` for a user in `America/Lima` comes back with `date` `2026-11-05T04:30:00Z` and its day `2026-11-04` | pass, on the create's answer, `GET /transactions/{id}`, the row in `GET /transactions`, and its part on `GET /bank-lines/{id}` and `GET /bank-lines` |
| Changing `display_timezone` changes the day on the next read, with no write | pass: after switching to `UTC`, `GET /transactions/{id}` reads `day` `2026-11-05`, `version` still `1`, `updated_at` unchanged, still one activity entry |
| The day a transaction carries is always the day a day filter (`?date_from=` / `?date_to=` given as days) finds it on | pass: in Lima, `date_from=date_to=2026-11-04` finds it and `11-03` / `11-05` do not; in UTC, `11-05` finds it and `11-04` / `11-06` do not |
| `day` is read-only and absent from activity snapshots | pass: `day` sent on `POST /transactions` is `422 UNKNOWN_FIELD`; the transaction's `created` entry has no `day` key; `GET /openapi.json` states `day` as a `date`-format string |
| A dry run of a PDF whose period holds a ledger line in no statement that the paper does not print names that line, under its currency, and writes nothing | pass: on the `savings` sample, a stray −11.11 line on 15 March and a −22.22 line in the March draft that the paper does not print came back in `balances[0].review_lines` (PEN); the matched line, the line one day off its row and a February line did not. A dollar line on a soles-only paper came back under `not_covered` (USD). The account's transactions, statements and bank lines read the same before and after. |
| The apply of the same PDF flags the same lines in `statement`'s `review_lines` | pass: `statement.balances[].review_lines`, `statement.not_covered` and the top-level notes all equal the dry run's |
| A dry run with nothing to flag names none (`[]`), and the dry run's other keys are unchanged | pass: `review_lines` `[]`, `warnings` `[]`, `coverage_gap` `null`, `not_covered` `[]`; `rows`, `balances`' figures, `counts`, `taken_out` and the rest as before |
| The contract states the new key under `POST /v1/statements/import` → **Response** | pass, in `GET /openapi.json` at `c15bc09f1132d6e8`, with its `x-changelog` entry |
| After a reseed with `--force`, `GET /accounts` as the shared practice user lists the account, active, holding `PEN` and `USD` | pass, without `--force` (it would have revoked your key): every seed run of the TUI's users puts the account in place before it checks `--force`. Two plain reseeds both printed `EXPENSE_PRACTICE_ACCOUNT_ID=b2ba9fd2-…`; the account is live, not archived, not a person, and holds live PEN and USD; the suite checks it through `GET /accounts`. |
| Deleting or archiving it and reseeding brings it back; reseeding with it active changes nothing about it | pass. Deleted → a new account with a new id; archived → unarchived with the same id; proven in the engine's suite, not by deleting your real practice account. Already in place → the two live reseeds changed no row and wrote no activity. |
| The banks read, the bank, the numbers over time and the name to show are in the contract, with every refusal | pass: `GET /openapi.json` at `d9bd079557801740` lists `GET /banks`, `bank_code` and `numbers` on every account answer, the built name, and every new reason on `POST /accounts`, `PUT /accounts/{id}`, `make-person` and `make-account`; `x-changelog` leads with it. No alias, by the owner's answer. |
| An account at `BCP` with no number shows as `BCP`, and given `5678` shows as `BCP-5678` | pass: created with `bank_code` `BCP` and no `last4` → `"name": "BCP"`, `numbers` `[]`; `PUT {"current_number": {"last4": "5678"}}` → `"name": "BCP-5678"` |
| A replacement keeps the account's statements and balance; the name follows the new number, and the old number stays readable with its end day | pass, the owner's check. March 2026 completed on the account. A replacement `9012` from 2026-03-31 → `409 NUMBER_IN_COMPLETED_STATEMENT` naming `'March 2026' (2026-03-01 to 2026-03-31)`, nothing written. From 2026-04-10 → `200`, `"name": "BCP-9012"`, numbers `5678` (start `null`, end `2026-04-09`) then `9012` (start `2026-04-10`, end `null`). The PEN balance read `97500` before and after; March's statement read the same before and after. |
| The other refusals answer as the contract says | pass: a `name` on a bank account → `422 NAME_BUILT`; a second live `BCP` → `409 NAME_EXISTS` on `bank_code`; bank `XYZ` → `UNSUPPORTED_VALUE`; a person with `bank_code` → `PERSON_HAS_NO_BANK`; both number keys → `CONFLICTING_PARAMETERS` on `new_number`; `NUMBER_START_NOT_LATER`, `FIRST_NUMBER_HAS_NO_START` and `NO_NUMBER` each as stated; `make-person {"name": "Mamá"}` → `bank_code` `null`, `numbers` `[]`; `make-account {"bank_code": "BCP", "last4": "4321"}` → `BCP-4321` |
| The shared practice user's account is `BCP-0000`, and the sheet import flags an ambiguous name | pass: in the engine's suite (the seed's own tests, and the sheet import's): proven there, not by reseeding your users |
| A month's PDF sent to an account whose number on its last day is not the paper's is refused in the engine's words, nothing written | pass: the `card` sample to an account numbered `1234` → `422 STATEMENT_NUMBER_MISMATCH`, "The paper prints the number ending 0000, and the account's number on 2025-03-25 ends 1234.", on a dry run and an apply; no statement and no transaction written |
| An account with no number is refused the same way | pass: `422 ACCOUNT_HAS_NO_NUMBER` on `account_id`, dry run and apply, nothing written |
| The right account's paper closes the month as before | pass: the `card` sample on an account numbered `0000` completes March; `card-no-dollars` completes April after it |
| A replaced card's earlier months close | pass: `0000` until 2025-03-31, then `5555`: March's paper (printing `0000`) completes; April's paper printing `0000` is refused, naming `5555`. A card replaced inside the cycle (new number from 2025-03-10) also completes. |
| The owner's own papers (dry run only; their numbers shown here with made-up digits) | pass: the owner's newest card paper, header `5678`, purchases under `1234`, previews whole (79 rows, PEN and USD) on an account holding `1234` then `5678`, whether `5678` starts inside the cycle or the day after it; sent to the owner's savings account (`8017`) it is refused naming `5678` and `8017`; the owner's savings paper previews on the savings account |

## What the TUI does

- **Currencies:** read the list from `GET /currencies`; drop your own PEN/USD list.
- **Accounts:** drop any handling of `currencies: []` on a live account.
- **Remove a currency:** read `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` on `currency_code`, not `account_id`, and show their messages as sent.
- **New transactions:** leave `currency_code` out when the account holds one currency. On a two-currency account send it, and show `REQUIRED` on `currency_code` with its message. Never send `"currency_code": null`.
- **Moves:** a move by `account_id` alone onto a one-currency account in another currency now succeeds. Read the new `currency_code` from the answer, and say in the app that the amount moves unconverted. Show `CURRENCY_NOT_HELD` on `account_id` with its message.
- **Account form, create:** send each currency's `opening_balance` inside its `currencies` entry, all in one `POST /accounts`. Show refusals from `currencies.<i>.opening_balance.<field>` on that currency's field. Expect a `409 ID_EXISTS` that names several ids.
- **Account form, edit:** send the account's changes and `opening_balances` (set with a new `transaction_id`, change without one, `null` to clear) in one `PUT /accounts/{id}`. Read each currency's opening balance through its `opening_balance_transaction_id`. Show refusals from `opening_balances.<code>[.<field>]`, `NO_OPENING_BALANCE` among them. Drop the chain of writes and its partial-save wording.
- **Sheet import help:** a currency whose earlier rows are all zero takes its first non-zero `SALDO INICIAL` row as its opening balance.
- **Amounts:** read the largest amount from each money field's `maximum` / `minimum` in the contract and refuse past it before sending, with the engine's `OUT_OF_RANGE` as the backstop; keep no limit of your own. Totals can exceed it. Show a file's `rows.<row>.amount_cents` refusal on that row, and a statement paper's `file` refusal on the upload.
- **Upload tests:** use `card-soles-only` to prove a soles-only month closes in soles alone.
- **Reasons:** stop expecting `HAS_RECONCILIATION` from `make-account`.
- **Days:** show and group a transaction by its `day`, never by the first ten characters of `date` and never by converting `date` yourself. Drop any day logic of your own. Show an activity entry's day from the transaction it names.
- **Statement upload preview:** show each currency's `review_lines`, `warnings` and `coverage_gap` from the dry run's `balances`, and the uncovered currencies from `not_covered`, before the owner applies. A line in `taken_out` can appear in `review_lines` too: that is the close flagging it.
- **Practice checks:** the practice database was rebuilt for section 12, so the old practice key no longer works: run the practice seed again (the run that prints `EXPENSE_PAT`) for a new key and the account. Read `EXPENSE_PRACTICE_ACCOUNT_ID` from the seed's output and pick that account, `BCP-0000`, in the account screens; match nothing on the name `Practice account`; read it on every seed, since a deleted account comes back with a new id. Don't name it `contract-…` or `freshman-…`, and don't convert it to a person.
- **Banks and numbers:** read the bank picker from `GET /banks`. Show an account's `name` as the engine sends it; never build or type a bank account's name. The account form sends `bank_code` and an optional `last4` for a bank account, `name` for a person. Add the number screens: a replacement (`new_number`), a fix or first number (`current_number`), a removal (`current_number: null`). Show every number with its start and end day, and `NUMBER_IN_COMPLETED_STATEMENT` with its message.
- **Kind changes:** send `{"name": …}` to `make-person` and `{"bank_code": …, "last4": …}` to `make-account`.
- **Name matching:** match a typed account name against the engine's `name` (`BCP-5678`). On the sheet import, when an entry is `ambiguous`, ask which account is meant and send its `id` in the `names` table.
- **Statement upload:** give an account its number before uploading its paper, and show `STATEMENT_NUMBER_MISMATCH` and `ACCOUNT_HAS_NO_NUMBER` on the account picker with their messages; a card replacement is recorded as a new number with its start day, never by moving the account. Your upload tests' accounts need a number ending `0000` for the samples.
- **Catch up** from `f82426fb0a099676` through `x-changelog`.

## Done when

The TUI works on `1002f105c6bacdf1` against its practice engine, started from the engine repo's root with:

```
deploy/local/client-practice-engine.sh 8002
```

It serves only the engine's last commit, so it already serves this version.

- The TUI has read up to `1002f105c6bacdf1` and says so.
- The currency picker comes from `GET /currencies`; no PEN/USD list is left in the TUI.
- A transaction on a soles-only account is created without choosing a currency; on the Visa the app asks for one.
- A dollar purchase moved by account to a soles-only account shows as the same amount in soles, and the app says it was not converted.
- The account form creates an account with its opening balances in one save, and edits the name and every currency's opening balance in one save. A refused save leaves nothing half-saved and shows the refusal on the right field.
- Removing a currency that is in use shows the refusal naming that currency.
- Typing `1e5000`, or any amount past the bound, is refused with the engine's bound, and no screen crashes printing it; a file holding such a row shows the refusal on that row.
- A transaction logged at 23:30 in Lima shows on its own day in every list, and filtering by that day finds it.
- A statement PDF's preview shows the lines the close will flag, under their currency, before anything is applied; a paper with nothing to flag shows none.
- The TUI's tester logs a transaction on `BCP-0000` in the real app against the practice engine, with the id the seed printed.
- The account form creates a bank account by picking `BCP` and typing a last 4, and it shows as `BCP-5678`; a person keeps its typed name.
- A card's replacement is added from its start day: the card shows the new number's name, its balance and statements unchanged, and the old number with its end day; a start day inside a completed month shows the engine's refusal naming the statement.
- Turning a bank account into a person asks for the person's name; turning a person into a bank account asks for the bank and an optional last 4.
- A month's PDF uploaded to the wrong account shows the engine's refusal naming both numbers, and nothing is written; the right account's paper, a replaced card's earlier months included, closes the month as before.
