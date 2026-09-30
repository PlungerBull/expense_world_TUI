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
| CLI is a thin wrapper / contract validator for the multi-client engine | [CLAUDE.md](../CLAUDE.md) "Product scope and role" |
| Server-first writes, no offline queue | [CLAUDE.md](../CLAUDE.md) "Tech stack" · [cli-runtime.md](cli-runtime.md) "Write semantics" |
| PAT auth (`ewe_pat_` prefix) | [cli-spec.md](cli-spec.md) "Auth model" |
| Public GitHub repo → secrets never enter the repo | [CLAUDE.md](../CLAUDE.md) "Config isolation" |
| Sanctioned deviations from the principles | [cli-spec.md](cli-spec.md) "Sanctioned exceptions" |
| Rates cross the wire as integers (`rate_e8`, the rate × 10^8), so every client does exact integer maths with no float drift | (contract: GET /v1/exchange-rates) |

## What a half-written batch means (2026-08-25)

**Context.** The LOG bar saves every staged row in one `POST /transactions/batch`, through [expense/batch_write.py](../expense/batch_write.py). A batch can partly fail.

**Decision.** (1) **A successful save stays on the screen**: written rows show a `✓` and are cleared the moment the next line is staged, so the list only ever holds rows about to be written. (2) **A partial failure ticks what landed and retries only the rest.** Failed rows keep their marker and the engine's message; `ctrl+s` covers only rows without a `✓`. This is safe because **`row_id` is minted at stage time and reused on every attempt** — a row whose response was lost replays as `409`, which the save reads as *written*. (3) **`ctrl+s` never touches an unstaged line in the bar** — `↵` is the only thing that stages. (4) **The discard card's `ctrl+s save first` saves and then leaves, unless the save fails**, in which case the screen stays so the error can be read. The row's **`date` is frozen at stage time** too, so a batch saved across midnight does not change day. A saved row cannot be lifted back into the bar — correcting a written row is the edit form's job. The chunk-then-singleton batch mechanics are shared with the `.xlsx` importer in `batch_write.py`, not copied.

**Rejected.** *Dismiss on success* — throws away the confirmation. *Keep ticked rows until you leave* — mixes history with intent and the per-currency total stops describing the batch. *Re-send the whole list on retry* — safe, but hides a partial failure behind a wall of 409s. *Auto-stage the bar's line on save* — writes something unfinished. *Save and stay after `esc`* — the user pressed `esc`.

## Four calls for the LOG bar (2026-08-25)

**Decision.** (1) **A staged row comes back as the raw line you typed** (`↑↓` pick, `↵` lifts it into the bar) — nothing is re-rendered, so line and row can never disagree. (2) **The staged table keeps its `tags` column.** (3) **The batch totals per currency** — never adds PEN to USD: `3 to the ledger · -45.20 PEN · -96.00 USD`. (4) **A refused line's reason reuses [route.py](../expense/quickadd/route.py)'s own phrases**; the flat `expense log` prints the same strings — one wording, one place. The date cell shows the year whenever it is not the current one, because the staged list is the echo that makes two-digit years safe.

**Rejected.** *Rebuild the line from the row* (names spelled out) — a second formatter that drifts from the parser and loses typed text. *Drop the tags column for width* — tags are half of why a line is typed. *A second, shorter wording for the reasons* — a phrase table that drifts from route.py.

## Two calls for the one-line `expense log` (2026-08-25)

**Decision.** (1) **One rule on both surfaces**: [quickadd/route.py](../expense/quickadd/route.py) decides whether a line is accepted or refused (see "A sparse line is a ledger row"); the flat command exits 1 on a refused line. An ambiguous name counts as no name, and the candidates are printed. (2) **The command always echoes the parsed row and asks before writing**; `--yes` skips. The grammar is forgiving (`18/8/26`, `hoy`, `$sig`) *because* the resolved row is always shown before it is committed — in the TUI the staged list is that echo; in the flat command the prompt is. The prompt lives in [log_cmd.py](../expense/commands/log_cmd.py), never in `expense/quickadd/`, so the TUI does not confirm twice.

**Rejected.** *Write, then echo, with `--dry-run` to look first* — the check is skipped exactly when typing fast. *Prompt only when something was inferred* — an unpredictable prompt trains you to dismiss it.

## Three quick-add grammar rules (2026-08-25)

**Decision.** (1) **Names match on "contains, anywhere"**, accent- and case-blind ([quickadd/names.py](../expense/quickadd/names.py) `fold()`, shared by every picker). An exact name wins outright, longer phrases are tried first (`#caja chica` before `#caja`); zero or several hits leave the token unresolved with its candidates for a picker. (2) **Dashed ISO dates are accepted** (`2026-08-18`) because `--date` takes that shape everywhere; dashes stay ISO-only, so `18-08-2026` is not a date. (3) **An unmatched `#tag` is refused, never created.**

**Rejected.** *Whole-name or starts-with matching* — fails the common case of typing the distinctive middle word. *Slash dates only* — a user who types dashes everywhere else would silently get title text. *Create unknown tags on save* — a typo becomes a permanent tag. *Swallow an unknown tag as title text* — loses it silently.

## Sign is always literal — no default-to-expense magic (2026-04-25)

**Decision.** The sign is explicit end-to-end in every UX layer: `20` is income, `-20` is expense. An amount whose sign is ambiguous gets a prompt or an error, never a guess. No exceptions.

**Rejected.** *Default an unsigned amount to expense* (offered, declined) — hidden behaviour that diverges from what the engine stores and forces the parser to infer intent.

## Dual-UX strategy — flat commands + TUI + quick-add (2026-04-25)

**Decision.** Three surfaces over one implementation: **flat commands** (canonical, scriptable, the contract-validator surface), the **TUI** `expense world` for management and discovery, and the **quick-add grammar** for capture (`expense log` and the LOG bar). Every interactive action goes through the shared fetch/write layer. `expense` with no args prints group help.

**Rejected.** *Interactive-first* (slower for capture, unscriptable); *folding flat commands under the interactive surface* (kills scripting and testing); *a second interactive surface beside the TUI* (every feature built twice).

## Mockup-first, and showing ≠ approval (hardened 2026-05-24)

**Decision.** Every user-facing view or table change starts with an HTML mockup in [mockups/](mockups/), and **presenting mockups is never authorization** — implementation waits for an explicit pick, even in auto-accept mode and even when a follow-up sounds like consent. A prior session's approval is not a standing license. Full rule: [CLAUDE.md](../CLAUDE.md) "Mock every screen before building it".

**Rejected.** *Treating an earlier approval as durable*; *inferring layout or columns from the response shape* — scannability is the owner's judgment.

## The open-work list holds only open work (2026-07-06)

**Decision.** [todo.md](todo.md) is a working list, not an archive: closed items — and whole finished docs — are deleted; git history is the archive.

**Rejected.** *Append and keep* (closed items get re-read forever); *a separate archive doc* (a second home for what git already keeps).

## Manage detail: system categories are editable, not immutable (2026-07-07)

**Decision.** The TUI offers `e` (rename/recolor) on system categories (`@Opening`, `@Pendiente`). The engine resolves them by an immutable `system_key`, never by name, so renaming is safe and allowed; delete is refused by the engine. The client mirrors the engine: it offers what the engine accepts.

**Rejected.** *Hide `e` on system categories* — client-invented business logic. *Ask the engine to refuse `PUT` on them* — a false consistency that throws away rename/localisation.

## TUI writes: FIFO queue in EngineWriteMixin, error drops the queue (2026-07-08)

**Decision.** `EngineWriteMixin.run_write` ([_base.py](../expense/tui/screens/_base.py)) owns a per-screen FIFO: exactly one request in flight, order preserved. **A failed write drops the queued remainder** — those intents were decided against a screen state the engine just contradicted; the error callback resyncs.

**Rejected.** *Per-screen queues* (N copies of one race fix); *cancelling in-flight writes on supersede* (thread cancellation cannot stop a request, and the idempotency key already covers retries); *continuing past a failure* (later writes may depend on the failed one). Independent bulk writes use their own worker instead — see "Home is the month".

## Connection errors get exit code 6, off the click collision on 2 (2026-07-10)

**Decision.** Exit codes: **1** engine rejected the request, **3** config, **6** connection; **2** belongs to click's usage errors alone. A new meaning gets a fresh code, never an overloaded one; 4 and 5 are retired and not reused. Source of truth: `_ENVELOPE_ERRORS` in [expense/errors.py](../expense/errors.py).

**Rejected.** *Sharing 2 with a distinguishing message* — scripts branch on the code, not prose. *Renumbering to be contiguous* — churn for cosmetics.

## TUI paints the terminal's own background — ANSI mode (2026-07-11)

**Decision.** The app runs in ANSI mode (`ansi_color=True`, [app.py](../expense/tui/app.py)) and the base fills (`Screen`, `#menu`) are `ansi_default`, so the app and the terminal's window padding are one surface on any terminal. Guard: `test_base_fills_are_terminal_transparent`. The foreground half is "The terminal supplies the palette".

**Rejected.** *Match a fixed hex* — correct on one terminal profile only. *Fix it in the terminal profile* — pushes a code-owned problem onto every machine.

## Archive is a prompt-free toggle; Manage lists have no record detail (2026-07-11)

**Decision.** (1) **The Manage lists are the whole surface** — no record-detail screen: `e` opens the prefilled edit form, `a` archives/unarchives the cursor row (accounts only), `enter` is a no-op. (2) **Archive is a reversible toggle, not a destructive operation**: no confirm modal in the TUI, no prompt and no `--yes` on the flat `archive`. Only delete/revert/clear are confirm-gated ([test_command_surface.py](../tests/unit/test_command_surface.py)).

**Rejected.** *A record-detail screen* — repeats the list's columns. *Inline cell editing* — a second edit idiom for three screens. *A confirm on archive* — pure friction on something one keypress undoes. *`enter` as an edit alias* — declined; `enter` stays non-mutating.

## Every data table pages at 20 rows (2026-07-11)

**Decision.** `DEFAULT_PAGE_ROWS = 20` in [_resource.py](../expense/commands/_resource.py), one copy for CLI and TUI. **CLI:** human mode sends `limit=20` on cursor-paged lists via `effective_limit`; explicit flags win; `--json` sends no default and stays byte-verbatim. **TUI:** full-data lists (Manage lists, Reconciliations panes, the tick-list) are display-windowed — the window follows the cursor — at the size set by "TUI rows-per-page adapt to the terminal". The ledger and the "no batch" pane grow instead ("Long lists grow, they do not page").

**Rejected.** *Client-side slicing of engine-paged reads* — the next client must inherit real pagination. *Auto-fetching when `↓` reaches the edge* — holding a key would fire a read per keystroke.

## TUI is keyboard-only — mouse disabled via `run(mouse=False)` (2026-07-12)

**Decision.** `run_world` launches with `mouse=False` ([app.py](../expense/tui/app.py)): Textual never enables mouse tracking, so clicks do nothing and the terminal's native select-to-copy works. Every affordance has a keyboard path. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Rejected.** *Textual's default mouse* — unintended behaviour that blocks native copy. *Per-widget click swallowing* — brittle and still blocks copy.

## TUI rows-per-page adapt to the terminal — min(20, what fits) (2026-07-13)

**Decision.** The page is the screenful, capped at `PAGE_ROWS_CAP` (default 20). `SectionScreen.measure_list_rows` ([_base.py](../expense/tui/screens/_base.py)) measures `#content`'s real height (screens declare their extra lines; `LIST_FRAME_LINES = 6` is the panel frame), floor `PAGE_ROWS_FLOOR = 5`; the first load waits for the first layout pass. The panel always fits, so `#content` never grows a scrollbar nothing could operate. CLI human mode is untouched (stdout has no viewport).

**Rejected.** *A fixed 20 with a scrolling container* — the title and headers scroll away and the scrollbar is undraggable. *Grow-to-fit on every screen* — short lists read worse spread out; only the ledger lifts the cap ("The ledger fills the window").

## The ledger fills the window (2026-08-29)

**Decision.** Transactions sets `PAGE_ROWS_CAP = ENGINE_PAGE_CAP` (the engine's own `limit` ceiling) and `CARD_WIDTH = None`, so the ledger spans the terminal in both directions. Every other screen keeps the 20-row cap and its narrow card. Guarded by `test_transactions_panel_fills_and_fits_the_viewport`.

**Rejected.** *Lifting the caps app-wide* — declined: two short columns spread over 200 columns read worse. *A bigger arbitrary cap (50, 100)* — the engine's ceiling is the only non-arbitrary bound.

## Ledger cells fill their columns — flex text columns, no pre-truncation (2026-09-12)

**Decision.** Rows hand the table whole strings; `CursorList`'s `flex` mapping gives Transactions `{Title: 3, Description: 3, Hashtags: 2}` as Rich ratios. Amount, date, account and category keep their natural width; the text columns split the rest and are ellipsised at their real edge. Column edges depend on the terminal, not on the page's data, so the table never reflows while scrolling.

**Rejected.** *Natural width* — data-dependent layout, and on a narrow terminal Rich trims every column evenly until the amount is a bare `…`. *Bigger fixed caps* — the same bug on a bigger terminal.

## `expense world` clears the terminal scrollback at launch — `CSI 2J 3J H` (2026-07-13)

**Decision.** `run_world` emits `\x1b[2J\x1b[3J\x1b[H` before Textual starts ([app.py](../expense/tui/app.py)), so Terminal.app cannot scroll pre-launch text in above the running app. **Accepted cost (owner-confirmed):** the tab's whole scrollback is wiped on every launch. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Rejected.** *Clear only the screen (`2J`)* — the scrollback still slides in. *Re-enable the mouse to swallow wheel events* — reverts keyboard-only.

## The cursor is reverse video — applied as a Rich style, never as CSS (2026-08-20)

**Decision.** Reverse video is the one "you are here" gesture. Textual 8.2.7 drops `reverse` when both cursor colours are `ansi_default`, and a CSS override is dropped the same way, so `CURSOR_STYLE` ([windowed.py](../expense/tui/widgets/windowed.py)) is applied as a Rich style — `CursorOptionList` applies it in `render_line`. `test_tui_menu_cursor.py` asserts on the **rendered strip**, because the resolved style reported `reverse` throughout the bug: with terminal-owned colours, only rendered output is evidence.

**Rejected.** *A coloured cursor bar* — names fixed colours and gives the menu a different gesture from the lists. *Bold* — already means "pending".

## Opening balances are an engine concept (`@Opening` system category), not a CLI convention (2026-07-20)

**Decision.** `POST /accounts/{id}/opening-balance` seeds a balance as a transaction under the `@Opening` system category (`system_key = 'opening_balance'`, renameable); flow reports exclude it entirely, so no phantom income appears and visible rows sum to net. One per account (409). `expense accounts opening-balance` wraps it; the sheet importer routes rows marked `SALDO INICIAL` in the **title or the category** column to it (deduped per account and currency).

**Rejected.** *A user category plus a naming convention* — invisible to the engine, so reports can never exclude it, and every client invents its own name. *An opening-balance param on `POST /accounts` only* — never fires for accounts that already exist. *Keep the `@Opening` row visible in panels* — visible rows would no longer sum to the total.

## Local-first deployment — the one engine moves to the user's Mac; cloud mothballed until iOS (2026-07-30)

**Decision.** The same engine runs on the owner's Mac (launchd, local Postgres), the daily FX fetch runs as a launchd task, and a nightly `pg_dump` to iCloud Drive is the durability layer. Every architectural invariant holds: one engine, zero client logic, server-first writes. The CLI's only change is `engine_url`. Reactivating the cloud for iOS is a relocation (restore the dump, redeploy, repoint). Ops: the engine's local- and cloud-deployment guides.

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

**Decision.** The engine returns `null` for a home-currency aggregate when any row in the group has no resolvable rate, with an `unconverted_count`. The client renders that as **`3 unrated`** in the cell — never `0.00` and never a native-currency fallback (which would read USD cents as PEN cents). One shared pair, `format_aggregate` / `has_aggregate` in [_resource.py](../expense/commands/_resource.py), backs CLI and TUI. Month cells carry the count, so *no activity* (dim `—`) and *unpriceable* stay distinct. A category with nothing in the report is not drawn; `categories list` and `--json` still show every one.

**Rejected.** *A partial total with a marker* — a half-true number on screen. *`n/a (3)`* — an abbreviation to learn. *A footnote with the count* — loses which row it belongs to.

## Contract tests verify against a disposable database, and refuse the real ledger (2026-08-16)

**Decision.** `tests/contract` runs against `expense_world_test` through a second engine on **`:8002`** (setup: [cli-runtime.md](cli-runtime.md) "Working against the live engine"). The suite **refuses to start** when it would write to the real ledger (`EXPENSE_ALLOW_REAL_LEDGER=1` overrides) — a `pytest_sessionstart` hook, with the `PYTEST_LIVE` gate as a `pytest_collection_modifyitems` hook, because a `pytestmark` in a conftest does not apply to other modules. Fixture drift is checked separately by [scripts/check_fixture_drift.py](../scripts/check_fixture_drift.py).

**Rejected.** *A warning banner instead of refusing* — useless when nobody is watching, which is when it matters. *A separate user in the real database* — the junk still accumulates in production. *The drift check inside `pytest tests/unit`* — the unit suite blocks sockets on purpose.

## A settled person is folded, never hidden — and creating one is a TYPE field, not a `people` group (2026-08-16)

**Decision — creation.** `expense accounts create-person`, and in the TUI a **TYPE field** (`bank` / `person`, prefilled `bank`) first on the New Account form; `person` posts to `POST /people`. `is_person` is never sent — the endpoint is the flag — and TYPE is read-only on the edit form.

**Decision — settled people.** Folded behind a count (`▸ 3 settled`), never dropped — on the flat dashboard and on Home. "Settled" is exactly zero in the person's own currency. `split_settled` / `settled_label` in [_resource.py](../expense/commands/_resource.py) are the single copy. The engine refuses to hide settled people (a repaid loan and an unrecorded one would look identical; a coincidental net zero is two live debts), so the count line keeps the client from silently omitting anyone.

**Decision — archived people.** On the flat dashboard, `--include-archived` adds `archived_people` as its own panel right after archived accounts — two lists, as on every other surface — and it is not folded: the panel is what the flag was passed to see.

**Rejected.** *An `expense people` group* — promises a set of commands when there is exactly one. *`accounts create --person`* — one command posting to two endpoints. *Printing every settled person* — buries the ones you owe. *Naming them on the fold line* — grows until it needs truncating.

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

## One key per job — `j k h l , .` deleted, and the month window moves to `pgdn`/`pgup` (2026-08-27)

**Decision.** No aliases: `j`/`k`/`h`/`l`/`,`/`.` are not bound — a widget alias silently outranks a screen binding, so aliases make letters unusable as commands. `pgdn`/`pgup` mean "the next window of data": on the ledger they grow the list, on Home they slide the month window (`pgdn` goes older). `[`/`]` are bound nowhere. Guards: `test_no_duplicate_movement_key_aliases`, `test_square_brackets_are_not_bound_anywhere` ([test_tui_help.py](../tests/unit/test_tui_help.py)).

**Rejected.** *`←`/`→` for the month window* — Home's rows carry `▶` carets, and `→` on one must unfold it. *`shift+←/→`* — a third tier of arrows for one screen. *Vim aliases as free extras* — free until something wants the letter.

## The LOG bar shows the named account's ledger — elastic, and it stays put (2026-08-29)

**Decision.** Name an account in the line and `AccountPeek` shows its ledger under the staged list: **elastic** (`height: 1fr`, as many rows as the staged list leaves; re-renders on resize), **the bar's account, never a staged row's** (an open picker previews the highlighted candidate; an unresolved token shows nothing), and **it stays on the last account named** after `↵` clears the bar. No balance. One debounced `GET /transactions?account_id=…` per account, cached for the screen; a save invalidates the accounts it wrote to; a failed peek says so in its border and never retries.

**Rejected.** *A fixed 12-row strip* — steals rows from a long batch. *A one-line summary* — does not answer "did I already log this?". *Blanking the peek when the bar is empty* — blinks off at every `↵`. *A navigable peek* — a second cursor on the screen.

## The legend, the two picker gaps, and day+month dates (2026-08-29)

**Decision.** (1) **The grammar legend is a permanent row** (`$account · @category · #tag · ±amount · //note · when     ↵ stages the line`) that never changes; everything that does change lives on the `#hint` row above it. (2) **A bare `$`/`@`/`#` opens the full list** — it stands unresolved carrying every candidate. (3) **Matching is accent-blind** via one `fold()` ([quickadd/names.py](../expense/quickadd/names.py)). (4) **Day + month means this year**: `28Aug`, `28/ago`, `1set`, `15DEC` — separator optional, month any prefix of three letters or more in English or Spanish (no three-letter prefix reaches two months); an explicit year wins. Mockup: [mockups/expense-world-log-legend-and-picker.html](mockups/expense-world-log-legend-and-picker.html).

**Rejected.** *A bare numeric `28/08`* — `1/2` in a title would silently become a date; the month must be letters. *A four-row key block* — costs the peek four rows. *A live checklist legend* — declined for a row that is the same every time you look.

## Importer ids are positional — the sheet is append-only, and `--unreconciled` is the check (2026-09-12)

**Decision.** `expense import sheet` derives each id as `uuid5(IMPORT_NAMESPACE, stable_row_key(row))`, and the key includes the row number — without it, two identical purchases on one day would collapse into one and the second would be lost. So **the sheet is append-only below the last imported row**: insert, delete or re-sort above it and every row below gets a new id and imports twice. The check is `expense transactions list --unreconciled` over the last reconciled period after every import: a duplicate lands outside any closed period, so it cannot hide in `difference_cents`. `--unreconciled` with `--reconciliation-id` is a `422`, not an empty result, because empty here asserts safety.

**Rejected.** *A duplicate-group counter instead of the line* — better in isolation and the fix if the sheet ever must be edited in place; not worth changing every existing id. *An importer guard storing the last row count* — state the CLI does not keep, and a sheet can legitimately shrink.

## A sparse line is a ledger row under `@Pendiente` (2026-09-12)

**Decision.** (1) **A ledger row needs an account, an amount and a date**; title, category, tags and note are optional. (2) **An empty category files the row under the `@Pendiente` system category** (`system_key = 'pending'`, renameable, delete refused), which **counts** in every total, grid and balance. Naming `@pendiente` explicitly is allowed, so a row can be sent back to pending. (3) **A date ahead of today is refused**; **an unknown `#tag` is refused**; **a titleless row shows a dash** everywhere. (4) **A line is accepted or refused**: the LOG bar's `↵` stages it or shows the reason under the bar ([route.py](../expense/quickadd/route.py)), and `expense log` exits 1 on the same lines. (5) **The category cell alone carries the pending state** — no marker column.

**Rejected.** *A draft table that does not count toward totals* — the money is missing from every figure until promoted; this is what made capture heavier than a spreadsheet. *A `pending` flag on the row* — a second axis every client must know, and it allows a real category plus the flag. *Accepting future dates* — a balance holding next week's rent reads wrong today. *Defaulting a missing title to the category or account name* — invented text indistinguishable from typed text. *An `UNTITLED` placeholder* — a lie the ledger carries.

## Bank downloads are matched against the ledger, not hashed (2026-09-12)

**Decision.** `expense import bank` ([expense/bank_import/](../expense/bank_import/)): (1) **It asks which account** and remembers the answer per file stem (`Config.bank_files`); a card's two currencies are one pick. (2) **The engine matches** — the whole file in one `POST /transactions/import`, dry run by default, `--apply` the same call with `dry_run: false`, `--json` the engine's body. The engine matches by operation code, then same day + amount + title, then ± 1 day + amount + title, claiming each ledger row once; a content match onto a code-less ledger row writes the code onto it. The per-account UNIQUE on `operation_code` is the floor. **More rows beats fewer**: there is no amount-only rule, because a duplicate shows up at reconciliation and a missed row is invisible. (3) **A day where the ledger holds more unmatched rows than the file is a loud warning, never an action.** (4) **The title is the bank's text**, whitespace collapsed, and no description is written (description is the owner's notes field). (5) **New rows land under `@Pendiente`.** (6) Nothing dated before **2026-01-01** is sent; a file over **500** rows (the engine's cap) is refused; a row inside a completed reconciliation comes back `sealed` and is shown in its own block. The preview's `#` is the row's line in the file. Request and response live once in [expense/bank_import/engine.py](../expense/bank_import/engine.py). Mockup: [mockups/expense-world-bank-import-10b.html](mockups/expense-world-bank-import-10b.html).

**Rejected.** *Content-hashed ids* — blind to rows already in the ledger from the sheet or the LOG bar, and to a card row that moves a day between downloads. *A client-side matcher* — every client would need its own copy. *Splitting a file over 500 rows across calls* — a later call's row could be claimed by one an earlier call just created. *A `--since` floor* — one forgotten flag from duplicates. *A cleaned merchant name as the title* — the title is what the bank sent.

## Home is the month — a live list, `⏎` is the filter, and bulk edits are select + one key (2026-09-12)

**Decision.** (1) **Home is a live list off the one `/dashboard` read**: categories (see "Home draws four months"), then accounts and people **in their own currency with the code beside the figure**, then LEDGER, MANAGE and SYSTEM as always-open section headers with every screen a row. A failed read is one dim row with the reason. (2) **`⏎` on a row pushes Transactions with a `LedgerFilter`** — the engine's own `?category_id=` / `?account_id=` — crumbed `Ledger ▸ NAME`. (3) **Bulk is select + one key**: `space` selects, `a` selects every loaded row, `c` / `b` / `h` open one `PickerModal` over the selection (or the cursor row) and write **one `PUT /transactions/{id}` per row on its own worker**, then reload. A refused row is named by number and does not stop the others — which is why this is not `run_write`'s drop-on-error queue. (4) **Changed rows leave a filtered list at once**; the toast is the receipt. (5) **`esc` clears a selection, otherwise pops the screen** — the filter is the door, not a state. (6) **Hashtags replace the set** (the engine's `hashtag_ids` semantics); an empty apply is refused rather than read as "clear every tag". (7) **`@Pendiente` is pickable**, so a wrong bulk pick can be undone.

**Rejected.** *A categorising mode with history suggestions* — a second way to edit a category and a guess the engine would have to learn. *Spreading a category to every row with the same title* — same title, different payees; the selection is the spread. *Native balances with a converted figure beside them* — the balance you act on is the native one. *Bulk through `run_write`'s FIFO* — one refusal would drop every row behind it. *Folding the section rows* — the owner wants every screen visible. *`esc` stepping back to the unfiltered ledger* — two keys for "back".

## Home draws four months — three filters, empty categories hidden (2026-09-13)

**Decision.** (1) **Home draws categories × four months** (home currency), with unfoldable hashtag rows and inflow/outflow/net, from the same `build_range_grid` as the flat `reports monthly --from/--to`; `pgdn`/`pgup` walk the window a month at a time, never past this month. Balances are today's, and the header says so. (2) **`⏎` is three filters**: a category row → that category; a hashtag row → that category *and* that hashtag; an account or person row → that account. (3) **A category with nothing in the window is hidden.** (4) **A combo of several hashtags, or of none, is drawn but not filterable** — `?hashtag_id=` takes one id and there is no untagged filter, so a looser filter would show rows the cell does not count; `@Pendiente` draws no caret.

**Rejected.** *This month beside last month* — drops the long view. *A cell cursor scoping `⏎` to one month* — a second cursor axis. *Keeping zero-activity categories* — the Categories screen and the pickers list every one. *A separate Overview screen or tab* — the same numbers twice. *Twelve months* — ~160 columns; the flat range table is the long view. *Balances as of the window's month* — no endpoint, rarely acted on. *Filtering a multi-tag combo by its first hashtag* — a superset presented as the cell's rows.

## A null difference is blank, a zero difference is the em-dash (2026-09-14)

**Decision.** A reconciliation's `ending_balance_cents` and `difference_cents` are nullable (not entered yet). In the TUI ([cells.py](../expense/tui/widgets/cells.py)): `0` difference is the dim em-dash ("balances, move on"); `None` or junk is a **blank** cell — never the em-dash, which would assert the batch balances; a null amount renders `—`, not `(null)`. The flat CLI uses `format_cents_or_dash` for those two fields and always prints a zero difference as a number (it gets piped); `format_cents` keeps `(null)` everywhere else, deliberately ugly.

**Rejected.** *Null and zero both `—`* — tells you an unfinished batch balances. *A `?` glyph for null* — a blank already reads correctly. *Changing `format_cents` globally* — blunts a signal meant to be noticed.

## The TUI sees the response body only where it asks for it (2026-09-20)

**Decision.** `run_write` takes an optional `on_response: Callable[[dict], None]`, called **before** `on_success` and only when the body is a dict ([_base.py](../expense/tui/screens/_base.py)). Opt-in: only reconciliation `complete` uses it, for its `warnings`. Before `on_success`, so "read it, then repaint" needs no extra state.

**Rejected.** *A `body` argument on `on_success`* — every screen pays for one screen's need. *Stashing the body on the mixin* — a later `on_success` could read an earlier write's body. *Re-reading the record after completing* — the warning is computed at the transition and is not on the row.

## The gap report is a line under the header, not a toast and not the rows (2026-09-22)

**Decision.** A completed period's coverage-gap warnings render as a line under the header (`#rwarn`, `PALETTE.warning`), hidden when there are none; it survives `r` and clears on the next status change. The engine's sentence is shown **verbatim** and never parsed; `reconcile complete` prints the structured `coverage_gap` once. The "completed" toast still fires — a gap is not a failure. Reviewing unfiled rows is the `u` pane's job ("Rows in no batch live in the reconciliation view").

**Rejected.** *A toast* — fades in five seconds, and this message exists not to be missed. *A full screen* — interrupts every close, including deliberate gaps. *Working the gap's dates out client-side* — a copy of an engine rule.

## Rows in no batch live in the reconciliation view, not in a filtered ledger (2026-09-22)

**Decision.** (1) **`u` swaps an open account's reconciliation panel** for that account's rows in no reconciliation, oldest first; `esc` swaps back. (2) **`⏎` opens the edit form** (wrong date or wrong account is the usual cause) and **`d` deletes after a confirm** that says a delete is final. (3) **A `!` flag** marks a row whose date falls inside a period the screen already holds — a hint, never a ruling. (4) **No "tick all, then complete"**: `space` files rows one at a time so the difference updates before you seal. (5) **The ledger's bulk refusals collapse to one line per distinct engine message** (`rows 1, 2, 3: <message>`).

**Rejected.** *"Tick all N, then complete"* — a non-zero difference never blocks completion, so one keypress could seal a month that does not add up. *A filtered ledger with an `unreconciled` filter* — reconciliation work belongs in the reconciliation view (owner). *A delete key on the ledger* — the pane scopes it to rows being triaged. *Parsing the period name out of refusals to group them* — the whole message groups them without reading prose.

## The transaction list pages by cursor (2026-09-23)

**Decision.** `GET /transactions` pages by bookmark (`next_cursor` → `?after=`, `null` is the end), `?sort=date_asc` starts from the oldest, and the count is its own read, `GET /transactions/count`, asked once when a list opens or after a write. The client treats the cursor as opaque, drops it whenever the filter or sort changes, and walks forward only. Every list is one of three shapes ([cli-runtime.md](cli-runtime.md) "Three list shapes"). This was an engine ask, and it is the case behind CLAUDE.md's "Ask the engine to change" rule.

**Rejected.** *Offset paging* — a list that shrinks while you file rows silently skips rows. *A probe-then-offset-then-reverse read for oldest-first* — two reads, a race at the page edge, and a pattern every client would copy.

## Deleted is deleted (2026-09-23)

**Decision.** A delete is final from every client: there are no restore commands and no `--include-deleted`. The engine still soft-deletes, so `GET /activity` keeps the history; **undoing a delete is an operator task** (contract: "Base Conventions", "There is no restore"). Delete prompts are unchanged.

**Rejected.** *A flat-only restore* — a write no other client has. *A "recently deleted" view* — a list shape for a rare operator action.

## Activity and Rates leave the TUI (2026-09-23, owner)

**Decision.** Activity and Rates have no TUI screens; the flat `expense activity list` and `expense rates list` stay, with `--from` / `--to` / `--after` and a line naming the window read ([cli-spec.md](cli-spec.md) "Pagination"). A bare `--from`/`--to` day is sent as typed; the engine reads it as a whole day in `display_timezone`. No TUI screen reads a date window.

**Rejected.** *Porting both screens to date windows* — a second paging model for two unused screens. *Converting a typed day to an instant client-side* — the engine's date rule copied into the client; tried and removed.

## Long lists grow, they do not page (2026-09-25, owner)

**Decision.** The ledger and the "no batch" pane are **one list that grows**, both through `GrowingRead` ([_growing.py](../expense/tui/screens/_growing.py)): **10 rows** to start; `pgdn` **appends** the next 10 with the cursor on the first new row; `↑↓` scroll everything loaded; `pgup` moves up a screenful with no read; a resize fetches nothing. The caption reads `N of M loaded`.
- **Rows and count load together; a missing count fails the whole list** — never rows beside a guessed total.
- **After any write the list starts over**: `+`, an edit, `c` / `b` / `h`, `d` and `r` read the first 10 fresh with the cursor on row 1. A refused bulk row stays selected only if the fresh read brings it back.

**Rejected.** *Page swapping* — a cursor cannot say "page 3 of 11", and a resize either loses your place or repeats rows. *Keeping the loaded depth and cursor after a write* — the owner wants the plain reload. *Keeping an off-screen refused row selected* — the next bulk key would change a row you cannot see.

## Reconciliations opens on the accounts (2026-09-25, owner)

**Decision.** The screen opens with **the accounts alone** and reads nothing. `⏎` on an account reads its reconciliations (`GET /reconciliations?account_id=`, whole, in period order) and opens the panel under it; `esc` closes it. `u` works only inside an open panel. Returning from a reconciliation re-reads the account and lands on the same row; "not in the account's list" is how the working screen knows a reconciliation was deleted.

**Rejected.** *Reading on cursor pause* — a read per pause for a screen whose next step is always `⏎`. *Reading every account's list at open* — grows with the account list.

## Reconciliation periods are days (2026-09-26, owner's pick)

**Decision.** A period's `date_start` / `date_end` are **bare `YYYY-MM-DD`**, both required; the engine refuses anything else. The flat commands send the typed text unconverted. The TUI form checks the date **at the field** with `is_calendar_day` ([dates.py](../expense/dates.py)) — zero-padded, a real day — and sends it unchanged. The tick-list passes the period's days straight into `date_from` / `date_to`.

**Rejected.** *The LOG bar's forgiving dates* — a statement's dates are copied off paper. *`date.fromisoformat` alone* — accepts `20260831`, which the engine refuses.

## Delete anything that no longer points anywhere (2026-09-25, owner)

**Decision.** A removed flag, command or code path is deleted outright — **no stub, no friendlier message**: a stale `--limit` on a whole list gets Typer's own "No such option". Test fakes use the engine's real shapes (`whole()`, `cursor_page()` in [tests/unit/helpers.py](../tests/unit/helpers.py)) and refuse what the engine refuses. Guard: `test_command_surface.py::test_whole_lists_take_no_paging_flags`.

**Rejected.** *A stub that explains the removal* — a second copy of the engine's change that lives forever. *Keeping a dead branch "in case"* — unreachable code is untested; git history keeps old behaviour.

## Sealed periods: the engine guards, the client reports (2026-09-20)

**Decision.**
- **The engine is the only guard.** No client checks a seal before a write or caches completed windows (they change under `revert`). The `!` flag and the bank import's `sealed` rows only report.
- **Every refusal says what to do next** ([reconcile_cmd.py](../expense/commands/reconcile_cmd.py)): an inverted range names the flags; an overlap points at `reconcile list --account-id <id>`; on `complete`, an empty batch and unassigned rows each get their own hint. Both `complete` refusals share `fields["transactions"]`; **the hint is chosen by the reason on that field** `NO_TRANSACTIONS_ASSIGNED` or `UNASSIGNED_IN_PERIOD` (contract: "Error reasons"), never by wording, and a test holds each hint to its reason.
- **Only a date or account change can hit a seal**: of the bulk keys only `b` can be refused; `c` and `h` stay legal inside a sealed period. The LOG bar and the bank import name the sealing period on the refused row and still save the rest.
- **`revert` shows nothing extra.**

**Rejected.** *A client-side seal check* — a copy of an engine rule, stale the moment another client reverts. *A "close every month" bulk command* — would seal months nobody reviewed.

## The agent loop: one per repo, the main session orchestrates (2026-09-27, owner)

**Context.** The owner is not a coder. Work runs through agents that build, check and commit without asking about each task, while the owner keeps what users see, money rules a spec does not cover, and real data. The rules live in [CLAUDE.md](../CLAUDE.md) "How work runs (the agent loop)"; this entry holds the why.

**Decision.**
- **One loop per repo.** The worker definitions are written once in `~/.claude/agents/` and shared; each repo supplies its rules through its own CLAUDE.md. This repo came first because it has the most tests and guards; the engine repo copies it.
- **The main session is always the orchestrator** and never writes code or tests; the builder writes, the reviewer and tester only read and run, the librarian edits only docs.
- **The tester never writes tests.** A criterion with no test proving it goes back to the builder.
- **The loop runs on its own** once the owner approves a spec's tasks, pushing after every finished task, and stops only for what goes to the owner. A task needing a screen draws its mockup, parks, and the loop moves on.
- **Workers run on the session's model** (`model: inherit`).
- **The tester may start the practice engine**, the one exception to staying inside this repo, and recreates the practice user each check with a fresh key it never stores.

**Why.** "Done" (tests pass, committed and pushed) only means something inside one repo, and a loop per repo keeps the wall between this client and the engine automatic. Every change is written by one agent and read by another, so nothing is approved by the agent that wrote it; the same holds for a tester that would otherwise write the test it then checks. Pushing after each task runs GitHub's checks on each one. A fresh practice key per check leaves nothing stored and practice data starting clean. A fact written in two docs drifts, which is why the librarian exists. The trial run and the next spec both finished on 2026-09-28 under these rules.

**Rejected.** *One loop over the whole `productivity_world` folder* — "done" stops meaning anything across repos and the client–engine wall stops being automatic. *Checking in with the owner after every task* — the questions would be technical ones the owner hands back to the agents anyway.

## Review per task, test and align once per spec (2026-09-27, owner)

**Decision.** Each task runs builder → reviewer → commit and push; the reviewer also confirms each "passes if…" item. When a spec's tasks are done, the tester runs once as an acceptance check against the practice engine (version check, fixture check, the live contract suite, the spec's done-checks, and the app when a screen changed), and anything that fails becomes a new task. The librarian runs last, sweeping every doc before the spec is retired.

**Why.** The commit hook already runs the unit tests on every commit, so a per-task tester only repeated them; its real value is the real engine and checking criteria rather than tests, which one pass per spec covers. Docs drift slowly, so one sweep at the end catches what per-task passes did. Reading is cheaper than testing, so the reviewer goes first.

**Rejected.** *Tester and librarian after every task* — the first spec showed most of their time went on re-running what the commit hook checks and on small follow-up rounds. *No tester at all* — nothing else runs the app against the real engine or catches a criterion the tests miss.

## The engine is learned only from its live contract (2026-09-28, owner)

**Decision.** This repo learns how the engine behaves only from `GET /openapi.json` on the practice engine (`:8002`), read live; no copy of the contract is kept. Only its version is saved ([scripts/engine-contract-version](../scripts/engine-contract-version)); the fixture check compares it on every run and, when it moves, prints the contract's own change log (`x-changelog`). A moved version stops the loop and becomes a question for the owner, who decides whether catching up is the next spec; the new version is recorded only when acting on that answer. Code comments and docs cite the part of the contract that states a rule, as `(contract: …)` ([CLAUDE.md](../CLAUDE.md) "Key documentation"). No agent reads a file in the engine's folder: the guard blocks it for every agent, and the tester keeps only its start, reseed and stop there ([CLAUDE.md](../CLAUDE.md) "Stay inside this repo").

**Why.** Reading the engine's folder broke the rule that agents stay inside this repo, and the web and iOS clients never see that folder: they have only the published contract, so this client validates the same thing they will use. A saved version with the engine's own change log says *that* the contract moved and *what* moved, without keeping a copy that goes stale.

**Rejected.** *Keeping a copy of `openapi.json` in the repo* — it drifts, and each client would keep its own. *Accepting a moved version automatically* — an engine change would slip into the ledger's client unreviewed. *Reporting a change as the fixtures that no longer match* — it says what this repo's test data got wrong, not what the engine changed.

## Hints are chosen by the engine's reasons, never its wording (2026-09-28, owner)

**Decision.** Every engine error carries `error.reasons`, one code per field in `fields` (contract: "Error reasons"). The CLI and TUI choose every hint from those codes, and from the status and error code, never from `message` or `fields` text; `EngineError` keeps them next to `fields` ([errors.py](../expense/errors.py)). What people see does not change: the engine's message, each field's message and the hint, with no codes on screen; `--json` passes the engine's envelope through verbatim, codes included ([cli-spec.md](cli-spec.md) "Output conventions").

**Why.** The engine publishes its message wording for people and changes it without notice; a hint keyed to words breaks silently on a rewording, and web and iOS would copy the same fragile match. Reason codes are part of the published contract, listed per operation, so a change to them moves the contract version and reaches the owner.

**Rejected.** *Showing the codes on screen* — the owner kept errors as they read today (2026-09-28); the codes are for code, and `--json` has them. *Keeping the wording matches as a fallback* — two ways to decide the same thing, one of them unreliable.
