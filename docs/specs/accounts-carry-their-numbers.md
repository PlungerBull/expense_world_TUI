# Accounts carry their numbers, the account form saves in one write, and a PDF is checked against its account

Catches up to contract sections 12 and 13 of the engine's hand-off of 2026-11-08
(`d9bd079557801740`, `8b9824e76593ec1e`, `be127df8432341a1`, `9dc0e6c4a5c83bcb`), and its one-write
account form (`edbafcc162850075`, `14fb4741b9db37b8`).

**Status: approved on 2026-11-03; redrawn on 2026-11-08 from the engine's hand-off, which built
the name and declined the alias, as the owner accepted. Its new questions 9 to 12 were answered and the spec approved on 2026-11-08, on the mockup
[expense-world-account-numbers.html](../mockups/expense-world-account-numbers.html). Cash is [the cash account](the-cash-account.md)'s, which runs after it; the sheet import's names
join [the official import](before-the-official-import.md).** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Every BCP paper prints its card or account number. An account that knows its own number lets
the engine refuse a paper sent to the wrong account before anything is written, and lets every
client name the account the way the bank does, `BCP-1234`, instead of a name typed by hand.

A card number changes when a card is replaced (a lost card, say) while the balance carries
over: it stays the same account, so the account has to know which number it had until which
day. A card that is closed ends its account, and a new card is a new account.

The account form saves the account, then each opening balance, one write after another, so a
refusal half-way leaves part of it saved. The engine now saves them in one write, whole or not
at all.

## What it must do

1. **A bank account holds its bank and the last 4 digits of its card or account number,** set in
   the app on each account. A person holds neither.
2. **A bank account shows as bank + last 4 digits** (`BCP-1234`), or as its bank alone until it
   has a number, everywhere an account's name shows. The engine builds the name; no client types
   it. A person shows the name typed.
3. **An account keeps its card numbers over time:** which number it had until which day, and
   which one after. A replacement card is added to the same account in the app.
4. **A PDF sent to an account whose number for that month is not the paper's is refused,**
   in the engine's words, nothing written.
5. **The account form saves in one write,** the account and every opening balance, whole or not
   at all, on New and Edit.
6. Which of the owner's card numbers belong to which account is set in the app, card by card.

## How the owner knows it is done

1. The owner picks `BCP` and types the Visa's last 4 digits, and it shows as `BCP-1234` on every
   screen; a person keeps its typed name.
2. A replacement card added to the Visa keeps its statements and balance on the same account; the
   old number shows with its end day; a start day inside a completed month shows the engine's
   refusal naming the statement.
3. Turning a bank account into a person asks for the person's name; turning a person into a bank
   account asks for the bank and an optional last 4.
4. The account form creates an account with its opening balances in one save, and edits every
   line and every currency's opening balance in one save; a refused save leaves nothing
   half-saved and shows the refusal on the right line.
5. A month's PDF sent to the wrong account is refused in the engine's words, naming both numbers,
   nothing written; the right account's paper closes the month as before, the replaced card's
   months included.
6. The live contract suite proves the banks read, the fields, the name built, the numbers over
   time, the one-write form and every refusal.

## What the engine declined, or did differently

- **No alias:** a bank account's name is always built, `BCP-5678` with a dash, or `BCP` with no
  number; accounts made before the change read `BCP` until each is given its number.
- **Cash is neither a person nor a bank account** in the engine yet; it is asked for separately.
- **The upload's number check reads the card above each group of purchases too,** and accepts a
  header printing a card that starts after the statement's last day (a card replaced at the cut).
- **The one-write answer names each opening balance by its id,** read from that transaction.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | When a card is replaced, does the account's name follow the new card's last 4 digits, or keep the first card's? | The new card's: the name matches the card in the wallet and this month's paper; the old number stays in the account's history (2026-11-03). |
| 2 | People and cash have no bank and no number. What is their name? | A person keeps a typed name; cash is one account per user named `Efectivo`, which the engine makes (2026-11-08). |
| 3 | A PDF whose number is not the account's number for that month? | Refused, in the engine's words, naming the paper's number and the account's; nothing written (2026-11-03). |
| 4 | The names accounts already carry, once an account has its bank and last 4 digits? | Dropped: the engine builds every bank account's name; there is no alias (2026-11-08). |
| 5 | The card numbers over time, as a table? | One row per number, kept by the engine: the first has no start day; each later one starts on its day and the one before ends the day before, so every day has one number (2026-11-03). |
| 6 | A PDF sent to an account with no number yet? | Refused until the account has its number, as an account with no statement code is today (2026-11-03). |
| 7 | A replacement whose start day falls inside a month already closed from a PDF? | Refused, naming that month, so a closed month's paper always matches its account's number (2026-11-03). |
| 8 | The mockup's first picks | 1A the bank picked from the engine's list · 3A a replacement is `new card` and `new card from` on the Edit form, older numbers read-only as `cards before` · 4A Manage ▸ Accounts keeps its columns, Name the name shown · 5A the LOG bar's `$` matches the name shown, either word · a refused PDF stays on the account question (2026-11-03). |
| 9 | The New form, mockup pane 1? | A: New takes each currency's opening balance, saved with the account in one write (2026-11-08). |
| 10 | Removing a number, mockup pane 2? | A: emptying `last 4` and saving asks `Remove card 5678 from BCP-5678?`, only `y` removes, and the number before it is current again; the engine refuses a removal a completed month depends on (2026-11-08). |
| 11 | `t`, mockup pane 3? | A: a short question asking the person's name, or the bank and an optional last 4 (2026-11-08). |
| 12 | The LOG bar's `$` and a card's digits, mockup pane 5? | A: `$` and exactly four digits that are one of the cards' last 4 find that card; any other digits after `$` stay money (2026-11-08). |

---

## Tasks

Approved. Each reads the live contract on the practice engine before
building.

4. **The Edit form's number lines.** `bank`, `last 4` (a first number, or its digits fixed) and
   `since` (the current number's first day) through `current_number`; emptying `last 4` removes
   the number after question 10's question; each refusal on its line.
5. **A replacement card.** `new card` and `new card from` through `new_number`, the older numbers
   read-only as `cards before` with their end days; `NUMBER_IN_COMPLETED_STATEMENT` on `new card
   from` in the engine's words.
6. **`t` asks for what the engine needs** (question 11): `make-person` with the name typed,
   `make-account` with the bank and an optional last 4; `NAME_EXISTS` on its line.
7. **The PDF upload's two new refusals:** `STATEMENT_NUMBER_MISMATCH` and `ACCOUNT_HAS_NO_NUMBER`
   show in the engine's words on the account question, which stays open.
8. **The live contract tests:** the banks read, `bank_code` and `numbers` on every account read,
   the built name, a replacement and its end day, a removal, the kind changes' bodies, the
   one-write create and edit (all or nothing, each refusal's key), a card paper refused on the
   savings account, an account with no number refused, and a replaced card's earlier month
   closing.

## Reply to the engine

Part 2 of the reply to the hand-off of 2026-11-08: sections 6, 12 and 13. It reports on the
hand-off's "Done when" checks named in "How the owner knows it is done" above and any contract
problem found, says the sheet import's `ambiguous` names are taken up with the official import,
and closes the asks "An account and its opening balances save in one write", "Save an account's
changes and its opening balances in one write, whole or not at all" and "An account carries its
bank and its card numbers over time, and a PDF is checked against them".

## Found along the way

Not built in this spec; sorted when it is done.

- Once accounts carry their numbers, the engine could name a PDF's account from the number the
  paper prints, so the upload would not ask "Which account is this statement?" at all.
- **For decisions.md at the sweep:** the parser keeps exact-name-wins, so `$BCP` is the line's
  text for the account named `BCP` and every written name parses back to its own account (the line
  is its own storage format); while `$bcp` is typed, the LOG bar's list offers the exact name and
  every name built on it (`BCP-…`), in the engine's order, since a bank account is
  named by its bank alone only until it has a number. Rejected: the parser listing them all (a
  picked `BCP` could never be staged); dropping exact-name-wins for every account name (`BCP
  Signature` beside `BCP Signature Platinum` turned ambiguous).
- **Pane 5 draws `"$5678" matches 1 account — ↵ writes the full name`,** but no single match shows
  a suggestion line on the LOG bar today (a unique name resolves as you type, as `$nic` does), so
  four digits matching one card resolve the same way. Pane 5 also draws `$56 is an amount: 56.00`
  under a `$` with digits, which no line shows today either. For the owner: both hint lines for
  every such token, or as it is.
- **For decisions.md at the sweep:** the account Edit form saves in one `PUT`, so its partial-save
  wording and the "a save of several writes counts once, the account Edit form's" example are no
  longer true (decisions.md ~854, ~1320, ~1333).
- The Edit form's tests land no `color` refusal, and a few refusal tests put a raw string in
  `_values` (tests/unit/test_tui_opening_balance.py:514, :712); they check only where the
  cursor lands.
- **A bank account's New form left before its save is refused** reads `Not created · Account
  (unnamed)`: the account has no name until the engine builds it, and the app builds none. For
  the owner: keep it, or name it by the bank typed (`Account BCP`). The `bank` line has no
  hint, as the mockup draws none.
- No screen test covers a plain `↵` on a typed `$bcp` taking the list's first entry
  (tests/unit/test_tui_log_bar.py's pick test covers picks 1 and 2 only).
