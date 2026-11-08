# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks wait in [to-engine/](to-engine/), one file each, until
handed over.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes it. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### The engine's contract moved to ce7749236717b163
Asked 2026-11-07 · Blocks: the acceptance check of [empty lists' `?` cards, and leaving a screen
while it draws](specs/empty-lists-and-leaving-mid-draw.md), and every new task

The practice engine's contract is ten changes past the one this client last caught up to,
`f82426fb0a099676`: new `GET /currencies`, opening balances set with `POST /accounts` and
`PUT /accounts/{id}`, `currency_code` optional on an account holding one currency, a new
statement sample, and wording. The version check prints:

```
the engine's contract version has changed: saved f82426fb0a099676, engine ce7749236717b163.
what the contract changed since f82426fb0a099676, newest first:
  ce7749236717b163  2026-11-07
    changed: wording only, *Base Conventions* → *Client-supplied UUIDs*: the keys a taken id is refused on now name `opening_balances.<code>.transaction_id`, for an opening balance `PUT /accounts/{id}` sets, as that route's section already says.
  f3ee39cdc9d602e5  2026-11-07
    changed: wording only, the overview and the reasons `UNSUPPORTED_VALUE` and `CURRENCY_NOT_HELD`: the supported currencies are the ones `GET /currencies` lists. A client keeps no list of its own.
  21bba425e1f9a489  2026-11-07
    changed: `DELETE /accounts/{id}/currencies/{currency_code}`: `HAS_TRANSACTIONS` and `IN_LIVE_STATEMENT` are keyed on `currency_code` (they were on `account_id`), as `LAST_CURRENCY` is, and their messages name the currency: `"Must not be used by any active transaction in USD."` and `"Must be a currency no live statement holds in USD, draft or completed: delete the statement first."`, the code as in the path. A client reading `fields.account_id` or `reasons.account_id` on this route for these two refusals reads `currency_code` instead. `ACCOUNT_ARCHIVED` stays on `account_id`; `DELETE /accounts/{id}` keeps its refusals, keys and messages as they were.
    changed: *Bank Accounts*, the account response's `currencies`: states that a live account always lists at least one currency (it is created with at least one, its last currency is never removed, and it is deleted whole); the `[]` for an account holding none is gone from the wording. Wording only.
  5278888de6fdb51a  2026-11-07
    added: `GET /statements/samples` and `GET /statements/samples/{sample}`: the sample `card-soles-only`, a soles-only card's made-up paper (26 April to 25 May 2025) whose dollars print at zero with no dollar row. Uploaded for an account holding soles alone, it closes the month in soles only, on a dry run and an apply. It follows `card-no-dollars` in the list. Its `balances` hold soles only: a currency the paper shows at zero with no row has no entry, as the upload leaves it out.
    changed: `POST /statements/import`, *The paper's layout*: any label on a card's undated line that carries an amount is read as one entry on the statement's last day, in the direction printed, not only the labels the section names.
    changed: `POST /statements/import`, *Concurrency*: names the `409` on `category_id` or `hashtag_ids` (`CONCURRENT_CHANGE`) when the pending category or hashtag is deleted while a created row is filed under it, and states that only a write creating a statement in the paper's month or moving one into it between the upload's read and its write reaches `STATEMENT_MONTH_TAKEN`: a `POST /statements`, a `PUT /statements/{id}` or another upload's apply.
    changed: `GET /bank-lines/{id}`, `is_opening_balance`: no longer mentions a `PUT` of a statement's order, a route that does not exist.
    changed: `POST /transactions`, `OPERATION_CODE_EXISTS`: states both texts as sent, `error.message` `"Another bank line on this account already has operation code '<code>'."` and the field's `"Must not be an operation code already on this account."`; `POST /transactions/batch`, `PUT /transactions/{id}`, the bank-line writes and `POST /transactions/import` say they word it alike. Wording only; the engine did not change.
    changed: `POST /transactions/batch`: a repeated operation code (`DUPLICATE_IN_REQUEST`) is refused on every item of the later line, the first keeping its place. Wording only.
    removed: `POST /accounts/{id}/make-account` no longer declares `HAS_RECONCILIATION`: no person ever holds a statement, so it was never sent. `POST /accounts/{id}/make-person` keeps it.
    changed: reason `HAS_RECONCILIATION`, its description: sent only by `POST /accounts/{id}/make-person`; an account that has had a statement never becomes a person. Wording only.
  11ab349bdfc38647  2026-11-07
    changed: `POST /transactions/import-sheet`, *Opening balances*: a row of zero amount (`skipped`) no longer counts as a row of the same currency of the account dated before a `SALDO INICIAL` row. A currency's opening balance is its first `SALDO INICIAL` row of a non-zero amount with no non-zero row of that currency dated before it: a `SALDO INICIAL` of `0.00` on 2 January and one of `1,000.00` on 5 January import the 5 January row as the opening balance (it was an ordinary row). If this leaves two `SALDO INICIAL` rows on the first non-zero day, both are refused (`DUPLICATE_IN_REQUEST`), as before.
  14fb4741b9db37b8  2026-11-07
    added: `PUT /accounts/{id}`: `opening_balances`, an object keyed by currency code, sets, changes or clears the opening balance of any currency the account holds in the same write as the account's own fields, all or nothing. An entry is: a **set** (the currency has none): the body of `POST /accounts/{id}/opening-balance` without `currency_code` (`transaction_id`, `amount_cents`, `date` required, `title` optional), judged by that route's rules; a **change** (it has one): `amount_cents`, `date`, `title`, each optional, judged by the rules `PUT /transactions/{id}` applies to that opening balance (`LOCKED` in a completed statement, `SEALED_PERIOD`, `ZERO_AMOUNT`, `FUTURE_DATE`, `ACCOUNT_ARCHIVED`), a `transaction_id` sent there `UNKNOWN_FIELD`; a **clear** (`null`): the opening balance is deleted by the rules of `DELETE /transactions/{id}`, and a currency with none is `422 NO_OPENING_BALANCE`. Each refusal is keyed `opening_balances.<code>.<field>` (or `opening_balances.<code>` for the whole entry: a code the account does not hold, `CURRENCY_NOT_HELD`; one `GET /currencies` does not list, `UNSUPPORTED_VALUE`); a refusal of any part writes nothing, the name and statement code included. The account's `version` moves and its `UPDATED` entry is written only when `name`, `color`, `sort_order` or `statement_code` is sent; each opening balance logs the entry its own route logs. The answer is the account, each currency's `opening_balance_transaction_id` set or `null`. The refusal order is in the route's *Refusals*. On an archived account a set is refused as `POST /accounts/{id}/opening-balance` refuses it (`INVALID_REFERENCE`), a change as `PUT /transactions/{id}` does (`ACCOUNT_ARCHIVED` on each field sent) and a clear as `DELETE /transactions/{id}` does (`409 ACCOUNT_ARCHIVED`), each on `opening_balances.<code>[.<field>]`, and the request is refused whole; a request without `opening_balances` saves the archived account's own fields as before. New reason `NO_OPENING_BALANCE`: a clear of a currency with no opening balance.
    changed: wording only, *Base Conventions* (*Settings preconditions*), *Bank Accounts* (*An archived account*), *Transactions (Ledger)* (*Opening balances stay put*, *Hashtags on a transaction*, *Bank lines*) and *Bank Lines*: `PUT /accounts/{id}` is listed with the writes that set an opening balance, and its *Sent at the same moment* states how it is ordered with the account's other writes.
  edbafcc162850075  2026-11-07
    added: `POST /accounts`: each entry of `currencies` may carry `opening_balance`, the body of `POST /accounts/{id}/opening-balance` without `currency_code` (the entry's own is used; sending one is `UNKNOWN_FIELD`): `transaction_id`, `amount_cents`, `date`, optional `title`. The account is created with each currency's opening balance in one write, all or nothing: a refusal of any part leaves no account, no currency and no opening balance. Each opening balance is judged by the rules of that route and refused on `currencies.<i>.opening_balance.<field>`: a zero `amount_cents` (`ZERO_AMOUNT`), a `date` in the future (`FUTURE_DATE`) and a `transaction_id` carried twice in the request (`DUPLICATE_IN_REQUEST`) with the other request-shape refusals at step 1; a taken `transaction_id` (`ID_EXISTS`, `409`) at step 2, named in one answer with the account's own taken `id`; after the account's rules, in this order: `@Opening` made on first use (`RESERVED_NAME_HELD`, `CONCURRENT_CHANGE`, on `currencies.<i>.opening_balance.category_id`), missing settings (`SETTINGS_MISSING` on `user_settings`, read only when an entry carries `opening_balance`), a sealed day (never on a new account), the line codes used up (`LIMIT_REACHED`). The answer is the account with each currency's `opening_balance_transaction_id` set to the `transaction_id` sent and its `current_balance_cents` the opening balance. Each opening balance is logged as the separate route logs it. An entry without `opening_balance` is created as before.
  2105213d3035b4d4  2026-11-07
    changed: `PUT /transactions/{id}` and `PUT /bank-lines/{id}` sending `account_id` and no `currency_code`: onto an account that holds the line's currency, the line keeps it, as before; onto an account that does not but holds exactly one live currency, the line moves to that currency, every live part of a bank line with it, the amount unchanged. A $100.00 outflow moved to a soles-only account is a S/ 100.00 outflow, and the answer's `currency_code` is `"PEN"`. It was `CURRENCY_NOT_HELD` on `account_id`. The move is exactly the one sending that `currency_code` too, with every rule of it (the lock, an archived account, an opening balance, the statement assignment, a sealed day, an operation code taken in the new currency); a refusal stays keyed on `account_id`. Onto an account holding several currencies, none the line's, it is still `CURRENCY_NOT_HELD` on `account_id`, the message now naming the currencies held (`"The account holds no USD: it holds EUR, PEN."`).
    changed: *Transactions (Ledger)* → *Moving a transaction* states that a move between currencies never converts the amount.
  b7c5772dbcc8b811  2026-11-07
    changed: `POST /transactions` and each item of `POST /transactions/batch`: `currency_code` is optional. Left out on an account holding exactly one live currency, the transaction is in that currency (the answer's `currency_code` names it). Left out on an account holding several, it is `422` on `currency_code` (`transactions.<i>.currency_code` in a batch), reason `REQUIRED`, `"Must be one of the account's currencies: PEN, USD."`, the codes in `currency_code` order; nothing is written. An explicit `null` is still `422` (`INVALID_FORMAT`). A currency sent behaves as before. The `REQUIRED` is judged with the account, after a taken `id` (*Which refusal comes first on a create*, step 3); an unknown account is still `INVALID_REFERENCE` on `account_id`.
    changed: `POST /transactions/batch`: the items of one `line_group` are compared on the currency each lands in, so on a soles-only account an item sending `PEN` and one leaving `currency_code` out are one line; one sending `USD` beside one leaving it out is `CURRENCY_NOT_HELD` on the first and `LINE_GROUP_FIELDS_DIFFER` on the second. An operation code is unique per settled currency. Both are judged with the account (step 3), not at step 1, which compares only what the items sent; a batch sent again still answers `ID_EXISTS`.
  385b112ad7f34bb8  2026-11-07
    added: `GET /currencies`: the currencies the engine accepts, `{"items": [{"currency_code": "PEN"}, {"currency_code": "USD"}]}`, in `currency_code` order, the same for every user. Read it instead of keeping a list of codes: it is the list every `currency_code` the engine takes is checked against (`UNSUPPORTED_VALUE`).
    changed: wording only, *Base Conventions*, *Bank Accounts*, *Transactions (Ledger)*, *Statements* and *Exchange Rates*: a refusal for an unsupported currency points to `GET /currencies` where it named the supported currencies.
Once the change is handled, record the new version with: python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002 --record-version
```

- **A.** Ask the engine coders now for one hand-off file from `f82426fb0a099676` to
  `ce7749236717b163`; record the new version now so the empty-lists spec finishes its check
  (it touches nothing the engine changed); catching up becomes the next spec once the file
  arrives.
- **B.** Ask for the same hand-off file, and leave the empty-lists spec open until it arrives
  and is planned; the version is recorded then.

**Recommended:** A, because the empty-lists spec reads none of what changed, and the hand-off is
needed either way.

### Approve the rewritten specs
Asked 2026-10-29 · Blocks: every spec in [specs/](specs/)

To approve, every question answered: [the official import](specs/before-the-official-import.md).

Answered, waiting on its engine ask (handed over 2026-11-07) and a mockup of the preview:
[a statement PDF's preview names the lines the close will flag](specs/the-preview-names-the-lines-the-close-will-flag.md).

Approved: [accounts carry their numbers](specs/accounts-carry-their-numbers.md), waiting on the
engine.

**Recommended:** approve the rest.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **The shared practice user holds no accounts,** so the tester proves LOG bar and account
  checks with unit tests only. Nothing you see changes. Waits on the engine ask "Give the
  shared practice user an account that every reseed keeps".
- **No live test sends a zero-amount `SALDO INICIAL` row dated before a person's opening
  balance.** Nothing you see changes. It waits on the engine ask "Say whether a zero-amount row
  dated earlier stops a sheet row being the opening balance"; then
  [test_sheet_import.py](../tests/contract/test_sheet_import.py) pins the answer.
- **A huge amount reads, then crashes what prints it.** `parse_amount`
  ([quickadd/money.py](../expense/quickadd/money.py)) reads a finite `1e5000`, typed or in either
  importer's file, as an integer of over 4,300 digits, and printing it (the bank preview, a row's
  repr) raises `ValueError`. The live contract states no largest amount, so it waits on the
  engine ask "State the largest amount the engine takes, and refuse past it everywhere".
- **A row's day shows in UTC.** The engine sends times in UTC, and every list shows the first
  ten characters as the day ([formatting.py](../expense/formatting.py) `format_short_date`), so a
  row timed after 19:00 in Lima shows the next day, though the engine counts it on its own day.
  Rows dated by day alone (00:00 in the user's time zone) show right. Waits on the engine ask
  "Send each transaction's calendar day with it"; the lists then show that day.
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown.
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **The drift check reads a nested union of lists the old way.** `_list_items` in
  [check_fixture_drift.py](../scripts/check_fixture_drift.py) reads `anyOf [A[], anyOf [B[],
  C[]]]` as A's items alone, where `_object_schema` reads nested unions whole. No marked answer
  has such a shape today. Nothing you see changes.
- **No unit test pins a union that contains itself.** `_alternatives` in
  [check_fixture_drift.py](../scripts/check_fixture_drift.py) drops a `$ref` already seen on its
  path, so such a union ends; nothing in
  [test_fixture_drift_script.py](../tests/unit/test_fixture_drift_script.py) proves it.
- **The theme's rule comment repeats tui.md "Amounts" and gets one detail wrong.** The comment
  in [theme.py](../expense/tui/theme.py) says `AMOUNT_RULE` covers dashboard totals, but Home's
  inflow and outflow rows are plain; only the net uses it. Cut it to a pointer at
  [tui.md](tui.md) "Amounts", its one home. Nothing you see changes.
- **Bank files become the intake.** Plan: [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside the TUI
  ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html), which
  also records the ⌘E conflict). Convenience, not access: `+` opens the LOG bar inside the app.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **The "no statement" list under 68 columns.** The Statements screen's list of lines in no
  statement cuts its amount, then its currency, under 68 columns, and under 62 its caption wraps a
  lone `·` onto a line of its own. Parked 2026-11-07: the app is built for 80 columns.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
