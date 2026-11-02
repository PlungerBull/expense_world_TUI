# What the main views on an account and its currencies turned up

What part 6 of the catch-up to contract `f82426fb0a099676`, the main views (done on 2026-10-31),
turned up while it ran.

**Status: drafted on 2026-10-31; its nine questions answered and the spec and its tasks
approved by the owner on 2026-11-02.** It runs after
part 3's leftovers (done on 2026-11-02) and before [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

- **Words no drawing showed.** Building the currency as its own field, the app needed words that
  no mockup drew; it uses the nearest existing pattern for each, listed in question 2.
- **Four things look different from the drawings,** or were never drawn: the LOG bar's staged
  list keeps "<account> · <code>" where the ledger has a `Cur` column; the Edit form draws a
  currency an account change took dim, where a drawing had it purple; the opening balances'
  summary draws its amounts plain, where a drawing coloured them by sign; and a bulk move with
  one refused row heads it `Refused`, where a drawing wrote `1 of 3 refused`.
- **A few behaviours were never asked:** the Edit form's CURRENCY line has no `changes every
  part of the transaction` hint on a split transaction, though the engine writes the currency
  onto every part; two opening-balance notes do not name their currency; a currency picked by
  mistake on the New form cannot be un-picked; the LOG bar's hint names only the currency on a
  line refused for its currency and something else; and the app's line after an opening
  balance's `OPENING_BALANCE_ACCOUNT_FIXED`, `To move an opening balance, set it on the other
  account's Edit form.`, also shows when `m` moves an opening balance to another currency, where
  it does not fit.
- **Small gaps in the code and tests:**
  - `ctrl+s` drops a code typed but not added on the New form's CURRENCIES line, where the Edit
    form's HASHTAGS line keeps it.
  - A second `c` while the first add is in flight offers the same currency again, and the engine
    refuses it; `a` and `t` guard against this.
  - No test pins a `color` refusal landing on the New form's COLOR line.
  - No test pins the `?` card's rule `⏎ never changes data, except on a currency pick`; the busy
    guard's in-flight path is tested for `x` only.
  - A taken statement code's test (`test_a_taken_code_on_edit_shows_the_engines_words_alone`)
    and tui.md cite pane 3·2 B of `expense-world-statement-code-field.html`, the pane with the
    app's line; the engine's words alone are pane 3·2 A.

## What it must do

1. **The LOG bar's staged list, a fill's colour, the summary's amounts and a single refusal's
   head** follow questions 1 A to 1 D.
2. **The undrawn words** stay or change as question 2 picks.
3. **The Edit form's CURRENCY line** carries the split hint as question 3 picks.
4. **The two opening-balance notes** name their currency as question 4 picks.
5. **A currency picked by mistake on the New form** can be taken back as question 5 picks.
6. **The LOG bar's hint** on a line refused for more than one reason follows question 6.
7. **`x`'s two sentences**, **the note after a half-saved save** and **the opening balance's
   line on `m`** follow questions 7 to 9.
8. **`ctrl+s` keeps a code typed on the New form's CURRENCIES line,** as the HASHTAGS line does.
9. **`c` guards against a second add in flight,** as `a` and `t` do.
10. **The missing tests** are written: the `color` refusal, the `?` card's rule, the busy guard
    for `c`, and the statement-code test citing pane 3·2 A, with tui.md.

## How the owner knows it is done

1. The LOG bar, the Edit form and the bulk moves read as questions 1 to 9 pick.
2. A code typed on the New form's CURRENCIES line and not yet added is kept on `ctrl+s`.
3. Pressing `c` twice quickly adds the currency once.
4. The unit suite and the drift check pass.

## What the owner settled

All answered 2026-11-02 ([expense-world-currencies-leftovers.html](../mockups/expense-world-currencies-leftovers.html)
for question 1); questions 2 to 4 as recommended, the owner taking the recommendation where no
letter was given:

- **Question 1:**
  - **1 A, A:** the LOG bar's staged list has a `Cur` column of its own, as the ledger has, in
    place of "<account> · <code>".
  - **1 B, A:** a currency an account change took on the Edit form is drawn dim, as built.
  - **1 C, B:** the opening balances' summary on a two-currency account colours its amounts by
    sign.
  - **1 D, A:** a bulk move with one row refused heads it `Refused`, as built.
- **Question 2 A:** the words no drawing showed stay as built, each following a pattern already
  approved.
- **Question 3 A:** the Edit form's CURRENCY line shows `changes every part of the transaction` on
  a transaction of two parts or more, as ACCOUNT, the date and the title do.
- **Question 4 A:** the two opening-balance notes name their currency: `The PEN opening balance
  is not:` and `The PEN opening balance is still loading.`
- **Question 5 A:** a currency picked by mistake on the New form stays picked, as on the hashtags
  line; `esc` and starting over is the way out.
- **Question 6 A:** the LOG bar's hint on a line refused for more than one reason is the plain
  `not staged — fix the line and press ↵ again`.
- **Question 7 A:** `x` keeps its two sentences, `Currency removed: USD.` and `<account> holds no
  currency.`
- **Question 8 A:** the half-saved save keeps the engine's words alone until the engine ask "An
  account and its opening balances save in one write" lands.
- **Question 9 A:** on `m`, an opening balance's `OPENING_BALANCE_ACCOUNT_FIXED` shows the
  engine's words alone; the app's line stays for `b` and the Edit form's account.

## Questions for the owner

None.

---

## Tasks

2. **The opening balances' summary colours its amounts by sign (1 C)** on an account holding two
   currencies, as pane 3 B of the same mockup draws (Manage ▸ Accounts ▸ Edit).
3. **The Edit form's CURRENCY line shows `changes every part of the transaction`** on a
   transaction of two parts or more (question 3), as ACCOUNT, the date and the title do
   ([edit_form.py](../../expense/tui/screens/edit_form.py) `EVERY_PART_NOTE`).
4. **The two opening-balance notes name their currency (question 4):** `The PEN opening balance
   is not:` and `The PEN opening balance is still loading.`
   ([create_forms.py](../../expense/tui/screens/create_forms.py)).
5. **Two lines drop back to plain words (questions 6 and 9):** the LOG bar's hint on a line
   refused for more than one reason is `REFUSED_HINT`; on `m`, an opening balance's
   `OPENING_BALANCE_ACCOUNT_FIXED` shows the engine's words alone, the app's line staying for `b`
   and the Edit form's account ([errors.py](../../expense/errors.py)).
6. **`ctrl+s` keeps a code typed but not added on the New form's CURRENCIES line,** as the Edit
   form's HASHTAGS line keeps one.
7. **`c` guards against a second add in flight,** as `a` and `t` do, with the busy guard's
   in-flight test for `c`.
8. **The missing tests:** a `color` refusal landing on the New form's COLOR line; the `?` card's
   rule `⏎ never changes data, except on a currency pick`; and
   `test_a_taken_code_on_edit_shows_the_engines_words_alone` with tui.md citing pane 3·2 A of
   `expense-world-statement-code-field.html`.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- **The LOG bar's staged list cuts cells at 80 columns** with ordinary names (`BCP Signature
  PEN`), against tui.md §5 "80×24 — everything correct"; with a long title Rich shrinks the
  `cur` column to nothing at 80 wide, and at 60 wide even with short titles. It cut cells
  before the `Cur` column too. A minimum width for `cur`, or title and tags as the columns that
  give way, as the ledger does, would fix it.
