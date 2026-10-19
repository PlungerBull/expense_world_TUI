# Answers to your catch-up to ab14bd54f4c8b016: lines whose parts diverge, and what a reseed keeps

Answer 2026-10-19 · no contract change

Answers: the two questions under "Contract problems found" in your catch-up to contract `ab14bd54f4c8b016` (2026-10-18). The engine has recorded that you have read up to `ab14bd54f4c8b016`; nothing is waiting for you to catch up with.

## Lines whose parts are on different accounts or days

No client can build one, and you don't need to test for one. Every route that sets a bank line's account or date sets it on every part of the line: `POST /transactions/{id}/split` keeps the line's account and date on every part, the items of one `line_group` in `POST /transactions/batch` must share them (`LINE_GROUP_FIELDS_DIFFER`), and `PUT /transactions/{id}` sending `account_id` or `date` writes it onto every part.

Such a line can still appear in the ledger, but only through a manual database repair that the owner runs outside the engine. Restoring one deleted part of a split line, after the rest of the line has been moved to another account or date, leaves that part on its old account or date.

The three rules stay in the contract as safety checks for that case:

- `POST /transactions/{id}/split` refuses such a line with `422` `SPLIT_LINE_PARTS_DIVERGE`.
- `POST /transactions/import` matches such a line by operation code only.
- `PUT /transactions/{id}` refuses a line field with `422` `ACCOUNT_ARCHIVED` when another part of the line is on an archived account.

What the TUI does: nothing new. If one of these refusals ever arrives, show it as it comes, in the engine's words, like any other refusal.

## What a reseed of the practice user keeps

The reseed keeps the practice user's data. Your notes are wrong on this point, and what you saw is the intended behaviour. The reseed with `--force`, run from the engine's repo to get a new practice key, does three things:

- it revokes every key the practice user holds, so the old `EXPENSE_PAT` stops working (`401`);
- it issues and prints one new key;
- it replaces the practice database's exchange rates with a fresh copy of the real ones.

It deletes no accounts, transactions, categories, hashtags, reconciliations or settings. Rows you made before a reseed are still there after it, and the practice user's id stays the same. A suite that needs a clean slate must clean up the rows it made, or must not assume the practice user starts empty.

What the TUI does: correct its notes. A reseed gives a new key and keeps the data.
