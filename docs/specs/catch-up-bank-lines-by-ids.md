# The app catches up with the engine: flagged lines read in one call, oldest first

Catches up to contract `46e2fdf6e11d7548`, from `6687b18541c068e3`: the engine's hand-off of
2026-10-26, "The bank-line list reads several lines by their ids in one call, and lists oldest
first on request", covering `6687b18541c068e3`, `872eff6cfffc787a`, `7a90cdeb492d883e` and
`46e2fdf6e11d7548`. The same day the engine declined the sheet import's two asks, with no
contract change; that answer is in
[sheet-import-through-the-engine.md](sheet-import-through-the-engine.md).

**Status: approved by the owner on 2026-10-27, running.** When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The engine changed on 2026-10-26:

- **It reads several bank lines in one call**, the ask this client raised:
  `GET /bank-lines?ids=<id>,<id>,…` (contract: GET /v1/bank-lines). The screen of the lines a
  statement's close flagged reads them one call per line today, and drops the ones the engine
  no longer has by itself ([reads.py](../../expense/reads.py) `fetch_live_bank_lines`).
- **It lists bank lines oldest first on request**, `?sort=date_asc`. The flagged lines' screen
  sorts them oldest first by itself today (`flagged_order` in
  [reconciliations.py](../../expense/tui/screens/reconciliations.py)).
- **A future-dated import row's refusal now names its row**: "Row 16: Must not be in the
  future." where it read "Must not be in the future.". The bank import already shows a refusal
  that names its row in the engine's words alone, so that line now reads
  `! Row 16: Must not be in the future.` where it read `! rows.16.date: Must not be in the
  future.`. The unit tests' fake engine still sends the old words.
- **One live test fails** since the move: it expects the engine to refuse oldest first beside a
  statement, which it now takes
  ([test_statement_order.py](../../tests/contract/test_statement_order.py)).
- Two pieces of wording changed with no rule changing: the refusal for sending
  `unassigned_in_period_of` with another filter, and four pointers to *Sealed periods*. No code
  of this app quotes either.

Until this client records the new version, the version check fails and no other work starts.

## What it must do

1. **The flagged lines' screen reads its lines in one call**, oldest first as the engine orders
   them, and reads them again the same way after an edit or a delete; a line the engine no longer
   has drops out. The app reads no line one at a time and sorts none itself. Nothing you see
   changes.
2. **The tests quote the engine's current words** for a future-dated import row, and the docs
   say the bank import's line for it shows the engine's words alone.
3. **Live tests prove each change against the practice engine**: reading lines by their ids,
   oldest first, and a future-dated row naming its row on the bank import and the sheet import.
4. **The app records that it has caught up to `46e2fdf6e11d7548`.**

## How the owner knows it is done

1. In the app against the practice engine, completing a statement with leftover lines shows them
   flagged, oldest first, and deleting one drops it from the list.
2. The unit suite, the live suite and the drift check pass, the version check included.

## Questions for the owner

None. Nothing you see changes but the bank import's line for a future-dated row, which now shows
the engine's words, row number included.

---

## Tasks

Approved by the owner on 2026-10-27.

2. **The engine's current words for a future-dated row.** The unit tests' fake engines send
   "Row <n>: Must not be in the future." on an import row
   ([test_tui_bank_import.py](../../tests/unit/test_tui_bank_import.py),
   [test_sheet_import_engine.py](../../tests/unit/test_sheet_import_engine.py)), the bank
   import's refusal test expects that line alone, and [tui.md](../tui.md) no longer gives a
   `FUTURE_DATE` as words that name no row. A refusal whose words name no row still keeps its
   key.
3. **Live tests of the new reads, and the version recorded.** The bank-line list by `ids`: the
   live lines among the ids sent, in the list's shape, deleted and unknown ids left out, `/count`
   agreeing, combined with `account_id`, refused beside `unassigned_in_period_of` and over 200
   ids. `?sort=date_asc`: the newest-first list in reverse, beside a statement too, its cursors
   its own. The failing case in
   [test_statement_order.py](../../tests/contract/test_statement_order.py) follows the
   contract. A future-dated row on the bank import and the sheet import names its row. The
   contract version is recorded with `--record-version` at `46e2fdf6e11d7548`, and the fixture
   check passes.

## Reply to the engine

Written into [to-engine/](../to-engine/) when the spec is done, with the tester's results.

- **Range:** `6687b18541c068e3` to `46e2fdf6e11d7548`, the hand-off "The bank-line list reads
  several lines by their ids in one call, and lists oldest first on request".
- **The engine's "Done when" checks to report on:** the close's review screen draws its flagged
  lines from one `GET /bank-lines?ids=…` call and drops deleted lines on re-read, without a
  per-id loop; the TUI's contract snapshot is at `46e2fdf6e11d7548`.
- **Contract problems found:** `review_lines` states no bound, while `ids` takes at most 200, so
  a close flagging more lines needs several reads, ordered only within each.
- **The asks it closes:** "The bank-line list reads several lines by their ids in one call".

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
