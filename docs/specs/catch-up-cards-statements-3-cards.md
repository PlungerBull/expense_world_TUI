# Cards in the app

Catches up to contract `e7393dd869963db1`, from `46e2fdf6e11d7548`: the cards part of the engine's
hand-off of 2026-10-27, "A card is its own object, its statement is one object for the whole
card, and a closed statement's review list is readable in full" (`29228c5191b6669b` and
`e06456a20aca6e4c`, holders and archiving a holder), and the holder part of its hand-off of
2026-10-28, "A person carries an opening balance, and a card is now called a holder everywhere"
(`2cec1b59048f50dc` and `e7393dd869963db1`: holder in every route, field, reason and
section); then to `256f3190cf24fc36`: the engine's hand-off of 2026-10-28, "An account moves
between holders, a holder is made and unmade with its accounts, and a holder's bank lines list in
one read" (`3e472b3256dcdc69` to `256f3190cf24fc36`; this client recorded it as
`f00534abdde7fa82`, a draft that never shipped), its parts on the move, a holder deleted with its
last account, a holder created with its accounts and an account's delete refused while a
statement holds it; then to `e020782e3579d011`: the engine's hand-off of 2026-10-28, "A person is
a holder; unpairing is one write; the PDF upload moves a line one day off; the change log reaches
back; your practice engine serves only shipped code" (`4dd95f836dba7be2` to `e020782e3579d011`),
its parts on a holder's kind, the kind changed on the holder, archiving on the holder only, a
person's move, `POST /people` removed and unpairing in one write. The other parts:
part 1a, the app's reads and writes (done on 2026-10-28),
part 1b, the statement screens (done on 2026-10-28),
[catch-up-cards-statements-2a-live-suite-foundation.md](catch-up-cards-statements-2a-live-suite-foundation.md),
[catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md),
[catch-up-split-rows.md](catch-up-split-rows.md) and
[catch-up-cards-statements-4-statement-screen.md](catch-up-cards-statements-4-statement-screen.md).

**On hold since 2026-10-28:** the owner asked the engine to make the holder the account and each account one of its currencies (the ask "An account holds its currencies: the holder becomes the account, and each account becomes one of its currencies"). Holders, pairing, unpairing and person holders go, so this spec is rewritten from the engine's hand-off for that ask; its answered questions stand where they still apply, and questions 11 to 13 are not asked.

**Status: draft; questions 1 to 10 answered by the owner on 2026-10-28 (question 3 folded into the
card-field mockup's question b, question 5 no longer applying); questions 11 to 13, from the
hand-off "A person is a holder; …", wait on the owner. Its tasks are drafted when the owner names it the current spec.** It runs after
part 1b, the statement screens (done on 2026-10-28), and
[before-the-official-import.md](before-the-official-import.md) runs after it. When done, the why
moves to [decisions.md](../decisions.md) and this file is deleted.

**Reshaped by the engine's changes** (the engine coders' answer of 2026-10-27, "Which of the
terminal app's seven card and statement specs the engine's coming changes touch"):
- **Card is holder:** in the contract since `e7393dd869963db1` (the hand-off "A person carries an
  opening balance, and a card is now called a holder everywhere", shipped 2026-10-28). This spec
  names the engine's routes, fields, reasons and sections as the contract does.
- **An account moves between holders,** which is how pairing and unpairing work
  (contract: POST /v1/accounts/{account_id}/move).
- **A holder goes with its last account, and is created with its accounts:** deleting a holder's
  last live account deletes the holder too, and a `DELETE /holders/{id}` after it answers `404`
  (contract: DELETE /v1/accounts/{account_id}); `POST /v1/holders` takes its accounts, up to 10,
  in the same write, all or nothing, a refused item keyed `accounts.<i>.<field>`
  (contract: POST /v1/holders).
- **An account a live statement holds is not deleted:** `409 IN_LIVE_STATEMENT` on `account_id`,
  judged after `HAS_TRANSACTIONS`; the statement is deleted first, a completed one reverted
  before (contract: DELETE /v1/accounts/{account_id}).
- **People are holders too** (contract: "Holders", "Its kind"): a holder is a bank holder or a
  person holder (`is_person`), and every account is on one, a person included. A person is made
  with `POST /holders` and `is_person: true`, one account per currency (ALEJO in soles and in
  dollars is one write), or with `POST /accounts` on a person holder; `POST /people` answers
  `404`. `GET /holders` lists bank holders first, then person holders.
- **The kind changes on the holder, whole:** `POST /holders/{id}/make-person` and
  `/make-account` turn the holder and every account of it; the holder stays. The account routes
  answer `404`, and `HOLDER_HAS_OTHER_ACCOUNTS` is sent by no operation
  (contract: POST /v1/holders/{holder_id}/make-person).
- **Archiving is on the holder only,** a person's included: `POST /accounts/{id}/archive` and
  `/unarchive` answer `404`, and `ARCHIVE_THE_HOLDER` is sent by no operation
  (contract: POST /v1/holders/{holder_id}/archive).
- **A person moves between person holders,** as a bank account between bank holders; a move onto
  a holder of the other kind is `HOLDER_KIND_MISMATCH`, and `PERSON_NOT_MOVED` is sent by no
  operation (contract: POST /v1/accounts/{account_id}/move).
- **Unpairing is one write:** the move takes `holder`, a new holder made of the account's kind
  and the account moved onto it, all or nothing, a refusal of the holder keyed `holder.<field>`;
  exactly one of `holder_id` and `holder` is sent (contract: POST /v1/accounts/{account_id}/move).
- **A person takes no statement and no bank file** (`PERSON_TAKES_NO_STATEMENT`). The app already
  leaves people out of Reconciliations and of the import door's account lists, so nothing on
  screen changes for it.

Two holders cannot share a name, whatever their kind (contract: POST /v1/holders).

---

## Why

In the engine, a holder is a thing of its own: one bank product holding its accounts, one per
currency. A savings account is a holder of one account; the Visa credit card, billed in soles and
in dollars, is a holder of two. Every account is on exactly one holder: a bank account on a bank
holder, a person on a person holder (ALEJO in soles and in dollars is one person holder of two). The statement code belongs to the holder, not to the account, and a bank account is archived
with its holder, every currency at once (contract: "Holders").

An account that has never been in a statement moves between holders
(contract: "Holders", "An account in no statement moves between holders of its kind"):
`POST /v1/accounts/{account_id}/move` puts it on another holder, keeping its id, transactions and
balance, and a holder the move leaves holding no live account is deleted in the same write
(contract: POST /v1/accounts/{account_id}/move). Pairing two currencies is moving one account onto
the other's holder; unpairing is moving the account onto a new holder made in the same write.
People pair and unpair the same way, between person holders. The move answers this client's "Yes to moving an account to another card, with the
limits you proposed; no to the sheet import refusing a name used in two currencies".

Until this spec lands, these break against the engine (the live engine serves
`e7393dd869963db1` and the practice engine `88333696fca6a504` on 2026-10-28):

- **A new bank account** (`n` on Manage ▸ Accounts) is refused: the engine needs the holder it
  goes on (contract: POST /v1/accounts).
- **The statement code line** of the New and Edit account forms is refused: an account carries
  no code any more.
- **Manage ▸ Accounts' Code column** shows `—` on every row: the code is the holder's.
- **`a` on any account, a person's included,** answers `404`: archiving is on the holder only.
- **`t` on any account** answers `404`: the kind changes on the holder.
- **A new person** (`n` with type person) answers `404`: `POST /people` is gone.
- **`d` on an account a live statement holds** is refused `IN_LIVE_STATEMENT`, in the engine's
  words (contract: DELETE /v1/accounts/{account_id}).
- **`expense import sheet --create-names`** is refused on its first account: it creates accounts
  with no holder ([commands.md](../commands.md) "Renaming an account" names the steps).

## What it must do

1. **Holders are shown and edited in the app,** where question 1 decides: a holder's name, its
   statement code and the accounts on it (contract: "Holders").
2. **A new bank account goes on a holder,** as question 2 decides: a holder made for it first, or
   one picked that holds no account in its currency (contract: POST /v1/accounts). **A new person
   goes on a person holder,** as question 13 decides (contract: POST /v1/holders).
3. **The statement code is the holder's,** set, changed and cleared where question 3 decides
   (contract: "Holders", "Statement code"); the account's New and Edit forms lose their code line,
   and a person's Edit form keeps its `opening` and `as of` lines
   ([decisions.md](../decisions.md) "A person carries an opening balance"). The app's line for
   `HAS_STATEMENT_CODE`, which `make-person` no longer sends now that the code is the holder's, goes
   with the code line, in errors.py, tui.md and test_errors.py.
4. **`a` on any account archives its holder, every account on it,** a person's included, and
   unarchives it the same way, as question 4 decides
   (contract: POST /v1/holders/{holder_id}/archive).
5. **`t` turns the account's holder, every account on it, into the other kind,** as question 11
   decides (contract: POST /v1/holders/{holder_id}/make-person)
   (contract: POST /v1/holders/{holder_id}/make-account); its refusals (`KIND_UNCHANGED`,
   `ACCOUNT_ARCHIVED`, `HAS_RECONCILIATION`, all on `holder_id`) read as question 6 decides.
6. **Pairing and unpairing an account in the app,** with the engine's move to another holder
   (contract: POST /v1/accounts/{account_id}/move): putting an account on another holder of its
   kind (the Visa's dollars onto the Visa's holder, ALEJO's dollars onto ALEJO's), or taking it
   off onto a new holder of its own, in one write (`holder` in place of `holder_id`). A holder the
   move leaves with no live account is deleted in the same write. It is the holder line of a bank
   account's Edit form (question 1, answered B), drawn in `expense-world-holders-card-field.html`,
   and of a person's as question 12 decides. The line lists only holders of the account's kind.
   The engine's refusals, first one first, show in its words: an archived account
   (`ACCOUNT_ARCHIVED`), an account that has ever been in a statement, a deleted one included
   (`STATEMENT_KEEPS_ACCOUNT`), the account's own holder (`HOLDER_UNCHANGED`), an unknown or
   archived holder (`INVALID_REFERENCE`), a holder of the other kind (`HOLDER_KIND_MISMATCH`), a
   holder already holding that currency (`HOLDER_CURRENCY_TAKEN`), a holder with a statement
   (`HOLDER_HAS_STATEMENT`), and a new holder's refusals keyed `holder.<field>`
   (`NAME_EXISTS`, `STATEMENT_CODE_EXISTS`, `CAP_REACHED`).
7. **No flow leaves an empty holder behind, or deletes one the engine already removed:** a
   holder goes with its last account, so the app sends no `DELETE /holders/{id}` after an
   account's delete, and re-reads what it shows after a delete or a move.
8. **`expense import sheet --create-names` gives each account it creates a holder of its own,**
   named as question 8 decides; pairing, such as the Visa's two accounts, is done afterwards in
   the app (point 6), as [before-the-official-import.md](before-the-official-import.md) plans it.
9. **A holder's refusals read in the engine's words:** `NAME_EXISTS` and `STATEMENT_CODE_EXISTS`
   on a holder, `HOLDER_CURRENCY_TAKEN`, `HOLDER_HAS_STATEMENT`, `HOLDER_HAS_ACCOUNTS` and an
   archived holder refused as `INVALID_REFERENCE`, with the app's own line only where question 9
   adds one.
10. **Each new write lands with unit tests** for its happy path and each refusal it handles; the
    live tests of the holder routes are
    [catch-up-cards-statements-2b-live-suite-upload-lines-people.md](catch-up-cards-statements-2b-live-suite-upload-lines-people.md)'s.
11. **`d` on an account a live statement holds** shows `IN_LIVE_STATEMENT` and what to do next, as
    question 10 decides.

## How the owner knows it is done

1. You create a holder in two currencies and its soles and dollar accounts on it from the app,
   and the app shows them as one holder.
2. A new savings account goes on a holder of its own.
3. You set, change and clear a holder's statement code; the account forms ask for none.
4. `a` on either of the Visa's accounts archives both and says so as question 4 decides; `a`
   again unarchives both. `a` on ALEJO archives both of ALEJO's currencies the same way.
5. `t` on ALEJO turns both of ALEJO's currencies into bank accounts, and `t` back turns them into
   people, as question 11 decides; a holder that has had a statement is refused in the engine's
   words.
6. An account created on a holder of its own is paired onto another holder and unpaired again,
   each one request; a person the same, between person holders; one that has been in a
   statement is refused in the engine's words, a refused unpairing leaves no holder behind, and
   every move refusal shows its message.
7. `--create-names` on a sheet gives every account it creates a holder of its own, named as
   question 8 decides, and the dry run after it lists no name missing.
8. A refused holder write says why in the engine's words and writes nothing.
9. No flow leaves an empty holder behind or deletes a holder its last account's delete already
   removed; a new bank account with its own holder, and a two-currency holder, are each one
   write.
10. Deleting an account a live statement holds shows `IN_LIVE_STATEMENT` and what to do next.
11. The unit suite and the drift check pass.
12. ALEJO in soles and in dollars is created in one write from the app, as question 13 decides.
13. No request names `POST /people`, `POST /accounts/{id}/make-person`, `/make-account`,
    `/archive` or `/unarchive`, and nothing expects an account with no holder.

## Questions for the owner

Questions 1, 2, 4, 5 and 10, and pairing (point 6), are drawn in [mockups/](../mockups/):
`expense-world-holders-where.html` (1), `expense-world-holders-new-account.html` (2),
`expense-world-holders-archive.html` (4), `expense-world-holders-person-to-bank.html` (5),
`expense-world-holders-delete-in-statement.html` (10) and `expense-world-holders-card-field.html`
(pairing and unpairing on the account's Edit form, the owner's design, with questions a to c). The screen names and lines the options quote (Manage ▸ Cards, the CARD
line, "Archived with its card: …", "Another card has this code: …") say "card" until question
1's last part picks the app's word.

1. **Where holders live** (mockup).
   - **A.** A new Manage ▸ Cards list (name, statement code, its accounts' currencies, archived),
     where a holder is created, renamed, given its code, archived and deleted, and where accounts
     are paired and unpaired; Manage ▸ Accounts' Code column becomes the holder's name.
   - **B.** No Cards screen: the New account form makes or picks the holder, and Manage ▸
     Accounts' keys act on the account's holder.
   - **C.** B now, A later.

   **Recommended:** A. A holder is the engine's own thing that every app will show, and only a
   screen of its own renames a holder or changes its code in one place.

   Also: the engine's word is "holder", and a savings account is a holder of one account; the
   engine keeps "card" for the bank's product, a credit card. What word does the app use for the
   engine's holder? **Recommended:** "holder", the engine's word, so every app shares it.

   **Answered 2026-10-28:** B, no Cards screen. The owner's design: Manage ▸ Accounts gets a Card column, a
   bank account's Edit form a card line that picks the card it sits on, and New makes a card
   (question 2 C); drawn in `expense-world-holders-card-field.html`, whose questions a (what "a
   new card of its own" does), b (a card renamed and its code changed on its accounts' Edit
   forms) and c (the app's word), answered 2026-10-28: a, "a new card of its own" makes the
   holder at once on save, named after the account with no code; b, a holder's name and code
   are changed on any of its accounts' Edit forms, two lines marked as the holder's; c,
   **holder**, the engine's word: the screens and lines the mockups quote say "holder" where they
   say "card" (the Holder column, the holder line, "Archived with its holder: …").
2. **How a new bank account gets its holder, and how pairing looks** (mockup).
   - **A.** New always makes a holder of its own, named after the account; putting it with
     another holder's account is pairing, afterwards (point 6).
   - **B.** New has a CARD line: pick a holder holding no account in this currency, or a new
     holder. Pairing afterwards is for an account put on the wrong holder.

   - **C.** New makes a holder with its accounts in one form: its name, its statement code and
     its currencies (the Visa: PEN and USD), sent as one write (contract: POST /v1/holders).
     Adding a currency to a holder later is pairing (point 6).

   **Recommended:** C: the Visa's two accounts and its holder are made at once, in one write, and
   no step after it is needed. A collides on holder names when one name is used in two
   currencies; B needs the holder made before its first account. Also, under C: each account
   is named the holder's name and its currency (`Visa Signature PEN`, `Visa Signature USD`), or
   you type each account's name. **Recommended:** the holder's name and its currency, changed
   afterwards on the account's Edit form if you want.

   **Answered 2026-10-28:** C, as drawn: each account is named the holder's name and its currency.
3. **Where the statement code is edited.**
   - **A.** On the holder (its own Edit, under question 1 A).
   - **B.** On the account's Edit form, a line that says it changes the code of the whole holder.

   **Recommended:** A: one code per holder, edited in one place.

   With question 1 B there is no holder screen, so A has no place; this becomes question b of
   `expense-world-holders-card-field.html`, which waits on the owner.
4. **`a` archives the whole holder** (mockup).
   - **A.** The same key and note; every account of the holder dims.
   - **B.** As A, and the note names every account archived with it ("Archived with its card:
     Visa PEN, Visa USD.").
   - **C.** `a` on a bank account moves to the Cards screen; Manage ▸ Accounts keeps `a` for
     people only.

   **Recommended:** B: the key stays where it is, and the note says the other currency went too.

   **Answered 2026-10-28:** B.
5. **`t` on a person needs a holder** (mockup).
   - **A.** `t` makes a holder of its own, named after the person, at once.
   - **B.** `t` asks which holder: one holding no account in its currency, or a new one.

   **Recommended:** B, as question 2 B; A collides on holder names for a person in two
   currencies.

   **Answered 2026-10-28:** B. **No longer applies** since contract `e1959ea3b1d8ca6d`: `t`
   changes the kind of the whole holder, which stays, so there is no holder to pick; question 11
   asks what `t` does instead.
6. **`t`: what its refusals say.** The engine refuses `t` on an archived holder
   (`ACCOUNT_ARCHIVED`), on a holder already that kind (`KIND_UNCHANGED`) and on a holder that has
   ever had a statement, a deleted one included (`HAS_RECONCILIATION`), each on `holder_id`
   (contract: POST /v1/holders/{holder_id}/make-person). Part 1b dropped the app's line for
   `HAS_RECONCILIATION`.
   - **A.** The engine's words alone, for both.
   - **B.** A line of the app's under each.

   **Recommended:** A: the engine's words already say what is wrong, and the app guesses no rule.

   **Answered 2026-10-28:** A.
7. **Answered by the engine:** a holder goes with its last account (point 7), so no empty
   holder is left to delete. Nothing to pick.
8. **`--create-names`: a holder's name when one name is used in two currencies.** Each account it
   creates gets a holder of its own. Holder names are unique (contract: POST /v1/holders), and a
   name used in two currencies (the four people in both currencies, the old Oro card) makes two
   accounts.
   - **A.** The name and the currency (`ALEJO PEN`, `ALEJO USD`) only where the name is used
     twice; every other holder is named as its account.
   - **B.** Always the name and the currency.

   **Recommended:** A: most holders read as their account, and a person's holder goes when `t`
   turns it into a person. Also: the line `Created 4 accounts, 3 categories, 2 hashtags.` says
   nothing of holders; should it count them? **Recommended:** no: a holder per account is how
   accounts are made. Each account and its holder are one write (contract: POST /v1/holders).

   **Answered 2026-10-28:** A, and the line does not count holders.
9. **`STATEMENT_CODE_EXISTS`: the app's line.** It says "Another account in this currency has
   this code: pick another, or clear it there first.", which is no longer true: a code is held by
   one holder, whatever the currency (contract: "Holders", "One holder per code").
   - **A.** The engine's words alone.
   - **B.** A new line: "Another card has this code: pick another, or clear it there first."

   **Recommended:** A: the engine names the clash itself.

   **Answered 2026-10-28:** A.
10. **`d` on an account a live statement holds** (mockup). The engine refuses it,
    `IN_LIVE_STATEMENT`: "Must be an account no live statement holds, draft or completed: delete
    the statement first." (contract: DELETE /v1/accounts/{account_id}).
    - **A.** The engine's words alone, as every refusal shows.
    - **B.** The engine's words, then the app offers to delete that statement first (`y`), a
      completed one reverted before, and then the account.
    - **C.** The engine's words, and a line of the app's naming the statement and where to delete
      it.

    **Recommended:** A: the engine already says what to do, and deleting a statement is a choice
    of its own, made on its own screen.

    **Answered 2026-10-28:** A.

11. **`t` on an account whose holder holds two** (mockup
    `expense-world-holders-kind-whole.html`). `t` turns every account of the holder: on the Visa,
    both currencies become people; on ALEJO, both become bank accounts.
    - **A.** No question; the note names every account turned ("Now people: Visa Signature PEN,
      Visa Signature USD."), as the archive's note does (question 4 B).
    - **B.** No question; today's note ("Now a person."), and both rows move.
    - **C.** On a holder of more than one account, `t` asks first; a holder of one turns at once.

    **Recommended:** A: one key turns the whole holder, as `a` does, and the note says what went.
12. **A person's holder line** (mockup `expense-world-holders-person-line.html`). People are on
    holders, so the Holder column shows a person's holder too.
    - **A.** A person's Edit form gets the holder line a bank account's has, listing only person
      holders holding no account in its currency, and a new holder of its own: ALEJO's dollars are
      paired onto ALEJO's holder there.
    - **B.** No holder line on a person; a person's currencies are paired only when it is made
      (question 13).

    **Recommended:** A: people pair and unpair as bank accounts do, with the same line.
13. **A new person** (mockup `expense-world-holders-new-person.html`), `n` with type person.
    - **A.** One form, its currencies picked (PEN, USD or both), one write; each account named the
      person's own name ("ALEJO" in both).
    - **B.** The same form; each account named the name and its currency ("ALEJO PEN",
      "ALEJO USD").
    - **C.** Today's form, one currency; a second currency is a second New, paired afterwards
      (question 12 A).

    **Recommended:** A: one person in two currencies is made at once, and a person shows by name
    with its currency beside it.

Mockups this spec redraws, once picked: `expense-world-statement-code-field.html`,
`expense-world-account-to-person.html`, `expense-world-person-reconciliations.html` and the
archive panes of `expense-world-archived-account.html` in [mockups/](../mockups/).

---

## Tasks

Drafted when the owner names this the current spec.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `46e2fdf6e11d7548` → `e7393dd869963db1`, shared with the other parts of this
  catch-up; the holders (`29228c5191b6669b`), archiving a holder (`e06456a20aca6e4c`) and the
  rename of card to holder (`2cec1b59048f50dc`, `e7393dd869963db1`). `d34fc8d06ff652c4` and
  `4ac20e42cf8566ee` are answered by the catch-up on a person's opening balance, done on
  2026-10-28. Then `3e472b3256dcdc69` → `256f3190cf24fc36` (the hand-off "An account moves
  between holders, …"): the move, the delete with the last account, a holder created with its
  accounts and `IN_LIVE_STATEMENT`. Then `4dd95f836dba7be2` → `e020782e3579d011` (the hand-off "A
  person is a holder; …"): a holder's kind, the kind changed on the holder, the archive on the
  holder only, a person's move, `POST /people` removed and unpairing in one write.
- **The engine's "Done when" checks to report on:** the TUI reads and writes holders, and creates
  accounts with `holder_id`; archiving goes through the holder. From the hand-off "A person
  carries an opening balance, …": a refusal the app explains by reason is matched by its
  holder-named reason. From the hand-off "An account moves between holders, …": pairing and
  unpairing work from the TUI, every move refusal shows its message, no flow leaves an empty
  holder behind or calls `DELETE /holders/{id}` on a holder already gone, a new bank account and
  a two-currency holder are each one `POST /holders`, and deleting an account a live statement
  holds shows `IN_LIVE_STATEMENT`. From the hand-off "A person is a holder; …": no request names
  `POST /people`, `POST /accounts/{id}/make-person`, `/make-account`, `/archive` or `/unarchive`;
  ALEJO in soles and dollars is created in one write from the app, and a person made on its own
  holder is paired with another by the move; unpairing is one request, and a refused one leaves no
  holder behind.
- **The asks it closes:** "Yes to moving an account to another card, with the limits you
  proposed; no to the sheet import refusing a name used in two currencies", "Delete a card with
  its last account, so no client leaves an empty card behind", "Create a bank account and its own
  card in one write" (its `make-account` half answered differently: the kind changes on the
  holder, whole) and "Move an account onto a new holder in one write".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
