# A card's statement on one screen

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full", the part about what the statement screens
show; then the engine's hand-off of 2026-10-28, "An account moves between holders, a holder is
made and unmade with its accounts, and a holder's bank lines list in one read", its parts on a
holder's bank lines in one read (`903200521b7c116a`) and what a client does with a flagged line
(`3e3bd0b766c709fc`); then the engine's hand-off of 2026-10-28, "A person is a holder; unpairing is
one write; the PDF upload moves a line one day off; the change log reaches back; your practice
engine serves only shipped code", its parts on the PDF upload matching a line one day off
(`95e8fea031ba6bd1`) and the flagged-line advice reworded (`e020782e3579d011`). The routes, the live suite, the sheet import's counts and cards themselves are the other
specs of this catch-up: part 1a, the app's reads and writes (done on 2026-10-28),
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md),
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md),
[catch-up-split-rows.md](catch-up-split-rows.md) and
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md).

**On hold since 2026-10-28:** it waits on the engine's hand-off for the ask "An account holds its currencies: the holder becomes the account, and each account becomes one of its currencies", which makes a card one account with a balance per currency; its question 12, the PDF preview's moved lines, did not depend on it and is answered.

**Status: draft; questions 1 to 11 answered by the owner on 2026-10-28, each as recommended (2 A
picked from its mockup; 11 settled as B by the engine), and these screens say "holder" (question 1
of the cards spec); question 12, from the hand-off "A person is a holder; …", answered by the owner
on 2026-10-28 as B, picked from its mockup. It runs
after the catch-up's other specs, since it names cards by their own names. Its questions about
screens are drawn in
[expense-world-card-statement-questions.html](../mockups/expense-world-card-statement-questions.html);
its tasks are drafted when the owner names it the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

**Built on the holder names.** The engine calls a card a holder since contract
`e7393dd869963db1` (its hand-off of 2026-10-28, "A person carries an opening balance, and a card
is now called a holder everywhere"): `/holders`, `holder_id` everywhere,
`GET /statements?holder_id=`, and every reason and message says holder, with nothing behaving
differently. "Card" stays for the bank's product: a credit card, its paper and its download. This
spec uses the holder names for everything the engine names. People become holders in a later
engine change, still to come (the engine coders' answer of 2026-10-27, "Which of the terminal
app's seven card and statement specs the engine's coming changes touch"); from then on only a
bank holder takes a statement.

---

## Why

The engine now keeps a card's statement as one thing: one name, one set of days, one status for
the whole card, and a starting and ending balance for each of its accounts, one per currency
(contract: "Statements", "A statement covers its whole holder"). A Visa card's soles and dollars
can no longer be half closed. The first spec of this catch-up moves the statement screens onto
the new routes but keeps showing one account at a time, as today. This spec makes the screens
show the card's statement the way the engine now holds it, and the way the bank's paper prints
it.

The engine also changed what the screens can do:

- **A currency with no movement closes by hand** on a card with no statement code: an account
  with no transaction completes when its starting and ending balances are equal, beside the
  other account (contract: POST /v1/statements/{statement_id}/complete, "Every account adds up").
- **The lines a close flags can be read at any time,** before and after the close, page by page,
  with their count, instead of only from the close's answer (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line").
- **A statement's lines come in one order,** the paper's numbering across both currencies, then
  the lines with no place, oldest first (contract: "Statements", "A statement's order").
- **A transaction moved to the card's other account can stay in its open statement,** where
  today every move takes it out.
- **A card's lines in no statement come in one read,** both currencies together, with their
  count (contract: GET /v1/bank-lines).
- **The engine says what to do with a flagged line on a card with a statement code:** keep the
  bank's, by deleting the flagged line; or keep your own, by reverting the statement, deleting
  the line the PDF upload made from the paper's row, moving your line to that row's day and
  uploading the PDF again (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line").

## What it must do

1. **Every statement screen shows one statement per card**: the list of statements, the form
   that opens one and the statement's own screen, each with a balance per account, as questions
   2, 3 and 5 decide. The screen is named as question 1 decides.
2. **A statement's lines are listed in the paper's order** (contract: GET /v1/bank-lines,
   "Ordering"): on a card with a statement code, numbered as the paper numbers them, both
   currencies in one numbering; the opening balance listed apart, since it holds no place on the
   paper. Screen 4 of
   [expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html)
   is drawn per currency, so it is drawn again for one numbering (question 3).
3. **Editing a line from a statement opens the ledger's Edit form.**
4. **An open statement on a card with a statement code waits for its PDF**: no ticking and no
   `c` (the owner's 5 A, now about cards). Completing it needs every line in the paper's order,
   which only the PDF sets (contract: "Statements", "Completing needs the order").
5. **On a card with no statement code, a statement is closed by hand**: lines ticked in and out,
   an ending balance entered for each account, and `c` completing it, a currency with no movement
   included, as question 4 decides.
6. **The lines a close flags show as question 6 decides,** read from the engine's list of them,
   and the screen says what to do with one on a card with a statement code as question 11
   decides.
7. **The PDF upload's and the bank download's list of accounts name a card by its own name,** as
   question 7 decides.
8. **A transaction moved to its card's other account** stays in its open statement or leaves
   it, as question 8 decides.
9. **A completed statement's footer shows only the keys that work on it,** as question 9
   decides, and **the list of lines in no statement** lists as question 10 decides.
10. **The statement's head shows a bracketed name whole,** pinned by a test, as the other heads
    in [test_tui_bracketed_names.py](../../tests/unit/test_tui_bracketed_names.py) are.
11. **The mockups these screens replace are deleted, with their links**:
    `expense-world-card-statement.html`, `expense-world-statement-order.html`,
    `expense-world-statement-screen.html` and `expense-world-statement-flagged-lines.html` in
    [mockups/](../mockups/), once the new screens' mockups are picked. They are linked from
    tui.md, decisions.md, todo.md, `reconciliations.py` and the tests of the card statement, the
    statement list and the flagged lines.
12. **A statement refused because one of its accounts was deleted while it was written** is sent
    again with the card's remaining accounts, as the engine asks
    (contract: DELETE /v1/accounts/{account_id}).
13. **The PDF upload's preview and result read `redated`,** as question 12 decides (B: a
    `· day moved` mark on each moved row), and nothing
    reads `near_misses` (contract: POST /v1/statements/import).

## How the owner knows it is done

1. A Visa card's statement opens as one screen holding both currencies' balances, in the layout
   question 3 picks.
2. A statement closed from its PDF lists its lines numbered as the paper numbers them, both
   currencies in one numbering, its opening balance apart.
3. A statement on a card with no statement code, with lines in soles and none in dollars,
   completes by hand once the dollar account's starting and ending balances are equal; with them
   unequal, it is refused in the engine's words.
4. An open statement on a card with a statement code offers no ticking and no `c`.
5. The flagged lines show when question 6 says, and what to do with one reads as question 11
   says.
6. A transaction moved to its card's other account does what question 8 says.
7. The unit suite, the live suite and the drift check pass.

## What the owner settled

- **A card with a statement code waits for its PDF** (owner, 2026-10-27, question 5 of
  [expense-world-statement-pdf-screens.html](../mockups/expense-world-statement-pdf-screens.html),
  A): its open statement offers no ticking and no `c`.
- **Editing goes to the ledger's Edit form** (owner, 2026-10-25): the statement screens stick to
  statement work.

## Questions for the owner

Questions 2 to 7, 9 and 10 are about screens: each is drawn as a mockup, every option as its own
pane, when this spec is named the current one. Questions 1, 8 and 11 are about words. Which
word these screens use for a card, "card" or "holder", is question 1 of
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md), and they follow it.

1. **The screen's name.** Home and its screens say "Reconciliations"; the engine, the bank's
   paper and the PDF upload say "statement".
   - **A.** Keep "Reconciliations".
   - **B.** "Statements", everywhere the app says "reconciliation".

   **Recommended:** B: one word for one thing, the same as the engine's and the paper's.
2. **What the list of statements opens on.** Today it opens on one row per account.
   - **A.** One row per card, with its name and its currencies, then that card's statements.
   - **B.** One row per account, as today; a card's two accounts open the same statements.

   **Recommended:** A: a statement belongs to a card, so the card is what you pick.

   **Answered 2026-10-28:** A.
3. **A two-currency card's statement screen** (screen 4 of the PDF mockup, drawn again).
   - **A.** One list in the paper's order, both currencies mixed and numbered 1, 2, 3 … with no
     gaps, a currency column, and each currency's starting, ending and difference once at the
     top.
   - **B.** One section per currency, each with its balances, the numbers keeping the gaps the
     other currency leaves.
   - **C.** One currency at a time, switched with a key, as today's halves are.

   **Recommended:** A: it reads as the bank's paper does, in the engine's one numbering.
4. **Closing a currency with no movement by hand,** on a card with no statement code. The engine
   completes it when its starting and ending balances are equal.
   - **A.** You type its ending balance as for any account; the box starts empty.
   - **B.** The box starts holding the starting balance, for you to confirm or change.

   **Recommended:** A: the app suggests no balance; the engine judges what you type.
5. **The form that opens a statement.** It asks for a starting balance, and optionally an ending
   one, for every account of the card.
   - **A.** As today's forms: a one-account card's form unchanged, a two-account card's as
     today's card form, a starting and an ending balance under each currency.
   - **B.** One line per balance, its currency named on it.

   **Recommended:** A: it is the form you know, now for every card.
6. **When the flagged lines show.** The engine can now list them at any time, with their count.
   - **A.** `⚑` and `f` show whenever a statement has flagged lines, open or completed, counted
     when the screen opens.
   - **B.** As today: only right after a close.

   **Recommended:** A: a line left for later stays visible until it is dealt with. Either way the
   lines are listed in the statement's order, both currencies together.
7. **How a card is named in the PDF upload's and the bank download's list of accounts.** Today
   a card's line is a name the app makes from its two accounts' names.
   - **A.** The card's own name and its currencies (`Visa Signature   PEN + USD`); a
     one-account card shows its card's name.
   - **B.** As A, but a one-account card shows its account's name.
   - **C.** One line per account.

   **Recommended:** A: one name, the one you give the card. And which cards the PDF upload
   lists:
   - **A.** Every card, the same list as the download; a card with no statement code is refused
     in the engine's words.
   - **B.** Only cards with a statement code.

   **Recommended:** A: it is the list you approved on 2026-10-27 (question 7 of the PDF spec).
8. **A transaction moved to its card's other account** (soles to dollars on one Visa) while it
   is in an open statement. Today every move takes it out of its statement.
   - **A.** It stays in the open statement: it is still on the same paper.
   - **B.** It leaves the statement, as today.

   **Recommended:** A. A transaction in a completed statement cannot be moved either way.
9. **A completed statement's footer.** On a completed statement, `c Complete` only says
   "Already completed.", and `d Delete` asks, then shows the engine's refusal (a completed
   statement is reverted before it is deleted).
   - **A.** Show neither.
   - **B.** Drop `c` only; `d` stays, and the engine's refusal says to revert first.
   - **C.** Keep the footer as it is.

   **Recommended:** B: `c` does nothing there, while `d` leads you to the engine's own words on
   what to do.
10. **The list of lines in no statement** (today `u`, newest first, one account at a time).
    - **Whose lines:** **A.** One account's, as today. **B.** The whole card's, both currencies
      together, in one read with its count (contract: GET /v1/bank-lines).

      **Recommended:** B: a statement is the card's, so its leftovers are too.
    - **In what order:** **A.** Newest first: the lines bought last on top. **B.** Oldest
      first, as a bank statement and the flagged lines read: the oldest leftovers, most likely
      forgotten, on top.

      **Recommended:** B.
11. **What the flagged lines screen offers on a card with a statement code.** The engine states
    both ways to settle a flagged line there (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line"):
    keep the bank's, by deleting the flagged line, the statement staying completed; or keep your
    own, its category, hashtags and text, by reverting the statement, deleting the line the
    upload made from the paper's row, moving your line to that row's day (and its total), and
    uploading the same PDF again, which completes the statement. Ticking the line in by hand does
    not work on such a card.
    - **A.** Two keys on a flagged line: `b` keeps the bank's (asks, then deletes the line), and
      `m` keeps yours (asks, then reverts, deletes the bank's line, moves yours to the paper's
      day, and asks for the PDF again).
    - **B.** The engine's two ways shown as words under the line; you do each step yourself on
      the other screens.
    - **C.** As today: "revert, tick it, complete again", which cannot work on such a card.

    **Recommended:** A, once the engine names each flagged line's twin where the flagged lines
    are read (the ask "Name a flagged line's twin wherever the flagged lines are read"): today
    only the upload's answer names it, so A would leave the app matching lines itself. B until it
    lands. With A, the app does each step the engine names, in its order, and you only choose
    which line to keep. Moving your line to the paper's day sends that day at 00:00 in the
    time zone the engine knows you by (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line"); the app today
    sends days in the computer's own zone, which is the same while both say Lima.

    **Settled by the engine, 2026-10-28:** the engine declined to name a flagged line's twin.
    Instead the PDF upload matches a line one day off the paper's row and moves it to the row's
    day, so the close no longer flags it; a flagged line sits a day off its twin only where the
    upload could not take it, and you tell them apart by the row's day, amount and description
    (contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line").
    The recommendation's "B until it lands" is therefore the answer: **B**, the engine's two ways
    as words under the line.
12. **The PDF upload's preview when the engine moves a line one day** (mockup
    `expense-world-statement-pdf-redated.html`). Today a row the paper printed shows a warning
    under it when your line sits one day off ("… in the ledger is one day off: not paired"), from
    `near_misses`, which the engine removed. Now the engine matches that line and moves it to the
    paper's day; the row reads matched, with `redated` (contract: POST /v1/statements/import).
    - **A.** A dim line under the matched row names the day the line moves from.
    - **B.** A short mark at the end of the matched row, with no day.
    - **C.** Nothing on the rows; the preview's count line says how many lines move.

    **Recommended:** A: you see which of your lines the bank's paper moves, and from which day,
    before anything is written.

    **Answered by the owner, 2026-10-28: B.** A matched row the engine moves reads
    `✓ In the ledger · day moved`, with no old day, the way a fee row carries its note; the
    result after ⏎ reads as it does today.

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c`, then `2cec1b59048f50dc` and
  `e7393dd869963db1` (the rename), reaching `e7393dd869963db1`, shared with the other specs of
  this catch-up; `d34fc8d06ff652c4` and `4ac20e42cf8566ee` are
  answered by the catch-up on a person's opening balance, done on 2026-10-28.
  Then `903200521b7c116a` and `3e3bd0b766c709fc` of the hand-off "An account moves between
  holders, a holder is made and unmade with its accounts, and a holder's bank lines list in one
  read". Then `95e8fea031ba6bd1` and `e020782e3579d011` of the hand-off "A person is a holder;
  …": the one-day-off match and the flagged-line advice.
- **The engine's "Done when" checks to report on:** "Every statement screen uses /statements,
  one object per card, with balances per account." From the hand-off "An account moves between
  holders…": a holder's lines in no statement show in one list, both currencies together, with
  their count; the flagged-line screen offers both paths on a holder with a statement code, as
  words (question 11 B). From the hand-off "A person is a holder; …": no code reads
  `near_misses`, and the PDF upload shows which lines moved to the bank's day.
- **The asks it closes:** "List a card's bank lines in no statement in one read" and "Say what a
  client does with a flagged line on a card with a statement code"; "Name a flagged line's twin
  wherever the flagged lines are read" is answered differently by the engine (question 11).

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
