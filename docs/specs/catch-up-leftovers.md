# Leftovers of the bank download and closing catch-up

**Status: draft, for the owner to rewrite or approve; questions 1 and 2 wait on the owner. Its tasks
are drafted when the owner names it the current spec.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Found while the catch-up of the engine's hand-off of 2026-10-26 sent bank downloads whole, showed
what a statement's close flags and took a card's other account from the engine (done on
2026-10-26), not fixed there:

- **Old engine words still quoted.** The `SEALED_PERIOD` sentence "The date falls inside a
  completed reconciliation's period." is still quoted in [tui.md](../tui.md),
  [test_grouped_refusals.py](../../tests/unit/test_grouped_refusals.py) and
  [test_tui_log_bar.py](../../tests/unit/test_tui_log_bar.py); the engine now sends "Period … is
  sealed by completed reconciliation '…'. Revert it to draft to change anything inside it." The
  first case of the tick-refusal test in
  [test_tui_reconcile_detail.py](../../tests/unit/test_tui_reconcile_detail.py) sends a reason
  the engine does not have, `PERIOD_SEALED` ("Period is sealed."); its reason is
  `SEALED_PERIOD`, and a tick is never refused for sealing.
- **A completed statement's footer offers keys that do not act there.** On a completed
  statement the footer still shows `c Complete` and `d Delete`; the picked mockup of the flagged lines draws
  the statement after `esc` as `esc Back  r Refresh  u Revert  f Flagged  ? Keys`
  ([expense-world-statement-flagged-lines.html](../mockups/expense-world-statement-flagged-lines.html)).
- **The practice-data cleaner speaks of one practice user.**
  [clean_practice_user.py](../../scripts/clean_practice_user.py) takes its key only from
  `EXPENSE_PAT`, and [runtime.md](../runtime.md) "Leftovers" says it cleans "the practice user";
  a leftover on the reserved-names practice user is cleaned by passing that user's key as
  `EXPENSE_PAT`, which no doc says.
- **Small things in the code and tests:**
  - The helper that draws the "no batch" list's `!` is still named `blocking_windows`, and its
    local `blocked`, though the mark now means "dated inside a statement", and the
    `unfiled_rows` docstring still says "the engine is the authority at close time", though the
    close decides nothing about these lines
    ([reconciliations.py](../../expense/tui/screens/reconciliations.py)).
  - [test_reserved_name_held.py](../../tests/contract/test_reserved_name_held.py) builds its
    download's header and body by hand, where the contract conftest's shared `download_body` and
    `CURRENT_HEADER` do it.
  - Found while the sheet import went through the engine (2026-10-27): the batch helper keeps
    what only the old sheet import used. `chunk_size`, `require_sendable_chunk_size` and the
    `engine_text` default in [batch_write.py](../../expense/batch_write.py) serve no caller but
    the tests, since the LOG bar always passes its own; and a test docstring in
    [test_batch_write.py](../../tests/unit/test_batch_write.py) calls the default "the
    importer's". The comment above `_ENVELOPE_ERRORS` in [errors.py](../../expense/errors.py)
    says EngineError is a branch in `render()`, where it is in `json_body` and `exit_code_of`.
    Two comments in [import_cmd.py](../../expense/commands/import_cmd.py) carry "pick 2 A" tags
    instead of saying what they mean. And
    [test_tui_setup.py](../../tests/unit/test_tui_setup.py) keeps the old "openpyxl is required
    for `expense import`" words as a guard's fixture text.
- **Mockups that draw old words:** `expense-world-split-transaction-screen.html` (a part's amount
  stating both totals), `expense-world-edit-part.html` ("Another part of this bank line …"),
  `expense-world-grouped-refusals.html` (the old sealed sentence) and
  `expense-world-import-door.html` ("not a BCP bank file", and a movement count on its account
  list) in [mockups/](../mockups/). `expense-world-import-report.html` still draws the
  `Before 2026` and `Couldn't read the row` rows the app no longer shows. And the
  "u · the question" pane of `expense-world-card-statement.html` reads "Unlocks their
  transactions and balances. The order stays."; the app asks "Unlocks the assigned transactions
  and this batch's balances." ([reconciliations.py](../../expense/tui/screens/reconciliations.py);
  found while tidying the engine's words' leftovers, 2026-10-27).

- **Found while catching up with reading bank lines by their ids (2026-10-27).** The comment
  over `UNFILED_FILTER` in
  [reconciliations.py](../../expense/tui/screens/reconciliations.py) says newest first is the
  engine's one order for bank lines; the engine also takes `sort=date_asc` now, so it is only
  the order when no `sort` is sent. And `fetch_bank_lines_by_ids` in
  [reads.py](../../expense/reads.py) splits the ids by the engine's largest page, a separate
  rule from the most ids one read takes (contract: GET /v1/bank-lines, "At most 200 ids"); both
  are 200 today, but each rule wants its own name. Whether the "no batch" list now lists oldest
  first is question 2.

## What it must do

1. **The tests and docs quote the engine's current words**: the sealed sentence, and the
   tick-refusal test's reason.
2. **A completed statement's footer shows only the keys that work on it**, as question 1 decides.
3. **The cleaner's doc says how to clean either practice user.**
4. **The small things are tidied**: the `!` helper named for what it marks, the hand-built download body using the shared helpers, the batch helper keeping only what a
   caller uses, the stale comments and tags said plainly, the "no batch" comment saying
   newest first is the engine's order when none is asked for, and the ids read split by the
   engine's own bound on ids.
5. **The six mockups draw the words the app shows**, or are deleted with their links if they
   back no open work (the rule in [todo.md](../todo.md) "Mockups that back no open work").
6. **The "no batch" list lists in the order question 2 decides.**

## How the owner knows it is done

1. On a completed statement, the footer shows what question 1 decided.
2. A statement's "no batch" list shows its lines in the order question 2 decided.
3. The unit suite, the live suite and the drift check pass.

## Questions for the owner

1. **A completed statement's footer.** On a completed statement, `c Complete` only says
   "Already completed.", and `d Delete` asks, then shows the engine's refusal (a completed
   statement is reverted before it is deleted). The flagged lines mockup drew neither.
   - **A.** Show neither, as the mockup drew it.
   - **B.** Drop `c` only; `d` stays, and the engine's refusal says to revert first.
   - **C.** Keep the footer as it is.

   **Recommended:** B: `c` does nothing there, while `d` leads you to the engine's own words on
   what to do, and the app guesses no engine rule.

2. **The order of the "no batch" list.** It lists an account's lines in no statement newest
   first, because the engine could list bank lines no other way. Since 2026-10-26 the engine
   can list them oldest first too, as the flagged lines already show.
   - **A.** Keep newest first: the lines you bought last are on top.
   - **B.** Oldest first, as a bank statement and the flagged lines read: the oldest leftovers,
     most likely forgotten, are on top.

   **Recommended:** B: the list is checked against a statement, which reads oldest first, and
   the flagged lines already do.

---

## Tasks

Drafted when the owner names this the current spec.

## Found along the way
