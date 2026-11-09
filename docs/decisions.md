# Decision record

Why the product is the way it is today, and what was rejected, so nobody re-litigates it. Only decisions that govern current code or product live here; a decision that is undone, or whose subject is deleted, is deleted too (git history is the archive).

Rules for this file:

- **Each entry has three parts:** `## <decision> (<date>)`, then **Decision.** the rule in a sentence or two · **Why.** one to three sentences (left out when no reason was recorded; never invented) · **Rejected.** *Option* — reason, one sentence each, only for options someone might plausibly propose again (left out when there are none).
- **The rule's details live in their own home** (tui.md, runtime.md, commands.md, a docstring, a test, or the live contract); the entry points there instead of retelling them. A detail with no other home stays in the entry.
- **Absolute dates, present tense.** No history of how a decision got there, and no provenance (CLAUDE.md doc rule (5)).
- **Headings are stable.** Code cites an entry by its heading without the date, and `test_docs_links.py` checks every citation; renaming a heading means updating its citations in the same change.

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

**Decision.** (1) A successful save stays on the screen: written rows show a `✓` until the next line is staged. (2) A partial failure ticks what landed, and `ctrl+s` retries only the rows without a `✓`; a refusal every further write would draw is said once, on no row ("Missing settings stop a multi-write run"). (3) `ctrl+s` never writes an unstaged line. (4) The discard card's `ctrl+s save first` leaves only if the save succeeds. Details: [log_bar.py](../expense/tui/screens/log_bar.py)'s docstrings (`Staged`: `row_id` and `date` frozen at stage time, a written row never lifted back), [batch_write.py](../expense/batch_write.py)'s docstring, `is_own_id_replay` in [errors.py](../expense/errors.py).

**Why.** A batch can partly fail. The retry is safe because a row keeps the id minted at staging, so a lost answer replays as `ID_EXISTS` on that id and reads as written.

**Rejected.** *Dismiss on success* — throws away the confirmation. *Keep ticked rows until you leave* — mixes history with intent, and the per-currency total stops describing the batch. *Re-send the whole list on retry* — hides a partial failure behind a wall of 409s. *Auto-stage the bar's line on save* — writes something unfinished. *Save and stay after `esc`* — the user pressed `esc`.

## Four calls for the LOG bar (2026-08-25)

**Decision.** (1) A staged row comes back as the raw line typed. (2) The staged table keeps its `tags` column. (3) The batch totals per currency: `3 to the ledger · -45.20 PEN · -96.00 USD`. (4) A refused line's reason uses [route.py](../expense/quickadd/route.py)'s own phrases. Details: [log_bar.py](../expense/tui/screens/log_bar.py)'s docstrings (`format_date_cell` for the staged date's year).

**Why.** Nothing is re-rendered or reworded, so line, row and reason never disagree.

**Rejected.** *Rebuild the line from the row* — a second formatter that drifts from the parser and loses typed text. *Drop the tags column for width* — tags are half of why a line is typed. *A shorter second wording for the reasons* — a phrase table that drifts from route.py.

## The quick-add line: one rule, shown before it is written (2026-08-25)

**Decision.** (1) [quickadd/route.py](../expense/quickadd/route.py) alone decides whether a line is accepted (see "A sparse line is a ledger row"); an ambiguous name counts as no name, its candidates shown. (2) The parsed row is always shown before it is written: the LOG bar's staged list is that echo, and nothing in `expense/quickadd/` asks again.

**Why.** The echo is what lets the grammar be forgiving (`18/8/26`, `hoy`, `$sig`).

**Rejected.** *Write, then echo, with `--dry-run` to look first* — the check is skipped exactly when typing fast. *Prompt only when something was inferred* — an unpredictable prompt trains you to dismiss it.

## Three quick-add grammar rules (2026-08-25)

**Decision.** (1) Names match on "contains, anywhere", accent- and case-blind; an exact name wins, longer phrases first. (2) Dashed ISO dates are accepted; dashes stay ISO-only. (3) An unmatched `#tag` is refused, never created. Details: the docstrings of [quickadd/parse.py](../expense/quickadd/parse.py), [quickadd/names.py](../expense/quickadd/names.py) and `when.py`.

**Why.** The distinctive word of a name is often in its middle, and every date field in the app takes ISO.

**Rejected.** *Whole-name or starts-with matching* — fails typing the distinctive middle word. *Slash dates only* — dashes typed out of habit silently become title text. *Create unknown tags on save* — a typo becomes a permanent tag. *Swallow an unknown tag as title text* — loses it silently.

## Sign is always literal — no default-to-expense magic (2026-04-25)

**Decision.** The sign is explicit in every UX layer: `20` is income, `-20` is expense. An ambiguous sign gets a prompt or an error, never a guess. No exceptions.

**Rejected.** *Default an unsigned amount to expense* — hidden behaviour that diverges from what the engine stores.

## The TUI is the only surface (2026-10-13)

**Decision.** Every feature is built once, in the TUI ([commands.md](commands.md) lists what is typed). A new engine capability gets a TUI screen and a contract test, nothing typed. Agents get no typed commands: the owner acts on the ledger, in the app. Engine features with no screen, exercised by the contract suite alone and the engine's to keep working: activity history; exchange-rate history; editing a statement's name and dates after creation, and its balances beyond the blank ones `c` asks for; updating the profile and the settings; the single-month report; posting a batch in one call. A screen for one is new work, when the owner asks.

**Why.** The owner uses only the TUI, so a typed command over the same reads and writes is the feature built and approved twice for nobody. Web and iOS call the engine's API, never this repo.

**Rejected.** *Flat commands beside the TUI* — every feature built, tested and approved twice. *One generic `expense api` command for agents* — an agent acting on the ledger belongs behind an MCP server beside the engine. *JSON-only commands for agents* — the same double build, for no reader.

## The open-work list holds only open work (2026-07-06)

**Decision.** [todo.md](todo.md) is a working list: closed items and finished docs are deleted.

**Why.** Git history is the archive.

**Rejected.** *Append and keep* — closed items get re-read forever. *A separate archive doc* — a second home for what git keeps.

## Split transactions, the pending hashtag and system rows (2026-10-17)

**Decision.** (1) Each part of a split transaction is its own ledger row; `c` and `h` change only the selected parts, and the bank's fields belong to every part (contract: PUT /v1/transactions/{transaction_id}). (2) `⏎` and `s` on any part open one Edit form for the whole line, saved in one write; parts are added and dropped only there (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"), and `^s` always sends (contract: PUT /v1/bank-lines/{bank_line_id}, "The total"). (3) The pending hashtag is found by its `system_key` like any hashtag, so Home has no "(no hashtags)" row. (4) No screen offers a rename or delete on `@Opening`, `@Pendiente` or the pending hashtag (contract: PUT /v1/categories/{category_id}, "A system category keeps its name"). (5) The spreadsheet import groups split rows by `COD_EECC` ("The sheet import brings a split purchase in as one split transaction"). Details: [tui.md](tui.md) §2.

**Why.** A category or hashtag belongs to a part; the add-up rule and the built-in names are the engine's.

**Rejected.** *One ledger row per split transaction* — hides what `c` and `h` change, and the engine declined a ledger read by bank line. *Holding `^s` until the parts add up* — a business rule every client would copy; the engine refuses and says by how much. *One LOG-bar line per part* — a part keeps the line's title, account and date, so most of the grammar only led to refusals, and it read badly. *Every part's fields in one long form* — the table shows every part at a glance. *Renaming from the Edit form after a split* — two writes, the first can land alone. *`e` on system categories* — would only lead to a refusal.

## A split transaction is reconciled and deleted whole (2026-10-17)

**Decision.** (1) Reconciliation screens list bank lines, in the bank's columns only, nothing marking a split (contract: GET /v1/bank-lines). (2) A tick is one write on any part and moves every part (contract: PUT /v1/transactions/{transaction_id}). (3) `d` on any part deletes the whole line, after a question naming its part count (contract: DELETE /v1/bank-lines/{bank_line_id}); `b` moves the whole line. (4) `⏎` in "no statement" opens the Edit form. (5) The app's word is "transaction", split or not; a form's variant keeps its name. Details: [tui.md](tui.md) §2.

**Why.** The bank sees one movement, so no screen shows half a line ticked.

**Rejected.** *Category and hashtags on reconciliation rows* — a reconciliation checks the bank's movements. *A split mark or part count* — nothing in a reconciliation depends on it. *`d` deleting one part* — the line's total would fall short of the bank's; re-splitting changes parts. *A form of its own for a split transaction* — a new screen name for a variant.

## TUI writes: FIFO queue in EngineWriteMixin, error drops the queue (2026-07-08)

**Decision.** `EngineWriteMixin.run_write` keeps one FIFO per screen, one request in flight; a failed write drops the queued rest, except once the screen has left ("A save you left still says how it ended"). Details: its docstring in [_base.py](../expense/tui/screens/_base.py).

**Why.** The queued intents were decided against a state the engine just contradicted.

**Rejected.** *Per-screen queues* — N copies of one race fix. *Cancelling in-flight writes* — a thread cannot stop a request, and the idempotency key covers retries. *Continuing past a failure* — later writes may depend on it. Independent bulk writes use their own worker (see "Home is the month").

## Connection errors get exit code 6, off the click collision on 2 (2026-07-10)

**Decision.** Exit 1 engine refused, 3 config, 6 connection; 2 is click's usage errors alone. A new meaning gets a fresh code. Source: `_ENVELOPE_ERRORS` in [errors.py](../expense/errors.py).

**Why.** Scripts branch on the code, not the prose.

**Rejected.** *Sharing 2 with a distinguishing message* — scripts cannot branch on it. *Renumbering to be contiguous* — churn for cosmetics.

## TUI paints the terminal's own background — ANSI mode (2026-07-11)

**Decision.** ANSI mode with `ansi_default` base fills, so app and terminal padding are one surface. Details: [tui.md](tui.md) §3; the foreground is "The terminal supplies the palette".

**Why.** A painted ground leaves a seam against the window padding.

**Rejected.** *Match a fixed hex* — right on one terminal profile only. *Fix the terminal profile* — pushes a code-owned problem onto every machine.

## Archive is a prompt-free toggle; Manage lists have no record detail (2026-07-11)

**Decision.** (1) The Manage lists are the whole surface: `e` edits, `a` archives or unarchives (accounts), `enter` does nothing. (2) Archive asks nothing; only delete and revert ask. Details: [tui.md](tui.md) §4.

**Why.** One keypress undoes an archive.

**Rejected.** *A record-detail screen* — repeats the list's columns. *Inline cell editing* — a second edit idiom for three screens. *A confirm on archive* — friction for nothing. *`enter` as an edit alias* — `enter` never changes data.

## Every data table pages at 20 rows (2026-07-11)

**Decision.** `DEFAULT_PAGE_ROWS = 20` in [reads.py](../expense/reads.py), one copy; full-data lists window locally at "TUI rows-per-page adapt to the terminal"; the ledger and "no statement" grow ("Long lists grow, they do not page"). Details: [tui.md](tui.md) §5.

**Why.** One size everywhere, and real engine pagination for the next client.

**Rejected.** *Client-side slicing of engine-paged reads* — the next client must inherit real pagination. *Auto-fetching at the edge on `↓`* — a held key fires a read per keystroke.

## TUI is keyboard-only — mouse disabled via `run(mouse=False)` (2026-07-12)

**Decision.** `launch` runs with `mouse=False` ([app.py](../expense/tui/app.py)); every affordance has a keyboard path. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Why.** Without mouse tracking the terminal's own select-to-copy works.

**Rejected.** *Textual's default mouse* — blocks native copy. *Per-widget click swallowing* — brittle, and still blocks copy.

## TUI rows-per-page adapt to the terminal — min(20, what fits) (2026-07-13)

**Decision.** The page is the screenful, capped at 20, so `#content` never scrolls. Details: [tui.md](tui.md) §5.

**Why.** Headers stay put and no scrollbar shows that nothing can operate.

**Rejected.** *A fixed 20 in a scrolling container* — headers scroll away, the scrollbar is undraggable. *Grow-to-fit everywhere* — short lists read worse spread out; only the ledger lifts the cap ("The ledger fills the window").

## The ledger fills the window (2026-08-29)

**Decision.** Transactions takes the whole terminal: row cap at the engine's `limit` ceiling, no card width (`PAGE_ROWS_CAP`, `CARD_WIDTH` in [transactions.py](../expense/tui/screens/transactions.py)); other screens keep 20 rows and a narrow card. Guard: `test_transactions_panel_fills_and_fits_the_viewport`.

**Why.** The ledger is the screen you sit in.

**Rejected.** *Lifting the caps app-wide* — two short columns over 200 columns read worse. *A bigger arbitrary cap* — the engine's ceiling is the only non-arbitrary bound.

## Ledger cells fill their columns — flex text columns, no pre-truncation (2026-09-12)

**Decision.** Title, Description and Hashtags share what the other columns leave, 3:3:2, each whole cell cut at its real edge (`_FLEX` in [transactions.py](../expense/tui/screens/transactions.py)).

**Why.** Column edges follow the terminal, not the page's data, so the table never reflows while scrolling.

**Rejected.** *Natural width* — data-dependent, and on a narrow terminal Rich trims every column until the amount is a bare `…`. *Bigger fixed caps* — the same bug on a bigger terminal.

## The app clears the terminal scrollback at launch — `CSI 2J 3J H` (2026-07-13)

**Decision.** `launch` emits `\x1b[2J\x1b[3J\x1b[H` before Textual starts ([app.py](../expense/tui/app.py)), at the cost of the tab's whole scrollback. Locked by [test_tui_mouse.py](../tests/unit/test_tui_mouse.py).

**Why.** With the mouse off, Terminal.app would scroll pre-launch text in above the app.

**Rejected.** *Clear only the screen (`2J`)* — the scrollback still slides in. *Re-enable the mouse to swallow the wheel* — undoes keyboard-only.

## The cursor is reverse video — applied as a Rich style, never as CSS (2026-08-20)

**Decision.** Reverse video is the one "you are here" gesture, applied as the Rich style `CURSOR_STYLE` ([windowed.py](../expense/tui/widgets/windowed.py)); tests assert on the rendered strip. Details: [tui.md](tui.md) §3.

**Why.** Textual 8.2.7 drops `reverse`, from CSS too, when both cursor colours are `ansi_default`, while still reporting it.

**Rejected.** *A coloured cursor bar* — fixed colours, and a gesture unlike the lists'. *Bold* — already means "pending".

## Opening balances are an engine concept (`@Opening` system category), not a client convention (2026-07-20)

**Decision.** An opening balance is the engine's transaction under `@Opening`, one per currency of an account, left out of flow reports; which sheet rows are opening balances is the engine's call (contract: POST /v1/transactions/import-sheet). The New statement form offers a begin balance on every currency. Details: [tui.md](tui.md) §2.

**Why.** Only the engine can exclude it, so no phantom income shows and visible rows sum to net. Its statement counts it in the add-up check (contract: "Statements", "`difference_cents` — the add-up check") and so begins at 0.00, and the form cannot know which statement that is.

**Rejected.** *A user category with a naming convention* — invisible to the engine, and every client invents a name. *An opening-balance param on `POST /accounts` only* — never fires for existing accounts. *Showing the `@Opening` row in panels* — visible rows would no longer sum to the total.

## All reads are live — no local replica (2026-08-06)

**Decision.** No cache and no write queue: every read is a live GET, every write waits for the answer. Details: [runtime.md](runtime.md).

**Why.** The engine runs on the owner's Mac, so a read is sub-millisecond and a replica only adds staleness and conflicts.

**Rejected.** *A cache rebuilt from REST reads* — every consistency cost, no latency gain. *Local-first writes with a last-write-wins queue* — the engine's writes have computed side effects, so it means duplicating the engine or "saved" rows bouncing later.

## Transfers are two ordinary transactions (2026-08-16)

**Decision.** A move between accounts is two ordinary transactions, each with its own sign and category.

**Why.** The engine has no transfer feature.

**Rejected.** *A client-side move writing both legs* — a new UX that can fail halfway (one leg lands, the other 422s).

## Reconciliation de-chaining — a statement is a period, ordered by its date (2026-08-16)

**Decision.** Both balances are typed off the paper, in one form with no chained fork. A statement is placed by its period's days; moving it is editing its dates. `difference_cents` shows on the lists and the working screen (see "A null difference is blank").

**Rejected.** *Prefilling the beginning balance from the previous statement's end* — the deleted engine feature redone in the client, stale-neighbour bug included.

## Home aggregates are nullable — `3 unrated` is a state, not a number (2026-08-16)

**Decision.** A `null` home-currency aggregate reads `3 unrated`, never `0.00` or a native figure; month cells carry the count, so no activity (dim `—`) and unpriceable stay distinct. One pair backs every screen: `format_aggregate` / `has_aggregate` in [formatting.py](../expense/formatting.py) (their docstrings hold the rest).

**Why.** The engine declines to total a group with an unrated row, and a native fallback reads USD cents as PEN cents.

**Rejected.** *A partial total with a marker* — a half-true number. *`n/a (3)`* — an abbreviation to learn. *A footnote with the count* — loses which row it belongs to.

## Contract tests verify against a disposable database, and refuse the real ledger (2026-08-16)

**Decision.** `tests/contract` runs against the practice engine on `:8002` and refuses to start when it would write to the real ledger. Details: [runtime.md](runtime.md) "Working against the live engine".

**Why.** A contract run's junk must never reach the one true ledger.

**Rejected.** *A warning banner* — useless when nobody is watching, which is when it matters. *A separate user in the real database* — the junk still lands in production. *The drift check in `pytest tests/unit`* — the unit suite blocks sockets on purpose.

## A settled person is folded, never hidden — and creating one is a TYPE field, not a `people` group (2026-08-16)

**Decision.** (1) A TYPE field (`bank` / `person`) leads the New Account form, both kinds posting to `POST /accounts`, read-only on edit ([create_forms.py](../expense/tui/screens/create_forms.py)'s docstring). (2) Home folds settled people behind a count (`▶ 3 settled`), a person whole or not at all (`split_settled` in [formatting.py](../expense/formatting.py)).

**Why.** One route makes either kind, so there is no second create path. The engine refuses to hide settled people (a repaid loan and an unrecorded one would look alike), so the count keeps anyone from vanishing silently.

**Rejected.** *Printing every settled person* — buries the ones you owe. *Naming them on the fold line* — grows until it needs truncating.

## One word for hashtags — the engine's, everywhere (2026-08-16)

**Decision.** Labels say `Hashtags`, the engine's word (`/hashtags`, `hashtag_ids`). Where client and engine name a thing differently, the engine wins.

**Why.** Every client inherits one vocabulary.

**Rejected.** *`Tags`* — shorter, but the client's word over the wire format's.

## The command palette is removed, not populated — `?` is the one discoverability surface (2026-08-17)

**Decision.** `ENABLE_COMMAND_PALETTE = False`; `?` opens our `HelpModal`, derived from the `BINDINGS` under `expense.tui`, and `test_tui_help.py` fails a binding with neither description nor tooltip. Details: [tui.md](tui.md) §4.

**Why.** Deriving from our own bindings keeps Textual's internals out with no suppression list.

**Rejected.** *Populating the palette with a `Provider`* — more work, and keeps Textual's theme picker and footer strip. *`?` on Textual's help panel* — lists internals, unthemed, squeezes the content.

## The terminal supplies the palette — every colour is an ANSI slot (2026-08-19)

**Decision.** Nothing is detected: every colour is an ANSI slot on one `Theme(ansi=True)`, and the terminal's profile decides its look. Pending is bold, no colour. Cost: the app looks different on each machine. Details: [theme.py](../expense/tui/theme.py), [tui.md](tui.md) §3; guard `test_theme_is_ansi_slots_not_hexes`.

**Why.** The terminal knows its palette, so dark, light and custom profiles all read right. Yellow fails on white.

**Rejected.** *Detect the background and pick one of two palettes* — two palettes approximating what the terminal knows. *A stored light/dark setting* — one more thing to configure. *Textual's `ansi-dark`/`ansi-light`* — the light/dark split this refuses. *Cards or boxed panels* — a vertical edge costs border and padding on both sides, the width an explaining column needs, and a card hides the screen that gives a question its context.

## A terminal too small is the user's to fix (2026-08-20)

**Decision.** No size guard. Everything is right at 80×24; 60×20 is workable but lossy (columns ellipsised, every row present); columns collapse from about 75 wide. Details: [tui.md](tui.md) §5.

**Why.** A guard would refuse readable terminals and cannot see a window shrink after launch.

**Rejected.** *Refuse at launch* — refuses readable terminals, misses later shrinking. *A persistent warning line* — spends a row where rows are fewest. *A notice screen below the threshold* — the one to build if this becomes a real complaint; rejected only on cost.

## Logging is a key, not a menu row — plain `+`, and the footer stops naming the arrow keys (2026-08-20)

**Decision.** Plain `+` opens the LOG bar on Home and Transactions; arrow keys get no footer slot (the `?` card lists them). Details: [tui.md](tui.md) §4; form keys: "Form fields move with `tab`".

**Why.** The most frequent action gets one key with one meaning.

**Rejected.** *`shift`+`+`* — unbindable: the shift is already in the character. *A menu row* — the most frequent action with the most steps.

## Form fields move with `tab` — plain arrows too, unless a suggestion list is open (2026-09-30)

**Decision.** In every bar form `tab` / `shift+tab` always move fields, shown as the footer's one `⇥ Field`; plain `↑↓` walk an open suggestion list and move fields otherwise; `^↑`/`^↓` work unadvertised. One copy: `form_bindings` ([_form.py](../expense/tui/screens/_form.py)). Details: [tui.md](tui.md) §4.

**Why.** A focused `Input` swallows `?` and forms have no help card, so the key that always works is the one shown.

**Rejected.** *`^↑`/`^↓` as field keys* — macOS takes them for Mission Control and Application Windows. *`shift+↑↓`* — a chord where `tab` is what every form uses. *Arrows only walking the list* — dead on the four fields with no list. *Arrows always moving fields* — the list would need its own key.

## Stepping through a form never changes it (2026-10-23)

**Decision.** (1) ACCOUNT and CATEGORY start on the row's own value. (2) `@Pendiente` is in the Edit form's category list, shared with the bulk `c` (`pickable_categories` in [reads.py](../expense/reads.py)). (3) A read-only line takes nothing. (4) `⏎` saves when no line ahead can change. (5) One `⏎` moves one line. Details: [tui.md](tui.md) §4 "The bar forms' keys".

**Why.** `⏎` walks a form line by line, so what it does on a line happens to every row walked past.

**Rejected.** *`@Pendiente` left out of the Edit form's list* — two lists for one pick, and no way to send a row back to waiting.

## One reader for every amount, refusing what it cannot read for sure (2026-10-23)

**Decision.** (1) A typed amount with a comma after its dot is refused ([tui.md](tui.md) "One reader for every typed amount"); the importers send their files whole, for the engine to read. (2) A part read from the line never drops when emptied; only `ctrl+x` takes it out (`part_empty` in [parts_table.py](../expense/tui/widgets/parts_table.py)). (3) A Manage Edit screen sends `color` only when another swatch was picked.

**Why.** Which mark is the decimal depends on who typed it.

**Rejected.** *Reading `13.853,20` as thirteen thousand* — a wrong guess saves a wrong amount silently. *An emptied saved part dropping* — takes a part out of a split unasked.

## One key per job — `j k h l , .` deleted, and the month window moves to `pgdn`/`pgup` (2026-08-27)

**Decision.** No aliases: `j k h l , .` and `[`/`]` are bound nowhere. `pgdn`/`pgup` move to the next window of data: the ledger grows, Home's months slide (`pgdn` older), `priority=True` over the menu `OptionList`'s own page keys. Details: [tui.md](tui.md) §4; guards in [test_tui_help.py](../tests/unit/test_tui_help.py).

**Why.** A widget alias silently outranks a screen binding, so aliases make letters unusable as commands.

**Rejected.** *`←`/`→` for the months* — `→` must unfold a Home row's `▶`. *`shift+←/→`* — a third tier of arrows for one screen. *Vim aliases as free extras* — free until something wants the letter.

## The LOG bar shows the named account's ledger — elastic, and it stays put (2026-08-29)

**Decision.** The account the line names shows its ledger under the staged list: elastic, the bar's account never a staged row's, staying on the last one named. No balance. Its count line names the pick's label, as an account holds several currencies and the peek lists one. Details: [tui.md](tui.md) "The account peek".

**Why.** It answers "did I already log this?" for the line being typed, without taking rows from the batch.

**Rejected.** *A fixed 12-row strip* — steals rows from a long batch. *A one-line summary* — cannot answer the question. *Blanking it when the bar is empty* — blinks off at every `↵`. *A navigable peek* — a second cursor.

## The LOG bar's staged title gives way before the columns that place a line (2026-11-03)

**Decision.** Title and tags give way first; marker, date, amount, currency, account and category stay whole ([tui.md](tui.md) "The LOG bar's account is one row per account").

**Why.** At 80 columns, a 20-letter account and category leave a title a few letters, or a bare `…`.

**Rejected.** *A least title width of about 10 letters, then cutting account and category* — cuts the names that say where a line is written.
## The LOG bar peek's title and count line shorten the account name, never the count or currency (2026-11-07)

**Decision.** On the peek's title and count line only the account name gives way, with `…`;
the count, the currency and the line's ending stay whole ([tui.md](tui.md) "The account peek").

**Why.** So long a name is rare, and a peek row is worth more.

**Rejected.** *Wrapping either line* — a peek row lost to a rare name.

## The legend, the two picker gaps, and day+month dates (2026-08-29)

**Decision.** (1) The grammar legend is one row that never changes; what changes is on the
`#hint` row ([tui.md](tui.md) "The legend row"). (2) A bare `$`/`@`/`#` opens the full list
([parse.py](../expense/quickadd/parse.py)). (3) Matching is accent-blind through one `fold()`
([quickadd/names.py](../expense/quickadd/names.py)). (4) Day + month means this year, the month
in letters ([quickadd/when.py](../expense/quickadd/when.py)'s docstring).

**Why.** A fixed row never moves the rows below it.

**Rejected.** *A bare numeric `28/08`* — `1/2` in a title would become a date. *A four-row key
block* — four peek rows. *A live checklist legend* — a row that is the same every time you look.
*`↵ stages the line` beside the legend* — wraps at 80 columns, a peek row lost.

## A sparse line is a ledger row under `@Pendiente` (2026-09-12)

**Decision.** A row needs an account, an amount and a date not ahead of today, and every name it
types must resolve ([route.py](../expense/quickadd/route.py)'s docstring). No category files it
under the `@Pendiente` system category, which counts in every total, grid and balance; naming
`@pendiente` sends a row back, and the category cell alone marks pending. A titleless row shows
`(untitled)`, drawn by the screen and never sent as a title.

**Why.** Money that counts nowhere until promoted is what made capture heavier than a spreadsheet.

**Rejected.** *A draft table outside the totals* — the money is missing from every figure. *A
`pending` flag on the row* — a second axis every client must know, and it allows a real category
plus the flag. *Accepting future dates* — next week's rent in today's balance. *Defaulting a
missing title to the category or account* — invented text that looks typed. *Storing an
`UNTITLED` title* — a lie the ledger carries.

## Bank downloads are matched against the ledger, not hashed (2026-09-12)

**Decision.** BCP `.xlsx` downloads go to the engine whole, dry run first, and the engine reads
and matches them ([tui.md](tui.md) "The import door"); titles play no part
(contract: POST /v1/transactions/import, "Matching") and there is no amount-only rule. The
account is asked every run. A day whose totals disagree is only reported; ledger lines no row
claimed stay out of that month's reconciliation and are deleted there. A row a day off its
ledger line is new. The title is the bank's text and the client writes no description (the
owner's notes field). New rows land under `@Pendiente` and `#Pendiente`, classified by hand in
Home. Unclaimed lines arrive unsigned and the engine will not sign them, so one guarded helper
does ([runtime.md](runtime.md) "Read semantics").

**Why.** A browser re-download (`… (1).xlsx`) is a new name. More rows beats fewer: a duplicate
shows at reconciliation, a missed row never shows.

**Rejected.** *Content-hashed ids* — blind to rows already in the ledger from the sheet or the
LOG bar. *Matching a row one day off* — can claim the wrong line on a busy card. *A client-side
matcher, or reading the file in the app* — a copy per client. *Splitting a file over 500 rows
across calls* — a later call's row could be claimed by one an earlier call created. *A `--since`
floor* — every row of the file goes in. *A cleaned merchant name as title* — the title is what
the bank sent. *Merchant memory or category suggestions* — classification stays manual.
*Detecting transfers, card payments or ITF* (`TRAN.CTAS.PROP.BM`, `PAG.T.PROP.VISA.BM`,
`IMPUESTO ITF`) — ordinary rows, classified by hand. *Import provenance and undo* — bulk `b` in
Home fixes a wrong account. *A per-row override in the preview* — every verdict is a fact, not a
guess (contract: POST /v1/transactions/import, "Matching"). *Other banks or CSV* — BCP only; its
PDF comes in only as a month's statement. *A one-time title alignment before the first import* —
overlapping rows already carry the statement's wording.

## The TUI import door — a drop is text, read up front, asked every time (2026-10-02)

**Decision.** A line is files only if every word is an existing file path
([dropped.py](../expense/tui/dropped.py)'s docstring). Every file is read before any screen
opens, the engine judges whether it is a download, and `esc` cancels this file and every later
one; the account is asked every time (see "Bank downloads are matched against the ledger" (1)).
The days that disagree are the ledger after the import (contract: POST /v1/transactions/import).
Details: [tui.md](tui.md) "The import door".

**Why.** The terminal types a dropped path, so no emulator hook is needed, and a half-recognised
line would import some files and stage the rest. `esc` cancels everywhere in the app. Counting
the ledger after the import shows a movement typed on another day instead of hiding it as a
silent duplicate.

**Rejected.** *Remembering the account per file name* — a re-download is a new name. *Splitting
quoted paths glued by repeated VS Code drops* — reads the line as no shell would. *A "rename to the bank's wording"
offer after apply* — the note names the day, and deleting the extra row is one
key. *An error screen for a non-BCP file* — the bar is where the right file gets dropped next.

## Home is the month — a live list, `⏎` is the filter, and bulk edits are select + one key (2026-09-12)

**Decision.** Home lists categories, accounts and people, balances native and never summed; `⏎`
opens Transactions filtered by the row; bulk edits are select + one key, one
`PUT /transactions/{id}` per row on the bulk's own worker. Details: [tui.md](tui.md) §2
"The filtered ledger is the categorising pass", "The bulk pick is a full screen".

**Why.** The filter is a door, not a state, so `esc` pops the screen. A surface that carries rows
is a screen; a pop-up only asks. `@Pendiente` stays pickable so a wrong pick can be undone.

**Rejected.** *A categorising mode with history suggestions* — a second way to edit, and a guess
for the engine to learn. *Spreading a category to rows with the same title* — same title,
different payees; the selection is the spread. *Converted figures beside native balances* — you
act on the native one. *Bulk through `run_write`'s FIFO* — one refusal drops every row behind
it. *Folding the section rows* — every screen stays one key away. *`esc` back to the unfiltered
ledger* — two keys for "back".

## Home draws four months — three filters, empty categories hidden (2026-09-13)

**Decision.** Home draws categories × four months; `⏎` filters by category, category and hashtag,
or account; empty categories are hidden; a multi-hashtag combo is not filterable ([tui.md](tui.md)
§2 "Home is four months of the ledger").

**Why.** `?hashtag_id=` takes one id, so a looser filter would show rows the cell does not count.

**Rejected.** *This month beside last* — drops the long view. *A cell cursor scoping `⏎` to a
month* — a second cursor axis. *Keeping zero-activity categories* — Categories and the pickers
list every one. *A separate Overview* — the same numbers twice. *Twelve months* — ~160 columns.
*Balances as of the window's month* — no endpoint, rarely acted on. *Filtering a combo by its
first hashtag* — a superset shown as the cell's rows.

## A null difference is blank, a zero difference is the em-dash (2026-09-14)

**Decision.** A `0` difference is the dim em-dash, a null one blank; a null amount is `—`, never
`(null)` ([cells.py](../expense/tui/widgets/cells.py)).

**Why.** The em-dash reads "balances, move on", which a statement with no balance entered does not.

**Rejected.** *`—` for both* — says an unfinished statement balances. *A `?` for null* — a blank
already reads right. *Changing `format_cents` globally* — blunts a signal meant to be noticed.

## The TUI sees the response body only where it asks for it (2026-09-20)

**Decision.** `run_write`'s opt-in `on_response` gets a dict body before `on_success`
([_base.py](../expense/tui/screens/_base.py)). Users: `complete` (its `warnings`), the gap report,
the balance save, setup's bootstrap, and form saves via `FormScreen._answered` (the edit form's
`changed_parts`).

**Why.** Before `on_success`, "read it, then repaint" needs no extra state.

**Rejected.** *A `body` argument on `on_success`* — every screen pays for one screen's need.
*Stashing the body on the mixin* — a later write could read an earlier body. *Re-reading after
completing* — the warning is computed at the transition, not stored on the row.

## The gap report is a line under the header, not a toast and not the rows (2026-09-22)

**Decision.** Coverage-gap warnings show verbatim on a line under the header (`_report_gap` in
[statements.py](../expense/tui/screens/statements.py)); the "completed" toast still fires.
Unfiled rows are the `u` pane's ("Rows in no statement live in the Statements view").

**Why.** The message must not be missed, and a gap is not a failure.

**Rejected.** *A toast* — gone in five seconds. *A full screen* — interrupts every close,
deliberate gaps included. *Working out the gap's dates client-side* — a copy of an engine rule.

## Rows in no statement live in the Statements view, not in a filtered ledger (2026-09-22)

**Decision.** `u` swaps an open account's panel for its bank lines in no statement
("A split transaction is reconciled and deleted whole"); `⏎` edits, `d` deletes, a `!` flag hints at a
row dated inside a period on screen, and `space` files one row at a time. Refusals read as in
"Refused rows read one line per kind of error". Details: [tui.md](tui.md) §2
"`u` on the Statements browse".

**Why.** A wrong date or account is the usual cause, and one tick at a time updates the difference
before you seal. The `!` compares the date prefix while the engine uses calendar days in the
user's timezone (contract: "Base Conventions", "Calendar days"): they agree only because live rows
sit at 00:00 America/Lima (no daylight saving; nothing enforces midnight), and the import dates
the rows it creates or moves the same way (contract: POST /v1/transactions/import). The first
writer storing a time of day makes the `!` wrong near midnight, and is the point to ask the
engine for a per-row flag.

**Rejected.** *"Tick all, then complete"* — a non-zero difference never blocks completion, so one
key could seal a month that does not add up. *A filtered ledger with `unreconciled`* — statement
work belongs in Statements. *Grouping refusals by the period name in them* — rows group by the
engine's code, fields and reasons, never its words.

## The transaction list pages by cursor (2026-09-23)

**Decision.** Transactions page by the engine's opaque cursor, the count its own read, asked when
a list opens or after a write ([runtime.md](runtime.md) "Three list shapes"). The client never
builds a cursor, since the engine refuses one it did not issue (contract: "Base Conventions", "Cursors, on every cursor-paged list"),
drops it when the filter or sort changes, and walks forward only.

**Why.** The engine owns paging and the count (CLAUDE.md "Ask the engine to change").

**Rejected.** *Offset paging* — a list that shrinks while you file rows skips rows. *Probe, offset,
then reverse for oldest-first* — two reads, a race at the page edge, a pattern every client copies.

## Deleted is deleted (2026-09-23)

**Decision.** A delete is final in every client; undoing one is an operator task
([runtime.md](runtime.md) "Read semantics").

**Why.** No client offers a way back the others lack.

**Rejected.** *A restore in this client only* — a write no other client has. *A "recently deleted"
view* — a list shape for a rare operator action.

## Activity and Rates leave the TUI (2026-09-23)

**Decision.** Activity and Rates have no screens ("The TUI is the only surface").

**Why.** Neither is used, and keeping them needs a second paging model.

**Rejected.** *Porting both to date windows* — that second model for two unused screens.

## Long lists grow, they do not page (2026-09-25)

**Decision.** The ledger and the "no statement" pane grow 10 rows at a time, rows and count
together, and start over after any write ([_growing.py](../expense/tui/screens/_growing.py)'s
docstring; [tui.md](tui.md) §5).

**Why.** A cursor-paged list grows only at its end.

**Rejected.** *Page swapping* — a cursor cannot say "page 3 of 11", and a resize loses your place
or repeats rows. *Keeping depth and cursor after a write* — a plain reload, like any list.
*Keeping an off-screen refused row selected* — the next bulk key changes a row you cannot see.

## Reconciliations opens on the accounts (2026-09-25)

**Decision.** The screen opens on the accounts, reading nothing; `⏎` reads one account's
statements ([tui.md](tui.md) "The Statements browse").

**Why.** The next step is always `⏎`.

**Rejected.** *Reading on cursor pause* — a read per pause. *Reading every account's list at
open* — grows with the account list.

## Reconciliation periods are days (2026-09-26)

**Decision.** A period's two dates are bare `YYYY-MM-DD`, both required, checked at the field by
`is_calendar_day` ([dates.py](../expense/dates.py)) and sent unchanged; the tick-list passes them
straight into `date_from` / `date_to`.

**Why.** The engine refuses any other shape.

**Rejected.** *The LOG bar's forgiving dates* — a statement's dates are copied off paper.
*`date.fromisoformat` alone* — accepts `20260831`, which the engine refuses.

## Delete anything that no longer points anywhere (2026-09-25)

**Decision.** A removed flag, command or code path goes outright, with no stub: a removed command
gets Typer's "No such command". Test fakes use the engine's real shapes and refuse what it refuses
([tests/unit/helpers.py](../tests/unit/helpers.py)); `test_command_surface.py` pins the typed
surface.

**Why.** Dead code is untested, and git history keeps old behaviour.

**Rejected.** *A stub explaining the removal* — a second copy of the engine's change, forever. *A
dead branch "in case"* — unreachable, so untested.

## Sealed periods: the engine guards, the client reports (2026-09-20)

**Decision.** Only the engine guards a seal: no client checks one or caches completed windows, and
the `!` flag and the import's `sealed` rows only report. Only a date, account or currency change
hits a seal, so of the bulk keys only `b` and `m` can. The LOG bar names the sealing period on the
refused row, the import shows `✗ Closed period`, and both write the rest; `revert` shows nothing
extra.

**Why.** Completed windows change under `revert`.

**Rejected.** *A client-side seal check* — stale once another client reverts. *A "close every month"
bulk command* — seals months nobody reviewed.

## The agent loop: one per repo, the main session orchestrates (2026-09-27)

**Decision.** One loop per repo, the workers shared from `~/.claude/agents/`, each repo's rules in
its own CLAUDE.md; the main session orchestrates and writes no code or tests ([CLAUDE.md](../CLAUDE.md)
"How work runs (the agent loop)").

**Why.** The owner is not a coder. "Done" (tests pass, committed and pushed) means something only
inside one repo, and a loop per repo keeps the client–engine wall automatic. Nothing is approved,
or tested, by the agent that wrote it; pushing per task runs GitHub's checks on each; a fresh
practice key per check stores nothing; a fact written in two docs drifts, hence the librarian.

**Rejected.** *One loop over the whole `productivity_world` folder* — "done" and the wall stop
holding. *Checking in with the owner after every task* — technical questions handed back anyway.

## Review per task, test and align once per spec (2026-09-27)

**Decision.** Builder → reviewer → commit and push per task; tester and librarian once per spec
([CLAUDE.md](../CLAUDE.md) "Per task", "Per spec").

**Why.** The commit hook already runs the unit tests; the tester's value is the real engine and the
criteria. Docs drift slowly. Reading is cheaper than testing, so the reviewer goes first.
A builder resumed after a second rejection spends the round rereading its failed attempts, so a
fresh one takes over, except for a small fix named by file and line, which a fresh builder would
reread whole files for. A reused agent carries every earlier task's reads and grows until it
compacts, so every task starts a fresh builder and reviewer.

**Rejected.** *Tester and librarian per task* — mostly re-running the hook, plus small follow-up
rounds. *No tester* — nothing else runs the app against the real engine or catches a criterion
the tests miss.

## The engine is learned only from its live contract (2026-09-28)

**Decision.** The engine is learned only from the practice engine's live `GET /openapi.json`; the
repo keeps its version, never a copy ([runtime.md](runtime.md) "Contract version"; [CLAUDE.md](../CLAUDE.md)
"Key documentation", "Stay inside this repo").

**Why.** Web and iOS see only the published contract, so this client validates what they will use.
A saved version plus the engine's change log say that the contract moved and what moved.

**Rejected.** *A copy of `openapi.json` in the repo* — it drifts, one per client. *Accepting a
moved version automatically* — an engine change slips in unreviewed. *Reporting the fixtures that
broke* — says what our test data got wrong, not what the engine changed.

## Hints are chosen by the engine's reasons, never its wording (2026-09-28)

**Decision.** Hints come from the `error.reasons` codes (contract: "Error reasons"), the status and
the error code, never from `message` or `fields` text; screens show no codes ([runtime.md](runtime.md)
"Engine errors surface cleanly"; [commands.md](commands.md) "Output conventions").

**Why.** The engine rewords messages without notice, and web and iOS would copy a fragile match.
Reason codes are listed per operation, so a change moves the contract version and reaches the owner.

**Rejected.** *Codes on screen* — they are for code; people read the words and the hint. *Wording
matches as a fallback* — two ways to decide, one unreliable.

## A move to another account takes the row out of its reconciliation (2026-09-30)

**Decision.** An account change sends `statement_id: null`, and the note counts the distinct parts
the engine says left ([tui.md](tui.md) §2 "A move takes a row out of its statement").

**Why.** The engine refuses the move otherwise (contract: PUT /v1/transactions/{transaction_id}),
the old account's reconciliation cannot hold the row, and reconciling the new account assigns it as
usual. A line field reaches every part of a split, so one request moves several rows and two can
list the same rows: only the engine knows what moved.

**Rejected.** *Asking each time whether to unassign or assign into a new draft* — a new screen,
and the second answer is the normal reconciling flow. *Counting requests, or deciding "left" from
rows read before the save* — wrong for a split, and a guess. *Re-reading the line after a move* —
a round trip for what the answer holds. *`0 rows → <account>` when nothing moved* — a note about
nothing.

## Missing settings stop a multi-write run (2026-10-11)

**Decision.** `SETTINGS_MISSING`, and `LIMIT_REACHED` with `LINE_CODES_EXHAUSTED`, end a multi-write
run: said once, nothing further sent, though `LINE_CODES_EXHAUSTED` still fails the row it names in
the engine's words ([runtime.md](runtime.md) "Bulk writes"; `refuses_every_write` in
[errors.py](../expense/errors.py)).

**Why.** `SETTINGS_MISSING` is about the account, not a row (contract: "Base Conventions", "Settings preconditions"),
and once the line codes are used up every write needing a new line is refused
(contract: POST /v1/transactions/batch).

**Rejected.** *Settling it like any other `422`* — `SETTINGS_MISSING` names no row, so every row
and every later chunk would carry the same four-line error; `LINE_CODES_EXHAUSTED` names one row a
send, so the run would spend a request per row to fail them all.

## The practice engine serves only the engine's shipped code, and only a listed version is recorded (2026-10-28)

**Decision.** Only the engine's own client practice launcher starts the practice engine, from an
export of its last commit, and a contract version is recorded only when it heads the served change
log ([runtime.md](runtime.md) "Working against the live engine", "Contract version").

**Why.** The engine coders work in the checkout it runs from: started there, it serves unfinished
work and unshipped versions, and fails to restart mid-edit.

**Rejected.** *Starting uvicorn from the checkout with its own Python* — serves half-built work.
*Trusting the served version alone* — a draft looks like any version until it never ships.

## A list's order is written in the contract's words, in one home (2026-10-12)

**Decision.** A doc or comment stating a list's order uses the contract's words, direction
included, and cites them; each order has one home ([tui.md](tui.md) "The Statements browse" for
an account's reconciliations), and no screen sorts a list the engine orders. Guard:
`test_list_orders_state_their_direction` in [test_docs_links.py](../tests/unit/test_docs_links.py).

**Why.** Every client shows a list as the engine returns it, and the contract states each order
with its direction: accounts come every real account first, then every person, each group by
`sort_order` ascending, then creation time, oldest first (contract: GET /v1/accounts, "Ordering").

**Rejected.** *SQL-style shorthand* — names columns the contract does not publish, as if from the
engine's insides. *Stating the order wherever the list appears* — the copies drift.

## The unit suite pins its terminal size (2026-10-12)

**Decision.** Every unit test's terminal is 80×24 ([runtime.md](runtime.md)
"Unit tests never touch the network").

**Why.** Typer boxes a usage error as wide as the terminal (`COLUMNS` or the window), and the
commit gate runs the suite in whatever session commits.

**Rejected.** *Loosening each assertion to survive wrapping* — every new test must remember it.

## The tag picker is one full list, narrowed by typing (2026-10-13)

**Decision.** `#` lists every tag in the engine's order, read once from `GET /v1/hashtags`; typing
keeps the tags whose name contains the text, case- and accent-blind, in that order
([quickadd/names.py](../expense/quickadd/names.py)). The list ignores the line's category, and the
app sorts and merges nothing. The engine's list of a category's tags, most-used first
(contract: GET /v1/categories/{category_id}/hashtags), has no screen; the contract suite covers it
([test_category_hashtags.py](../tests/contract/test_category_hashtags.py)).

**Why.** One list needs one order, so no client picks its own.

**Rejected.** *A category's own tags first, a divider, then the rest* — a second order each client
would pick. *The engine sending that two-group list* — with one list there is nothing to merge.
*Hiding tags a category never used* — any tag may go on any category. *A typed command listing a
category's tags* — the TUI is the surface in use.

## Completing a statement asks for every balance it needs first (2026-10-30)

**Decision.** `c` on a draft with blank balances asks for each, saves them in one write, then asks
`Complete statement?`; a refused complete naming a balance or a currency opens the same boxes for
it ([tui.md](tui.md) "`c` needs every balance", "A refused complete"). Saving and completing stay
two writes, and a refused save closes the box.

**Why.** The engine refuses a complete with a balance not entered (contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered")
or with money at the start in a currency not covered
(contract: POST /v1/statements/{statement_id}/complete, "Every currency with money at the start has balances in it"),
yet drafts hold blanks: an ending balance before the paper arrives, a beginning one when a new
currency joins. Which currency needs a balance is the engine's call. Two writes let balances be
saved without completing, and a refused save's note already says what to do. No statement was
completed without its balances, so there is no revert-and-fill path.

**Rejected.** *One box that saves and completes on one `enter`* — completing seals rows and keeps
its own `y`. *Refusing `c` with the engine's words only* — the user must then find where the
balance is typed. *A `Failed` title* — the screen's other refusals say `Couldn't …`.
## The Statements screens read whole at 80×24 (2026-11-03)

**Decision.** Both Statements screens fit 80×24 without scrolling: lists page, the statements list's name is the column that gives way, and `c`'s boxes open under the head. Only a completed statement on an account with a statement code is numbered; an open one there waits for its PDF, with no ticking and no `c` ("A card's statement is one statement, and a month closes from the bank's PDF"). Details: [tui.md](tui.md) §4 "The Statements browse" and §5 "The Statements screens fit 80×24".

**Why.** They are read against the bank's paper at the smallest terminal the app plans for ("A terminal too small is the user's to fix"). The numbers are the paper's places, and the order and the figures are what a list is read for.

**Rejected.** *Cutting the order word* (`not in …`) — it is the column the list is read for. *Cutting every name to fit* — ordinary names would lose their month. *A centred box over the balances* — it hides the figures it asks about. *Scrolling the screen* — its scrollbar cuts the last column.

## A create leaves an empty colour to the engine (2026-10-15)

**Decision.** New Category and New Account make colour optional and leave a skipped one out of the body, the sheet import sends none for the categories it creates, and Edit Category keeps it required. Details: [tui.md](tui.md) §2 "Stepping past COLOR keeps it".

**Why.** A create with no colour gets the engine's default, while an update refuses a null one (contract: "Colour format").

**Rejected.** *A palette the client cycles through for imported categories* — a client-side copy of a choice the engine makes. *Highlighting the first swatch on the empty line* — `enter` there skips the colour, so it shows a pick that does not happen.

## The unit suite runs in parallel by default (2026-10-16)

**Decision.** `addopts = ["-n", "auto"]` in [pyproject.toml](../pyproject.toml) runs the tests gate, CI and hand runs in parallel; pytest-xdist is a required dev dependency.

**Why.** Run serially the suite is several times slower, and the loop runs it on every task. Only addopts or the command line reach pytest-cov, which reads `-n` before any conftest loads.

**Rejected.** *An opt-in `-n` flag* — the gate and CI would not get it. *Setting `-n` from a conftest hook* — pytest-cov does not see it and crashes.

## Live contract runs stay in one process (2026-10-16)

**Decision.** A live run answers `-n auto` with zero workers however it is started; only an explicit `-n N` overrides it ([tests/conftest.py](../tests/conftest.py), [tests/contract/conftest.py](../tests/contract/conftest.py)).

**Why.** The contract tests share one practice user and make real writes, and one seals periods others write into.

**Rejected.** *Letting the default parallel run spread them* — they would race on the shared user and the sealed periods.

## The whole unit suite runs once per task, and docs never trigger it (2026-10-22)

**Decision.** The tests gate skips pytest on code it has already passed and leaves docs out of what it compares, so a docs-only change runs no tests ([tests_gate.py](../.claude/hooks/tests_gate.py)); a doc edit that breaks a doc-reading test is caught by the librarian's docs-link run or by CI after the push. The guard stops a builder, reviewer or librarian running the whole suite by hand ([guard.py](../.claude/hooks/guard.py)).

**Why.** Otherwise a task runs the suite three or four times on the same code: at the builder's stop, at commit and by hand. Common practice runs the full suite once when the work is done, with CI as the safety net, and build tools such as Bazel never re-test unchanged code; written instructions alone do not hold, so tooling enforces it.

**Rejected.** *Running only the tests a change can affect (`pytest-testmon`)* — with unchanged code skipped, the builder's stop is the only full run; testmon would move it to commit, where a failure costs a round trip, and add a data file that can go stale; revisit past about 90 s. *Running the doc-reading tests on a docs-only change* — a list to keep in step, for a check CI already makes. *Keeping docs in the fingerprint* — the orchestrator edits docs between the builder's stop and every commit, so nearly every commit would rerun the suite.

## The practice engine has one script, run in exact shapes (2026-10-16)

**Decision.** `scripts/practice-engine up|down` starts, reseeds and stops the `:8002` engine. Any agent may run it, the guard allows only its exact forms, and it takes no options and inherits no environment ([its header](../scripts/practice-engine)).

**Why.** Sending a tester just to start or stop the engine cost an agent round trip on every task that needed the contract live. The start prints both practice users' keys, which must never reach a file, and nothing the caller sets may point it at the live engine or the real ledger.

**Rejected.** *Keeping the start tester-only* — slow. *A script that takes options or inherits the environment* — one variable could reach the real ledger.

## Engine changes arrive as one catch-up file and leave as one reply (2026-10-17)

**Decision.** One hand-off file covers every contract change since the version last caught up to; it becomes catch-up specs and is deleted, and each catch-up spec ends with a reply to the engine ([from-engine/README.md](from-engine/README.md), [to-engine/README.md](to-engine/README.md)).

**Why.** One range per catch-up leaves no gap and no double work, and once the spec holds everything the file adds nothing. The reply closes the loop: this app is the contract's first real user, so the engine coders learn what held up before the web and iOS clients build on it.

**Rejected.** *One file per engine change* — overlapping ranges and gaps. *Keeping the hand-off file until the spec retires* — two homes for the same facts.

## An ask leaves the outbox once it is handed over (2026-10-24)

**Decision.** An ask is deleted when the owner says it is handed over, as a reply is; whatever waits on it names it by title ([to-engine/README.md](to-engine/README.md)).

**Why.** The outbox lists only what the owner still has to carry, so nothing goes to the engine twice; the engine's copy and git history keep the text.

**Rejected.** *Keeping each ask until a hand-off answers it* — the folder stops telling the owner what to carry, and an ask the engine holds gets carried again.

## The bank import's preview is one table: a mark and a reason per file row (2026-10-18)

**Decision.** The preview is one table of every row the engine read, each with a mark and one reason from a short fixed list: ✓ the row is in the ledger after the import, ✗ it needs looking at, `·` a row of `0`. A move to the bank's day is one more "Modified existing transaction"; a move a completed statement stops is ✗ `Not moved: <statement> is completed`, the statement named by one read by its id (contract: GET /v1/statements/{statement_id}). The days where the file and the ledger disagree show on the preview only. Details: [tui.md](tui.md) §2 "The import door".

**Why.** A fixed list takes a new engine behaviour as one more reason, not a new suffix with its own wording. With a reconciliation done right the bank's day and the ledger's agree, so a stopped move points at one completed wrong; it says "not moved" because the bank's title and operation number still land (contract: POST /v1/transactions/import). The engine's answer holds the statement's id alone, as every reference to another record.

**Rejected.** *✓ only for a new transaction* — a re-imported file would be mostly ✗ with nothing wrong. *The reason followed by what changed* (`· day 03 Oct → 04 Oct`) — longer rows. *A reason of its own for a move* — a longer list; the count says it. *The table again after importing* — the preview gave it. *A ✓ on a stopped move* — it hides a reconciliation to check.

## Every contract citation is checked against the live contract (2026-10-18)

**Decision.** [test_contract_citations.py](../tests/contract/test_contract_citations.py) fails, naming file and line, on any `(contract: …)` citation the live contract does not hold in the place it names; its docstring defines the forms. It runs with the live suite, so the tester's acceptance check catches a rule the engine moved or renamed.

**Why.** The engine moves and renames rules between versions without changing behaviour, and a stale citation sends readers to the wrong place. A name-and-place check is mechanical, so it is a test, not a sweep to remember.

**Rejected.** *A hermetic unit test over a saved copy of the contract* — no copy is kept ("The engine is learned only from its live contract"). *Checking only that each quoted name appears somewhere* — a rule moved to another tag would still pass.

## A form never sends `null` where the engine refuses it (2026-10-18)

**Decision.** The Edit forms send `null` only for the fields the engine clears with it (`statement_id`, `title`, `operation_code`); an emptied note goes as `description: ""` (contract: PUT /v1/transactions/{transaction_id}). A test in [test_tui_edit_form.py](../tests/unit/test_tui_edit_form.py) empties every field of both forms and fails on any other `null`.

**Why.** An explicit `null` is `NOT_NULL` on every other field, a refusal the owner did nothing to cause; pinning each field keeps a new one from bringing the bug back.

**Rejected.** *Leaving an emptied note unsent* — the old note stays, and the emptying is silently lost.

## An archived account's frozen writes are not offered, and a refusal is the engine's words (2026-10-18)

**Decision.** The engine freezes an archived account: its transactions change only in category, hashtags and note, plus one fill of an empty title or operation code, and its reconciliations not at all (contract: POST /v1/accounts/{account_id}/archive). The app reads `is_archived` from the accounts read each screen already makes and offers none of the rest: no `d` on its ledger rows, while `s` stays ("The Edit form's keys and words name what it does"); the Edit form reads what is read-only from `edit_limits`; Reconciliations lists only active accounts. A frozen change sent anyway shows the engine's words alone. Details: [tui.md](tui.md) §2 "On an archived account's row the ledger offers no `d`" and the paragraph after it.

**Why.** Offering a key the engine always refuses invites a refusal for nothing, on every client. Reading the engine's own flag keeps the rule in the engine: a failed accounts read only puts the keys back, and the engine's refusal already says to unarchive first.

**Rejected.** *Dimming the archived account's rows* — some of their lines still change. *A line naming where to unarchive* — the engine's words say it. *A question that unarchives and retries* — unfreezing would become a side effect of an edit. *Listing archived accounts on Reconciliations, read-only* — nothing there can change.

## The sheet import brings a split purchase in as one split transaction (2026-10-22)

**Decision.** (1) Rows sharing a `COD_EECC` come in as one split transaction, grouped by the engine (contract: POST /v1/transactions/import-sheet); the app shows its count and the groups are checked in the app afterwards ([commands.md](commands.md) "`expense import sheet`"). (2) `COD_EECC` only groups: a statement line, a line's place in the statement's order, comes only from a reconciliation. (3) Letter case counts in a `COD_EECC`: `SIG-1` and `sig-1` are two movements. Every match follows one rule: a field a person types, a name, matches in any letter case; a field from the bank or a program (an operation code, a statement code, a bank file's operation number) matches exactly.

**Why.** One bank movement split across categories is several sheet rows sharing a `COD_EECC` (`SIG-202603-029`), and the sheet has no column for the bank line or the bank's operation number, so `COD_EECC` alone tells which rows were one movement.

**Rejected.** *Keeping `COD_EECC` as each line's statement line* — statement lines come only from a reconciliation, and 2,275 hand-typed codes would clash with the ones a reconciliation makes. *Creating each month's reconciliations and their order at the import, from `COD_EECC`* — reconciling is the owner's call, made later. *Folding case in a `COD_EECC` or an operation code* — they come from a program, and folding would merge two movements the engine keeps apart. *Listing every group on the dry run* — the groups are checked in the app.

## The sheet import creates its names in a step of its own, and a dry run never writes (2026-10-27)

**Decision.** `expense import sheet` runs in three steps, the dry run, `--create-names` and `--apply`, so a refused sheet creates nothing and the counts are always seen before anything is imported. The counts name the split transactions and the rows they hold, as the engine counts them (contract: POST /v1/transactions/import-sheet, "Response"). Details: [commands.md](commands.md) "`expense import sheet`".

**Why.** The engine never creates a name and counts a dry run only once every name has an id (contract: POST /v1/transactions/import-sheet, "Names"), and on the official import into an empty ledger every name is new. Counting rows beside splits keeps three splits of eight rows from reading like three of six.

**Rejected.** *A dry run with no counts* — the numbers would show only after the one-time import. *A dry run that creates the missing names* — a preview that writes. *`--apply` creating what is missing* — an import made without its counts seen. *A command of its own for the step* — `import sheet` stays the only command. *The app counting the split rows itself* — only possible after an apply, and the grouping is the engine's rule.

## A person carries an opening balance (2026-10-28)

**Decision.** A person's opening balance works as a bank account's, in the engine (contract: PUT /v1/accounts/{account_id}) and in the app: the same Edit form pairs, kept through `t`. A person's New and Edit forms have no statement code line, though the engine takes one. Details: [tui.md](tui.md) §2 "An account's opening balance lives on its Edit form, one per currency" and "A bank account's statement code is a line of its own on New and Edit".

**Why.** A person's balance is a debt to or from them, and a debt standing when tracking starts is an opening balance, as on a bank account.

**Rejected.** *A person's opening balance only from the sheet import* — a starting debt is a balance like any other, and nothing in the app could set or fix one.

## An account becomes a person, and back, with one key and a short question (2026-10-22)

**Decision.** An account turns into a person and back in the app, not in the import: `t` on Manage ▸ Accounts, which asks for what the engine needs: a person's name, or a bank account's bank and an optional last 4, from which the engine builds its name. The account keeps its id, currencies, balances, opening balance and transactions (contract: POST /v1/accounts/{account_id}/make-person) (contract: POST /v1/accounts/{account_id}/make-account), as "A person carries an opening balance" says. A refusal, such as `HAS_RECONCILIATION` on an account ever in a statement, is the engine's words alone. The sheet import matches no names itself: the engine proposes an account per sheet name, so a re-run after a conversion is the engine's to match. Details: [tui.md](tui.md) §2 "`t` turns an account into a person and back".

**Why.** The owner's sheet records loans as the app does, one account per person and currency whose balance is the debt (ALEJO, ALONSO, LC, ALEX, LIDIA, MATILDE, CARLOS, KORAKUEN), and the import creates every sheet account as a bank account. A person never has statements, since a person sends no bank statement.

**Rejected.** *Teaching the import which sheet names are people* — a list to keep in step with the sheet, while an account action also fixes any account created as the wrong kind. *`t` opening the Edit form, turned* — a whole form for one or two lines.

## The engine names a bank account from its bank and card number (2026-11-09)

**Decision.** A bank account holds its bank and the last 4 digits of its card or account number
over time, and the engine builds its name, `BCP-5678`, or `BCP` until it has a number
(contract: POST /v1/accounts, "The name"). Every screen shows that name, and no client types or
builds one, not even to say what a removal or a failed create would leave. A person keeps a typed
name. A replaced card is the same account, its name following the new card; older numbers read
`cards before`; emptying `last 4` asks before it removes a number. On the LOG bar, `$` finds a
name by either word, and `$` with exactly four digits that are one of a card's last 4 finds that
account; other digits after `$` stay money. Exact-name-wins stays, so `$BCP` is the account named
`BCP` and every written line parses back to its own account; while `$bcp` is typed, the list
offers the exact name and every name built on it, in the engine's order. Details: [tui.md](tui.md)
§2, the account forms and the LOG bar's `$`.

**Why.** Every BCP paper prints its number, so an account that knows it lets the engine refuse a
paper sent to the wrong account and name the account as the bank does. A card replaced after a
loss keeps its balance, so the account keeps its numbers by day.

**Rejected.** *An alias beside the built name* — the engine declined it; one name per account.
*The parser listing every name built on `BCP`* — a picked `BCP` could never be staged. *Dropping
exact-name-wins* — `BCP Signature` beside `BCP Signature Platinum` turns ambiguous. *Digits after
`$` always money* — the number on the card in hand would not find it. *No removal in the app* — a
replacement added by mistake would stay for good.

## The account form saves in one write (2026-11-09)

**Decision.** The New form makes an account, its currencies and each currency's opening balance in
one `POST /accounts`; the Edit form saves its lines, numbers and every opening balance (set,
changed or cleared) in one `PUT /accounts/{id}` (contract: PUT /v1/accounts/{account_id}). Whole
or not at all; a refusal lands on the line its key names. A PDF refused for its account's number
goes back to the account question, the right account one pick away
(contract: POST /v1/statements/import, "The numbers the paper prints must fit the account's").
Details: [tui.md](tui.md) §2.

**Why.** A save of several writes, refused half-way, left part of it saved and needed a report of
what landed; one write leaves nothing to explain.

**Rejected.** *Openings only on the Edit form* — a new account would take two saves. *A chain of
writes with a report of the parts saved* — the half-saved state it explains is the problem.

## A hint says what `⏎` does there, and a note names what the app can't read (2026-10-24)

**Decision.** (1) A bar form's hint says "enter to save" only where `⏎` saves and "enter to go on" where it moves on, a guard test walking every bar form. (2) A non-date on the Edit form's DATE is refused at `⏎`, in the words of the app's other dates. (3) The LOG bar names a signed amount it can't read rather than saying it needs a sign. Details: [tui.md](tui.md) §4 "The bar forms' keys", §2 "A date the form can't read is refused at `⏎`".

**Why.** A hint or note that says something the screen does not do teaches the wrong key, and a typo must never close the app and lose what was typed.

**Rejected.** *Refusing a bad date only at save* — the note would come after the line is left, while every other line is checked at `⏎`.

## Refused rows read one line per kind of error (2026-10-22)

**Decision.** A refused save of several rows reads one line per kind of error, from one shared helper: the field, the engine's words, then the rows hit. Rows are one kind when the engine's code, fields and reasons match, never by its top-level message. Details: [runtime.md](runtime.md) "How refused rows read".

**Rejected.** *One line per row* — a refusal hitting many rows repeats itself. *The engine's words alone* — often general (`Must not be null.`), so two lines could read the same with no field named. *Grouping by the top-level message* — it carries a count, so one kind sent twice would read as two.

## The Edit form saves a whole line in one write, and the engine says what is locked (2026-10-25)

**Decision.** (1) Every Edit form save on a bank line is one `PUT /bank-lines/{bank_line_id}` with the line's fields and its full set of parts, an opening balance's line and an archived account's line included (contract: PUT /v1/bank-lines/{bank_line_id}, "The parts' rules"); a kept part's unchanged amount is sent, which the engine does not count as a change on an archived account ([bank_line_write.py](../expense/bank_line_write.py) has the body). (2) What is read-only comes from the line's `edit_limits` alone; the form reads no reconciliation and holds no locking rule. (3) A locked field says `read-only` and the engine's sentence ("Notes keep the engine's words, and a read-only line says why"). Details: [tui.md](tui.md) §2 "What is read-only is the line's `edit_limits`, and nothing else".

**Why.** One write lands whole or not at all, and a retry under the same key never applies twice. The engine computes `edit_limits` with the write's own rules on every read, so the form never offers what the write would refuse and every client reads the same answer.

**Rejected.** *A transaction's own write for an opening balance's or an archived account's line* — two write paths for one form, the second taking different fields. *One write per part* — a chain that can land halfway. *Reading the line's reconciliation to decide what is locked* — an extra read, and a copy of the engine's rules.

## Notes keep the engine's words, and a read-only line says why (2026-10-26)

**Decision.** (1) Every note shows the engine's words as text, never as styling, guarded by a test. (2) A read-only line on the Edit form says why in the engine's sentence, the `message` of the line's `edit_limits`, each distinct sentence once. (3) A refusal that stops a run of writes reads the same everywhere, from one helper. (4) The question before completing a reconciliation names all six things it locks. Details: [tui.md](tui.md) §2 "The engine's words show as text, never as styling" and "What is read-only is the line's `edit_limits`, and nothing else", §4 for the question.

**Why.** The engine's words are its contract with every client; restyled or vanishing text is a lossy copy. The engine sends each lock's reason in words, so no client keeps its own table from code to words that could drift, and one problem reads one way on every screen.

**Rejected.** *A table in the app from each reason code to a sentence* — a copy of the engine's wording in every client. *The sentence beside every read-only line* — the same sentence three times on a line in a completed reconciliation. *A second sentence in the complete question saying what still changes* — longer, and the Edit form shows it.

## A list shows a name as the engine holds it, `[` and all (2026-10-27)

**Decision.** Every list cell holding a name or title is drawn as plain words through one helper, `list_cell` in [cursor_list.py](../expense/tui/widgets/cursor_list.py), so `BCP [like this]` shows whole everywhere; a cell the app styles is drawn as built. Details: [tui.md](tui.md) §2 "The engine's words show as text, never as styling"; the screens pinned: [test_tui_bracketed_names.py](../tests/unit/test_tui_bracketed_names.py).

**Why.** A name is the owner's words, held by the engine, and a list that hides part of it shows a different name from every other client. One helper means a new list gets this by default.

**Rejected.** *Escaping each name where a screen builds its row* — every new list would have to remember it, and one that forgot would lose text silently.

## The Edit form's keys and words name what it does (2026-10-25)

**Decision.** (1) `s` stays on an archived account's ledger row and opens the Edit form as `⏎` does; only `d` leaves. (2) The ledger's footer reads `s Edit`, and a refused part names its field by the parts table's column word (`part 1 (category)`, `FIELD_WORDS` in [parts_table.py](../expense/tui/widgets/parts_table.py)). (3) An opening balance's hashtag refusal on the Edit form shows the engine's words alone; "Leave the opening balance out of the selection." stays on the ledger's bulk `h`. Details: [tui.md](tui.md) §2 "On an archived account's row the ledger offers no `d`" and "A refused save stays under the parts".

**Why.** `⏎` and `s` open one form, so hiding one hides nothing. Words must name the screen they open, and a field named by its column reads better than the engine's name and needs no second list. A line about a selection makes no sense on a form that edits one transaction.

**Rejected.** *Keeping `s` hidden on an archived row* — it hides a form `⏎` opens anyway. *Keeping `s Split` in the footer* — `s` opens the Edit form; it does not split. *Listing every field on the "no statement" card* — three lines for what "the transaction and its parts" says in one. *A line of the form's own for the opening balance's hashtag refusal* — rare, its field already shows read-only, and the engine's words are enough.

## A card's statement is one statement, and a month closes from the bank's PDF (2026-10-25)

**Decision.** (1) A card's month is one statement covering every currency of the account, listed as one row and written whole (contract: "Statements", "Every write acts on the whole statement"). (2) The statement line is never shown: it only keeps a statement's lines in the paper's order. (3) No screen orders a statement, ticks the lines it still needs, or edits its name, days or balances beyond the blanks `c` asks for; a month's statement may be opened before its PDF, and uploading the PDF closes it, the engine reading, matching and completing. (4) The PDF writes what the ledger lacks and never changes or deletes what the paper lacks: a line the paper lacks is taken out or flagged and never stops the close, equal lines on one day match one to one, a card's undated charges each land on the statement's last day, and an installment purchase is one transaction a month, as billed (contract: POST /v1/statements/import). Details: [tui.md](tui.md) §4 "The Statements browse", §2 "A statement PDF closes its month".

**Why.** A statement is one thing on paper, so it is one row and one write. The owner checks a month against the bank's PDF, which already holds each currency's balances, every line and the paper's order, so reading it replaces every hand step. Writing exactly what the paper holds makes every statement add up to it, while a logged line the paper lacks stays for the owner to judge.

**Rejected.** *A heading per statement with a line per currency under it* — three lines a month show a third as many months. *A screen to order a statement with `shift+↑↓`, the lines still to tick under it, and an `e` form for the name, days and balances* — each is a hand step the PDF does. *Ticking lines into an open month by date as they are imported* — with no ending balance before the PDF there is nothing to compare them against.
## The suites copy the engine's answers and leave the practice user as they found it (2026-10-25)

**Decision.** (1) The unit suite's fake engine answers writes through one builder per endpoint,
checked both ways by the drift script ([runtime.md](runtime.md) "Fixture drift"). (2) Every unit
request body is checked for the fields the engine sets itself
([tests/unit/conftest.py](../tests/unit/conftest.py)). (3) A live test fails when it leaves an
account, category or hashtag it made ([runtime.md](runtime.md) "Leftovers"). (4) Engine-side probes
use a practice user of their own, never this client's. (5) The begin balance hint says a statement
holding the opening balance begins at 0.00 ([tui.md](tui.md) §4 "The New statement form"). (6) The live suite's bank accounts carry a
number starting `9`, the cleaner's mark for them ([scripts/clean_practice_user.py](../scripts/clean_practice_user.py)),
and a sample PDF goes to the seed's `BCP-0000` by its id ([runtime.md](runtime.md) "Leftovers").

**Why.** A fake answering `{}` hides fields a screen reads, a fixture missing a required field
passes until the real engine answers, and a field checked against every schema passes on another
answer's. Leftovers take statement codes other tests need and clutter hand checks; failing the
leaking test finds the leak at its source. The engine adds an assigned opening balance into the sum,
so typing it again counts it twice. The engine builds a bank account's name, so a name prefix can no
longer mark the suite's accounts, and names are unique, so a second `…0000` account, the number every
sample prints, cannot exist beside the seed's.

**Rejected.** *Checking each fixture against the endpoint it mocks* — fixtures are not mapped to
endpoints. *Reading every local catch-all* — a widget's `**kwargs` would read as engine fields.
*Cleaning the practice user before each run* — it hides which test leaks. *Probes deleting what they
make* — a second user cannot leak into this one at all. *A hint "0.00 on the first one"* — not the
exact rule. *Calling the paper's figure the "starting balance"* — it changes words in use.

## A held reserved name is the engine's words alone, proven on each side (2026-10-25)

**Decision.** (1) A `RESERVED_NAME_HELD` refusal on `hashtag_ids` shows the engine's words alone
under the Edit form's parts ([tui.md](tui.md) §2 "When the engine says no"); the engine sends it on
the transaction's hashtags as a whole, never on one part's (contract: "Hashtags").
`test_a_held_reserved_name_shows_the_engines_words_alone_under_the_parts` in
[test_tui_edit_form_parts.py](../tests/unit/test_tui_edit_form_parts.py) pins it. (2) Its live proof
runs as the reserved-names practice user ([runtime.md](runtime.md)
"Working against the live engine"). (3) A test comment says what its case proves, never which spec's
pick it came from.

**Why.** The engine's words already say what to do. The shared practice user cannot reach the state:
its pending hashtag exists and can never be deleted, and no other hashtag may take the name
`Pendiente` (contract: "Hashtags"). A pick's name means nothing once its spec is deleted.

**Rejected.** *An app line for the refusal* — the engine's words are enough. *Faking the state on
the shared user* — the engine allows no way in.

## A close refuses a leftover line on a day it seals, and flags one on a day it leaves open (2026-11-09)

**Decision.** (1) A close or a statement PDF's upload refused `LOOSE_LINES_ON_SEALED_DAYS` shows the
engine's words; the app keeps no rule of which days a close seals
(contract: POST /v1/statements/{statement_id}/complete, "Validation"). (2) A close that goes through
may flag lines on days it leaves open (its last day, a gap); they show on a screen of its own right
after the complete and from the `⚑` line and `f`. That screen, the `⚑` count and whether the screen
opens go by the statement's review list and the engine's count of it, never a sum of `review_lines`
(contract: GET /v1/bank-lines, "It has no bound"). Details: [tui.md](tui.md) §4
"The lines a complete flagged for review" and "On the statement". (3) A statement is the account's,
covering its currencies, under the account's code
(contract: "What an account is", "Statement code"); codes are never matched across accounts. (4) The
"no statement" list's `!` reads `! dated inside a statement` ([tui.md](tui.md) §2). (5) The
reserved-names practice user's key is handled like the shared one's ([runtime.md](runtime.md)
"Working against the live engine").

**Why.** Once a month is closed, every line dated on its days is in a statement: a line left over is
wrong by definition, so it is resolved before the close, not reviewed after. A line on a day the
close leaves open may still be the next statement's, so it is flagged, not refused. Which days a
close seals and which lines it flags are engine rules; a copy per client drifts. The review list
rereads the flagged lines any time, in the statement's order; the count, read first, shows sooner.

**Rejected.** *Flagging every leftover line after the close* — a closed month would hold a line no
statement explains. *One read per flagged line, sorted by the app* — a call per line and a copied
ordering rule. *Listing them on the statement itself* — among its own lines, each needing keys of
its own. *Dropping the `!`* — it marks the lines worth opening first.

## The engine lists the currencies, dates each row and bounds every amount (2026-11-09)

**Decision.** (1) Every currency list and picker reads `GET /currencies`; the app keeps no list.
(2) A row shows on the engine's `day`, never a day the app works out from its moment. (3) An amount
past the largest is refused in the engine's words, typed or in a file; the app's reader refuses
what it cannot read for sure before anything is sent. (4) The statement PDF's preview lists the lines
the close will flag before `⏎`, under the table's columns, its count beside the others, with the
close's notes per currency (contract: POST /v1/statements/import, "Response").

**Why.** Each is an engine fact every client needs the same way, and a copy drifts: a currency
added, a time zone changed, a bound moved. The preview is where the owner checks an upload before
anything is written, so a line the close will flag shows there.

**Rejected.** *A count only in the preview* — the lines would show only after the close. *A day
worked out from the row's moment in the machine's zone* — wrong whenever the machine's zone is not
the user's.

## A statement PDF comes in through the import door, and its preview is the check (2026-10-27)

**Decision.** (1) A month's PDF is dropped on the LOG bar like a download, its account picked from
the same list; several files go one by one, and a file's kind is its name's ending alone
(contract: POST /v1/statements/import). (2) Both uploads send one body from `request_body`, as the
contract gives both routes the same three keys, and share base preview and result screens. (3) A
`CONCURRENT_CHANGE` on the apply leads to a fresh preview, never a resend, whatever key it names.
(4) The preview is the check against another account's PDF: the engine does not compare the paper's
number with the account. (5) The upload's small details follow the download's. (6) The live suite
draws its own statement PDFs, with no PDF library
([test_statement_import.py](../tests/contract/test_statement_import.py)'s docstring). (7) Balance
lines follow the engine's currency order; the app sorts nothing
(contract: POST /v1/statements/import, "Response"). Details: [tui.md](tui.md) §2
"A statement PDF closes its month", §4 "A dropped bank file".

**Why.** One door for every bank file is one place to learn; the engine reads the paper, the app
only sends it. The contract says to resend after the ledger moved. A wrong paper shows almost every
row as new before anything is written; comparing numbers belongs to accounts carrying them, a spec
of its own. A test PDF is fixed-width text at exact points, a few lines of code.

**Rejected.** *Soles first on a card* — the app would reorder the engine's answer, and clients could
differ. *Starting the upload from the statement on Reconciliations* — a key and a path field for
what a drop does. *A PDF dropped only alone* — a download and its PDF could not go in together.
*Keeping the tick-list on a coded account's open statement* — ticking cannot close the month there.
*Waiting for accounts to carry their numbers* — closing statements would wait on account names.

## An account holds its currencies (2026-10-28)

**Decision.** A bank account or a person is one account holding one or more currencies (a Peruvian
card holds soles and dollars; ALEJO owes in both). The account carries the name, colour, order,
kind, statement code and archived flag; each currency only its code, opening balance and balance, so
two currencies are never summed. A currency shows as the account's name and its code
("VISA Infinite Sapphire · USD").

**Why.** The owner works with the holder. Per-currency accounts under it, there only to keep
currencies apart yet each with its own name, colour, order, kind and archived flag and movable, made
two levels acting as an account, plus pairing, unpairing, person holders, one-account holders and
"the whole holder" for every client to teach. A balance per currency inside one account keeps both
levels, without the duplication.

**Rejected.** *Holders and per-currency accounts shown as one* — every client hides the same split,
and pairing and person holders remain. *Renaming holder to account and account to currency, nothing
else* — the duplication stays under new names. *One balance mixing currencies* — a total across
currencies means nothing.

## An account shows once and its currency is a field of its own; one currency shows, several are picked (2026-10-31)

**Decision.** (1) An account shows once on every screen and picker; `d` names it and each currency's
balance, since the delete removes them all. (2) The currency is a field of its own, picked like any
other. (3) One currency asks for none, several are picked before a save; the app then sends no currency and
a move sends the account alone, and the engine settles it, a row moved onto a one-currency account
taking that currency at the same amount, said as `· was USD · not converted` on the Edit form and
counted in `b`'s note. (4) A currency move keeps a draft statement and an account move takes the row
out, as the engine leaves the assignment to the client (contract: "Statements", "Assigning
transactions"). Details: [tui.md](tui.md) §2.

**Why.** An account holds its currencies and a transaction names both, so the account shows once and
the currency where it is chosen; a question with one possible answer is not asked, and the engine,
not each client, picks the only answer. An amount moves as it is, and the owner is told so where the
move is made, without a question that would follow every such move.

**Rejected.** *One row per account and currency* — it splits the account the owner thinks of. *The
currency typed after the amount* (`-45.50 USD`) — a field is picked like every other, and the legend
names it. *`b` asking every row's currency* — each row holds its own, and `m` is the currency key.
*Converting on a currency move* — the app holds no rates. *Asking before a move that changes
currency* — one more key on every such move, for what the line already says. *`d` naming one currency plus
"the others go too"* — it hides the balances the delete removes.

## The PDF upload and the two imports send the account (2026-10-30)

**Decision.** (1) Both import doors list one line per bank account with its currencies in the
engine's order (`formatting.currencies_phrase`) and send the account's id alone; the engine files
each row and PDF balance under its own currency. (2) The PDF preview shows a balance only for
currencies the answer covers. (3) The sheet's names table lists each account name once, its
currencies in `CUR`; `--create-names` makes one account per missing name. (4) A rename is the sheet
name alone (`--account-name SHEET_NAME=LEDGER_NAME`), and two sheet names may land on one account,
the engine judging. (5) One statement per account, covering its currencies
("A close flags lines instead of refusing, and a statement is the account's"). Details:
[tui.md](tui.md) §2 "The import door"; [commands.md](commands.md) "`expense import sheet`".

**Why.** An account holds its currencies (contract: "Bank Accounts", "`currencies`"), so a sheet
name, a door's pick and a statement are each the account's.

**Rejected.** *Renames per name and currency* — a name is one account, and the engine reads each
row's currency. *The client refusing two names onto one account* — the engine allows it and judges.
*Keeping a typed `Caja:USD` while a saved one reads as `Caja`* — a rename that holds one run only;
such a sheet name cannot be renamed.

## The live suite makes every record one way (2026-10-30)

**Decision.** Every live contract test makes records and checks refusals through the shared helpers
in [tests/contract/conftest.py](../tests/contract/conftest.py), with one cleanup; no test file
copies a helper. A test's account has no statement code unless the test is about codes, since a
coded account's statement must be ordered before it completes.

**Why.** One place to change when the engine's shapes change, and cleanup that cannot drift from
what was made.

**Rejected.** *Per-file body builders and refusal checks* — copies drift, and a check that only
finds the field's name in the answer proves less than the contract states.

## A live test's data passes only for the reason it states, and the suite tests the contract as it stands (2026-10-31)

**Decision.** (1) A live test's data passes only for the reason it states: an order test's rows
differ from date order, a left-alone test puts a look-alike beside. (2) A case the contract no
longer states is dropped, not ported. (3) Where engine and contract disagree, the suite tests what
both agree on and the catch-up's reply raises the rest. (4) Where the contract leaves a detail open,
the suite accepts every allowed answer and asks in the reply. (5) A case no request can build is
tested as what the contract says it equals, or left out with its reason.

**Why.** Data a wrong engine also passes proves nothing. A dropped case pins behaviour the engine
may change. Pinning a contract break defends the bug; pinning an open detail fails when the engine
picks another allowed answer.

**Rejected.** *Porting every old case* — it keeps rules the engine no longer states. *Pinning
today's behaviour where it breaks the contract* — it fails the day the engine is fixed.

## A screen's live test reads through the screen's own read (2026-11-03)

**Decision.** A live test of what a screen lists calls the screen's own read, through one function
both call (`fetch_month_lines` in [statements.py](../expense/tui/screens/statements.py) for a
statement's lines).

**Why.** A test that rebuilds the screen's arguments keeps passing after the screen changes what it
sends: a list the screen reads oldest first stays tested newest first.

**Rejected.** *The engine's filters tested with raw calls* — that proves the engine, not this
client's use of it.

## A live test dates a recent row and reads its month from one moment (2026-11-02)

**Decision.** A live test needing a transaction dated now logs it a minute ago in the practice
user's display timezone and takes its month from the same clock reading; each body comes from
`Scratch` in [tests/contract/conftest.py](../tests/contract/conftest.py).

**Why.** Noon today is future before noon, and the engine refuses a future date; two readings
straddle a month's turn; a minute off the wall clock can land on an hour a daylight-saving jump
skipped (`minute_before`, `recent_moment`). One body shape is one place to change.

**Rejected.** *Noon of yesterday* — the reports' tests need a row in the current month, which
yesterday is not on a month's first day.

## A list's one-write guard belongs to the write that set it (2026-11-02)

**Decision.** On Manage ▸ Accounts, `a`, `t`, `c` and `x` send one write at a time, under a guard
tied to the write that set it ([tui.md](tui.md) §2; `ResourceListScreen.run_guarded_write` in
[_base.py](../expense/tui/screens/_base.py)). It also lifts when that write is dropped behind
another's refusal.

**Why.** A key must act on a list that shows the write before it: a second `c` on rows read before
the add offers the new currency again, and the engine refuses it. A reload (`r`, a form closing)
lands with rows read before or after the write, and a refused write queued behind (`d`) never
reloads, so only the guarded write's aftermath says the list is fresh.

**Rejected.** *Lifting on every build* — `r` mid-write lifts it with stale rows. *Lifting on a build
with no write unanswered* — a refused `d` queued behind never reloads, so the guard stays until the
next read.

## What a spec finds becomes a spec only if the owner would see it (2026-11-02)

**Decision.** A find becomes a spec only if the owner would see it in the app or it is a money or
business rule; the rest goes to [todo.md](todo.md)'s Backlog ([CLAUDE.md](../CLAUDE.md)
"Specs and tasks", "Per spec").

**Why.** Otherwise every finished spec leaves a smaller leftovers spec, and leftovers leave
leftovers. Each spec costs an approval, a tester and a librarian run, which internal tidy-ups do not
need one by one, and the specs that need the owner get lost among them.

**Rejected.** *Every find a spec* — the list never shrinks. *One cleanup spec for the small
leftovers* — the owner still approves work they cannot see, and it keeps growing.

## One approval per spec, a queue of approved specs, small specs merged (2026-11-08)

**Decision.** The owner approves a spec, its answers and its tasks in one reply; approved specs
wait in [todo.md](todo.md)'s Queue and the loop runs them in order without stopping between
them; a spec of fewer than about 4 tasks merges into another ([CLAUDE.md](../CLAUDE.md)
"Specs and tasks", "Task size", "Per task" step 6).

**Why.** The owner felt the loop was slow. The session logs from 2026-10-28 to 2026-11-08 put
38% of this repo's loop time on waiting for the owner, more than the builders' 30%; the
reviewer, tester and librarian together took about 15%. Most waits sat between specs, or between
a spec's questions, its approval and its tasks' approval, and 41 specs in 11 days paid each
spec's fixed cost again and again.

**Rejected.** *Dropping the librarian* — about 4 minutes and 3% of the time, and it fixes a doc
in most runs. *Skipping the reviewer on small tasks* — refused 2026-10-16.

## The staged list's title and tags give way; OPERATION says it changes every part (2026-11-02)

**Decision.** Staged rows wider than the LOG bar cut the title and tags, never another cell
([tui.md](tui.md) §4 "The LOG bar's account is one row per account"). The OPERATION line says it
changes every part, as date, title, account and currency do ([tui.md](tui.md) §2
"A split transaction says what reaches every part").

**Why.** A staged row is checked by its amount, currency, account and category; the title was just
typed. The operation number belongs to the whole line, as the date does.

**Rejected.** *Title, category and tags share the cut* — similar categories read the same once cut.
*OPERATION without the note* — the one such line that would not say so.

## The PDF preview marks a line moved to the bank's day (2026-10-28)

**Decision.** A matched row the engine `redated` reads `✓ In the ledger · day moved`, with no old
day and no count (contract: POST /v1/statements/import, "The bank's day wins"); details:
[tui.md](tui.md) §2 "A statement PDF closes its month".

**Why.** The row is in the ledger like any match; a short mark says the line moves with no second
read and no taller row.

**Rejected.** *A dim line naming the old day* — a read per moved line for a day about to change, and
two lines per row. *Only a count under the table* — it says how many move, not which.

## Every screen's frame: no blank lines at the crumb, refusals under the form, `+` on incomes (2026-11-03)

**Decision.** On every screen: no blank line above or under the crumb; a form's refused save is a
block under the form until the next key, sized to fit 80×24; `^s` keeps what is typed as `⏎` would,
then saves, an untouched line keeping nothing; a long crumb is cut with `…` so the `!` rate alert
always shows; `pgup Prev` is off a list's first page; a positive transaction amount carries its `+`,
balances and sums none. Details: [tui.md](tui.md) §1, §3 "Amounts", §4, §5.

**Why.** Two rows gained per list let the Statements screens fit 80×24. A toast fades before it is
read or fixed. A value in the bar is typed as far as the user sees, and dropping it drew a refusal
for a value they gave. A footer offers only keys that act. The sign stays explicit with colour off,
as "Sign is always literal" holds for typing; a sum is not a transaction, but a split's count line
weighs the parts' sum against the total, so it writes both like the parts.

**Rejected.** *Keeping the blank lines* — two rows fewer per list. *Keeping the toast* — it fades.
*`^s` sending only lines entered with `⏎`* — the engine refuses the missing value. *`^s` keeping an
untouched line too* — on a choice line it picks the first account or colour for the user. *`+` on
balances and totals* — the drawings write them without one.

## The Statements screens say "statement", and a statement's screen follows its own layout (2026-11-05)

**Decision.** (1) The Statements screens say "statement", never "batch". (2) A refused complete is
lines between the head and the box until the next key; other refusals there stay toasts. (3) The
list refits, and a box under the head re-places itself, on Textual's `screen_layout_refresh_signal`,
so the `⚑` and refusal lines never cost the page line. (4) A difference not checked yet stays blank
on a draft too, as "A null difference is blank, a zero difference is the em-dash" holds. (5) An
unreadable balance's note names its currency. Details: [tui.md](tui.md) §4, §5.

**Why.** "Statement" is the owner's word. The box under the head is where the refused complete is
fixed; a toast covers it and fades. `call_after_refresh` runs after the top screen, so under a box
it measured the list too early and lost the page line on a slower terminal.

**Rejected.** *A dim `—` for a difference not checked yet* — it reads as "adds up". *Chained
`call_after_refresh`* — it raced the layout beneath a box at 20 fps and below.

## The app holds its settings from launch, and only the newest read hands back (2026-11-05)

**Decision.** (1) The app reads its settings once, at launch, and every engine call uses that copy
until setup's save replaces it ([runtime.md](runtime.md) "The settings file and a fresh start"). (2)
A read a newer read replaced is dropped on the UI thread ([tui.md](tui.md) §1
"A read a newer one replaced paints nothing").

**Why.** (1) Read per call, settings could not come from a pipe, so an agent's practice key would
reach a file. They are the app's own, not engine data, so holding them is no cache. (2) A worker's
`is_cancelled` runs on its thread, so a read could pass it just before a newer one began and still
paint or spend the cursor's landing line; only the UI thread knows the newest.

**Rejected.** *Passing settings into every screen* — about 25 call sites and every test that patches
them, for the same result. *Textual's exclusive workers alone* — cancelling does not stop a
hand-back already queued.

## A footer too wide for the screen tightens, then leaves keys out whole (2026-11-06)

**Decision.** Every footer is `FittingFooter` ([footer.py](../expense/tui/widgets/footer.py)): it
tightens first, then leaves keys out whole ([tui.md](tui.md) §5).

**Why.** Past a first page the footer gains `pgup Prev` ("Every screen's frame"), and Manage's
outgrows 80 columns and the ledger's 140. A cut key (`d Del`, `m Currenc`) reads as another word.
Tightening keeps every key at 80 columns, but the ledger past its first page needs 144 even
tightened.

**Rejected.** *Tightening alone* — the ledger's `d Delete` is still cut below 144 columns. *Leaving
keys out without tightening* — it drops keys tighter spacing keeps whole.

## The `?` card shows whole, and it and the footer list only keys that work (2026-11-08)

**Decision.** A card taller than its room spreads out on a wide terminal, else scrolls; one that
fits keeps its layout and covers what is behind it to its frame. It lists each key once, and a key
in `CARD_FOLLOWS_CHECK` only while it works, and one in `CARD_NEEDS_A_ROW` only while its list
holds a row, worded for the empty list where `CARD_TEXT_WHILE_EMPTY` says so ([tui.md](tui.md) §4).
The footer reads the same declaration: on an empty list a key needing a row leaves it, and comes
back with the first row; a key off only for a moment, such as the ledger's while a bulk write
runs, stays greyed ([tui.md](tui.md) §5).

**Why.** A narrow footer leaves keys for `?` to list, so a cut card left a key shown nowhere. A card
that fits keeps its familiar look; a row that does nothing lies, on an empty list too, and so does
a footer key; a screen peeking beside it looks half-drawn. One declaration keeps the footer and the
card from disagreeing.

**Rejected.** *Scrolling at every size* — a wide terminal can show it whole. *Spreading whenever the
terminal is wide* — a card that fits would change shape. *Off keys listed, dimmed* — rows that do
nothing. *An empty list's footer kept as with rows* — it offers keys that do nothing.

## A save you left still says how it ended (2026-11-06)

**Decision.** A write that can be left carries a `LeftBehind`
([_base.py](../expense/tui/screens/_base.py)): answered after its screen left, it shows the screen's
message, a refusal titled with what did not happen and to what; queued writes are still sent, a
refusal stopping none. What each screen says: [tui.md](tui.md) §1.

**Why.** An unseen refusal is a change you think happened, and once the screen is gone nothing holds
the queued writes for a retry.

**Rejected.** *One `Saved.` / `Not saved` for every save* — it hides which refusal and why. *Holding
`esc` until the save answers* — it keeps you on a form you left.

## A save whose ending is not known never says it was not saved, and its list reads again (2026-11-07)

**Decision.** After a server error or no answer, a left save shows the engine's words alone
(`open_it_again` in [_form.py](../expense/tui/screens/_form.py)). Its Manage list, if shown, reads again as after a save
that landed ([tui.md](tui.md) §1).

**Why.** Such a save may have landed, so "nothing was saved" would be untrue, and the list shows
whether it did without `r`.

**Rejected.** *`It may have saved: open it to check.`* — a new sentence where the ledger's Edit
forms say nothing more. *The list waiting for `r`* — it may hide a change that landed.

## Quitting asks while saves are still being sent (2026-11-06)

**Decision.** While any save is unanswered or waiting, on any screen, quitting asks first and only
`y` quits; a save of several writes counts once ([tui.md](tui.md) §1).

**Why.** Quitting drops what is still being sent, and you would not learn whether it landed.

**Rejected.** *Quitting at once* — the saves vanish silently. *Waiting for them* — an engine that
does not answer holds the app open.

## A unit test waits for what it checks, never for a fixed moment (2026-11-07)

**Decision.** A test waits through `wait_for` ([helpers.py](../tests/unit/helpers.py)), in that
screen's own test helpers, for what the app finishes a moment later, and fails if it never comes
([tui.md](tui.md) §6).

**Why.** A fixed pause passes on the owner's Mac and fails now and then on GitHub's slower runners.

**Rejected.** *Longer pauses* — slower and still a guess. *One general wait in `run_app`* — looser
than what each test reads.
