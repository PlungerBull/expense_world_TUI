# Cards in the app

Catches up to contract `e06456a20aca6e4c`, from `46e2fdf6e11d7548`: the cards part of the engine's
hand-off of 2026-10-27, "A card is its own object, its statement is one object for the whole
card, and a closed statement's review list is readable in full" (`29228c5191b6669b` and
`e06456a20aca6e4c`, cards and archiving a card). The other parts:
[catch-up-cards-statements-1a-reads-and-writes.md](catch-up-cards-statements-1a-reads-and-writes.md),
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md),
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md),
[catch-up-split-rows.md](catch-up-split-rows.md) and
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

**Status: draft, for the owner to rewrite or approve; questions 1 to 9 wait on the owner. Its
tasks are drafted when the owner names it the current spec.** It runs after
[catch-up-cards-statements-1b-statement-screens.md](catch-up-cards-statements-1b-statement-screens.md), and
[before-the-official-import.md](before-the-official-import.md) runs after it. When done, the why
moves to [decisions.md](../decisions.md) and this file is deleted.

**Reshaped by the engine's next changes** (the engine coders' answer of 2026-10-27, "Which of
the terminal app's seven card and statement specs the engine's coming changes touch"): card
becomes holder; an account moves between holders, which is how pairing and unpairing work; and
people become holders too, so creating, converting and archiving a person happen on its holder,
and the people route goes. Two holders cannot share a name. This spec is rewritten around
holders when those hand-offs land; its questions wait until then.

---

## Why

In the engine, a card is now a thing of its own: one bank product holding its accounts, one per
currency. A savings account is a card of one account; the Visa, billed in soles and in dollars,
is a card of two. Every bank account is on exactly one card, and a person is on none. The
statement code belongs to the card, not to the account, and a bank account is archived with its
card, every currency at once (contract: "Cards").

An account never moves between cards today: it gets its card when it is created and keeps it
(contract: "Cards", "An account never moves between cards"). The engine coders propose an action
that moves an account to another card while it has never been in a statement; this client said
yes in its answer "Yes to moving an account to another card, with the limits you proposed; no to the sheet import refusing a name used in two currencies",
in [to-engine/](../to-engine/). Until it lands, a card's accounts are put together when they are
created, or never.

Until this spec lands, these break against the engine (the practice engine, and the live one,
both serve `e06456a20aca6e4c` on 2026-10-27):

- **A new bank account** (`n` on Manage ▸ Accounts) is refused: the engine needs the card it
  goes on (contract: POST /v1/accounts).
- **The statement code line** of the New and Edit account forms is refused: an account carries
  no code any more.
- **Manage ▸ Accounts' Code column** shows `—` on every row: the code is the card's.
- **`a` on a bank account** is refused with `ARCHIVE_THE_CARD` and writes nothing; a person's
  `a` works as before (contract: "Cards", "A card is archived whole").
- **`t` on a person** (Make bank) is refused: the engine needs the card the account goes on
  (contract: POST /v1/accounts/{account_id}/make-account). `t` on a bank account works when the
  account is alone on its card and has never been in a statement; its card is deleted with it
  (contract: POST /v1/accounts/{account_id}/make-person).
- **`d` on an account with no transactions** works, and leaves its card behind with no account
  (contract: DELETE /v1/cards/{card_id}).
- **`expense import sheet --create-names`** is refused on its first account: it creates accounts
  with no card ([commands.md](../commands.md) "Renaming an account" names the steps).

## What it must do

1. **Cards are shown and edited in the app,** where question 1 decides: a card's name, its
   statement code and the accounts on it (contract: "Cards").
2. **A new bank account goes on a card,** as question 2 decides: a card made for it first, or
   one picked that holds no account in its currency (contract: POST /v1/accounts). A person is
   created as before, on no card.
3. **The statement code is the card's,** set, changed and cleared where question 3 decides
   (contract: "Cards", "Statement code"); the account's New and Edit forms lose their code line.
4. **`a` on a bank account archives its card, every account on it,** and unarchives it the same
   way, as question 4 decides (contract: POST /v1/cards/{card_id}/archive). A person's `a` stays
   as it is.
5. **`t` on a person makes it a bank account on a card,** as question 5 decides
   (contract: POST /v1/accounts/{account_id}/make-account). `t` on a bank account and its
   refusals read as question 6 decides.
6. **Pairing and unpairing an account in the app,** once the engine's move to another card
   lands: putting an account on another card (the Visa's dollars onto the Visa's card), or
   taking it off onto a card of its own. Where it lives is question 1, how it looks question 2.
   The engine's refusals (an account that has been in a statement, a card already holding that
   currency, an archived card, a card with a statement) show in its words. **Waits on the
   engine change** this client answered with "Yes to moving an account to another card, with the limits you proposed; no to the sheet import refusing a name used in two currencies".
7. **A card left with no account after a delete** is handled as question 7 decides.
8. **`expense import sheet --create-names` gives each account it creates a card of its own,**
   named as question 8 decides; pairing, such as the Visa's two accounts, is done afterwards in
   the app (point 6), as [before-the-official-import.md](before-the-official-import.md) plans it.
9. **A card's refusals read in the engine's words:** `NAME_EXISTS` and `STATEMENT_CODE_EXISTS`
   on a card, `CARD_CURRENCY_TAKEN`, `CARD_HAS_STATEMENT`, `CARD_HAS_ACCOUNTS` and an archived
   card refused as `INVALID_REFERENCE`, with the app's own line only where question 9 adds one.
10. **Each new write lands with unit tests** for its happy path and each refusal it handles; the
    live tests of the card routes are
    [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md)'s.

## How the owner knows it is done

1. You create a card in two currencies and its soles and dollar accounts on it from the app, and
   the app shows them as one card.
2. A new savings account goes on a card of its own.
3. You set, change and clear a card's statement code; the account forms ask for none.
4. `a` on either of the Visa's accounts archives both and says so as question 4 decides; `a`
   again unarchives both. A person's `a` works as before.
5. `t` on a person makes it a bank account on the card question 5 decides; `t` back works on an
   account alone on its card and never in a statement.
6. Once the engine's move lands: an account created on a card of its own is paired onto
   another card and unpaired again; one that has been in a statement is refused in the engine's
   words.
7. `--create-names` on a sheet gives every account it creates a card of its own, named as
   question 8 decides, and the dry run after it lists no name missing.
8. A refused card write says why in the engine's words and writes nothing.
9. The unit suite and the drift check pass.

## Questions for the owner

Questions 1, 2, 4 and 5 need a mockup before you pick; the orchestrator draws them when you name
this the current spec.

1. **Where cards live** (mockup).
   - **A.** A new Manage ▸ Cards list (name, statement code, its accounts' currencies, archived),
     where a card is created, renamed, given its code, archived and deleted, and where accounts
     are paired and unpaired; Manage ▸ Accounts' Code column becomes the card's name.
   - **B.** No Cards screen: the New account form makes or picks the card, and Manage ▸ Accounts'
     keys act on the account's card.
   - **C.** B now, A later.

   **Recommended:** A. A card is the engine's own thing that every app will show, and only a
   screen of its own renames a card or changes its code in one place.

   Also: the engine's word is "card", and a savings account is a card of one account. Does the
   app say "card" everywhere? **Recommended:** yes, the engine's word, so every app shares it.
2. **How a new bank account gets its card, and how pairing looks** (mockup).
   - **A.** New always makes a card of its own, named after the account; putting it with another
     card's account is pairing, afterwards (point 6).
   - **B.** New has a CARD line: pick a card holding no account in this currency, or a new card.
     Pairing afterwards is for an account put on the wrong card.

   **Recommended:** B: the Visa's dollar account goes straight onto the Visa's card, and no
   step after it is needed. A collides on card names when one name is used in two currencies.
3. **Where the statement code is edited.**
   - **A.** On the card (its own Edit, under question 1 A).
   - **B.** On the account's Edit form, a line that says it changes the code of the whole card.

   **Recommended:** A: one code per card, edited in one place.
4. **`a` archives the whole card** (mockup).
   - **A.** The same key and note; every account of the card dims.
   - **B.** As A, and the note names every account archived with it ("Archived with its card:
     Visa PEN, Visa USD.").
   - **C.** `a` on a bank account moves to the Cards screen; Manage ▸ Accounts keeps `a` for
     people only.

   **Recommended:** B: the key stays where it is, and the note says the other currency went too.
5. **`t` on a person needs a card** (mockup).
   - **A.** `t` makes a card of its own, named after the person, at once.
   - **B.** `t` asks which card: one holding no account in its currency, or a new one.

   **Recommended:** B, as question 2 B; A collides on card names for a person in two currencies.
6. **`t` on a bank account: what its refusals say.** The engine now refuses an account that has
   been in any statement, even a deleted one, so the app's line "On Reconciliations, press d on
   each of its reconciliations; a completed one needs u first." gives advice that no longer
   works (contract: POST /v1/accounts/{account_id}/make-person). It also refuses an account
   sharing its card (`CARD_HAS_OTHER_ACCOUNTS`) and a card with a statement
   (`CARD_HAS_STATEMENT`).
   - **A.** The engine's words alone, for all three.
   - **B.** A line of the app's under each.

   **Recommended:** A: the engine's words already say what is wrong, and the app guesses no rule.
7. **Deleting a card's last account leaves an empty card.**
   - **A.** It stays, and you delete it where cards live (question 1 A).
   - **B.** The engine deletes the card with its last account, as it does when an account
     becomes a person: the ask "Delete a card with its last account, so no client leaves an
     empty card behind" in [to-engine/](../to-engine/).

   **Recommended:** B, with A until it lands.
8. **`--create-names`: a card's name when one name is used in two currencies.** Each account it
   creates gets a card of its own. Card names are unique, and a name used in two currencies
   (the four people in both currencies, the old Oro card) makes two accounts.
   - **A.** The name and the currency (`ALEJO PEN`, `ALEJO USD`) only where the name is used
     twice; every other card is named as its account.
   - **B.** Always the name and the currency.

   **Recommended:** A: most cards read as their account, and a person's card goes when `t` turns
   it into a person. Also: the line `Created 4 accounts, 3 categories, 2 hashtags.` says
   nothing of cards; should it count them? **Recommended:** no: a card per account is how
   accounts are made. The ask "Create a bank account and its own card in one write" in
   [to-engine/](../to-engine/) makes each of these one write instead of two.
9. **`STATEMENT_CODE_EXISTS`: the app's line.** It says "Another account in this currency has
   this code: pick another, or clear it there first.", which is no longer true: a code is held by
   one card, whatever the currency (contract: "Cards", "One card per code").
   - **A.** The engine's words alone.
   - **B.** A new line: "Another card has this code: pick another, or clear it there first."

   **Recommended:** A: the engine names the clash itself.

Mockups this spec redraws, once picked: `expense-world-statement-code-field.html`,
`expense-world-account-to-person.html`, `expense-world-person-reconciliations.html` and the
archive panes of `expense-world-archived-account.html` in [mockups/](../mockups/).

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e06456a20aca6e4c`, shared with the other parts of this
  catch-up; the cards (`29228c5191b6669b`) and archiving a card (`e06456a20aca6e4c`).
- **The engine's "Done when" checks to report on:** the TUI reads and writes cards, and creates
  accounts with `card_id`; archiving a bank account goes through its card; make-account creates
  the new card first, then sends `{"card_id": …}`.
- **The asks it closes:** none of its own; it reports on the engine's move to another card once
  that lands.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
