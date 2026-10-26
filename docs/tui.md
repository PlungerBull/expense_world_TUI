# The TUI — `expense`

What the Textual app **is**, in present tense. `expense`, run alone, opens it: the
one surface of this client ([decisions.md](decisions.md) "The TUI is the only
surface"), over the shared fetch/write layer; it implements **zero** business logic
(repo thin-wrapper rule).

Companions: [commands.md](commands.md) (the typed surface: the launch, the sheet
import and the settings file) ·
[runtime.md](runtime.md) (read/write semantics, which apply to the TUI
unchanged) · [decisions.md](decisions.md) (why the calls below went the way they did) ·
[mockups/](mockups/) (the approval gate for every screen).

---

## 1. Architecture

```
expense/tui/
  app.py            # ExpenseApp(App): screen stack, global bindings, worker helper
  app.tcss          # Textual CSS — layout + the structural ANSI fills (§3)
  theme.py          # the ANSI Theme + the PALETTE constant Rich content styles with
  dropped.py        # dropped_bank_files() — is the LOG bar's line a dropped/pasted
                    #   bank file (or several)? Pure: text in, paths or None out
  widgets/
    header.py       # Breadcrumb — slim section header (home banner lives in home.py)
                    #   + rate_alert() — the `!` staleness mark both headers share
    cells.py        # cell renderers: color swatch, sign-colored right-aligned amount_cell
                    #   (amount_text: the same as Text, for a line that appends it),
                    #   code_cell (a code, or a dim `—` when there is none);
                    #   `—` for a null amount, BLANK for a null difference_cents
                    #   (different states, never the same glyph — decisions.md)
    windowed.py     # CURSOR_STYLE (reverse video, app-wide) + WindowedList — the
                    #   window/cursor/page arithmetic both list widgets stand on
                    #   + page_indicator() — `rows 21-40 of 133 · page 2 of 7`
    cursor_list.py  # CursorList — arrow-key list, window + growing modes
                    #   + list_table() — the table it draws, which the bulk pick
                    #   also draws the ledger's rows with
                    #   + CursorOptionList — the home menu
    checklist.py    # CheckList — the reconciliation tick-list, one bank line per row
    picker.py       # suggestion_list() — the scrolling name list the quick-add
                    #   surfaces and the bulk pick drop under their input
    refusal.py      # hanging() — the `! …` line a screen keeps under a refusal
                    #   (the import door's preview and result, the Edit form)
                    #   + under_itself() — words wrapping under themselves
                    #   after a head, as the Edit form's read-only sentences do
                    #   + toast() — a toast whose words the app did not write,
                    #   shown as text; as_markup() — words set inside the app's
                    #   own markup, every `[` escaped
                    #   + run_stopped() — the one note for a refusal that stops
                    #   a run of writes (the LOG bar's save, the bulk edit)
    parts_table.py  # the Edit form's parts: the Part model, the table, the dim
                    #   `read-only` lines and the engine's sentence for each, the
                    #   line adding the parts up, and a refused save's lines;
                    #   pure builders
  screens/
    _base.py        # run_write + confirm_delete (EngineWriteMixin), SectionScreen, keymap
    _form.py        # FormScreen base — fields, validation, bar-cycle plumbing
    _growing.py     # GrowingRead — a list that grows by cursor (ledger, "no batch" pane)
    help.py         # HelpModal — the `?` card, derived from BINDINGS (§4)
    home.py         # four months × categories, balances today, then every screen
    transactions.py # the ledger — whole, or filtered by Home; `space` + `c`/`b`/`h` bulk
                    #   edits; `⏎` and `s` open the Edit form, `d` deletes the cursor row
    bulk_pick.py    # BulkPickScreen — what `c`/`b`/`h` open: the rows they change
                    #   over one bar and its suggestion list; writes nothing itself
    accounts.py     categories.py  hashtags.py
    reconciliations.py               # full lifecycle
    system.py       # Config / Auth screens
    setup.py        # SetupScreen — first-time setup: engine address + key, then a
                    #   profile; what the app opens on with no usable settings file
    edit_form.py    # the Edit form (`⏎` and `s` on a row); `record` is required. The
                    #   line's shared fields, then every part, saved in one
                    #   PUT /bank-lines/{id} (body by expense/bank_line_write.py);
                    #   what is read-only is the line's `edit_limits`
                    #   + BankLineEditFormScreen — the same form on a line of the
                    #   "no batch" list, OPERATION among its shared fields
    log_bar.py      # the LOG bar — what `+` opens. One typed line, a staged batch,
                    #   the named account's ledger below it (AccountPeek), one save.
                    #   Parses through expense/quickadd/; `↵` stages a line or refuses
                    #   it in place; ctrl+s writes every row through POST
                    #   /transactions/batch (via expense/batch_write.py; chunking in
                    #   runtime.md "Bulk writes"). Saved rows
                    #   keep a ✓ until the next line is staged; a partial failure
                    #   re-sends only the rest.
    bank_import.py  # the import door behind the LOG bar: a dropped bank file →
                    #   which account → preview → result, one file after another.
                    #   Reads, previews and applies through expense/bank_import/
                    #   (flow.py)
    create_forms.py # BarFormScreen + New{Account,Category,Hashtag} small forms
                    #   New account carries a TYPE field (bank/person, prefilled
                    #   bank) that picks POST /accounts vs POST /people; the
                    #   account Edit form carries the opening balance (§2).
                    #   COLOR is optional on New account and New category
                    #   (hints: §4 "The bar forms' keys"): a skipped
                    #   colour is left out of the body, never sent as null, and
                    #   the engine gives its default (contract: POST /v1/categories).
                    #   While an optional line is empty no swatch is highlighted;
                    #   typing or ↑/↓ highlights one, and enter then picks it.
                    #   Edit category keeps it required, so a PUT never sends null;
                    #   on an Edit screen the line starts on the row's own colour
                    #   ("Stepping past COLOR keeps it", §2)
    modals.py       # ConfirmModal, DiscardStagedModal (the LOG bar's one
                    #   confirmation), and PromptBox — one line typed in a box —
                    #   under PromptModal (text) and AmountPromptModal (a signed
                    #   amount, read by the shared money parser)
```

**The fetch/draw split is the anti-duplication guardrail.** Every engine read is a
pure `fetch_*(cfg, …) -> dict` the screens call; a screen never reimplements one. The
engine reads live in [reads.py](../expense/reads.py), the formatters in
[formatting.py](../expense/formatting.py), the bank-import steps in
[bank_import/flow.py](../expense/bank_import/flow.py) — none of them under
`expense/commands/`, which holds only what `expense import sheet` alone uses
(guard: [test_shared_code_home.py](../tests/unit/test_shared_code_home.py)). Write
plumbing in [_base.py](../expense/tui/screens/_base.py), form scaffolding in
[_form.py](../expense/tui/screens/_form.py).

**One reader for every typed amount.** `parse_amount` in
[quickadd/money.py](../expense/quickadd/money.py) reads the amount on the LOG bar, the Edit
form, an account's opening balance, a new reconciliation's two balances and
the reconciliation's `Ending balance first` box. It takes a signed decimal with a dot for its
decimals (`-99.92`, `13853.20`); every comma is dropped as a thousands mark (`13,853.20`,
`1,000`) unless one comes after the dot. An amount with a comma after its dot (`13.853,20`,
`-12.50,`) is unreadable, never read as 13.85: each form field refuses it with its own note and
the cursor stays (the box stays open), and on the LOG bar it is no amount, so `↵` refuses the
line with a note naming the first signed number it couldn't read, as typed:
`can't read -13.853,20 as an amount`. A line with no signed number at all is refused with
`the line has no amount — a number needs a sign to be one`. `nan`, `inf`, `Infinity`
and an amount whose cents overflow (`1e999999`) are unreadable too. The two importers read an
amount cell through the same reader, by `amount_to_cents` in
[import_/parse.py](../expense/import_/parse.py): a text cell as typed, a number cell as its
value, so a cell that is not an amount (`13.853,20`, `nan`, `inf`, as text or as a number)
refuses its own row and the rest of the file is read — in a bank file as
`Couldn't read the row` (§2 "Each row's mark and reason"), in the sheet as
[commands.md](commands.md) "`expense import sheet`" says.

**Async / workers.** Textual runs on asyncio; the engine client is synchronous, and
stays that way. It is called inside a Textual worker (`@work(thread=True)`) so the UI
never blocks. Read screens subclass `SectionScreen` and override `fetch()` (runs in
the worker) + `build(data)`; writes go through `EngineWriteMixin.run_write` in its own
worker group — a FIFO queue, one write in flight, and an error drops the queued
remainder. `writes_unanswered()` lists the write in flight and the queued ones, and the
`_writes_dropped(failed, dropped)` hook runs after a refusal, so a screen can redraw what
it showed of the writes that were never sent.

**A thread worker hands back through `call_while_attached`.** A thread worker cannot be
stopped, so a read still in flight when its screen is popped or the app quits still
lands, and painting it then queries widgets already taken down (`NoMatches`). Textual
cancels a node's workers only on its Unmount, after its children are gone, so a check in
the worker is too early. `call_while_attached(node, callback, …)` in
[_base.py](../expense/tui/screens/_base.py) makes the check on the UI thread, at the
moment the callback would run, and drops it once the node has left the app.
`SectionScreen._load`, every worker of the LOG bar and the Edit form's reads hand back
this way.

**Invariant: `build()` runs on the UI thread and must never do HTTP.** Where a render
needs resolved names, resolve them in `fetch()` and hand `build()` precomputed cells —
`TransactionsScreen` is the worked example (`fetch()` reads the page and the three name
maps, and `build()` only looks names up in them).

**Name resolution is live HTTP and fails silently by design.**
`load_account_name_map` / `load_category_name_map` / `load_hashtag_name_map` each open
their own client and page the reference list; on **any** failure they return `{}` and
renderers fall back to 8-char short ids. `load_account_index`, what the ledger reads, is the
same accounts read giving the names and the archived ids together; on a failure it has
neither, so no key leaves the ledger's footer. No toast, no error. If a user ever reports
"my tables show hex ids", the cause is the engine rejecting reference-list reads
(auth/config), never data loss. Every call site must be inside a worker thread.

### The header rate alert

Every header carries a `!` when today has no exchange rate of its own — meaning every
home-currency figure on screen is priced at an older day's rate. The trigger is
deliberately sensitive (no grace period), so it also shows on an ordinary morning before
the engine's fetch job has run.

- **No dedicated engine surface.** `GET /exchange-rates` returns the day you asked about
  (`date`) and the day it actually used (`rate_date`); the whole signal is
  `rate_date < date`, which covers every failure mode. `reads.rate_is_stale`
  applies it; `fetch_rate_staleness` adds the `404` case (no rate at all → stale).
  There is no screen behind the mark.
- **App-owned, fetched once per launch.** `ExpenseApp.rate_stale` holds `True` /
  `False` / `None`, filled by one worker on mount. A screen pushed after the fetch
  reads the value itself; one already mounted is repainted (breadcrumbs by query, home
  via its `repaint_header` hook).
- **`None` renders nothing.** Offline, unconfigured, pre-fetch, or an unexpected body
  shape all mean "don't know". Warning-colored, not error: a carried-forward rate is
  the engine's designed fallback.
- Guard: [tests/unit/test_rate_alert.py](../tests/unit/test_rate_alert.py).

---

## 2. Screens

**Setup comes first when there is nothing to connect with.** With no settings file, or
one that cannot be read (damaged, half-written, not a config — `config.load_usable`),
`launch` in [app.py](../expense/tui/app.py) opens the app with `SetupScreen`
([setup.py](../expense/tui/screens/setup.py)) pushed over Home, crumb `Setup`, drawn like
the bar forms (screens in
[expense-world-first-time-setup.html](mockups/expense-world-first-time-setup.html)):

| Question | Starts as | `⏎` |
|---|---|---|
| **ENGINE ADDRESS** | the local engine's address (`config.LOCAL_ENGINE_URL`), listed with `*` until accepted | accepts it, or refuses an answer that is not a full http(s) URL in place — red, with the local address as the example — before anything is sent |
| **KEY** | empty, hidden as typed; listed masked (`ewe_pat_****wxyz`) once given | asks the engine (below) |
| **YOUR NAME** | asked only when the engine accepts the key and has no profile for it | the next question, or creates the profile |
| **TIME ZONE** | read from this Mac and listed `read-only`; asked as one more question only when it cannot be read | creates the profile |

The key's `⏎` (or `^s Connect` from either field) shows `asking the engine…` and asks two
things with the address and key as typed: `GET /health`, which needs no key, then
`GET /auth/me` (contract: "Base Conventions", "Authentication") (contract: GET /v1/auth/me).
A failure goes red where the hint was, with the cursor on the answer to fix:

- **No engine answers** (`/health` fails) — the client's `could not reach engine at …` and
  `nothing was saved · start the engine or fix the address, then enter`; back on the
  address, the key kept.
- **`401 UNAUTHORIZED`** — the engine's own `CODE — message`, no hint, and `nothing was
  saved · type the key again, then enter`; back on an empty key line. Branched on the code.
- **`404 NOT_FOUND`** — not a failure: the key is fine and has no profile, so YOUR NAME (and
  TIME ZONE) appear and `^s` reads `Create`. Creating is `POST /auth/bootstrap` with the
  name exactly as typed and the zone; the engine's refusal (an empty name, an unknown zone)
  shows in its own words and the cursor stays (contract: POST /v1/auth/bootstrap).
- Any other refusal shows in the shared error text with `nothing was saved · enter to try
  again`.

**Nothing is written to the settings file until setup is done** — the engine has answered
`/auth/me` with 200, or the profile was created. Then the file is saved through
`config.save` (chmod 600) with the home currency the engine named, Setup closes onto Home
with `Connected.`, and the launch-time rate check runs. `esc Quit` leaves the app with
nothing saved; while the engine is being asked no key does anything (the bar is disabled).
A refused profile shows the engine's words without the shared text's hints, which point at
System screens Setup cannot reach. The next launch with
a usable file opens on Home; changing the address or key later is System ▸ Config.

**Home is four months of the ledger.** One worker reads `/dashboard` and `/reports/monthly` and draws:

| Section | Rows | `⏎` |
|---|---|---|
| **CATEGORIES** · four month columns, the newest marked `▸` | every category with activity somewhere in the window, home currency, `—` for a month with none, `3 unrated` when unpriceable — **a category with nothing in the whole window is hidden**. `→` unfolds its hashtag rows, `←` folds them, `@Pendiente` included. Under them: `inflow`, `outflow`, `net` | the ledger filtered to that category, every month |
| hashtag row (unfolded) | the category's spend on that hashtag, per month, one row per row of the engine's `hashtag_breakdown`, under the name `GET /hashtags` gives it. The rows still waiting for a hashtag are the **pending hashtag's row** (`#Pendiente`), dim like every hashtag row: the engine groups the pending hashtag like any other, so `hashtag_ids` is never empty (contract: GET /v1/dashboard) | the ledger filtered to **that category and that hashtag** (`?category_id=&hashtag_id=`); on the pending row, that category's transactions still waiting for a hashtag (contract: GET /v1/transactions). A combo of several hashtags is drawn so the sums add up, but `⏎` on it says it cannot be filtered — the engine filters by one hashtag |
| **BANK ACCOUNTS** · *balance today* | every account with `current_balance_cents` in its own currency, the code beside it | the ledger filtered to that account |
| **PEOPLE** | outstanding people in their own currency; settled ones folded behind `▶ N settled` (`⏎`/`→` opens it); `none` when there is nobody | the ledger filtered to that person |
| **LEDGER** | Transactions · Reconciliations, each a row of its own | `⏎` on an entry pushes the screen |
| **MANAGE** | Accounts · Categories · Hashtags | as above |
| **SYSTEM** | Config · Auth & profile | as above |

`pgdn` walks the window one month back, `pgup` one month forward and never past this
month. Balances do not move with it — there is no balances-as-of-date endpoint — so
their header always says `balance today`. The window and fold keys are
`priority=True` because the menu is an `OptionList`, which binds `pgdn`/`pgup` to its own
page scroll. LEDGER, MANAGE and SYSTEM never fold. The screen rows are there before the
reads land and after they fail — a failure is one dim row with the reason, and `r`
re-reads. The first month to land moves the cursor to the first category; later re-reads
leave it where it was. The wordmark line carries the window's newest month on the right.
`_SCREENS` in [home.py](../expense/tui/screens/home.py) maps entry id → screen, kept in
lockstep by `test_screens_map_covers_every_section_entry`. Logging a transaction is
**`+`**, not a menu row — see §4. Each unfolded category costs its hashtag count in
lines; past the terminal's height the list scrolls.

**The filtered ledger is the categorising pass.** `⏎` on a Home row pushes
[transactions.py](../expense/tui/screens/transactions.py) with a `LedgerFilter`: the
crumb reads `Ledger ▸ @Pendiente`, the panel is titled for the filter, the fetch is the
engine's own `?category_id=` / `?account_id=`, and the legend says `filter: category
@Pendiente · 20 of 57 loaded · 3 selected`. `space` selects rows (a `●` in the title gutter,
the row in the accent), `a` selects every loaded row or clears them, and `c` / `b` / `h` open
the bulk pick for the selection — or for the cursor row when nothing is selected —
to set the category, move to an account, or **replace** the hashtag set. The write is
one `PUT /transactions/{id}` per row, in order, on one client, then the list reads fresh
from the newest 10 with the cursor on row 1: on a filtered list the changed rows **leave
at once**, the toast `3 rows → KORAKUEN` is the receipt, and a refused row (an account
move a completed reconciliation locks) is named by number and does not stop the others,
in a note read as the LOG bar reads one ("Refused rows read one line per kind of error" below).
The one refusal that does stop them is `SETTINGS_MISSING`
([runtime.md](runtime.md) "Bulk writes"): the rows after it are never sent, and stay
selected with the refused one, and it shows once, in the note the LOG bar shows for it
("Refused rows read one line per kind of error" below).
A row stays selected only if the fresh read brings it back among the newest 10; further down
it drops out of the selection.

**The bulk pick is a full screen** ([bulk_pick.py](../expense/tui/screens/bulk_pick.py),
Question 6 B of [expense-world-wording-picks.html](mockups/expense-world-wording-picks.html)),
not a pop-up: it carries rows. Its crumb adds `Category for 3 rows` (`Account for …`,
`Hashtags for …`; `1 row` for one) to the ledger's. On top, dim, `the 3 rows it changes`, and
under it those rows in the ledger's own columns, title gutter and amount colours
(`changed_rows` in [transactions.py](../expense/tui/screens/transactions.py), drawn by
`list_table` in [cursor_list.py](../expense/tui/widgets/cursor_list.py), the table `CursorList`
draws), at most five, then a dim `+ N more` under their titles. Then one bar, `CATEGORY`,
`ACCOUNT` or `HASHTAGS`, its hint, and the list under it in the engine's order, drawn
and filtered as on the Edit form's entity lines (`suggestion_list` and `matching` in
[picker.py](../expense/tui/widgets/picker.py)). Typing narrows the list and highlights its
first match, `↑↓` move the highlight, and `esc` goes back to the ledger with nothing sent
and the selection as it was; the footer is `esc Cancel` alone. On `CATEGORY` and `ACCOUNT`
the hint reads `type to narrow · ↑↓ highlight · enter picks it for the 3 rows · esc cancels`,
and `⏎` picks the highlighted name for every row (with nothing typed, the first); a bar that
matches nothing says `Nothing matches “…”.` and stays. On `HASHTAGS` it reads
`replaces every tag on the 3 rows · enter adds · empty enter applies · ⌫ drops the last`:
`⏎` on a typed name adds the highlighted tag to the `picked` line under the list
(`picked    #casa`; `(none yet)` before the first) and empties the bar, a picked tag leaves
the list, `⌫` on the
empty bar drops the last pick, and `⏎` on the empty bar applies; with nothing picked it says
`Pick at least one tag, or esc to leave the rows as they are.` rather than clear every tag.
The screen writes nothing: the ledger sends its `PUT`s with the pick, as above.
**Stepping past ACCOUNT or CATEGORY keeps them** (Question 1 A of
[expense-world-enter-and-esc.html](mockups/expense-world-enter-and-esc.html)). On the Edit
form the ACCOUNT line and each part's CATEGORY line open with the bar empty and the whole list
in its usual order, the highlight on the line's own account or the part's own category, so `⏎`
with nothing typed keeps it and moves on: `⏎` on every line and then `ctrl+s` send nothing and
say `No changes to save.` Typing filters the list and highlights its first match, `↑↓` choose
another, and a bar emptied again puts the highlight back on the line's or part's own.
CATEGORY's list is the one the ledger's `c` offers (`pickable_categories` in
[reads.py](../expense/reads.py)): `@Pendiente` is in it, where the engine lists it, so on a
part in `@Pendiente` the highlight starts on it and `⏎` keeps it, and picking it on another
part sends that part back to waiting for a category (Question 3 A of the same mockup);
`@Opening` is never in it. A value the list does not hold leaves the highlight on the first
entry, and there `⏎` with nothing typed takes that entry. The "no batch" Edit form works the
same (`_recompute` in [edit_form.py](../expense/tui/screens/edit_form.py)).
**Stepping past COLOR keeps it** on the Edit screens of Manage ▸ Categories and Manage ▸
Accounts. The line opens with the bar empty and the highlight on the row's own swatch, so `⏎`
with nothing typed keeps it and the summary goes on showing it; typing filters and highlights
the first match, `↑↓` choose another, and a bar emptied again puts the highlight back on the
row's own. An account with no colour opens on nothing, and `⏎` skips the line (`—
(optional)`). A colour no swatch shows (the engine's own, on a row created with none) highlights
nothing and `⏎` keeps it, on a category too, where COLOR is required; the summary shows it as
its hex. The save sends `color` only when another swatch was picked, so `⏎` down every line
saves the name alone and the engine keeps the colour (`_edit_payload` in
[create_forms.py](../expense/tui/screens/create_forms.py)).
**A move takes a row out of its reconciliation.** The engine refuses an account change on
a row in a draft reconciliation unless the write also says what happens to the assignment
(contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id}), so `b` adds
`reconciliation_id: null` to each row whose account changes, and only to those: a row
already on the picked account keeps its reconciliation. The Edit form adds
`reconciliation_id: null` beside its parts the same way when the line's account changes
(contract: PUT /v1/bank-lines/{bank_line_id}, "Rules"); both share `unassign_on_move`
in [edit_form.py](../expense/tui/screens/edit_form.py). The receipt after `b` counts what the
engine says moved: each `PUT` answers with `changed_parts`, every part whose line field the
write changed and whether it left its reconciliation
(contract: PUT /v1/transactions/{transaction_id}, "Response"), and `b` counts the distinct parts
across the answers that landed and those flagged as leaving — `3 rows → BCP USD · 2 left their
reconciliation` (`· 1 left its reconciliation` for one) — with nothing read to count them
(`moved_parts` in [edit_form.py](../expense/tui/screens/edit_form.py)). A row already on
the picked account lists no part, so it is not counted, and a move that changes nothing shows
no receipt; a refused row is still named. The Edit form reads its save's answer the same way
(`moved_parts`; contract: PUT /v1/bank-lines/{bank_line_id}, "Response"): it says
`Saved. It left its reconciliation.` when the answer flags any part as leaving, and `Saved.`
when `changed_parts` is `[]` or flags none, never judging from the line as read before the
save.
**An emptied note empties it.** `⏎` on a part's emptied NOTE empties the note: the save sends
the part's `description: ""` and says `Saved.`; the engine refuses `null` there as `NOT_NULL`
(contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").
On a part with no note it is no change. No field the form sends is `null` except
`operation_code`, which `null` clears, and the `reconciliation_id: null` a move adds.
**A date the form can't read is refused at `⏎`.** On DATE, on the Edit form from the ledger
and from "no batch" alike, `⏎` checks the bar with the reader the save uses
(`is_readable_date` in [dates.py](../expense/dates.py)): a day `2026-10-23`, with or without
a time (`2026-10-23 14:30`), is taken, and an emptied bar commits today. Anything else, `abc`
say, notes `Date: use YYYY-MM-DD.` as an error, the words New reconciliation's dates and the
opening balance's `as of` use; the bar keeps what was typed, the cursor stays on DATE, and the
line keeps its value, so a `ctrl+s` after it never sends the unread date.
**An opening balance stays on its account and in @Opening.** The engine refuses to move
such a row to another account or category, `@Pendiente` included, and accepts every other
field (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put"); screens in
[expense-world-opening-balance-rows.html](mockups/expense-world-opening-balance-rows.html).
An opening balance also carries no hashtag, not even the pending one
(contract: PUT /v1/transactions/{transaction_id}); screen 6 A in
[expense-world-pending-hashtag-manage.html](mockups/expense-world-pending-hashtag-manage.html).
Its bank line keeps its one part
(contract: PUT /v1/bank-lines/{bank_line_id}, "A line holding an opening balance keeps its parts").
The Edit form reads all of it from the line's `edit_limits` ("What is read-only is the line's
`edit_limits`" below): `account` reads `read-only`, the part's category and hashtags cells are
dimmed under a dim `category  read-only` and `hashtags  read-only`, each with the engine's
sentence for it, every field move (`tab`,
`shift+tab` and the arrows) skips them, the save never sends them, and there is no `^n` or
`^x`; date, title, amount and note save as on any line. `b`, `c` and `h` send such a row like any other, and the engine
refuses it: its "Refused" note is the engine's words for the field, the row, then the line saying what to do
("When the engine says no" below), the other rows still go, and the refused row stays
selected. The LOG bar is untouched: it only creates rows, and a typed line cannot name
@Opening.
**A split transaction says what reaches every part.** The engine writes a line's date,
title and account onto every part of it, in one go, while amount, category, hashtags and note
stay each part's own (contract: "Transactions (Ledger)", "Bank lines"). So while the Edit form's
table holds two parts or more, its hint under the bar adds
`· changes every part of the transaction`, in the accent, while the bar is on date, title or
account, and says nothing more on a part's lines; screen 1 B in
[expense-world-edit-part.html](mockups/expense-world-edit-part.html). On a line of one part
the hints are as on any form.
The ledger's bulk keys follow the same rule on a part: `c` and `h` change only the selected
parts, and `b` on one part moves the whole transaction, every part leaving its reconciliation
with it, in the engine's one write
(contract: PUT /v1/transactions/{transaction_id}, "Line fields").
The app sends one `PUT` per selected row either way and fans nothing out itself. With every
part of a split transaction selected, each part gets its own `PUT`; a later one finds the line
already moved and the engine accepts it as it is, since the `PUT` carries no `version`. `b`
counts the parts the engine says moved, so one part of a 60 + 40 transaction in a draft
reconciliation reads `2 rows → … · 2 left their reconciliation`, and both parts selected still
read `2 rows`; `c` and `h` count the rows they wrote.
**`⏎` and `s` open the Edit form** ([edit_form.py](../expense/tui/screens/edit_form.py),
[expense-world-split-transaction-screen.html](mockups/expense-world-split-transaction-screen.html),
picks 1 A and 3 A to 6 A). `⏎` on any ledger row and `s` on the cursor row open the same full
screen, its crumb `Capture & ledger ▸ Transactions ▸ Edit`, the bar on the same line either way:
DATE, or the first line that can change when the line's `edit_limits` makes DATE read-only
("What is read-only is the line's `edit_limits`" below). `s Edit` sits
in the ledger's footer before `d Delete`, whole ledger or filtered from Home, its `?` card line
"Edit the transaction and its parts" (screen 1 A of
[expense-world-edit-form-words.html](mockups/expense-world-edit-form-words.html)), and like `d` it
works on the cursor row only: off, and out of the footer, while rows are selected, while a bulk
write runs, or on an empty list. On an archived account's row `s` stays and `d` goes ("On an
archived account's row the ledger offers no `d`" below). The form reads the reference lists and
the row's bank line, one `GET /bank-lines/{id}` by its `bank_line_id` (`fetch_bank_line` in
[reads.py](../expense/reads.py)): its `parts` in the engine's order, its signed `net_cents`
total and its `edit_limits` (contract: GET /v1/bank-lines/{bank_line_id}, "Response fields").
Each part comes as a magnitude and its `transaction_type`, signed by `signed_cents` in
[formatting.py](../expense/formatting.py). Until both reads are in the form takes nothing
typed; a failed read says why in a toast (`format_error`) and the form saves nothing.
**On top, the line's shared fields**: `date`, `title` and `account`, as the summary of any bar
form. Under them **the parts table** ([parts_table.py](../expense/tui/widgets/parts_table.py)):
`amount  category  hashtags  note`, dim, then each part numbered, a transaction never split
being its line's one part 1. A part with no amount, category or real hashtag reads `—` there
(no category is `@Pendiente`, the pending hashtag alone is no hashtag); no note reads blank.
The part the bar is on reads `▌ 2 …`, bold in the accent; an amount reads in its sign's colour.
With two parts or more the line adding them up follows:
`2 parts  ·  -100.00 of -100.00  ✓`, the tick in the success colour, or
`2 parts  ·  -90.00 of -100.00  ·  -10.00 left`, `-10.00 left` in the error colour: the
parts' amounts summed against the engine's total. It never stops a save.
**The bar walks every line**: the shared fields, then each part's `PART 1 AMOUNT`,
`PART 1 CATEGORY`, `PART 1 HASHTAGS` and `PART 1 NOTE`, then part 2's, one line per `⏎`, `⇥`
or arrow, as on every bar form ("The bar forms' keys", §4). AMOUNT and NOTE open on what the
part holds; ACCOUNT and a part's CATEGORY and HASHTAGS open with the bar empty and the list
under it (below). `⏎` on HASHTAGS with a name typed adds that hashtag and stays for another;
with nothing typed it moves on. A part's NOTE hint reads `optional · enter to go on` where `⏎`
goes on to the next part, and `optional · enter saves · (ctrl+s anytime)` on the last line. An
amount that is not a number, a zero amount, or a name that matches nothing is not kept: a toast
says why and the bar stays.
**`^n Add part`** adds an empty part at the end of the table, the bar on its AMOUNT.
**`^x Drop part`**, on a part's line while the table holds two parts or more, drops that part
at once, the bar moving to the same line of the part above (part 1's when the first goes).
A part added and left with nothing in it is left out of the save; a part holding only the
pending hashtag counts as empty, since the table never shows it and the save sends no hashtag
for it (`part_empty`).
**What is read-only is the line's `edit_limits`, and nothing else**
(contract: GET /v1/bank-lines/{bank_line_id}, "Response fields"). Each field it names carries
`{reason, message}`: the reason the write refuses that field with and the engine's sentence for
it, the write's own words. A line field its `locked_fields` names reads dimmed with
`read-only` beside its value; a part field its `locked_part_fields` names for that part's id is
dimmed in its cell, and under the table a dim `amount  read-only` (`category`, `hashtags`,
`note`) line names each column read-only on some part. **Each says why, in the engine's
sentence** (screen 1 B of
[expense-world-read-only-reasons.html](mockups/expense-world-read-only-reasons.html)): under
the line fields, one dim line per distinct sentence names the lines it covers by their names on
the form, in the form's order, then the sentence
(`date, title, account: Locked by completed reconciliation.`; a field the form has no line for,
such as `reconciliation_id`, is named nowhere); under the parts, each column's line carries its
sentence, `amount  read-only · The parts must add up to the line's total.`, two parts locked in
one column for different sentences showing each once, joined by ` · `. A long sentence wraps:
beside a column's `read-only`, under the `·` that opens it; under the shared fields, under its
own first word. Every sentence is the engine's `message` as sent, shown as text,
never as styling (`reason_lines` and `readonly_lines` in
[parts_table.py](../expense/tui/widgets/parts_table.py)); the app keeps no table from reason to
sentence. The "no batch" Edit form shows the same, OPERATION among the lines it names. Every
field move skips them, and the form opens on its first line that can change. Where
`parts_fixed` holds (an opening balance's line, a line on an archived account) neither `^n` nor
`^x` shows. Where `total_fixed` holds and `parts_fixed` does not (a line in a completed
reconciliation), an amount `locked_part_fields` names is a one-part line's total: it holds while
the table has one part, and opens once a part is added, since amounts may be redistributed with
the total kept (contract: PUT /v1/bank-lines/{bank_line_id}, "The total"). A field that turns
read-only again (the added part dropped) goes back to the value read from the line, so a
read-only cell always shows and sends the line's own value. The app keeps no
copy of the engine's locking rules.
**`ctrl+s` sends one `PUT /bank-lines/{id}`** through `run_write` (one idempotency key, the
same on a retry), the body built by [bank_line_write.py](../expense/bank_line_write.py), the one
home for every whole-line write. It first keeps what is typed in the bar, as `⏎` would. Beside
`parts` go the line fields the owner changed, never a read-only one, and never `statement_line`
or `statement_place` (contract: PUT /v1/bank-lines/{bank_line_id}, "Body"). `parts` is the
line's whole set (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"): a part read from the
line goes under its own id with its signed `amount_cents` as it is, and beside it only what
changed: a new `category_id`, an emptied note as `description: ""`, and `hashtag_ids` only when
its set of real hashtags changed, since a kept part sent with them is always written, even with
the set it has
(contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").
A part added here goes under a fresh id with what it holds, its hashtags through
`hashtags_to_send` with `pending_alone=False`, so a part with only the pending hashtag sends
none; a part dropped with `^x` is left out, so the engine deletes it. An account changed also
sends `reconciliation_id: null` ("A move takes a row out of its reconciliation" above). With no
line field changed, the same parts and each kept part holding only its id and amount, the form
says `No changes to save.` and sends nothing. Saved, it says `Saved.`, or
`Saved. It left its reconciliation.` when the answer flags a part as leaving, closes, and the
ledger reads fresh from the newest 10, cursor on row 1.
**A refused save stays under the parts** until something changes: the engine's
`CODE — message` in the error colour, one `! <key>: <words>` line per refused key with
`parts.<i>.<field>` read as `part i+1 (field)`, the field named by its column's word
(`amount_cents` reads `amount`, `category_id` `category`, `hashtag_ids` `hashtags`,
`description` `note`, and a part field with no column as sent, e.g. `part 1 (id)`;
`FIELD_WORDS` in [parts_table.py](../expense/tui/widgets/parts_table.py), the index read by
`key_index` in [errors.py](../expense/errors.py)) and any other key as sent (`! title: …`), each
hanging under its own words (`hanging` in
[refusal.py](../expense/tui/widgets/refusal.py)), then `Nothing was saved.` dim (not under a
`5xx`), then a blank line and the app's line when the reason has one (`app_lines`; "When the
engine says no" below). The amounts a `parts.<i>.amount_cents` key names turn the error colour
in the table. `SPLIT_TOTAL_MISMATCH` is keyed `parts`, whose words give both totals in cents,
and every `parts.<i>.amount_cents`, whose words say only that the parts must add up to the line's
total (contract: PUT /v1/bank-lines/{bank_line_id}, "The total"); it and every other refusal of
the route show this way. A failure that
is not the engine's answer (the engine out of reach) shows the app's error text there instead.
`esc` leaves with nothing sent, and the ledger keeps its rows and its cursor.
No suggestions and no same-merchant spreading — [decisions.md](decisions.md) "Home is the
month".

**The pending hashtag never rides beside a real one.** The engine files a transaction with no
hashtag under its built-in pending hashtag and refuses that hashtag together with another
(`PENDING_HASHTAG_NOT_ALONE`), while a set of real hashtags replaces it on its own
(contract: "Transactions (Ledger)", "Hashtags on a transaction").
So every hashtag write sends a set naming a real hashtag without the pending one: a part on
the Edit form, `h` on ledger rows and the LOG bar's `#tag` lines, the pending hashtag named
beside a real one included. An emptied set on a part of the Edit form sends `[]`, a part added
there with no real hashtag and a LOG bar line with no `#tag` send no hashtags; the engine files
them under the pending hashtag. **What the screens list is what the save sends:** on the Edit
form the pending hashtag leaves a part the moment a real hashtag is added, and a part's cell
never shows it; a
staged LOG bar row lists only the real hashtags when its line names the pending one beside
them, and a line with no `#tag` reads `#Pendiente` (the pending hashtag's name) in its tags
column, in the accent, as its category column reads `@Pendiente`; `↑` still lifts the line
exactly as typed. The rule is one helper, `hashtags_to_send` in
[reads.py](../expense/reads.py), for the sends and the lists alike; the pending hashtag is
`QuickAddRefs.pending_hashtag`, found by its `system_key` in the hashtags list the screens
already read, never by its name. With none yet nothing is dropped, and a LOG bar line with no
`#tag` reads `—`. Screens:
[expense-world-pending-hashtag-home.html](mockups/expense-world-pending-hashtag-home.html).
A hashtag refusal (`PENDING_HASHTAG_NOT_ALONE`, `RESERVED_NAME_HELD`, `CONCURRENT_CHANGE`,
`INVALID_REFERENCE`) shows the engine's words whole on all three, with a
line under it only for `CONCURRENT_CHANGE` ("When the engine says no" below).

Aggregates are **nullable** — a group holding an unconvertible row reports `3 unrated`
rather than a partial total. Opening balances are excluded engine-side. Home's grid
builder, `formatting.build_range_grid`, is covered by
[test_range_grid.py](../tests/unit/test_range_grid.py).

**`u` on the Reconciliations browse — the account's bank lines in no batch** (pane 2d of
[expense-world-bank-lines-whole.html](mockups/expense-world-bank-lines-whole.html)).
The **panel swaps**: same screen, same place, and the open account's reconciliations
are replaced by its bank lines assigned to no reconciliation, any day: `GET /bank-lines`
with `account_id` and `unreconciled=true` and no dates (contract: GET /v1/bank-lines), through
`fetch_bank_lines` in [reads.py](../expense/reads.py). `u` works only while an account's
panel is open — on the plain account list it does nothing and is not in the footer.
It is deliberately not a filtered ledger: reconciliation work stays in the reconciliation
view.

Every row is **one line of the bank's own columns**, `Date · Title · Operation · Amount`,
as on a reconciliation's batch screen (below): `bank_line_columns` in
[formatting.py](../expense/formatting.py) gives the day and title of the line's parts, its
`operation_code` (a dim `—` when it has none) and its signed `net_cents`, sign-coloured. A
transaction split into parts is **one row**, its title alone and its total; nothing on the row
says it is split, and its parts are not listed. No category, hashtags or note.

The list is **newest first**, the one order the engine's line list has (contract: GET /v1/bank-lines),
and the caption says so: `In no batch · <account>   ·   N of M loaded · newest first   ·
! blocks a batch's close`. It reads ten lines at a time and grows like the ledger (§5,
`GrowingRead`); M is `GET /bank-lines/count` with the same filters (`count_bank_lines`),
read together with the first rows, and counts a split transaction once
(contract: GET /v1/bank-lines/count); a count that cannot be read fails the pane. `r`, an
edit and a delete all start again from the newest ten, cursor on row 1. The **`!` flag is
a hint, not a ruling** — it marks a row whose date falls inside a batch window this screen
already holds, so it costs no request; the engine stays the authority at close time.

**Keys**: `esc` swaps back to the panel. `⏎ Edit`, on every row, opens the Edit form on the
line and its parts (below); the `?` card words it "Edit the transaction and its parts", as the
ledger's `s` (screen 2 A of
[expense-world-edit-form-words.html](mockups/expense-world-edit-form-words.html)). `d` deletes
the line under the cursor after a question (pane 3b, and "`d` is the TUI's one destructive key" below), with the line the list
already holds, so nothing is read before asking: a split transaction (`part_count` above 1)
asks the ledger's question for a split transaction and goes whole in one
`DELETE /bank-lines/{id}` (contract: DELETE /v1/bank-lines/{bank_line_id}),
a line never split asks the ledger's transaction question and goes as its one transaction
in `DELETE /transactions/{id}`.

**`⏎` in "no batch" — the Edit form on the line** (Question 1 A of
[expense-world-split-transaction-screen.html](mockups/expense-world-split-transaction-screen.html);
`BankLineEditFormScreen` in [edit_form.py](../expense/tui/screens/edit_form.py)). It is the
ledger's Edit form ("`⏎` and `s` open the Edit form" above) with OPERATION among the shared
fields, `date › title › operation › account`, then every part, and its crumb reads
`Capture & ledger ▸ Reconciliations ▸ Edit`. Over the bar, the line as the list shows it:
its title, then its signed `net_cents` and the account's currency
(`FARMACIA  ·  -100.00 PEN`). Every value comes from the line the list already holds, its
`edit_limits` included, so the form reads no line: the day and title off its first part, its
`operation_code` and its account. An operation with nothing typed reads `—  (optional)`; its
hint is `optional · the bank's operation number · empty clears it`, and an emptied operation
sends `operation_code: null`, which clears the line's operation code
(contract: PUT /v1/bank-lines/{bank_line_id}, "Body"). `ctrl+s` saves as the ledger's Edit
form does, in one `PUT /bank-lines/{id}`, and a refusal stays under its parts the same way.
Saved, "no batch" reads its newest ten again, cursor on row 1; a row whose date or account
moved it out of the list is gone. `esc` sends nothing and keeps the list and its cursor.

**The import door — a dropped bank file into the ledger**
([bank_import.py](../expense/tui/screens/bank_import.py), screens in
[expense-world-import-door.html](mockups/expense-world-import-door.html), the preview's table
of the file's rows and the screen after importing in
[expense-world-import-report.html](mockups/expense-world-import-report.html), and the days that
disagree and a row changed while the import ran in
[expense-world-bank-lines-upload.html](mockups/expense-world-bank-lines-upload.html)). `↵` on the LOG
bar's dropped files (§4 "A dropped bank file") reads every file at once, before any screen
opens, through `read_bank_file` in [flow.py](../expense/bank_import/flow.py)
(a BCP download: sheet `data`, columns Fecha, Descripcion, Moneda, Monto and an
optional Numero de Operacion). A file that is not a BCP export, or cannot be read, keeps the
bar where it is: the hint reads `not a BCP bank file · missing the columns Fecha, Monto`
with `it has: <its headers>` dim under it, the footer is `esc Cancel` alone, nothing is
sent, and the next keystroke clears it. With several files dropped, the hint names the
first bad one and none of them starts. Otherwise each file, in drop order, goes through
three full screens that replace one another above the LOG bar:

| Screen | Shows | Keys |
|---|---|---|
| **Which account is this file?** | the file's `14 movements · 2026-09-02 → 2026-09-15 · PEN` dim beside the question; every live, non-person account, a card's two currency legs folded into one line (`BCP Signature   PEN + USD`) — `account_groups` in [flow.py](../expense/bank_import/flow.py), archived accounts left out. Asked every time; nothing is remembered | `↑↓` move, `⏎ Pick`, `esc Cancel` |
| **Preview · <account> · nothing written yet** | the engine's dry run (contract: POST /v1/transactions/import) as one table of the file's lines, `#  date  title  amount  ✓  reason` (the mark's column has no heading), one row per line numbered by the file's own line, the lines under the floor and the ones the parser could not read included (a cell it could not read shows `—`); each row's mark and reason (below); `… N more · pgdn` when the rows outrun the screen; then the counts (below), and under them the days where the file and the ledger disagree (below) | `⏎ Import 9 rows` (with nothing new: below), `pgdn`/`pgup` (hinted in the body, not the footer), `esc Cancel` |
| **✓ 9 rows imported · <account>** | `new ones under @Pendiente and #Pendiente` dim on the same line, then the counts in the past tense (below): no table and no days | `⏎ Home` (`⏎ Next file` while a file follows), `esc Back` |

**Each row's mark and reason.** `✓` (success colour) means the row is in the ledger after the
import, `✗` (error colour, bold) that it is left out. The reason stands alone on the row, from
`row_reason` in [engine.py](../expense/bank_import/engine.py) and `file_lines` in
[flow.py](../expense/bank_import/flow.py):

| Mark | Reason | When |
|---|---|---|
| ✓ | `New` (success colour) | the engine's `new`: created on `⏎` |
| ✓ | `Already in the ledger` (dim) | `matched`, and the apply writes nothing onto its line |
| ✓ | `Modified existing transaction` | `matched`, and the apply writes the file's operation number onto the line (`backfill_code`), the bank's title (`retitled`), or moves the line to the bank's day (`redated`) |
| ✗ | `Not moved: <reconciliation> is reconciled` | `matched`, and a completed reconciliation stops the move to the bank's day (`redate_blocked_by`), whatever else the apply writes |
| ✗ | `Closed period` | the engine's `sealed`: inside a closed period, never created |
| ✗ | `Before 2026` | dated before 2026-01-01: never sent |
| ✗ | `Couldn't read the row` | a line the parser refused, an amount cell that is not an amount among them ("One reader for every typed amount"): never sent, and the rest of the file is read |

Every `✗` reason is in the warning style (`PALETTE.warning`). The answer carries the stopping
reconciliation's id only, so the preview's worker reads each distinct one once by its id
(`reconciliation_names` in [flow.py](../expense/bank_import/flow.py)), never the account's list
and never while drawing
(contract: GET /v1/reconciliations/{reconciliation_id}).
When a read fails, its rows read `Not moved: a reconciliation is reconciled`, the other ids are
still read, and a dim `! could not read the reconciliations' names: <why>` sits under the
counts with the first failure's reason.

**The counts** under the table: `14 rows · 5 new · 6 in the ledger · 1 moves to the bank's day ·
1 takes the bank's title`, the moved and title counts only when not zero; then, on a line of
its own under the first count, `1 closed · 1 before 2026 · 1 unreadable`, each only when not
zero, the line only when one is. After importing they read in the past tense: `1 moved to the
bank's day`, `1 took the bank's title`.

Every count on the preview and the result, and the count in `⏎ Import N rows`, is the
engine's `counts` (`new`, `matched`, `sealed`, `retitled`, `redated`); the app counts only the
file's own lines (the total, the pre-2026 and the unreadable ones), never the answer's rows.

**The days where the file and the ledger disagree** are the engine's `day_mismatches`: a day is
reported when its file total and its ledger total after the import differ, or when it holds a
ledger line no file row claimed, so a day with equal totals can be one
(contract: POST /v1/transactions/import). Each names the file rows it found in no ledger line
(`unmatched_rows`, by the index each row was sent under) and the ledger lines no file row
claimed (`unclaimed_lines`: a `bank_line_id`, a signed `net_cents` and its `parts`, the whole
transaction responses, a split transaction being one entry with every part). The preview takes
them as they come, in `day_mismatches` in [engine.py](../expense/bank_import/engine.py), and
read no transaction to fill them. Each part is its own row, the transaction's title and the
part's own amount: the parts arrive with `amount_cents` positive and the direction in
`transaction_type`, and `signed_cents` in [formatting.py](../expense/formatting.py) signs them;
nothing adds parts up, and every total is the engine's.

They show **on the preview only**, under the counts: `! 3 days where the file and the ledger
disagree`, then each day as `2026-09-12   file -42.90 · ledger after import -84.90`, and under
it its rows: a file row as `row 4   FARMACIA CENTRAL  -42.90   in the file, not found`, a
ledger part as `Farmacia  -42.00   in the ledger, not in the file`. It is a report only: nothing on
it changes what `⏎` writes. On a card file, whose two currencies are two accounts, each day
names its account: `2026-09-12 · BCP Signature USD`. A line the import moves to the bank's day
counts on that day, so the move leaves no day disagreeing
(contract: POST /v1/transactions/import). The screen after importing shows no days.

The upload does nothing to a ledger row no file row claimed: it removes nothing and asks
nothing. Such a row stays out of that month's reconciliation, where it is deleted.

A preview with nothing new keeps the table and the counts and adds dim `nothing to import`.
On the last (or only) file `⏎` does nothing and the footer is `esc Back`. With a file still
to come the footer is `esc Cancel both` / `esc Cancel all` (below) and `⏎ Next file`, and
`⏎` opens the next file's account list, writing nothing. `⏎` on a preview with new rows
sends the same rows, under the same ids, as the apply — one `POST /transactions/import`
with `dry_run: false` through the shared HTTP client (its idempotency key covers a retry). A refusal or a short answer
stays on the preview, the rows it names by file line, and nothing else is sent.

**A ledger line changed while the import ran** (screen 4 A in
[expense-world-bank-lines-upload.html](mockups/expense-world-bank-lines-upload.html)): the apply's `409 CONFLICT`
with `CONCURRENT_CHANGE` on a `rows.<index>` key means something else split, deleted or
changed a ledger line a file row matched, and nothing was written
(contract: POST /v1/transactions/import). The preview shows the engine's words, each row by
the file's line (`! row 6: …`), `Nothing was written.` dim, and under a blank line
`It changed while the import ran: ⏎ checks the file against the ledger again.`; the footer
is `⏎ Preview again`. `⏎` runs the dry run again on the ledger as it is now, and the footer
returns to `⏎ Import N rows`: nothing is sent again without a fresh preview. A file the
picked account cannot hold (a currency with no leg, more than 500 rows, nothing on or after
2026-01-01) is refused on the account list in flow.py's words.

**Several files** carry `Import ▸ file 1 of 2` in the crumb and the file's name under the
question. `esc` before a file is written cancels it and every file after it, and its word
counts the files still to come, this one included: `esc Cancel all` (three or more),
`esc Cancel both` (two), `esc Cancel` (this one alone — `esc Back` on a nothing-new preview).
File 1 of 2 says `Cancel both`, file 2 of 2 `Cancel`, file 2 of 3 `Cancel both`. A file
already imported stays imported. **`esc`** on any import screen lands on the LOG bar with
the bar cleared and the staged rows as they were; a row lifted for editing goes back
unchanged when the drop is imported.
`⏎ Home` leaves the bar for Home, through the bar's discard question when rows are staged
and unwritten, and Home reads afresh: this month's window, every category folded, the
cursor on the first category (`HomeScreen.start_fresh`).

**Accounts stand in the engine's order everywhere.** Manage ▸ Accounts, the LOG bar's `$`
picker, the Edit form's account field, the ledger's `b` pick, the Reconciliations
browse, the new-reconciliation form and the bank import's "Which account is this file?"
show accounts as `GET /accounts` lists them, every real account first, then every person
(contract: GET /v1/accounts). No screen sorts them. A screen that has no use for people
leaves them out and moves nothing else, and the bank import's card line stands where its
first currency leg does. The LOG bar's `$` picker, the Edit form's account field and the
ledger's `b` pick offer no archived account (`QuickAddRefs.accounts` in
[reads.py](../expense/reads.py)): the engine refuses an archived account as a transaction's
`account_id` (contract: POST /v1/accounts/{account_id}/archive). A row already on one still
shows its name, read-only on its Edit form (below).

**On an archived account's row the ledger offers no `d`** (the row and `d` as screen 1 A of
[expense-world-archived-account.html](mockups/expense-world-archived-account.html) draws them;
that screen also draws `s` gone, though the app keeps it, below). The engine deletes none of
an archived account's transactions (contract: POST /v1/accounts/{account_id}/archive), so with
the cursor on one, whole ledger or filtered from Home, `d Delete` leaves the footer and the key
does nothing and sends nothing; on the next row of an active account or a person it is back,
the footer following the cursor. `s` stays on the row and opens the same Edit form `⏎` does, where
only what the line's `edit_limits` leaves open changes ("On an archived account's line the Edit
form changes the categorisation alone" below). The row is drawn as any other, with nothing on
it saying why, and `s`, `c`, `b`, `h`, `⏎` and every other key stay; the engine still judges
each write they send. The ledger learns which accounts are archived from the same
`GET /accounts` that gives it the names, one read per load (`reads.load_account_index`), so an
account unarchived on Manage ▸ Accounts gets its `d` back at the ledger's next read (`r`, or
any reload). The `?` card still lists `d`, as it does while rows are selected: it lists a
screen's own keys as the screen declares them.

**On an archived account's line the Edit form changes the categorisation alone**
(screen 2 B of [expense-world-archived-account.html](mockups/expense-world-archived-account.html),
pick 5 A of [expense-world-split-transaction-screen.html](mockups/expense-world-split-transaction-screen.html)).
Such a line keeps its parts and their amounts, and every line field sent is refused but a title
or operation code filled while it is empty
(contract: PUT /v1/bank-lines/{bank_line_id}, "A line with a part on an archived account keeps its parts and their amounts")
(contract: PUT /v1/bank-lines/{bank_line_id}, "Rules"). The form reads it from the line's
`edit_limits`, as every read-only line ("What is read-only is the line's `edit_limits`"
above): the line fields it names read `read-only`, and one line under them names them with the
engine's sentence, for example `date, title, account: The account is archived. Unarchive it first.`
(`date, account: …` when the engine leaves an empty title open); each part's amount is dimmed
under a dim `amount  read-only` with the same sentence beside it, there is no `^n` or `^x`,
and the form opens on the first line that can change, a title still empty if the engine leaves
it open, else part 1's CATEGORY. Each part's category, hashtags and note change as on any
line, and the save sends each part at its current amount. The "no batch" Edit form follows the same `edit_limits` on a
line of an archived account, which only a list read before the account was archived still
shows. When the engine refuses anyway (the account archived after the line was read), its
words stay under the parts ("When the engine says no" below).

**Manage ▸ Categories and Manage ▸ Hashtags mark the built-in rows** (screens 1 and 2 A in
[expense-world-pending-hashtag-manage.html](mockups/expense-world-pending-hashtag-manage.html)).
Categories is a table of Color, Name and System; Hashtags one of Name and System, the same
without the colour, in the order `GET /hashtags` lists them, or `(no hashtags)` when there
are none. System reads `system 🔒` on a built-in row and `—` on the rest. The built-in rows
are `@Pendiente` and `@Opening` among the categories and the pending hashtag among the
hashtags: the rows with a `system_key`, never found by name (`reads.is_system_row`). They
keep their names and are never deleted
(contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
(contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name"), so with the
cursor on one the footer offers neither `e Edit` nor `d Delete` and both keys do nothing
(`ResourceListScreen.is_fixed` in [_base.py](../expense/tui/screens/_base.py)); on every
other row they end the footer as usual. A built-in category's colour is not changed
from this app either. Under the list a legend says so: `System categories cannot be renamed
or deleted.` on Categories, `System hashtags cannot be renamed or deleted.` on Hashtags.

**Manage ▸ Accounts is a table of Name, Type, Cur, Code, Color, Balance and Status** (screen
4 B in [expense-world-statement-code-field.html](mockups/expense-world-statement-code-field.html)
for Code), banks and people together, archived rows dimmed, under the legend `balances are
native currency`. Code is the account's statement code, or a dim `—` when it has none (a
person never has one); it is where both accounts of one card show the same code. Balance is the
one right-aligned column (`account_rows` in
[accounts.py](../expense/tui/screens/accounts.py)).

**`t` turns an account into a person and back** (screens 1 A, 2 A, 3, 4 B and 5 B in
[expense-world-account-to-person.html](mockups/expense-world-account-to-person.html)). On
Manage ▸ Accounts the footer reads `t Make person` on a bank account's row and
`t Make bank` on a person's, following the cursor, between `a Archive` and `d Delete`.
`t` sends `POST /accounts/{id}/make-person` or `POST /accounts/{id}/make-account` at once,
with no body and no question, through `run_write` as `a` does
(contract: POST /v1/accounts/{account_id}/make-person)
(contract: POST /v1/accounts/{account_id}/make-account). The list reads again with the
cursor on the account in its new place, among the people or the bank accounts, and the
note says `Now a person.` or `Now a bank account.`, so a second `t` turns it back. While
one is in flight, `t` and `a` do nothing. On an archived row `t` leaves the footer and does
nothing, a person's too; on an empty list it is off, as `a` is. A refusal leaves the list
as it was and `t` works again; the "Failed" note is the engine's words whole, and
`HAS_OPENING_BALANCE` adds `Press e and empty its opening balance first.` (the table in
"When the engine says no"). A person never has reconciliations, so `t Make person` on an
account with one, draft or completed, is refused with `HAS_RECONCILIATION` until each is
deleted (contract: POST /v1/accounts/{account_id}/make-person, "Refusals"), and the note adds
`On Reconciliations, press d on each of its reconciliations; a completed one needs u first.`
(screen 1 A in
[expense-world-person-reconciliations.html](mockups/expense-world-person-reconciliations.html)).
Home shows the account under its new group, BANK ACCOUNTS or
PEOPLE, at its next read of `/dashboard`. The Edit form's `type` line stays read-only:
`t` is how an account's type changes.

**`d` is the TUI's one destructive key** (screens in
[expense-world-delete.html](mockups/expense-world-delete.html)). It deletes the row under
the cursor on Manage ▸ Accounts, Categories and Hashtags (a built-in row aside, above), on
the ledger (whole or filtered from Home) and in the reconciliation's "no batch" list, always
as the last entry of the screen's footer keys. Cursor row only, never a selection: on the ledger `d` is off, and out
of the footer, while rows are selected (`esc` clears the selection and it is back),
while a bulk write runs and on an archived account's row (above). On an
empty list it does nothing. On Accounts `a Archive` stays as it is: archive puts an account
away and can be undone, delete is for something made by mistake.

Every delete asks first with `ConfirmModal` (only `y` deletes; `⏎`, `n` and `esc` cancel
and send nothing). The question names the row, then says the part that matters: **no
screen can bring it back.**

| Screen | Question | Body | Note after |
|---|---|---|---|
| Accounts | `Delete this account?` | `Prueba · bank · PEN · 0.00` · `It is for an account made by mistake: no screen can bring it back.` | `Account deleted.` |
| Categories | `Delete this category?` | `PRUEBA` · `It is for a category made by mistake: no screen can bring it back.` | `Category deleted.` |
| Hashtags | `Delete this hashtag?` | `#viaje-cusco` · `It is also taken off every transaction that carries it; one with no other hashtag goes to #Pendiente. No screen can bring it back.` | `Hashtag deleted.` |
| Ledger, and a line never split in the "no batch" list | `Delete this transaction?` | `Cine Plaza · -28.00 · 2026-10-10 · Sueldo Soles` · `It leaves every balance and report, and no screen can bring it back.` | `Transaction deleted.` |
| Ledger, on a part of a split transaction; a split transaction in the "no batch" list | `Delete this transaction and its 2 parts?` (the line's real part count) | `FARMACIA · -100.00 · 2026-10-11 · Sueldo Soles` · `No screen can bring it back.` | `Transaction deleted.` |
| A reconciliation's batch screen (`d` deletes the batch itself) | `Delete reconciliation?` | `Detaches its transactions and removes the batch. Its transactions stay. No screen can bring it back.` | `Reconciliation deleted.` |

`y` sends `DELETE /{resource}/{id}` through `run_write` (the shared client's idempotency
key, `EngineWriteMixin.confirm_delete` in [_base.py](../expense/tui/screens/_base.py)).
Deleted, the list reads again from the start, cursor on row 1: a Manage list's first
page, the ledger's newest ten, the "no batch" list's newest ten. The hashtag question names the
cascade because the engine never refuses that delete for being in use; it takes the tag
off every transaction carrying it, and one left with no hashtag carries the pending hashtag
(contract: DELETE /v1/hashtags/{hashtag_id}). The question names the pending hashtag as the
list gives it (`#Pendiente`), or says `the pending hashtag` while the user has none yet;
screen 3 B in
[expense-world-pending-hashtag-manage.html](mockups/expense-world-pending-hashtag-manage.html).

**On the ledger, a split transaction goes whole** (screens 3a, 3c, 3d and 3e in
[expense-world-bank-lines-whole.html](mockups/expense-world-bank-lines-whole.html)). Every
ledger row names its bank line (contract: "Transactions (Ledger)", "Bank lines"), but not how
many parts the line holds, so `d` on a row first reads its line once with the shared
`reads.fetch_bank_line` (contract: GET /v1/bank-lines/{bank_line_id}). With `part_count`
above 1 the row is a part of a split transaction: the question names the real part count, its
body is the bank line (its date, title and signed total `net_cents` exactly as the
reconciliation lists show them, through the shared `formatting.bank_line_columns`, then its
account), and `y` sends one `DELETE /bank-lines/{id}`, which deletes every
part in one write (contract: DELETE /v1/bank-lines/{bank_line_id}), through the same
`confirm_delete`; the note reads `Transaction deleted.` and the ledger reads its newest ten
again, cursor on row 1, every part gone. A line of one part is a row never split: the
ledger's own question and `DELETE /transactions/{id}`, as above. A line in a completed
reconciliation is refused, `IN_COMPLETED_RECONCILIATION` on `bank_line_id`, and nothing is
deleted; the "Failed" note is the engine's words whole, as for a single row (the table in
"When the engine says no"). A line that cannot be read asks nothing and sends nothing: the
"Failed" note carries the engine's words, and `d` again reads again. While the read runs,
`d` again does nothing; a read that lands once the ledger is gone or covered by another
screen asks nothing.

**A refused delete** leaves the row and the list as they were and shows the "Failed" note:
the engine's own words, then the line saying what to do instead ("When the engine says no"
below).

**When the engine says no.** Every refusal with code `CONFLICT`, `FORBIDDEN` or
`LIMIT_REACHED` names the rule that fired in `reasons`, keyed by the thing refused
(contract: "Base Conventions", "`fields` and `reasons` semantics"); so do the
`VALIDATION_ERROR` an opening balance draws when asked to move or given a hashtag, the one a
reconciliation draws when completed without its ending balance, the one a new
reconciliation draws on a person account, the one a system category
or the pending hashtag draws when sent a new name, and the one a hashtag draws when named
like the pending hashtag. The note it draws (a
toast, a LOG bar row, the bank import's preview, the Edit form's parts) shows the engine's words whole (`CODE —
message`, then one `key: …` line per refused field; a LOG bar row the engine names reads
`key: …` for each refused field, without the code and message, and so does a ledger row
refused by `b`, `c` or `h`, "Saved" below), and for the
reasons below a blank line and one line of the app's saying what to do. Screens in
[expense-world-refusal-hints.html](mockups/expense-world-refusal-hints.html).

| Reason (contract: "Error reasons") | Where you meet it | The line under it |
|---|---|---|
| `HAS_TRANSACTIONS` on `account_id` | `d` on Manage ▸ Accounts | `To retire it instead, archive it: press a.` |
| `HAS_TRANSACTIONS` on `category_id` | `d` on Manage ▸ Categories | `Move its transactions to another category first.` |
| `SYSTEM_CATEGORY` | `d` on a category, should the engine find it a system one (Manage offers no `d` on `@Pendiente` or `@Opening`) | `System categories cannot be renamed or deleted.` |
| `SYSTEM_HASHTAG` | `d` on a hashtag, should the engine find it the pending one (Manage offers no `d` on it) | `The pending hashtag cannot be renamed or deleted.` |
| `HAS_OPENING_BALANCE` on `account_id` | `t Make person` on Manage ▸ Accounts, on an account with an opening balance | `Press e and empty its opening balance first.` |
| `HAS_RECONCILIATION` on `account_id` | `t Make person` on Manage ▸ Accounts, on an account with a reconciliation, draft or completed | `On Reconciliations, press d on each of its reconciliations; a completed one needs u first.` |
| `PERSON_ACCOUNT` (a `VALIDATION_ERROR`) on `account_id` | a new reconciliation started from a screen read before its account became a person (contract: POST /v1/reconciliations, "A person account never has reconciliations") | none: the engine's words already say a person cannot have reconciliations, and the form stays open with what was typed |
| `KIND_UNCHANGED` on `account_id` | `t` on Manage ▸ Accounts, on a list read before the account was turned elsewhere | none: the engine's words already say the account is of that kind |
| `HAS_STATEMENT_CODE` on `account_id` | `t Make person` on Manage ▸ Accounts, on an account with a statement code (contract: POST /v1/accounts/{account_id}/make-person, "Refusals") | none: the engine's message already names the code and says to clear it first |
| `IN_COMPLETED_RECONCILIATION` on `transaction_id` or `bank_line_id` | `d` on the ledger | none: the engine's message already says to revert the reconciliation to draft first |
| `ACCOUNT_ARCHIVED` (a `CONFLICT` on a delete, complete, revert or `t`; a `VALIDATION_ERROR` on a save) | a write sent from a screen read before its account was archived: `t` on Manage ▸ Accounts, `d` on the ledger or in "no batch", `b` on ledger rows, a save on the Edit form or the "no batch" Edit form, and `space`, `c` (its ending balance's save too), `u` and `d` on a reconciliation's batch screen | none: the engine's words already say to unarchive the account first, and the screen stays as after any refusal |
| `NAME_EXISTS` | a new account, person, category or hashtag; a rename on an Edit form | `That name is taken: pick another.` |
| `STATEMENT_CODE_EXISTS` on `statement_code` | a new bank account, or a bank account's Edit form, given a code another account in its currency has (contract: "Bank Accounts", "Statement code") | `Another account in this currency has this code: pick another, or clear it there first.` |
| `STATEMENT_MONTH_TAKEN`, `COMPLETED_STATEMENT_JOINED` (a `VALIDATION_ERROR`) on `statement_code` | a code set or changed on a bank account's Edit form that would clash with a reconciliation under it (contract: "Bank Accounts", "Statement code") | none: the engine's words name the reconciliations and say what to do |
| `CAP_REACHED` | a new account, person, category or hashtag | `Delete one first.` |
| `OPERATION_CODE_EXISTS` | a transaction's account changed on its Edit form; an operation number or account changed on the "no batch" Edit form; `b` on ledger rows; a bank file | `That account already has a row with this operation number: look there for a duplicate.` |
| `CONCURRENT_CHANGE`, on a list | `d` on an account, a category, a hashtag or a reconciliation; saving the ending balance at `c` on a reconciliation's batch screen | `It changed at the same moment: press r, then try again.` |
| `CONCURRENT_CHANGE`, elsewhere | saving an opening balance, the LOG bar, the Edit form, or `h` on ledger rows | `It changed at the same moment: save again.` |
| `CONCURRENT_CHANGE` on `rows.<index>` | a bank file's apply, when a ledger line a file row matched changed while it ran (§2 "The import door") | `It changed while the import ran: ⏎ checks the file against the ledger again.` |
| `RESERVED_NAME_HELD` | saving an opening balance, the LOG bar, the Edit form, a bank file | `One of your categories has a built-in category's name: rename it on Manage ▸ Categories, then save again.` |
| `RESERVED_NAME_HELD` on `hashtag_ids` or `hashtag_id` | a transaction's hashtags on its Edit form, `h` on ledger rows, the LOG bar; `d` on Manage ▸ Hashtags | none: one of your hashtags holds the pending hashtag's name, and the engine's message names the remedy |
| `OPENING_BALANCE_EXISTS` | saving an opening balance on the account's Edit form | `It got one meanwhile: close the form and open it again to change it.` |
| `RECONCILIATION_NOT_DRAFT` | `d` on a reconciliation's batch screen | `Press u to revert it, then d again.` |
| `OPENING_BALANCE_ACCOUNT_FIXED` (a `VALIDATION_ERROR`) | `b` on ledger rows that include an opening balance; its Edit form, should the refusal reach it | `To move an opening balance, set it on the other account's Edit form.` |
| `OPENING_BALANCE_CATEGORY_FIXED` (a `VALIDATION_ERROR`) | `c` on ledger rows that include an opening balance; its Edit form, should the refusal reach it | `An opening balance always stays in @Opening.` |
| `ENDING_BALANCE_REQUIRED` (a `VALIDATION_ERROR`) | `c` on a reconciliation's batch screen, when its ending balance was cleared elsewhere | `Press c again: the app asks for it first.` |
| `SYSTEM_NAME_FIXED` (a `VALIDATION_ERROR`) on `name` | a new name, letter case alone included, for `@Pendiente`, `@Opening` or the pending hashtag on an Edit form, should one open on it (Manage offers no `e` on them) | `Built-in names never change: press esc to leave it as it is.` |
| `RESERVED_NAME` (a `VALIDATION_ERROR`) on `name` | a new category, or a category renamed on its Edit form, named like a system category (`@Opening`, `@Pendiente`); a new hashtag, or a hashtag renamed on its Edit form, named `Pendiente` in any letter case | `That name belongs to a system row: pick another.` |
| `OPENING_BALANCE_NOT_TAGGED` (a `VALIDATION_ERROR`) on `hashtag_ids` | `h` on ledger rows that include an opening balance | `Leave the opening balance out of the selection.` |
| `OPENING_BALANCE_NOT_TAGGED` (a `VALIDATION_ERROR`) on `parts.<index>.hashtag_ids` | an opening balance's Edit form, should the refusal reach it (its hashtags show read-only) | none: the engine's words alone |
| `ID_EXISTS`, `IDEMPOTENCY_KEY_REUSED` | any save, rarely: both mean the app sent something wrong | `Not your mistake: the app sent it wrong and nothing was saved. Try again; if it happens again, report it.` |

The line is chosen by the error's `code` and reason alone, never by the HTTP status, the
route or the engine's wording ([decisions.md](decisions.md) "Hints are chosen by the
engine's reasons, never its wording"). The choice lives in one table, `NEXT_STEPS` in
[errors.py](../expense/errors.py), read by the shared error text `format_error`, so every
screen that reports a failure through it shows the line. One row is the import door's own:
`CONCURRENT_CHANGE` on a `rows.<index>` key is picked by `changed_while_running` in
[bank_import.py](../expense/tui/screens/bank_import.py), which shows its line in place of
`format_error`'s, since what follows is `⏎ Preview again`. A write sent from a list (every
`d`, `t` on Manage ▸ Accounts, and the ending balance saved at `c` on a reconciliation's
batch screen, where `r` reads it again) asks for the list's line (`list_refusal_text` in
[_base.py](../expense/tui/screens/_base.py)). `HAS_TRANSACTIONS` is the one reason two
resources share; its key (`account_id` or `category_id`) picks the line, the keys
`hashtag_ids` and `hashtag_id` keep the category line off `RESERVED_NAME_HELD`, and
`OPENING_BALANCE_NOT_TAGGED` has its line on a transaction write's `hashtag_ids` alone, so
the Edit form, whose whole-line write names the part's `parts.<index>.hashtag_ids`, shows the
engine's words alone (the last screen of
[expense-world-edit-form-words.html](mockups/expense-world-edit-form-words.html)). The three
opening-balance reasons, `ENDING_BALANCE_REQUIRED`, `SYSTEM_NAME_FIXED` and `RESERVED_NAME`
are the table's only `VALIDATION_ERROR` rows with a line; any other validation error,
`ACCOUNT_ARCHIVED` and `LOCKED` included (the field lock answers first in a completed reconciliation), has no line. The lines for
`SYSTEM_HASHTAG`, `SYSTEM_NAME_FIXED` and `OPENING_BALANCE_NOT_TAGGED` are screens 4 B, 5 B
and 7 B in
[expense-world-pending-hashtag-manage.html](mockups/expense-world-pending-hashtag-manage.html);
`RESERVED_NAME` has one line for a category and a hashtag alike, since both meet it on
`name` and the line follows the reason alone.
`SECRET_NOT_REPLAYABLE` has no line: only creating a sign-in key draws it, and the app never
creates one.

**The engine's words show as text, never as styling.** Every note shows them as sent,
`[` and all: a `[like this]` or a lone `[` in a refusal, a warning or a name is never read
as markup and never vanishes. Lines drawn on a screen (under the parts, the import's
preview, the LOG bar's rows, a question, the "Could not load." banner, a status line) are
Rich `Text`. A toast whose message is not a fixed sentence of the app's goes through
`toast` in [refusal.py](../expense/tui/widgets/refusal.py), which shows it as text; the
title is always text. The one toast that styles the engine's words on purpose, the
ledger's bulk edit note, writes them into its content markup through `as_markup` there,
which escapes every `[`. [test_toast_words.py](../tests/unit/test_toast_words.py) fails
on any other `notify` whose message is not a fixed sentence, and
[test_tui_engine_words.py](../tests/unit/test_tui_engine_words.py) drives each place with
a refusal holding brackets.

**"Saved" means the engine holds the row.** The LOG bar ticks a row only when the engine
created it, or refused it only because the row's own id is taken (`ID_EXISTS` on its
`transactions.<i>.id` and nothing else): a replay of a save whose answer was lost. Every
other refusal (`CONCURRENT_CHANGE`, `RESERVED_NAME_HELD`, …) is shown on each row it
covers, which keeps no `✓` (`errors.is_own_id_replay`; [runtime.md](runtime.md) "Bulk writes").

**Refused rows read one line per kind of error** under the table (`save_errors`; screens 2 A
and 3 A in [expense-world-grouped-refusals.html](mockups/expense-world-grouped-refusals.html)):
what was refused in the error colour, then the rows it hit, unstyled — `row 2`, or
`rows 4, 6` for several — and, last and dim, `ctrl+s retries just the rows without a ✓.`

```
  amount_cents: Must not be zero. row 2
  date: The date falls inside a completed reconciliation's period. rows 4, 6
  ctrl+s retries just the rows without a ✓.
```

- **A row the engine names** reads in the engine's words for it, and rows refused alike
  share one line, on two sends of one save too
  ([runtime.md](runtime.md) "How refused rows read"). The app's line saying what to do, when
  the refusal has one ("When the engine says no" above), follows dim on the next line.
- **A refusal naming no row** (a `409` keyed `category_id`, a `5xx`) is a line of its own,
  as every surface shows one (same paragraph), with the app's line under it, dim.
- **A save the connection stopped** puts its words on every row it left unsent: one line,
  those rows after it. A save a refusal of every further write stopped is said once, in a
  toast, on no row ([runtime.md](runtime.md) "Bulk writes").

**The ledger's bulk edit reads its refused rows the same way** (`b`, `c`, `h`; Question 5 A of
[expense-world-wording-picks.html](mockups/expense-world-wording-picks.html)), through the same
grouping (`refusal_notes` in [transactions.py](../expense/tui/screens/transactions.py)): one
toast per kind of refusal, titled `Refused`, or `2 of 3 refused` when more than one row was
refused, holding what was refused in the error colour, the rows under it, unstyled, as the list
numbered them before the write, and the app's line saying what to do, dim. Every row it
hit is named. A refusal with no field words (a `401`, `404` or `5xx`, or a `409`/`422`
naming no key; `errors.is_keyed_refusal`) reads whole, as a refusal naming no row: the
engine's code and message first, the rows it met under them, its field lines and the app's
line after. A lost connection reads in the shared text, the rows it met under it.

```
2 of 3 refused
account_id: Locked by completed reconciliation.
rows 1, 3
```

A refusal of every further write (`SETTINGS_MISSING`) is no row's and is not counted among
them: it shows after them, once, in the note the LOG bar shows when the same refusal stops its
save (screen 2 A of
[expense-world-read-only-reasons.html](mockups/expense-world-read-only-reasons.html)), one
copy for both (`run_stopped` in [refusal.py](../expense/tui/widgets/refusal.py)): titled
`Failed`, the engine's words whole, then, after a blank line, the line saying what to do. A
row refused for its own reason before the stop keeps its own note.

```
Failed
SETTINGS_MISSING — User settings have not been provisioned.
  user_settings: Must be provisioned via POST /v1/auth/bootstrap.

Hint: First-time setup is not done yet. Open System ▸ Auth & profile and press b.
```

**A bank account's statement code is a line of its own on New and Edit** (screens 1 A, 1b A,
2 A, 3·1 B, 3·2 B, 3·3 and 3·4 in
[expense-world-statement-code-field.html](mockups/expense-world-statement-code-field.html)).
**`statement code`** sits right after `currency`, on a bank account only: only a real
account carries a code, and `POST /people` takes none (contract: "Bank Accounts", "Statement code").
On New, TYPE turned to `person` takes the line off the form and the save sends no code;
turned back to `bank`, the line returns holding what was typed. A person's Edit form has no
such line.

- **The hint** reads `optional · three capital letters, e.g. SIG · enter to go on` on New,
  and `optional · three capital letters, e.g. SIG · empty clears it · enter to go on` on
  Edit; `⏎` goes on to `color`.
- **Small letters show as capitals while typing,** typed or pasted (`FormScreen._typed`,
  which `FormBar` applies to every edit of the bar); no other line of any form changes what
  is typed. The app checks nothing else about the code: the engine judges its shape, and a
  digit, a missing letter or a fourth one comes back refused in its words.
- **On New,** a code typed is sent as `statement_code` on `POST /accounts`; skipped, the key
  is left out of the body, never sent as `null` (contract: POST /v1/accounts).
- **On Edit,** the line opens holding the account's code. The save sends `statement_code`
  only when it differs from the account's own, and `null` when the line was emptied, which
  clears the code with no question: nothing is lost, since typing the code again brings
  every statement line back (contract: PUT /v1/accounts/{account_id}).
- **A refusal** shows the "Failed" note in the engine's words, the cursor back on the code
  line with what was typed on the Edit form; `STATEMENT_CODE_EXISTS` adds the app's line
  `Another account in this currency has this code: pick another, or clear it there first.`,
  and every other refusal of a code reads in the engine's words alone (the table in "When
  the engine says no").

**An account's opening balance lives on its Edit form** (`e` on Manage ▸ Accounts; screens
in [expense-world-opening-balance.html](mockups/expense-world-opening-balance.html)). A bank
account's form ends with two optional lines after `color`: **`opening`**, the amount, and
**`as of`**, its day. There is no title line; the engine names the row. A person's form has
neither line: what you owe each other comes only from the rows you record.

- **The amount is signed and taken as typed**, in the account's currency. The hint reads
  `signed · 350.00 is money you have · -350.00 is money you owe · in PEN · optional`; the
  app never adds or flips a sign. `as of` takes `YYYY-MM-DD` (hint `YYYY-MM-DD · the day the
  account held this`), starts empty, and is marked `*` once there is an amount.
- **An account that has one opens with both lines filled.** The account names its opening
  balance by id, or `null` when it has none (contract: "Bank Accounts", "Opening balance"),
  and the form reads that one row with `GET /transactions/{id}?debit_as_negative=true`
  (`reads.fetch_transaction`), so the amount arrives signed and nothing reads the sign off
  `transaction_type` (contract: "Base Conventions", "Sign convention — responses"). A save
  waits for that read; a read that fails shows its "Failed" note and leaves the two lines
  read-only, so the account itself still saves.
- **A save can send two writes, in order:** the account's own changes (`PUT
  /accounts/{id}`), then the opening balance — `POST /accounts/{id}/opening-balance` with a
  client `transaction_id`, the signed `amount_cents` and the `date` when there is none; a
  `PUT /transactions/{id}` of only the changed amount or date when there is one. The account
  write goes when the account changed, or when the opening balance has nothing to send.
- **Emptying the amount of an existing one and saving deletes it**, after `ConfirmModal`
  asks `Delete this opening balance?` over the form (`Sueldo Soles · 3,200.00 · 2026-01-01` ·
  `It leaves the account's balance, and no screen can bring it back.`). Only `y` sends the
  account's changes and `DELETE /transactions/{id}`; `⏎`, `n` and `esc` go back to the form
  with nothing saved.
- **A refusal** shows the "Failed" note in the engine's words, with the line saying what to
  do when it has one (`format_error`), and leaves the
  form open with what was typed, the cursor on the line the refusal names (an amount on
  `opening`, a date on `as of`, a name, statement code or colour on its own line); a refusal that names
  none of them leaves the cursor where it was. When the account saved and the opening balance was refused,
  the note says so: `The account's changes are saved. The opening balance is not:`, the
  engine's words, then `It is still in the form: fix it and save again.`, or, for a
  refusal with a line of its own ("When the engine says no" above), that line instead.
  The next save sends only the opening balance; `esc` just leaves.
- **Saved,** the form closes with `Saved.` and the account list reads again from its first
  page, cursor on row 1. Every Manage Edit form (accounts, categories, hashtags) closes
  this way: one that wrote dismisses with `True` and the list starts over; one closed with
  `esc` before any write keeps the edited row selected (`ResourceListScreen._edited` in
  [_base.py](../expense/tui/screens/_base.py)).

**Every new screen starts with an HTML mockup in [mockups/](mockups/) for review before
code** — every time, including screens approved before (CLAUDE.md "Mock every screen").

**No cards. No vertical lines. Horizontal rules divide sections.** *(Owner rule.)*

- **Nothing is drawn inside a box** — not a modal, not a list panel, not the input bar,
  not a plain yes/no `ConfirmModal`.
- **Horizontal rules are the divider** (the header's `border-bottom` is the pattern).
- **A question that needs room becomes a screen**, not a card.

The reason is terminal width: a vertical edge costs border and padding on both sides,
exactly the width an explaining column needs, and a card hides the screen that supplies
the question's context.

**List chrome is content.** A list's page status (`rows 21-40 of 133 · page 2 of 7`) is
drawn as ordinary content by `WindowedList.framed()`
([windowed.py](../expense/tui/widgets/windowed.py)) — the one method every repaint of both
list widgets passes through: a plain rule opens the section, the page status sits dim
beneath the rows, and there is no title, the breadcrumb already naming the screen.
Two details are load-bearing. **The status line is always drawn, blank when there is
nothing to say** — a line that came and went would make the widget's height depend on
its row count, which is what `AdaptiveRowsMixin` measures. And **the rule passes an
explicit style**: Rich's default `rule.line` resolves to a literal green that
`test_no_literal_color_styles_in_tui` cannot see, because it greps source rather than
renders.

⚠️ **One exception.** A title that is *chrome* disappears; one that is *information*
becomes a line of content above the rule. The Reconciliations browse stacks two lists once
a panel is open, and its caption (`Reconciliations · BCP PEN · oldest → newest`) is the
only thing tying the lower rows to an account above. Ask "would the screen still be
unambiguous without this?" — not "is this a title?".

---

## 3. Theming — the terminal supplies every colour

**No literal colors in the TUI, and no authored ones either.** CSS uses `$accent` /
`$secondary` / `$error`; Rich content takes the `PALETTE` constant
([theme.py](../expense/tui/theme.py)). Guarded by
`test_no_literal_color_styles_in_tui`.

The tokens themselves are **ANSI slots**, not hexes (`ansi_green` is slot 2 — the
terminal fills it in), so the app reads on dark, light, Solarized and Gruvbox with **no
detection at startup**, no light/dark pair and no `NO_COLOR` mode. A hex in `theme.py` would pin the app back to one terminal —
guarded by `test_theme_is_ansi_slots_not_hexes`. Why: [decisions.md](decisions.md) "The
terminal supplies the palette".

**Theme the foreground, never the base surface.** The app runs in ANSI mode
(`ExpenseApp(ansi_color=True)`): the base fill is `ansi_default` — the terminal's *own*
background — set **structurally** in `app.tcss`, not per theme. So there is no seam
against the terminal's window padding. **The rule for any future theme:** recolor the
foreground and semantic spans only (text, accents, sign-colors, selection/diff
highlights) — **never** paint a full-screen or base-surface background. A painted
ground reintroduces the seam *and* breaks any light/dark/auto theme, because one fixed
surface cannot match every terminal. Guard:
`test_tui_theme.py::test_base_fills_are_terminal_transparent`.
This is how Claude Code keeps a full theme menu while staying seamless.

Things only rendering revealed, all load-bearing:

- `$surface` / `$panel` generate to **`transparent`** under an ANSI theme → structural
  rules take `$secondary`, the modal ground a literal `ansi_default`.
- **Alpha is dropped** on `ansi_default`, so a modal scrim becomes an opaque fill that
  *wipes* the screen behind it → literal `black 60%`, guarded by
  `test_modal_scrim_dims_rather_than_wipes`.
- An `ansi=True` theme must ship Textual's whole `variables` block or the app dies at
  startup on `$ansi-background`.
- **`text-style: reverse` does not survive CSS** when foreground and background are
  both `ansi_default` — Textual drops it in `get_visual_style()`.

**The cursor is reverse video, and it must be applied as a Rich style.** "You are here"
is drawn the same way everywhere: the terminal's own foreground and background, swapped
— colour-free, so correct on any ground by construction. The shared constant is
`CURSOR_STYLE` in [windowed.py](../expense/tui/widgets/windowed.py) (re-exported from
`cursor_list.py`); `CursorList` / `CheckList` apply it to their Rich table rows,
`suggestion_list` to the picked name, the LOG bar to its staged row, and `CursorOptionList` (the home menu) applies it to the finished strip,
because the theme gives the block cursor no colour of its own and the CSS path drops
`reverse`.

**Assert on rendered strips, not on styles.** `get_component_styles` can report
`text_style: reverse` for a style that is discarded later. Only `render_line(y)` shows
what the user sees, which is what `test_tui_menu_cursor.py` checks.

Slot 3 (yellow) is the one slot that fails on white, so the pending role carries
`bold` rather than a colour.

---

## 4. The keymap contract

Three cross-screen rules. No screen declares them, so no generated key list can find
them — they are hand-written into the `?` card
([help.py](../expense/tui/screens/help.py) `CONVENTIONS`):

- **`r` always refreshes**, everywhere.
- **`y` alone confirms** — scoped to delete / revert / promote, since archive is
  confirm-free (a reversible toggle, not destruction).
- **`⏎` never changes data.** On the Manage lists it is a literal no-op: no screen
  handles `CursorList.Selected` there, and the help card *drops* the row rather than
  advertise `⏎ Open` falsely. A widget whose key is off on some rows names the action in
  its `CARD_FOLLOWS_CHECK`, and the card lists that row only while the widget's
  `check_action` allows it, as the footer does: the Reconciliations panel's `⏎ Open` and
  `⏎ Edit`, which is on in the "no batch" list alone, on every row.

**The import door's exceptions** (§2 "The import door",
[bank_import.py](../expense/tui/screens/bank_import.py)):

- **`⏎ Import N rows` writes.** On the preview `⏎` is the apply — the one key on an import
  screen that changes data, named in the footer with the count it writes. After the apply
  met a ledger line changed while it ran, `⏎ Preview again` reads the dry run afresh and
  writes nothing.
- **The preview's `pgdn`/`pgup` are hinted in the body, not the footer.** The
  `… N more · pgdn` / `… N above · pgup` line under the table says where more rows are; the
  footer keeps to `esc` and `⏎`.
- **No `r` on the import screens.** Each reads once, when it opens — the account list, the
  preview's dry run and the names of the reconciliations that stop a move (read again only by
  `⏎ Preview again`); dropping the file on the LOG bar
  again reads them all afresh.
- **No `?` on the import screens.** They do not take `HelpBindingMixin`; the footer is their
  whole key list.

**The ledger's selection keys** ([transactions.py](../expense/tui/screens/transactions.py)):
`space` selects / unselects the cursor row without moving it (`↓` then `space` is the
rhythm), `a` selects every loaded row or clears the selection, `c` / `b` / `h` open the
bulk pick for category / account / hashtags (§2 "The bulk pick is a full screen": type to
narrow, `↑↓`, `⏎` picks, `esc Cancel`), `esc` clears the selection if there is one,
else goes back to the screen that opened the ledger. `s` and `d` never follow the
selection: they are off while one exists and while a bulk write runs, and `d` is off on an
archived account's row too (§2 "`⏎` and `s` open the Edit form", "On an archived account's
row the ledger offers no `d`", "`d` is the TUI's one destructive key").
`space` is declared on `CursorList` but is live — key and footer both — only on a
screen that handles `CursorList.Toggled`, the same `NEEDS_SCREEN_HANDLER` gate `⏎ Open`
goes through on the `?` card, so the Manage lists neither react to it nor advertise it.

**`pgdn` means "more of this list", in three ways.** In the two growing lists, the ledger
and the "no batch" pane, it appends the next 10 rows by cursor and puts the cursor on the
first new one (footer `pgdn 10 more`; gone at the end), and `pgup` just goes up a
screenful ([decisions.md](decisions.md) "Long lists grow, they do not page"). In every
other list it is the next page of rows already loaded (§5). On Home it walks the month
window one month older, `pgup` one newer (§2).

**The Reconciliations browse** opens on
the **account list alone**, full height, and reads no reconciliations. The list is the
bank accounts of one `GET /accounts?include_archived=true`, people and archived accounts
left out, so an archived account and its own list are not offered until it is unarchived on
Manage ▸ Accounts; the read keeps the archived ones only to name a statement list's
columns (below). Nothing about reconciliations is read until `⏎`, so moving the account
cursor costs nothing. `⏎ Its reconciliations` reads that account's list in **one read**,
whole, in the engine's order (`date_start` ascending, then by account in the accounts'
order, then creation time, oldest first (contract: "Reconciliations", "Ordering")), and
opens the **panel** under the accounts, halving the height, with the cursor in it; the
open account keeps an accent `▸`, and the breadcrumb grows to
`Reconciliations ▸ <account>`. An account with none says `none yet · n to create one`
inside the panel; a read that fails toasts the engine's words and leaves the panel closed.
Coming back from a reconciliation, or `r`, reads the same list again and lands on the same
row.

- **An account with no statement code** reads `GET /reconciliations?account_id=<id>` and
  lists one row per reconciliation: `Name · Period · Begin · End · Diff · Status`, titled
  `Reconciliations · BCP PEN   ·   oldest → newest`.
- **An account with a statement code** reads `GET /reconciliations?statement_of=<id>`
  instead: the reconciliations of every account holding its code, an archived one
  included, the same items in the same order from either card account, each non-null
  `twin_id` naming an item of the same answer (contract: GET /v1/reconciliations). It lists
  **one row per statement** (pane 1 A of
  [expense-world-card-statement.html](mockups/expense-world-card-statement.html), and its
  task 6 question 3 B for a code one account holds): an item, and the item its `twin_id`
  names, found by id, the row standing where the first of them stands; no other read, and
  no pairing by dates or names. The statement's accounts are the open account, the card's
  other account the engine names on it as `statement_partner_id`
  (contract: "Bank Accounts", "Statement partner"), and any account the answer has a half on
  (`statement_columns` in [reconciliations.py](../expense/tui/screens/reconciliations.py));
  the app never pairs accounts by their codes. The columns are `Name · Period`, one
  `Diff <CUR>` per account of the statement in the accounts' order (`Diff PEN · Diff USD`;
  `Diff` alone on a code one account holds), then `Status · Order`. Each Diff is that half's difference by
  the rule of every reconciliation list (a dim `—` when it adds up, the figure when off, blank with no ending
  balance), `no half` where the statement has none on that account. Status is `completed`
  or `draft` when the halves agree and `half completed` (warning) when they do not; Order
  is `in order` when the engine's `unplaced_count` and `shared_place_count` both read 0 and
  `not in order` (warning) otherwise, the same two counts on both halves (contract: "Reconciliations", "A statement's order").
  A completed statement is dim, as a completed reconciliation is. The title names every
  account of the statement, then the code:
  `Reconciliations · Signature PEN + Signature USD · SIG   ·   oldest → newest`, and every
  listed one carries the `▸`, so opening either card account shows the identical list. An
  archived card account is not listed, and while it is archived neither account names the
  other (contract: "Bank Accounts", "While one of the two accounts is archived"), but its
  halves still show under its own column, which the answer's halves and the accounts read
  name; while it holds no half it has no column. A row stands for the open account's half,
  or the other half on a month with none there: `⏎` opens that half on the batch
  screen, in its own currency.

**Keys**: `n` new
batch — for the open account, or with no panel for the account under the cursor, and once
saved the panel opens on the new one (on a card account, the card statement's form below); `u` swaps the panel to the account's rows in no
batch (panel open only); `d` deletes the cursor row **in that pane only** (a no-op on the
reconciliation list, where a batch's own delete lives one screen deeper); `esc` retreats
one step — no-batch rows → the panel → the account list (`esc Close the panel`) → Home.
`u` means *revert* on the batch screen one keypress away; the overlap is deliberate.

**The begin balance's hint takes two lines** on the new-reconciliation form, the whole hint
dim as every hint is (panes 1 B and 2 B of
[expense-world-opening-balance-note.html](mockups/expense-world-opening-balance-note.html)):
`signed decimal · your statement's opening balance`, then directly under it
`0.00 if it holds the account's opening balance, which already counts it`. The engine sums
every transaction assigned to a reconciliation, an account's opening balance included, into
its add-up check (contract: "Reconciliations", "`difference_cents` — the add-up check"), so
the statement holding that line begins at 0.00; the form cannot know which statement that is,
so the line is always there. Each half's begin on a card's form carries the same second line.

**A card statement's create form** (`n` on a card account; pane 2 A of
[expense-world-card-statement.html](mockups/expense-world-card-statement.html)). A card is
two bank accounts sharing a statement code, one per currency
(contract: "Bank Accounts", "Statement code"). The engine names a card account's other account
on it as `statement_partner_id`, and the browse reads that account from the accounts list it
already holds (`card_partners` in [reads.py](../expense/reads.py))
(contract: "Bank Accounts", "Statement partner"). It is null on an account with no code, on one
whose code no other live account holds, and on both accounts while either is archived, so such
an account keeps the one-account form. On a card account `n` opens one
form, `Reconciliations ▸ <account> ▸ New`: `name`, then the line `accounts  Signature PEN +
Signature USD · SIG` (stated, never edited), `date start`, `date end`, then the open account's
`begin balance <CUR>` and `end balance <CUR>`, then the other account's. Each balance's hint
names its half by currency (`signed decimal · the dollar half's opening balance`; `soles half`
for PEN, `dollar half` for USD, any other by its code, `formatting.half_name`), a begin's
with the opening-balance line under it (above); both begins are
required, both ends optional. `^s Create both`, or `⏎` on the last line, sends one
`POST /reconciliations` whose `twin` is the other half, its own id, account and balances,
taking the request's name and days (contract: POST /v1/reconciliations). Both halves are
created, or neither is: a refusal is the form's `Failed` note with the engine's words whole,
one check at a time, a `twin.` key naming the other half (`twin.date_start: Overlaps …`); no
line of the app's is added (a taken id keeps its app-fault line), and the form stays with
what was typed. Saved, it says `Statement created.` and, as the one-account form does, the
panel opens on the open account's reconciliations, the cursor on its new half.

**A reconciliation's batch screen** (`⏎` on one in the panel; screens 2a–2c in
[expense-world-bank-lines-whole.html](mockups/expense-world-bank-lines-whole.html)) is its
header — name, account, period, then `begin`, `end`, `diff` and `status` — over a list of
**bank lines**, read from `GET /bank-lines` (contract: GET /v1/bank-lines) through
`fetch_bank_lines` in [reads.py](../expense/reads.py), every page of each read. On a draft
it is a tick-list: the batch's lines (`reconciliation_id=`) ticked and first, then the
account's lines in no batch inside the period (`account_id`, `unreconciled=true`, and the
period's own days as `date_from` / `date_to`), each read in the engine's order, newest
first. Once completed it is the batch's lines alone, read-only, with no tick box. A
transaction split into parts is **one row with its total**, never half of it, and nothing on
the row says it is split. Every row is one line of the bank's own columns, `Date ·
Title · Operation · Amount`, made by `bank_line_columns` in
[formatting.py](../expense/formatting.py): the day and title of the line's parts, its
`operation_code` (a dim `—` when it has none) and its signed `net_cents`, sign-coloured
(contract: GET /v1/bank-lines/{bank_line_id}); no category, hashtags, note or part count.
**Keys**: `space` puts the line under the cursor in or out of the batch with one
`PUT /transactions/{id}` of `reconciliation_id` (or `null`) on one of its parts, which
moves every part (contract: PUT /v1/transactions/{transaction_id}, "Reconciliation assignment");
once every tick sent is answered, the screen reads the reconciliation and its lines again,
so the header's `diff` is the engine's, and the cursor stays on the line ticked last, now
among the ticked ones; a read that lands while a tick is still unanswered is not drawn, so
ticking down a statement (`space`, `↓`, `space`…) never lands on another row. A refused
tick drops the ticks queued behind it, shows `Couldn't update` with the engine's words and
reads the reconciliation and its lines again, the cursor on row 1; so does a refused
complete, revert, delete or balance save that had ticks queued behind it, under its own
`Couldn't …` note. `c` completes, after the question `Complete reconciliation?` · `Locks the
amount, date, title, account, operation number and reconciliation of the N ticked rows.` (N
the rows ticked, and `1 ticked row` for one): completing makes those six read-only on each
ticked row, an empty title or operation number staying fillable
(contract: PUT /v1/transactions/{transaction_id}, "Field locking");
`u` reverts, `d` deletes the reconciliation, `r` reads it again, `esc` goes back.
**On a half of a card statement** the screen shows that half alone, its own lines and figures,
while `c`, `u` and `d` act on both halves in one write, from either half
(contract: POST /v1/reconciliations/{reconciliation_id}/complete)
(contract: DELETE /v1/reconciliations/{reconciliation_id}).
On an account with a statement code the engine completes nothing until every line of the
statement has a place in its order (contract: POST /v1/reconciliations/{reconciliation_id}/complete),
and no screen sets the order ([decisions.md](decisions.md) "A card's statement is one statement, and a month closes from the bank's PDF").
**`c` needs the ending balance**: the engine completes no reconciliation without it
(contract: POST /v1/reconciliations/{reconciliation_id}/complete, "The ending balance must be entered").
On a draft whose `end` is empty, `c` first opens the box `Ending balance first` (`The
statement's closing figure for <account>, in <currency> · signed · e.g. 13,853.20`,
`[enter] save    [esc] cancel`). The figure is read by the shared money parser exactly as
typed — the sign is the one typed, never added or flipped; text it cannot read keeps the
box open with what was typed and notes `End balance: a signed decimal, e.g. 9460.00`, and
nothing is sent. `esc` closes it with nothing saved. `enter` saves it
(`PUT /reconciliations/{id}` with `ending_balance_cents`), the header shows the engine's
saved `end` and `diff`, and then the usual `Complete reconciliation?` asks; only `y`
completes, and any other answer leaves a draft with its balance saved, so the next `c`
goes straight to the question. A draft that already has its ending balance goes straight
to the question too. A refused save shows `Couldn't save` with the engine's words and,
for `CONCURRENT_CHANGE`, `It changed at the same moment: press r, then try again.`. A
refused complete shows `Couldn't complete` with the engine's words — after a save in the
same `c`, under the line `The ending balance is saved. The reconciliation is not
completed:` — and the screen reads the reconciliation fresh, so the header and the next
`c` go by what the engine holds.

**`+` logs a transaction** — Home and Transactions (`LogTransactionMixin` in
[_base.py](../expense/tui/screens/_base.py), splatted into each host's BINDINGS like
`HelpBindingMixin`). It always opens the **LOG bar**: one key, one meaning. Whether a line
stages is decided by *the line you typed* — refused in place with the reason if it
cannot. Plain `+`, no modifier — `shift`+`+` is not bindable at all, and the numpad and
main-row keys send the same byte, so one binding catches both.

**The LOG bar's own keys** ([log_bar.py](../expense/tui/screens/log_bar.py)): `↵`
stages the line — or completes the open token, or puts a lifted row back; `↑↓` drive
the completion picker while a token is open and move through staged rows when the bar
is empty; `ctrl+s` writes everything not already written; `ctrl+x` drops the picked
row; `esc` unpicks, then leaves (confirming if rows are staged and unwritten). The bar
always holds focus, which is why no bare letter is a command there and why the screen
has no `?` — a focused `Input` swallows printable keys.

**A dropped bank file.** Dragging a file onto the terminal makes the emulator type its
path into the bar, each in its own shell syntax: Terminal.app backslash-escapes spaces,
parentheses and every other shell-special character, and puts several dropped files on
one line separated by spaces; VS Code's terminal single-quotes the path for bash and zsh
(double quotes for some other shells) and inserts only the first file of a multi-file
drop. A path pasted or typed by hand may also be raw, spaces and all. One pure function,
`dropped_bank_files` in [dropped.py](../expense/tui/dropped.py), reads every form: the
line is bank files only when **every** word is an absolute (or `~/`) path to an existing
`.xlsx` file, any letter case; one word that is not leaves the whole line quick-add.
Typing, pasting and dropping reach it as the same text. While it holds, quick-add stands
down — no token colouring, no picker, no refusal, no account peek (hidden, still on its
last account), no legend row — and the hint reads `bank file · <name> · ⏎ import it`,
or `bank files · <n> · ⏎ import them, one by one` with each name on its own indented
line. The footer reads `esc Cancel  ⏎ Import` (`ctrl+s` is off while files are in the
bar). `↵` stages nothing: it hands the paths to `LogBarScreen.import_bank_files`, which
starts the import door (§2 "The import door"). Editing the line back to anything else
returns the bar to quick-add on the same keystroke.

**The Edit form's own keys** ([edit_form.py](../expense/tui/screens/edit_form.py)): the bar
form's keymap (`form_bindings`, "The bar forms' keys" below) with two more, each shown only
where it works (`check_action`): `ctrl+n` adds a part and `ctrl+x` drops the part the bar is
on, both off where the line's `edit_limits` holds `parts_fixed`, and `ctrl+x` only on a part's
line while the table holds two parts or more. On a part's line `ctrl+x` drops the part in place
of the bar's own cut. The footer reads `esc Cancel  ^s Save  ⇥ Field  ^n Add part`, then
`^x Drop part` where it works. There is no `?`: the Edit form is a bar form (`FormScreen`), and
forms take no `HelpBindingMixin`, so there is no `?` card; the bar takes `?` as a character.

**The legend row.** One fixed row under the bar carrying the whole grammar and what `↵`
does: `$account · @category · #tag · ±amount · //note · when     ↵ stages the line`. It
never changes, so nothing below it moves; everything that *does* change (the amount echo,
the resolved date in words, how many names a token matches, loading/writing) is the
`#hint` row above it.

**The account peek.** The moment the typed line names an account, that account's posted
ledger fills the room under the staged list — `AccountPeek`, five columns (date, title,
amount, category, tags; no account column, every row names the same one).

* **Elastic.** `#peek` is `height: 1fr` and everything above it is `height: auto`, so the
  panel gets exactly the rows the staged list leaves and draws that many; it re-renders on
  its own `Resize`. The empty-state invitation stands down while it is up.
* **The account is the bar's**, never a staged row's — the highlighted candidate while a
  picker is open, nothing at all when the token resolves to nothing.
* **It stays put.** `↵` clears the bar; the panel keeps the last account the bar named.

Read-only: no cursor, no keys, `↑↓` stay with the staged list. One debounced
`GET /transactions?account_id=…` per account, cached for the life of the screen, and a
save invalidates what it wrote to.

**The bar forms' keys** (`form_bindings` in [_form.py](../expense/tui/screens/_form.py),
one copy for the Edit form, the create/edit forms, the new-reconciliation and card statement
forms and Setup; the Edit form adds the keys "The Edit form's own keys" above names):
`⏎` keeps the field and moves one line on, to the next field that can change; when no field
ahead can change (on the last field, or with only read-only fields after it) it saves the form
as `ctrl+s` does (`FormScreen._advance`). Textual runs the `on_input_submitted` of every class
in a screen's MRO on one `⏎`, so a form whose handler overrides an inherited one calls it
itself and prevents the message's default, and one `⏎` moves one line (guarded by
`test_a_forms_own_enter_handler_stops_the_ones_under_it`). `ctrl+s` saves the form, `esc`
cancels. `tab` moves to the next field and `shift+tab` to the previous, on every field,
whether or not a suggestion list is open. `FormScreen` is declared
`inherit_bindings=False`, so Textual's focus-cycling `tab` never applies and the bar
keeps focus; Screen's hidden `ctrl+c` copy key is declared again in `form_bindings`.
Plain `↑`/`↓` walk the suggestion list when the field has a non-empty one and move to the
previous/next field when it has none. `ctrl+↑`/`ctrl+↓` also move fields but are never
advertised: macOS claims `⌃↑` (Mission Control) and `⌃↓` (Application Windows) before the
terminal sees them. Every field move skips read-only fields and stops at either end.
On a read-only field, where the bar sits only when every field is read-only, the bar
(`FormBar`) takes nothing typed, pasted or deleted, and `⏎` keeps nothing and moves on as
from any line (with nothing ahead to change, it saves), so nothing ever lands on a read-only
line.
**No hint says "save" on a line where `⏎` moves on, and none says "go on" on a line where
`⏎` saves** (`FormScreen._goes_on`; guard: [test_tui_form_hints.py](../tests/unit/test_tui_form_hints.py),
which walks every bar form). NAME on Manage ▸ Accounts and Manage ▸ Categories (New and Edit)
and the Edit forms' TITLE read `free text · enter to go on`, and a new reconciliation's NAME
`e.g. “April 2026” · enter to go on`. A bank account's STATEMENT CODE reads
`optional · three capital letters, e.g. SIG · enter to go on`, with `· empty clears it` before
`· enter to go on` on Edit. The account's COLOR, New and Edit, reads
`optional · enter keeps it · ↑↓ another swatch`, though on New, and on a person's Edit, it is
the last line and `⏎` there saves. Some lines where `⏎` saves say so: a new category's COLOR
(`optional · enter to save · ↑↓ another swatch`), the Edit form's last NOTE (a part's NOTE
with another part after it reads `optional · enter to go on`), a new reconciliation's END
BALANCE, and the Edit form's TITLE when no line after it can change, which reads
`free text · enter to save`; others, such as Edit category's COLOR (`pick a swatch`) and
Setup's last line, leave it unsaid.
The footer reads `esc Cancel  ^s Save  ⇥ Field` (`Create` on a create form; the Edit form's
own keys after them):
**`⇥ Field` is the form's one navigation footer slot**, because forms have no `?` card
that could list the other keys (below). Guarded by `test_form_navigation_keys_are_not_advertised`.
**Setup's footer** reads `esc Quit  ^s Connect  ⇥ Field`: there is no screen of its own
under it to go back to, so `esc` leaves the app, and `^s` reads `Create` once the engine
asks for a profile (two `ctrl+s` bindings, `check_action` showing one). Its address and key
are read-only once the engine has accepted them.

**The footer never advertises the arrow keys.** `Navigate` is declared `show=False` on
`CursorList` and `CheckList`. The keys work unchanged and the `?` card still lists them.
`pgdn`/`pgup` and `→ ←` expand/collapse **stay** in the footer: they are not obvious (the
import preview's `pgdn`/`pgup` are the exception above). New
bindings inherit this rule — if a key only says "the cursor moves", it does not get a
footer slot.

**One key per job.** No movement aliases (`j k h l`, `,` `.`) and no `[`/`]` — a widget
alias silently outranks a screen binding, so letters stay free as *command* keys. Guarded
by [test_tui_help.py](../tests/unit/test_tui_help.py)
(`test_no_duplicate_movement_key_aliases`, `test_square_brackets_are_not_bound_anywhere`).

**A screen key that a focused `Input` also claims needs `priority=True`.** Textual
resolves the focused widget's bindings before the screen's, and `Input` binds more
chords than it looks like — `ctrl+x` is `cut`, `ctrl+k`/`ctrl+u`/`ctrl+w` are line
edits, `ctrl+a`/`ctrl+e` are home/end. The LOG bar's `ctrl+x drop row`
([log_bar.py](../expense/tui/screens/log_bar.py)) would otherwise edit the line
instead of dropping the staged row. Plain `↑`/`↓` and `escape` need nothing — `Input`
does not bind them — and `⏎` arrives as `Input.Submitted`, not as a binding at all.

**Standing constraint:** any future rename action on Manage screens ships as `e`,
never `r`.

**App-wide keys are `^q` and `?`.** `?` opens `HelpModal`, a two-column card whose
content is **derived** from BINDINGS by walking the screen's and the focused widget's
MRO and keeping only classes declared under `expense.tui` — which is what keeps
Textual's own `home`/`end`/`tab` out without a suppression list. `Binding.tooltip`
carries the card's fuller wording (`Archive / unarchive`) while `description` stays the
terse footer label (`Archive`): one declaration, two audiences. `?` is bound per screen
root via `HelpBindingMixin`, **never on the App** — letters bubble up from lists, the
same reason there is no app-level `q` (it is scoped to Home). **Forms have no help
key**: a focused `Input` swallows printable keys, so `?` would type a question mark.

**The Textual command palette is off** (`ENABLE_COMMAND_PALETTE = False`); `?` is the
one discoverability surface.

**Mouse is off** (`run(mouse=False)`) — the TUI is keyboard-only. Corollary:
terminal-level scrolling reaches the terminal itself, and Terminal.app will scroll into
scrollback *above* the running app. Launch therefore wipes screen and scrollback
(`CSI 2J 3J H` in `launch`) so there is nothing to reveal.

---

## 5. Pagination and terminal size

Every `CursorList` / `CheckList` renders one window of **min(`PAGE_ROWS_CAP`, what fits
the terminal)** rows — the page IS the screenful, so the page status and footer never
clip and no dead scrollbar appears. A resize re-measures
(`SectionScreen.measure_list_rows`, floor 5) and keeps the first visible row.
`DEFAULT_PAGE_ROWS` (20, one copy in [reads.py](../expense/reads.py)) is the app-wide cap and the
pre-layout fallback everywhere except **Transactions, which fills the window**: it sets
`PAGE_ROWS_CAP = ENGINE_PAGE_CAP` (200, the engine's own `limit` ceiling) and
`CARD_WIDTH = None`, so its card spans the full width too. Every other screen keeps its
20-row cap and its own `CARD_WIDTH`.

The ledger's cells fill that width:
`transaction_rows` hands the table whole strings and `CursorList(flex={0: 3, 1: 3, 6: 2})`
makes Title, Description and Hashtags Rich ratio columns — Amount, Date, Account and Cat
take their natural width first, the three text columns share what is left 3:3:2, and each
cell is cut at the edge of the column it actually has. On a narrow terminal the free text
gives way before the numbers. Every other list leaves `flex` empty and keeps Rich's
content-proportional spread.

**Transactions is one list that grows**,
through `GrowingRead` in [_growing.py](../expense/tui/screens/_growing.py): it opens with
the newest `GROW_STEP` (10) rows and the count, read together — a count that cannot be
read fails the screen — and `pgdn` (footer: `pgdn 10 more`) appends the next 10 by the
engine's cursor, with no recount, the cursor landing on the first new row. `↑`/`↓` scroll
everything loaded and `pgup` goes up a screenful. The window sizes only what is drawn: a
resize reads nothing. After a write (a bulk key, the `⏎` edit, `+`, `s`, `d`) it starts over from
the newest 10 with the cursor on row 1, as `r` does. Leaving the `⏎` form with `esc` is
not a write: nothing is read and the list comes back as it was — the rows `pgdn` loaded
and the cursor on its row; the form dismisses with `True` only on a
save. The "no batch" list on
Reconciliations grows through the same `GrowingRead`, newest first — one copy of the
cursor, the count, the `pgdn` read and the rule that a `pgdn` read never lands on a list a
fresh read replaced.

**Full-data screens window locally** — Manage, the Reconciliations account list (full
height alone, an equal split with the open panel), the recon checklist at what fits —
with `pgdn` next page, `pgup` previous (hidden when one page holds it all); `↑`/`↓` walk
through and cursor-restore lands on its page. Exempt: Home's month grid, static tables,
System kv-tables.

**Minimum terminal size: there is no guard.** The app degrades and says nothing; the
terminal is the user's to size ([decisions.md](decisions.md) "A terminal too small is the
user's to fix"). Two reference sizes, both measured:

- **80×24 — everything correct.** No truncation anywhere, full footer. The size the
  screens are designed at.
- **60×20 — still workable, already lossy.** Every row draws, but columns are
  ellipsised (`R…`, `-1…`).

| dimension | measured behaviour |
|---|---|
| w ≥ 80 | no ellipsis in any cell |
| **w ≈ 75** | **truncation begins** |
| w ≈ 50 | title column is a bare `…`, amount `-…`; every row still drawn |
| w ≤ 40 | date goes too — rows of pure ellipsis |
| height | the list clips when content exceeds the viewport, so the threshold moves with the page size. Rows are cut off, never reflowed. Above the floor the page is measured to fit exactly — `LIST_FRAME_LINES` (6: section rule 1, the table's 4, page status 1) is **derived from the render** by `test_the_frame_costs_exactly_list_frame_lines` |
| h ≤ 10 | no data rows at all, while the footer still offers to page through them |

`PAGE_ROWS_FLOOR = 5` floors the *requested page size*, not the viewport — it cannot
make rows fit that do not. Width has **no** floor of any kind.

---

## 6. Test conventions

- **A pilot test waits on a condition, never on the clock.** Use `wait_for(pilot,
  predicate)` / `wait_for_list` / `wait_for_loaded` in
  [tests/unit/helpers.py](../tests/unit/helpers.py). A `SectionScreen` has settled when
  its `section-load` worker has finished (`section_settled`), not when `#card` is in the
  DOM: the card is queryable before its children are mounted, and before the screen's
  `_show` has run its tail (focus, mode). Wait for the thing the test is about: a save
  is over when its request was sent *and* `_saving` is false again, since `_saving` is
  already false before the key reaches the screen. A **bare** `pilot.pause()` is the
  pump-drain for asserting a *non-event* (an inert key, a confirm that must not fire),
  where no predicate can be written. Timed `pilot.pause(<n>)` is rejected by
  [tests/unit/test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py), which carries
  exactly one documented exemption (the cancelled-worker window in
  `test_tui_reconcile_detail.py`, keyed on the whole source line so editing it re-opens
  the question).
- **Patch `load_*_name_map` at the screen module** (`expense.tui.screens.X.load_…`),
  not at `expense.reads` — when the test's point is name display. Use the short-id fallback
  when it isn't.
- **`fake_client` (conftest) patches the lazy-import seams only** —
  `expense.http.ExpenseClient` and `expense.config.ensure_loaded`. Assert on
  `client.calls` / `.posts` / `.puts` ordering.
- **A `FakeClient` write answers in the engine's shape where helpers.py knows it** — a
  POST or PUT gets the test's own `write_responses[path]` first, exactly as set; then,
  as a DELETE always does (`write_responses` is keyed by path alone, so a PUT answer
  never comes back on a DELETE of the same path), the endpoint's entry in
  `helpers.FAKE_ANSWERS`; otherwise `{}`. A reconciliation's create, revert,
  complete and delete have entries, each built by the endpoint's `answer_of` builder, so
  the drift check covers its shape ([runtime.md](runtime.md) "Working against the live
  engine", "Fixture drift"): the
  create answers what it was sent, `twin` included on a card; the other three answer the
  half the path names, read from the test's `GET /reconciliations/{id}` when it serves
  one (its id alone otherwise), with its status after the write, and its twin when that
  record names a `twin_id`.
- **No request body carries `line_code`, `statement_line` or `statement_place`, at any
  depth** — the engine sets each itself and refuses it in every request body as
  `UNKNOWN_FIELD` (contract: "Transactions (Ledger)", "Bank lines"), while a statement's
  order goes out as `places`, a list of line ids, which passes
  (contract: "Reconciliations", "A statement's order"). The autouse
  `_no_read_only_fields_in_requests` in [conftest.py](../tests/unit/conftest.py) fails any
  unit test whose request holds one (`helpers.READ_ONLY_FIELDS`), even when the app
  swallows the refusal: it checks `httpx.Client.send` (respx), `FakeClient.post`/`.put` and
  any function a test puts in their place.
  [test_no_read_only_fields.py](../tests/unit/test_no_read_only_fields.py) trips it on each
  field. Any other class in `tests/unit` with its own `post` or `put` is a fake engine: it
  subclasses `FakeClient` or calls `helpers.refuse_read_only_fields` in each, as
  `test_every_fake_engine_refuses_read_only_fields` in
  [test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py) checks.
- **A test that reads what a toast shows runs with `run_app(..., toasts=True)`** and reads
  `toasts_shown(app)` ([helpers.py](../tests/unit/helpers.py)): each toast's title and
  message as Textual draws them, markup read. `run_test` draws no toast unless asked; a
  test that only needs what was sent patches `notify`.
- **The typed surface is pinned** by
  [test_command_surface.py](../tests/unit/test_command_surface.py) (CLAUDE.md "Testing
  conventions").

**Known, accepted:** a screen load may open several short-lived clients (Transactions:
the page and three name maps; the bulk pick's reference lists load once, on the first
bulk key) — harmless on loopback.
