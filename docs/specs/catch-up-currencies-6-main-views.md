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
4. part 4, the live tests for the upload, bank lines and kinds (done on 2026-10-31)
5. [catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md)
6. this one
7. [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md)

**Status:** approved by the owner on 2026-10-31, its questions answered that day. At the
owner's ask it runs before part 4's tasks 4 to 8 and before
[catch-up-currencies-5-live-suite-account-currencies.md](catch-up-currencies-5-live-suite-account-currencies.md),
which need the practice engine. Its first half, 6a, is done; its second half, 6b, had its tasks
approved by the owner on 2026-10-31, and runs after part 4's tasks 4 to 9.
[catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md) runs
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
- **One currency shows, several are picked** (owner, 2026-10-31): wherever a line names an
  account, an account holding one currency shows no currency picker, its currency just shown;
  an account holding several makes the owner pick one. Questions 12 to 14 draw what that means
  for the Edit form and `b`.
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
  `opening` line, now drawn in the 5 A panes of
  [expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)):
  no line under the amount; on its right `debt` when negative and `credit` when positive, then
  the currency; a, nothing on the right while the line is empty or `0.00`; b, the same word on
  every account.

## Questions for the owner

1. **Manage ▸ Accounts with a two-currency account** ([expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)).
   - **A.** One row per account, a currencies cell holding every balance:
     `-2,340.50 PEN · -185.20 USD`.
   - **B.** The account's row, then an indented line per currency under it, each with its
     balance.
   - **C.** One row per account, a PEN column and a USD column.

   **Recommended:** B: adding and removing a currency, and its opening balance, act on one
   currency, so each currency needs a line to put the cursor on. The mockup also draws the
   delete question's body naming the account's currencies, and an archived account dimmed with
   its lines.

   **Answered C** (owner, 2026-10-31): a PEN column and a USD column, one row per account, a dim `—`
   where the account does not hold the currency. The owner expects to revisit it once accounts hold
   more currencies.

2. **Home's BANK ACCOUNTS and PEOPLE** ([expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)).
   - **A.** One row per account, its balances side by side, as 1 A.
   - **B.** The account's row, then an indented line per currency, as 1 B.

   **Recommended:** B, the same as Manage ▸ Accounts. Under B, `⏎` on the account's row opens
   the ledger on the account, every currency, and on a currency's line on that currency alone
   (`?account_id=` and `?currency_code=`). Also: a person in two currencies folds into
   `▶ N settled` only when every currency reads `0.00` (recommended), or each currency's line
   folds alone (contract: "People / Person Accounts", "A settled person is never hidden").

   **Answered B** (owner, 2026-10-31), for now: the account's row, then an indented line per
   currency. A person in two currencies folds into `▶ N settled` only when every currency reads
   `0.00`.

3. **The New form** for a bank account and for a person ([expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)).
   - **A.** A `currencies` line taking one or both, picked as the hashtags line picks them: `⏎`
     adds the highlighted one, an empty `⏎` goes on.
   - **B.** A choice line: `PEN`, `USD` or `PEN + USD`.

   **Recommended:** A: the same picking every list line uses. Under either, a bank account's form
   then has its statement code line, and a person's has none.

   **Answered A** (owner, 2026-10-31).

4. **Removing the app's `HAS_TRANSACTIONS` line from a currency's removal.** Today a refused
   delete of an account that has transactions adds the app's line `To retire it instead, archive
   it: press a.`. The engine sends the same reason, on the same key, when a currency holding a
   transaction is removed, and there archiving puts away every currency, not the one.
   - **A.** The engine's words alone on a currency's removal; the line stays on the account's
     delete.
   - **B.** The line on both.

   **Recommended:** A.

   **Answered A** (owner, 2026-10-31).

5. **The opening balance per currency on the Edit form** ([expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)).
   - **A.** One `opening` and `as of` pair per currency, each label naming its currency
     (`PEN opening`, `PEN as of`, `USD opening`, `USD as of`), the word on the right alone
     (`debt`).
   - **B.** As A, the word on the right followed by the currency (`debt · PEN`), as picked for one
     currency.
   - **C.** A heading line per currency, with `opening` and `as of` under it.

   **Recommended:** A: once the label names the currency, the currency on the right says it
   twice.

   **Answered A** (owner, 2026-10-31).

6. **Adding a currency** ([expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)).
   - **A.** A key on the account's row: it lists the currencies the account does not hold, and
     `⏎` adds the picked one at once, as `a` writes.
   - **B.** A `currencies` line on the Edit form; the save adds what was picked.

   **Recommended:** A: one key, one write, and the Edit form keeps to the account's own fields.

   **Answered A** (owner, 2026-10-31): drawn as `c`, the key's name a placeholder the owner kept. On
   an account already holding every currency, the key says so.

7. **Removing a currency** ([expense-world-currencies-accounts-picks.html](../mockups/expense-world-currencies-accounts-picks.html)).
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

   **Answered** (owner, 2026-10-31): since question 1 is answered C, there is no currency line.
   **Where:** a remove-a-currency key on the account's row lists the account's currencies; the pick
   asks first, only `y` removing it; `d` on the row still deletes the account, and the remove key
   mirrors question 6's add key. Its pick and question are drawn before its task is built. **On
   `LAST_CURRENCY`:** A, the engine's words alone.

8. **How the currency is typed in the LOG bar** ([expense-world-currencies-transaction-picks.html](../mockups/expense-world-currencies-transaction-picks.html)). The owner wants a field you
   select, like any other field.
   - **A.** A token of its own, with a mark of its own beside `$`, `@` and `#`, picked from a
     list of the account's currencies as they are.
   - **B.** A step after the account: once `$Visa` names an account holding two currencies, the
     picker lists them for the currency.
   - **C.** The code typed after the amount: `-45.50 USD`.

   **Recommended:** A: one token per field, as every other field is typed, and the legend row
   names it. Also, on an account holding one currency: the line takes it with nothing typed
   (recommended: the account holds no other), or the currency is always typed.

   **Answered A** (owner, 2026-10-31): its own token, drawn as `%`, a placeholder the owner kept; on
   an account holding one currency the line takes it with nothing typed.

9. **The Edit form's currency line** ([expense-world-currencies-transaction-picks.html](../mockups/expense-world-currencies-transaction-picks.html)).
   - **A.** A `currency` line right after `account`, listing the currencies of the account on the
     line above.
   - **B.** As A, listing every currency; one the account does not hold is refused in the
     engine's words.

   **Recommended:** A: the list shows what the account holds, read from the engine.

   **Answered A** (owner, 2026-10-31).

10. **The ledger's currency** ([expense-world-currencies-transaction-picks.html](../mockups/expense-world-currencies-transaction-picks.html)).
    - **A.** A `Cur` column of its own beside Amount.
    - **B.** The code after the amount, in the Amount column.

    **Recommended:** A: the currency is its own field, so it has its own column.

   **Answered A** (owner, 2026-10-31).

11. **Moving rows to another currency in bulk** ([expense-world-currencies-transaction-picks.html](../mockups/expense-world-currencies-transaction-picks.html)).
    - **A.** A key of its own beside `b`, `c` and `h`, picking the currency; `b` keeps each row's
      currency, and a row whose new account lacks it is refused in the engine's words.
    - **B.** `b` picks the account, then the currency.

    **Recommended:** A: one key per field, as the owner asked.

   **Answered A** (owner, 2026-10-31): drawn as `m`, a placeholder the owner kept.

12. **The Edit form on an account holding one currency**.
    - **A.** The currency line is shown dim with why, and the bar skips it.
    - **B.** A picker holding the one currency, as 9 A drew it.

    **Recommended:** A: the owner's rule, and a list of one leaves nothing to choose.

    **Answered A** (owner, 2026-10-31).

13. **The Edit form when the account changes to one holding two currencies**.
    A change to a one-currency account follows question 12.
    - **A.** The currency empties and the bar steps to it; nothing saves until one is picked.
    - **B.** It keeps the line's currency when the new account holds it, the bar stopping on it.

    **Recommended:** A: the owner's rule word for word.

    **Answered A** (owner, 2026-10-31).

14. **`b` moving selected rows to another account**.
    To a one-currency account:
    - **A.** Every row takes that currency.
    - **B.** Each row keeps its currency; a row the account lacks is refused in the engine's words.

    To an account holding two currencies:
    - **C.** Each row keeps its own currency.
    - **D.** A second pick asks the currency for every row.

    **Recommended:** B and C: no amount changes currency on several rows at once without being
    asked, and `m` is the currency's own key.

    **Answered A and C** (owner, 2026-10-31): to a one-currency account every row takes its
    currency, the amount as it is, with no question; to an account holding two, each row keeps
    its own.

---

## Tasks

Each screen task waits on its question's mockup, picked by the owner. The builder reads the
question, the files named, and the tui.md section named.

**6a, the accounts**

Approved by the owner on 2026-10-31, with task 6's note naming the account (`Visa Inventada
already holds every currency.`) and `x` as task 7's key (footer `x Remove currency`).
On 2026-10-31 the owner also approved the `x` mockup
([expense-world-currencies-remove-key.html](../mockups/expense-world-currencies-remove-key.html)),
the opening balance's words as built in task 5, `c`'s receipt `Currency added: USD.`, both
picks' titles naming the account (`Add a currency · <account>`, `Remove a currency ·
<account>`), and the `?` card naming `⏎`'s exception on a currency pick.

**6a's acceptance check** passed on the owner's machine on 2026-10-31, against the practice
engine: the drift check, the unit suite, and checks 1 to 8 of "How the owner knows it is done"
tried in the app. Its doc sweep followed, and a review of its tasks on 2026-10-31 approved them.

**6b, the currency as its own field**

Approved by the owner on 2026-10-31, with questions 12 to 14 answered.

Its tasks were all done on 2026-10-31. Its first acceptance check that day found two things, a
live Edit form test and two drift flags, both fixed; it runs again.

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

- **A currency picked by mistake on the New form cannot be un-picked**, as on the hashtag line;
  `esc` and starting over is the way out. Put to the owner on 2026-10-31.
- **`ctrl+s` drops a code typed but not added on the New form's CURRENCIES line**, where the
  Edit form's HASHTAGS line keeps it (`_keep_typed`); the old CURRENCY line did the same.
- **No test pins a `color` refusal landing on the New form's COLOR line**, though the code maps
  it.
- **A taken statement code's test and tui.md name the wrong mockup pane.**
  `test_a_taken_code_on_edit_shows_the_engines_words_alone` in
  [test_tui_statement_code.py](../../tests/unit/test_tui_statement_code.py) and tui.md cite
  "3·2 B" of `expense-world-statement-code-field.html`, the pane with the app's line; the engine's
  words alone are pane 3·2 A.
- **Two opening-balance notes do not name their currency**: `The opening balance is not:` and
  `The opening balance is still loading.`, though more than one currency may be involved.
- **The 5 A mockup colours the summary's amounts by sign**; the Edit form draws them plain, as
  before.
- **A second `c` while the first add is in flight** offers the same currency again, and the
  engine refuses it; `a` and `t` guard with `_toggle_busy`.
- **No mockup draws the LOG bar's words for a `%` that matches nothing**: `"%xx" matches no
  currencies` follows the `$` token's `"$x" matches no accounts`.
- **No mockup draws the LOG bar's words for an account holding three or more currencies** with
  none picked: the bar says `Multi holds PEN, USD and EUR: pick one`, extending the two-currency
  pane's `holds PEN and USD`.
- **The LOG bar writes a picked currency as `%USD`**, as `$` and `@` write the engine's own
  name, where the LOG bar pane the owner picked wrote `%usd`.
- **The LOG bar's staged list has no `cur` column**, which pane 8 A says follows question 10;
  task 12 gives the ledger its column, and the staged list's account cell still reads
  "<account> · <code>".
- **A LOG bar line naming an account that matches nothing, `↵` pressed inside the token**, now
  shows the plain hint `not staged — fix the line and press ↵ again` and the refusal `! not
  staged — "$zzz" matches no accounts` under the bar, as it already did with the caret outside
  the token; before, the hint named the match and the bar showed `no matches — pick something
  that exists`.
- **A LOG bar line refused for its currency and another reason** (`taxi -5 $visa @zzz`) gets the
  hint `not staged — pick a currency and press ↵ again`, naming only the currency; the refusal
  line names both.
- **The Edit form's CURRENCY line carries no `changes every part of the transaction` hint** on a
  transaction of two parts or more, where ACCOUNT, date and title do; the engine writes the
  currency onto every part. No mockup draws it.
- **The picked drawing of question 13 marked a currency the account change took in purple**; the
  Edit form draws the line dim. Was the purple meant for the app, or only a mark on the page?
- **No mockup draws the Edit form's toast for a currency that matches nothing**: `No currency
  matches “…”.` follows the account line's `No account matches “…”.`
- **A line on an archived account** shows its CURRENCY line `read-only` with the shared reason,
  as the engine locks it; no mockup draws it.
- **No mockup draws the ledger filtered on one currency of an account**: its crumb reads
  `Ledger ▸ Visa Inventada · USD`, its legend `filter: account Visa Inventada · USD · 20 of 57
  loaded` and its empty text `(no transactions under Visa Inventada · USD)`, the account's name
  and code as the other screens write them.
- **The ledger's `m` names its move on the `?` card `Move the selection to a currency`** and
  stands before `s` and `d` in the footer with no row selected; no pane draws either.
- **Pane 11 A·3 heads a single refused row `1 of 3 refused`**, where the app's shared rule for
  `b`, `c`, `h` and `m` heads it `Refused`. Which should it be?
- **The New reconciliation form's account picker draws `<name>  ?`** against the engine's
  accounts: `account_choices` puts a `currency_code` beside each name and the account carries
  none. The statement screens' rewrite in
  [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md) replaces
  that form; until then the column reads `?`.
- **The body of `POST /accounts/{id}/currencies`** (`{"currency_code": …}`) and its archived
  refusal (`INVALID_REFERENCE` on `account_id`) are taken from part 5's plan; part 5's live test
  confirms them.
- **Two of `x`'s words wait on the owner** (asked 2026-10-31): the receipt `Currency removed:
  USD.` and `<account> holds no currency.` for `x` on an account holding none. Built with these
  words.
- **After a half-saved save, the note does not say which opening balances went through**:
  when the dollars' opening balance is refused after the soles' saved, the screen shows the
  engine's words alone. Its words go to the owner. The engine ask "An account and its opening
  balances save in one write" removes the half save.
- **The app fills in an account's only currency itself** on the LOG bar, the Edit form's
  account change and `b` (questions 8·i, 13 A, 14 A); the engine ask "An account's only currency
  is taken when a write names none" moves that rule to the engine for every client.
- **No test pins the `?` card's new rule** (`⏎ never changes data, except on a currency pick`)
  or its wrap; and the busy guard's in-flight path is tested for `x` only, `c`'s test setting
  the guard by hand.
