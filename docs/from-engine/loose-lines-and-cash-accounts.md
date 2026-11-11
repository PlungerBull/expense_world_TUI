# A loose-lines refusal names its lines by id in `error.details`, a user may hold several cash accounts, every message and promise the contract publishes says exactly what the engine sends, and an import or upload that waits behind another change is judged on what it finds

Shipped 2026-11-09 to 2026-11-11 · ⚠️ breaking · contract `ebadad5b9499610c` → `3a4ff8dac458cf83`

Answers:
- "A loose-lines refusal names its lines by id, in a field a client reads", raised 2026-11-08.
- From the catch-up note on `1002f105c6bacdf1` (2026-11-09):
  - "`card-soles-only` cannot be tested"
  - "the bound is written two ways"
- From the catch-up note on `9b3b43429d8bd11e` (2026-11-09): "`POST /auth/pat`: the taken-id message differs from the contract".
- From the catch-up note on `2fa4967b8eed9c3f` (2026-11-09): the cash account's two `null` problems ("`null` on the cash account answers two codes for one mistake" and "PUT's null rule leaves out the cash account's `name`").
- No ask: the owner's own change, several cash accounts.
- No ask: the engine's own contract fixes, items 9–12 below.
- No ask: the engine's own fixes for writes sent at the same moment, items 13–14 below.
- No ask: wording only, item 15 below.

It is breaking in these places:
- the `card-soles-only` sample now prints a different account number;
- a request amount past the largest amount answers a new message;
- the cash account is no longer one account named `Efectivo`: there may be several, named `CASH-0001`, `CASH-0002`, …, and an empty one can be deleted;
- some `null`s on `PUT /accounts/{id}` answer a different reason or in a different order;
- a `404` message names its resource in words (`bank line not found.`, where it read `bank_line not found.`), and `SETTINGS_MISSING`'s message changed;
- `GET /statements/samples/{sample}` no longer declares `NOT_FOUND`;
- a `RESTORED` activity entry now carries the same snapshot shape as any other entry of its resource;
- a bank download that waits behind `make-person` on its account, and a PDF upload that waits behind another upload on its account, answer differently (items 13–14).

No field or status was removed.

## Each ask

- **Loose-lines ids in a field a client reads:** done as asked. The ids are in the new `error.details` key, on `POST /statements/{id}/complete` and `POST /statements/import` (dry run and apply).
- **`card-soles-only` cannot be tested:** done as proposed.
  - The sample now prints a number ending `0001`.
  - Every run of the practice seed keeps a soles-only `BCP-0001` beside `BCP-0000` and prints its id.
- **The bound written two ways:** done. There is now one wording everywhere, the file rows' own: `The amount is past the largest amount, 99,999,999,999 cents.`
- **`POST /auth/pat` taken-id message:** done the second way you offered. The engine already sends a message in each place, so the contract now quotes both exactly as sent; the engine's answer is unchanged.

- **The cash account's `null` answers two codes:** done the first way you offered. A `null` on the cash account answers `CASH_TAKES_NO_FIELD` on `PUT /accounts/{id}` too, as on `POST /accounts`.
- **PUT's null rule leaves out the cash account's `name`:** done. The null-rule exceptions now name the cash account's fields.

## What changed

**1. Every error body has a fifth key, `details`** (`ebadad5b9499610c`).

```json
{"error": {"code": "...", "message": "...", "fields": {...}, "reasons": {...}, "details": null}}
```

- `details` is `null` on every error except the refusals whose operation section lists a shape for it. Today that is only `LOOSE_LINES_ON_SEALED_DAYS`.
- Read data from `details`; never parse `message`.
- The error schema `ErrorBody` now marks all five keys `code`, `message`, `fields`, `reasons` and `details` as required. Every error already carried the first four.

**2. `LOOSE_LINES_ON_SEALED_DAYS` carries the lines' ids** (`e5b3b599ad5113e4`, `7cf2b95ec352b082`).

It applies on `POST /statements/{id}/complete` and on `POST /statements/import`, dry run and apply alike. For example, `422`, `VALIDATION_ERROR`:

```json
"details": {"bank_line_ids": ["d0a7475f-…", "04f0775e-…"], "count": 2}
```

- **Which lines:** exactly the lines in no statement that sit on a day the close would seal. A flagged line on a day that stays open (such as the statement's open last day) is never in it. On an upload, a line the upload takes out of the draft is included.
- **Order:** the order `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement` lists them. That is the line's date, then when the line was created, then its line number.
- **Cap:** past 200 lines, `bank_line_ids` holds the first 200 and `count` is the full number. For example, 201 loose lines answer 200 ids and `"count": 201`.
- **The upload's message link:** it now carries a limit, `GET /bank-lines?ids=<id>,…&limit=<n>`, where `n` is the number of ids named. Following the link reads every named line in one page.
- **Any `?ids=` read:** `GET /bank-lines?ids=` answers 50 per page unless you send `limit` (up to 200). To read up to 200 named lines in one page, send `limit`.
- **The close's message link** is `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement`. It is unchanged and still paged. It also lists the flagged lines on open days, so use `details` for the lines that refuse.

**3. The amount bound has one wording** (`9c2b12e848fde12b`).

On a request `*_cents` field, reason `OUT_OF_RANGE`:
- Before: `Input should be less than or equal to 99999999999`, or `greater than or equal to -99999999999`.
- After, in both directions: `The amount is past the largest amount, 99,999,999,999 cents.`

On a file row the message is as before. A paper row reads `Row 2: The amount is past the largest amount, 99,999,999,999 cents.`. A sheet row or bank-download row names the cell it read, then ends in the same `is past the largest amount, 99,999,999,999 cents.`.

Reasons, statuses and the published `minimum` and `maximum` are unchanged.

**4. `POST /auth/pat` with a taken id** (`9c2b12e848fde12b`, wording only).

`409 CONFLICT`, `ID_EXISTS`:
- the top-level `message` is `A personal access token with id '<id>' already exists.`;
- `fields.id` is `A personal access token with this id already exists.`.

**5. Rows tied on creation time list by `id`** (`9c2b12e848fde12b`, wording only).

The order of accounts, categories, hashtags and a category's hashtags is `sort_order`, then creation time, then `id`. This covers `GET /accounts`, `GET /categories`, `GET /hashtags` and `/dashboard`'s `accounts`. Two rows created in the same instant now always list in the same order.

**6. The soles-only card sample prints `0001`** (`42e2772f0e9a8ac7`).

- `card-soles-only` now prints `0000-00XX-XXXX-0001` in its header and `000000XXXXXX0001` above its purchases. Every other sample still prints `0000`.
- Upload it to a soles-only account numbered `0001`. An account numbered `0000` now refuses it with `422` on `account_id` (`STATEMENT_NUMBER_MISMATCH`).

**The practice seed** now leaves the shared practice user two accounts on every run:
- `BCP-0000`, holding PEN and USD, as before;
- a new live, active `BCP-0001`, holding PEN only.

It prints each account's id on its own line:

```
EXPENSE_PRACTICE_ACCOUNT_ID=<id>
EXPENSE_PRACTICE_SOLES_ACCOUNT_ID=<id>
```

The first line is unchanged. If `BCP-0001` is archived, deleted, holds dollars or lacks soles, the seed puts it back. If it holds dollars with something booked in them, the seed stops with an error and changes nothing more.

Neither practice account has a statement code. An upload to either answers `422` `NO_STATEMENT_CODE` until you set one with `PUT /accounts/{id}`, for example `{"statement_code": "SOL"}`.

**7. Several cash accounts** (`3c4855fecadcfc80`).

- Every `POST /accounts` with `kind: "cash"` makes a new cash account. `409 CASH_EXISTS` is no longer sent, so the New form can always offer `cash`. The account cap (`422 LIMIT_REACHED` on `id`) still applies.
- The engine names each one `CASH-<n>`, four digits: `CASH-0001`, `CASH-0002`, …. The number is one more than the highest any of the user's cash accounts has ever had, archived and deleted ones included, so a number is never reused. It skips a number whose name another live account already holds: a person named `CASH-0004` makes the next cash account `CASH-0005`. The client still sends no name (`CASH_TAKES_NO_FIELD`).
- Past `CASH-9999`: `422 LIMIT_REACHED` on `kind`, reason `CASH_NUMBERS_EXHAUSTED` (new).
- `Efectivo` is no longer a held name; a person may be named `Efectivo`. The user's existing `Efectivo` cash account becomes `CASH-0001`, with the same `id`, balances and transactions.
- **A cash account is deleted like any account:** `DELETE /accounts/{id}` deletes one with no transactions, and refuses one holding any transaction, its opening balance included (`409 HAS_TRANSACTIONS`). `CASH_NOT_DELETABLE` is no longer sent. Its kind still never changes (`409 CASH_KIND_FIXED` on `make-person` and `make-account`).
- Everything else is as before: no bank, no numbers, no statement code, no statement.

Before: `GET /accounts` →
```json
{"id": "…", "kind": "cash", "name": "Efectivo", "bank_code": null, "numbers": [], …}
```
After:
```json
{"id": "…", "kind": "cash", "name": "CASH-0001", "bank_code": null, "numbers": [], …}
```

**8. The cash account's `null`s** (`75a4a9be5c8b86f0`).

On `PUT /accounts/{id}`:
- On the cash account, a `null` `name`, `bank_code`, `current_number`, `new_number` or `statement_code` is `422 CASH_TAKES_NO_FIELD` on that field, as a value is. Before, a `null` `bank_code` or `new_number` was `NOT_NULL`.
- On a bank account or a person, a `null` `bank_code` or `new_number` is still `NOT_NULL`. It is now answered alone, after the account is found. So:
  - an unknown, deleted or another user's id with a `null` `bank_code` now answers `404`, where it answered `422 NOT_NULL`;
  - a `null` on any other field (`sort_order`, `color`, `currency_code`, `opening_balances`), a malformed `color` or a sent `currency_code` answers first: `{"color": null, "bank_code": null}` answers `NOT_NULL` on `color` alone, where it named both.
- The cash fields each route takes: `POST /accounts` takes `name`, `bank_code`, `last4` and `statement_code` (`current_number` and `new_number` are `UNKNOWN_FIELD` there); `PUT /accounts/{id}` takes `name`, `bank_code`, `current_number`, `new_number` and `statement_code` (`last4` is `UNKNOWN_FIELD` there).

**9. Messages name a resource in words** (no contract version of its own; `SETTINGS_MISSING` in `250da4756700ac63`).

The status, `code` and reasons are unchanged; only the text a person reads changed.

| Where | Before | After |
|---|---|---|
| `404` on a bank line | `bank_line not found.` | `bank line not found.` |
| `404` on a personal access token | `personal_access_token not found.` | `personal access token not found.` |
| `SETTINGS_MISSING` | `user_settings not found. Call /auth/bootstrap first.` | `User's settings not found. Call /auth/bootstrap first.` |
| `409` after a concurrent change to a bank line | `bank_line was changed by a concurrent request.` | `bank line was changed by a concurrent request.` |

Every other resource already read in words (`transaction not found.`, `statement not found.`, …).

**10. Two reason texts and one declared code** (`250da4756700ac63`).

- `SEALED_PERIOD`'s published text now covers both of its uses:
  - a line put on a day a completed statement locks;
  - a line left in no statement on such a day, on `statement_id` or `file`. That happens on an unassign, the deletion of a draft, or an upload taking the line out of its draft.
- `ACCOUNT_ARCHIVED`'s published text names `make-person` and `make-account` once, and lists where each other refusal lands. The full list is in the reason table of `/openapi.json`.
- `GET /statements/samples/{sample}` no longer declares `NOT_FOUND`. An unknown sample was always `422` (`INVALID_FORMAT` on `sample`). `NOT_FOUND` is now declared only on operations with an id in the path.

**11. A replay promises the same JSON, not the same bytes** (`82a974b3c1384d85`, wording only).

A write repeated with the same `X-Idempotency-Key` answers the first answer's status and the same JSON body: the same keys and values. The keys may come in another order. The engine behaved this way already; the contract said "verbatim". Compare replays as parsed JSON, never as text.

**12. A restored row's activity entry has the normal shape** (`2dc7f6cfcb365f8e`).

A `RESTORED` entry is written only when the owner undeletes a row by hand, never by an API route. It now carries the same `before` and `after` snapshots as any other entry of its resource:
- a transaction's `account_id` is its account, with `currency_code` beside it (it was the id of the account's currency record, which is no account);
- a statement's snapshot carries its `balances`, `unplaced_count` and `shared_place_count`;
- an account's carries its `numbers`, and its `kind` as `bank`, `person` or `cash` (it was the stored number, such as `2`);
- a currency's carries no record id.

Entries restored before 2026-11-09 keep their old shape. *Activity Log* → *Older and restored entries* says how to read each, resource by resource. Read every entry by its keys.

**13. A bank download that waits behind `make-person`** (`8348a760a6465c58`).

`POST /transactions/import` sent for an account at the same moment as `POST /accounts/{id}/make-person` on it is judged wholly before or wholly after the conversion:
- judged after it, the account is a person: `422` on `account_id`, reason `PERSON_TAKES_NO_STATEMENT`, nothing written, as for a download sent for a person;
- judged before it, the download lands as on a bank account.

Before, a download that waited behind the conversion could write its rows onto the person. `POST /transactions/import-sheet` is unchanged: it lands either way, on the person when judged after the conversion.

**14. A PDF upload that waits behind another upload** (`41c1b4d57b8dea1c`).

`POST /statements/import` sent at the same moment as another upload (or a `POST /transactions/import`) on the same account runs after it, whatever currencies each paper prints, and is judged on what the first left: it answers what a fresh upload of the same paper would.
- Before: the second upload could be judged on the month as it stood before its wait and answer `422` on `file`, `PERIOD_OVERLAPS`.
- After: it answers the month as the first left it, for example `409` on `file`, `RECONCILIATION_NOT_DRAFT`, or `422` on `account_id`, `ACCOUNT_CURRENCY_NOT_ON_PAPER`, or succeeds.
- `STATEMENT_MONTH_TAKEN` on an upload now comes only from a `POST /statements` or a `PUT /statements/{id}` changing the days at the same moment, never from another upload.

An upload that waits behind a currency added to or removed from its account still answers `409 CONCURRENT_CHANGE` on `account_id`; send it again.

**15. Cash accounts in the plural** (`3a4ff8dac458cf83`, wording only).

The published texts of the reasons `CASH_KIND_FIXED`, `CASH_NOT_DELETABLE` and `NAME_EXISTS`, and the description of `GET /dashboard`'s `archived_accounts`, now speak of cash accounts as a kind a user may hold several of ("A cash account's kind never changes", "banks and cash accounts"), where they said "the cash account". No status, code, reason or message the engine sends changed.

**Not a contract change: the sample card papers** (`GET /statements/samples`). Each card paper now prints a payment due date 20 days after its cycle's closing day, and a minimum payment of 5% of the soles billed. Before, every paper printed `20/10/26` and `123.45`. The engine reads neither value, so an upload's result is unchanged. Two calls to `GET /statements/samples` answer the same thing.

## How it was checked

Against the engine's practice engine on 2026-11-09: items 1–6 at `42e2772f0e9a8ac7`, items 7–8 at `3c4855fecadcfc80`. Every check passed.

- **A close refused for one loose line:** `details` is `{"bank_line_ids": ["<that line>"], "count": 1}`, and the flagged line on the statement's open last day is not in it. Once the loose line was deleted, the close passed, and the last-day line came back as flagged only.
- **An upload refused for two loose lines, one taken out of the draft:** both ids are in `details`, `"count": 2`, on the dry run and on the apply. Nothing was written: the line stayed in the draft, and the transaction and statement counts did not change.
- **201 loose lines:** 200 ids in statement order and `"count": 201`, on the close and on the upload's dry run.
- **The upload message's link:** it read every named line in one page with no `next_cursor`. That held for 2 lines (`&limit=2`) and for 200 (`&limit=200`).
- **The seed:** run twice. Both runs printed both id lines, each on its own line, with the same ids. The shared practice user holds `BCP-0000` (PEN and USD) and `BCP-0001` (PEN only), both live and active.
- **The soles-only sample:** after a statement code was set on a PEN-only account numbered `0001`, `card-soles-only` uploaded and closed (balances matched the sample, difference 0). An account numbered `0000` refused it with `STATEMENT_NUMBER_MISMATCH`.
- **The bound:** `POST /transactions` with `amount_cents` `100000000000` answers the new message with `OUT_OF_RANGE`. The file-row wording is pinned by the engine's own tests.
- **`POST /auth/pat` with a taken id:** both messages match the contract byte for byte.

- **Several cash accounts:** three creates made `CASH-0001`, `CASH-0002`, `CASH-0003`. After archiving `CASH-0003` the next was `CASH-0004`; after deleting the empty `CASH-0004` the next was `CASH-0005`. A cash account with an opening balance refused `DELETE` with `HAS_TRANSACTIONS`, nothing written. A person named `CASH-0005` made the next cash account `CASH-0006`; a person named `Efectivo` was accepted; `make-person` on a cash account is still `CASH_KIND_FIXED`.
- **The rename:** the engine's own tests show an `Efectivo` cash account, live or archived, becoming `CASH-0001` with every other field unchanged, and the next one `CASH-0002`.
- **The cash `null`s:** on the cash account, a `null` `bank_code` or `name` on `POST`, and a `null` `bank_code`, `new_number`, `name`, `current_number` or `statement_code` on `PUT`, each answered `CASH_TAKES_NO_FIELD`, nothing written. On a bank account and a person, a `null` `bank_code` or `new_number` answered `NOT_NULL`.

**`f4a9878710884e09`** is wording only: the contract speaks of "a cash account" and "cash accounts" where it meant the kind, and *The cash account takes no statement either* is now *A cash account takes no statement either*. No behaviour changed.

Items 9–12 and the sample papers, against the practice engine at `2dc7f6cfcb365f8e` on 2026-11-10. Every check passed.

- **Messages in words:** a `404` on a random id read `bank line not found.` (on `GET` and `DELETE /bank-lines/{id}`), `personal access token not found.`, `transaction not found.`, `statement not found.`, `account not found.`, `category not found.`, `hashtag not found.` The engine's own tests walk every resource through every message.
- **Declared codes:** `GET /statements/samples/{sample}` declares `VALIDATION_ERROR`, `UNAUTHORIZED`, `INTERNAL_ERROR` and no `NOT_FOUND`. `GET /statements/samples/nope` answered `422`, `INVALID_FORMAT` on `sample`. `GET`, `PUT` and `DELETE /statements/{statement_id}` still declare `NOT_FOUND`.
- **Reason texts:** `SEALED_PERIOD`'s and `ACCOUNT_ARCHIVED`'s texts in `/openapi.json` read as item 10 says.
- **Replay:** the same `POST /transactions` sent twice answered `201` both times, with equal JSON once parsed and keys in a different order. The same key with a different amount answered `409`.
- **Restored entries:** pinned by the engine's own tests, which compare each restored entry with the engine's own snapshot of the same row, for every resource.
- **Sample papers:**
  - `card` closes 25/03/25 and is due 14/04/25;
  - `card-no-dollars` closes 25/04/25 and is due 15/05/25;
  - `card-soles-only` closes 25/05/25 and is due 14/06/25.

  `card` still uploads (dry run) with its published balances.

Items 13–14, against the practice engine at `41c1b4d57b8dea1c` on 2026-11-11. Every check passed.

- **Download onto a person:** after `make-person` on a new account, `POST /transactions/import` for it answered `422`, `PERSON_TAKES_NO_STATEMENT` on `account_id` alone, and `GET /transactions?account_id=<id>` listed nothing. The race itself (a download waiting behind the conversion) is forced by the engine's own tests, for the download and the sheet import; they fail when the check under the lock is removed.
- **An upload queued behind another:** forced by the engine's own tests. The queued upload's answer equals a fresh upload's of the same paper (`409 RECONCILIATION_NOT_DRAFT`, and `422 ACCOUNT_CURRENCY_NOT_ON_PAPER` when the papers print different currencies), and one statement is written. They fail with `PERIOD_OVERLAPS` when the wait is undone.
- **Contract:** `/openapi.json` serves `41c1b4d57b8dea1c`, and `x-changelog` carries both entries above.

Item 15, by the engine's own contract tests at `3a4ff8dac458cf83` on 2026-11-11: `/openapi.json` carries the new texts and the `x-changelog` entry.

**Live engine:** it serves `3a4ff8dac458cf83`. The owner has applied the ledger update for several cash accounts.

## What the TUI does

1. Read `error.details` as part of the error body. Expect it `null` everywhere except `LOOSE_LINES_ON_SEALED_DAYS`.
2. For the loose-lines screen, take the ids from `details.bank_line_ids`. When `count` is greater than the number of ids, say so. Read the lines with `GET /bank-lines?ids=<ids>&limit=<number of ids>`.
3. Wherever you read `GET /bank-lines?ids=`, send `limit`.
4. If anything matches the old bound message (`Input should be less than or equal to …`), match `The amount is past the largest amount, 99,999,999,999 cents.` instead, or better, the reason `OUT_OF_RANGE`.
5. For `card-soles-only`:
   - read `EXPENSE_PRACTICE_SOLES_ACCOUNT_ID` from the seed's output;
   - set a statement code on that account with `PUT /accounts/{id}`;
   - upload the sample to it and close it.

   Your soles-only close can now be tested.
6. Cash accounts:
   - offer `kind: "cash"` in the New form always (no `CASH_EXISTS`);
   - never match a cash account by the name `Efectivo`; read `kind` and the `id`;
   - offer Delete on a cash account, and show `HAS_TRANSACTIONS` when it refuses;
   - handle `CASH_NUMBERS_EXHAUSTED` like any `LIMIT_REACHED`.
7. On `PUT /accounts/{id}`, expect `CASH_TAKES_NO_FIELD` for any `null` sent to the cash account, and the new order for a bank account's or person's `null`.
8. Because `expense_world_test` was rebuilt, the TUI's practice users had no live key there. The engine's check ran the plain seed, which issued one. That key went unrecorded, so run your launcher's `--force` reseed to get a key you hold.
9. If anything matches a message with an underscore noun (`bank_line not found.`, `personal_access_token not found.`, `user_settings not found. …`, `bank_line was changed by a concurrent request.`), match the `code` and reason instead.
10. Drop any handling of a `404` from `GET /statements/samples/{sample}`; an unknown sample is `422`.
11. Wherever a test compares a replayed answer with the first one, compare parsed JSON, not text.
12. If the TUI shows activity entries, read a `RESTORED` entry like any other entry of its resource. Read an entry restored before 2026-11-09 by its keys, as *Activity Log* → *Older and restored entries* says.
13. Show a bank download's `PERSON_TAKES_NO_STATEMENT` as for a download sent for a person, even when the account was a bank account when the user picked it.
14. Show a PDF upload's refusal as for a fresh upload; do not treat `PERIOD_OVERLAPS` or `STATEMENT_MONTH_TAKEN` as "another upload is running".

## Done when

- A close refused for one loose line shows that line's id from `details`, and the flagged line on the open last day is not listed.
- An upload's dry run refused for two loose lines, one taken out of the draft, shows both ids.
- A refusal for 201 lines shows 200 lines and says there are 201.
- The `card-soles-only` contract test uploads to `BCP-0001` and closes it.
- Three cash creates show `CASH-0001`, `CASH-0002`, `CASH-0003`, and an empty one deletes.
- A `null` `bank_code` sent to the cash account on edit shows `CASH_TAKES_NO_FIELD`.
- No TUI code or test matches an underscore noun in a message, or a `404` from the samples route.
- A bank download refused `PERSON_TAKES_NO_STATEMENT` shows as a download for a person.
- The TUI reads `3a4ff8dac458cf83` from `/openapi.json` with no open catch-up.
