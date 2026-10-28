# A card's statement on one screen

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the engine's hand-off of
2026-10-27, "A card is its own object, its statement is one object for the whole card, and a
closed statement's review list is readable in full", the part about what the statement screens
show. The routes, the live suite, the sheet import's counts and cards themselves are the other
specs of this catch-up: [catch-up-cards-statements-1a-reads-and-writes.md](catch-up-cards-statements-1a-reads-and-writes.md),
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md),
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md),
[catch-up-split-rows.md](catch-up-split-rows.md) and
[catch-up-cards-statements-3-cards.md](catch-up-cards-statements-3-cards.md).

**Status: draft, for the owner to rewrite or approve; its questions wait on the owner. It runs
after the other four specs of this catch-up, since it names cards by their own names. Each
question about a screen is drawn as a mockup, and its tasks are drafted, when the owner names it
the current spec.** When done, the why moves to [decisions.md](../decisions.md) and this file is
deleted.

---

## Why

The engine now keeps a card's statement as one thing: one name, one set of days, one status for
the whole card, and a starting and ending balance for each of its accounts, one per currency
(contract: "Statements", "A statement covers its whole card"). A Visa card's soles and dollars
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
pane, when this spec is named the current one. Questions 1, 8 and 11 are about words.

1. **The screen's name.** Home and its screens say "Reconciliations"; the engine, the bank's
   paper and the PDF upload say "statement".
   - **A.** Keep "Reconciliations".
   - **B.** "Statements", everywhere the app says "reconciliation".

   **Recommended:** B: one word for one thing, the same as the engine's and the paper's.
2. **What the list of statements opens on.** Today it opens on one row per account.
   - **A.** One row per card, with its name and its currencies, then that card's statements.
   - **B.** One row per account, as today; a card's two accounts open the same statements.

   **Recommended:** A: a statement belongs to a card, so the card is what you pick.
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
      together, which needs the engine ask
      [bank-lines-card-filter.md](../to-engine/bank-lines-card-filter.md) to read in one list.

      **Recommended:** B, with the ask: a statement is the card's, so its leftovers are too.
    - **In what order:** **A.** Newest first: the lines bought last on top. **B.** Oldest
      first, as a bank statement and the flagged lines read: the oldest leftovers, most likely
      forgotten, on top.

      **Recommended:** B.
11. **What the flagged lines screen says to do with a line on a card with a statement code.** It
    says "revert, tick it, complete again", as the engine's advice does. On such a card that
    cannot work: a line added to a statement by hand holds no place on the paper, so the engine
    refuses to complete until the PDF is uploaded again (contract: POST /v1/statements/{statement_id}/complete, "On a card with a statement code, the statement must be fully ordered").
    What does work is fixing the line (usually its day), reverting, and uploading the PDF again.
    - **A.** The app says that on such a card, in its own words.
    - **B.** Ask the engine to state that path in its advice
      ([flagged-line-on-a-coded-card.md](../to-engine/flagged-line-on-a-coded-card.md)), and
      show its words.
    - **C.** Leave it as it is.

    **Recommended:** B, with A until the engine's words land: every app would otherwise work the
    path out for itself.

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c`, shared with the other specs of this
  catch-up.
- **The engine's "Done when" checks to report on:** "Every statement screen uses /statements,
  one object per card, with balances per account."
- **The asks it closes:** none. It raises "List a card's bank lines in no statement in one read"
  and "Say what a client does with a flagged line on a card with a statement code", if the owner
  picks them.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
