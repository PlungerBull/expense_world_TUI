# Accounts carry their numbers, and a PDF is checked against its account

What a month's statement closing from the bank's PDF (done on 2026-11-03) left for a spec of its
own: today the owner names a PDF's account by hand, and the engine never compares the number
the paper prints with the account picked, so the preview is the only check against a wrong
account's paper.

**Status: drafted on 2026-11-03 for the owner to rewrite or approve; three questions, and the
account form needs a mockup to draw.** It waits on no other spec. The engine holds the fields
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
4. **A PDF sent to an account whose number for that month is not the paper's is refused** (or
   as question 3 picks), in the engine's words, nothing written.
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

## Questions for the owner

### 1. A replaced card's name
When a card is replaced, does the account's name follow the new card's last 4 digits, or keep
the first card's?
- **A.** Follow the new card.
- **B.** Keep the first card's.

**Recommended:** A, because the name then matches the card in your wallet and the paper the
bank sends this month; the old number stays in the account's history.

### 2. Accounts with no bank number
People and cash have no bank and no number. What is their name?
- **A.** Their alias is their name, and it is required when there is no number.
- **B.** Every account must have a bank number.

**Recommended:** A, because cash and people can never have a bank number.

### 3. A PDF whose number is not the account's
- **A.** Refused, in the engine's words, naming the paper's number and the account's; nothing
  written.
- **B.** A warning in the preview; you can still confirm.

**Recommended:** A, because a wrong paper creates a month of wrong lines, and the right account
is one pick away.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
