# Decision record

Why the product is the way it is today — **including the alternatives that were rejected**, so nobody re-litigates them. Only decisions that govern current code or product live here; a decision that is undone or whose subject is deleted is deleted too (git history is the archive).

Rules for this file:

- **One home per fact.** If a decision's rationale already lives in another doc, link it there instead of copying.
- **Absolute dates, always.**
- **Present tense.** State the rule and why; no history of how it got there.
- New entry template: `## <decision> (<date>)` → **Context** / **Decision** / **Rejected** — short paragraphs; a rejected alternative only if someone would plausibly propose it again, one line each.

Decisions whose why lives elsewhere:

| Decision | The why lives in |
|---|---|
| The app is a thin wrapper / contract validator for the multi-client engine | [CLAUDE.md](../CLAUDE.md) "Product scope and role" |
| Server-first writes, no offline queue | [CLAUDE.md](../CLAUDE.md) "Tech stack" · [runtime.md](runtime.md) "Write semantics" |
| PAT auth (`ewe_pat_` prefix) | [commands.md](commands.md) "Auth model" |
| Public GitHub repo (free CI), so secrets and real ledger data never enter it | [CLAUDE.md](../CLAUDE.md) "Config isolation" |
| Sanctioned deviations from the principles | [commands.md](commands.md) "Sanctioned exceptions" |
| Rates cross the wire as integers (`rate_e8`, the rate × 10^8), so every client does exact integer maths with no float drift | (contract: GET /v1/exchange-rates) |

## What a half-written batch means (2026-08-25)

**Context.** The LOG bar saves every staged row through `POST /transactions/batch`, in chunks, via [expense/batch_write.py](../expense/batch_write.py). A batch can partly fail.

**Decision.** (1) **A successful save stays on the screen**: written rows show a `✓` and are cleared the moment the next line is staged, so the list only ever holds rows about to be written. (2) **A partial failure ticks what landed and retries only the rest.** Failed rows keep their marker and the engine's message; `ctrl+s` covers only rows without a `✓`. A refusal that holds for every further write is said once, on no row ("Missing settings stop a multi-write run"). This is safe because **`row_id` is minted at stage time and reused on every attempt** — a row whose response was lost replays as `409` with reason `ID_EXISTS` on that row's own id, which the save reads as *written*; every other `409` is a refusal (`is_own_id_replay` in [errors.py](../expense/errors.py)). (3) **`ctrl+s` never touches an unstaged line in the bar** — `↵` is the only thing that stages. (4) **The discard card's `ctrl+s save first` saves and then leaves, unless the save fails**, in which case the screen stays so the error can be read. The row's **`date` is frozen at stage time** too, so a batch saved across midnight does not change day. A saved row cannot be lifted back into the bar — correcting a written row is the edit form's job. The batch mechanics are shared with the `.xlsx` importer in `batch_write.py`, not copied: a refused chunk's named rows settle, each `ID_EXISTS` on its own id as written and every other refusal as failed, and the rest go again as one batch.

**Rejected.** *Dismiss on success* — throws away the confirmation. *Keep ticked rows until you leave* — mixes history with intent and the per-currency total stops describing the batch. *Re-send the whole list on retry* — safe, but hides a partial failure behind a wall of 409s. *Auto-stage the bar's line on save* — writes something unfinished. *Save and stay after `esc`* — the user pressed `esc`.

## Four calls for the LOG bar (2026-08-25)

**Decision.** (1) **A staged row comes back as the raw line you typed** (`↑↓` pick, `↵` lifts it into the bar) — nothing is re-rendered, so line and row can never disagree. (2) **The staged table keeps its `tags` column.** (3) **The batch totals per currency** — never adds PEN to USD: `3 to the ledger · -45.20 PEN · -96.00 USD`. (4) **A refused line's reason reuses [route.py](../expense/quickadd/route.py)'s own phrases**; one wording, one place. The date cell shows the year whenever it is not the current one, because the staged list is the echo that makes two-digit years safe.

**Rejected.** *Rebuild the line from the row* (names spelled out) — a second formatter that drifts from the parser and loses typed text. *Drop the tags column for width* — tags are half of why a line is typed. *A second, shorter wording for the reasons* — a phrase table that drifts from route.py.

## The quick-add line: one rule, shown before it is written (2026-08-25)

**Decision.** (1) **One rule**: [quickadd/route.py](../expense/quickadd/route.py) decides whether a line is accepted or refused (see "A sparse line is a ledger row"). An ambiguous name counts as no name, and the candidates are shown. (2) **The parsed row is always shown before it is written.** The grammar is forgiving (`18/8/26`, `hoy`, `$sig`) *because* the resolved row is always shown before it is committed: the LOG bar's staged list is that echo, and nothing in `expense/quickadd/` asks a second time.

**Rejected.** *Write, then echo, with `--dry-run` to look first* — the check is skipped exactly when typing fast. *Prompt only when something was inferred* — an unpredictable prompt trains you to dismiss it.

## Three quick-add grammar rules (2026-08-25)

**Decision.** (1) **Names match on "contains, anywhere"**, accent- and case-blind ([quickadd/names.py](../expense/quickadd/names.py) `fold()`, shared by every picker). An exact name wins outright, longer phrases are tried first (`#caja chica` before `#caja`); zero or several hits leave the token unresolved with its candidates for a picker. (2) **Dashed ISO dates are accepted** (`2026-08-18`) because every date field in the app takes that shape; dashes stay ISO-only, so `18-08-2026` is not a date. (3) **An unmatched `#tag` is refused, never created.**

**Rejected.** *Whole-name or starts-with matching* — fails the common case of typing the distinctive middle word. *Slash dates only* — a user who types dashes everywhere else would silently get title text. *Create unknown tags on save* — a typo becomes a permanent tag. *Swallow an unknown tag as title text* — loses it silently.

## Sign is always literal — no default-to-expense magic (2026-04-25)

**Decision.** The sign is explicit end-to-end in every UX layer: `20` is income, `-20` is expense. An amount whose sign is ambiguous gets a prompt or an error, never a guess. No exceptions.

**Rejected.** *Default an unsigned amount to expense* (offered, declined) — hidden behaviour that diverges from what the engine stores and forces the parser to infer intent.

## The TUI is the only surface (2026-10-13, owner)

**Context.** The owner uses only the TUI. A typed command calling the same Python reads, formatters and write plumbing as a screen is a second face on the same feature, built and approved a second time for a surface nobody reads. Web and iOS call the engine's HTTPS API, never this repo.

**Decision.** Every feature is built once, in the TUI. Two things are typed: `expense`, which opens the TUI, and `expense import sheet`, the door for the owner's spreadsheet. Every engine endpoint is exercised by the owner's real use of the TUI and by the live contract suite, which calls the engine directly; an engine feature with no TUI screen is exercised by the contract suite alone. Agents get no typed commands: what is done to the ledger is done by the owner, in the app. The quick-add grammar is one implementation, used by the LOG bar. A new engine capability gets its TUI screen and its contract test, and nothing typed. The repo is `PlungerBull/expense_world_TUI` on GitHub and `expense_world_TUI` as the local folder; the command is still `expense`.

**Engine features with no screen.** Activity history; exchange-rate history; editing a reconciliation's details (name, dates, balances) after it is created; updating the profile and the settings; the single-month report (Home shows the four-month grid); posting a batch of transactions in one call. They are the engine's own to keep working, and the contract suite exercises them. Adding a screen for one is new work of its own, when the owner asks for it.

**Rejected.** *Flat commands as the canonical surface beside the TUI* — every feature built, tested and approved twice. *One generic `expense api` command for agents* — an agent acting on the ledger belongs behind an MCP server beside the engine, not behind a command in this client. *Keeping every command as JSON-only for agents* — the same double build, for no reader.

## Mockup-first, and showing ≠ approval (hardened 2026-05-24)

**Decision.** Every user-facing view or table change starts with an HTML mockup in [mockups/](mockups/), and **presenting mockups is never authorization** — implementation waits for an explicit pick, even in auto-accept mode and even when a follow-up sounds like consent. A prior session's approval is not a standing license. Full rule: [CLAUDE.md](../CLAUDE.md) "Mock every screen before building it".

**Rejected.** *Treating an earlier approval as durable*; *inferring layout or columns from the response shape* — scannability is the owner's judgment.

## The open-work list holds only open work (2026-07-06)

**Decision.** [todo.md](todo.md) is a working list, not an archive: closed items — and whole finished docs — are deleted; git history is the archive.

**Rejected.** *Append and keep* (closed items get re-read forever); *a separate archive doc* (a second home for what git already keeps).

## Split transactions, the pending hashtag and system rows (2026-10-17)

**Decision.** (1) **Each part of a split transaction is its own ledger row** (owner, 2026-10-17): the transaction's title, its own amount, category, hashtags and note. `c` and `h` change only the selected parts; the bank's fields (title, date, account, bank code) belong to every part, and the Edit form says so before a part's title, date or account is saved (contract: PUT /v1/transactions/{transaction_id}). (2) **`⏎` and `s` on any part open one Edit form: the line's shared fields on top and a table of every part below, and one save writes the whole line** (owner, 2026-10-25, [mockups/expense-world-split-transaction-screen.html](mockups/expense-world-split-transaction-screen.html)), from one read of the bank line: its parts, the engine's total and its `edit_limits` (contract: GET /v1/bank-lines/{bank_line_id}). Parts change in that one place: a kept part keeps its id, `^n` adds one and `^x` drops one, so a line never split keeps its one transaction as part 1 (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). The form shows how much of that total the typed parts leave, red until it is 0, as a guide only: `^s` always sends, and the engine's `SPLIT_TOTAL_MISMATCH` decides whether the parts add up (contract: PUT /v1/bank-lines/{bank_line_id}, "The total"). **The title is the transaction's, one field written onto every part in the same write**, sent only when it differs from the transaction's (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"); an emptied title is refused, so a save never removes a title. (3) **The pending hashtag is a hashtag like the others**, found by its `system_key`: every transaction carries at least one hashtag, so Home has no "(no hashtags)" row, and a screen that tags a row sends only the real hashtags. (4) **The built-in rows keep their names** (owner, 2026-10-16): no screen offers a rename or a delete on `@Opening`, `@Pendiente` or the pending hashtag, because the engine refuses both (contract: PUT /v1/categories/{category_id}, "A system category keeps its name"); a name the engine keeps for a system row is refused with one line, "That name belongs to a system row: pick another." (5) **The spreadsheet import groups split rows by their `COD_EECC`** ("The sheet import brings a split purchase in as one split transaction").

**Rejected.** *One ledger row per split transaction, its parts inside* — a category or hashtag belongs to a part, so one row for all the parts hides what `c` and `h` change; the engine declined a ledger read by bank line too. *Holding `^s` until the parts add up* — a business rule checked in the client, which every client would copy; the engine already refuses and says by how much. *One typed line per part, in the LOG bar's grammar* — a part keeps the transaction's title, account and date, so most of the grammar only led to refusals, and the owner found it hard to read. *Every part's fields in one long form* — the table shows every part at a glance. *Renaming a split transaction from the Edit form after the split* — two writes, and the first can land without the second. *Offering `e` on system categories* — the engine refuses a rename, so the key would only lead to a refusal.

## A split transaction is reconciled and deleted whole (2026-10-17, owner)

**Decision.** (1) **The reconciliation screens list bank lines, not ledger rows** (owner, 2026-10-17): one row per bank line, in the bank's columns only (date · title · operation · amount) with the line's total, and nothing marks a split, because the bank sees one movement (contract: GET /v1/bank-lines). (2) **A tick is one write on any part**; the engine puts every part in the reconciliation or takes every part out, so no screen shows half a line ticked (contract: PUT /v1/transactions/{transaction_id}). (3) **`d` on any part of a split transaction deletes the whole line**, from the ledger or from "no batch", after a question naming how many parts go: "Delete this transaction and its N parts? No screen can bring it back." (contract: DELETE /v1/bank-lines/{bank_line_id}). `b` moves the whole line, as the engine does. (4) **`⏎` in "no batch" opens the Edit form**, as on the ledger (owner, 2026-10-25): the line's fields on top and every part below, saved in one write. (5) **The app's word is "transaction"** (owner, 2026-10-17), for a split one too; a variant of a form keeps that form's name.

**Rejected.** *Category and hashtags on the reconciliation rows* — a reconciliation checks the bank's movements, and the owner wants only the bank's columns. *A part count or a split mark on the row* — nothing in a reconciliation depends on how a transaction is split. *Oldest first in "no batch"* — the engine's line list has one order, newest first, and the owner accepted it. *Deleting one part with `d`* — the bank holds one movement, so deleting a part would leave the line's total short of the bank's; re-splitting changes the parts. *A form of its own for a split transaction* — a new screen name for a variant of the Edit form.

## TUI writes: FIFO queue in EngineWriteMixin, error drops the queue (2026-07-08)

**Decision.** `EngineWriteMixin.run_write` ([_base.py](../expense/tui/screens/_base.py)) owns a per-screen FIFO: exactly one request in flight, order preserved. **A failed write drops the queued remainder** — those intents were decided against a screen state the engine just contradicted; the error callback resyncs.

**Rejected.** *Per-screen queues* (N copies of one race fix); *cancelling in-flight writes on supersede* (thread cancellation cannot stop a request, and the idempotency key already covers retries); *continuing past a failure* (later writes may depend on the failed one). Independent bulk writes use their own worker instead — see "Home is the month". A screen that holds back its redraw while a write is unanswered reads that state from the queue (`writes_unanswered()`) and redraws in the `_writes_dropped` hook, so a dropped queue can never leave it waiting.

## Connection errors get exit code 6, off the click collision on 2 (2026-07-10)

**Decision.** Exit codes: **1** engine rejected the request, **3** config, **6** connection; **2** belongs to click's usage errors alone. A new meaning gets a fresh code, never an overloaded one; 4 and 5 are retired and not reused. Source of truth: `_ENVELOPE_ERRORS` in [expense/errors.py](../expense/errors.py).

**Rejected.** *Sharing 2 with a distinguishing message* — scripts branch on the code, not prose. *Renumbering to be contiguous* — churn for cosmetics.

## TUI paints the terminal's own background — ANSI mode (2026-07-11)

**Decision.** The app runs in ANSI mode (`ansi_color=True`, [app.py](../expense/tui/app.py)) and the base fills (`Screen`, `#menu`) are `ansi_default`, so the app and the terminal's window padding are one surface on any terminal. Guard: `test_base_fills_are_terminal_transparent`. The foreground half is "The terminal supplies the palette".

**Rejected.** *Match a fixed hex* — correct on one terminal profile only. *Fix it in the terminal profile* — pushes a code-owned problem onto every machine.

## Archive is a prompt-free toggle; Manage lists have no record detail (2026-07-11)

**Decision.** (1) **The Manage lists are the whole surface** — no record-detail screen: `e` opens the prefilled edit form, `a` archives/unarchives the cursor row (accounts only), `enter` is a no-op. (2) **Archive is a reversible toggle, not a destructive operation**: no confirm question. Only delete and revert ask first.

**Rejected.** *A record-detail screen* — repeats the list's columns. *Inline cell editing* — a second edit idiom for three screens. *A confirm on archive* — pure friction on something one keypress undoes. *`enter` as an edit alias* — declined; `enter` stays non-mutating.

## Every data table pages at 20 rows (2026-07-11)

**Decision.** `DEFAULT_PAGE_ROWS = 20` in [reads.py](../expense/reads.py), one copy. Full-data lists (Manage lists, Reconciliations panes, the tick-list) are display-windowed — the window follows the cursor — at the size set by "TUI rows-per-page adapt to the terminal". The ledger and the "no batch" pane grow instead ("Long lists grow, they do not page").

**Rejected.** *Client-side slicing of engine-paged reads* — the next client must inherit real pagination. *Auto-fetching when `↓` reaches the edge* — holding a key would fire a read per keystroke.

## TUI is keyboard-only — mouse disabled via `run(mouse=False)` (2026-07-12)

**Decision.** `launch` launches with `mouse=False` ([app.py](../expense/tui/app.py)): Textual never enables mouse tracking, so clicks do nothing and the terminal's native select-to-copy works. Every affordance has a keyboard path. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Rejected.** *Textual's default mouse* — unintended behaviour that blocks native copy. *Per-widget click swallowing* — brittle and still blocks copy.

## TUI rows-per-page adapt to the terminal — min(20, what fits) (2026-07-13)

**Decision.** The page is the screenful, capped at `PAGE_ROWS_CAP` (default 20). `SectionScreen.measure_list_rows` ([_base.py](../expense/tui/screens/_base.py)) measures `#content`'s real height (screens declare their extra lines; `LIST_FRAME_LINES = 6` is the panel frame), floor `PAGE_ROWS_FLOOR = 5`; the first load waits for the first layout pass. The panel always fits, so `#content` never grows a scrollbar nothing could operate.

**Rejected.** *A fixed 20 with a scrolling container* — the title and headers scroll away and the scrollbar is undraggable. *Grow-to-fit on every screen* — short lists read worse spread out; only the ledger lifts the cap ("The ledger fills the window").

## The ledger fills the window (2026-08-29)

**Decision.** Transactions sets `PAGE_ROWS_CAP = ENGINE_PAGE_CAP` (the engine's own `limit` ceiling) and `CARD_WIDTH = None`, so the ledger spans the terminal in both directions. Every other screen keeps the 20-row cap and its narrow card. Guarded by `test_transactions_panel_fills_and_fits_the_viewport`.

**Rejected.** *Lifting the caps app-wide* — declined: two short columns spread over 200 columns read worse. *A bigger arbitrary cap (50, 100)* — the engine's ceiling is the only non-arbitrary bound.

## Ledger cells fill their columns — flex text columns, no pre-truncation (2026-09-12)

**Decision.** Rows hand the table whole strings; `CursorList`'s `flex` mapping gives Transactions `{Title: 3, Description: 3, Hashtags: 2}` as Rich ratios. Amount, date, account and category keep their natural width; the text columns split the rest and are ellipsised at their real edge. Column edges depend on the terminal, not on the page's data, so the table never reflows while scrolling.

**Rejected.** *Natural width* — data-dependent layout, and on a narrow terminal Rich trims every column evenly until the amount is a bare `…`. *Bigger fixed caps* — the same bug on a bigger terminal.

## The app clears the terminal scrollback at launch — `CSI 2J 3J H` (2026-07-13)

**Decision.** `launch` emits `\x1b[2J\x1b[3J\x1b[H` before Textual starts ([app.py](../expense/tui/app.py)), so Terminal.app cannot scroll pre-launch text in above the running app. **Accepted cost (owner-confirmed):** the tab's whole scrollback is wiped on every launch. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Rejected.** *Clear only the screen (`2J`)* — the scrollback still slides in. *Re-enable the mouse to swallow wheel events* — reverts keyboard-only.

## The cursor is reverse video — applied as a Rich style, never as CSS (2026-08-20)

**Decision.** Reverse video is the one "you are here" gesture. Textual 8.2.7 drops `reverse` when both cursor colours are `ansi_default`, and a CSS override is dropped the same way, so `CURSOR_STYLE` ([windowed.py](../expense/tui/widgets/windowed.py)) is applied as a Rich style — `CursorOptionList` applies it in `render_line`. `test_tui_menu_cursor.py` asserts on the **rendered strip**, because the resolved style reported `reverse` throughout the bug: with terminal-owned colours, only rendered output is evidence.

**Rejected.** *A coloured cursor bar* — names fixed colours and gives the menu a different gesture from the lists. *Bold* — already means "pending".

## Opening balances are an engine concept (`@Opening` system category), not a client convention (2026-07-20)

**Decision.** `POST /accounts/{id}/opening-balance` seeds a balance as a transaction under the `@Opening` system category (`system_key = 'opening_balance'`, its name fixed by the engine); flow reports exclude it entirely, so no phantom income appears and visible rows sum to net. One per account (409). The sheet importer routes rows marked `SALDO INICIAL` in the **title or the category** column to it (deduped per account and currency).

**Rejected.** *A user category plus a naming convention* — invisible to the engine, so reports can never exclude it, and every client invents its own name. *An opening-balance param on `POST /accounts` only* — never fires for accounts that already exist. *Keep the `@Opening` row visible in panels* — visible rows would no longer sum to the total.

## Local-first deployment — the one engine moves to the user's Mac; cloud mothballed until iOS (2026-07-30)

**Decision.** The same engine runs on the owner's Mac (launchd, local Postgres), the daily FX fetch runs as a launchd task, and a nightly `pg_dump` to iCloud Drive is the durability layer. Every architectural invariant holds: one engine, zero client logic, server-first writes. This app's only change is `engine_url`. Reactivating the cloud for iOS is a relocation (restore the dump, redeploy, repoint). Ops: the engine's local- and cloud-deployment guides.

**Rejected.** *Keep the cloud warm on a paid tier* — needs internet for every command and still leaves FX unwired. *Local-first writes with an LWW queue in the client* — the engine's writes have computed side effects, so optimistic acceptance means duplicating the engine or "saved" rows bouncing later. *Port the engine to SQLite* — rewrites the money layer and forks local from cloud.

## All reads are live — no local replica (2026-08-06)

**Decision.** No local cache: every read is a live engine GET; there is no `expense sync`, no `--no-cache`, no cache env vars. With the engine on loopback a read is sub-millisecond, and a replica only adds staleness and conflict handling.

**Rejected.** *Rebuilding the cache from REST reads* — every consistency cost, for zero latency benefit.

## Transfers are two ordinary transactions (2026-08-16)

**Decision.** The engine has no transfer feature. A move between accounts is two ordinary transactions, each with its own explicit sign and category.

**Rejected.** *A client-side "move between accounts" that writes both legs* — a new UX with a non-atomic failure (one leg lands, the other 422s); parked in [todo.md](todo.md) behind a mockup. *Deprecation stubs for the old flags* — see "Delete anything that no longer points anywhere".

## Reconciliation de-chaining — a batch is a statement period, ordered by its date (2026-08-16)

**Decision.** Both balances are typed off the paper statement — one form, no chained/manual fork. A batch is positioned by its period's days; repositioning is editing its dates. `difference_cents` shows on the list surfaces and the working screen (see "A null difference is blank").

**Rejected.** *A client-side "chained" prefill of the beginning balance from the previous batch's end* — the deleted engine feature reimplemented in the client, with the same stale-neighbour bug.

## Home aggregates are nullable — `3 unrated` is a state, not a number (2026-08-16)

**Decision.** The engine returns `null` for a home-currency aggregate when any row in the group has no resolvable rate, with an `unconverted_count`. The client renders that as **`3 unrated`** in the cell — never `0.00` and never a native-currency fallback (which would read USD cents as PEN cents). One shared pair, `format_aggregate` / `has_aggregate` in [formatting.py](../expense/formatting.py), backs every screen. Month cells carry the count, so *no activity* (dim `—`) and *unpriceable* stay distinct. A category with nothing in the report is not drawn; the Categories screen still lists every one.

**Rejected.** *A partial total with a marker* — a half-true number on screen. *`n/a (3)`* — an abbreviation to learn. *A footnote with the count* — loses which row it belongs to.

## Contract tests verify against a disposable database, and refuse the real ledger (2026-08-16)

**Decision.** `tests/contract` runs against `expense_world_test` through a second engine on **`:8002`** (setup: [runtime.md](runtime.md) "Working against the live engine"). The suite **refuses to start** when it would write to the real ledger (`EXPENSE_ALLOW_REAL_LEDGER=1` overrides) — a `pytest_sessionstart` hook, with the `PYTEST_LIVE` gate as a `pytest_collection_modifyitems` hook, because a `pytestmark` in a conftest does not apply to other modules. Fixture drift is checked separately by [scripts/check_fixture_drift.py](../scripts/check_fixture_drift.py).

**Rejected.** *A warning banner instead of refusing* — useless when nobody is watching, which is when it matters. *A separate user in the real database* — the junk still accumulates in production. *The drift check inside `pytest tests/unit`* — the unit suite blocks sockets on purpose.

## A settled person is folded, never hidden — and creating one is a TYPE field, not a `people` group (2026-08-16)

**Decision — creation.** A **TYPE field** (`bank` / `person`, prefilled `bank`) first on the New Account form; `person` posts to `POST /people`. `is_person` is never sent — the endpoint is the flag — and TYPE is read-only on the edit form.

**Decision — settled people.** Folded behind a count (`▶ 3 settled`), never dropped — on Home. "Settled" is exactly zero in the person's own currency. `split_settled` / `settled_label` in [formatting.py](../expense/formatting.py) are the single copy. The engine refuses to hide settled people (a repaid loan and an unrecorded one would look identical; a coincidental net zero is two live debts), so the count line keeps the client from silently omitting anyone.

**Rejected.** *Printing every settled person* — buries the ones you owe. *Naming them on the fold line* — grows until it needs truncating.

## One word for hashtags — the engine's, everywhere (2026-08-16)

**Decision.** Column labels say **`Hashtags`**, the engine's word (`/hashtags`, `hashtag_ids`). Where client and engine disagree on a name, the engine wins, so every client inherits one vocabulary.

**Rejected.** *`Tags`* — shorter, but puts the client's word in front of the wire format's.

## The command palette is removed, not populated — `?` is the one discoverability surface (2026-08-17)

**Decision.** `ENABLE_COMMAND_PALETTE = False`; `?` opens our own two-column `HelpModal`, bound per screen via `HelpBindingMixin` (never on the App, and not on forms, where `?` types a character). The card is **derived** from `BINDINGS` declared under `expense.tui`, so Textual's internals stay out without a suppression list; `test_tui_help.py` fails any binding with neither description nor tooltip.

**Rejected.** *Populating the palette with a `Provider`* — more work than removal, and it keeps Textual's theme picker and footer strip. *Binding `?` to Textual's own help panel* — lists internals, unthemed, squeezes the content.

## The terminal supplies the palette — every colour is an ANSI slot (2026-08-19)

**Decision.** Nothing is detected. Every colour in [theme.py](../expense/tui/theme.py) is an ANSI slot (`ansi_green`, `ansi_red`, `ansi_blue`, `ansi_bright_black`, `ansi_default`) on one `Theme(ansi=True)`; the terminal's profile decides what each slot looks like, so the app is correct on dark, light and any custom profile. Picks: pending is **bold** with no colour (yellow fails on white); accent `ansi_blue`; structural rules `ansi_bright_black` via `$secondary`; modal card opaque with a dim scrim; no separate `NO_COLOR` mode. **Accepted cost:** the app does not look identical on every machine. Render-only traps: `$surface`/`$panel` generate to transparent under an ANSI theme (hence `$secondary` for rules), and alpha is dropped on `ansi_default`, so the scrim is a literal `black 60%` (`test_modal_scrim_dims_rather_than_wipes`). Guarded by `test_theme_is_ansi_slots_not_hexes`.

**Rejected.** *Detect the terminal's background and pick between two authored palettes* — maintains two palettes to approximate what the terminal already knows. *A stored light/dark setting* — one more thing to configure. *Textual's `ansi-dark`/`ansi-light`* — they encode the light/dark split this refuses.

## A terminal too small is the user's to fix (2026-08-20)

**Decision.** **No size guard.** **80×24** is where everything is correct; **60×20** is workable but lossy (columns ellipsised, every row present); nothing enforces either. Below that the app degrades silently: columns collapse from ~75 wide, and rows clip rather than reflow. `PAGE_ROWS_FLOOR` is a floor on the page size *requested*, not a protection.

**Rejected.** *Refuse at launch* — refuses readable terminals and misses the window shrinking after launch. *A persistent warning line* — spends a row where there are fewest. *An in-app notice screen below the threshold* — the one to build if this ever becomes a real complaint; rejected only on cost.

## Logging is a key, not a menu row — plain `+`, and the footer stops naming the arrow keys (2026-08-20)

**Decision.** **Plain `+`** (`LogTransactionMixin`, [_base.py](../expense/tui/screens/_base.py)) opens the LOG bar on Home and Transactions — one key, one meaning. Arrow keys are `show=False` in every footer (the `?` card still lists them). The form's field keys are in "Form fields move with `tab`" below.

**Rejected.** *`shift`+`+`* — unbindable: for a printable key the shift is already baked into the character. *A menu row* — the most frequent action with the most steps.

## Form fields move with `tab` — plain arrows too, unless a suggestion list is open (2026-09-30)

**Decision.** In every bar form, `tab` / `shift+tab` move to the next / previous field, always, and the footer shows `⇥ Field` — the form's one navigation slot, because a focused `Input` swallows `?` and forms have no help card. Plain `↑↓` walk the suggestion list when the field has one open and move fields otherwise. `^↑`/`^↓` stay bound and unadvertised. One copy: `form_bindings` ([_form.py](../expense/tui/screens/_form.py)).

**Rejected.** *`^↑`/`^↓` as the field keys* — macOS claims them for Mission Control and Application Windows before the terminal sees them. *`shift+↑↓`* — a chord for the key that must always work, where `tab` is what every form uses. *Plain arrows only walking the list* — dead keys on the four fields with no list. *Plain arrows always moving fields* — the suggestion list would need a key of its own.

## Stepping through a form never changes it (2026-10-23, owner)

**Context.** `⏎` walks down a bar form line by line. On the Edit form's ACCOUNT and CATEGORY it took the first name in the list, so walking past a transaction could move it to another account or category; a read-only line still took typing; and `⏎` saved only on the last line, so a form whose remaining lines were locked could be saved only with `ctrl+s`.

**Decision.** (1) **ACCOUNT and CATEGORY start on the row's own value**, in the list's usual order, so `⏎` with nothing typed keeps it (owner's pick 1 A, [mockups/expense-world-enter-and-esc.html](mockups/expense-world-enter-and-esc.html)). (2) **`@Pendiente` is in the Edit form's category list**, where the engine lists it, and a row in it starts highlighted there (pick 3 A); the Edit form and the bulk `c` pick share one list, `pickable_categories` ([reads.py](../expense/reads.py)), in the engine's order, `@Opening` never in it. (3) **A read-only line takes nothing**: the shared bar, `FormBar` ([_form.py](../expense/tui/screens/_form.py)), refuses typing, paste and delete there, and every field a bank line's `edit_limits` names opens read-only, showing what it holds. (4) **`⏎` saves when no line ahead can change**, as `ctrl+s` does. (5) **A form's own `on_input_submitted` calls `event.prevent_default()`** when a class under it has one: Textual runs each class's handler along the MRO otherwise, so one `⏎` moved two lines; a guard test holds it ([tui.md](tui.md) "The bar forms' keys").

**Rejected.** Leaving `@Pendiente` out of the Edit form's list with nothing highlighted (pick 3 B): the Edit form and the bulk pick would offer different lists, and the Edit form could never send a row back to waiting.

## One reader for every amount, refusing what it cannot read for sure (2026-10-23, owner)

**Context.** `13.853,20` was saved as 13.85: the amount reader dropped every comma, and the bank importer kept its own copy of that reader. A `nan` or `inf` cell crashed both importers.

**Decision.** (1) **An amount with a comma after its dot is refused**, never guessed, on every typed amount field and in both importers (owner, 2026-10-15); a comma before the dot is a thousands mark ([tui.md](tui.md) "One reader for every typed amount"). (2) **Both importers read an amount cell with the typed fields' reader**, so a rule lands everywhere at once; `nan`, `inf` and an overflowing amount refuse their row and the rest of the file imports. (3) **A part added on the Edit form and left with only the pending hashtag drops**, as an empty one does; **a part read from the line never drops**, whatever is emptied, since only `ctrl+x` should take a saved part out. (4) **A Manage Edit screen sends `color` only when another swatch was picked**, so stepping past the line never rewrites a colour no swatch shows.

**Rejected.** Reading `13.853,20` as thirteen thousand: whether a dot or a comma marks the decimals is a guess, and a guess that is wrong saves a wrong amount silently. Letting an emptied saved part drop: it would take a part out of a split without the person asking.

## One key per job — `j k h l , .` deleted, and the month window moves to `pgdn`/`pgup` (2026-08-27)

**Decision.** No aliases: `j`/`k`/`h`/`l`/`,`/`.` are not bound — a widget alias silently outranks a screen binding, so aliases make letters unusable as commands. `pgdn`/`pgup` mean "the next window of data": on the ledger they grow the list, on Home they slide the month window (`pgdn` goes older). `[`/`]` are bound nowhere. Guards: `test_no_duplicate_movement_key_aliases`, `test_square_brackets_are_not_bound_anywhere` ([test_tui_help.py](../tests/unit/test_tui_help.py)).

**Rejected.** *`←`/`→` for the month window* — Home's rows carry `▶` carets, and `→` on one must unfold it. *`shift+←/→`* — a third tier of arrows for one screen. *Vim aliases as free extras* — free until something wants the letter.

## The LOG bar shows the named account's ledger — elastic, and it stays put (2026-08-29)

**Decision.** Name an account in the line and `AccountPeek` shows its ledger under the staged list: **elastic** (`height: 1fr`, as many rows as the staged list leaves; re-renders on resize), **the bar's account, never a staged row's** (an open picker previews the highlighted candidate; an unresolved token shows nothing), and **it stays on the last account named** after `↵` clears the bar. No balance. One debounced `GET /transactions?account_id=…` per account, cached for the screen; a save invalidates the accounts it wrote to; a failed peek says so in its border and never retries.

**Rejected.** *A fixed 12-row strip* — steals rows from a long batch. *A one-line summary* — does not answer "did I already log this?". *Blanking the peek when the bar is empty* — blinks off at every `↵`. *A navigable peek* — a second cursor on the screen.

## The legend, the two picker gaps, and day+month dates (2026-08-29)

**Decision.** (1) **The grammar legend is a permanent row** (`$account · @category · #tag · ±amount · //note · when     ↵ stages the line`) that never changes; everything that does change lives on the `#hint` row above it. (2) **A bare `$`/`@`/`#` opens the full list** — it stands unresolved carrying every candidate. (3) **Matching is accent-blind** via one `fold()` ([quickadd/names.py](../expense/quickadd/names.py)). (4) **Day + month means this year**: `28Aug`, `28/ago`, `1set`, `15DEC` — separator optional, month any prefix of three letters or more in English or Spanish (no three-letter prefix reaches two months); an explicit year wins.

**Rejected.** *A bare numeric `28/08`* — `1/2` in a title would silently become a date; the month must be letters. *A four-row key block* — costs the peek four rows. *A live checklist legend* — declined for a row that is the same every time you look.

## Importer ids are positional — the sheet is append-only, and the rows in no batch are the check (2026-09-12)

**Decision.** `expense import sheet` derives each id as `uuid5(IMPORT_NAMESPACE, stable_row_key(row))`, and the key includes the row number — without it, two identical purchases on one day would collapse into one and the second would be lost. So **the sheet is append-only below the last imported row**: insert, delete or re-sort above it and every row below gets a new id and imports twice. The check is the account's rows in no batch (`u` on the Reconciliations browse) after every import: a duplicate lands outside any closed period, so it cannot hide in `difference_cents`.

**Rejected.** *A duplicate-group counter instead of the line* — better in isolation and the fix if the sheet ever must be edited in place; not worth changing every existing id. *An importer guard storing the last row count* — state the app does not keep, and a sheet can legitimately shrink.

## A sparse line is a ledger row under `@Pendiente` (2026-09-12)

**Decision.** (1) **A ledger row needs an account, an amount and a date**; title, category, tags and note are optional. (2) **An empty category files the row under the `@Pendiente` system category** (`system_key = 'pending'`, its name fixed and delete refused by the engine), which **counts** in every total, grid and balance. Naming `@pendiente` explicitly is allowed, so a row can be sent back to pending. (3) **A date ahead of today is refused**; **an unknown `#tag` is refused**; **a titleless row shows a dash** everywhere. (4) **A line is accepted or refused**: the LOG bar's `↵` stages it or shows the reason under the bar ([route.py](../expense/quickadd/route.py)). (5) **The category cell alone carries the pending state** — no marker column.

**Rejected.** *A draft table that does not count toward totals* — the money is missing from every figure until promoted; this is what made capture heavier than a spreadsheet. *A `pending` flag on the row* — a second axis every client must know, and it allows a real category plus the flag. *Accepting future dates* — a balance holding next week's rent reads wrong today. *Defaulting a missing title to the category or account name* — invented text indistinguishable from typed text. *An `UNTITLED` placeholder* — a lie the ledger carries.

## Bank downloads are matched against the ledger, not hashed (2026-09-12)

**Decision.** The TUI import door brings bank files in ([expense/bank_import/](../expense/bank_import/)): (1) **It asks which account, every run**; nothing is remembered by file name, because a browser re-download (`… (1).xlsx`) is a new name and a per-name memory would prompt again and grow the config forever. A card's two currencies are one pick. (2) **The engine matches** — the whole file in one `POST /transactions/import`, a dry run first, then the same call with `dry_run: false`. The engine matches each row to a bank line (one transaction, or the parts of a split) by operation code, otherwise by account + exact day + direction + total, claiming each line once; titles play no part, and a match writes the bank's title and any missing code onto every part of the line (contract: POST /v1/transactions/import, "Matching"). The per-account UNIQUE on `operation_code` is the floor. **More rows beats fewer**: there is no amount-only rule, because a duplicate shows up at reconciliation and a missed row is invisible. (3) **A day whose file total and ledger total disagree, or that holds a ledger line no file row claimed, is a report, never an action** (the engine's `day_mismatches`); the unclaimed lines stay out of that month's reconciliation, where the owner deletes them. **A row a day off its ledger line is new** (owner, 2026-10-16): it is added, and the leftover ledger line's own day shows as disagreeing when it falls inside the file's dates, so the owner fixes it by hand. (4) **The title is the bank's text**, whitespace collapsed; the client writes no description (description is the owner's notes field). (5) **New rows land under `@Pendiente` and `#Pendiente`.** (6) Nothing dated before **2026-01-01** is sent; a file over **500** rows (the engine's cap) is refused; a row inside a completed reconciliation comes back `sealed` and is its own row on the preview, `✗ Closed period`. The preview's `#` is the row's line in the file. Request and response live once in [expense/bank_import/engine.py](../expense/bank_import/engine.py). (7) **The ledger lines no file row claimed are shown signed by the app**: the engine sends them as ordinary transaction responses, `amount_cents` positive with the direction in `transaction_type`, and declined a signed copy; `?debit_as_negative` is refused on every route but the two transaction reads (contract: "Base Conventions", "Sign convention — responses"). So the app signs them in one helper, and a guard keeps it the only place a sign is read off the type ([runtime.md](runtime.md) "Read semantics"). Screens: [mockups/expense-world-import-report.html](mockups/expense-world-import-report.html).

**Rejected.** *Content-hashed ids* — blind to rows already in the ledger from the sheet or the LOG bar. *Matching a row one day off* — it can claim the wrong line on a busy card, and the leftover line shows in the days that disagree. *A client-side matcher* — every client would need its own copy. *Splitting a file over 500 rows across calls* — a later call's row could be claimed by one an earlier call just created. *A `--since` floor* — one forgotten flag from duplicates. *A cleaned merchant name as the title* — the title is what the bank sent.

## The TUI import door — a drop is text, read up front, asked every time (2026-10-02)

**Decision.** (1) **A dropped or pasted path is recognised as text** by one pure function
([dropped.py](../expense/tui/dropped.py)): the terminal types the path, so no mouse tracking or
emulator hook is involved. Terminal.app's backslash escapes and VS Code's quotes are both read.
**A line counts as files only if every word is an existing `.xlsx` path**; otherwise it stays
quick-add, so a half-recognised line never imports some files and stages the rest. VS Code's
terminal inserts one file per drop, so several files at once work in Terminal.app only.
(2) **Every file is read before any screen opens**; a file that is not a BCP export keeps the
LOG bar where it is, with what it is missing, and nothing is sent. (3) **Three full screens**
(account list, preview, result) replace one another above the bar, built on the shared steps of
[flow.py](../expense/bank_import/flow.py) and the reasons of [engine.py](../expense/bank_import/engine.py). (4) **The account is asked every time** (see "Bank downloads
are matched against the ledger" (1)). (5) **`esc` cancels this file and every later one**,
because `esc` means cancel everywhere in the app; a file already imported stays imported. A
nothing-new file with files after it moves on with `⏎`. (6) **The days that disagree are the
ledger after the import**, as the engine computes them (contract: POST /v1/transactions/import),
so a movement typed on another day than the bank's shows as a new row plus the typed line's
own day disagreeing (when that day is inside the file's dates), not as a silent duplicate.

**Rejected.** *Remembering the account per file name* — a browser re-download is a new name.
*Splitting quoted paths glued together by repeated VS Code drops* — it reads the line in a way a
shell would not. *A "rename to the bank's wording" offer after apply* — the note names the day;
deleting the extra row is one key in the ledger. *A separate error screen for a non-BCP file* —
the bar is where the right file gets dropped next.

## Home is the month — a live list, `⏎` is the filter, and bulk edits are select + one key (2026-09-12)

**Decision.** (1) **Home is a live list off the one `/dashboard` read**: categories (see "Home draws four months"), then accounts and people **in their own currency with the code beside the figure**, then LEDGER, MANAGE and SYSTEM as always-open section headers with every screen a row. A failed read is one dim row with the reason. (2) **`⏎` on a row pushes Transactions with a `LedgerFilter`** — the engine's own `?category_id=` / `?account_id=` — crumbed `Ledger ▸ NAME`. (3) **Bulk is select + one key**: `space` selects, `a` selects every loaded row, `c` / `b` / `h` open the bulk pick for the selection (or the cursor row) — a full screen listing the rows it changes above its bar, since a surface that carries rows is a screen and a pop-up only asks — and write **one `PUT /transactions/{id}` per row on its own worker**, then reload. A refused row is named by number and does not stop the others — which is why this is not `run_write`'s drop-on-error queue. The one refusal that ends a run is missing settings ("Missing settings stop a multi-write run"). (4) **Changed rows leave a filtered list at once**; the toast is the receipt. (5) **`esc` clears a selection, otherwise pops the screen** — the filter is the door, not a state. (6) **Hashtags replace the set** (the engine's `hashtag_ids` semantics); an empty apply is refused rather than read as "clear every tag". (7) **`@Pendiente` is pickable**, so a wrong bulk pick can be undone.

**Rejected.** *A categorising mode with history suggestions* — a second way to edit a category and a guess the engine would have to learn. *Spreading a category to every row with the same title* — same title, different payees; the selection is the spread. *Native balances with a converted figure beside them* — the balance you act on is the native one. *Bulk through `run_write`'s FIFO* — one refusal would drop every row behind it. *Folding the section rows* — the owner wants every screen visible. *`esc` stepping back to the unfiltered ledger* — two keys for "back".

## Home draws four months — three filters, empty categories hidden (2026-09-13)

**Decision.** (1) **Home draws categories × four months** (home currency), with unfoldable hashtag rows and inflow/outflow/net, from `build_range_grid` ([formatting.py](../expense/formatting.py)); `pgdn`/`pgup` walk the window a month at a time, never past this month. Balances are today's, and the header says so. (2) **`⏎` is three filters**: a category row → that category; a hashtag row → that category *and* that hashtag; an account or person row → that account. (3) **A category with nothing in the window is hidden.** (4) **A combo of several hashtags is drawn but not filterable** — `?hashtag_id=` takes one id, so a looser filter would show rows the cell does not count. A row still waiting for a hashtag sits on the pending hashtag, whose row filters like any other, and `@Pendiente` unfolds like any category.

**Rejected.** *This month beside last month* — drops the long view. *A cell cursor scoping `⏎` to one month* — a second cursor axis. *Keeping zero-activity categories* — the Categories screen and the pickers list every one. *A separate Overview screen or tab* — the same numbers twice. *Twelve months* — ~160 columns. *Balances as of the window's month* — no endpoint, rarely acted on. *Filtering a multi-tag combo by its first hashtag* — a superset presented as the cell's rows.

## A null difference is blank, a zero difference is the em-dash (2026-09-14)

**Decision.** A reconciliation's `ending_balance_cents` and `difference_cents` are nullable (not entered yet). In the TUI ([cells.py](../expense/tui/widgets/cells.py)): `0` difference is the dim em-dash ("balances, move on"); `None` or junk is a **blank** cell — never the em-dash, which would assert the batch balances; a null amount renders `—`, not `(null)`.

**Rejected.** *Null and zero both `—`* — tells you an unfinished batch balances. *A `?` glyph for null* — a blank already reads correctly. *Changing `format_cents` globally* — blunts a signal meant to be noticed.

## The TUI sees the response body only where it asks for it (2026-09-20)

**Decision.** `run_write` takes an optional `on_response: Callable[[dict], None]`, called **before** `on_success` and only when the body is a dict ([_base.py](../expense/tui/screens/_base.py)). Opt-in: reconciliation `complete` reads its `warnings`, the gap report and the balance save read the record they answer with, setup reads its bootstrap, and every form save offers it through `FormScreen._answered`, which the edit form uses to read `changed_parts`. Before `on_success`, so "read it, then repaint" needs no extra state.

**Rejected.** *A `body` argument on `on_success`* — every screen pays for one screen's need. *Stashing the body on the mixin* — a later `on_success` could read an earlier write's body. *Re-reading the record after completing* — the warning is computed at the transition and is not on the row.

## The gap report is a line under the header, not a toast and not the rows (2026-09-22)

**Decision.** A completed period's coverage-gap warnings render as a line under the header (`#rwarn`, `PALETTE.warning`), hidden when there are none; it survives `r` and clears on the next status change. The engine's sentence is shown **verbatim** and never parsed. The "completed" toast still fires — a gap is not a failure. Reviewing unfiled rows is the `u` pane's job ("Rows in no batch live in the reconciliation view").

**Rejected.** *A toast* — fades in five seconds, and this message exists not to be missed. *A full screen* — interrupts every close, including deliberate gaps. *Working the gap's dates out client-side* — a copy of an engine rule.

## Rows in no batch live in the reconciliation view, not in a filtered ledger (2026-09-22)

**Decision.** (1) **`u` swaps an open account's reconciliation panel** for that account's bank lines in no reconciliation, one row per line in the bank's columns, newest first ("A split transaction is reconciled and deleted whole"); `esc` swaps back. (2) **`⏎` opens the edit form** (wrong date or wrong account is the usual cause) and **`d` deletes after a confirm** that says a delete is final. (3) **A `!` flag** marks a row whose date falls inside a period the screen already holds — a hint, never a ruling. (4) **No "tick all, then complete"**: `space` files rows one at a time so the difference updates before you seal. (5) **The ledger's bulk refusals read one line per kind of error**, as every save of several rows does ("Refused rows read one line per kind of error").

**Rejected.** *"Tick all N, then complete"* — a non-zero difference never blocks completion, so one keypress could seal a month that does not add up. *A filtered ledger with an `unreconciled` filter* — reconciliation work belongs in the reconciliation view (owner). *Parsing the period name out of refusals to group them* — rows are grouped by the engine's code, fields and reasons, never by its words.

## The transaction list pages by cursor (2026-09-23)

**Decision.** `GET /transactions` pages by bookmark (`next_cursor` → `?after=`, `null` is the end), `?sort=date_asc` starts from the oldest, and the count is its own read, `GET /transactions/count`, asked once when a list opens or after a write. The client treats the cursor as opaque, drops it whenever the filter or sort changes, and walks forward only. Every list is one of three shapes ([runtime.md](runtime.md) "Three list shapes"). The engine owns paging and the count, which is the case behind CLAUDE.md's "Ask the engine to change" rule.

**Rejected.** *Offset paging* — a list that shrinks while you file rows silently skips rows. *A probe-then-offset-then-reverse read for oldest-first* — two reads, a race at the page edge, and a pattern every client would copy.

## Deleted is deleted (2026-09-23)

**Decision.** A delete is final from every client: there is no restore and no way to list deleted rows. The engine still soft-deletes, so `GET /activity` keeps the history; **undoing a delete is an operator task** (contract: "Base Conventions", "A delete is final"). Delete prompts are unchanged.

**Rejected.** *A restore in this client only* — a write no other client has. *A "recently deleted" view* — a list shape for a rare operator action.

## Activity and Rates leave the TUI (2026-09-23, owner)

**Decision.** Activity and Rates have no screens; the live contract suite exercises them ("The TUI is the only surface"). Adding a screen for either is new work of its own.

**Rejected.** *Porting both screens to date windows* — a second paging model for two unused screens.

## Long lists grow, they do not page (2026-09-25, owner)

**Decision.** The ledger and the "no batch" pane are **one list that grows**, both through `GrowingRead` ([_growing.py](../expense/tui/screens/_growing.py)): **10 rows** to start; `pgdn` **appends** the next 10 with the cursor on the first new row; `↑↓` scroll everything loaded; `pgup` moves up a screenful with no read; a resize fetches nothing. The caption reads `N of M loaded`.
- **Rows and count load together; a missing count fails the whole list** — never rows beside a guessed total.
- **After any write the list starts over**: `+`, an edit, `c` / `b` / `h`, `d` and `r` read the first 10 fresh with the cursor on row 1. A refused bulk row stays selected only if the fresh read brings it back.

**Rejected.** *Page swapping* — a cursor cannot say "page 3 of 11", and a resize either loses your place or repeats rows. *Keeping the loaded depth and cursor after a write* — the owner wants the plain reload. *Keeping an off-screen refused row selected* — the next bulk key would change a row you cannot see.

## Reconciliations opens on the accounts (2026-09-25, owner)

**Decision.** The screen opens with **the accounts alone** and reads nothing. `⏎` on an account reads its reconciliations (`GET /reconciliations?account_id=`, or `?statement_of=` on an account with a statement code, which lists every account holding the code; whole, in the engine's order: [tui.md](tui.md) "The Reconciliations browse") and opens the panel under it; `esc` closes it. `u` works only inside an open panel. Returning from a reconciliation re-reads the account and lands on the same row; "not in the account's list" is how the working screen knows a reconciliation was deleted.

**Rejected.** *Reading on cursor pause* — a read per pause for a screen whose next step is always `⏎`. *Reading every account's list at open* — grows with the account list.

## Reconciliation periods are days (2026-09-26, owner's pick)

**Decision.** A period's `date_start` / `date_end` are **bare `YYYY-MM-DD`**, both required; the engine refuses anything else. The TUI form checks the date **at the field** with `is_calendar_day` ([dates.py](../expense/dates.py)) — zero-padded, a real day — and sends it unchanged. The tick-list passes the period's days straight into `date_from` / `date_to`.

**Rejected.** *The LOG bar's forgiving dates* — a statement's dates are copied off paper. *`date.fromisoformat` alone* — accepts `20260831`, which the engine refuses.

## Delete anything that no longer points anywhere (2026-09-25, owner)

**Decision.** A removed flag, command or code path is deleted outright — **no stub, no friendlier message**: a removed command gets Typer's own "No such command". Test fakes use the engine's real shapes (`whole()`, `cursor_page()` in [tests/unit/helpers.py](../tests/unit/helpers.py)) and refuse what the engine refuses. Guard: `test_command_surface.py` pins the typed surface.

**Rejected.** *A stub that explains the removal* — a second copy of the engine's change that lives forever. *Keeping a dead branch "in case"* — unreachable code is untested; git history keeps old behaviour.

## Sealed periods: the engine guards, the client reports (2026-09-20)

**Decision.**
- **The engine is the only guard.** No client checks a seal before a write or caches completed windows (they change under `revert`). The `!` flag and the bank import's `sealed` rows only report.
- **Only a date or account change can hit a seal**: of the bulk keys only `b` can be refused by a seal; `c` and `h` stay legal inside a sealed period. The LOG bar names the sealing period on the refused row and still saves the rest; the bank import shows such a row as `✗ Closed period` and imports the rest.
- **`revert` shows nothing extra.**

**Rejected.** *A client-side seal check* — a copy of an engine rule, stale the moment another client reverts. *A "close every month" bulk command* — would seal months nobody reviewed.

## The agent loop: one per repo, the main session orchestrates (2026-09-27, owner)

**Context.** The owner is not a coder. Work runs through agents that build, check and commit without asking about each task, while the owner keeps what users see, money rules a spec does not cover, and real data. The rules live in [CLAUDE.md](../CLAUDE.md) "How work runs (the agent loop)"; this entry holds the why.

**Decision.**
- **One loop per repo.** The worker definitions are written once in `~/.claude/agents/` and shared; each repo supplies its rules through its own CLAUDE.md. This repo came first because it has the most tests and guards; the engine repo runs its own copy, with its own guards and rulebook.
- **The main session is always the orchestrator** and never writes code or tests; the builder writes, the reviewer and tester only read and run, the librarian edits only docs.
- **The tester never writes tests.** A criterion with no test proving it goes back to the builder.
- **The loop runs on its own** once the owner approves a spec's tasks, pushing after every finished task, and stops only for what goes to the owner. A task needing a screen draws its mockup, parks, and the loop moves on.
- **Workers run on the session's model** (`model: inherit`).
- **The practice engine is the one exception to staying inside this repo.** Any agent starts and stops it with `scripts/practice-engine up|down`, which reseeds the practice user with a fresh key that is never stored; the hand-run start and stop stay the tester's.

**Why.** "Done" (tests pass, committed and pushed) only means something inside one repo, and a loop per repo keeps the wall between this client and the engine automatic. Every change is written by one agent and read by another, so nothing is approved by the agent that wrote it; the same holds for a tester that would otherwise write the test it then checks. Pushing after each task runs GitHub's checks on each one. A fresh practice key per check leaves nothing stored. A fact written in two docs drifts, which is why the librarian exists.

**Rejected.** *One loop over the whole `productivity_world` folder* — "done" stops meaning anything across repos and the client–engine wall stops being automatic. *Checking in with the owner after every task* — the questions would be technical ones the owner hands back to the agents anyway.

## Review per task, test and align once per spec (2026-09-27, owner)

**Decision.** Each task runs builder → reviewer → commit and push; the reviewer also confirms each "passes if…" item. When a spec's tasks are done, the tester runs once as an acceptance check against the practice engine (version check, fixture check, the live contract suite, the spec's done-checks, and the app when a screen changed), and anything that fails becomes a new task. The librarian runs last, sweeping every doc before the spec is retired.

**Why.** The commit hook already runs the unit tests on every commit, so a per-task tester only repeated them; its real value is the real engine and checking criteria rather than tests, which one pass per spec covers. Docs drift slowly, so one sweep at the end catches what per-task passes did. Reading is cheaper than testing, so the reviewer goes first.

**Rejected.** *Tester and librarian after every task* — most of their time goes on re-running what the commit hook checks and on small follow-up rounds. *No tester at all* — nothing else runs the app against the real engine or catches a criterion the tests miss.

## The engine is learned only from its live contract (2026-09-28, owner)

**Decision.** This repo learns how the engine behaves only from `GET /openapi.json` on the practice engine (`:8002`), read live; no copy of the contract is kept. Only its version is saved ([scripts/engine-contract-version](../scripts/engine-contract-version)); the fixture check compares it on every run and, when it moves, prints the contract's own change log (`x-changelog`). A moved version stops the loop and becomes a question for the owner, who decides whether catching up is the next spec; the new version is recorded only when acting on that answer. Code comments and docs cite the part of the contract that states a rule, as `(contract: …)` ([CLAUDE.md](../CLAUDE.md) "Key documentation"). No agent reads a file in the engine's folder: the guard blocks it for every agent, and the tester keeps only its start, reseed and stop there ([CLAUDE.md](../CLAUDE.md) "Stay inside this repo").

**Why.** Reading the engine's folder broke the rule that agents stay inside this repo, and the web and iOS clients never see that folder: they have only the published contract, so this client validates the same thing they will use. A saved version with the engine's own change log says *that* the contract moved and *what* moved, without keeping a copy that goes stale.

**Rejected.** *Keeping a copy of `openapi.json` in the repo* — it drifts, and each client would keep its own. *Accepting a moved version automatically* — an engine change would slip into the ledger's client unreviewed. *Reporting a change as the fixtures that no longer match* — it says what this repo's test data got wrong, not what the engine changed.

## Hints are chosen by the engine's reasons, never its wording (2026-09-28, owner)

**Decision.** Every engine error carries `error.reasons`, one code per field in `fields` (contract: "Error reasons"). The app chooses every hint from those codes, and from the status and error code, never from `message` or `fields` text; `EngineError` keeps them next to `fields` ([errors.py](../expense/errors.py)). What people see does not change: the engine's message, each field's message and the hint, with no codes on screen; `expense import sheet --json` passes the engine's envelope through verbatim, codes included ([commands.md](commands.md) "Output conventions").

**Why.** The engine publishes its message wording for people and changes it without notice; a hint keyed to words breaks silently on a rewording, and web and iOS would copy the same fragile match. Reason codes are part of the published contract, listed per operation, so a change to them moves the contract version and reaches the owner.

**Rejected.** *Showing the codes on screen* — the owner kept errors as they read today (2026-09-28); the codes are for code. *Keeping the wording matches as a fallback* — two ways to decide the same thing, one of them unreliable.

## A move to another account takes the row out of its reconciliation (2026-09-30, owner)

**Context.** A reconciliation holds only rows on its own account. The engine refuses a write that changes a row's account while the row sits in a draft reconciliation, unless the same write says what happens to the assignment (contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id}). In the TUI a row changes account from its edit form or with `b` in Home.

**Decision.** Both paths send `reconciliation_id: null` with every account change, so the move goes through and the row leaves its old reconciliation. A row kept on its own account sends no `reconciliation_id` and keeps its reconciliation. A short note says so: `Saved. It left its reconciliation.` in the edit form, `3 rows → BCP USD · 2 left their reconciliation` after `b`. The old reconciliation is on the old account and cannot hold the row any more; reconciling the new account assigns it there in the usual way.

The counts are the engine's: each move's answer lists every part of the bank line it changed and whether each left its reconciliation (contract: PUT /v1/transactions/{transaction_id}, "Response"), and the note counts the distinct parts listed across the answers that landed. A move that changes nothing shows no note. A line field reaches every part of a split transaction, so one request can move several rows, and two requests on one line can list the same rows; only the engine knows what moved.

**Rejected.**
- Asking each time whether to unassign or to assign into a draft on the new account: a new screen for a choice whose second answer is the normal reconciling flow anyway.
- Counting the requests sent, or deciding "left" from the rows read before the save: wrong for a split transaction, and a guess where the engine's answer says.
- Reading the line again after a move to learn what changed: an extra round trip for what the answer already holds.
- `0 rows → <account>` when nothing moved: a note about nothing; the owner chose silence.

## Missing settings stop a multi-write run (2026-10-11)

**Context.** Before first-time setup the engine answers `422 SETTINGS_MISSING` on every request its settings preconditions name (contract: "Base Conventions", "Settings preconditions"). The LOG bar save, the sheet importer and a bulk edit each make several writes in one run, and a `422` on a batch normally names its bad rows, so the batch settles them and sends the rest again ([runtime.md](runtime.md) "Bulk writes").

**Decision.** `SETTINGS_MISSING` is about the account, not a row: the first one ends the run, is reported once with its hint, and nothing further is sent. `LIMIT_REACHED` with reason `LINE_CODES_EXHAUSTED` ends a run the same way: once the line codes are used up, every write that needs a new line is refused (contract: POST /v1/transactions/batch), so the row it names fails in the engine's words and nothing further is sent. Both are one predicate in [expense/errors.py](../expense/errors.py), next to the hint's one home.

**Rejected.** *Settle it like any other `422`* — `SETTINGS_MISSING` names no row, so every row would carry the same four-line error and every later chunk would draw it again; `LINE_CODES_EXHAUSTED` names one row a send, so the run would spend one request per row to fail them all.

## The practice engine starts with its own Python only (2026-10-12)

**Context.** The engine needs Python 3.12 and its dependencies live in its own checkout's environment. The practice engine is started from this repo's sessions, behind the session guard ([runtime.md](runtime.md) "Working against the live engine").

**Decision.** The guard allows one start command, word for word, with the engine checkout's `.venv/bin/python` as its interpreter, and refuses every other spelling. The ops guide gives the same command, so the command a person copies and the command the guard accepts are one text.

**Rejected.** *A list of acceptable interpreters* (`python`, `python3`, …) — each resolves to whatever the shell finds first, which may be this repo's Python or the system's, without the engine's dependencies or on the wrong version. *Accepting any path that ends in the engine's interpreter* — the guard would have to resolve paths to know it is the same file.

## A list's order is written in the contract's words, in one home (2026-10-12)

**Context.** The contract states each list's order with its direction: accounts come every real account first, then every person, each group by `sort_order` ascending, then creation time, oldest first (contract: GET /v1/accounts, "Ordering"). Every client shows a list as the engine returns it.

**Decision.** A doc or comment that states a list's order uses the contract's wording, including the direction, and cites it; each order has one home and other places link there ([tui.md](tui.md) "The Reconciliations browse" for an account's reconciliations). `test_list_orders_state_their_direction` in [test_docs_links.py](../tests/unit/test_docs_links.py) fails on an SQL-style order and on a cited order without its direction. No screen sorts a list the engine orders.

**Rejected.** *SQL-style shorthand* (a column name followed by a sort keyword) — it names columns the contract does not publish and reads as knowledge of the engine's insides. *Stating the order wherever the list appears* — the copies drift.

## The unit suite pins its terminal size (2026-10-12)

**Context.** Typer prints a usage error in a box as wide as the terminal, and the width comes from the shell's `COLUMNS` or the window. The commit gate runs the unit suite in whatever session commits.

**Decision.** An autouse fixture in [tests/unit/conftest.py](../tests/unit/conftest.py) sets every test's terminal to 80×24, so the suite's result does not depend on the shell or the window ([runtime.md](runtime.md) "Unit tests never touch the network").

**Rejected.** *Loosening each assertion to survive wrapping* — every new test would have to remember it.

## The tag picker is one full list, narrowed by typing (2026-10-13, owner)

**Context.** The LOG bar's `#` lists every tag. The engine can also say which tags a category's transactions use, most-used first (contract: GET /v1/categories/{category_id}/hashtags).

**Decision.** `#` shows every tag in the order the engine lists them, read once from `GET /v1/hashtags`, and typing keeps the tags whose name contains the text, case- and accent-blind, in that same order ([quickadd/names.py](../expense/quickadd/names.py)). The list is the same whichever category the line names; the app sorts and merges nothing. The category-tags endpoint has no screen; the contract suite exercises it ([test_category_hashtags.py](../tests/contract/test_category_hashtags.py)).

**Rejected.** *A category's own tags first, a divider, then the rest* — two groups need a second order, and each client would pick its own. *The engine sending that two-group list* — declined by the engine coders: with one list there is nothing to merge. *Hiding the tags a category has never used* — any tag may go on any category. *A typed command listing a category's tags* — the TUI is the surface in use.

## Completing a reconciliation asks for its ending balance first (2026-10-15, owner)

**Context.** The engine refuses to complete a reconciliation whose ending balance is empty, and drafts still take an empty one for when the statement has not arrived (contract: POST /v1/reconciliations/{reconciliation_id}/complete, "The ending balance must be entered").

**Decision.** `c` on a draft with no ending balance opens a box for it; `enter` saves it, and then the usual question asks, where only `y` completes ([tui.md](tui.md) "A reconciliation's batch screen"). Saving and completing stay two writes and two answers, so a balance can be saved without completing. A refused write keeps the screen's usual note titles (`Couldn't save`, `Couldn't complete`), and a refused save closes the box, because the note already says what to do. No reconciliation was completed without an ending balance, so the app offers no revert-and-fill path.

**Rejected.** *One box that saves and completes on a single `enter`* — completing is the step that seals rows, and it keeps its own `y`. *Refusing `c` with the engine's words only* — the user then has to find where the balance is typed. *A `Failed` title for this flow* — the screen's other refusals say `Couldn't …`.

## A create leaves an empty colour to the engine (2026-10-15, owner)

**Context.** A create with no colour gets the engine's default, and an update still refuses a null one (contract: "Colour format").

**Decision.** New Category and New Account make colour optional, and a skipped colour is left out of the body. The sheet import sends no colour for the categories it creates, so they take the engine's default. While an optional colour line is empty, no swatch is highlighted, so the screen never shows a pick that `enter` will not make ([tui.md](tui.md) module map, `create_forms.py`). Edit Category keeps its colour required.

**Rejected.** *A palette the client cycles through for imported categories* — a client-side copy of a choice the engine makes. *Highlighting the first swatch on the empty line* — `enter` there skips the colour, so the highlight shows a pick that does not happen.

## The unit suite runs in parallel by default (2026-10-16)

**Context.** The agent loop spent most of its time waiting on `pytest tests/unit`: about 165 s run serially, four or more times per task. With pytest-xdist it takes about 25 s.

**Decision.** `addopts = ["-n", "auto"]` in pyproject.toml, so the tests gate, CI and hand runs all run in parallel; `-n0` forces one process. pytest-xdist is a dev dependency, not optional. It sits in addopts because pytest-cov reads `-n` before any conftest loads, so only addopts or the command line give CI a parallel coverage run.

**Rejected.** *An opt-in `-n` flag:* the gate and CI would not get it. *Setting `-n` from a conftest hook:* pytest-cov does not see it and crashes.

## Live contract runs stay in one process (2026-10-16)

**Context.** The contract tests share one practice user and make real writes, and one of them seals periods that others write into.

**Decision.** tests/contract/conftest.py and tests/conftest.py answer `-n auto` with zero workers for any live run, however it is started; only an explicit `-n N` overrides them.

**Rejected.** *Letting the default parallel run spread them:* they would race on the shared user and the sealed periods.

## The whole unit suite runs once per task, and docs never trigger it (2026-10-22, owner)

**Context.** The unit suite takes about 45 s and a task ran it three or four times: at the builder's stop, again at commit on the same code, and by hand from builders, reviewers and the librarian despite their instructions. Common practice keeps commit-time checks fast, runs the full suite once when the work is done, and keeps CI as the safety net; build tools such as Bazel never re-test code that has not changed since it passed.

**Decision.** The tests gate saves a fingerprint after a green run (the tree with untracked files, the venv's packages and Python version, the pytest command) and skips pytest when the builder's stop or a commit sees the same fingerprint. Every `.md` file and everything under `docs/` are left out of it, the owner's pick, so a docs-only change runs no tests; a doc edit that breaks a test that reads docs (`test_docs_links.py`, parts of `test_claude_hooks.py`) is caught by the librarian's docs-link run or by CI after the push. Anything that stops the fingerprint being computed, read or saved makes pytest run. The guard blocks a builder, reviewer or librarian running the whole suite by hand — enforcement by tooling, since written instructions did not hold — and names what to run instead; a bare `--lf` counts as whole-suite, since after a green run it reruns everything.

**Rejected.** *Running only the tests a change can affect (`pytest-testmon`):* once the gate skips unchanged code the builder's stop is the only full run, and testmon would move it to commit, where a failure costs a round trip, and add a data file that can go stale; revisit past about 90 s. *Running the doc-reading tests on a docs-only change:* a list of doc-reading tests to keep in step, for a check CI already makes. *Keeping docs in the fingerprint:* the orchestrator edits docs between the builder's stop and every commit, so the commit would rerun the suite on nearly every task.

## The practice engine has one script, run in exact shapes (2026-10-16)

**Context.** Sending a tester just to start or stop the practice engine added an agent round trip to every task that needed the contract live. The start's output carries the practice user's key, which must never reach a file.

**Decision.** `scripts/practice-engine up|down` starts, reseeds and stops the `:8002` engine, and any agent may run it; the orchestrator runs it around tasks. The guard allows only the whole command in a few exact forms, with no chaining, substitution, env prefix or wrapper, so the key stays off disk ([runtime.md](runtime.md) "Working against the live engine"). The script takes no options and runs under `bash -p` with every inherited variable unset and `env -i`, so nothing the caller sets can point it at the live engine or the real ledger.

**Rejected.** *Keeping the start tester-only:* slow. *A script that takes options or inherits the environment:* one variable could reach the real ledger.

## Engine changes arrive as one catch-up file and leave as one reply (2026-10-17, owner)

**Context.** The engine sent one hand-off file per change, each with its own contract range, so files overlapped, a version between two files could go unexplained, and a catch-up spec leaned on a file that lived until the spec retired. The engine coders heard nothing back once this client caught up.

**Decision.** The owner asks the engine coders for one hand-off file covering every contract change since the version this client last caught up to ([from-engine/README.md](from-engine/README.md)). The orchestrator turns the waiting files into catch-up specs, grouped as one unless parts are independent; each spec takes the engine's "What the TUI does", "Done when" and declined points, and the hand-off file is deleted. Each catch-up spec ends with a reply, written once the spec is done, that tells the engine the version caught up to, how each of its checks went, and any contract problems found ([to-engine/README.md](to-engine/README.md)). That reply's version is the one quoted for the next catch-up.

**Why.** One range per catch-up leaves no gap and no double work. The spec holding everything makes it stand alone, so the hand-off file adds nothing once the spec exists. The reply closes the loop: this app is the contract's first real user, and the engine coders learn what held up before the web and iOS clients build on it.

**Rejected.** *One file per engine change:* overlapping ranges and gaps. *Keeping the hand-off file until the spec retires:* two homes for the same facts.

## An ask leaves the outbox once it is handed over (2026-10-24, owner)

**Context.** An ask stayed in [to-engine/](to-engine/) from the day it was written until a hand-off answered it, so the folder mixed asks still to carry with asks the engine already held, and on 2026-10-24 the owner carried an ask the engine coders had already approved a second time.

**Decision.** An ask is deleted when the owner says it is handed over, as a reply is ([to-engine/README.md](to-engine/README.md)). From then on the engine holds it: its hand-off answers it, and whatever here waits on it (a spec's task, a todo.md item) names it by title. A revised ask is a file in the outbox again until it is handed over.

**Why.** The outbox lists only what the owner still has to carry, so nothing goes to the engine twice. The engine's copy and git history keep the ask's text, and the work waiting on it keeps its title in sight.

**Rejected.** *Keeping each ask until a hand-off answers it:* the folder no longer tells the owner what to carry, and an ask the engine already holds gets carried again.

## The bank import's preview is one table: a mark and a reason per file row (2026-10-18, owner)

**Decision.** (1) The preview lists every line of the file, the unreadable and pre-2026 ones
included, each with a **mark** and a **reason** from a short fixed list, the reason alone on
the row ([tui.md](tui.md) "The import door"). (2) **✓ means the row is in the ledger after the
import** (new, already there, or changed); **✗ means it needs looking at**: left out, or a move
to the bank's day stopped. (3) **A move to the bank's day is one more "Modified existing
transaction"**; the counts line says how many move. (4) **A move stopped by a completed
reconciliation is ✗ `Not moved: <reconciliation> is reconciled`**: with a reconciliation done
right the bank's day and the ledger's agree, so the row points at a reconciliation completed
wrong. It says "not moved", because the bank's title and operation number still land on it
(contract: POST /v1/transactions/import). (5) **The days where the file and the ledger disagree
stay on the preview only**; after importing, the screen gives the counts alone, since the
preview already showed every row. (6) The stopping reconciliation is named by one read of it by its
id, once per distinct id, in the worker (contract: GET /v1/reconciliations/{reconciliation_id}).
The engine keeps a reference to another record an id alone, so it declined to put the name in
the import's answer. The fallback `a reconciliation` stays for a read that fails, and one failed
read does not stop the others, so the other rows keep their names.

**Why.** The old preview grew a suffix on its `match` column, or a note under the summary, for
each thing the engine learned to do (`+code`, `+title`, the bank's day), and each brought its own
wording questions. A reason per row from a fixed list takes a new engine behaviour as one more
reason.

**Rejected.** *✓ only for a new transaction* — a re-imported file would be mostly ✗ with nothing
wrong. *The reason followed by what changed* (`· day 03 Oct → 04 Oct`) — the owner keeps the
rows short. *A reason of its own for a move* — the owner keeps the list short; the count says
it. *The table again after importing* — the preview already gave it. *A ✓ on a stopped move* —
it hides a reconciliation to check.

## Every contract citation is checked against the live contract (2026-10-18)

**Decision.** [tests/contract/test_contract_citations.py](../tests/contract/test_contract_citations.py)
reads every `(contract: …)` citation in the repo's code, tests and docs and fails, naming the
file and line, on one whose operation, tag, section or rule heading the live contract does not
hold in the place the citation names. Its docstring defines what counts as a heading. It runs
with the rest of the live suite, so the tester's acceptance check catches a citation the engine
moved or renamed.

**Why.** The engine moves and renames rules between versions without changing behaviour
(contract `15063ec5587491ad` moved a dozen and renamed several), and a citation that no longer
resolves sends the next reader looking for a rule that is not where it says. A name-and-place
check is mechanical, so it is a test, not a sweep someone has to remember.

**Rejected.** *A hermetic unit test over a saved copy of the contract* — no copy is kept ("The
engine is learned only from its live contract"). *Checking only that each quoted name appears
somewhere* — a rule moved to another tag would still pass while the citation sends readers to
the wrong place.

## A form never sends `null` where the engine refuses it (2026-10-18)

**Decision.** The Edit form sends `null` only for the fields the engine clears with it
(`reconciliation_id`, `title`, `operation_code`); an emptied note is sent as
`description: ""` (contract: PUT /v1/transactions/{transaction_id}). A unit test empties every
field of both Edit forms and fails on any other `null`.

**Why.** An explicit `null` is `NOT_NULL` on every other field, so a `null` there is a refusal
the owner did nothing to cause. Pinning it field by field keeps a new field from bringing the
bug back.

**Rejected.** *Leaving an emptied note unsent* — the old note stays, and the owner's emptying is
silently lost.

## An archived account's frozen writes are not offered, and a refusal is the engine's words (2026-10-18, owner)

**Decision.** The engine freezes an archived account: of its transactions only the category,
hashtags and note change and an empty title or operation code is filled once, and its
reconciliations don't change (contract: POST /v1/accounts/{account_id}/archive). The app reads
`is_archived` from the accounts read each screen already makes and stops offering what the
engine would refuse: (1) the ledger hides `d` on such a row and draws the row as any other,
while `s` stays and opens the Edit form as `⏎` does (owner, 2026-10-25); (2) the Edit form shows read-only the fields the line's `edit_limits` names, as for an
opening balance or a completed reconciliation, each marked `read-only` with no line saying why
(owner, 2026-10-25), and offers no `^n` or `^x` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"); (3) a frozen change sent anyway (a screen opened before the archive) shows
the engine's words alone, with no line of the app's own; (4) the Reconciliations screen keeps
listing only active accounts. The owner picked each from
[expense-world-archived-account.html](mockups/expense-world-archived-account.html) (screens
1 A, 2 B, 3 A, 4 A); screen 1 A holds for the row and `d`, while `s` stays ("The Edit form's
keys and words name what it does"). The engine still judges every write.

**Why.** Offering a key the engine always refuses invites a refusal for nothing, and every
client would meet it. Reading the engine's own flag keeps the rule in the engine: the app adds
no judgement of its own, and a failed accounts read only puts the keys back for the engine to
refuse. The engine's refusal already says to unarchive first, so the app adds nothing to it.

**Rejected.** *Dimming the archived account's rows* and *a line on the Edit form saying why*
while some of its lines still change — the owner keeps the screens as they are. *A line naming where to unarchive* — the engine's words
say it. *A question that unarchives and retries* — it would make unfreezing a side effect of an
edit. *Listing archived accounts on Reconciliations, read-only* — nothing there can change.

## The sheet import brings a split purchase in as one split transaction (2026-10-22, owner)

**Context.** One bank movement split across categories is several rows in the owner's sheet,
and the rows of one movement share a `COD_EECC` (`SIG-202603-029`). The sheet has no column for
the engine's bank line or the bank's operation number, so `COD_EECC` is the only way to tell from
it which rows were one movement. Imported row by row, each would become a movement of its own,
and a later bank upload would add the movement again.

**Decision.** (1) **Rows sharing a `COD_EECC` come in as one split transaction**, sent as one
`line_group` (contract: POST /v1/transactions/batch, "Line groups"); a chunk never cuts a group.
(2) **`COD_EECC` only groups; it is stored nowhere** (owner, 2026-10-23): no row the import
sends carries a statement line. A movement's statement line gives its place in the statement's
order and comes only from a reconciliation. (3) **A group goes whole or not at all:** a group
whose rows differ on account, date or title, or with a row the import cannot read, is skipped
whole as `split-mismatch` and named under the `Skipped` line, and the rest imports; once the
sheet is fixed, a re-run brings the group in. A zero-amount row is only dropped, since it
changes nothing. (4) **The dry run counts the groups in one line** ([commands.md](commands.md) "What it
prints"); the groups are checked in the app after the import. (5) **A refused batch is read item by item:** a row named `ID_EXISTS` on
its own id is already there, a row named by another refusal fails, and the rest go again as one
batch, so a re-run costs one request per chunk; a refused part fails its whole group. This rests
on the engine answering a taken id before any other conflict (contract: "Base Conventions", "Which refusal comes first on a create").
(6) **Letter case counts in a `COD_EECC`:** rows group by its exact text, trimmed, so `SIG-1`
and `sig-1` are two movements. This is the owner's rule for every match (2026-10-22): a field a
person types, a name, is matched without regard to case; a field from the bank or a program, an
operation code or a statement code, is matched exactly. A bank file's operation numbers are
compared the same way.

**Rejected.** *Keeping `COD_EECC` as each line's statement line* — a statement line comes only
from a reconciliation, and 2,275 hand-typed codes in the ledger would clash with the ones a
reconciliation makes. *Creating each month's reconciliations and their statement order at the
import, read from `COD_EECC`* (owner, 2026-10-24) — reconciling is the owner's call, made later;
an imported line has no statement line until its month is reconciled and ordered in the app.
*Folding case
in a `COD_EECC` or an operation code* — they come from a program, not a person, and a client
that folded them would merge two movements the engine keeps apart. *Stopping the whole import on
a differing group* — one slip in the sheet would hold back thousands of good rows. *Letting a
group's readable rows in without its unreadable one* — the split lands with a part missing.
*Listing every group on the dry run* — the owner checks them in the app. *Re-sending a refused
batch row by row* — one request per row, now that the engine names every item it refuses.

## An account becomes a person, and back, with one key (2026-10-22, owner)

**Context.** The owner's sheet records loans the way the app does: every movement with a person
is mirrored in an account named after that person, and its balance is the debt (ALEJO, ALONSO,
LC, ALEX, LIDIA, MATILDE, CARLOS and KORAKUEN; twelve accounts once split by currency). The sheet
import creates every sheet account as a bank account.

**Decision.** (1) **The owner turns an account into a person in the app,** not in the import:
`t` on Manage ▸ Accounts sends make-person or make-account at once, with no question, since it
is reversible and keeps the account's id, name, currency, balance and transactions
(contract: POST /v1/accounts/{account_id}/make-person). The cursor stays on the account in its
new group, and the note says what it became, so a second `t` turns it back. (2) **A refusal is
the engine's words,** and `HAS_OPENING_BALANCE` adds what to do: empty the opening balance with
`e` first, since a person cannot carry one. A person never has reconciliations either, since a
reconciliation checks the ledger against a bank statement and a person sends none (owner,
2026-10-22): `HAS_RECONCILIATION` adds `On Reconciliations, press d on each of its
reconciliations; a completed one needs u first.`, because the engine's words cannot say that a
completed one goes back to draft before it is deleted. (3) **The sheet import finds people and archived
accounts too** when it matches by name and currency, so a re-run after a conversion reuses the
person instead of creating the name again and failing its rows.

**Rejected.** *Teaching the import which sheet names are people* — a list to keep in step with
the sheet, while a plain account action also fixes any account created as the wrong kind.
*Asking before `t`* — nothing is lost, and `t` again undoes it.

## A hint says what `⏎` does there, and a note names what the app can't read (2026-10-24, owner)

**Decision.** (1) **A bar form's hint says "enter to save" only where `⏎` saves**; where it moves
on it says "enter to go on" (NAME on Manage ▸ Accounts and Categories, the Edit form's TITLE, a
new reconciliation's NAME, which keeps its example: `e.g. “April 2026” · enter to go on`), and
the account's COLOR reads `optional · enter keeps it · ↑↓ another swatch`; a guard test walks
every bar form ([tui.md](tui.md) "The bar forms' keys"). (2) **A non-date on the Edit form's DATE
is refused at `⏎`** with `Date: use YYYY-MM-DD.`, the words of the app's other dates, on both
Edit forms. (3) **The LOG bar names a signed amount it can't read**: `tottus -13.853,20 $BCP PEN`
reads `can't read -13.853,20 as an amount`, and "a number needs a sign" is left to a line with no
signed number. (4) **The bulk `c`, `b` and `h` pick is a full screen**, the rows it changes
above its bar ("Home is the month", point 3).

**Why.** A hint or note that says something the screen does not do teaches the wrong key, and
a typo must never close the app and lose what was typed.

**Rejected.** *Refusing a bad date only at save* — the note would come after the line is left,
where every other line of the form is checked at `⏎`.

## Refused rows read one line per kind of error (2026-10-22, owner)

**Decision.** When a save of several rows is refused, the sheet import's `Failures` block, the
LOG bar's lines under the table and the ledger's bulk `c`, `b` and `h` note read one line per
kind of error, from one shared helper: the field the engine names, its
words, then the rows it hit (`date: Must not be null. row 77`, `rows 3, 5, 7`). Rows are one kind
when the engine's code, fields and reasons for them are the same, never by its top-level message,
which counts the items. The engine's whole answer stays in the import's `--json`. A split refused
for one row shows that row's line, and its other rows read `Part of a split transaction refused
for another row.`; rows the app holds back read `Not sent: …` and `Part of a split transaction
not sent for another row.`, so "refused" only ever means the engine said no.

**Rejected.** *One line per row* — a refusal that hits many rows repeats itself line after line.
*The engine's words alone* — its words are often general (`Must not be null.`), so two lines
could read the same with nothing to say which field each is about. *Grouping by the top-level
message* — it carries a count, so one kind sent twice would read as two.

## The Edit form saves a whole line in one write, and the engine says what is locked (2026-10-25, owner)

**Decision.** (1) **Every save from the Edit form on a bank line is one
`PUT /bank-lines/{bank_line_id}`**: the line's fields and its full set of parts together, a kept
part keeping its id, an opening balance's line and an archived account's line included
(contract: PUT /v1/bank-lines/{bank_line_id}, "The parts' rules"). A kept part's hashtags are
sent only when they changed, since the engine counts any sent hashtags as a change; each kept
part's amount is sent as it is, which the engine does not count as one on an archived account.
(2) **What is read-only comes from the line's `edit_limits` alone**: the fields it names read
`read-only` and are dimmed, `^n` and `^x` show only when the parts are not fixed, and the total
is kept when it is fixed (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). The
form reads no reconciliation and holds no locking rule. (3) **A locked field says `read-only`
and no more** (owner's pick, 2026-10-25), although `edit_limits` carries a reason for each.

**Why.** One write lands whole or not at all, so a save never leaves a line half-edited, and a
retry under the same key never applies twice. The engine works out `edit_limits` with the write's
own rules on every read, so the form can never offer what the write would refuse, and every
client reads the same answer instead of keeping its own copy of the rules.

**Rejected.** *A transaction's own write for an opening balance's or an archived account's line*
— two write paths for one form, and the second takes a different set of fields. *One write per
part* — a chain that can land halfway. *Reading the line's reconciliation to decide what is
locked* — an extra read, and a copy of the engine's rules in the client. *The reason beside
`read-only`* — the owner kept the picked wording; it can come later as its own change.

## The Edit form's keys and words name what it does (2026-10-25, owner)

**Decision.** (1) **`s` stays on an archived account's ledger row and opens the Edit form as `⏎`
does**; only `d` leaves the footer there, and the form reads what is read-only from the line's
`edit_limits` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). (2) **The words
follow the form**: the ledger's footer reads `s Edit` and its `?` card "Edit the transaction and
its parts", the "no batch" `?` card says the same for `⏎`, and a refused part names its field by
the parts table's column word (`part 1 (category)`, `(hashtags)`, `(note)`, `(amount)`), from
one mapping derived from the table's columns (`FIELD_WORDS` in
[parts_table.py](../expense/tui/widgets/parts_table.py)). (3) **An opening balance's hashtag
refusal on the Edit form shows the engine's words alone**; "Leave the opening balance out of the
selection." stays on the ledger's bulk `h`, chosen by the refusal's `hashtag_ids` key, while the
whole-line write names `parts.<i>.hashtag_ids`. The owner picked 1 A, 2 A and 3 A in
[expense-world-edit-form-words.html](mockups/expense-world-edit-form-words.html).

**Why.** `⏎` and `s` open one form, so hiding one of them on a row hides nothing, and the engine
still judges every write. Words that describe a replaced screen promise the wrong screen. A field
named by the column the owner sees reads better than the engine's name for it, and needs no
second list to keep in step. A line about a selection makes no sense on a form that edits one
transaction, and the engine's words already say what is refused.

**Rejected.** *Keeping `s` hidden on an archived row* — it hides a form `⏎` opens anyway.
*Keeping `s Split` in the footer* — `s` opens the Edit form; it does not split. *Listing every
field on the "no batch" card* — three lines for what "the transaction and its parts" says in
one. *A line of the form's own for the opening balance's hashtag refusal* — rare, its field
already shows read-only, and the engine's words are enough.

## A card's statement is one statement, and a month closes from the bank's PDF (2026-10-25, owner)

**Decision.** (1) **A card is two bank accounts, one per currency, sharing a statement code**,
and the engine acts on a card's month as one statement: one create makes both halves, and a
complete, revert, delete or `PUT` on either half writes both
(contract: "Reconciliations", "A statement's order"). (2) **An account with a statement code
lists its statements from one `GET /reconciliations?statement_of=`**, one row per statement, the
other half found by its `twin_id` among the same items, never by days or names; what the row
shows is in [tui.md](tui.md) "The Reconciliations browse". The owner picked 1 A and question 3 B
in [expense-world-card-statement.html](mockups/expense-world-card-statement.html). (3) **The
statement line is never shown**: it only keeps a statement's lines in the paper's order. (4)
**No screen orders a statement, ticks the lines it still needs or edits a statement's name, days
and balances.** A month's reconciliation stays open until the bank's PDF statement arrives, and
uploading the PDF closes it, the engine reading, matching and completing
([specs/statements-close-from-their-pdf.md](specs/statements-close-from-their-pdf.md)). Until
then the live contract suite proves each of those engine parts ([runtime.md](runtime.md)
"Working against the live engine").

**Why.** A statement is one thing on paper, so it is one row and one write, and the engine, not
each client, knows which halves belong together. The owner checks a month against the bank's
PDF, not by linking rows one at a time; the PDF already holds each currency's balances, every
line and the paper's order, so reading it replaces every hand step.

**Rejected.** *A heading per statement with its two halves under it* (1 B) — three lines a month
show a third as many months. *Pairing a card's halves in the app by code and days* — a copy of a
rule the engine holds. *A screen to put a statement in order with `shift+↑↓`, the lines still
to tick under it, and an `e` form for the name, days and balances* — picked, then replaced by the
PDF upload before it was built: each is a hand step the PDF does. *Ticking lines into an open
month by date as they are imported* — with no ending balance before the PDF there is nothing to
compare them against.

## The suites copy the engine's answers and leave the practice user as they found it (2026-10-25)

**Decision.** (1) **The unit suite's fake engine answers a reconciliation write in the engine's
shape**, a card's twin included, through answer builders marked with the endpoint they stand
for, and the drift script reports any field the contract requires that a marked builder leaves
out ([runtime.md](runtime.md) "Fixture drift"). (2) **Every request body a unit test sends is
checked for the fields the engine sets itself** (`line_code`, `statement_line`,
`statement_place`), which the engine refuses in every body. (3) **Every live contract test fails
when it leaves an account, category or hashtag it made**, the rows the engine creates for itself
excepted, and a cleaner removes leftovers by name prefix ([runtime.md](runtime.md)
"Leftovers"). (4) **Engine-side probes use a practice user of their own**, never the one this
client's suite and hand checks use; the engine coders took that on 2026-10-25, after their
probes left about 60 accounts and 55 reconciliations here. (5) **The create form's begin balance
hint says a statement holding the opening balance begins at 0.00**, drawn in
[expense-world-opening-balance-note.html](mockups/expense-world-opening-balance-note.html).

**Why.** A fake that answers `{}` hides every field a screen might read, and a fixture missing a
required field passes until the real engine answers. A test that leaves records takes statement
codes other tests need and fills the browse the owner checks by hand; failing the test that
leaves them finds the leak where it starts. The engine adds an assigned opening balance into the
statement's sum, so typing the paper's starting figure too counts it twice.

**Rejected.** *Checking every fixture against the one endpoint it mocks* — the fixtures are not
mapped to endpoints; marking the builders that stand for an answer checks those exactly.
*Cleaning the practice user before each run* — it hides which test leaks. *Every engine-side
probe remembering to delete what it made* — a second practice user cannot leak into this one at
all. *A one-line hint, "0.00 on the first one"*, and *calling the paper's figure the "starting
balance"* — the first is not the exact rule, the second changes words already in use.

## A held reserved name is the engine's words alone, proven on each side (2026-10-25, owner)

**Decision.** (1) **When the Edit form's whole-line write is refused with `RESERVED_NAME_HELD`
on `hashtag_ids`, the form shows the engine's words alone**, with "Nothing was saved." and the
one write sent; the engine sends this refusal on the transaction's hashtags as a whole, never
on one part's (contract: "Hashtags").
`test_a_held_reserved_name_shows_the_engines_words_alone_under_the_parts` in
[test_tui_edit_form_parts.py](../tests/unit/test_tui_edit_form_parts.py) pins it. (2) **The
live proof that the engine sends it runs as a second practice user**, seeded by the practice
engine with its own category and hashtag holding the built-in names, never as the practice user
the suite shares. (3) **A test comment says what its case proves**, never which spec's pick it
came from.

**Why.** The engine's words already say what to do, so a line of the app's would only repeat
them. The shared practice user cannot reach a held reserved name: its pending hashtag already
exists and can never be deleted, and no hashtag of a user's may take the name `Pendiente`
(contract: "Hashtags"). A pick's name means nothing once its spec is deleted.

**Rejected.** *A line of the form's own for the refusal* — the engine's words are enough.
*Faking the state on the shared practice user* — the engine allows no way into it. *Holding the
spec open for the live test* — the owner chose to finish the unit half first and ask the engine
for the second practice user.
