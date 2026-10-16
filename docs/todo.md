# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks live in [engine-asks/](engine-asks/), one file each.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes the entry. After a round of
answers it tells the owner what each answer unlocked, and drafts a spec in [specs/](specs/) for
work that is now unblocked. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### The engine contract moved: catch up now?
Asked 2026-10-16 · Blocks: every new task (the loop stays stopped until this is answered)
The faster-loop spec's acceptance check found the engine's contract six versions ahead of
this repo: bank lines, `POST /transactions/{id}/split`, batch `line_group`, and an import
that compares bank lines. The bank import's `matched` rows now carry `bank_line_id`, not
`ledger_id`, and `excess` is gone. That breaks one live contract test
(`test_dry_run_then_apply_then_the_same_file_matches`, `KeyError: 'ledger_id'`) and leaves five
fixture keys stale. The check printed:

```
the engine's contract version has changed: saved 42d70a629215928d, engine 66d65a86a9cf1c19.
what the contract changed since 42d70a629215928d, newest first:
  66d65a86a9cf1c19  2026-10-16
    added: `line_group` on each item of `POST /transactions/batch`, optional. Items naming the same `line_group` are created as the parts of one bank line the engine mints, sharing one `bank_line_id`; an item without one gets a line of its own, as before. The name is trimmed, must not be blank (`EMPTY`) and is at most 64 characters (`OUT_OF_RANGE`). It is scoped to the request: never stored, never returned. *POST /transactions/batch* → *Line groups* describes it.
    added: error reason `LINE_GROUP_FIELDS_DIFFER`. The items of one group must have the same `account_id`, `date` (the same instant), `title` and `operation_code`; otherwise every item of the group is `422` on each field that differs, keyed `transactions.<i>.<field>`, and nothing is written.
    changed: the in-batch operation code rule is per line. The items of one group may share a code; two lines with one code on one account are still `DUPLICATE_IN_REQUEST`, and a code already on the account is the `409` (`OPERATION_CODE_EXISTS`) keyed by the group's first item.
    changed: *Transactions (Ledger)* → *Bank lines* names a batch `line_group` beside `POST /transactions/{id}/split` as a way a line comes to hold several transactions.
  086a35cfb55a35e2  2026-10-16
    changed: `POST /transactions/import` compares the file's rows with the ledger's bank lines instead of its transactions. A line split into parts is recognised by its code, or by its total on its account and exact day, like a line held by one transaction, so re-importing a split line matches it and adds nothing. *POST /transactions/import* → *Bank lines, not rows* and *Matching* describe it.
    changed: titles no longer take part in matching: `same_day` claims a line with the same account, exact day and a total of the same direction and amount, whatever its title. An edited title is still recognised.
    removed: the `adjacent_day` rule and its `rule` value. A row one day off its ledger line is `new`; `day_mismatches` shows the leftover line on its own day when that day is inside the account's range.
    changed: on a match, the apply writes the bank's title onto every part of the line whose title differs; an old title moves into an empty description, otherwise it is dropped. A row without a title writes none. This and the code backfill now reach lines inside a completed reconciliation; *PUT /transactions/{id}* → *Field locking* names the import as the one exception. Each changed part gets one `updated` activity entry.
    changed: a `matched` row carries `bank_line_id` (the line it matched) instead of `ledger_id`, and a new key `retitled` (`true` when the bank's title is written onto the line, `false` when not, `null` on other outcomes). `backfill_code` is the code written onto the line.
    removed: `excess`. Added: `day_mismatches`. For each account, every day from its first to its last file date, inclusive, days with no file row included (file total `0`), whose signed total differs from the ledger's after the import is reported, with `file_net_cents`, `ledger_net_cents`, `unmatched_rows` (file row indexes) and `unclaimed_lines` (`{bank_line_id, transaction_ids}`).
    added: `counts.retitled`.
    changed: the apply re-checks every match while holding the matched lines. A line that another request split, deleted or changed so that it no longer qualifies since the import read the ledger makes the apply `409 CONFLICT` keyed `rows.<index>` (`CONCURRENT_CHANGE`), writing nothing; it used to refuse only when a code backfill's target was gone. *Concurrency* says so.
  5c5ae48b4583046f  2026-10-16
    changed: `PUT /transactions/{id}` sending `title`, `date`, `account_id` or `operation_code` on a transaction whose bank line holds several parts writes the value onto every live part of the line, in one write. It used to change only `{id}` (and, for `operation_code` and the account, the line). Each other part that changes gets its own `updated` activity entry and a `version` bump; a part that already has the value is untouched. The response is still `{id}`. *PUT /transactions/{id}* → *Line fields* describes it.
    changed: such a `PUT` checks *Field locking*, *Opening balances stay put*, *Reconciliation assignment* and *Sealed periods* on every part it would change, and writes nothing if one refuses. A refusal caused by another part keeps the key the request sent and the usual reason (`LOCKED`, `ASSIGNED_TO_RECONCILIATION`, `SEALED_PERIOD`, `OPENING_BALANCE_ACCOUNT_FIXED`); its message names that part's id. `reconciliation_id` in the body settles `{id}` alone: moving a line to another account while another part is in a draft reconciliation is `422` `ASSIGNED_TO_RECONCILIATION` until it is unassigned, and `LOCKED` while it is in a completed one.
    changed: `amount_cents`, `category_id`, `description`, `hashtag_ids` and `reconciliation_id` still change only `{id}`. *Bank lines* says which fields are the line's and which are each part's.
    changed: `POST /transactions/import` apply is `409 CONFLICT` keyed `rows.<index>` (`CONCURRENT_CHANGE`), writing nothing, when another request deletes or splits a transaction it matched for a code backfill while it runs; send it again. It already declared `CONCURRENT_CHANGE`. *POST /transactions/import* → *Concurrency* says so.
    changed: wording only. `SPLIT_LINE_PARTS_DIVERGE` says to send the account and date on one part with `PUT /transactions/{id}`. The `@Pendiente` paragraph in *Categories* lists `POST /transactions/{id}/split` among the writes that can send `RESERVED_NAME_HELD` and `CONCURRENT_CHANGE`. *Aggregate exceptions* item 9 says a line change logs every part it changes.
  a55cc4c271a45287  2026-10-16
    added: `POST /transactions/{id}/split`. It splits the bank line a transaction belongs to into parts: `{"parts": [...]}`, 2 to 500, the complete new set of the line's parts, each with its own `id`, signed `amount_cents`, `category_id`, `description` and `hashtag_ids`. Every live transaction on the line is deleted and the parts are created on the same line, with its account, date and operation code and the title of the transaction named by `{id}`; the same request re-splits a line or splits one of its parts. The parts' signed sum must equal the line's current total. A split is allowed inside a completed reconciliation, a sealed period and on an archived account, and every part joins the line's reconciliation. A line whose transactions are on different accounts or dates, or in different reconciliations, is refused. Returns `201` with `{"parts": [...]}`. *POST /transactions/{id}/split* describes it.
    added: four error reasons, `SPLIT_TOTAL_MISMATCH`, `SPLIT_RECONCILIATION_MIXED`, `SPLIT_LINE_PARTS_DIVERGE` and `OPENING_BALANCE_NOT_SPLIT`. *Error reasons* describes each.
    changed: *Bank lines* no longer says every line holds one transaction; a split puts several on one line. *Sealed periods* names the split as the one way to create a transaction inside a sealed window. *Aggregate exceptions* item 9 says a split leaves the line unchanged. *Field locking*, `DELETE /transactions/{id}` and `POST /reconciliations/{id}/complete` name the split as the one structural change allowed on a transaction in a completed reconciliation. *Transactions (Ledger)* says a split adds no fields to a transaction.
  1a064b29a1a77b01  2026-10-16
    changed: *Transactions (Ledger)* → *Bank lines*. A bank line stores no figures of its own: its day, direction and total are always those of its transactions, so editing a transaction changes them. It used to keep the day, direction and amount its transaction had when it was created. No request or response changes.
  d09030c7f3719106  2026-10-16
    added: `bank_line_id` on every transaction response: `GET /transactions`, `GET /transactions/{id}`, `POST /transactions`, `PUT /transactions/{id}`, `DELETE /transactions/{id}`, `POST /transactions/batch` and `POST /accounts/{id}/opening-balance`, and in transaction entries of the activity log written from now on. It is the id of the transaction's bank line, the engine's record of one bank movement, minted by the engine and never `null`. Every transaction belongs to exactly one line, and today every line holds one transaction; every existing transaction has a line of its own. *Transactions (Ledger)* → *Bank lines* describes it.
    changed: `operation_code` is stored on the transaction's bank line. What a client sends and reads is unchanged: the same field on the same requests and responses, the same trimming, the same `409` (`OPERATION_CODE_EXISTS`), the same reconciliation lock and the same import backfill.
    added: *Aggregate exceptions* item 9: a bank line has no activity entries of its own; the transaction's entries carry `bank_line_id` and `operation_code`.

fields the tests still expect, that the engine no longer has:
  excess, file_count, ledger_count, ledger_id, unclaimed_ledger_ids
  (test_bank_import.py, test_tui_bank_import.py)
```

- **A.** Make catching up the next spec now: the bank import's match keys, `day_mismatches`,
  and recording the new version. The split and `line_group` work feeds the official-migration
  spec's task 2.
- **B.** Wait until the engine coders finish the split-line work they are on today, then catch
  up once.
**Recommended:** B, because the contract moved six times today and is likely still moving; one
catch-up at the end avoids redoing it. Until then the bank-import door may misread matches.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **A bank import's 409 names the engine's row key, not the file line.** A refused
  `POST /v1/transactions/import` maps `rows.<i>.*` keys to file lines only on a 422
  ([bank_import.py](../expense/tui/screens/bank_import.py), `row_refusals` in
  [bank_import/engine.py](../expense/bank_import/engine.py)); a 409 keyed
  `rows.<i>.operation_code` or `rows.<i>.id` shows the raw key, though its next-step line is
  right. It changes what the screen shows, so it needs a mockup first.

- **The guard allows a practice-engine start from a subfolder of the engine checkout.** It checks
  the interpreter word `.venv/bin/python`, not that the command runs from the checkout's root
  ([guard.py](../.claude/hooks/guard.py)); either check the folder or list it under the
  docstring's limits, with a test.

- **The guard allows a practice-engine start with only one of the two database URLs.** The engine
  coders' rule is that `SUPABASE_DB_URL` and `ADMIN_DB_URL` are both set on the start command,
  every time; the guard accepts either one alone and leans on the engine refusing to start
  ([guard.py](../.claude/hooks/guard.py)). Require both, with a test.

- **The app reads its settings file on every engine call.** `load_usable` at launch, then about
  25 `ensure_loaded()` calls ([reads.py](../expense/reads.py), [app.py](../expense/tui/app.py),
  the screens), so the app cannot take its settings as a pipe and an agent cannot point it at
  the practice engine without the key reaching a file. Load the settings once at launch and hand
  them to every screen; then the pipe form in [runtime.md](runtime.md) works for the app.

- **The bank import works out a sign from `transaction_type`.** `excess_groups` flips the sign of
  the import response's `excess` rows from their `transaction_type`
  ([bank_import/engine.py](../expense/bank_import/engine.py)), a client-side copy of the engine's
  sign rule. Check whether `POST /v1/transactions/import` can answer signed; if it cannot, write
  an engine ask for a signed `excess`, and delete the flip once it lands.

- **A test docstring tells history.** `test_tui_reconciliations.py` line 157 says "`date_start`
  orders the batch now"; state it in the present tense
  ([test_tui_reconciliations.py](../tests/unit/test_tui_reconciliations.py)).

- **Every thread worker hands back through `call_while_attached`.** A worker whose screen is
  popped or the app closing still runs its callback, which then queries pruned widgets
  ([tui.md](tui.md) "Async/workers"). `SectionScreen._load` and the LOG bar use the guard; about
  20 hand-backs still call `self.app.call_from_thread` directly: `_base.py` (`_execute_write`),
  `_growing.py`, `reconciliations.py`, `home.py`, `bank_import.py`, `transactions.py`,
  `edit_form.py`, `create_forms.py`, `setup.py`, `app.py`. Move them, checking first whether a
  write's `on_success` must still run after a dismiss, and add a guard in
  `test_suite_hygiene.py` that refuses a raw `call_from_thread` in `expense/tui/screens/`.
- **An amount typed with a dot for thousands is misread.** `parse_amount` drops every comma, so
  `13.853,20` is saved as 13.85 on every amount field. The owner chose (2026-10-15): every amount
  field refuses an amount whose comma comes after its dot, with the field's usual "can't read
  that" note ([quickadd/money.py](../expense/quickadd/money.py)).
- **The colour line on an edit screen starts on the colour the row already has.** Every other
  line starts on its current value; the colour line starts on the first swatch (a category) or
  on nothing (an account), so `enter` there turns a category blue and shows an account's colour
  as gone ([create_forms.py](../expense/tui/screens/create_forms.py)). Owner's pick
  (2026-10-15): it starts on the current colour, so `enter` keeps it.
- **The bulk `c` pick lists categories in the engine's order.** `_picker_options` moves
  `@Pendiente` to the end ([transactions.py](../expense/tui/screens/transactions.py)); the
  owner's pick (2026-10-15) is the order the engine sends, unchanged.
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft, deferred): [specs/official-migration.md](specs/official-migration.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.
- **`PickerModal` carries rows but is still a modal.** A surface carrying rows should be a
  pushed screen (the bulk `c`/`b`/`h` picks). The other modals (`HelpModal`, `PromptModal`,
  `DiscardStagedModal`, `ConfirmModal`) are short questions and stay modals. **[UI]** — the
  replacement needs drawing.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside the TUI
  ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html), which
  also records the ⌘E conflict). Convenience, not access: `+` opens the LOG bar inside the app.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
