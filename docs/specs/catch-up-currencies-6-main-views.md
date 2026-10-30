# The main views on an account and its currencies

Catches up to contract `f82426fb0a099676`, from `e020782e3579d011`: the engine's hand-off of
2026-10-29, "An account holds its currencies: every route names an account and a currency code;
holders are gone" — its parts on what the owner sees of an account and a currency: the accounts
list, the account's writes, adding and removing a currency, the opening balance per currency,
`/dashboard`'s account rows and a transaction's currency (its sections 2 to 8 and 12).

The seven specs of this catch-up, run in this order:

1. part 1, the app's reads and writes (done on 2026-10-30)
2. part 2, the PDF upload and the two imports (done on 2026-10-30)
3. part 3, the live tests' foundation (done on 2026-10-30)
4. [catch-up-currencies-4-live-suite-upload-lines-kinds.md](catch-up-currencies-4-live-suite-upload-lines-kinds.md)
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md)
6. this one
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)

**Status:** draft, written 2026-10-29 for the owner to approve. It runs after
[catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md),
and [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md) runs
after it. Every screen task waits on its question's mockup, picked by the owner.

**Split:** fifteen tasks, more than one spec's eight, so it runs as two halves, each closed by
its own acceptance check and the librarian's sweep before the next starts: **6a, the accounts**
(tasks 1 to 8) and **6b, the currency as its own field** (tasks 9 to 15).

---

## Why

In the engine an account now holds its currencies: the Visa is one account holding soles and
dollars, ALEJO one person holding soles and dollars, each currency with its own balance, never
added to the other (contract: "What an account is", "Its currencies")
(contract: "Bank Accounts", "No conversion and no mixing"). The Visa and ALEJO are each made in
one write with both currencies (contract: POST /v1/accounts); a currency is added later, or
removed while nothing is booked in it; archive, kind, rename and delete act on the account, every
currency at once (contract: "What an account is", "An account is archived whole").

Specs 1 to 5 keep every screen working on that model with as little change on screen as it
allows: where a list or a picker showed one row per currency, it shows one row per account and
currency, named as the engine's owner ruling says, "VISA Infinite Sapphire · USD". This spec makes
the screens show what the engine now holds:

- **An account is one row,** on Manage ▸ Accounts and on Home, its currencies' balances on it,
  each in its own currency, never summed.
- **A new account is made with its currencies,** the Visa or ALEJO in soles and dollars at once;
  a currency is added to an account and removed from it.
- **The opening balance is per currency:** the Visa's soles and its dollars each have their own.
- **The currency is picked as its own field, like any other field** (owner, 2026-10-29): in the
  LOG bar, on the Edit form, in the ledger's columns, filter and bulk edit. The
  "<account> · <code>" rows go from every picker.

## What it must do

**6a, the accounts**

1. **Manage ▸ Accounts lists one row per account,** bank accounts then people, each showing its
   currencies' balances, each in its own currency and never summed, as question 1 picks
   (contract: GET /v1/accounts, "Ordering").
2. **Home's BANK ACCOUNTS and PEOPLE list one row per account** with its currencies, as question
   2 picks; `⏎` opens the ledger as question 2 picks
   (contract: GET /v1/dashboard, "Balances are native only").
3. **The New form makes an account with its currencies in one write,** a bank account with its
   name, its currencies, its statement code typed once and its colour; a person with its name,
   its currencies and its colour, no code line; one `POST /accounts`, as question 3 picks
   (contract: POST /v1/accounts).
4. **The Edit form changes the account in one write:** name, colour and statement code in one
   `PUT /accounts/{id}`; the code line stays on a bank account, an emptied line clearing the
   code (contract: PUT /v1/accounts/{account_id}, "`statement_code`").
   `STATEMENT_CODE_EXISTS` reads in the engine's words alone.
5. **Each currency has its own opening balance on the Edit form,** an amount and a day per
   currency, sent with its `currency_code`, one request per currency, as question 5 picks, and
   read with the owner's words: no line under the amount; on its right `debt` when negative,
   `credit` when positive, nothing while empty or `0.00`, the same on every account, bank or
   person (contract: POST /v1/accounts/{account_id}/opening-balance). Today a person's `opening`
   line explains the sign in a bank account's words (`350.00 is money you have`), where a
   person's balance is a debt.
6. **A currency is added to an account** with `POST /accounts/{id}/currencies`, as question 6
   picks; `DUPLICATE_CURRENCY` and an archived account read in the engine's words
   (contract: POST /v1/accounts/{account_id}/currencies, "Refusals").
7. **A currency is removed from an account** with
   `DELETE /accounts/{id}/currencies/{code}`, after a question only `y` answers, as question 7
   picks; `LAST_CURRENCY`, `HAS_TRANSACTIONS`, `IN_LIVE_STATEMENT` and `ACCOUNT_ARCHIVED` read as
   question 7 picks (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals").
8. **`a`, `t` and `d` act on the whole account,** every currency at once: `a` archives and
   unarchives it (contract: POST /v1/accounts/{account_id}/archive, "Every currency at once"),
   `t` turns it into a person and back, its refusals in the engine's words
   (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"), `d` deletes it after its
   question, which names its currencies, and `IN_LIVE_STATEMENT` reads in the engine's words
   (contract: DELETE /v1/accounts/{account_id}, "Refusals"). The app's row for
   `HAS_STATEMENT_CODE`, which no operation sends, goes from tui.md's "When the engine says no"
   table and from the tests.

**6b, the currency as its own field**

9. **A line typed in the LOG bar names its currency as a field of its own,** picked as question
   8 picks, and is sent with `account_id` and `currency_code`
   (contract: POST /v1/transactions, "`account_id` and `currency_code`"). The legend row names
   the field, and the account peek follows the picked currency. A currency the account does not
   hold is refused in the engine's words, nothing written, and the bar shows why.
10. **The Edit form has a currency line,** as question 9 picks: a move to another currency of the
    same account is one `PUT` with `currency_code`
    (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction")
    (contract: PUT /v1/bank-lines/{bank_line_id}, "`account_id` and `currency_code` move the line").
    On a line in a draft statement it stays in that statement, the owner's answer of 2026-10-28
    (question 8 A in [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)
    "What the owner settled"). The line is read-only where the line's `edit_limits` names
    `currency_code` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields").
11. **The ledger shows each row's currency** as question 10 picks, and **filters by currency**,
    with `?currency_code=` beside `?account_id=`, from where question 2 picks
    (contract: GET /v1/transactions).
12. **The ledger's bulk edit moves rows to another currency,** as question 11 picks, one `PUT`
    per row, as `b`, `c` and `h` write today.
13. **No picker shows "<account> · <code>" rows:** the LOG bar's `$` picker, the Edit form's
    account line and the ledger's `b` list one row per account. The import door's "Which account
    is this file?" asks no currency: a bank download's rows each go to the account's currency in
    their own `Moneda` (contract: POST /v1/transactions/import, "Accounts"); how that list reads is
    [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)'s.
14. **Each new write lands with unit tests** for its happy path and each refusal it handles; the
    live tests of the account routes are
    [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md)'s.
15. **The holder mockups go, with their links:** `expense-world-holders-where.html`,
    `-new-account`, `-archive`, `-delete-in-statement`, `-kind-whole`, `-new-person`,
    `-person-line`, `-person-to-bank`, `-card-field` and `expense-world-holder-pick-line.html` in
    [mockups/](../mockups/), and the mockups this spec's picks replace
    (`expense-world-person-opening-hint.html` among them), each once its new mockup is picked.

## How the owner knows it is done

1. On Manage ▸ Accounts, `n` makes the Visa in soles and dollars, and ALEJO in soles and dollars,
   each in one write, and each shows as one account with a balance per currency, never summed.
2. You set, change and clear the Visa's statement code on its Edit form; the code shows on its
   row.
3. `a` on the Visa archives the whole account, both currencies; `a` again unarchives it.
4. `t` on ALEJO turns him into a bank account, both currencies, and `t` again back into a
   person; an account that has had a statement is refused in the engine's words.
5. Dollars are added to a soles-only account; a currency with nothing booked is removed after
   `y`; removing the last currency, or one holding a transaction, is refused as question 7 picks,
   nothing written.
6. On the Visa's Edit form, the soles and the dollars each take their own opening balance, the
   word on the right reading `debt` or `credit`.
7. An account with nothing in it is deleted after `y`; one a live statement holds is refused in
   the engine's words.
8. Home shows the Visa once, with a balance per currency, under BANK ACCOUNTS, and ALEJO once
   under PEOPLE.
9. A line typed in the LOG bar names its currency as question 8 picks and saves in it; a currency
   the account does not hold is refused, nothing written, and the bar says why.
10. A line moved to its account's other currency on the Edit form saves in one write.
11. The ledger shows each row's currency, lists one currency of an account, and moves selected
    rows to another currency.
12. No picker shows a "<account> · <code>" row, and no request sends a `/holders` route,
    `POST /accounts/{id}/move`, `?holder_id=` or a per-currency id.
13. The unit suite and the drift check pass, after each half.

## What the owner settled

- **The currency is picked as its own field, like any other field** (owner, 2026-10-29): in the
  LOG bar, the Edit form, the ledger's filters and bulk edit and the account forms.
- **A new account is made in one form, sent as one write** (owner, 2026-10-28, question 2 C of
  the cards spec): its name, its statement code typed once and its currencies (the Visa: PEN and
  USD).
- **`t`'s refusals read in the engine's words alone** (owner, 2026-10-28, question 6 A of the
  cards spec): `KIND_UNCHANGED`, `ACCOUNT_ARCHIVED`, `HAS_RECONCILIATION`.
- **`STATEMENT_CODE_EXISTS` reads in the engine's words alone** (owner, 2026-10-28, question 9 A
  of the cards spec).
- **`d` on an account a live statement holds** shows `IN_LIVE_STATEMENT` in the engine's words
  alone (owner, 2026-10-28, question 10 A of the cards spec).
- **The sheet import's `--create-names` line counts accounts alone** (owner, 2026-10-28, question
  8 of the cards spec): `Created 4 accounts, 3 categories, 2 hashtags.`, built by
  part 2 of the currencies catch-up (done on 2026-10-30).
- **The opening balance's words** (owner, 2026-10-28, the owner's design for a person's
  `opening` line, drawn in
  [expense-world-person-opening-hint.html](../mockups/expense-world-person-opening-hint.html)):
  no line under the amount; on its right `debt` when negative and `credit` when positive, then
  the currency; a, nothing on the right while the line is empty or `0.00`; b, the same word on
  every account.

## Questions for the owner

1. **Manage ▸ Accounts with a two-currency account** [mockup to draw].
   - **A.** One row per account, a currencies cell holding every balance:
     `-2,340.50 PEN · -185.20 USD`.
   - **B.** The account's row, then an indented line per currency under it, each with its
     balance.
   - **C.** One row per account, a PEN column and a USD column.

   **Recommended:** B: adding and removing a currency, and its opening balance, act on one
   currency, so each currency needs a line to put the cursor on. The mockup also draws the
   delete question's body naming the account's currencies, and an archived account dimmed with
   its lines.
2. **Home's BANK ACCOUNTS and PEOPLE** [mockup to draw].
   - **A.** One row per account, its balances side by side, as 1 A.
   - **B.** The account's row, then an indented line per currency, as 1 B.

   **Recommended:** B, the same as Manage ▸ Accounts. Under B, `⏎` on the account's row opens
   the ledger on the account, every currency, and on a currency's line on that currency alone
   (`?account_id=` and `?currency_code=`). Also: a person in two currencies folds into
   `▶ N settled` only when every currency reads `0.00` (recommended), or each currency's line
   folds alone (contract: "People / Person Accounts", "A settled person is never hidden").
3. **The New form** for a bank account and for a person [mockup to draw].
   - **A.** A `currencies` line taking one or both, picked as the hashtags line picks them: `⏎`
     adds the highlighted one, an empty `⏎` goes on.
   - **B.** A choice line: `PEN`, `USD` or `PEN + USD`.

   **Recommended:** A: the same picking every list line uses. Under either, a bank account's form
   then has its statement code line, and a person's has none.
4. **Removing the app's `HAS_TRANSACTIONS` line from a currency's removal.** Today a refused
   delete of an account that has transactions adds the app's line `To retire it instead, archive
   it: press a.`. The engine sends the same reason, on the same key, when a currency holding a
   transaction is removed, and there archiving puts away every currency, not the one.
   - **A.** The engine's words alone on a currency's removal; the line stays on the account's
     delete.
   - **B.** The line on both.

   **Recommended:** A.
5. **The opening balance per currency on the Edit form** [mockup to draw].
   - **A.** One `opening` and `as of` pair per currency, each label naming its currency
     (`PEN opening`, `PEN as of`, `USD opening`, `USD as of`), the word on the right alone
     (`debt`).
   - **B.** As A, the word on the right followed by the currency (`debt · PEN`), as picked for one
     currency.
   - **C.** A heading line per currency, with `opening` and `as of` under it.

   **Recommended:** A: once the label names the currency, the currency on the right says it
   twice.
6. **Adding a currency** [mockup to draw].
   - **A.** A key on the account's row: it lists the currencies the account does not hold, and
     `⏎` adds the picked one at once, as `a` writes.
   - **B.** A `currencies` line on the Edit form; the save adds what was picked.

   **Recommended:** A: one key, one write, and the Edit form keeps to the account's own fields.
7. **Removing a currency** [mockup to draw].
   - **Where:** **A.** `d` on the currency's line (under 1 B), asking first, only `y` removing
     it. **B.** On the Edit form's `currencies` line (under 6 B), asking first on save.

     **Recommended:** A: `d` is the app's one destructive key, and the question names the
     account and the currency.
   - **On `LAST_CURRENCY`** (the account's last currency): **A.** The engine's words alone.
     **B.** The engine's words, then the app asks `Delete the account instead?`, only `y`
     deleting it. **C.** The engine's words and a line of the app's: `To delete the account,
     press d on its row.`

     **Recommended:** A, as the owner picked for a refused account delete (question 10 A of the
     cards spec): deleting an account is a choice of its own. The engine suggests B.
8. **How the currency is typed in the LOG bar** [mockup to draw]. The owner wants a field you
   select, like any other field.
   - **A.** A token of its own, with a mark of its own beside `$`, `@` and `#`, picked from a
     list of the account's currencies as they are.
   - **B.** A step after the account: once `$Visa` names an account holding two currencies, the
     picker lists them for the currency.
   - **C.** The code typed after the amount: `-45.50 USD`.

   **Recommended:** A: one token per field, as every other field is typed, and the legend row
   names it. Also, on an account holding one currency: the line takes it with nothing typed
   (recommended: the account holds no other), or the currency is always typed.
9. **The Edit form's currency line** [mockup to draw].
   - **A.** A `currency` line right after `account`, listing the currencies of the account on the
     line above.
   - **B.** As A, listing every currency; one the account does not hold is refused in the
     engine's words.

   **Recommended:** A: the list shows what the account holds, read from the engine.
10. **The ledger's currency** [mockup to draw].
    - **A.** A `Cur` column of its own beside Amount.
    - **B.** The code after the amount, in the Amount column.

    **Recommended:** A: the currency is its own field, so it has its own column.
11. **Moving rows to another currency in bulk** [mockup to draw].
    - **A.** A key of its own beside `b`, `c` and `h`, picking the currency; `b` keeps each row's
      currency, and a row whose new account lacks it is refused in the engine's words.
    - **B.** `b` picks the account, then the currency.

    **Recommended:** A: one key per field, as the owner asked.

---

## Tasks

Each screen task waits on its question's mockup, picked by the owner. The builder reads the
question, the files named, and the tui.md section named.

**6a, the accounts**

1. **Manage ▸ Accounts, one row per account** (point 1; question 1). `account_rows` and
   `_HEADERS` in [accounts.py](../../expense/tui/screens/accounts.py) and its tests; tui.md §2
   "Manage ▸ Accounts is a table of …". *Passes if:* a fake engine's Visa in PEN and USD and
   ALEJO in PEN and USD each draw as one account in the picked layout, each balance in its own
   currency and none summed, archived ones dimmed whole; the unit tests pin it; tui.md says so.
2. **Home's BANK ACCOUNTS and PEOPLE** (point 2; question 2). The account rows of
   [home.py](../../expense/tui/screens/home.py) and its tests; tui.md §2 "Home is four months of
   the ledger". *Passes if:* `/dashboard` rows `{id, name, currencies}` draw as question 2
   picks, the settled fold follows its answer, `⏎` opens the ledger on the account; the tests
   pin each.
3. **The New form** (point 3; question 3). `NewAccountScreen` in
   [create_forms.py](../../expense/tui/screens/create_forms.py) and its tests; tui.md §2 "A bank
   account's statement code is a line of its own on New and Edit". *Passes if:* a bank account
   and a person are each one `POST /accounts` with `currencies`, the person with `is_person:
   true` and no code line, nothing sends `currency_code` at the top or `/people`; each refusal
   the form meets shows the engine's words with the cursor on its line; the tests pin each.
4. **The Edit form's account write** (point 4). The account Edit form in
   [create_forms.py](../../expense/tui/screens/create_forms.py), the `STATEMENT_CODE_EXISTS` line
   in [errors.py](../../expense/errors.py) and their tests; tui.md §2 "A bank account's statement
   code …". *Passes if:* name, colour and code go in one `PUT /accounts/{id}`, an emptied code
   as `null`; `STATEMENT_CODE_EXISTS` shows the engine's words alone; the tests pin each.
5. **The opening balance per currency** (point 5; question 5). The opening-balance lines of the
   account Edit form in [create_forms.py](../../expense/tui/screens/create_forms.py) and its
   tests; tui.md §2 "An account's opening balance lives on its Edit form". *Passes if:* each
   currency of the account has its pair, reads its own `opening_balance_transaction_id`, and
   saves with `currency_code` in its own request; the word on the right reads `debt`, `credit`
   or nothing as settled; a refusal names its currency's line; the tests pin each.
6. **Adding a currency** (point 6; question 6). [accounts.py](../../expense/tui/screens/accounts.py)
   (or the Edit form, as question 6 picks) and its tests; tui.md §4 for a new key. *Passes if:*
   one `POST /accounts/{id}/currencies` adds the picked currency and the list reads fresh;
   `DUPLICATE_CURRENCY` and `INVALID_REFERENCE` show the engine's words; the tests pin each.
7. **Removing a currency** (point 7; questions 4 and 7). [accounts.py](../../expense/tui/screens/accounts.py),
   [errors.py](../../expense/errors.py) and their tests; tui.md §2 "`d` is the TUI's one
   destructive key". *Passes if:* only `y` sends `DELETE /accounts/{id}/currencies/{code}`; each
   of `LAST_CURRENCY`, `HAS_TRANSACTIONS`, `IN_LIVE_STATEMENT` and `ACCOUNT_ARCHIVED` reads as
   questions 4 and 7 pick, nothing written; the list reads fresh after a removal; the tests pin
   each.
8. **`a`, `t` and `d` on the whole account; the holder mockups go** (points 8 and 15). Their
   handlers in [accounts.py](../../expense/tui/screens/accounts.py), `test_tui_account_kind.py`;
   tui.md §2 "`t` turns an account into a person and back", "`d` is the TUI's one destructive
   key" and the "When the engine says no" table. *Passes if:* each key sends its one request on
   `/accounts/{id}…` and the list shows the whole account changed; the delete question names its
   currencies as question 1's mockup draws; `HAS_STATEMENT_CODE` is in no table or test; the
   holder mockups are deleted and no doc links to them.

**6b, the currency as its own field**

9. **The quick-add grammar's currency** (point 9; question 8). [expense/quickadd/](../../expense/quickadd/)
   (`parse.py`, `payload.py`) and its tests. *Passes if:* a line naming an account and a currency
   parses to `account_id` and `currency_code` and its payload carries both; a line on a
   one-currency account follows question 8's answer; mypy and the tests pass.
10. **The LOG bar's currency field** (point 9; question 8). [log_bar.py](../../expense/tui/screens/log_bar.py),
    `QuickAddRefs` in [reads.py](../../expense/reads.py) and their tests; tui.md §4 "The legend
    row" and "The account peek". *Passes if:* the bar picks the currency as question 8 draws, the
    legend names it, the peek reads `?currency_code=` beside `?account_id=`, and a
    `CURRENCY_NOT_HELD` refusal shows under the row, nothing written; the tests pin each.
11. **The Edit form's currency line** (point 10; question 9). [edit_form.py](../../expense/tui/screens/edit_form.py),
    `LINE_FIELDS` in [bank_line_write.py](../../expense/bank_line_write.py) and their tests;
    tui.md §2 "On top, the line's shared fields". *Passes if:* a move to the other currency is one
    `PUT /bank-lines/{id}` with `currency_code`, keeping a draft statement's `statement_id`;
    `edit_limits` naming `currency_code` makes the line read-only; the tests pin each.
12. **The ledger's currency column and filter** (point 11; questions 2 and 10).
    [transactions.py](../../expense/tui/screens/transactions.py) (`transaction_rows`,
    `LedgerFilter`), the filter params in [reads.py](../../expense/reads.py), and their tests;
    tui.md §2 "The filtered ledger is the categorising pass". *Passes if:* each row shows its
    currency as question 10 draws; Home's `⏎` on a currency opens the ledger as question 2 picks,
    reading `?currency_code=` with `?account_id=`, the crumb and legend naming it; the tests pin
    each.
13. **Moving rows to another currency in bulk** (point 12; question 11).
    [transactions.py](../../expense/tui/screens/transactions.py), [bulk_pick.py](../../expense/tui/screens/bulk_pick.py)
    and their tests; tui.md §2 "The bulk pick is a full screen" and §4. *Passes if:* the picked
    currency goes as one `PUT` per row with `currency_code`; a refused row is named by number and
    does not stop the others; the list reads fresh; the tests pin each.
14. **One row per account in every picker** (point 13). `account_choices` in
    [reads.py](../../expense/reads.py), the `$` picker, the Edit form's account line and the `b`
    pick, and their tests; tui.md §2 "Accounts stand in the engine's order everywhere". *Passes
    if:* no picker lists a "<account> · <code>" row; a test fails on one.
15. **The mockups this half replaces go** (point 15). [mockups/](../mockups/) and every doc or
    code comment linking them. *Passes if:* each mockup replaced by a pick of questions 8 to 11
    is deleted, and `test_docs_links.py` passes.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results, as
part 6 of 7 of the reply to `f82426fb0a099676`.

- **Range:** `e020782e3579d011` → `f82426fb0a099676`, shared with the other six specs of this
  catch-up: its sections 2 to 8 and 12, on screen.
- **The engine's "Done when" checks to report on:** "The Visa in soles and dollars, and ALEJO in
  soles and dollars, are each created in one write from the app; a currency is added to an
  account later, and a currency with nothing booked is removed."; "Archiving, unarchiving,
  turning into a person and back, and deleting act on the account, all its currencies at
  once."; "A transaction names an account and a currency it holds; one in a currency the account
  does not hold is refused, nothing written, and the app shows why."
- **The asks it closes:** none; the ask "An account holds its currencies: the holder becomes the
  account, and each account becomes one of its currencies" is closed by the reply of
  [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- The currency pickers read the app's own list of the supported currencies, PEN and USD, since no
  route lists them; the engine ask "A read lists the supported currencies" would let every
  client read the list from the engine instead.
