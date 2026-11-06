# Accounts carry their numbers, and a PDF is checked against its account

What a month's statement closing from the bank's PDF (done on 2026-11-03) left for a spec of its
own: today the owner names a PDF's account by hand, and the engine never compares the number
the paper prints with the account picked, so the preview is the only check against a wrong
account's paper.

**Status: every question answered, the mockup picked and the tasks approved on 2026-11-03; the
tasks wait for the engine ask "An account carries its bank and its card numbers over time, and a
PDF is checked against them"**, handed over to the engine coders; it waits for their hand-off. The engine's hand-off for it is planned into these tasks, with the reply this spec
then ends with. When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

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
| 5 | The card numbers over time, as a table? | One row per number, kept by the engine: the first has no start day; each later one starts on its day and the one before ends the day before, so every day has one number (2026-11-03). |
| 6 | A PDF sent to an account with no number yet? | Refused until the account has its number, as an account with no statement code is today (2026-11-03). |
| 7 | A replacement whose start day falls inside a month already closed from a PDF? | Refused, naming that month, so a closed month's paper always matches its account's number (2026-11-03). |
| 8 | The mockup, [expense-world-account-numbers.html](../mockups/expense-world-account-numbers.html) | 1A the bank picked from the engine's list · 2A the line is `alias` on every account · 3A a replacement is `new card` and `new card from` on the Edit form, older numbers read-only as `cards before` · 4A Manage ▸ Accounts keeps its columns, Name the name shown · 5A the LOG bar's `$` matches the name shown, either word (2026-11-03). |

---

## Tasks

Approved; waiting on the engine ask named in the status above. Each task reads the live contract
once the hand-off lands, and its "passes if…" is written then.

1. **Every screen shows the engine's name to show.** The account reads carry it, and each
   screen and the LOG bar's `$` (either word, 5A) use it in place of the typed name.
2. **The banks and a new account's lines.** The engine's banks read; New takes `bank` (picked,
   1A), `last 4` and `alias` where `name` is today (2A); a person's form has `alias` alone; the
   engine's refusals land on their lines.
3. **The Edit form's number lines.** `bank`, `last 4`, `since` and `alias`, the current number
   fixed in place; the refusals on their lines.
4. **A replacement card on the Edit form** (3A): `new card` and `new card from`, the older
   numbers read-only as `cards before`; a start day refused for a closed month shows in the
   engine's words on its line.
5. **The PDF upload's two new refusals**: a wrong account's paper and an account with no number,
   in the engine's words on the account question, which stays open (pane 6).
6. **The live contract tests**: the banks read, the fields, the name served, the numbers over
   time, and each refusal (done check 4).

## Reply to the engine

Drafted from the hand-off once it lands: the range it covers, its "Done when" checks reported
on, and the ask it closes by title.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.

- Once accounts carry their numbers, the engine could name a PDF's account from the number the
  paper prints, so the upload would not ask "Which account is this statement?" at all.
