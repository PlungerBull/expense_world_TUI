# What the main views on an account and its currencies turned up

What part 6 of the catch-up to contract `f82426fb0a099676`, the main views (done on 2026-10-31),
turned up while it ran.

**Status: drafted on 2026-10-31 for the owner to rewrite or approve; nine questions, the first
with a mockup.** It runs after
[catch-up-currencies-3-leftovers.md](catch-up-currencies-3-leftovers.md) and before [catch-up-currencies-7-statement-screen.md](catch-up-currencies-7-statement-screen.md).
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

## Questions for the owner

1. **Four drawings** ([expense-world-currencies-leftovers.html](../mockups/expense-world-currencies-leftovers.html)):
   - **1 A.** The LOG bar's staged list: a `Cur` column of its own, as the ledger has, or
     "<account> · <code>" as today.
   - **1 B.** A currency an account change took on the Edit form: dim, as built, or purple.
   - **1 C.** The opening balances' summary on a two-currency account: plain, as built, or
     coloured by sign.
   - **1 D.** A bulk move with one row refused: headed `Refused`, as built, or `1 of 3 refused`.

   **Recommended:** as the mockup marks each.

2. **The words no drawing showed.** Each is built with these words, following the pattern beside
   it:
   - a `%` matching none of the account's currencies: `"%xx" matches no currencies` (as
     `"$x" matches no accounts`);
   - an account holding three or more currencies with none picked: `Multi holds PEN, USD and
     EUR: pick one` (as the two-currency `holds PEN and USD`);
   - a picked currency written into the line in capitals, `%USD`, as `$` and `@` write the
     engine's own name; the drawing wrote `%usd`;
   - the Edit form's toast for a currency matching nothing: `No currency matches “…”.` (as
     `No account matches “…”.`);
   - a line on an archived account: its CURRENCY line `read-only` with the shared reason;
   - the ledger on one currency of an account: crumb `Ledger ▸ Visa Inventada · USD`, legend
     `filter: account Visa Inventada · USD · 20 of 57 loaded`, empty text `(no transactions
     under Visa Inventada · USD)`;
   - the ledger's `m` on the `?` card: `Move the selection to a currency`, and `m Currency`
     standing before `s` and `d` in the footer with no row selected;
   - a LOG bar line naming an account that matches nothing, `↵` pressed inside the token: the
     hint `not staged — fix the line and press ↵ again` and, under the bar, `! not staged —
     "$zzz" matches no accounts`, as with the caret outside the token.

   - **A.** Keep them all.
   - **B.** Change some: tell me which, and to what.

   **Recommended:** A: each follows words you already approved.

3. **The Edit form's CURRENCY line on a transaction of two parts or more.** ACCOUNT, the date and
   the title show `changes every part of the transaction`; the engine writes the currency onto
   every part too.
   - **A.** CURRENCY shows it too.
   - **B.** It stays without.

   **Recommended:** A: it does change every part.

4. **Two opening-balance notes that do not say which currency:** `The opening balance is not:`
   and `The opening balance is still loading.`, on an account that may hold two.
   - **A.** They name the currency: `The PEN opening balance is not:`, `The PEN opening balance
     is still loading.`
   - **B.** They stay as they are.

   **Recommended:** A: with two opening balances on the form, the note should say which.

5. **A currency picked by mistake on the New form.** Today, as on the hashtags line, it cannot be
   taken back; `esc` and starting over is the way out.
   - **A.** It stays so, as the hashtags line.
   - **B.** `⏎` on a picked currency takes it back, on both lines.

   **Recommended:** A: one rule for every list line, and a new account is quick to start over.

6. **The LOG bar's hint on a line refused for its currency and something else** (`taxi -5
   $visa @zzz`). Today it says `not staged — pick a currency and press ↵ again`; the line under
   the bar names both reasons.
   - **A.** The plain hint, `not staged — fix the line and press ↵ again`, whenever there is more
     than one reason.
   - **B.** As today.

   **Recommended:** A: the hint should not send you to fix one thing when two are wrong.

7. **`x`'s two sentences:** the receipt `Currency removed: USD.`, and `<account> holds no
   currency.` for `x` on an account holding none. Built with these words.
   - **A.** Keep them.
   - **B.** Other words: tell me which.

   **Recommended:** A: they mirror `c`'s `Currency added: USD.`

8. **The note after a half-saved save:** when the dollars' opening balance is refused after the
   soles' saved, the screen shows the engine's words alone, not which balance went through.
   - **A.** Leave it until the engine ask "An account and its opening balances save in one
     write" lands, which removes the half save.
   - **B.** Add a line now naming what saved.

   **Recommended:** A: the engine ask removes the case for every client.

9. **An opening balance refused on `m`.** `m` moving an opening balance to another currency is
   refused (`OPENING_BALANCE_ACCOUNT_FIXED`, "Must not move an opening balance to another account
   or currency."), and the app adds its line `To move an opening balance, set it on the other
   account's Edit form.`, written for a move to another account.
   - **A.** On `m`, the engine's words alone; the line stays for `b` and the Edit form's account.
   - **B.** One line for both: `To change an opening balance's account or currency, set it on
     that account's Edit form.`

   **Recommended:** A: the engine's words already say what is refused, and the line's advice is
   about another account.

---

## Tasks

Drafted when the owner approves this spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
