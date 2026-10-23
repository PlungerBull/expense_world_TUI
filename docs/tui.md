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
    cells.py        # cell renderers: color swatch, sign-colored right-aligned amount_cell;
                    #   `—` for a null amount, BLANK for a null difference_cents
                    #   (different states, never the same glyph — decisions.md)
    windowed.py     # CURSOR_STYLE (reverse video, app-wide) + WindowedList — the
                    #   window/cursor/page arithmetic both list widgets stand on
                    #   + page_indicator() — `rows 21-40 of 133 · page 2 of 7`
    cursor_list.py  # CursorList — arrow-key list, window + growing modes
                    #   + CursorOptionList — the home menu
    checklist.py    # CheckList — the reconciliation tick-list, one bank line per row
    picker.py       # suggestion_list() — the scrolling name list both quick-add
                    #   surfaces drop under their input
  screens/
    _base.py        # run_write + confirm_delete (EngineWriteMixin), SectionScreen, keymap
    _form.py        # FormScreen base — fields, validation, bar-cycle plumbing
    _growing.py     # GrowingRead — a list that grows by cursor (ledger, "no batch" pane)
    help.py         # HelpModal — the `?` card, derived from BINDINGS (§4)
    home.py         # four months × categories, balances today, then every screen
    transactions.py # the ledger — whole, or filtered by Home; `space` + `c`/`b`/`h` bulk
                    #   edits; `s` splits and `d` deletes the cursor row
    accounts.py     categories.py  hashtags.py
    reconciliations.py               # full lifecycle
    system.py       # Config / Auth screens
    setup.py        # SetupScreen — first-time setup: engine address + key, then a
                    #   profile; what the app opens on with no usable settings file
    edit_form.py    # the transaction EDIT form (`⏎` on a row); `record` is required
                    #   + BankLineEditFormScreen — the same form on a bank line,
                    #   `⏎` in the "no batch" list: the bank's columns only
    log_bar.py      # the LOG bar — what `+` opens. One typed line, a staged batch,
                    #   the named account's ledger below it (AccountPeek), one save.
                    #   Parses through expense/quickadd/; `↵` stages a line or refuses
                    #   it in place; ctrl+s writes every row through POST
                    #   /transactions/batch (via expense/batch_write.py; chunking in
                    #   runtime.md "Bulk writes"). Saved rows
                    #   keep a ✓ until the next line is staged; a partial failure
                    #   re-sends only the rest.
    split.py        # the split screen — what `s` on a ledger row opens. A table of
                    #   the parts, the picked part's fields or the title's one field
                    #   below it (FormScreen), one POST /transactions/{id}/split with
                    #   the title when it changed; a refusal stays under the parts
    bank_import.py  # the import door behind the LOG bar: a dropped bank file →
                    #   which account → preview → result, one file after another.
                    #   Reads, previews and applies through expense/bank_import/
                    #   (flow.py)
    create_forms.py # BarFormScreen + New{Account,Category,Hashtag} small forms
                    #   New account carries a TYPE field (bank/person, prefilled
                    #   bank) that picks POST /accounts vs POST /people; the
                    #   account Edit form carries the opening balance (§2).
                    #   COLOR is optional on New account and New category
                    #   (hint `optional · empty enter to skip`): a skipped
                    #   colour is left out of the body, never sent as null, and
                    #   the engine gives its default (contract: POST /v1/categories).
                    #   While an optional line is empty no swatch is highlighted;
                    #   typing or ↑/↓ highlights one, and enter then picks it.
                    #   Edit category keeps it required, so a PUT never sends null
    modals.py       # ConfirmModal, PickerModal, DiscardStagedModal (the LOG bar's one
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
`SectionScreen._load`, every worker of the LOG bar and the split screen's read hand back
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
`PickerModal` over the selection — or over the cursor row when nothing is selected —
to set the category, move to an account, or **replace** the hashtag set. The write is
one `PUT /transactions/{id}` per row, in order, on one client, then the list reads fresh
from the newest 10 with the cursor on row 1: on a filtered list the changed rows **leave
at once**, the toast `3 rows → KORAKUEN` is the receipt, and a refused row (an account
move a completed reconciliation locks) is named by number and does not stop the others.
The one refusal that does stop them is `SETTINGS_MISSING`
([runtime.md](runtime.md) "Bulk writes"): the rows after it are never sent, and stay
selected with the refused one.
A row stays selected only if the fresh read brings it back among the newest 10; further down
it drops out of the selection.
**Stepping past ACCOUNT or CATEGORY keeps them** (Question 1 A of
[expense-world-enter-and-esc.html](mockups/expense-world-enter-and-esc.html)). On the `⏎`
edit form the ACCOUNT and CATEGORY lines open with the bar empty and the whole list in its
usual order, the highlight on the row's own account or category, so `⏎` with nothing typed
keeps it and moves on: `⏎` on every line and then `ctrl+s` send nothing and say
`No changes to save.` Typing filters the list and highlights its first match, `↑↓` choose
another, and a bar emptied again puts the highlight back on the row's own. CATEGORY's list
is the one the ledger's `c` offers (`pickable_categories` in [reads.py](../expense/reads.py)):
`@Pendiente` is in it, where the engine lists it, so on a row in `@Pendiente` the highlight
starts on it and `⏎` keeps it, and picking it on another row sends that row back to waiting
for a category (Question 3 A of the same mockup); `@Opening` is never in it. A value the list
does not hold leaves the highlight on the first entry, and there `⏎` with nothing typed takes
that entry. The "no batch" Edit form's ACCOUNT works the same (`_recompute` in
[edit_form.py](../expense/tui/screens/edit_form.py)).
**A move takes a row out of its reconciliation.** The engine refuses an account change on
a row in a draft reconciliation unless the write also says what happens to the assignment
(contract: "Assigning transactions") (contract: PUT /v1/transactions/{transaction_id}), so `b` adds
`reconciliation_id: null` to each row whose account changes, and only to those: a row
already on the picked account keeps its reconciliation. The receipt then counts the rows
that left one — `3 rows → BCP USD · 2 left their reconciliation` (`· 1 left its
reconciliation` for one). The `⏎` edit form does the same when its account changes and
says `Saved. It left its reconciliation.` instead of `Saved.`; both share
`unassign_on_move` in [edit_form.py](../expense/tui/screens/edit_form.py).
**An emptied note empties it.** `⏎` on an emptied NOTE empties the note: the save sends
`description: ""` and says `Saved.`; the engine refuses `null` there as `NOT_NULL`
(contract: PUT /v1/transactions/{transaction_id}). On a row with no note it is no change.
No field the form sends is `null` except `operation_code`, which `null` clears, and the
`reconciliation_id: null` a move adds.
**An opening balance stays on its account and in @Opening.** The engine refuses to move
such a row to another account or category, `@Pendiente` included, and accepts every other
field (contract: PUT /v1/transactions/{transaction_id}, "Opening balances stay put"); screens in
[expense-world-opening-balance-rows.html](mockups/expense-world-opening-balance-rows.html).
An opening balance also carries no hashtag, not even the pending one
(contract: PUT /v1/transactions/{transaction_id}); screen 6 A in
[expense-world-pending-hashtag-manage.html](mockups/expense-world-pending-hashtag-manage.html).
The app knows the row by its category: the @Opening system row, found by its `system_key`
in the categories list the form already reads (`QuickAddRefs.opening` in
[reads.py](../expense/reads.py)). On such a row the `⏎` edit form shows `account`,
`category` and `hashtags` (`—`) dimmed and marked `read-only`, every field move (`tab`,
`shift+tab` and the arrows) skips them, and the save never sends them; date, title, amount
and note save as on any row. `b`, `c` and `h` send such a row like any other, and the engine
refuses it: its "Refused" note is the engine's words, then the line saying what to do
("When the engine says no" below), the other rows still go, and the refused row stays
selected. The LOG bar is untouched: it only creates rows, and a typed line cannot name
@Opening.
**A part of a split transaction says what reaches every part.** The engine writes a part's
date, title and account onto every part of its bank line, in one go, while amount,
category, hashtags and note stay the part's own
(contract: "Transactions (Ledger)", "Bank lines"). So on a part, the `⏎` edit form's hint
under the bar adds `· changes every part of the transaction`, in the accent, while the cursor
is on date, title or account, and says nothing more on the other fields; screen 1 B in
[expense-world-edit-part.html](mockups/expense-world-edit-part.html). The form knows the
row is a part from one `GET /bank-lines/{id}` read as it opens, by the row's
`bank_line_id`: the engine's `part_count` above 1 (contract: GET /v1/bank-lines/{bank_line_id}).
On a row that is not split, and when that read fails, the form and its hints are as on
any row; the save is the engine's either way.
The ledger's bulk keys follow the same rule on a part: `c` and `h` change only the selected
parts, and `b` on one part moves the whole transaction, every part leaving its reconciliation with
it, in the engine's one write (contract: PUT /v1/transactions/{transaction_id}, "Line fields").
The app sends one `PUT` per selected row either way and fans nothing out itself. With every part
of a split transaction selected, each part gets its own `PUT`; a later one finds the line already moved
and the engine accepts it as it is, since the `PUT` carries no `version`. The receipt counts the
rows sent, so `b` on one part reads `1 row → …` however many parts moved.
**`s` splits the cursor row into parts** ([split.py](../expense/tui/screens/split.py),
screens 1 to 6 in [expense-world-split-screen.html](mockups/expense-world-split-screen.html)).
`s Split` sits in the ledger's footer before `d Delete`, whole ledger or filtered from Home, and
like `d` it works on the cursor row only: off, and out of the footer, while rows are selected,
while a bulk write runs, or while the cursor is on an archived account's row ("On an
archived account's row the ledger offers no `s` and no `d`" below). It pushes the split
screen, a full screen whose crumb adds `Split` to the ledger's. On top, what every part
keeps: `2026-10-11  ·  Sueldo Soles  ·  -100.00 PEN  ·  every part keeps this date and account`, the date, the account and the line's total. Under it the
TITLE line, `TITLE      Tottus Jockey Plaza      same on every part`: the title every part
takes, the transaction's until it is changed (below). The screen opens the row's bank line
with one `GET /bank-lines/{id}` (`fetch_bank_line` in [reads.py](../expense/reads.py)): its
`parts`, its `part_count` and its signed `net_cents` total
(contract: GET /v1/bank-lines/{bank_line_id}). Each part comes as a magnitude and its
`transaction_type`, signed by `signed_cents` in [formatting.py](../expense/formatting.py). A
transaction never split is its line's one part, so the table opens empty; on any part of a
split transaction (`part_count` above 1) the table opens with all its current parts, ready to
change, drop or add to. A row with no bank line opens at its own amount and reads none.
**The table** is `amount  category  hashtags  note`, each part numbered, then `+  add a part`
dim, then the line adding the parts up: `2 parts  ·  -100.00 of -100.00  ✓`, the tick in the
success colour, or `2 parts  ·  -90.00 of -100.00  ·  -10.00 left`, `-10.00 left` in the error
colour: the parts' amounts summed against the engine's total. It never stops a send. A part
with no amount, category or real hashtag reads `—` there (no category is `@Pendiente`, the
pending hashtag alone is no hashtag); no note reads blank. `↑↓` move the cursor from the TITLE
line through the parts to `+ add a part`, the cursor's line in reverse, and stop at either end;
the screen opens with the cursor on the first part, or on `+ add a part` when there is none.
**The fields below.** `⏎` on a part opens its fields under the table, under a dim rule and
`PART 2`: `AMOUNT`, `CATEGORY`, `HASHTAGS`, `NOTE`, one per line, the part marked `▌ 2` in the
accent in the table. They are the bar form's (`FormScreen` in
[_form.py](../expense/tui/screens/_form.py)), behaving as on the Edit form: the field the
cursor is on reads `▌ CATEGORY` in the accent with its input after it; AMOUNT and NOTE open on
what the part holds; CATEGORY and HASHTAGS open with the bar empty and no list (unlike the
Edit form's ACCOUNT and CATEGORY, whose list opens on the row's own, "Stepping past ACCOUNT or
CATEGORY keeps them" above). On CATEGORY and HASHTAGS the shared suggestion list
([picker.py](../expense/tui/widgets/picker.py), `matching`) shows under the field once
something is typed, and `↑↓` move in it while it is open. CATEGORY offers the user categories
only, unlike the Edit form's list, which holds `@Pendiente`: a part left with no category is
filed under `@Pendiente`. A field is kept when you leave it, by `⏎`, `↑↓` or `⇥`, and shows in
the table row at once: an amount that is not a number, or a name that matches nothing, is not
kept, a toast says why (the Edit form's words) and the cursor stays. A field left empty clears
the amount or the note, and keeps the category and the hashtags the part holds. `⏎` on
HASHTAGS with a name typed adds that hashtag and stays for another; with nothing typed it
moves on. `⏎` on NOTE goes back to the table, the cursor on that part. `esc` goes back too,
keeping every field already left and every hashtag already added with `⏎`; only the field
being typed goes back to what it was (Question 2 A of
[expense-world-enter-and-esc.html](mockups/expense-world-enter-and-esc.html)).
**`⏎` on `+ add a part`** adds an empty part, every cell `—`, and opens its fields on AMOUNT.
A part left with nothing in it, by `esc` or `⏎` through its fields, drops again, the cursor
back on `+ add a part`.
**`⏎` on the TITLE line** opens one field below (screen 4), under the dim rule and
`TITLE · changes it on every part` (`TITLE` bold, the rest dim): `▌ TITLE` in the accent with
the input after it, opening on the title as it is. While it is open the TITLE line reads
`▌TITLE      Tottus Jockey Plaza` in the accent, bold, the `▌` in the column `TITLE` starts in
otherwise, the title as last kept, and no part is under the cursor. `⏎` keeps the title typed,
trimmed, puts it on the TITLE line and goes back to the table, the cursor on the TITLE line; `esc` goes back leaving the title as it was. An
empty title, or spaces only, is refused as on the Edit form (`_title_given` in
[_form.py](../expense/tui/screens/_form.py), one copy for both): the error toast
`Title is required.`, the field stays open and the TITLE line keeps its title (screen 5), so
a split never removes a title. `↑↓` do nothing in this one field, and there is no `⇥ Field`.
`ctrl+s` always sends every part in one `POST /transactions/{id}/split` through `run_write`
(one idempotency key), by the id of the row `s` was pressed on, each part under a fresh id,
with only what it holds: its signed `amount_cents`, `category_id`, `description`, and
`hashtag_ids` through `hashtags_to_send` with `pending_alone=False`, so a part with only the
pending hashtag sends none. Beside `parts` goes `title`, once for the line, only when the title
kept differs from the transaction's; the engine writes it onto every part, and with the key
left out every part keeps the title it has
(contract: POST /v1/transactions/{transaction_id}/split). Pressed in a part's fields or the
title's, it keeps the field being typed first (an empty title is refused there as on `⏎`)
and the table comes back. The engine decides whether the parts add up
(contract: POST /v1/transactions/{transaction_id}/split, "The total is kept"). Split, the screen
closes and the ledger reads fresh from the newest 10, cursor on row 1.
**A refused split stays under the parts** until a part or the title changes: the engine's
`CODE — message` in the error colour, one `! <key>: <words>` line per refused key with
`parts.<i>.<field>` read as `part i+1 (field)` (`amount_cents` reads `amount`, the index read
by `key_index` in [errors.py](../expense/errors.py)) and any other key as sent (`! title: …`),
each hanging under its own words (`hanging` in
[refusal.py](../expense/tui/widgets/refusal.py)), then `Nothing was split.` dim (not under a
`5xx`), then a blank line and the app's line when the reason has one (`app_lines`; "When the
engine says no" below). The amounts a `parts.<i>.amount_cents` key names turn the error colour
in the table.
`SPLIT_TOTAL_MISMATCH` (keyed `parts` and every `parts.<i>.amount_cents`, its words giving
both totals in cents), and every other refusal of the route, `ACCOUNT_ARCHIVED`,
`OPENING_BALANCE_NOT_SPLIT`, `SPLIT_LINE_PARTS_DIVERGE`, `PENDING_HASHTAG_NOT_ALONE`,
`ZERO_AMOUNT`, `INVALID_REFERENCE`, `RESERVED_CATEGORY`, `DUPLICATE_IN_REQUEST`, `OUT_OF_RANGE`,
`ID_EXISTS`, `RESERVED_NAME_HELD` and `CONCURRENT_CHANGE`, show this way, and so does `LOCKED` on `title`:
a transaction in a completed reconciliation may be split, but a changed title is refused, with
any part's refusal from the same `422`, and nothing is split (screen 6). A failure that is not
the engine's answer (the engine out of reach) shows the app's error text there instead.
`esc` clears the selection if there is one, and otherwise goes back to the screen that
opened the ledger. Title, description, amount and date stay single-row edits behind `⏎`.
No suggestions and no same-merchant spreading — [decisions.md](decisions.md) "Home is the
month".

**The pending hashtag never rides beside a real one.** The engine files a transaction with no
hashtag under its built-in pending hashtag and refuses that hashtag together with another
(`PENDING_HASHTAG_NOT_ALONE`), while a set of real hashtags replaces it on its own
(contract: "Transactions (Ledger)", "Hashtags on a transaction").
So every hashtag write sends a set naming a real hashtag without the pending one: the `⏎`
edit form, `h` on ledger rows and the LOG bar's `#tag` lines, the pending hashtag named
beside a real one included. The pending hashtag alone goes as picked, an emptied set on the
edit form sends `[]`, and a LOG bar line with no `#tag` sends no hashtags; the engine files
both under the pending hashtag. **What the screens list is what the save sends:** on the edit
form the pending hashtag leaves the `hashtags` line the moment a real hashtag is added; a
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
line with the bank's columns only (below). `d` deletes the line under the cursor after a
question (pane 3b, and "`d` is the TUI's one destructive key" below), with the line the list
already holds, so nothing is read before asking: a split transaction (`part_count` above 1)
asks the ledger's question for a split transaction and goes whole in one
`DELETE /bank-lines/{id}` (contract: DELETE /v1/bank-lines/{bank_line_id}),
a line never split asks the ledger's transaction question and goes as its one transaction
in `DELETE /transactions/{id}`.

**`⏎` in "no batch" — the Edit form on the bank's columns** (pane 2e C2 of
[expense-world-bank-lines-whole.html](mockups/expense-world-bank-lines-whole.html);
`BankLineEditFormScreen` in [edit_form.py](../expense/tui/screens/edit_form.py)). It is the
Edit form, a variant on the shared form scaffolding, and its crumb reads
`Capture & ledger ▸ Reconciliations ▸ Edit`. Over the bar, the line as the list shows it:
its title, then its signed `net_cents` and the account's currency
(`FARMACIA  ·  -100.00 PEN`). Every value comes from the line the list already holds, so
the form reads no line: the day and title off its first part, its `operation_code` and its
account. A line never split edits `date › title › operation › amount › account`, all
editable but on an archived account's line ("On an archived account's transaction the Edit
form shows the read-only lines alone" below), its amount the one part's, signed by `signed_cents` in
[formatting.py](../expense/formatting.py). A split transaction edits
`date › title › operation › account`, and under the summary stands a read-only `Parts`
section: each part's amount, signed by `signed_cents`, then a rule, then `total` and the
line's own `net_cents` (`parts_section`; the app adds nothing up), and the dim line `the
parts must add up to the total · s in the ledger splits it again to change them`. There is
no amount field there, and neither form shows category, hashtags or note: those are the
ledger's. An operation with nothing typed reads `—  (optional)`; its hint is `optional ·
the bank's operation number · empty clears it`.
`ctrl+s` saves as the Edit form does: one `PUT /transactions/{id}` on the line's first part,
through the shared write path with one idempotency key, carrying only the fields changed.
The engine writes date, title, operation and account onto every part of the line in that
write, while the amount stays the part's own
(contract: PUT /v1/transactions/{transaction_id}, "Line fields"). An emptied operation
sends `operation_code: null`, which clears the line's operation code
(contract: PUT /v1/transactions/{transaction_id}); a changed account also sends
`reconciliation_id: null` (`unassign_on_move`, as on the ledger's form). Saved, the note
reads `Saved.` and "no batch" reads its newest ten again, cursor on row 1; a row whose date
or account moved it out of the list is gone. A refusal is the engine's words in the
"Failed" note, with the line saying what to do when it has one (`format_error`), the form
still open; `esc` sends nothing and keeps the list and its cursor.

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
| ✗ | `Couldn't read the row` | a line the parser refused: never sent |

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
picker, the edit form's account field, the ledger's `b` picker, the Reconciliations
browse, the new-reconciliation form and the bank import's "Which account is this file?"
show accounts as `GET /accounts` lists them, every real account first, then every person
(contract: GET /v1/accounts). No screen sorts them. A screen that has no use for people
leaves them out and moves nothing else, and the bank import's card line stands where its
first currency leg does. The LOG bar's `$` picker, the edit forms' account field and the
ledger's `b` picker offer no archived account (`QuickAddRefs.accounts` in
[reads.py](../expense/reads.py)): the engine refuses an archived account as a transaction's
`account_id` (contract: POST /v1/accounts/{account_id}/archive). A row already on one still
shows its name, read-only on its Edit form (below).

**On an archived account's row the ledger offers no `s` and no `d`** (screen 1 A of
[expense-world-archived-account.html](mockups/expense-world-archived-account.html)). The
engine splits and deletes none of an archived account's transactions
(contract: POST /v1/accounts/{account_id}/archive), so with the cursor on one, whole ledger or
filtered from Home, `s Split` and `d Delete` leave the footer and both keys do nothing and
send nothing; on the next row of an active account or a person they are back, the footer
following the cursor. The row is drawn as any other, with nothing on it saying why, and `c`,
`b`, `h`, `⏎` and every other key stay; the engine still judges each write they send. The
ledger learns which accounts are archived from the same `GET /accounts` that gives it the
names, one read per load (`reads.load_account_index`), so an account unarchived on
Manage ▸ Accounts gets its `s` and `d` back at the ledger's next read (`r`, or any reload).
The `?` card still lists `s` and `d`, as it does while rows are selected: it lists a screen's
own keys as the screen declares them.

**On an archived account's transaction the Edit form shows the read-only lines alone**
(screen 2 B of [expense-world-archived-account.html](mockups/expense-world-archived-account.html)).
Only such a transaction's categorisation changes, and the engine refuses `amount_cents`, `date`,
`title`, `operation_code`, `account_id` and `reconciliation_id` sent even at their current value
(contract: PUT /v1/transactions/{transaction_id}, "Archived accounts"). So the `⏎` edit form
shows `date`, `title`, `amount` and `account` dimmed and marked `read-only`, as an opening
balance's locked lines, every field move skips them, and it opens on `category`; nothing on it
says why. The save sends only what changed among `category_id`, `hashtag_ids` and
`description`, and never a `reconciliation_id`, since the account never changes. A title that
is still empty may be filled once
(contract: PUT /v1/transactions/{transaction_id}, "An empty field may be filled"): it stays
editable, with its look and hint as on any row, the form opens on it, and its first value is
saved; opened again once filled, it is read-only like the rest. The "no batch" Edit form
follows the same rule on a line of an archived account, which only a list read before the
account was archived still shows: `date`, `title`, `operation`, `amount` and `account` are
read-only, but a title or operation still empty, filled once. With both set, every line is
read-only: the form still opens, on `date`, showing what the line holds, and nothing typed
lands on a line ("The bar forms' keys" below). The form learns which accounts are archived
from the `GET /accounts` it already makes for its suggestions
(`QuickAddRefs.archived_accounts` in [reads.py](../expense/reads.py)); when that read fails,
the form is as on any row and the engine judges the save ("When the engine says no" below).

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
toast, a LOG bar row, the bank import's preview, the split screen's parts) shows the engine's words whole (`CODE —
message`, then one `key: …` line per refused field; a LOG bar row the engine names reads
`key: …` for each refused field, without the code and message, "Saved" below), and for the
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
| `IN_COMPLETED_RECONCILIATION` on `transaction_id` or `bank_line_id` | `d` on the ledger | none: the engine's message already says to revert the reconciliation to draft first |
| `ACCOUNT_ARCHIVED` (a `CONFLICT` on a delete, complete, revert or `t`; a `VALIDATION_ERROR` on a save or a split) | a write sent from a screen read before its account was archived: `t` on Manage ▸ Accounts, `d` on the ledger or in "no batch", `b` on ledger rows, a save on the Edit form or the "no batch" Edit form, `ctrl+s` on the split screen, and `space`, `c` (its ending balance's save too), `u` and `d` on a reconciliation's batch screen | none: the engine's words already say to unarchive the account first, and the screen stays as after any refusal |
| `NAME_EXISTS` | a new account, person, category or hashtag; a rename on an Edit form | `That name is taken: pick another.` |
| `CAP_REACHED` | a new account, person, category or hashtag | `Delete one first.` |
| `OPERATION_CODE_EXISTS` | a transaction's account changed on its Edit form; an operation number or account changed on the "no batch" Edit form; `b` on ledger rows; a bank file | `That account already has a row with this operation number: look there for a duplicate.` |
| `CONCURRENT_CHANGE`, on a list | `d` on an account, a category, a hashtag or a reconciliation; saving the ending balance at `c` on a reconciliation's batch screen | `It changed at the same moment: press r, then try again.` |
| `CONCURRENT_CHANGE`, elsewhere | saving an opening balance, the LOG bar, the split screen, a transaction's hashtags on its Edit form or `h` on ledger rows | `It changed at the same moment: save again.` |
| `CONCURRENT_CHANGE` on `rows.<index>` | a bank file's apply, when a ledger line a file row matched changed while it ran (§2 "The import door") | `It changed while the import ran: ⏎ checks the file against the ledger again.` |
| `RESERVED_NAME_HELD` | saving an opening balance, the LOG bar, the split screen, a bank file | `One of your categories has a built-in category's name: rename it on Manage ▸ Categories, then save again.` |
| `RESERVED_NAME_HELD` on `hashtag_ids` or `hashtag_id` | a transaction's hashtags on its Edit form, `h` on ledger rows, the LOG bar; `d` on Manage ▸ Hashtags | none: one of your hashtags holds the pending hashtag's name, and the engine's message names the remedy |
| `OPENING_BALANCE_EXISTS` | saving an opening balance on the account's Edit form | `It got one meanwhile: close the form and open it again to change it.` |
| `RECONCILIATION_NOT_DRAFT` | `d` on a reconciliation's batch screen | `Press u to revert it, then d again.` |
| `OPENING_BALANCE_ACCOUNT_FIXED` (a `VALIDATION_ERROR`) | `b` on ledger rows that include an opening balance; its Edit form, should the refusal reach it | `To move an opening balance, set it on the other account's Edit form.` |
| `OPENING_BALANCE_CATEGORY_FIXED` (a `VALIDATION_ERROR`) | `c` on ledger rows that include an opening balance; its Edit form, should the refusal reach it | `An opening balance always stays in @Opening.` |
| `ENDING_BALANCE_REQUIRED` (a `VALIDATION_ERROR`) | `c` on a reconciliation's batch screen, when its ending balance was cleared elsewhere | `Press c again: the app asks for it first.` |
| `SYSTEM_NAME_FIXED` (a `VALIDATION_ERROR`) on `name` | a new name, letter case alone included, for `@Pendiente`, `@Opening` or the pending hashtag on an Edit form, should one open on it (Manage offers no `e` on them) | `Built-in names never change: press esc to leave it as it is.` |
| `RESERVED_NAME` (a `VALIDATION_ERROR`) on `name` | a new category, or a category renamed on its Edit form, named like a system category (`@Opening`, `@Pendiente`); a new hashtag, or a hashtag renamed on its Edit form, named `Pendiente` in any letter case | `That name belongs to a system row: pick another.` |
| `OPENING_BALANCE_NOT_TAGGED` (a `VALIDATION_ERROR`) on `hashtag_ids` | `h` on ledger rows that include an opening balance; its Edit form, should the refusal reach it | `Leave the opening balance out of the selection.` |
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
resources share; its key (`account_id` or `category_id`) picks the line, and the keys
`hashtag_ids` and `hashtag_id` keep the category line off `RESERVED_NAME_HELD`. The three
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
  `opening`, a date on `as of`, a name or colour on its own line); a refusal that names
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
`suggestion_list` to the picked name, the LOG bar to its staged row and the field modal to
its candidate, and `CursorOptionList` (the home menu) applies it to the finished strip,
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
picker for category / account / hashtags, `esc` clears the selection if there is one,
else goes back to the screen that opened the ledger. `s` and `d` never follow the
selection: they are off while one exists, while a bulk write runs, and on an archived
account's row (§2 "`s` splits the cursor row into parts", "On an archived account's row the
ledger offers no `s` and no `d`", "`d` is the TUI's one destructive key").
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
the **account list alone**, full height, and reads no reconciliations. The list is
`GET /accounts` as the engine gives it without `include_archived`, people left out, so an
archived account and its reconciliations are not listed until it is unarchived on
Manage ▸ Accounts. The engine lists
reconciliations one account at a time (`GET /reconciliations?account_id=`, whole, `date_start`
ascending, then creation time, oldest first (contract: "Reconciliations", "Ordering")),
so moving the account cursor costs nothing. `⏎ Its reconciliations` reads that account's
list and opens the **panel** under the accounts, halving the height, with the cursor in
it; the open account keeps an accent `▸`, and the breadcrumb grows to
`Reconciliations ▸ <account>`. An account with none says `none yet · n to create one`
inside the panel; a read that fails toasts and leaves the panel closed. Coming back from
a reconciliation re-reads that account and lands on the same row. **Keys**: `n` new
batch — for the open account, or with no panel for the account under the cursor, and once
saved the panel opens on the new one; `u` swaps the panel to the account's rows in no
batch (panel open only); `d` deletes the cursor row **in that pane only** (a no-op on the
reconciliation list, where a batch's own delete lives one screen deeper); `esc` retreats
one step — no-batch rows → the panel → the account list (`esc Close the panel`) → Home.
`u` means *revert* on the batch screen one keypress away; the overlap is deliberate.

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
`Couldn't …` note. `c` completes, after the question `Complete reconciliation?` · `Locks
amount/account/title/date on the N ticked rows.` (N the rows ticked), `u` reverts, `d`
deletes the reconciliation, `r` reads it again, `esc` goes back.
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

**The split screen's own keys** ([split.py](../expense/tui/screens/split.py)): the bar
form's keymap (`form_bindings`) with the table's keys, each shown only where it works
(`check_action`). On the table nothing is focused: `↑↓` move the cursor, `⏎` opens the
title's field or the part under the cursor, or adds one, `ctrl+x` drops the part under it
(nothing on the TITLE line or `+ add a part`), `ctrl+s` sends the split, `esc` leaves at once
with nothing sent; the footer reads `esc Cancel  ^s Split  ⏎ Edit  ^x Drop part`. In a part's
fields the input holds focus: `↑↓` walk an open suggestion list or move fields, `⏎`, `⇥` and
`shift+tab` move fields, `ctrl+s` sends, `esc` goes back to the table keeping what `⏎` added
(each hashtag added with `⏎` on HASHTAGS stays on the part), only the line being typed
dropped; the footer reads `esc Back to the parts  ^s Split  ⇥ Field`. In the title's one
field, `⏎` keeps it, `ctrl+s` sends, `esc` goes back, and the footer reads
`esc Back to the parts  ^s Split`. `esc` is two bindings, `check_action` showing one. There
is no `?`: the split screen is a bar form (`FormScreen`), and forms take no
`HelpBindingMixin`, so there is no `?` card; in the fields the input takes `?` as a character.

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
one copy for the edit form, the create/edit forms, the new-reconciliation form, Setup and the
split screen's fields, whose keys differ as "The split screen's own keys" above says):
`⏎` saves the field and moves one line on, to the next field that can change; when no field
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
The footer reads `esc Cancel  ^s Save  ⇥ Field` (`Create` on a create form):
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
- **No request body carries `line_code`, at any depth** — the engine mints it and refuses
  it on every write (contract: "Transactions (Ledger)", "Bank lines"). The autouse
  `_no_line_code_in_requests` in [conftest.py](../tests/unit/conftest.py) fails any unit
  test whose request holds it, even when the app swallows the refusal: it checks
  `httpx.Client.send` (respx), `FakeClient.post`/`.put` and any function a test puts in
  their place. [test_no_line_code.py](../tests/unit/test_no_line_code.py) trips it. Any
  other class in `tests/unit` with its own `post` or `put` is a fake engine: it subclasses
  `FakeClient` or calls `helpers.refuse_line_code` in each, as
  `test_every_fake_engine_refuses_line_code` in
  [test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py) checks.
- **The typed surface is pinned** by
  [test_command_surface.py](../tests/unit/test_command_surface.py) (CLAUDE.md "Testing
  conventions").

**Known, accepted:** a screen load may open several short-lived clients (Transactions:
the page and three name maps; the bulk pickers' reference lists load once, on the first
bulk key) — harmless on loopback.
