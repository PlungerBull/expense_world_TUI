# Accounts carry their numbers, and a PDF is checked against its account

What a month's statement closing from the bank's PDF (done on 2026-11-03) left for a spec of its
own: today the owner names a PDF's account by hand, and the engine never compares the number
the paper prints with the account picked, so the preview is the only check against a wrong
account's paper.

**Status: the owner named it the current spec and answered its questions on 2026-11-03; the
account form's mockup, [expense-world-account-numbers.html](../mockups/expense-world-account-numbers.html),
waits for the owner's pick, one letter per pane.** It waits on no other spec. The engine holds the fields
and the rules, so its first step is an ask to the engine, written once the questions are
answered. When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## Why

Every BCP paper prints its card or account number. An account that knows its own number lets
the engine refuse a paper sent to the wrong account before anything is written, and lets every
client name the account the way the bank does, `BCP 1234`, instead of a name typed by hand.

A card number changes when a card is replaced (a lost card, say) while the balance carries
over: it stays the same account, so the account has to know which number it had until which
day. A card that is closed ends its account, and a new card is a new account.

## What it must do

1. **An account holds its bank and the last 4 digits of its card or account number,** and an
   optional alias, set in the app on each account.
2. **An account shows as bank + last 4 digits** (`BCP 1234`), or as its alias when it has one,
   everywhere an account's name shows. The engine serves the name to show, so every client
   shows the same.
3. **An account keeps its card numbers over time:** which number it had until which day, and
   which one after. A replacement card is added to the same account in the app.
4. **A PDF sent to an account whose number for that month is not the paper's is refused,**
   in the engine's words, nothing written.
5. Which of the owner's card numbers belong to which account is set in the app, card by card,
   once the fields exist.

## How the owner knows it is done

1. The owner sets the bank and last 4 digits on the Visa, and it shows as `BCP 1234` on every
   screen; given an alias, it shows the alias.
2. A replacement card added to the Visa keeps its statements and balance on the same account.
3. A month's PDF sent to the wrong account is refused in the engine's words, nothing written;
   the right account's paper closes the month as before, the replaced card's months included.
4. The live contract suite proves the fields, the name served, the numbers over time and the
   refusal.

## Decided

| # | Question | Answer (owner) |
|---|---|---|
| 1 | When a card is replaced, does the account's name follow the new card's last 4 digits, or keep the first card's? | The new card's: the name matches the card in the wallet and this month's paper; the old number stays in the account's history (2026-11-03). |
| 2 | People and cash have no bank and no number. What is their name? | Their alias, required when there is no number (2026-11-03). |
| 3 | A PDF whose number is not the account's number for that month? | Refused, in the engine's words, naming the paper's number and the account's; nothing written (2026-11-03). |
| 4 | The names accounts already carry, once an account has its bank and last 4 digits? | Dropped: an account with a number shows as bank + last 4; an account with no number keeps its name as its alias (2026-11-03). |

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- Once accounts carry their numbers, the engine could name a PDF's account from the number the
  paper prints, so the upload would not ask "Which account is this statement?" at all.
