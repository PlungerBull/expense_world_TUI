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
| Every screen is mocked first, and showing a mockup is not approval | [CLAUDE.md](../CLAUDE.md) "Mock every screen before building it" |
| The agent loop's rules (roles, per task, per spec) | [CLAUDE.md](../CLAUDE.md) "How work runs (the agent loop)"; the why is below |
| PAT auth (`ewe_pat_` prefix) | [commands.md](commands.md) "Auth model" |
| Public GitHub repo (free CI), so secrets and real ledger data never enter it | [CLAUDE.md](../CLAUDE.md) "Config isolation" |
| Sanctioned deviations from the principles | [commands.md](commands.md) "Sanctioned exceptions" |
| Rates cross the wire as integers (`rate_e8`, the rate × 10^8), so every client does exact integer maths with no float drift | (contract: GET /v1/exchange-rates) |

## What a half-written batch means (2026-08-25)

**Context.** The LOG bar saves every staged row through `POST /transactions/batch`, in chunks, via [expense/batch_write.py](../expense/batch_write.py). A batch can partly fail.

**Decision.** (1) **A successful save stays on the screen**: written rows show a `✓` and are cleared the moment the next line is staged, so the list only ever holds rows about to be written. (2) **A partial failure ticks what landed and retries only the rest.** Failed rows keep their marker and the engine's message; `ctrl+s` covers only rows without a `✓`. A refusal that holds for every further write is said once, on no row ("Missing settings stop a multi-write run"). This is safe because **`row_id` is minted at stage time and reused on every attempt** — a row whose response was lost replays as `409` with reason `ID_EXISTS` on that row's own id, which the save reads as *written*; every other `409` is a refusal (`is_own_id_replay` in [errors.py](../expense/errors.py)). (3) **`ctrl+s` never touches an unstaged line in the bar** — `↵` is the only thing that stages. (4) **The discard card's `ctrl+s save first` saves and then leaves, unless the save fails**, in which case the screen stays so the error can be read. The row's **`date` is frozen at stage time** too, so a batch saved across midnight does not change day. A saved row cannot be lifted back into the bar — correcting a written row is the edit form's job. The batch mechanics: [batch_write.py](../expense/batch_write.py)'s docstring.

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

## The TUI is the only surface (2026-10-13)

**Context.** The owner uses only the TUI. A typed command calling the same Python reads, formatters and write plumbing as a screen is a second face on the same feature, built and approved a second time for a surface nobody reads. Web and iOS call the engine's HTTPS API, never this repo.

**Decision.** Every feature is built once, in the TUI. Two things are typed: `expense`, which opens the TUI, and `expense import sheet`, the door for the owner's spreadsheet. Every engine endpoint is exercised by the owner's real use of the TUI and by the live contract suite, which calls the engine directly; an engine feature with no TUI screen is exercised by the contract suite alone. Agents get no typed commands: what is done to the ledger is done by the owner, in the app. The quick-add grammar is one implementation, used by the LOG bar. A new engine capability gets its TUI screen and its contract test, and nothing typed. The repo is `PlungerBull/expense_world_TUI` on GitHub and `expense_world_TUI` as the local folder; the command is `expense`.

**Engine features with no screen.** Activity history; exchange-rate history; editing a statement's name and dates after it is created, and its balances beyond the blank ones `c` asks for; updating the profile and the settings; the single-month report (Home shows the four-month grid); posting a batch of transactions in one call. They are the engine's own to keep working, and the contract suite exercises them. Adding a screen for one is new work of its own, when the owner asks for it.

**Rejected.** *Flat commands as the canonical surface beside the TUI* — every feature built, tested and approved twice. *One generic `expense api` command for agents* — an agent acting on the ledger belongs behind an MCP server beside the engine, not behind a command in this client. *Keeping every command as JSON-only for agents* — the same double build, for no reader.

## The open-work list holds only open work (2026-07-06)

**Decision.** [todo.md](todo.md) is a working list, not an archive: closed items — and whole finished docs — are deleted; git history is the archive.

**Rejected.** *Append and keep* (closed items get re-read forever); *a separate archive doc* (a second home for what git already keeps).

## Split transactions, the pending hashtag and system rows (2026-10-17)

**Decision.** (1) **Each part of a split transaction is its own ledger row**: `c` and `h` change only the selected parts; the bank's fields (title, date, account, bank code) belong to every part (contract: PUT /v1/transactions/{transaction_id}). (2) **`⏎` and `s` on any part open one Edit form, the line's fields on top and every part below, and one save writes the whole line**, from one read of the bank line (contract: GET /v1/bank-lines/{bank_line_id}); parts are added and dropped only there (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"). The amount the parts leave is a guide only: `^s` always sends, and the engine decides whether the parts add up (contract: PUT /v1/bank-lines/{bank_line_id}, "The total"). The title is the transaction's, one field written onto every part (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"). (3) **The pending hashtag is a hashtag like the others**, found by its `system_key`, so Home has no "(no hashtags)" row. (4) **The built-in rows keep their names**: no screen offers a rename or a delete on `@Opening`, `@Pendiente` or the pending hashtag, because the engine refuses both (contract: PUT /v1/categories/{category_id}, "A system category keeps its name"). (5) **The spreadsheet import's split rows are grouped by their `COD_EECC`** ("The sheet import brings a split purchase in as one split transaction").

**Rejected.** *One ledger row per split transaction, its parts inside* — a category or hashtag belongs to a part, so one row for all the parts hides what `c` and `h` change; the engine declined a ledger read by bank line too. *Holding `^s` until the parts add up* — a business rule checked in the client, which every client would copy; the engine already refuses and says by how much. *One typed line per part, in the LOG bar's grammar* — a part keeps the transaction's title, account and date, so most of the grammar only led to refusals, and the owner found it hard to read. *Every part's fields in one long form* — the table shows every part at a glance. *Renaming a split transaction from the Edit form after the split* — two writes, and the first can land without the second. *Offering `e` on system categories* — the engine refuses a rename, so the key would only lead to a refusal.

## A split transaction is reconciled and deleted whole (2026-10-17)

**Decision.** (1) **The reconciliation screens list bank lines, not ledger rows**: one row per bank line, in the bank's columns only (date · title · operation · amount) with the line's total, and nothing marks a split, because the bank sees one movement (contract: GET /v1/bank-lines). (2) **A tick is one write on any part**; the engine puts every part in the reconciliation or takes every part out, so no screen shows half a line ticked (contract: PUT /v1/transactions/{transaction_id}). (3) **`d` on any part of a split transaction deletes the whole line**, from the ledger or from "no batch", after a question naming how many parts go: "Delete this transaction and its N parts? No screen can bring it back." (contract: DELETE /v1/bank-lines/{bank_line_id}). `b` moves the whole line, as the engine does. (4) **`⏎` in "no batch" opens the Edit form**, as on the ledger. (5) **The app's word is "transaction"**, for a split one too; a variant of a form keeps that form's name.

**Rejected.** *Category and hashtags on the reconciliation rows* — a reconciliation checks the bank's movements, and the owner wants only the bank's columns. *A part count or a split mark on the row* — nothing in a reconciliation depends on how a transaction is split. *Deleting one part with `d`* — the bank holds one movement, so deleting a part would leave the line's total short of the bank's; re-splitting changes the parts. *A form of its own for a split transaction* — a new screen name for a variant of the Edit form.

## TUI writes: FIFO queue in EngineWriteMixin, error drops the queue (2026-07-08)

**Decision.** `EngineWriteMixin.run_write` ([_base.py](../expense/tui/screens/_base.py)) owns a per-screen FIFO: exactly one request in flight, order preserved. **A failed write drops the queued remainder** — those intents were decided against a screen state the engine just contradicted; the error callback resyncs.

**Rejected.** *Per-screen queues* (N copies of one race fix); *cancelling in-flight writes on supersede* (thread cancellation cannot stop a request, and the idempotency key already covers retries); *continuing past a failure* (later writes may depend on the failed one). Independent bulk writes use their own worker instead — see "Home is the month". A screen that holds back its redraw while a write is unanswered reads that state from the queue (`writes_unanswered()`) and redraws in the `_writes_dropped` hook, so a dropped queue can never leave it waiting.

## Connection errors get exit code 6, off the click collision on 2 (2026-07-10)

**Decision.** Exit codes: **1** engine rejected the request, **3** config, **6** connection; **2** belongs to click's usage errors alone. A new meaning gets a fresh code, never an overloaded one. Source of truth: `_ENVELOPE_ERRORS` in [expense/errors.py](../expense/errors.py).

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

**Decision.** The page is the screenful, measured from the real height and capped at 20 ([tui.md](tui.md) "Pagination and terminal size"). The panel always fits, so `#content` never grows a scrollbar nothing could operate.

**Rejected.** *A fixed 20 with a scrolling container* — the title and headers scroll away and the scrollbar is undraggable. *Grow-to-fit on every screen* — short lists read worse spread out; only the ledger lifts the cap ("The ledger fills the window").

## The ledger fills the window (2026-08-29)

**Decision.** Transactions sets `PAGE_ROWS_CAP = ENGINE_PAGE_CAP` (the engine's own `limit` ceiling) and `CARD_WIDTH = None`, so the ledger spans the terminal in both directions. Every other screen keeps the 20-row cap and its narrow card. Guarded by `test_transactions_panel_fills_and_fits_the_viewport`.

**Rejected.** *Lifting the caps app-wide* — declined: two short columns spread over 200 columns read worse. *A bigger arbitrary cap (50, 100)* — the engine's ceiling is the only non-arbitrary bound.

## Ledger cells fill their columns — flex text columns, no pre-truncation (2026-09-12)

**Decision.** Rows hand the table whole strings; `CursorList`'s `flex` mapping gives Transactions `{Title: 3, Description: 3, Hashtags: 2}` as Rich ratios. Amount, currency, date, account and category keep their natural width; the text columns split the rest and are ellipsised at their real edge. Column edges depend on the terminal, not on the page's data, so the table never reflows while scrolling.

**Rejected.** *Natural width* — data-dependent layout, and on a narrow terminal Rich trims every column evenly until the amount is a bare `…`. *Bigger fixed caps* — the same bug on a bigger terminal.

## The app clears the terminal scrollback at launch — `CSI 2J 3J H` (2026-07-13)

**Decision.** `launch` emits `\x1b[2J\x1b[3J\x1b[H` before Textual starts ([app.py](../expense/tui/app.py)), so Terminal.app cannot scroll pre-launch text in above the running app. **Accepted cost:** the tab's whole scrollback is wiped on every launch. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Rejected.** *Clear only the screen (`2J`)* — the scrollback still slides in. *Re-enable the mouse to swallow wheel events* — reverts keyboard-only.

## The cursor is reverse video — applied as a Rich style, never as CSS (2026-08-20)

**Decision.** Reverse video is the one "you are here" gesture. Textual 8.2.7 drops `reverse` when both cursor colours are `ansi_default`, and a CSS override is dropped the same way, so `CURSOR_STYLE` ([windowed.py](../expense/tui/widgets/windowed.py)) is applied as a Rich style — `CursorOptionList` applies it in `render_line`. `test_tui_menu_cursor.py` asserts on the **rendered strip**, because the resolved style reported `reverse` throughout the bug: with terminal-owned colours, only rendered output is evidence.

**Rejected.** *A coloured cursor bar* — names fixed colours and gives the menu a different gesture from the lists. *Bold* — already means "pending".

## Opening balances are an engine concept (`@Opening` system category), not a client convention (2026-07-20)

**Decision.** `POST /accounts/{id}/opening-balance` seeds a balance as a transaction under the `@Opening` system category (`system_key = 'opening_balance'`, its name fixed by the engine); flow reports exclude it entirely, so no phantom income appears and visible rows sum to net. One per currency of an account (409). Which rows of the owner's sheet are opening balances is the engine's to find when it reads the sheet (contract: POST /v1/transactions/import-sheet). The New statement form offers a begin-balance line on every currency: the engine sums every transaction assigned to a statement, the opening balance included, into its add-up check (contract: "Statements", "`difference_cents` — the add-up check"), so the statement holding it begins at 0.00, and the form cannot know which statement that is.

**Rejected.** *A user category plus a naming convention* — invisible to the engine, so reports can never exclude it, and every client invents its own name. *An opening-balance param on `POST /accounts` only* — never fires for accounts that already exist. *Keep the `@Opening` row visible in panels* — visible rows would no longer sum to the total.

## All reads are live — no local replica (2026-08-06)

**Decision.** No local cache and no write queue: every read is a live engine GET and every write waits for the engine's answer. With the engine on the owner's Mac a read is sub-millisecond, and a replica only adds staleness and conflict handling.

**Rejected.** *Rebuilding the cache from REST reads* — every consistency cost, for zero latency benefit. *Local-first writes with a last-write-wins queue in the client* — the engine's writes have computed side effects, so optimistic acceptance means duplicating the engine or "saved" rows bouncing later.

## Transfers are two ordinary transactions (2026-08-16)

**Decision.** The engine has no transfer feature. A move between accounts is two ordinary transactions, each with its own explicit sign and category.

**Rejected.** *A client-side "move between accounts" that writes both legs* — a new UX with a non-atomic failure (one leg lands, the other 422s).

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

**Decision — creation.** A **TYPE field** (`bank` / `person`, prefilled `bank`) first on the New Account form; both post to `POST /accounts`, `person` adding `is_person: true`, so one route makes either kind and the client keeps no second create path; TYPE is read-only on the edit form.

**Decision — settled people.** Folded behind a count (`▶ 3 settled`), never dropped — on Home. "Settled" is exactly zero in every currency the person holds, so a person folds whole or not at all. `split_settled` / `settled_label` in [formatting.py](../expense/formatting.py) are the single copy. The engine refuses to hide settled people (a repaid loan and an unrecorded one would look identical; a coincidental net zero is two live debts), so the count line keeps the client from silently omitting anyone.

**Rejected.** *Printing every settled person* — buries the ones you owe. *Naming them on the fold line* — grows until it needs truncating.

## One word for hashtags — the engine's, everywhere (2026-08-16)

**Decision.** Column labels say **`Hashtags`**, the engine's word (`/hashtags`, `hashtag_ids`). Where client and engine disagree on a name, the engine wins, so every client inherits one vocabulary.

**Rejected.** *`Tags`* — shorter, but puts the client's word in front of the wire format's.

## The command palette is removed, not populated — `?` is the one discoverability surface (2026-08-17)

**Decision.** `ENABLE_COMMAND_PALETTE = False`; `?` opens our own two-column `HelpModal`, bound per screen via `HelpBindingMixin` (never on the App, and not on forms, where `?` types a character). The card is **derived** from `BINDINGS` declared under `expense.tui`, so Textual's internals stay out without a suppression list; `test_tui_help.py` fails any binding with neither description nor tooltip.

**Rejected.** *Populating the palette with a `Provider`* — more work than removal, and it keeps Textual's theme picker and footer strip. *Binding `?` to Textual's own help panel* — lists internals, unthemed, squeezes the content.

## The terminal supplies the palette — every colour is an ANSI slot (2026-08-19)

**Decision.** Nothing is detected. Every colour in [theme.py](../expense/tui/theme.py) is an ANSI slot (`ansi_green`, `ansi_red`, `ansi_blue`, `ansi_bright_black`, `ansi_default`) on one `Theme(ansi=True)`; the terminal's profile decides what each slot looks like, so the app is correct on dark, light and any custom profile. Picks: pending is **bold** with no colour (yellow fails on white); accent `ansi_blue`; structural rules `ansi_bright_black` via `$secondary`; modal card opaque with a dim scrim; no separate `NO_COLOR` mode. **Accepted cost:** the app does not look identical on every machine. Render-only traps: `$surface`/`$panel` generate to transparent under an ANSI theme (hence `$secondary` for rules), and alpha is dropped on `ansi_default`, so the scrim is a literal `black 60%` (`test_modal_scrim_dims_rather_than_wipes`). Guarded by `test_theme_is_ansi_slots_not_hexes`.

**Rejected.** *Detect the terminal's background and pick between two authored palettes* — maintains two palettes to approximate what the terminal already knows. *A stored light/dark setting* — one more thing to configure. *Textual's `ansi-dark`/`ansi-light`* — they encode the light/dark split this refuses. *Cards or boxed panels* — a vertical edge costs border and padding on both sides, exactly the width an explaining column needs, and a card hides the screen that gives a question its context.

## A terminal too small is the user's to fix (2026-08-20)

**Decision.** **No size guard.** **80×24** is where everything is correct; **60×20** is workable but lossy (columns ellipsised, every row present); nothing enforces either. Below that the app degrades silently: columns collapse from ~75 wide, and rows clip rather than reflow. `PAGE_ROWS_FLOOR` is a floor on the page size *requested*, not a protection.

**Rejected.** *Refuse at launch* — refuses readable terminals and misses the window shrinking after launch. *A persistent warning line* — spends a row where there are fewest. *An in-app notice screen below the threshold* — the one to build if this ever becomes a real complaint; rejected only on cost.

## Logging is a key, not a menu row — plain `+`, and the footer stops naming the arrow keys (2026-08-20)

**Decision.** **Plain `+`** (`LogTransactionMixin`, [_base.py](../expense/tui/screens/_base.py)) opens the LOG bar on Home and Transactions — one key, one meaning. Arrow keys are `show=False` in every footer (the `?` card still lists them). The form's field keys are in "Form fields move with `tab`" below.

**Rejected.** *`shift`+`+`* — unbindable: for a printable key the shift is already baked into the character. *A menu row* — the most frequent action with the most steps.

## Form fields move with `tab` — plain arrows too, unless a suggestion list is open (2026-09-30)

**Decision.** In every bar form, `tab` / `shift+tab` move to the next / previous field, always, and the footer shows `⇥ Field` — the form's one navigation slot, because a focused `Input` swallows `?` and forms have no help card. Plain `↑↓` walk the suggestion list when the field has one open and move fields otherwise. `^↑`/`^↓` stay bound and unadvertised. One copy: `form_bindings` ([_form.py](../expense/tui/screens/_form.py)).

**Rejected.** *`^↑`/`^↓` as the field keys* — macOS claims them for Mission Control and Application Windows before the terminal sees them. *`shift+↑↓`* — a chord for the key that must always work, where `tab` is what every form uses. *Plain arrows only walking the list* — dead keys on the four fields with no list. *Plain arrows always moving fields* — the suggestion list would need a key of its own.

## Stepping through a form never changes it (2026-10-23)

**Context.** `⏎` walks down a bar form line by line, so whatever `⏎` does on a line happens to every row walked past.

**Decision.** (1) **ACCOUNT and CATEGORY start on the row's own value**, so `⏎` with nothing typed keeps it. (2) **`@Pendiente` is in the Edit form's category list**, where the engine lists it; the Edit form and the bulk `c` pick share one list, `pickable_categories` ([reads.py](../expense/reads.py)). (3) **A read-only line takes nothing**: no typing, paste or delete. (4) **`⏎` saves when no line ahead can change**, as `ctrl+s` does. (5) **One `⏎` moves one line**, held by a guard test ([tui.md](tui.md) "The bar forms' keys").

**Rejected.** Leaving `@Pendiente` out of the Edit form's list: the Edit form and the bulk pick would offer different lists, and the Edit form could never send a row back to waiting.

## One reader for every amount, refusing what it cannot read for sure (2026-10-23)

**Context.** Whether a dot or a comma marks an amount's decimals depends on who typed it: `13.853,20` is thirteen thousand to one person and an unreadable number to another.

**Decision.** (1) **An amount with a comma after its dot is refused**, never guessed, on every typed amount field; a comma before the dot is a thousands mark ([tui.md](tui.md) "One reader for every typed amount"); both importers send their file whole, so the engine reads their amounts. (2) **A part read from the line never drops**, whatever is emptied, since only `ctrl+x` should take a saved part out; a part added and left empty, or with only the pending hashtag, drops. (3) **A Manage Edit screen sends `color` only when another swatch was picked.**

**Rejected.** Reading `13.853,20` as thirteen thousand: whether a dot or a comma marks the decimals is a guess, and a guess that is wrong saves a wrong amount silently. Letting an emptied saved part drop: it would take a part out of a split without the person asking.

## One key per job — `j k h l , .` deleted, and the month window moves to `pgdn`/`pgup` (2026-08-27)

**Decision.** No aliases: `j`/`k`/`h`/`l`/`,`/`.` are not bound — a widget alias silently outranks a screen binding, so aliases make letters unusable as commands. `pgdn`/`pgup` mean "the next window of data": on the ledger they grow the list, on Home they slide the month window (`pgdn` goes older), bound `priority=True` because Home's menu is an `OptionList`, which binds `pgdn`/`pgup` to its own page scroll. `[`/`]` are bound nowhere. Guards: `test_no_duplicate_movement_key_aliases`, `test_square_brackets_are_not_bound_anywhere` ([test_tui_help.py](../tests/unit/test_tui_help.py)).

**Rejected.** *`←`/`→` for the month window* — Home's rows carry `▶` carets, and `→` on one must unfold it. *`shift+←/→`* — a third tier of arrows for one screen. *Vim aliases as free extras* — free until something wants the letter.

## The LOG bar shows the named account's ledger — elastic, and it stays put (2026-08-29)

**Decision.** Name an account in the line and `AccountPeek` shows its ledger under the staged list: **elastic** (`height: 1fr`, as many rows as the staged list leaves; re-renders on resize), **the bar's account, never a staged row's** (an open picker previews the highlighted candidate; an unresolved token shows nothing), and **it stays on the last account named** after `↵` clears the bar. No balance. One debounced `GET /transactions?account_id=…&currency_code=…` per account and currency, cached for the screen; a save invalidates the account currencies it wrote to; a failed peek says so in its border and never retries. Its count line names the pick's label, since one account holds several currencies and the peek lists one of them ([tui.md](tui.md) "The account peek").

**Rejected.** *A fixed 12-row strip* — steals rows from a long batch. *A one-line summary* — does not answer "did I already log this?". *Blanking the peek when the bar is empty* — blinks off at every `↵`. *A navigable peek* — a second cursor on the screen.

## The LOG bar's staged title gives way before the columns that place a line (2026-11-03)

**Context.** At 80 columns, an account and a category of about 20 letters each leave a staged
row's title a few letters, or a bare `…`.

**Decision.** The title and tags give way first; the marker, date, amount, currency, account
and category stay whole ([tui.md](tui.md) "The LOG bar's account is one row per account").

**Rejected.** *A least title width of about 10 letters, the account then the category cut
next*: it cuts the names that say where each line will be written.

## The legend, the two picker gaps, and day+month dates (2026-08-29)

**Decision.** (1) **The grammar legend is a permanent row** (`$account · @category · #tag · ±amount · //note · when     ↵ stages the line`) that never changes; everything that does change lives on the `#hint` row above it. (2) **A bare `$`/`@`/`#` opens the full list** — it stands unresolved carrying every candidate. (3) **Matching is accent-blind** via one `fold()` ([quickadd/names.py](../expense/quickadd/names.py)). (4) **Day + month means this year**: `28Aug`, `28/ago`, `1set`, `15DEC` — separator optional, month any prefix of three letters or more in English or Spanish (no three-letter prefix reaches two months); an explicit year wins.

**Rejected.** *A bare numeric `28/08`* — `1/2` in a title would silently become a date; the month must be letters. *A four-row key block* — costs the peek four rows. *A live checklist legend* — declined for a row that is the same every time you look.

## A sparse line is a ledger row under `@Pendiente` (2026-09-12)

**Decision.** (1) **A ledger row needs an account, an amount and a date**; title, category, tags and note are optional. (2) **An empty category files the row under the `@Pendiente` system category** (`system_key = 'pending'`, its name fixed and delete refused by the engine), which **counts** in every total, grid and balance. Naming `@pendiente` explicitly is allowed, so a row can be sent back to pending. (3) **A date ahead of today is refused**; **an unknown `#tag` is refused**; **a titleless row shows a dash** everywhere. (4) **A line is accepted or refused**: the LOG bar's `↵` stages it or shows the reason under the bar ([route.py](../expense/quickadd/route.py)). (5) **The category cell alone carries the pending state** — no marker column.

**Rejected.** *A draft table that does not count toward totals* — the money is missing from every figure until promoted; this is what made capture heavier than a spreadsheet. *A `pending` flag on the row* — a second axis every client must know, and it allows a real category plus the flag. *Accepting future dates* — a balance holding next week's rent reads wrong today. *Defaulting a missing title to the category or account name* — invented text indistinguishable from typed text. *An `UNTITLED` placeholder* — a lie the ledger carries.

## Bank downloads are matched against the ledger, not hashed (2026-09-12)

**Decision.** The TUI import door brings BCP `.xlsx` downloads in ([expense/bank_import/](../expense/bank_import/)): (1) **It asks which account, every run**; nothing is remembered by file name, because a browser re-download (`… (1).xlsx`) is a new name. The engine files each row under the currency of its own `Moneda` (contract: POST /v1/transactions/import, "Accounts"). (2) **The engine reads and matches**: the download is sent whole, a dry run first, then the same call with `dry_run: false`; the app reads no cell of it. Titles play no part in matching (contract: POST /v1/transactions/import, "Matching"). **More rows beats fewer**: there is no amount-only rule, because a duplicate shows up at reconciliation and a missed row is invisible. (3) **A day whose file total and ledger total disagree is a report, never an action**; the ledger lines no file row claimed stay out of that month's reconciliation, where the owner deletes them. **A row a day off its ledger line is new**, and the leftover line's day shows as disagreeing. (4) **The title is the bank's text**; the client writes no description, the owner's notes field. (5) **New rows land under `@Pendiente` and `#Pendiente`**, and classification stays manual, in Home's bulk keys. (6) **Every row of the file goes in, whatever its date.** (7) **The unclaimed ledger lines are signed by the app in one helper**, since the engine sends them unsigned and declined a signed copy (contract: "Base Conventions", "Sign convention — responses"); a guard keeps it the only place a sign is read off the type ([runtime.md](runtime.md) "Read semantics").

**Rejected.** *Content-hashed ids* — blind to rows already in the ledger from the sheet or the LOG bar. *Matching a row one day off* — it can claim the wrong line on a busy card. *A client-side matcher*, or *reading the download in the app and sending its rows* — every client would carry its own copy. *Splitting a file over 500 rows across calls* — a later call's row could be claimed by one an earlier call just created. *A `--since` floor* — the owner wants every row of the file in. *A cleaned merchant name as the title* — the title is what the bank sent. *Merchant memory or category suggestions* — classification stays manual. *Detecting transfers, card payments or ITF* (`TRAN.CTAS.PROP.BM`, `PAG.T.PROP.VISA.BM`, `IMPUESTO ITF`) — they import as ordinary rows, classified by hand. *Import provenance and undo* — a wrong-account import is fixed with bulk `b` in Home. *A per-row override in the preview* — every verdict is a fact, not a guess (contract: POST /v1/transactions/import, "Matching"). *Other banks or CSV* — BCP only; the bank's PDF comes in only as a month's statement. *A one-time title alignment before the first import* — every row the bank files overlap already carries the statement's wording.

## The TUI import door — a drop is text, read up front, asked every time (2026-10-02)

**Decision.** (1) **A dropped or pasted path is recognised as text** by one pure function
([dropped.py](../expense/tui/dropped.py)): the terminal types the path, so no mouse tracking or
emulator hook is involved. Terminal.app's backslash escapes and VS Code's quotes are both read.
**A line counts as files only if every word is an existing `.xlsx` path**; otherwise it stays
quick-add, so a half-recognised line never imports some files and stages the rest. VS Code's
terminal inserts one file per drop, so several files at once work in Terminal.app only.
(2) **Every file's bytes are read before any screen opens**; only a file the app cannot read
from disk keeps the LOG bar where it is, noted `can't read the file · …`, and nothing is sent.
Whether a file is a bank download is the engine's call: it refuses one that is not, on `file`. (3) **Three full screens**
(account list, preview, result) replace one another above the bar, built on the shared steps of
[flow.py](../expense/bank_import/flow.py) and the reasons of [engine.py](../expense/bank_import/engine.py). (4) **The account is asked every time** (see "Bank downloads
are matched against the ledger" (1)). (5) **`esc` cancels this file and every later one**,
because `esc` means cancel everywhere in the app; a file already imported stays imported. (6) **The days that disagree are the
ledger after the import**, as the engine computes them (contract: POST /v1/transactions/import),
so a movement typed on another day shows up rather than hiding as a silent duplicate.

**Rejected.** *Remembering the account per file name* — a browser re-download is a new name.
*Splitting quoted paths glued together by repeated VS Code drops* — it reads the line in a way a
shell would not. *A "rename to the bank's wording" offer after apply* — the note names the day;
deleting the extra row is one key in the ledger. *A separate error screen for a non-BCP file* —
the bar is where the right file gets dropped next.

## Home is the month — a live list, `⏎` is the filter, and bulk edits are select + one key (2026-09-12)

**Decision.** (1) **Home is a live list off the one `/dashboard` read**: categories (see "Home draws four months"), then accounts and people, **each account's row with a line per currency under it, each balance in its own currency, never summed**, then LEDGER, MANAGE and SYSTEM as always-open section headers with every screen a row. A failed read is one dim row with the reason. (2) **`⏎` on a row pushes Transactions with a `LedgerFilter`** — the engine's own `?category_id=` / `?account_id=` — crumbed `Ledger ▸ NAME`. (3) **Bulk is select + one key**: `space` selects, `a` selects every loaded row, `c` / `b` / `h` open the bulk pick for the selection (or the cursor row) — a full screen listing the rows it changes above its bar, since a surface that carries rows is a screen and a pop-up only asks — and write **one `PUT /transactions/{id}` per row on its own worker**, then reload. A refused row is named by number and does not stop the others — which is why this is not `run_write`'s drop-on-error queue. The one refusal that ends a run is missing settings ("Missing settings stop a multi-write run"). (4) **Changed rows leave a filtered list at once**; the toast is the receipt. (5) **`esc` clears a selection, otherwise pops the screen** — the filter is the door, not a state. (6) **Hashtags replace the set** (the engine's `hashtag_ids` semantics); an empty apply is refused rather than read as "clear every tag". (7) **`@Pendiente` is pickable**, so a wrong bulk pick can be undone.

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

**Decision.** (1) **`u` swaps an open account's reconciliation panel** for that account's bank lines in no reconciliation, one row per line in the bank's columns, oldest first ("A split transaction is reconciled and deleted whole"); `esc` swaps back. (2) **`⏎` opens the edit form** (wrong date or wrong account is the usual cause) and **`d` deletes after a confirm** that says a delete is final. (3) **A `!` flag** marks a row whose date falls inside a period the screen already holds — a hint, never a ruling. The flag compares the ISO date prefix of the row's `date` in the client, while the engine treats a period as whole calendar days in the user's timezone (contract: "Base Conventions", "Calendar days"). They agree only because every live row is stored at 00:00 America/Lima, which has no daylight saving; nothing enforces midnight. The bank import sends no dates: the engine dates each row it creates, or moves to the bank's day, 00:00 of that day in the user's timezone (contract: POST /v1/transactions/import). **The first writer that stores a real time of day makes the `!` wrong near midnight**, and that is the point to write an engine ask for a per-row flag. (4) **No "tick all, then complete"**: `space` files rows one at a time so the difference updates before you seal. (5) **The ledger's bulk refusals read one line per kind of error**, as every save of several rows does ("Refused rows read one line per kind of error").

**Rejected.** *"Tick all N, then complete"* — a non-zero difference never blocks completion, so one keypress could seal a month that does not add up. *A filtered ledger with an `unreconciled` filter* — reconciliation work belongs in the reconciliation view. *Parsing the period name out of refusals to group them* — rows are grouped by the engine's code, fields and reasons, never by its words.

## The transaction list pages by cursor (2026-09-23)

**Decision.** `GET /transactions` pages by bookmark (`next_cursor` → `?after=`, `null` is the end), `?sort=date_asc` starts from the oldest, and the count is its own read, `GET /transactions/count`, asked once when a list opens or after a write. The client treats the cursor as opaque and never builds one, since the engine refuses a cursor it did not issue (contract: "Base Conventions", "Cursors, on every cursor-paged list"); it drops it whenever the filter or sort changes, and walks forward only. Every list is one of three shapes ([runtime.md](runtime.md) "Three list shapes"). The engine owns paging and the count, which is the case behind CLAUDE.md's "Ask the engine to change" rule.

**Rejected.** *Offset paging* — a list that shrinks while you file rows silently skips rows. *A probe-then-offset-then-reverse read for oldest-first* — two reads, a race at the page edge, and a pattern every client would copy.

## Deleted is deleted (2026-09-23)

**Decision.** A delete is final from every client: there is no restore and no way to list deleted rows. The engine still soft-deletes, so `GET /activity` keeps the history; **undoing a delete is an operator task** (contract: "Base Conventions", "A delete is final"). Delete prompts are unchanged.

**Rejected.** *A restore in this client only* — a write no other client has. *A "recently deleted" view* — a list shape for a rare operator action.

## Activity and Rates leave the TUI (2026-09-23)

**Decision.** Activity and Rates have no screens; they are among the engine features with no screen in "The TUI is the only surface".

**Rejected.** *Porting both screens to date windows* — a second paging model for two unused screens.

## Long lists grow, they do not page (2026-09-25)

**Decision.** The ledger and the "no batch" pane are **one list that grows**, both through `GrowingRead` ([_growing.py](../expense/tui/screens/_growing.py)): **10 rows** to start; `pgdn` **appends** the next 10 with the cursor on the first new row; `↑↓` scroll everything loaded; `pgup` moves up a screenful with no read; a resize fetches nothing. The caption reads `N of M loaded`.
- **Rows and count load together; a missing count fails the whole list** — never rows beside a guessed total.
- **After any write the list starts over**: `+`, an edit, `c` / `b` / `h`, `d` and `r` read the first 10 fresh with the cursor on row 1. A refused bulk row stays selected only if the fresh read brings it back.

**Rejected.** *Page swapping* — a cursor cannot say "page 3 of 11", and a resize either loses your place or repeats rows. *Keeping the loaded depth and cursor after a write* — the owner wants the plain reload. *Keeping an off-screen refused row selected* — the next bulk key would change a row you cannot see.

## Reconciliations opens on the accounts (2026-09-25)

**Decision.** The screen opens with **the accounts alone** and reads nothing. `⏎` on an account reads its statements (`GET /statements?account_id=`, whole, in the engine's order: [tui.md](tui.md) "The Statements browse") and opens the panel under it; `esc` closes it. `u` works only inside an open panel. Returning from a statement reads the account's list again and lands on the same row; the statement's screen reads its statement by id, and a `404` is how it knows the statement was deleted.

**Rejected.** *Reading on cursor pause* — a read per pause for a screen whose next step is always `⏎`. *Reading every account's list at open* — grows with the account list.

## Reconciliation periods are days (2026-09-26)

**Decision.** A period's `date_start` / `date_end` are **bare `YYYY-MM-DD`**, both required; the engine refuses anything else. The TUI form checks the date **at the field** with `is_calendar_day` ([dates.py](../expense/dates.py)) — zero-padded, a real day — and sends it unchanged. The tick-list passes the period's days straight into `date_from` / `date_to`.

**Rejected.** *The LOG bar's forgiving dates* — a statement's dates are copied off paper. *`date.fromisoformat` alone* — accepts `20260831`, which the engine refuses.

## Delete anything that no longer points anywhere (2026-09-25)

**Decision.** A removed flag, command or code path is deleted outright — **no stub, no friendlier message**: a removed command gets Typer's own "No such command". Test fakes use the engine's real shapes (`whole()`, `cursor_page()` in [tests/unit/helpers.py](../tests/unit/helpers.py)) and refuse what the engine refuses. Guard: `test_command_surface.py` pins the typed surface.

**Rejected.** *A stub that explains the removal* — a second copy of the engine's change that lives forever. *Keeping a dead branch "in case"* — unreachable code is untested; git history keeps old behaviour.

## Sealed periods: the engine guards, the client reports (2026-09-20)

**Decision.**
- **The engine is the only guard.** No client checks a seal before a write or caches completed windows (they change under `revert`). The `!` flag and the bank import's `sealed` rows only report.
- **Only a date, account or currency change can hit a seal**: of the bulk keys only `b` and `m` can be refused by a seal; `c` and `h` stay legal inside a sealed period. The LOG bar names the sealing period on the refused row and still saves the rest; the bank import shows such a row as `✗ Closed period` and imports the rest.
- **`revert` shows nothing extra.**

**Rejected.** *A client-side seal check* — a copy of an engine rule, stale the moment another client reverts. *A "close every month" bulk command* — would seal months nobody reviewed.

## The agent loop: one per repo, the main session orchestrates (2026-09-27)

**Context.** The owner is not a coder. Work runs through agents that build, check and commit without asking about each task, while the owner keeps what users see, money rules a spec does not cover, and real data. The rules live in [CLAUDE.md](../CLAUDE.md) "How work runs (the agent loop)"; this entry holds the why.

**Decision.** One loop per repo, the worker definitions shared from `~/.claude/agents/`, each repo's rules in its own CLAUDE.md; the main session orchestrates and never writes code or tests; the tester never writes tests; the loop runs on its own once the owner approves a spec's tasks. The rules themselves: [CLAUDE.md](../CLAUDE.md) "How work runs (the agent loop)".

**Why.** "Done" (tests pass, committed and pushed) only means something inside one repo, and a loop per repo keeps the wall between this client and the engine automatic. Every change is written by one agent and read by another, so nothing is approved by the agent that wrote it; the same holds for a tester that would otherwise write the test it then checks. Pushing after each task runs GitHub's checks on each one. A fresh practice key per check leaves nothing stored. A fact written in two docs drifts, which is why the librarian exists.

**Rejected.** *One loop over the whole `productivity_world` folder* — "done" stops meaning anything across repos and the client–engine wall stops being automatic. *Checking in with the owner after every task* — the questions would be technical ones the owner hands back to the agents anyway.

## Review per task, test and align once per spec (2026-09-27)

**Decision.** Each task runs builder → reviewer → commit and push; the tester's acceptance check and the librarian's sweep run once per spec ([CLAUDE.md](../CLAUDE.md) "Per task", "Per spec").

**Why.** The commit hook already runs the unit tests on every commit, so a per-task tester only repeated them; its real value is the real engine and checking criteria rather than tests, which one pass per spec covers. Docs drift slowly, so one sweep at the end catches what per-task passes did. Reading is cheaper than testing, so the reviewer goes first.

**Rejected.** *Tester and librarian after every task* — most of their time goes on re-running what the commit hook checks and on small follow-up rounds. *No tester at all* — nothing else runs the app against the real engine or catches a criterion the tests miss.

## The engine is learned only from its live contract (2026-09-28)

**Decision.** This repo learns how the engine behaves only from `GET /openapi.json` on the practice engine, read live; no copy of the contract is kept, only its version ([runtime.md](runtime.md) "Contract version"). A moved version stops the loop and goes to the owner. Docs and comments cite the part of the contract that states a rule, and no agent reads a file in the engine's folder ([CLAUDE.md](../CLAUDE.md) "Key documentation", "Stay inside this repo").

**Why.** Reading the engine's folder broke the rule that agents stay inside this repo, and the web and iOS clients never see that folder: they have only the published contract, so this client validates the same thing they will use. A saved version with the engine's own change log says *that* the contract moved and *what* moved, without keeping a copy that goes stale.

**Rejected.** *Keeping a copy of `openapi.json` in the repo* — it drifts, and each client would keep its own. *Accepting a moved version automatically* — an engine change would slip into the ledger's client unreviewed. *Reporting a change as the fixtures that no longer match* — it says what this repo's test data got wrong, not what the engine changed.

## Hints are chosen by the engine's reasons, never its wording (2026-09-28)

**Decision.** Every engine error carries `error.reasons`, one code per field in `fields` (contract: "Error reasons"). The app chooses every hint from those codes, and from the status and error code, never from `message` or `fields` text; `EngineError` keeps them next to `fields` ([errors.py](../expense/errors.py)). What people see does not change: the engine's message, each field's message and the hint, with no codes on screen; `expense import sheet --json` passes the engine's envelope through verbatim, codes included ([commands.md](commands.md) "Output conventions").

**Why.** The engine publishes its message wording for people and changes it without notice; a hint keyed to words breaks silently on a rewording, and web and iOS would copy the same fragile match. Reason codes are part of the published contract, listed per operation, so a change to them moves the contract version and reaches the owner.

**Rejected.** *Showing the codes on screen* — the codes are for code; people read the engine's words and the hint. *Keeping the wording matches as a fallback* — two ways to decide the same thing, one of them unreliable.

## A move to another account takes the row out of its reconciliation (2026-09-30)

**Context.** A reconciliation holds only rows on its own account. The engine refuses a write that changes a row's account while the row sits in a draft reconciliation, unless the same write says what happens to the assignment (contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id}). In the TUI a row changes account from its edit form or with `b` on the ledger.

**Decision.** Both paths send `statement_id: null` with every account change, so the move goes through and the row leaves its old reconciliation. A row kept on its own account sends no `statement_id` and keeps its reconciliation. A short note says so: `Saved. It left its statement.` in the edit form, `3 rows → Caja Chica · PEN · 2 left their statement` after `b`. The old reconciliation is on the old account and cannot hold the row any more; reconciling the new account assigns it there in the usual way.

The counts are the engine's: each move's answer lists every part of the bank line it changed and whether each left its reconciliation (contract: PUT /v1/transactions/{transaction_id}, "Response"), and the note counts the distinct parts listed across the answers that landed. A move that changes nothing shows no note. A line field reaches every part of a split transaction, so one request can move several rows, and two requests on one line can list the same rows; only the engine knows what moved.

**Rejected.**
- Asking each time whether to unassign or to assign into a draft on the new account: a new screen for a choice whose second answer is the normal reconciling flow anyway.
- Counting the requests sent, or deciding "left" from the rows read before the save: wrong for a split transaction, and a guess where the engine's answer says.
- Reading the line again after a move to learn what changed: an extra round trip for what the answer already holds.
- `0 rows → <account>` when nothing moved: a note about nothing.

## Missing settings stop a multi-write run (2026-10-11)

**Context.** Before first-time setup the engine answers `422 SETTINGS_MISSING` on every request its settings preconditions name (contract: "Base Conventions", "Settings preconditions"). The LOG bar save and a bulk edit each make several writes in one run, and a `422` on a batch normally names its bad rows, so the batch settles them and sends the rest again ([runtime.md](runtime.md) "Bulk writes").

**Decision.** `SETTINGS_MISSING` is about the account, not a row: the first one ends the run, is reported once with its hint, and nothing further is sent. `LIMIT_REACHED` with reason `LINE_CODES_EXHAUSTED` ends a run the same way: once the line codes are used up, every write that needs a new line is refused (contract: POST /v1/transactions/batch), so the row it names fails in the engine's words and nothing further is sent. Both are one predicate in [expense/errors.py](../expense/errors.py), next to the hint's one home.

**Rejected.** *Settle it like any other `422`* — `SETTINGS_MISSING` names no row, so every row would carry the same four-line error and every later chunk would draw it again; `LINE_CODES_EXHAUSTED` names one row a send, so the run would spend one request per row to fail them all.

## The practice engine serves only the engine's shipped code, and only a listed version is recorded (2026-10-28)

**Context.** The engine coders work in the same checkout the practice engine runs from. A practice engine started from that working tree serves their unfinished work, including contract versions that never ship, and fails to restart while the checkout is mid-edit.

**Decision.** The practice engine is started only by the engine's own client practice launcher, which exports the engine's last commit and runs it from that export ([runtime.md](runtime.md) "Working against the live engine"). The drift script records a contract version only when the served contract's own change log lists it, since an engine running unreleased work serves versions the log never lists (contract: "Base Conventions", "The contract"); a missing or malformed log records nothing ([runtime.md](runtime.md) "Contract version").

**Rejected.** *Starting uvicorn from the checkout with its own Python* — it serves whatever the checkout holds, half-built work included. *Trusting the served version alone* — a draft looks like any other version until it never ships.

## A list's order is written in the contract's words, in one home (2026-10-12)

**Context.** The contract states each list's order with its direction: accounts come every real account first, then every person, each group by `sort_order` ascending, then creation time, oldest first (contract: GET /v1/accounts, "Ordering"). Every client shows a list as the engine returns it.

**Decision.** A doc or comment that states a list's order uses the contract's wording, including the direction, and cites it; each order has one home and other places link there ([tui.md](tui.md) "The Statements browse" for an account's reconciliations). `test_list_orders_state_their_direction` in [test_docs_links.py](../tests/unit/test_docs_links.py) fails on an SQL-style order and on a cited order without its direction. No screen sorts a list the engine orders.

**Rejected.** *SQL-style shorthand* (a column name followed by a sort keyword) — it names columns the contract does not publish and reads as knowledge of the engine's insides. *Stating the order wherever the list appears* — the copies drift.

## The unit suite pins its terminal size (2026-10-12)

**Context.** Typer prints a usage error in a box as wide as the terminal, and the width comes from the shell's `COLUMNS` or the window. The commit gate runs the unit suite in whatever session commits.

**Decision.** An autouse fixture in [tests/unit/conftest.py](../tests/unit/conftest.py) sets every test's terminal to 80×24, so the suite's result does not depend on the shell or the window ([runtime.md](runtime.md) "Unit tests never touch the network").

**Rejected.** *Loosening each assertion to survive wrapping* — every new test would have to remember it.

## The tag picker is one full list, narrowed by typing (2026-10-13)

**Context.** The LOG bar's `#` lists every tag. The engine can also say which tags a category's transactions use, most-used first (contract: GET /v1/categories/{category_id}/hashtags).

**Decision.** `#` shows every tag in the order the engine lists them, read once from `GET /v1/hashtags`, and typing keeps the tags whose name contains the text, case- and accent-blind, in that same order ([quickadd/names.py](../expense/quickadd/names.py)). The list is the same whichever category the line names; the app sorts and merges nothing. The category-tags endpoint has no screen; the contract suite exercises it ([test_category_hashtags.py](../tests/contract/test_category_hashtags.py)).

**Rejected.** *A category's own tags first, a divider, then the rest* — two groups need a second order, and each client would pick its own. *The engine sending that two-group list* — declined by the engine coders: with one list there is nothing to merge. *Hiding the tags a category has never used* — any tag may go on any category. *A typed command listing a category's tags* — the TUI is the surface in use.

## Completing a statement asks for every balance it needs first (2026-10-30)

**Context.** The engine refuses to complete a statement with a balance not entered, and drafts take an empty ending balance for when the paper has not arrived and a blank beginning balance when a line in a new currency joins (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered"). It also refuses a currency with money at the start the statement does not cover (contract: POST /v1/statements/{statement_id}/complete, "Every currency with money at the start has balances in it").

**Decision.** `c` on a draft with any blank balance opens a box for each one, `Starting balance first` then `Ending balance first`, currency by currency; after the last box one write saves them all, naming only the currencies that change, and then the usual question asks, where only `y` completes ([tui.md](tui.md) "A statement's screen"). A refused complete that names a balance, or a currency with money at the start, opens the same boxes for the currency the engine names; which currency needs a balance is always the engine's call. Saving and completing stay two writes and two answers, so balances can be saved without completing. A refused write keeps the screen's usual note titles (`Couldn't save`, `Couldn't complete`), and a refused save closes the box, because the note already says what to do. No statement was completed without its balances, so the app offers no revert-and-fill path.

**Rejected.** *One box that saves and completes on a single `enter`* — completing is the step that seals rows, and it keeps its own `y`. *Refusing `c` with the engine's words only* — the user then has to find where the balance is typed. *A `Failed` title for this flow* — the screen's other refusals say `Couldn't …`.

## The Statements screens read whole at 80×24 (2026-11-03)

**Context.** The statement screens are read against the bank's paper, at the smallest terminal
the app plans for ("A terminal too small is the user's to fix").

**Decision.** (1) **Only a completed statement on an account with a statement code is
numbered**: the numbers are the paper's places, and an open statement, or an account with no
paper, has none. (2) **An open statement on an account with a statement code waits for its
PDF**: no ticking and no `c`, since the PDF closes it ("A card's statement is one statement, and
a month closes from the bank's PDF"). (3) **Lists page rather than scroll**: the browse's panel
takes the rows the accounts leave, its caption measured as it wraps, so `#content` never
scrolls and no scrollbar cuts a column; the lines in no batch, a growing list, draw no page line
([tui.md](tui.md) "The Statements screens fit 80×24"). (4) **On an account with a statement code
the statements list's columns sit one space apart, and on every account the name is the column
that gives way**, cut with `…`: the order and the figures are what the list is read for. An
account with no code keeps two spaces. (5) **A footer that cannot fit its keys tightens its
spacing before it cuts one** (`FittingFooter`). (6) **`c`'s boxes open under the head**, with
the balances they ask about in sight.

**Rejected.** *Cutting the order word* (`not in …`): it is the column the list is read for.
*Cutting every name to fit*: ordinary names would lose their month. *A centred box over the
balances*: it hides the figures it asks about. *Scrolling the screen*: its scrollbar cuts the
last column.

## A create leaves an empty colour to the engine (2026-10-15)

**Context.** A create with no colour gets the engine's default, and an update still refuses a null one (contract: "Colour format").

**Decision.** New Category and New Account make colour optional, and a skipped colour is left out of the body. The sheet import sends no colour for the categories it creates, so they take the engine's default. While an optional colour line is empty, no swatch is highlighted, so the screen never shows a pick that `enter` will not make ([tui.md](tui.md) module map, `create_forms.py`). Edit Category keeps its colour required.

**Rejected.** *A palette the client cycles through for imported categories* — a client-side copy of a choice the engine makes. *Highlighting the first swatch on the empty line* — `enter` there skips the colour, so the highlight shows a pick that does not happen.

## The unit suite runs in parallel by default (2026-10-16)

**Context.** Run serially, the unit suite is several times slower, and the loop runs it on every task.

**Decision.** `addopts = ["-n", "auto"]` in pyproject.toml, so the tests gate, CI and hand runs all run in parallel; pytest-xdist is a required dev dependency. It sits in addopts because pytest-cov reads `-n` before any conftest loads, so only addopts or the command line give CI a parallel coverage run.

**Rejected.** *An opt-in `-n` flag:* the gate and CI would not get it. *Setting `-n` from a conftest hook:* pytest-cov does not see it and crashes.

## Live contract runs stay in one process (2026-10-16)

**Context.** The contract tests share one practice user and make real writes, and one of them seals periods that others write into.

**Decision.** tests/contract/conftest.py and tests/conftest.py answer `-n auto` with zero workers for any live run, however it is started; only an explicit `-n N` overrides them.

**Rejected.** *Letting the default parallel run spread them:* they would race on the shared user and the sealed periods.

## The whole unit suite runs once per task, and docs never trigger it (2026-10-22)

**Context.** Without a gate a task runs the whole unit suite three or four times on the same code: at the builder's stop, at commit, and by hand. Common practice keeps commit-time checks fast, runs the full suite once when the work is done, and keeps CI as the safety net; build tools such as Bazel never re-test code that has not changed since it passed.

**Decision.** The tests gate skips pytest on code it has already passed, and docs are left out of what it compares, so a docs-only change runs no tests; a doc edit that breaks a test that reads docs is caught by the librarian's docs-link run or by CI after the push ([tests_gate.py](../.claude/hooks/tests_gate.py)). The guard blocks a builder, reviewer or librarian running the whole suite by hand, enforcement by tooling, since written instructions do not hold.

**Rejected.** *Running only the tests a change can affect (`pytest-testmon`):* once the gate skips unchanged code the builder's stop is the only full run, and testmon would move it to commit, where a failure costs a round trip, and add a data file that can go stale; revisit past about 90 s. *Running the doc-reading tests on a docs-only change:* a list of doc-reading tests to keep in step, for a check CI already makes. *Keeping docs in the fingerprint:* the orchestrator edits docs between the builder's stop and every commit, so the commit would rerun the suite on nearly every task.

## The practice engine has one script, run in exact shapes (2026-10-16)

**Context.** Sending a tester just to start or stop the practice engine added an agent round trip to every task that needed the contract live. The start's output carries both practice users' keys, which must never reach a file.

**Decision.** `scripts/practice-engine up|down` starts, reseeds and stops the `:8002` engine, and any agent may run it; the orchestrator runs it around tasks. The guard allows only the whole command in a few exact forms, so the key stays off disk, and the script takes no options and inherits no environment, so nothing the caller sets can point it at the live engine or the real ledger ([scripts/practice-engine](../scripts/practice-engine)).

**Rejected.** *Keeping the start tester-only:* slow. *A script that takes options or inherits the environment:* one variable could reach the real ledger.

## Engine changes arrive as one catch-up file and leave as one reply (2026-10-17)

**Decision.** One hand-off file covers every contract change since the version this client last caught up to; it becomes catch-up specs and is deleted, and each catch-up spec ends with a reply naming the version caught up to, how each check went and any contract problems found ([from-engine/README.md](from-engine/README.md), [to-engine/README.md](to-engine/README.md)).

**Why.** One range per catch-up leaves no gap and no double work. The spec holding everything makes it stand alone, so the hand-off file adds nothing once the spec exists. The reply closes the loop: this app is the contract's first real user, and the engine coders learn what held up before the web and iOS clients build on it.

**Rejected.** *One file per engine change:* overlapping ranges and gaps. *Keeping the hand-off file until the spec retires:* two homes for the same facts.

## An ask leaves the outbox once it is handed over (2026-10-24)

**Decision.** An ask is deleted when the owner says it is handed over, as a reply is ([to-engine/README.md](to-engine/README.md)); whatever here waits on it names it by title.

**Why.** The outbox lists only what the owner still has to carry, so nothing goes to the engine twice. The engine's copy and git history keep the ask's text, and the work waiting on it keeps its title in sight.

**Rejected.** *Keeping each ask until a hand-off answers it:* the folder no longer tells the owner what to carry, and an ask the engine already holds gets carried again.

## The bank import's preview is one table: a mark and a reason per file row (2026-10-18)

**Decision.** (1) The preview lists every row the engine read, numbered by its spreadsheet
row, each with a **mark** and a **reason** from a short fixed list, the reason alone on
the row ([tui.md](tui.md) "The import door"). (2) **✓ means the row is in the ledger after the
import** (new, already there, or changed); **✗ means it needs looking at**: left out, or a move
to the bank's day stopped. (3) **A move to the bank's day is one more "Modified existing
transaction"**; the counts line says how many move. (4) **A move stopped by a completed
reconciliation is ✗ `Not moved: <statement> is completed`**: with a reconciliation done
right the bank's day and the ledger's agree, so the row points at a reconciliation completed
wrong. It says "not moved", because the bank's title and operation number still land on it
(contract: POST /v1/transactions/import). (5) **The days where the file and the ledger disagree
stay on the preview only**; after importing, the screen gives the counts alone. (6) The stopping
statement is named by one read of it by its id (contract: GET /v1/statements/{statement_id}),
since the engine keeps a reference to another record an id alone and declined to put the name in
the import's answer. (7) **A row of `0` is marked `·`, `Skipped: amount 0`**: the engine never
matches or creates it, so it is neither ✓ nor ✗. (8) **On a card, a `cur` column** names the
currency the engine filed the row under.

**Why.** A reason per row from a fixed list takes a new engine behaviour as one more reason,
instead of a new suffix or note, each with its own wording questions.

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

**Why.** The engine moves and renames rules between versions without changing behaviour, and a
citation that no longer
resolves sends the next reader looking for a rule that is not where it says. A name-and-place
check is mechanical, so it is a test, not a sweep someone has to remember.

**Rejected.** *A hermetic unit test over a saved copy of the contract* — no copy is kept ("The
engine is learned only from its live contract"). *Checking only that each quoted name appears
somewhere* — a rule moved to another tag would still pass while the citation sends readers to
the wrong place.

## A form never sends `null` where the engine refuses it (2026-10-18)

**Decision.** The Edit form sends `null` only for the fields the engine clears with it
(`statement_id`, `title`, `operation_code`); an emptied note is sent as
`description: ""` (contract: PUT /v1/transactions/{transaction_id}). A unit test empties every
field of both Edit forms and fails on any other `null`.

**Why.** An explicit `null` is `NOT_NULL` on every other field, so a `null` there is a refusal
the owner did nothing to cause. Pinning it field by field keeps a new field from bringing the
bug back.

**Rejected.** *Leaving an emptied note unsent* — the old note stays, and the owner's emptying is
silently lost.

## An archived account's frozen writes are not offered, and a refusal is the engine's words (2026-10-18)

**Decision.** The engine freezes an archived account: of its transactions only the category,
hashtags and note change and an empty title or operation code is filled once, and its
reconciliations don't change (contract: POST /v1/accounts/{account_id}/archive). The app reads
`is_archived` from the accounts read each screen already makes and stops offering what the
engine would refuse: (1) the ledger hides `d` on such a row and draws the row as any other,
while `s` stays ("The Edit form's keys and words name what it does"); (2) the Edit form shows
read-only the fields the line's `edit_limits` names, with the engine's sentence saying why, and
offers no `^n` or `^x` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"); (3) a
frozen change sent anyway shows the engine's words alone; (4) the Reconciliations screen lists
only active accounts. The engine still judges every write.

**Why.** Offering a key the engine always refuses invites a refusal for nothing, and every
client would meet it. Reading the engine's own flag keeps the rule in the engine: the app adds
no judgement of its own, and a failed accounts read only puts the keys back for the engine to
refuse. The engine's refusal already says to unarchive first, so the app adds nothing to it.

**Rejected.** *Dimming the archived account's rows* while some of its lines still change —
the owner keeps the ledger as it is. *A line naming where to unarchive* — the engine's words
say it. *A question that unarchives and retries* — it would make unfreezing a side effect of an
edit. *Listing archived accounts on Reconciliations, read-only* — nothing there can change.

## The sheet import brings a split purchase in as one split transaction (2026-10-22)

**Context.** One bank movement split across categories is several rows in the owner's sheet,
and the rows of one movement share a `COD_EECC` (`SIG-202603-029`). The sheet has no column for
the engine's bank line or the bank's operation number, so `COD_EECC` is the only way to tell from
it which rows were one movement.

**Decision.** (1) **Rows sharing a `COD_EECC` come in as one split transaction**, grouped by the
engine, which reads the whole sheet (contract: POST /v1/transactions/import-sheet); the app
shows the count the engine sends ([commands.md](commands.md) "`expense import sheet`"), and the
groups are checked in the app after the import. (2) **`COD_EECC` only groups**: a movement's statement line gives its place in the statement's order and comes only
from a reconciliation. (3) **Letter case counts in a `COD_EECC`:** `SIG-1` and `sig-1` are two
movements. This is the owner's rule for every match: a field a person types, a
name, is matched without regard to case; a field from the bank or a program, an operation code
or a statement code, is matched exactly. A bank file's operation numbers are compared the same
way.

**Rejected.** *Keeping `COD_EECC` as each line's statement line* — a statement line comes only
from a reconciliation, and 2,275 hand-typed codes in the ledger would clash with the ones a
reconciliation makes. *Creating each month's reconciliations and their statement order at the
import, read from `COD_EECC`* — reconciling is the owner's call, made later.
*Folding case in a `COD_EECC` or an operation code* — they come from a program, not a person,
and a client that folded them would merge two movements the engine keeps apart. *Listing every
group on the dry run* — the owner checks them in the app.

## The sheet import creates its names in a step of its own, and a dry run never writes (2026-10-27)

**Context.** The engine reads the whole sheet and writes everything or nothing, but it never
creates a name, and it answers a dry run's counts only once every account, category and hashtag
the sheet uses has an id (contract: POST /v1/transactions/import-sheet, "Names"). On the
official import into an empty ledger every name is new.

**Decision.** `expense import sheet` runs in three steps
([commands.md](commands.md) "`expense import sheet`"): (1) the dry run lists every name as
`yours` or `missing`, with no counts while one is missing, and names the step that creates
them; (2) `--create-names` checks the sheet with a dry run, then creates each missing name and
imports nothing, so a refused sheet creates nothing, after which the dry run shows the engine's
counts; (3) `--apply` writes the import, and is refused, naming the step, while a name is still
missing, so the owner always sees the counts before anything is imported. The counts name the
split transactions and the sheet rows they hold, both as the engine counts them, so three splits
of eight rows never read like three of six (contract: POST /v1/transactions/import-sheet, "Response").

**Rejected.** *A dry run with no counts* — the owner would see the numbers only after the
one-time import. *A dry run that creates the missing names* — a preview that writes. *`--apply`
creating what is missing* — an import made without its counts seen. *A command of its own for
the step* — `import sheet` stays the only command.
*The app counting the split rows itself* — only possible after an apply, and the grouping is the
engine's rule.

## A person carries an opening balance (2026-10-28)

**Context.** A person is someone the owner lends to or borrows from, and the balance on their
account is that debt. When tracking starts with someone who already owed, or was already owed,
that starting debt is an opening balance, as on a bank account.

**Decision.** A person's opening balance is judged by the engine exactly as a bank account's
(contract: POST /v1/accounts/{account_id}/opening-balance), and the app treats it the same way:
a person's Edit form shows a `<CODE> opening` and `<CODE> as of` pair per currency after the colour, through the same code as a bank
account's, and `t` turns an account into a person keeping its opening balance
(contract: POST /v1/accounts/{account_id}/make-person). The statement code line stays off a
person's New and Edit forms, though the engine takes a code on a person
(contract: "What an account is", "A person carries a code like any account").

**Rejected.** *A person's opening balance only from the sheet import* — a starting debt is a
balance like any other, and the app would have no way to set or fix one by hand.

## An account becomes a person, and back, with one key (2026-10-22)

**Context.** The owner's sheet records loans the way the app does: every movement with a person
is mirrored in an account named after that person, and its balance is the debt (ALEJO, ALONSO,
LC, ALEX, LIDIA, MATILDE, CARLOS and KORAKUEN, each in one account per currency). The sheet
import creates every sheet account as a bank account.

**Decision.** (1) **The owner turns an account into a person in the app,** not in the import:
`t` on Manage ▸ Accounts sends make-person or make-account at once, with no question, since it
is reversible and keeps the account's id, name, currencies, balances and transactions
(contract: POST /v1/accounts/{account_id}/make-person). The cursor stays on the account in its
new group, and the note says what it became, so a second `t` turns it back. (2) **A refusal is
the engine's words.** An account's opening balance goes with it both ways, since a person
carries one as a bank account does (see "A person carries an opening balance"). A person never
has statements, since a statement checks the ledger against a bank statement and a person sends
none. The engine refuses `t` on an account that has ever been in one, a deleted one included
(contract: "Error reasons"), and `HAS_RECONCILIATION` shows in the engine's words alone. (3) **The sheet import never matches names itself:** the
engine proposes an existing account for each sheet name
(contract: POST /v1/transactions/import-sheet), so a re-run after a conversion is the engine's
to match.

**Rejected.** *Teaching the import which sheet names are people* — a list to keep in step with
the sheet, while a plain account action also fixes any account created as the wrong kind.
*Asking before `t`* — nothing is lost, and `t` again undoes it.

## A hint says what `⏎` does there, and a note names what the app can't read (2026-10-24)

**Decision.** (1) **A bar form's hint says "enter to save" only where `⏎` saves**, and "enter to
go on" where it moves on; a guard test walks every bar form ([tui.md](tui.md) "The bar forms'
keys"). (2) **A non-date on the Edit form's DATE is refused at `⏎`**, in the words of the app's
other dates. (3) **The LOG bar names a signed amount it can't read** rather than saying it needs
a sign.

**Why.** A hint or note that says something the screen does not do teaches the wrong key, and
a typo must never close the app and lose what was typed.

**Rejected.** *Refusing a bad date only at save* — the note would come after the line is left,
where every other line of the form is checked at `⏎`.

## Refused rows read one line per kind of error (2026-10-22)

**Decision.** When a save of several rows is refused, the LOG bar's lines under the table and the ledger's bulk `c`, `b` and `h` note read one line per
kind of error, from one shared helper: the field the engine names, its
words, then the rows it hit (`date: Must not be null. row 77`, `rows 3, 5, 7`). Rows are one kind
when the engine's code, fields and reasons for them are the same, never by its top-level message,
which counts the items.

**Rejected.** *One line per row* — a refusal that hits many rows repeats itself line after line.
*The engine's words alone* — its words are often general (`Must not be null.`), so two lines
could read the same with nothing to say which field each is about. *Grouping by the top-level
message* — it carries a count, so one kind sent twice would read as two.

## The Edit form saves a whole line in one write, and the engine says what is locked (2026-10-25)

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
and the engine's sentence for it** ("Notes keep the engine's words, and a read-only line says
why").

**Why.** One write lands whole or not at all, so a save never leaves a line half-edited, and a
retry under the same key never applies twice. The engine works out `edit_limits` with the write's
own rules on every read, so the form can never offer what the write would refuse, and every
client reads the same answer instead of keeping its own copy of the rules.

**Rejected.** *A transaction's own write for an opening balance's or an archived account's line*
— two write paths for one form, and the second takes a different set of fields. *One write per
part* — a chain that can land halfway. *Reading the line's reconciliation to decide what is
locked* — an extra read, and a copy of the engine's rules in the client.

## Notes keep the engine's words, and a read-only line says why (2026-10-26)

**Decision.** (1) **Every note shows the engine's words as text**: a toast whose words the app
did not write is shown with styling off, and words set inside the app's own styling are escaped
exactly, so a `[` in them never hides part of the message; a guard test refuses a toast that
would read them as styling. (2) **A read-only line on the Edit form says why, in the engine's
sentence**: each line field keeps its `read-only`, one line under them gives each distinct
sentence once with the lines it covers, and each part column's `read-only` line carries its
sentence after a `·`. The sentence is the `message` of the line's `edit_limits`, the same words
the write refuses that field with
(contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). (3) **A refusal that stops a run of writes reads the same everywhere**, from one
helper. (4) **The question before completing a reconciliation names all six things it locks.**

**Why.** The engine's words are its contract with every client; text that vanishes or is
restyled is a lossy copy of them. The engine sends the reason for each lock in words, so every
client shows the same sentence and none keeps a table of its own from code to words that could
drift from the engine's. One problem reading one way on every screen is easier to learn.

**Rejected.** *A table in the app from each reason code to a sentence* — a copy of the engine's
wording in every client; the engine sends the sentence instead. *The sentence beside every
read-only line* — the same sentence three times on a line in a completed reconciliation. *A
second sentence in the complete question saying what still changes* — longer, and the Edit form
shows it.

## A list shows a name as the engine holds it, `[` and all (2026-10-27)

**Decision.** Every list cell that holds a name or a title is drawn as plain words, never read
as styling: one helper, `list_cell` in
[cursor_list.py](../expense/tui/widgets/cursor_list.py), draws a cell the app styled (a swatch, a
coloured amount, a mark) as built and anything else as words, and every table goes through it,
the ledger, Manage ▸ Accounts, the reconciliation tick list and the LOG bar's staged rows among
them; Home's balances and the bank import preview build their names as words too. An account
named `BCP [like this]` shows as `BCP [like this]` everywhere. The guards are
[test_tui_bracketed_names.py](../tests/unit/test_tui_bracketed_names.py) and
[test_toast_words.py](../tests/unit/test_toast_words.py).

**Why.** A name is the owner's words, held by the engine; a list that hides part of it shows a
different name from the one every other client shows. One helper for every cell means a new list
gets this by default, instead of each screen escaping its own names.

**Rejected.** *Escaping each name where a screen builds its row* — every new list would have to
remember it, and one that forgot would lose text silently.

## The Edit form's keys and words name what it does (2026-10-25)

**Decision.** (1) **`s` stays on an archived account's ledger row and opens the Edit form as `⏎`
does**; only `d` leaves the footer there, and the form reads what is read-only from the line's
`edit_limits` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). (2) **The words
follow the form**: the ledger's footer reads `s Edit`, and a refused part names its field by
the parts table's column word (`part 1 (category)`), from one mapping derived from the table's
columns (`FIELD_WORDS` in [parts_table.py](../expense/tui/widgets/parts_table.py)). (3) **An
opening balance's hashtag refusal on the Edit form shows the engine's words alone**; "Leave the
opening balance out of the selection." stays on the ledger's bulk `h`.

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

## A card's statement is one statement, and a month closes from the bank's PDF (2026-10-25)

**Decision.** (1) **A card's month is one statement** covering every currency of the account,
and every write acts on the whole statement
(contract: "Statements", "Every write acts on the whole statement"). (2) **An account lists its statements from one
`GET /statements?account_id=`**, one row per statement, each currency's balances from its entry
in `balances`; what the row shows is in [tui.md](tui.md) "The Statements browse". (3) **The
statement line is never shown**: it only keeps a statement's lines in the paper's order. (4)
**No screen orders a statement, ticks the lines it still needs or edits a statement's name and
days, or its balances beyond the blank ones `c` asks for at complete.** A month's statement
can be opened before its PDF and stays open until the PDF arrives; uploading it closes the
month, the engine reading, matching and completing ([tui.md](tui.md) "A statement PDF closes its month").
(5) **The PDF writes what the ledger lacks and never changes or deletes what the paper lacks**:
a line the ledger lacks is created under `@Pendiente`, a line the paper lacks is taken out of
the month or flagged and never stops the close, equal lines on one day are matched one to one, a card's undated charges are each a
transaction on the statement's last day, and an installment purchase is one transaction a
month, as the bank bills it (contract: POST /v1/statements/import).

**Why.** A statement is one thing on paper, so it is one row and one write. The owner checks a
month against the bank's PDF, not by linking rows one at a time; the PDF already holds each
currency's balances, every line and the paper's order, so reading it replaces every hand step.
Writing exactly what the paper holds makes every statement add up to the paper, while a line
the owner logged that the paper lacks stays for the owner to judge.

**Rejected.** *A heading per statement with a line per currency under it* — three lines a month
show a third as many months. *A screen to put a statement in order with `shift+↑↓`, the lines
still to tick under it, and an `e` form for the name, days and balances* — each is a hand step
the PDF does. *Ticking lines into an open month by date as they are imported* — with no ending
balance before the PDF there is nothing to compare them against.

## The suites copy the engine's answers and leave the practice user as they found it (2026-10-25)

**Decision.** (1) **The unit suite's fake engine answers a write in the engine's shape**,
through answer builders marked with the endpoint they stand for, which the drift script checks
([runtime.md](runtime.md) "Fixture drift"). (2) **Every request body a unit test sends is
checked for the fields the engine sets itself**, which it refuses in every body. (3) **Every live
contract test fails when it leaves an account, category or hashtag it made** ([runtime.md](runtime.md)
"Leftovers"). (4) **Engine-side probes use a practice user of their own**, never the one this
client's suite and hand checks use. (5) **The create form's begin balance hint says a statement
holding the opening balance begins at 0.00.**

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

## A held reserved name is the engine's words alone, proven on each side (2026-10-25)

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
*Faking the state on the shared practice user* — the engine allows no way into it.

## A close flags lines instead of refusing, and a statement is the account's (2026-10-26)

**Decision.** (1) **Completing a statement goes through when it adds up, and the app shows the
lines the close flagged** on a screen of its own, pushed right after the complete, in one list,
each line opening in the Edit form or deleted after the question; back on
the statement, a `⚑` line under the header and `f` open the list again while flagged lines are
left (contract: POST /v1/statements/{statement_id}/complete).
Nothing in the app treats leftover lines as a refusal of complete, and it keeps no rule of which
lines a close flags. (2) **The screen reads the flagged lines as the statement's review list**, opened on the
statement's id with no id sent, and its count is the engine's on the same filter
(contract: GET /v1/bank-lines, "It has no bound"); the request is in [tui.md](tui.md) "The lines
a complete flagged for review". The
`⚑` count after a close, and whether the screen opens, are that count too, never a sum of the
close's `review_lines`: the review list also holds earlier lines in no statement, so a sum can
disagree with the list it opens. The screen reads the count first and its head shows it before
the lines arrive: it shows sooner and is still the engine's number. (3) **A statement is
the account's**: it covers the currencies the account holds, and the statement code is the
account's (contract: "What an account is", "Statement code"), never a match of statement codes
across accounts. (4) **The "no batch" list explains its `!` as `! dated inside a statement`**: a
close flags such a line instead of being blocked by it. (5) **The practice engine's second key,
the reserved-names practice user's, is handled like the first** ([runtime.md](runtime.md)
"Working against the live engine").

**Why.** Which lines a close leaves behind is an engine rule; a copy in each client drifts. A
line dated in a statement but in none is often a later statement's, so stopping the close on it
would block the owner for a line that is fine. A screen right after the close shows them while
the owner is on the statement, and the engine's review list reads them again at any time, in the
statement's order, so no client reads them one by one or sorts them itself.

**Rejected.** *One read per flagged line, sorted by the app* — a call per line and an ordering
rule copied in each client. *The flagged lines listed on the statement itself* — they sit among
the statement's own lines, where each needs keys of its own. *Dropping the `!` mark* — it points
at the lines worth opening first.

## A statement PDF comes in through the import door, and its preview is the check (2026-10-27)

**Decision.** (1) **A month's PDF is dropped on the LOG bar**, as a bank download is, and its
account is picked from the download's own list; several files dropped together go one by one,
each its own way. A file's kind is its name's ending alone, and the engine judges what is inside
(contract: POST /v1/statements/import). (2) **Both uploads send one body**, built in one place, since the contract gives both routes the
same three keys, and their screens share one preview and one result screen; what differs is
what each shows. (3) **A `CONCURRENT_CHANGE` on the apply leads to a fresh preview, never a
resend**, whatever key the engine names, because the contract says to send it again after the
ledger moved. (4) **The preview is the check against another account's PDF**: the engine does
not compare the paper's number with the account picked, and a wrong paper shows almost every
row as new before anything is written. (5) **The upload's small details follow the download's
screens.** (6) **The live suite makes its statement PDFs itself**, with no PDF library: savings and card
papers drawn to the contract's stated layout, beside the engine's published samples. (7)
**A statement's balance lines follow the engine's order**, the account's currency order
(contract: POST /v1/statements/import, "Response"): every client shows the same order, and the
app sorts nothing.

**Why.** Every file from the bank then comes in through one door, so there is one place to learn.
The engine reads and matches the paper, so the app only sends it and shows the answer. A preview
shows a wrong file before anything is written, and checking numbers belongs to accounts carrying
them, a spec of its own. A test PDF needs fixed-width text at exact points, which a few lines of
the suite's own code write without adding a dependency.

**Rejected.** *Soles first on a card, whatever the accounts' order* — the app would reorder what the
engine sends, and each client could order it differently. *Starting the upload from the statement on
Reconciliations* — a key and a path field on another screen, for what a drop already does. *A
PDF dropped only on its own* — a month's download and its PDF could not go in together.
*Keeping the tick-list on an open statement of an account with a statement code* — ticking
cannot close the month there. *Waiting for accounts to carry their numbers* — closing statements
would wait on account names.

## An account holds its currencies (2026-10-28)

**Decision.** A bank account, or a person, is one account that holds one or more currencies: a
Peruvian credit card holds soles and dollars, and ALEJO owes in both. The engine's holder becomes
the account, with its name, colour, order, kind, statement code and archived flag; each of the
engine's per-currency accounts becomes one currency of it, keeping only its currency, opening
balance and balance, so amounts in two currencies are never added up. A currency has no name or
colour of its own: it shows as the account's name and its currency ("VISA Infinite Sapphire ·
USD").

**Why.** The owner always works with the holder, and the per-currency account was only a vehicle
to keep currencies apart, yet it carried a name, colour, order, kind and archived flag of its own
and moved between holders. Two levels that both act as an account made pairing, unpairing,
person holders, a holder of one account and "the whole holder" rules, each a thing every client
would have to teach. Every multi-currency ledger keeps an account and a balance per currency in
it; making the holder that account keeps both levels and drops the duplication.

**Rejected.** *Keeping holders and per-currency accounts, shown as one in the app* — every client
hides the same split, and pairing, unpairing and person holders stay for the owner to use.
*Renaming holder to account and account to currency, nothing else* — a currency keeping its own
name, colour, kind and move keeps the duplication under new names. *One account mixing
currencies in one balance* — a total across currencies has no meaning.

## An account shows once and its currency is a field of its own; one currency shows, several are picked (2026-10-31)

**Decision.**
- **An account shows once.** Manage ▸ Accounts has one row per account with a column per
  currency. Home has the account's row and a line per currency. Every account picker lists the
  account alone. `d` names the account and each currency with its balance
  (`Prueba · bank · PEN 0.00 · USD 0.00`), since a delete removes them all.
- **The currency is picked as its own field,** like any other field:
  - the LOG bar's `%` token;
  - the Edit form's CURRENCY line;
  - the ledger's `Cur` column and its filter (Home's `⏎` on a currency line);
  - the ledger's `m`, which moves selected rows to another currency.
- **One currency shows, several are picked.**
  - **Typing or editing:** an account holding one currency asks for none and its currency is
    just shown, dim on the Edit form. An account holding several makes the person pick: a LOG
    bar line with none picked is not staged, and an account change on the Edit form empties the
    currency and stops `ctrl+s` until one is picked.
  - **Moving rows with `b`:** to an account holding one currency, every row takes it, the amount
    as it is (no conversion). To an account holding several, each row keeps its own.
- **A currency move keeps a draft statement; an account move takes the row out.** A currency
  move sends the statement's own id, and an account move sends `statement_id: null`, as the
  engine leaves the assignment to the client
  (contract: "Statements", "Assigning transactions").
- **The app fills an account's only currency itself** in three places, listed once in
  `currencies.FILLS_AN_ONLY_CURRENCY` and guarded by a test, until the engine ask "An account's
  only currency is taken when a write names none" lands. `currencies.only_currency` is the
  display rule and stays.
- **The LOG bar's staged list has a `Cur` column of its own,** as the ledger has: the currency is
  its own field on every list.
- **The currency's words follow the patterns already in use** on every screen, and a hint names
  the currency only when the currency is the whole story ([tui.md](tui.md) owns the words); the
  engine keys each refusal on each field sent
  (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put").

**Why.** In the engine an account holds its currencies and a transaction names both, so the
screens show the account the owner thinks of, once, and the currency where it is chosen. Asking
for a currency an account cannot have is a question with one answer. Moving rows to a
one-currency account cannot keep their currency, so they take its, and the owner's rule is that
an amount moves as it is. A row moved within its account still belongs to the same statement;
one moved to another account does not.

**Rejected.**
- *One row per account and currency everywhere* ("<account> · <code>"): it splits the account the
  owner thinks of into pieces.
- *The currency typed after the amount* (`-45.50 USD`): a field of its own is picked like every
  other field, and the legend names it.
- *A second pick for `b` asking every row's currency:* to a two-currency account each row's own
  currency is already held, and `m` is the currency's own key.
- *Converting the amount on a currency move:* the app holds no rates, and the owner moves an
  amount as it is.
- *`d` naming one currency with a line saying the others go too:* it hides the balances the
  delete removes.

## The PDF upload and the two imports send the account (2026-10-30)

**Decision.** (1) **Both import doors list one line per bank account**, named by the account with
its currencies in the engine's order (`VISA Infinite Sapphire   PEN + USD`, one shared
`formatting.currencies_phrase`), and send the account's id alone; the engine files each row, and
each balance of a statement PDF, under its own currency. (2) **The PDF preview shows a balance
only for each currency the engine's answer covers.** (3) **The sheet's names table lists each
account name once**, its currencies in the CUR column; `--create-names` makes one account per missing name holding the currencies its rows use, two
names the engine holds as one made once. (4) **A rename is the sheet's name alone**,
`--account-name SHEET_NAME=LEDGER_NAME`; a saved key written with a currency (`BCP:PEN`) is read
by its name, keys of one name going to two ledger names stop the run before anything is written
until `--account-name` for that name replaces them, and two sheet names may be renamed onto one
account, the engine judging what may share it ([commands.md](commands.md) "`expense import
sheet`"). (5) **A statement is one per account**, covering its currencies
("A close flags lines instead of refusing, and a statement is the account's").

**Why.** An account holds its currencies (contract: "Bank Accounts", "`currencies`"), so a
name in the sheet, a pick in a door and a statement are each the account's.

**Rejected.** *Renames per name and currency* — a name is one account now, and the engine reads
each row's currency from the sheet. *The client refusing two names onto one account* — the
engine allows it and is the one to judge. *A rename typed as `Caja:USD` kept as typed while a
saved one is read as `Caja`* — a rename that holds for one run only; a sheet name ending in a
colon and three capitals cannot be renamed.

## The live suite makes every record one way (2026-10-30)

**Decision.** Every live contract test makes its records and checks its refusals through the
shared helpers in [tests/contract/conftest.py](../tests/contract/conftest.py), and one cleanup
removes what it made; a test file keeps no copy of a helper. A test's account has no statement
code unless the test is about codes, since a coded account's statement must be ordered before it
completes.

**Why.** One way of making records means one place to change when the engine's shapes change,
and cleanup that cannot drift from what was made.

**Rejected.** *Local body builders and refusal checks per file* — each copy drifts, and a check
that only finds the field's name somewhere in the answer proves less than the contract states.

## A live test's data passes only for the reason it states, and the suite tests the contract as it stands (2026-10-31)

**Decision.** (1) **A live test's data can pass only for the reason the test states**: a test of
an order uses rows whose stated order differs from date order, and a test that something is left
alone puts a look-alike beside it. (2) **A case the live contract no longer states is dropped,
not ported.** (3) **Where the engine and its contract disagree, the suite tests neither side**:
it tests what both agree on, and the disagreement goes to the engine in the catch-up's reply.
(4) **Where the contract leaves a detail open, the suite accepts every answer it allows**, and
the question goes in the reply. (5) **A case no request can build is tested as what the contract
says it equals, or left out with its reason.**

**Why.** A test whose data a wrong engine also passes proves nothing. A case the contract dropped
pins behaviour the engine is free to change. Pinning the engine where it breaks its contract
makes the suite defend the bug, and pinning a detail the contract leaves open fails the day the
engine picks another allowed answer.

**Rejected.** *Porting every old case onto the new shapes* — it keeps rules the engine no longer
states. *Pinning what the engine does today where it breaks its contract* — the suite would fail
the day the engine is fixed.

## A screen's live test reads through the screen's own read (2026-11-03)

**Decision.** A live test of what a screen lists calls the read the screen itself calls, with the
same filters and order, through one function both call (`fetch_month_lines` in
[reconciliations.py](../expense/tui/screens/reconciliations.py) for a statement's lines).

**Why.** A test that rebuilds the screen's arguments keeps passing after the screen changes what
it sends, and then proves the old screen: a list the screen reads oldest first stays tested
newest first.

**Rejected.** *Testing the engine's filters alone, with the client's raw calls* — that proves the
engine, not this client's use of it, which is what the live suite is for.

## A live test dates a recent row and reads its month from one moment (2026-11-02)

**Decision.** A live test that needs a transaction dated now logs it a minute ago in the
practice user's display timezone, and a test that reads the month of a row it logged takes both
from one clock reading; a new transaction's body and an opening balance's each come from one
helper (`Scratch` in [tests/contract/conftest.py](../tests/contract/conftest.py)).

**Why.** Noon today is in the future before noon, and the engine refuses a future date. Two clock
readings straddle a month's turn in its first minute. A minute taken off the wall clock lands,
after a daylight-saving jump, on an hour that does not exist. One body shape means one place to
change when the engine's shape changes.

**Rejected.** *Dating recent rows at noon of yesterday* — the reports' tests need a row in the
current month, which yesterday is not on a month's first day.

## A list's one-write guard belongs to the write that set it (2026-11-02)

**Decision.** On Manage ▸ Accounts, `a`, `t`, `c` and `x` send one write at a time: a key
pressed before that write's aftermath does nothing. The guard is tied to the write that set it
(`ResourceListScreen.run_guarded_write` in [_base.py](../expense/tui/screens/_base.py)): it
lifts when that write is refused, when it is dropped behind another write's refusal, or when the
list builds from a read begun after it was answered. Nothing else lifts it or keeps it set.

**Why.** The list a key acts on must already show the write before it: a second `c` read from
rows fetched before the add offers the currency just added again, and the engine refuses it. A
reload of its own (`r`, a form closing) can land at any time, with rows read before or after
the write, and a refused write queued behind (`d`) never reloads, so only the guarded write's
own aftermath says when the list is fresh.

**Rejected.** *Lifting the guard on every build* — `r` mid-write lifts it with stale rows.
*Lifting it on a build with no write unanswered* — a refused `d` queued behind it never reloads,
and the guard stays set until the list is read again.

## What a spec finds becomes a spec only if the owner would see it (2026-11-02)

**Decision.** What a spec's run finds along the way becomes a new spec only if the owner would
see it in the app or it is a money or business rule; the rest goes to [todo.md](todo.md)'s
Backlog ([CLAUDE.md](../CLAUDE.md) "Specs and tasks", "Per spec").

**Why.** When every find is a spec, every finished spec leaves a smaller leftovers spec, and
leftovers leave leftovers. Each spec costs the owner an approval and the loop a tester and a
librarian run, which internal tidy-ups do not need one by one; the specs that need the owner get
lost among them.

**Rejected.** *Every find a spec* — the list never shrinks. *Merging the small leftovers into
one cleanup spec* — it still asks the owner to approve work they cannot see, and keeps growing.

## The staged list's title and tags give way; OPERATION says it changes every part (2026-11-02)

**Decision.** When the LOG bar's staged rows are wider than the bar, the title and tags give
way and every other cell keeps its whole width ([tui.md](tui.md) "The LOG bar's account is one
row per account"). The OPERATION line says it changes every part of the transaction, as the
date, title, account and currency lines do.

**Why.** A staged row is checked before the save: the amount, currency, account and category are
the cells read, while the title is what was just typed. The operation number belongs to the
whole line as the date does.

**Rejected.** *Title, category and tags share the cut* — similar categories read the same
once cut. *OPERATION without the note* — the one line of the five that changes every part
without saying so.

## The PDF preview marks a line moved to the bank's day (2026-10-28)

**Decision.** On the statement PDF's preview, a matched row whose ledger line the engine moves to
the paper's day (its `redated`) reads `✓ In the ledger · day moved`, with no old day and no count
(contract: POST /v1/statements/import, "The bank's day wins"); the app draws the engine's
`redated` as sent and decides nothing ([tui.md](tui.md) "A statement PDF closes its month").

**Why.** The row is in the ledger like any matched row; a short mark says the line moves without
a second read and without a taller row.

**Rejected.** *A dim line under the row naming the day it moves from* — the app would read each
moved line by id to show a day the close is about to change, and every moved row takes two
lines. *Nothing on the rows, only a count under the table* — you see how many lines move, not
which.

## Every screen's frame: no blank lines at the crumb, refusals under the form, `+` on incomes (2026-11-03)

**Decision.** (1) **The crumb has no blank line above it or under it**: crumb, rule, one blank
line, content, on every screen. (2) **A form's refused save is a block under the form**,
`▌ Failed` and the engine's words, kept until the next key, on every form; every form leaves one
blank line under its hint when no suggestion list shows, so the block fits 80×24.
(3) **`^s` keeps what is typed in the bar as `⏎` would, then saves**; a line nobody typed on
keeps nothing. (4) **A long crumb is cut with `…`** and the `!` rate alert always shows after
it. (5) **`pgup Prev` leaves a list's footer on its first page.** (6) **A positive transaction
amount is written with its `+`** in every list; balances, totals and sums write no `+`
([tui.md](tui.md) "Amounts").

**Why.** Each list gains two rows, which is what lets the Statements screens fit 80×24 as
drawn. A toast fades before its words are read or the line is fixed. A value in the bar is what
the user sees as typed, and leaving it out drew a refusal for a value they had given. A footer
offers only keys that act. The sign stays explicit both ways with colour off, as "Sign is always
literal" holds for typing; a balance or a sum is not a transaction, and the drawings
write them bare.

**Rejected.** *Keep the blank lines* — two rows fewer on every list. *Keep the toast* — it
fades. *`^s` sends only lines entered with `⏎`* — the engine refuses the save for the missing
value. *`^s` also keeps an untouched line* — on a choice line `⏎`'s reading picks the first
account or colour for the user. *`+` on balances and totals too* — the drawings write them
without one.
