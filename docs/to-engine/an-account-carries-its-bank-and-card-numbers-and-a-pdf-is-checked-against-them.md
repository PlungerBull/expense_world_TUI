# An account carries its bank and its card numbers over time, and a PDF is checked against them

Raised 2026-11-03.

## Why

Every BCP statement prints its card or account number. Today an account knows nothing of it:
the bank's PDF (`POST /statements/import`) is closed into whatever account the client names, and
the contract's layout rules say the number "may print anywhere … or not at all". A paper sent to
the wrong account closes a month of wrong lines, and the client's preview is the only check
against it.

Accounts are also named by hand. The bank names a product by its bank and the last 4 digits of
its number (`BCP 5678`); each user types a name of their own, and each client shows that.

A card number changes when the card is replaced (lost, stolen, expired) while the account, its
balance and its statements carry over. So the account has to know which number it had on which
days, and a month's paper has to be checked against the number of that month.

## The ask

1. **An account's bank, from a list the engine serves.** A read (for example `GET /banks`)
   returns the banks the engine knows, in the order a picker shows them (`BCP` to start). A bank
   account may hold one of them; any other value is refused. A person holds no bank.
2. **An account's card or account numbers over time.** A bank account holds a list of numbers,
   each the last 4 digits (exactly four digits) and the day it starts:
   - the first number has no start day: it covers every day before the next one;
   - each later number starts on its day, and the one before it ends the day before, set by the
     engine, so every day belongs to exactly one number;
   - a write adds a replacement (its last 4 and its start day, after the current number's start);
   - a write fixes the current number's digits (a typo, no history kept) or its start day; older
     numbers are read-only;
   - a bank needs a number and a number needs a bank: one without the other is refused;
   - **a start day on or before the last day of a completed statement is refused**, naming that
     statement, so a closed month's paper always matches its account's number for that month;
   - the same bank and current last 4 on two of the user's live accounts is refused, as a taken
     name is today.
3. **An optional alias,** required when the account has no number (a person, cash). Aliases
   are unique among the user's live accounts as names are today.
4. **The name to show, served by the engine:** the alias when there is one, else the bank and the
   current number's last 4 (`BCP 5678`). Every response that names an account carries it, so
   every client shows the same; it is what a client matches a typed account name against.
5. **Today's names become aliases.** The first time an account gets a number, the alias it
   carried over from its old name is dropped, unless that same write sets an alias, so a card
   given its number shows as `BCP 5678`. Every route that takes an account's name today (the
   spreadsheet import, for one) takes the alias.
6. **The PDF is checked against the account's number.** `POST /statements/import` reads the
   number the paper prints (the contract's layout says where) and compares its last 4 digits with
   the account's number on the statement's last day:
   - a different number is `422`, a code of its own, naming the paper's last 4 and the account's
     for that day; nothing written, on a dry run too;
   - an account with no number is `422`, as `NO_STATEMENT_CODE` is today: set the number first;
   - a paper printing no number is refused as a layout it does not read;
   - the samples (`GET /statements/samples`) print a number, and the contract says which.
   If a replaced card's paper prints the number differently (the old one for the whole cycle, say),
   the contract states the rule the engine uses instead.
7. **The statement code stays as it is.** It labels the bank product (`SIG`); the number names the
   card.

## Done when

- The banks read, the bank, the numbers over time, the alias and the name to show are in the
  contract, with every refusal above.
- A replacement added to an account keeps its statements and balance; the name to show follows
  the new number, and the old number stays readable with its end day.
- A month's PDF sent to an account whose number on its last day is not the paper's is refused in
  the engine's words, nothing written; an account with no number is refused the same way; the
  right account's paper closes the month as before, a replaced card's earlier months included.
- An account carried over with its old name and then given a number shows as bank + last 4.

## What this client removes once it lands

The terminal app stops treating the name its user typed as an account's only name: every screen
shows the engine's name to show, and the account form's single typed name line gives way to the
bank, the last 4 digits and the alias. Its statement upload preview is no longer the only check
that a paper belongs to the account picked.
