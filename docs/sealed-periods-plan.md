# Sealed periods reach the user — CLI/TUI plan (drafted 2026-09-20)

> **2026-09-23:** everything here is built. The one step left, the contract run (§10 step 7),
> is Phase 12 of [engine-uptake-plan.md](engine-uptake-plan.md); this file is deleted then.

**Status: reviewed and settled 2026-09-20, not yet built.** This is ask **1 of 4**
on the 2026-09-20 queue ([todo.md](todo.md) "Now"). Every decision in §7 is
answered; the rest is settled by the engine's contract and recorded here so a
fresh session can act on it with no conversation history.

**The [UI] gate is closed.** Three screens were drawn as a walkable prototype,
[expense-world-reconciliation-flow.html](mockups/expense-world-reconciliation-flow.html)
(with the static panes in
[expense-world-sealed-period-refusals.html](mockups/expense-world-sealed-period-refusals.html)),
and the owner picked **C**, **E** and **F** on 2026-09-20. Two of the three went
against the recommendation in the mockup — recorded in §7 with what that costs,
because a pick made against a written argument is the kind that gets
second-guessed later by someone who only finds the argument.

**Why this one first.** It blocks the owner's next real task: creating roughly 24
reconciliations for 2026 by hand and closing them month by month, against windows
the engine's plan §2.3 already worked out. Every one of those closes can now be
refused for a reason this repo renders as a bare validation error.

The engine half shipped 2026-09-20 (its E1–E4) and **its rules live in
`engine-spec.md`**, not in a plan file — *Sealed periods* under Transactions, and
the window contract plus the close check under Reconciliations. Read the spec for
behaviour; read [the engine's plan](../../expense_world_engine/docs/file-import-plan.md)
§2 for the measurement the design rests on.

When this ships, its whys move to [decisions.md](decisions.md), any residue to
[todo.md](todo.md), and **this file is deleted** — per the "each fact has one
home" rule.

---

## 1. What the engine now does

Four rules, all live on `127.0.0.1:8000` since the 2026-09-20 restart.

**A completed reconciliation with both dates set seals its window.** No
transaction may come to exist on that account with a date inside
`[date_start, date_end]`, inclusive, resolved as calendar days in the user's
`display_timezone`. Six doors return `422 VALIDATION_ERROR`:

| Door | `fields` key | Reachable from this repo |
|---|---|---|
| `POST /transactions` | `date` | `transactions create`, TUI create form |
| `POST /transactions/batch` | `transactions.<index>.date` | **`import bank`, the LOG bar save** |
| `PUT /transactions/{id}` moving `date` in | `date` | `transactions update`, TUI edit form |
| `PUT /transactions/{id}` moving `account_id` in | `account_id` | `transactions update`, Home's bulk `b` |
| ~~`POST /transactions/{id}/restore`~~ | `date` | *Route deleted by the engine 2026-09-23 (Phase 6.1)* |
| `POST /accounts/{id}/opening-balance` | `date` | `accounts opening-balance` |

The message names the sealing period's days and name. Only a **COMPLETED,
non-deleted, fully-dated** reconciliation seals; a draft is a plan, a
soft-deleted one has been withdrawn, a half-dated one has no window.

**`complete` gained two preconditions and one report.**

1. Both dates required — `422` naming whichever of `date_start` / `date_end` is
   missing.
2. No transaction dated inside the period may be unassigned — `422` with
   `fields: {"transactions": "N transaction(s) dated inside this period are not
   assigned to any reconciliation. Assign or delete them first."}`. It asks
   whether the row is filed under **any** reconciliation, not this one, because
   a card statement is cut on the posting date while the ledger stores the
   purchase date, so two consecutive statements can bill the same day.
3. `warnings: list[str]` — always present, empty when clean. It carries exactly
   one thing: a stretch of days between the previously completed period on that
   account and this one that **no completed period covers**. Reported, never
   refused — skipping a period is legitimate, doing it silently is not.

> ⚠️ **The two `complete` 422s share one `fields` key.** The pre-existing
> "At least one transaction must be assigned." and the new "N transaction(s)
> dated inside this period…" both arrive as `fields["transactions"]`. Anything
> that tells them apart has to read the **message**, not the key. This is the
> single most likely thing to get wrong here.

**`create` / `update` validate the period.** `date_start ≤ date_end` (`422`
naming `date_end`), and no two periods on one account may share a calendar day
(`422` naming `date_start`, with the clashing period's name and days in the
message). Both are judged on the window the row will **have**, not on the keys
the request sent. Checked against drafts too, and scoped per account.

**Unchanged, and worth knowing:** `difference_cents` still does not block
completion; completing an already-completed batch is still a silent `200` no-op
that short-circuits before every check; `revert` carries **no** `warnings` key,
because unsealing a window cannot make the ledger incoherent.

## 2. What this repo does today (audited 2026-09-20)

- **`reconcile complete`** ([reconcile_cmd.py](../expense/commands/reconcile_cmd.py))
  catches `422`, scans `error_haystack(err)` for `"transaction"` plus one of
  `"no "` / `"empty"` / `"at least"`, and prints `_COMPLETE_EMPTY_HINT`. It then
  emits the body (`--json`) or renders the record. **It never looks at
  `warnings`.** The haystack scan does *not* fire on the new unassigned-rows
  wording — correct, since that hint would be wrong, but it leaves the new case
  with no hint at all.
- **`_print_warnings`** exists once, in
  [transactions_cmd.py](../expense/commands/transactions_cmd.py), private to that
  module and called from exactly one place: `transactions restore`. *(That command was deleted with the engine's restore, 2026-09-23; `reconcile complete` is now the only caller.)*
- **The TUI cannot show a warning at all.** `EngineWriteMixin.run_write`
  ([_base.py](../expense/tui/screens/_base.py)) calls `client.post(...)` and
  discards the return value; `on_success` takes no arguments. Five callsites
  across four screens, four of which pass `on_success`.
- **`reconcile create`** already requires `--date-start` and leaves `--date-end`
  optional. `update` passes both through `build_update_payload`.
- **The wall's two live doors** are `import bank` and the LOG bar save, both
  through [batch_write.py](../expense/batch_write.py). Its singleton retry
  re-posts a refused chunk one row at a time, so a per-row `422` already lands
  in `outcome.errors[index]` as the engine's own formatted message — which
  already names the period. **Nothing is lost today; nothing is pre-empted
  either.**

## 3. S1 — the gap report reaches both surfaces

**Flat.** `reconcile complete` prints the warnings after the record, the way
`transactions restore` did (deleted 2026-09-23). `--json` needs no change: it emits the engine body
verbatim, so `warnings` is already there.

**Shared, not copied.** `_print_warnings` moves to
[_resource.py](../expense/commands/_resource.py) as a public helper and both
commands call it. A second copy in `reconcile_cmd` would be exactly the
duplication CLAUDE.md's "One copy of everything shared" forbids.

**TUI.** `run_write` has to stop throwing the response body away — see decision
**D1**. The Reconciliations detail screen then surfaces the warnings on a
successful complete. A toast is the obvious vehicle; a gap is not an error, so
`severity="warning"`, and it must not replace the success feedback.

> **Why this is not cosmetic.** An uncovered stretch is the one place neither the
> close check nor `difference_cents` can see into. The close check only inspects
> days *inside* a window. `difference_cents` is `(ending − beginning) − sum(assigned)`
> and both balances are typed off the statement, so an unassigned phantom in a
> gap never enters the arithmetic at all. It corrupts only the account's computed
> balance, which nothing compares against a statement. Drop this message and the
> gap is invisible forever.

## 4. S2 — the two new refusals on `complete`

Both are 422s the user will meet during the 2026 backfill, and both deserve to
say what to do next rather than only what went wrong.

**Missing dates.** The engine names the field. The hint points at the fix:
`expense reconcile update <id> --date-end <YYYY-MM-DD>`.

**Unassigned rows inside the period.** The engine gives the count. The hint gives
the query that lists them, which already exists and needs no new flags:

```
expense transactions list --account-id <id> --unreconciled \
    --date-from <date_start> --date-to <date_end>
```

That is the ledger's orphan check as `engine-spec.md` describes it, and an empty
result is the statement that the period holds nothing unaccounted for.

To build that command line the CLI needs the reconciliation's `account_id` and
dates, which the 422 does **not** carry — see decision **D2**.

## 5. S3 — the two new refusals on `create` / `update`

Neither needs machinery: the engine's message already names the clashing period
and its days, and the error envelope renders `fields`. What they need is for the
CLI not to *bury* them, plus two hints:

- inverted range → "`--date-end` must not be before `--date-start`."
- overlap → point at `expense reconcile list --account-id <id>`, which since the
  de-chaining sorts by `date_start ASC` and so shows the neighbours in order.

The owner is about to type 24 of these against the windows in the engine plan
§2.3, where month N ends the day before statement N+1's earliest purchase date.
Off-by-one overlaps are the expected mistake, not an exotic one.

## 6. S4 — the wall, named at the two doors that can hit it

The importer's real answer is now the engine's: since 2026-09-25
`POST /transactions/import` reports a row inside a closed period as `sealed` and never
writes it, and [engine-uptake-plan.md](engine-uptake-plan.md) Phase 10b shows those rows
as a visible block. That replaced ask 2's **C5** pre-filter (2026-09-26); this ask does
not duplicate it. The `import bank` bullet below describes the importer before Phase 10b.

What belongs **here** is the floor under it, for the rows a pre-filter misses and
for the LOG bar, which has no pre-filter at all:

- **`import bank`:** a `422` on a row already surfaces per row via `batch_write`.
  Confirm with a test that the period name survives into the printed line, and
  that `report.ok` goes false so the run exits 1.
- **The LOG bar:** a refused row must say which period refused it, against the
  staged row, without discarding the rest of the batch.

## 7. Decisions, settled 2026-09-20

**D1 — how the TUI gets the response body.** `EngineWriteMixin.run_write` discards
it, and S1 needs it. **Resolved: a new optional `on_response: Callable[[dict], None]`,
called before `on_success`.** Purely additive — the four existing `on_success`
callsites do not move, and the one screen that cares opts in. *Rejected:* giving
`on_success` an optional `body` argument (every screen pays for one screen's
need); stashing the body on the mixin for `on_success` to read (an `on_success`
reading a body left by a previous write is a silent bug waiting to happen).

**D2 — the unassigned-rows answer.** Two surfaces, two answers.

- **TUI: pane E**, the shared results screen — not a shell command. The owner's
  correction, and the right one: "in the TUI the answer is not a command to copy,
  it is the rows."
- *(Superseded 2026-09-23: `GET /reconciliations/{id}` is gone and the owner accepted the
  generic hint, [engine-uptake-plan.md](engine-uptake-plan.md) Phase 5.)*
  **Flat CLI: fetch and print a command that works.** `GET /reconciliations/{id}`
  on this 422 only, to fill in the account and both dates, so the printed line is
  runnable rather than a template with three holes in it. One extra read on a
  path that has already failed. *Rejected:* printing `--account-id <id>` and
  making the user look all three up.

**D3 — before completing: pane C, drawn as a full screen.** Pressing `c` with
unticked rows in the window opens a **pushed screen** listing them, whose one
action is **“tick all N, then complete”**; `esc` returns to the checklist.

> **It was drawn as a box and redrawn the same day.** The owner's standing rule,
> set 2026-09-20 and recorded in [tui.md](tui.md) §2: *new surfaces are full
> screens, not modals* — anything carrying rows is a pushed `Screen`. With
> nothing unticked there is nothing to list, so `c` still raises the plain
> `ConfirmModal` yes/no; that is a **question**, not content, and cards are what
> questions are for.
>
> **Consequence: D3 and D2's TUI half are one screen.** C lists the blocking rows
> *before* the write; pane E lists them *after* the engine refuses anyway. Same
> rows, same layout — build it once, entered from two directions. The second door
> stays reachable because the engine remains the authority: a row written
> elsewhere while the screen sat open still produces a refusal C never saw.

> ⚠️ **This deliberately reverses a settled non-goal.** “Bulk assign everything
> shown on the reconciliation screen” was declined 2026-09-19
> ([file-import-plan.md](file-import-plan.md) §8) because the owner is doing the
> 2026 backfill by hand — with the note *revisit if monthly closing proves
> tedious*. Twenty-four closes is that moment, and the owner reversed it knowingly
> after the mockup argued the other way. **What it costs:** the button assigns
> rows the user has not individually reviewed, which is precisely what the
> non-goal protected against. Recorded so the reversal reads as a decision rather
> than an oversight.
>
> **What it implies for the code:** “Tick all N, then complete” is *N+1 writes*,
> not one — N × `PUT /transactions/{id}` then `POST …/complete` — so a partial
> failure is possible and must not report a completion that did not happen.

**D4 — `date_end` becomes required at create**, on both surfaces (`reconcile
create` and the TUI new-batch form). The engine still permits a half-dated draft;
this is a caller-side choice, in the same family as `debit_as_negative`. Its cost
is that a batch can no longer be opened before the statement arrives — accepted,
because a half-dated completed period seals nothing and the CLI has no way to
read the dates off a statement (the EECC are PDFs this repo never opens).

**D5 — the bulk refusal screen: pane F, full screen.** Reached from a refused
bulk edit in the ledger. It shares its layout with D3's screen — a list of rows
with a reason column — but not its content: this one carries **which period
refused each row**, which is the column a modal could not fit and the reason
[tui.md](tui.md) §2's full-screen rule exists. **`r retry` is dropped** — refused rows already stay selected after a bulk
write, so pressing the same key again *is* the retry, and retrying a row a sealed
period refused would simply be refused again.

**Scope note.** Of the three bulk keys, only `b` (move account) can be refused by
these rules: `c` (category) and `h` (hashtags) stay legal inside a sealed period
by design. Today a bulk refusal raises **one ten-second error toast per row** —
eight refusals is eight stacked toasts — which is the concrete problem this
screen solves.

## 8. Non-goals

| Not doing | Why |
|---|---|
| A client-side seal check before any write | The engine is the authority; re-deriving windows client-side is exactly the "no CLI-only shortcut" rule. The importer's C5 pre-filter is a *preview* feature, not a guard |
| Caching completed windows | Same reason, plus they change under `revert` |
| A "close every month" bulk command | The owner is doing the backfill by hand deliberately; see [file-import-plan.md](file-import-plan.md) §8 |
| Surfacing `warnings` on `revert` | The engine does not send the key there, and says why |

## 9. Tests

Unit, respx-mocked, one happy path plus one error shape per command touched:

- `complete` renders a non-empty `warnings`; renders nothing extra when it is `[]`.
- `--json` on `complete` passes `warnings` through untouched.
- The two `complete` 422s are told apart **by message**, with the same
  `fields["transactions"]` key on both — the pre-existing empty-batch hint must
  still fire on the old wording and must **not** fire on the new one.
- The unassigned-rows hint prints a command line carrying the real account id and
  both dates (D2's extra read, mocked).
- `create` / `update` render the inverted-range and overlap 422s with their hints.
- A sealed-period `422` inside an `import bank` batch names the period in the
  per-row line and exits 1.
- TUI: a complete whose response carries warnings draws the `#rwarn` line and
  does **not** suppress the success path (D1's `on_response`); an empty
  `warnings` draws no line; a revert clears a shown one.

`test_command_surface.py::test_every_command_has_an_error_shape_test` covers the
second half automatically once the tests exist.

## 10. Sequence

1. ~~D1–D5 answered by the owner.~~ Done 2026-09-20; [UI] gate closed.
2. ~~`_print_warnings` → `_resource.py`; flat `complete` renders warnings.~~
   Done 2026-09-21 (`bf5ffd0`), together with step 4.
3. ~~`run_write` gains `on_response`; the Reconciliations screen shows the gap.~~
   Done 2026-09-22. **Not a toast** — the owner picked a persistent line under the
   header (pick B of
   [mockups/expense-world-gap-warning.html](mockups/expense-world-gap-warning.html)),
   and the D/E variants that would have listed the uncovered rows were dropped
   with the engine-side ask they needed. Both whys are in
   [decisions.md](decisions.md) ("The TUI sees the response body only where it
   asks for it", "The gap report is a line under the header"). What came out of
   that review and is **not** part of ask 1: a standing unreconciled view, now
   its own item in [todo.md](todo.md).
4. ~~The three hint paths (`complete` ×2, `create`/`update` ×2).~~ Done
   2026-09-21 (`bf5ffd0`), with D4's required `--date-end`.
5. ~~The two wall doors pinned by test.~~ Done 2026-09-22 — **tests only, no
   code changed**: both doors already carried the refusal, and what was missing
   was anything holding them to it. The period's *name* lives only in the 422's
   field text, so each test follows it through the chunk → singleton fallback,
   `format_error` and the per-row line: `import bank` (the batch and the
   operation-code backfill, [test_cmd_import_bank.py](../tests/unit/test_cmd_import_bank.py))
   and the LOG bar save ([test_tui_log_bar.py](../tests/unit/test_tui_log_bar.py)).
   Each also pins the half that matters more: **the other rows still land.** The
   flat `expense log` needs no test of its own — one line is one row through the
   ordinary single-row path.
6. ~~The refusal results screen (D5), used by `complete` and by the ledger's bulk
   `b`; then pane C's confirm box on top of it.~~ **Re-scoped and done 2026-09-22.**
   The screen was not built: the owner took D3/D5 apart in review and the
   replacement is smaller and better — `u` on the Reconciliations browse swaps
   the lower pane to the account's rows in no batch, `⏎` fixes one in the
   existing edit form, `d` deletes it, and the ledger's bulk refusals collapse to
   one line per reason. D3's "tick all N, then complete" is **dropped**: it would
   have sealed a month with a corrupted `difference_cents`. Mockup
   [mockups/expense-world-rows-in-no-batch.html](mockups/expense-world-rows-in-no-batch.html);
   the why and the six rejected alternatives in [decisions.md](decisions.md)
   "Rows in no batch live in the reconciliation view".
7. Contract-suite pass against the disposable engine on `:8002` — this is the
   first change written against rules no contract test has ever exercised.
