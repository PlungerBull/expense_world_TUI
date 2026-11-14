# Catch-up to contract 3.1

Catches up from contract `1.1` through `2.0` and `3.0` to `3.1`, the engine's hand-off "A bank is a
code the owner types, every bank account has a last 4, and the sheet import makes the accounts,
categories and hashtags it lists" (2026-11-14), all but its screens: the bank account form and the
import's review are [the official import](before-the-official-import.md)'s tasks 7 and 8. It runs
first in v1.0: until it lands, the live contract suite fails on the engine.

**Status: drafted 2026-11-14, waiting for the owner's approval.** It has no question of its own;
the screens' questions are the official import's question 19. When done, its why moves to
[decisions.md](../decisions.md), its reply goes to [to-engine/](../to-engine/), and this file is
deleted.

---

## What changed

1. **A bank account always has a last 4** (`2.0`, breaking): a missing or `null` `last4` on
   `POST /accounts` and on `make-account` is refused (`REQUIRED`), and a bank account is always
   named `CODE-1234` (contract: "Bank Accounts").
2. **A bank is any 3 or 4 capital letters** (`2.0`, breaking), compared as sent; no bank has to
   exist first. Anything else is `INVALID_FORMAT` on `bank_code`; `UNSUPPORTED_VALUE` is no longer
   sent for it.
3. **`GET /banks` lists the banks whose statement PDFs the engine reads** (`2.0`), no longer the
   banks an account may be at. Its answer keeps its shape, and today holds `BCP` alone.
4. **Only a bank `GET /banks` lists takes a statement code** (`2.0`): otherwise
   `BANK_TAKES_NO_STATEMENT_CODE`, keyed on the field that caused it (contract: "What an account
   is", "Statement code").
5. **A bank account never loses its last number** (`2.0`): `current_number: null` on its only
   number is `409` (`LAST_NUMBER`).
6. **The sheet import's `names.accounts[]` loses `ambiguous`** (`3.0`, breaking).
7. **The sheet import takes an optional `create`** (`3.0`): the accounts, categories and hashtags
   it lists are made in the same write as the names and the rows, all or nothing, each judged by
   its create route's rules, a refusal keyed `create.<list>.<i>.<field>`. The answer gains
   `created` (contract: POST /v1/transactions/import-sheet, "Create").
8. **A dry run keeps nothing, its idempotency key included** (`3.0`, breaking), on the sheet
   import, the bank download and the statement upload: the apply may reuse its dry run's key
   (contract: "Base Conventions", "Idempotency").
9. **The dry run suggests each missing account** (`3.1`): `suggestion`, always present, by rules
   the contract publishes (contract: POST /v1/transactions/import-sheet, "Names").

## What the engine asks the TUI to do

1. **The account forms** (New, Edit, and `t` making a bank account): BANK typed, LAST 4 required,
   the statement code line only for a bank `GET /banks` lists, a number removed only while
   another stays, and the engine's refusals (`INVALID_FORMAT`, `BANK_TAKES_NO_STATEMENT_CODE` on
   either field, `LAST_NUMBER`) under their lines.
2. **The sheet import:** stop reading `ambiguous`; prefill each missing account from its
   `suggestion` and let the owner confirm or change it; send the confirmed accounts and the
   missing categories and hashtags in `create`, with ids this client generates, `names` pointing
   at them; show `created` from the dry run before the apply; show a refusal on its row.
3. **Dry-run keys:** the apply may reuse its dry run's key; nothing may rely on a dry run's key
   replaying its answer.
4. **Move the stored contract version to `3.1`.**

1 and 2 are screens: the official import's tasks 7 and 8. 3 needs no change: every dry run and
apply is a write of its own, under its own key. 4 is task 1 here.

## What the engine declined, or did differently

- **A lower-case bank is refused, never upper-cased by the engine.** Whether the form capitalises
  what the owner types is the official import's question 19, pane 7.
- **A person keeps its statement code as a label.** Making that person a bank account at a bank
  `GET /banks` does not list is refused on `bank_code`; `t`'s question shows it under BANK
  (task 7).
- **A suggestion is never applied by itself:** the import makes only what `create` lists.

## How the owner knows it is done

1. The version check against the practice engine reads `3.1` with nothing left to catch up, and
   the drift check is clean.
2. The live contract suite passes against the practice engine, with a test for each change above.
3. `pytest tests/unit` passes.
4. Part 1 of the reply to the engine is in [to-engine/](../to-engine/).

---

## Tasks

Each task leaves `pytest tests/unit` green and reads the live contract on the practice engine
before building. Each live test makes its accounts with a last 4 from `next_last4()`, so the
practice-user clean-up finds them.

1. **Record contract `3.1`** with the version check's `--record-version`. The sheet import's answer
   builder (`sheet_import_answer`, `sheet_name_use` in tests/unit/helpers.py) drops `ambiguous`
   and gains `suggestion` and `created`, until the drift check reports nothing. CHANGELOG's
   "Upgrading:" line names contract `3.1`.
2. **The five live tests that fail on `3.1`** follow the new rules: in
   tests/contract/test_account_numbers.py, every account read carrying its bank and numbers, a
   replacement ending the old number, and the kind changes' bodies, which make a bank account or
   make an account without a last 4; test_sheet_import.py's made-up sheet, which reads
   `ambiguous`; and test_statement_numbers.py's account with no number, which can no longer be set
   up and is cited, not driven, until the engine answers the reply's contract problem.
3. **Live tests for the account rules of `2.0`:** `IBK` with a last 4 made as `IBK-4321`, a second
   `IBK` with another last 4 made, the same last 4 again `NAME_EXISTS`; `ibk`, `IB`, `IBKXX`,
   ` IBK` and `I8K` each `INVALID_FORMAT` on `bank_code`; no last 4 `REQUIRED` on `POST /accounts`
   and on `make-account`; `BANK_TAKES_NO_STATEMENT_CODE` on each field it is keyed on, with a
   `BCP` account still taking a code; `GET /banks` still `BCP`; `LAST_NUMBER` on an only number,
   and the current number removed when there are two.
4. **Live tests for the sheet import of `3.0` and `3.1`:** one apply with `create` makes a bank
   account, a person, a cash account and an archived account, with categories and hashtags,
   `names` pointing at their ids; `created` counts them on the dry run and the apply; each made
   account's balance per currency equals its rows. A refusal of a row, of a made account's field,
   and of two made hashtags sharing a name is keyed as the contract says and leaves nothing made.
   `suggestion` is `null` beside a `proposed_id` and otherwise follows the published rules on a
   few names (`BCP 5678`, `BCP5678`, `Interbank PEN`, a name with two runs of four digits).
5. **A live test of dry-run keys** on each of the three routes: the apply under its dry run's key
   goes through, and a dry run sent again runs again. A key an apply used stays `409` for a dry run.

## Reply to the engine

Part 1 of the reply to the hand-off of 2026-11-14, covering `1.1` to `3.1` but the screens (part 2,
the official import's tasks 7 and 8, whose "Reply to the engine" section holds it).

- **Done when, reported back:** no TUI code reads `ambiguous` and the contract check passes
  against `3.1` (task 1); the forms and the review are reported in part 2.
- **Contract problems found:** `ACCOUNT_HAS_NO_NUMBER` (`POST /statements/import`), `NO_NUMBER`,
  and "to give a numberless account its first number, send `current_number` with `last4`"
  (`PUT /accounts/{id}`) are still published, though since `2.0` no request makes a numberless
  bank account. Does one still exist, from before `2.0`? If not, the contract would drop them; if
  so, it would say where one comes from, since no live test can set one up now.
- **Asks it closes:** "A bank account's bank is a 3–4 letter code the user types, its last 4 is
  required, and only a bank `GET /banks` lists takes a statement code" and "The sheet import
  suggests the accounts it is missing and makes the ones the user confirms, with its names and
  rows, in one write", each for its contract side.

## Found along the way

Not built in this spec; sorted when it is done.

- **The Backlog's "`scripts/clean_practice_user.py` cannot remove an unnumbered `BCP`"** has no
  cause left once `2.0` makes every bank account numbered; it goes once the acceptance check finds
  no unnumbered account on the practice user.
