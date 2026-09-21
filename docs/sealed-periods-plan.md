# Sealed periods reach the user — CLI/TUI plan (drafted 2026-09-20)

**Status: drafted 2026-09-20, not reviewed, not built.** This is ask **1 of 4** on
the 2026-09-20 queue ([todo.md](todo.md) "Now"). Every numbered decision in §7 is
a real fork that wants the owner's answer before the code is written; everything
else is settled by the engine's contract and recorded here so a fresh session can
act on it with no conversation history.

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
| `POST /transactions/{id}/restore` | `date` | `transactions restore` |
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
  module and called from exactly one place: `transactions restore`.
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
`transactions restore` does. `--json` needs no change: it emits the engine body
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

The importer's real answer is ask 2's **C5** pre-filter: fetch the account's
completed reconciliations, drop file rows dated inside one *before* matching, and
show them as a visible skipped block. That is in
[file-import-plan.md](file-import-plan.md) §7 and stays there — this ask does not
duplicate it.

What belongs **here** is the floor under it, for the rows a pre-filter misses and
for the LOG bar, which has no pre-filter at all:

- **`import bank`:** a `422` on a row already surfaces per row via `batch_write`.
  Confirm with a test that the period name survives into the printed line, and
  that `report.ok` goes false so the run exits 1.
- **The LOG bar:** a refused row must say which period refused it, against the
  staged row, without discarding the rest of the batch.

## 7. Decisions to review

**D1 — how the TUI gets the response body.** Needed for S1; nothing else in the
app has ever wanted it.

| | Shape | Cost |
|---|---|---|
| **A** | `on_success` gains an optional `body` argument | Touches all four `on_success` callsites, or needs arity inspection — implicit either way |
| **B** *(recommended)* | A new optional `on_response: Callable[[dict], None]`, called before `on_success` | Purely additive; the four existing callsites do not move; the one screen that cares opts in |
| **C** | The mixin stores `self._last_write_body` for `on_success` to read | Cheapest to write, stateful and easy to misuse — an `on_success` reading a body from a previous write is a silent bug |

**B**, because this is one screen's need and A makes every screen pay for it.

**D2 — where the unassigned-rows hint gets the account and dates.** The 422 has
the count but not the account id or the window.

| | Shape | Cost |
|---|---|---|
| **A** *(recommended)* | `GET /reconciliations/{id}` before building the hint, only on this 422 | One extra read on a path that has already failed; no cost on the happy path |
| **B** | Print a hint with placeholders (`--account-id <id>`) | Zero cost, and the user has to go and look all three values up |
| **C** | Read the record before every `complete` | An extra round trip on every close, to serve a case that is the exception |

**A**. The failure path is where a round trip is affordable.

**D3 — does the TUI pre-check before offering `c` (complete)?** The engine refuses
a close with unfiled rows. The detail screen *already* lists the account's
unassigned transactions in range while the batch is a draft, so it holds the
answer before the key is pressed.

| | Shape | Notes |
|---|---|---|
| **A** *(recommended)* | Stay thin: press `c`, let the engine refuse, toast the message | CLAUDE.md "thin wrapper"; matches the screen's existing stance — it deliberately has no ≥1-assigned pre-guard either, for the same reason |
| **B** | Show the count in the confirm modal before completing | Kinder, but it is client-side logic re-deriving an engine rule, and a stale list would lie |

**A**, and it is also the cheapest. **If the owner wants B, it changes a screen
and therefore needs a mockup first** — flagging that rather than assuming.

**D4 — should `reconcile create` require `--date-end`?** The engine allows a
draft without one but refuses to complete it.

Recommended: **leave it optional** and say so in the help text. A draft is allowed
to be incomplete — that is the engine's own split — and forcing the date at create
time would make it impossible to open a batch before the statement arrives. The
close check is where it is caught, which is the right moment.

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
- TUI: a complete whose response carries warnings raises a warning toast without
  suppressing the success path (D1's `on_response`).

`test_command_surface.py::test_every_command_has_an_error_shape_test` covers the
second half automatically once the tests exist.

## 10. Sequence

1. D1–D4 answered by the owner.
2. `_print_warnings` → `_resource.py`; flat `complete` renders warnings.
3. `run_write` gains `on_response`; the Reconciliations screen toasts the gap.
4. The three hint paths (`complete` ×2, `create`/`update` ×2).
5. The two wall doors pinned by test.
6. Contract-suite pass against the disposable engine on `:8002` — this is the
   first change written against rules no contract test has ever exercised.
