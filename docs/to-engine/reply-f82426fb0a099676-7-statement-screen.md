# Caught up with contract f82426fb0a099676: an account's statement on one screen, and the catch-up closed (part 7 of 7)

2026-11-03

## Covers

`e020782e3579d011` → `f82426fb0a099676`, your hand-off of 2026-10-29, "An account holds its
currencies: every route names an account and a currency code; holders are gone": its sections 9
and 10, on screen. This is the last of the seven parts, so it closes the catch-up.

The terminal app now shows a statement as the account's, every currency together:
- The Statements list shows an account's statements with a difference column per currency it
  holds and, on an account with a statement code, whether each is in order.
- A statement's screen is one list in the paper's order, both currencies mixed, with each
  currency's starting balance, ending balance and difference once at the top. An opening balance
  sits apart.
- A new statement takes a starting and an ending balance per currency, in one
  `POST /statements`.
- Completing asks for every blank balance first, saves them in one `PUT /statements/{id}`, then
  sends `complete`. A refusal that names a currency's balances opens a box for each.
- The close's notes show per currency, those of a currency the statement does not cover after
  the others, each led by its code.
- On an account with a statement code, an open statement waits for its PDF: no ticking and no
  completing by hand. The PDF upload closes it.
- The flagged lines show whenever a statement has any, open or completed. On an account with a
  statement code, your two ways to settle one read as words.
- The account's lines in no statement show in one read, every currency, oldest first, with
  their count.

It also answers the checks still open from earlier ranges, since the holder model they checked
is gone:
- `46e2fdf6e11d7548` → `e7393dd869963db1`: the parts on the live suite, cards and the card's
  statement screen.
- `3e472b3256dcdc69` → `256f3190cf24fc36`: "An account moves between holders, a holder is made
  and unmade with its accounts, and a holder's bank lines list in one read".
- `4dd95f836dba7be2` → `e020782e3579d011`: the parts of "A person is a holder; unpairing is one
  write; the PDF upload moves a line one day off; the change log reaches back; your practice
  engine serves only shipped code" not answered by the reply for `e020782e3579d011`.

## Done when, checked

All checked against the practice engine on 2026-11-03:
- the unit suite: 3697 passed;
- the live contract suite: 331 passed, including the check that every contract citation in this
  repo resolves (the part 6 reply's one failure is gone);
- each check tried in the app at 80 columns on made-up data, nothing left on either practice
  user;
- the contract version, unmoved.

- **"A statement is the account's, with a starting and ending balance per currency it covers,
  and the PDF upload closes it":** worked.
  - Statements were made per account with balances per currency. One account's month covered
    soles and dollars.
  - The PDF upload closed a two-currency month and a soles-only month on the same account.
  - A month with dollars owed and no dollar movement was refused for its missing dollar
    balances, in your words. Given `-300.00` → `-300.00`, it completed.
  - A dollar line ticked into a soles-only draft gave it blank dollar balances. Completing asked
    for both, then completed.
  - A line moved to its account's other currency stayed in its open statement.
  - A PDF whose paper lacks one of the account's currencies was refused in your words, nothing
    written.
- **"The TUI has read up to `f82426fb0a099676` and says so":** worked. The version this client
  records is `f82426fb0a099676`, the one the practice engine serves.
- **"No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`, `?holder_id=`
  or a per-currency id":** worked. The app's code names none of them. The unit tests assert none
  is sent, and the live suite shows the engine refuses each.

## Contract problems found

None in this part.

## Asks this closes

- "An account holds its currencies: the holder becomes the account, and each account becomes
  one of its currencies", with this last part of the catch-up.
- Answered by the account holding its currencies, with no holder left to move or make:
  - "Yes to moving an account to another card, with the limits you proposed; no to the sheet
    import refusing a name used in two currencies";
  - "Delete a card with its last account, so no client leaves an empty card behind";
  - "Create a bank account and its own card in one write";
  - "Move an account onto a new holder in one write".
- Built here:
  - "List a card's bank lines in no statement in one read": one read, every currency, oldest
    first;
  - "Say what a client does with a flagged line on a card with a statement code": your two ways,
    shown as words.
- "Name a flagged line's twin wherever the flagged lines are read": answered differently, by
  those two ways.
