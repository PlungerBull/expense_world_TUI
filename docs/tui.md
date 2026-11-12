# The TUI — `expense`

What the Textual app **is**, in present tense. `expense`, run alone, opens it: the
one surface of this client ([decisions.md](decisions.md) "The TUI is the only
surface"), over the shared fetch/write layer; it implements **zero** business logic
(repo thin-wrapper rule).

Companions: [commands.md](commands.md) (the typed surface: the launch, the sheet
import and the settings file) ·
[runtime.md](runtime.md) (read/write semantics, which apply to the TUI
unchanged) · [decisions.md](decisions.md) (why the calls below went the way they did).
Every screen is mocked before it is built ([CLAUDE.md](../CLAUDE.md) "Mock every screen
before building it — every time").

---

## 1. Architecture

```
expense/tui/
  app.py            # ExpenseApp: screen stack, global bindings, launch
  app.tcss          # Textual CSS — layout + the structural ANSI fills (§3)
  theme.py          # the ANSI Theme + PALETTE, the colours Rich content takes
  dropped.py        # dropped_bank_files() — is the LOG bar's line dropped bank files?
  widgets/
    header.py       # Breadcrumb + rate_alert(), the `!` both headers share
    cells.py        # cell renderers: swatch, signed amount, code, null glyphs
    windowed.py     # CURSOR_STYLE + WindowedList, the window/cursor/page arithmetic
    cursor_list.py  # CursorList, list_table(), list_cell(), waits_for_a_row(), CursorOptionList (home menu)
    checklist.py    # CheckList — a statement's bank lines, one per row
    footer.py       # FittingFooter — every screen's footer (§5)
    picker.py       # suggestion_list() + matching() — the name list under a bar
    refusal.py      # hanging(), under_itself(), warning_note(), toast(), as_markup(), run_stopped()
    parts_table.py  # the Edit form's parts table, read-only lines, refused-save lines
  screens/
    _base.py        # SectionScreen, EngineWriteMixin, ResourceListScreen, NewestReadMixin,
                    # call_while_attached, keymap mixins
    _form.py        # FormScreen + form_bindings — every bar form's scaffolding
    _growing.py     # GrowingRead — a list that grows by cursor
    help.py         # HelpModal — the `?` card (§4)
    home.py         # Home: four months, balances today, the menu
    transactions.py # the ledger, whole or filtered, and its bulk keys
    bulk_pick.py    # BulkPickScreen — the pick `c`/`b`/`h`/`m` open
    accounts.py  categories.py  hashtags.py   # Manage lists
    statements.py   # Statements: browse, new statement, a statement's screen, flagged lines
    system.py       # Config / Auth screens
    setup.py        # SetupScreen — first-time setup
    edit_form.py    # the Edit form, ledger and "no statement" (BankLineEditFormScreen)
    log_bar.py      # the LOG bar — what `+` opens
    bank_import.py  # the import door: a dropped bank file → account → preview → result
    statement_upload.py # a dropped statement PDF → account → preview → month closed
    create_forms.py # BarFormScreen + the New/Edit account, category, hashtag forms
    modals.py       # ConfirmModal, PickModal, PromptModal, AmountPromptModal, QuestionModal, …
```

**The fetch/draw split is the anti-duplication guardrail.** Every engine read is a
pure `fetch_*(cfg, …) -> dict` the screens call; a screen never reimplements one. The
shared homes are listed in [CLAUDE.md](../CLAUDE.md) "One copy of everything shared";
none of them is under `expense/commands/`, which holds only what `expense import sheet`
alone uses.

**One reader for every typed amount.** `parse_amount` in
[quickadd/money.py](../expense/quickadd/money.py) reads the amount on the LOG bar, the Edit
form, an account's opening balance, a new statement's two balances and the statement's
`Starting balance first` and `Ending balance first` boxes, in the session's format
([number_format.py](../expense/number_format.py)): at launch the account's `number_format`
setting, else the machine's region (`launch_format` in [region.py](../expense/region.py),
the setting read by `reads.fetch_number_format`). System ▸ Auth & profile shows it, and `f`
picks a format or *Follow this Mac* (`AuthScreen.action_number_format` in
[system.py](../expense/tui/screens/system.py)); a screen already drawn takes it at its next load. The
docstring of `parse_amount` holds the rule. An amount it cannot read is refused, never guessed, and nothing is
sent: the Edit form says `can't read this amount: amounts are 1,234.56`, every other field
ends its note `Amounts are 1,234.56.`, and the cursor stays (the box stays open). On the LOG
bar `↵` refuses the line, naming the first signed number it couldn't read, as typed:
`can't read -1,5 as an amount: amounts are 1,234.56`. A line with no signed number is refused
with `the line has no amount — a number needs a sign to be one`. A plain number is read at
any size and sent as whole cents; the app has no bound, so the engine's `OUT_OF_RANGE` shows
in its words on the line or file row (contract: "Money amounts"). A spreadsheet's cells
are the engine's to read: a bank download's (§2 "The import door") and the owner's sheet's
([commands.md](commands.md) "`expense import sheet`").

**Async / workers.** Textual runs on asyncio; the engine client is synchronous, and
stays that way. It is called inside a Textual worker (`@work(thread=True)`) so the UI
never blocks. Read screens subclass `SectionScreen` and override `fetch()` (runs in
the worker) + `build(data)`; writes go through `EngineWriteMixin.run_write`, one write in
flight and an error dropping the queued rest ([decisions.md](decisions.md) "TUI writes:
FIFO queue in EngineWriteMixin, error drops the queue").

**A thread worker hands back through `call_while_attached`.** A thread worker cannot be
stopped, so a read still in flight when its screen is popped or the app quits still
lands, and painting it then queries widgets already taken down (`NoMatches`).
`call_while_attached` in [_base.py](../expense/tui/screens/_base.py) runs the hand-back on
the UI thread only while its node is still in the app, and drops it otherwise; a coroutine
hand-back asks `still_attached` again after every await
([test_tui_leaving_mid_draw.py](../tests/unit/test_tui_leaving_mid_draw.py)). Every thread worker in
`expense/tui/` hands back this way except the app's rate check, which has no screen.

**A write answered after its screen has left still says how it ended** when it carries a
`LeftBehind` ([_base.py](../expense/tui/screens/_base.py)); one without is dropped with its
screen. The ending shows on the app: success as the screen's own toast, a refusal as an error
toast of 10 seconds titled with what was not done, the screen's words for it under the title.
Every write queued behind it is still sent and shown the same way, a refusal stopping none
([decisions.md](decisions.md) "A save you left still says how it ended").

The title reads `Not <what did not happen> · <what it was>`, the thing named as its screen
showed it: by kind and name (`Not archived · Account BCP`, `Person` for a person's account;
`not_done_line`), a transaction by title and amount, as its list draws them
(`not_done_transaction_line`), or alone where there is nothing to name (`Not provisioned`).
The writes that carry one, each naming its words where it is sent:

- **Manage ▸ Accounts' `a`, `t`, `c` and `x`, every Manage list's `d`, `d` on the ledger, the
  "no statement" list, the flagged lines and the leftover lines, and `b` and `f` on Auth & profile.**
- **The New and Edit forms of Manage ▸ Hashtags and Categories, New account and the account
  Edit form:** `Not created · Category Ropa`, `Not saved · Hashtag #viaje`, `Not saved ·
  Account BCP-5678` (the name its list showed before the edit; `Person` for a person); a
  refusal ends, dim, `Nothing was saved: open it again to fix it.`, except under a 5xx or when
  the engine did not answer (`open_it_again`).
- **A line's Edit forms** (`EditFormScreen`, `BankLineEditFormScreen`): `Not saved · <title> ·
  <amount>`; success says `Saved.` or `Saved. It left its statement.`, as the form would
  (`saved_words`); a refusal shows the words the form shows under its parts, ending with the
  same dim line (the same rule).
- **A statement's writes:** New statement (`Not created · Statement <name>`, the name as
  typed; a refusal ends with the same dim line, by the same rule), a tick (`Not ticked · <title> · <amount>`, `Not unticked · …`; a tick that lands
  shows nothing), `u` (`Not reverted · Statement <name>`), `d` (`Not deleted · Statement
  <name>`) and `c`, which opens no screen by itself. A complete that went through is
  `Statement completed · <name>` with the engine's notes (`close_notes`, the lines the head
  shows), then, when the engine's count of the review list read after the answer is above
  zero, `⚑ 3 lines flagged for review: open the statement and press f.`; with neither, the
  plain `Statement completed.`; refused, `Not completed · Statement <name>`. The balances `c`
  asks for first: saved, `Balances saved · <name>` ending, dim, `The statement is not
  completed: open it and press c.`, and the question to complete never shows; refused, `Not
  saved · Statement <name>` (`StatementScreen._say_after_leaving`).
- **The ledger's bulk edit:** "The ledger's bulk edit reads its refused rows the same way"
  (§2).

When such a write ends while the screen shown is the one it changed, that screen reads
again: a Manage form's list from its first page, cursor on row 1, after a save that landed or
whose ending is not known (a 5xx, no answer: `may_have_landed`), never after a clear refusal;
the screen that opened a line's Edit form, as after any save; the Statements
screen, a new statement opening that account's panel on it, and after the last tick too,
however it ended.

**Quitting asks while saves are still being sent.** `ctrl+q`, or `q` on Home, with a save on
any screen, a left one included, sent and not answered or waiting to be sent, asks first
through the confirm modal: `2 saves are still being sent. Quit anyway?` over `If you quit
now, no screen will tell you whether they were saved.` (`1 save … it was saved.`). Only `y`
quits; any other answer leaves the app running and each save still ends as above. With none,
quitting is immediate. What counts, a save of several writes (the
LOG bar's `ctrl+s` batch, a ledger bulk key, an import's apply) once, is `pending_writes` and
`counted_save` in [_base.py](../expense/tui/screens/_base.py); a screen that finishes under
the question closes once it is answered (`after_quit_question` in
[app.py](../expense/tui/app.py)).

**A read a newer one replaced paints nothing.** Where one screen's reads can overlap (a
statement's screen, the flagged lines, the two growing lists), only the newest read's answer
paints, counts or toasts; an older one is dropped on the UI thread (`NewestReadMixin` in
[_base.py](../expense/tui/screens/_base.py); why: [decisions.md](decisions.md) "The app holds
its settings from launch, and only the newest read hands back").

**Invariant: `build()` runs on the UI thread and must never do HTTP.** Where a render
needs resolved names, resolve them in `fetch()` and hand `build()` precomputed cells —
`TransactionsScreen` is the worked example.

**Name resolution is live HTTP and fails silently by design.**
`load_account_name_map` / `load_category_name_map` / `load_hashtag_name_map` each open
their own client and page the reference list; on **any** failure they return `{}` and
renderers fall back to 8-char short ids. `load_account_index`, what the ledger reads, is the
same accounts read giving the names and the archived ids together; on a failure it has
neither, so no `d` shows in the ledger's footer. No toast, no error: "my tables show hex
ids" means the engine is rejecting reference-list reads (auth/config), never data loss.
Every call site must be inside a worker thread.

### The header rate alert

Every header carries a `!` when today has no exchange rate of its own — every
home-currency figure on screen is priced at an older day's rate. It has no grace period,
so it also shows on an ordinary morning before the engine's fetch job has run.

- **No dedicated engine surface.** `GET /exchange-rates` returns the day asked about
  (`date`) and the day it used (`rate_date`); the signal is `rate_date < date`
  (`reads.rate_is_stale`), and `fetch_rate_staleness` adds the `404` case (no rate at all →
  stale). There is no screen behind the mark.
- **App-owned, fetched once per launch** into `ExpenseApp.rate_stale` (`True` / `False` /
  `None`); a screen pushed later reads it, and every screen already on the stack is repainted.
- **The `!` always shows.** A trail wider than the crumb is cut at its end with `…`, to the
  crumb's own width, so the alert after it is never pushed off.
- **`None` renders nothing** (offline, unconfigured, pre-fetch, an unexpected body).
  Warning-coloured, not error: a carried-forward rate is the engine's designed fallback.
- Guard: [tests/unit/test_rate_alert.py](../tests/unit/test_rate_alert.py).

---

## 2. Screens

**Setup comes first when there is nothing to connect with.** With no settings file, or one
that cannot be read (`config.load_usable`), `launch` in [app.py](../expense/tui/app.py) opens
the app with `SetupScreen` ([setup.py](../expense/tui/screens/setup.py)) pushed over Home;
its docstring holds the questions and the two calls, its footer the keys. **Nothing is written
to the settings file until setup is done**: the engine has answered `/auth/me` with 200, or
the profile was created. `esc Quit` leaves at once, nothing saved, no quit question; while the
engine is being asked no key does anything. A refused profile shows the engine's words without
the shared text's hints, which point at System screens Setup cannot reach. Changing the
address or key later is System ▸ Config.

**Home is four months of the ledger.** [home.py](../expense/tui/screens/home.py)'s docstring
holds the sections, the filter each `⏎` opens and the window keys, and `?` lists the keys.
The screens (LEDGER: Transactions · Statements; MANAGE: Accounts · Categories · Hashtags;
SYSTEM: Config · Auth & profile) are listed before the reads land and after they fail, where a
failure is one dim row with the reason and `r` re-reads; `_SCREENS` maps entry id to screen.
The first month to land puts the cursor on the first category, later re-reads leave it.
Aggregates are nullable: a group holding an unconvertible row reads `3 unrated`, never a
partial total, and opening balances are excluded engine-side. Logging a transaction is `+`,
not a menu row.

**The filtered ledger is the categorising pass.** `⏎` on a Home row pushes
[transactions.py](../expense/tui/screens/transactions.py) with a `LedgerFilter`; its docstring
holds the keys, the writes and the receipt, and `?` lists the keys. **Cur** is the row's own
`currency_code` (empty for a row naming none) and **Account** names the account alone. **A date
a screen shows for a transaction or a bank-line part is its engine `day`** (`format_day`), never
the first ten characters of `date`, an instant in UTC; a file row, a `day_mismatches` day and a
statement's period show their own dates (contract: GET /v1/transactions).

`b` sends `account_id` alone, whatever the account holds: a row whose currency the account
lacks moves to the account's only currency, the amount as it is, no conversion; the engine
refuses a row when the account holds several, none the row's (`CURRENCY_NOT_HELD`), while the
other rows go (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction"). `m`
sends `currency_code` alone, the row stays on its account, and the app filters no row
beforehand. A refused row is named by its number and stays selected; the one refusal that
stops the run is `SETTINGS_MISSING` ([runtime.md](runtime.md) "Bulk writes").

**The bulk pick is a full screen** ([bulk_pick.py](../expense/tui/screens/bulk_pick.py)), not
a pop-up: it carries rows. Its docstring holds the layout, the hints and the picks; its footer
is `esc Cancel` alone. `ACCOUNT` lists one row per account, its name alone
(`QuickAddRefs.quickadd_accounts`); `CURRENCY` every currency the accounts hold, once each.

**`⏎` and `s` open the Edit form** ([edit_form.py](../expense/tui/screens/edit_form.py)); its
docstring holds the layout, the walk through the lines, what is read-only, the one save and
its answer, and the footer is the key list. Until its reads are in it takes nothing typed; a
failed read says why in a toast and saves nothing. No suggestions and no same-merchant
spreading — [decisions.md](decisions.md) "Home is the month".

**Stepping past ACCOUNT, CURRENCY or CATEGORY keeps them.** The lines open with the bar empty
and the highlight on the line's own value, so `⏎` with nothing typed keeps it, and `⏎` on every
line and then `ctrl+s` send nothing and say `No changes to save.` A value the list does not
hold leaves the highlight on the first entry, which `⏎` then takes. CATEGORY's list is the
ledger's `c` list (`pickable_categories` in [reads.py](../expense/reads.py)): `@Pendiente` in
it, `@Opening` never. The "no statement" form works the same.
**Stepping past COLOR keeps it** on the Edit screens of Manage ▸ Categories and Manage ▸
Accounts. The line opens with the bar empty and the highlight on the row's own swatch, so `⏎`
with nothing typed keeps it and the summary goes on showing it; typing filters and highlights
the first match, `↑↓` choose another, and a bar emptied again puts the highlight back on the
row's own. An account with no colour opens on nothing, and `⏎` skips the line (`—
(optional)`). A colour no swatch shows (the engine's own, on a row created with none) highlights
nothing and `⏎` keeps it, on a category too, where COLOR is required; the summary shows it as
its hex. The save sends `color` only when another swatch was picked, so `⏎` down every line
saves the name alone and the engine keeps the colour (`_edit_payload` in
[create_forms.py](../expense/tui/screens/create_forms.py)). On New account and New category
COLOR is optional: while it is empty no swatch is highlighted, typing or `↑↓` highlights one
and `⏎` picks it, and a skipped colour is left out of the body, never sent as null, so the
engine gives its default (contract: POST /v1/categories). Edit category keeps it required, so
a `PUT` never sends null.

**A move takes a row out of its statement.** The engine wants the assignment said on an
account change, so `b` and the Edit form send `statement_id: null` for a row whose account or
currency changes, and a currency move alone keeps the statement (`unassign_on_move` in
[edit_form.py](../expense/tui/screens/edit_form.py) holds the rule and its citations). The
receipt counts what the engine says moved and left (`moved_parts`): `3 rows → Caja Chica · 2
left their statement`; a move that changes nothing shows no receipt. The form sends no `null`
except `operation_code` and that `statement_id`; an emptied note goes as `description: ""`
(contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place").

**A date the form can't read is refused at `⏎`.** On DATE, on both Edit forms, `⏎` checks the
bar with the reader the save uses (`is_readable_date` in [dates.py](../expense/dates.py)) and
notes `Date: use YYYY-MM-DD.` for anything else: the bar keeps what was typed, the cursor stays
and the line keeps its value, so a `ctrl+s` after it never sends the unread date.

**An opening balance stays on its account and in @Opening.** The engine refuses to move such a
row to another account or category, `@Pendiente` included (contract: PUT
/v1/transactions/{transaction_id}, "Opening balances stay put"), gives it no hashtag, not even
the pending one (contract: PUT /v1/transactions/{transaction_id}), and keeps its bank line's one
part (contract: PUT /v1/bank-lines/{bank_line_id}, "A line holding an opening balance keeps its
parts"). The Edit form reads this from `edit_limits`; `b`, `c`, `h` and `m` send such a row like
any other, the engine refuses it, the other rows go and it stays selected. The LOG bar cannot
name @Opening.

**A split transaction says what reaches every part.** The engine writes a line's date, title,
operation, account and currency onto every part, while amount, category, hashtags and note stay
each part's own (contract: "Transactions (Ledger)", "Bank lines"); with two parts or more the
hint under the bar adds `· changes every part of the transaction` on those lines. In the
ledger's bulk keys `c` and `h` change only the selected parts, `b` on one part moves the whole
transaction, every part leaving its statement, and `m` moves every part to the currency, each
keeping its statement (contract: PUT /v1/transactions/{transaction_id}, "Line fields"). One
`PUT` per selected row, nothing fanned out; with every part selected a later `PUT` finds the
line already moved and is accepted as it is, since it carries no `version`. `b` and `m` count
the parts the engine says moved, `c` and `h` the rows they wrote.

**A refused save stays under the parts** until something changes (`refusal_lines`).
`SPLIT_TOTAL_MISMATCH` is keyed `parts`, whose words give both totals in cents, and every
`parts.<i>.amount_cents` says only that the parts must add up to the line's total (contract: PUT
/v1/bank-lines/{bank_line_id}, "The total"). **What is read-only is the line's `edit_limits`,
and nothing else**; the app keeps no copy of the engine's locking rules (contract: GET
/v1/bank-lines/{bank_line_id}, "Response fields").

**The pending hashtag never rides beside a real one.** The engine refuses it together with
another hashtag (`PENDING_HASHTAG_NOT_ALONE`) and replaces it when a real set is written
(contract: "Transactions (Ledger)", "Hashtags on a transaction"). Every hashtag write sends a
set without it beside a real one, and the screens list what the save sends: a part's cell never
shows it, a LOG bar line with no `#tag` reads `#Pendiente`. One helper does both,
`hashtags_to_send` in [reads.py](../expense/reads.py).

**`u` on the Statements browse — the account's bank lines in no statement.** The panel swaps:
the open account's statements give way to its bank lines in no statement, any day, every
currency together (`account_id` and `unreconciled=true`) (contract: GET /v1/bank-lines,
"Filters"), through `fetch_bank_lines` in [reads.py](../expense/reads.py); `u` works only while
an account's panel is open. Why not a filtered ledger: [decisions.md](decisions.md) "Rows in no
statement live in the Statements view, not in a filtered ledger". The list is oldest first
(contract: GET /v1/bank-lines, "Ordering"), grows like the ledger (§5, `GrowingRead`), and M is
`GET /bank-lines/count`, a split transaction counted once (contract: GET /v1/bank-lines/count);
a count that cannot be read fails the pane. `r`, an edit and a delete start again from the
oldest ten. The **`!` flag is a hint, not a ruling** (`unfiled_rows` in
[statements.py](../expense/tui/screens/statements.py)); the footer is the key list
(`_UNFILED_FOOTER`). `⏎` opens `BankLineEditFormScreen` from the line the list holds, and an
emptied OPERATION sends `operation_code: null` (contract: PUT /v1/bank-lines/{bank_line_id},
"Body"). `d` asks with the line the list holds ("`d` is the TUI's one destructive key" below):
a split transaction goes whole in one `DELETE /bank-lines/{id}` (contract: DELETE
/v1/bank-lines/{bank_line_id}), a line never split as its one transaction.

**The import door — a dropped bank file into the ledger**
([bank_import.py](../expense/tui/screens/bank_import.py)).
The app sends the bank's download whole and reads no cell of it: the engine reads the file,
numbers its rows as the spreadsheet does, matches them against the ledger and refuses what it
cannot take (contract: POST /v1/transactions/import). Every row of the file goes in, whatever
its date. **Export the download with an explicit date range covering everything since the
last import, never the bank's default view:** BCP's current-account default is the last 20
movements, about twelve days on `BCP PEN`, nothing can detect rows a file does not contain,
and the month's statement is the only backstop.

`↵` on the LOG bar's dropped files (§4 "A dropped bank file") reads every file's bytes at
once, before any screen opens, through `read_file` in
[flow.py](../expense/bank_import/flow.py). A file that cannot be read from disk (gone, or not
readable) keeps the bar where it is: the hint reads
`can't read the file · File not found: <path>` (or
`can't read the file · Could not open <path>: <why>`), its first words in the error colour, the
footer is `esc Cancel` alone, nothing is sent, and the next keystroke clears it. With several
files dropped, the hint names the first such file (`<name> · can't read the file · …`) and none
of them starts. Otherwise each file, in drop order, goes through three full screens that replace
one another above the LOG bar: a download through the three below, a statement PDF through the
statement upload's own three ("A statement PDF closes its month" below):

| Screen | Shows | Keys |
|---|---|---|
| **Which account is this file?** | the file's name dim beside the question; every live bank account once, in the engine's order, named by the account, its currencies its own, the account's `currencies` in the engine's order (contract: "Bank Accounts", "`currencies`"): an account holding both is one line (`VISA Infinite Sapphire   PEN + USD`); archived accounts left out. `account_picks` in [flow.py](../expense/bank_import/flow.py) reads the one accounts list alone. Asked every time; nothing is remembered | `esc Cancel  ⏎ Pick  ↑↓ Move` |
| **Preview · <account> · nothing written yet** | the engine's dry run as one table, `#  date  title  amount  ✓  reason` (the mark's column has no heading), one row per row the engine read, numbered by its spreadsheet row (the first data row is 2), the amount signed by `signed_cents`, a row with no title showing `(untitled)`; on an account holding two currencies, `cur` after the amount: the row's own `currency_code`. Each row's mark and reason (below); `… N more · pgdn` when the rows outrun the screen; then the counts (below), and under them the days where the file and the ledger disagree (below) | `⏎ Import 9 rows` (with nothing new: below), `pgdn`/`pgup` (hinted in the body, not the footer), `esc Cancel` |
| **✓ 9 rows imported · <account>** | `new ones under @Pendiente and #Pendiente` dim on the same line, then the counts in the past tense (below): no table and no days | `⏎ Home` (`⏎ Next file` while a file follows), `esc Back` |

Picking an account sends its id as `account_id`; the engine files each row under the currency the
file names for it, `S/` or `$` (contract: POST /v1/transactions/import, "Accounts"). A row in a currency
the account does not hold is refused, `CURRENCY_NOT_HELD` on `rows.<row>.account_id`, and the
engine's words show under the preview. The request is
exactly `dry_run`, `account_id` and `file`, the file's bytes in standard base64
(`request_body` in [engine.py](../expense/bank_import/engine.py)).

**Each row's mark and reason** come from the engine's `outcome`, never from the reason's
words (`row_verdict` and `preview_line` in [engine.py](../expense/bank_import/engine.py)).
`✓` (success colour) means the row is in the ledger after the import, `✗` (error colour, bold)
that it is left out, `·` (dim) a row of `0`:

| Mark | Reason | When |
|---|---|---|
| ✓ | `New` (success colour) | the engine's `new`: created on `⏎` |
| ✓ | `Already in the ledger` (dim) | `matched`, and the apply writes nothing onto its line |
| ✓ | `Modified existing transaction` | `matched`, and the apply writes the file's operation number onto the line (`backfill_code`), the bank's title (`retitled`), or moves the line to the bank's day (`redated`) |
| ✗ | `Not moved: <statement> is completed` | `matched`, and a completed statement stops the move to the bank's day (`redate_blocked_by`), whatever else the apply writes |
| ✗ | `Closed period` | the engine's `sealed`: on a sealed day, never created |
| · | `Skipped: amount 0` (dim) | the engine's `skipped`: a row of `0`, never matched or created |

Every `✗` reason is in the warning style (`PALETTE.warning`). The answer carries the stopping
statement's id only, so the preview's worker reads each distinct one once by its id
(`statement_names` in [flow.py](../expense/bank_import/flow.py)), never a list of statements
and never while drawing
(contract: GET /v1/statements/{statement_id}).
When a read fails, its rows read `Not moved: its statement is completed`, the other ids are
still read, and a dim `! could not read the statements' names: <why>` sits under the
counts with the first failure's reason.

**The counts** under the table: `14 rows · 5 new · 6 in the ledger · 1 moves to the bank's day ·
1 takes the bank's title`, the moved and title counts only when not zero; then, on a line of
its own under the first count, `1 closed · 1 skipped`, each only when not zero, the line only
when one is. After importing they read in the past tense: `1 moved to the bank's day`,
`1 took the bank's title`. Every count on the preview and the result, and the count in
`⏎ Import N rows`, is the engine's: its `counts` (`new`, `matched`, `sealed`, `skipped`,
`retitled`, `redated`), and its rows for the total. The apply's answer is read for its counts
alone.

**The days where the file and the ledger disagree** are the engine's `day_mismatches`: a day is
reported when its file total and its ledger total after the import differ, or when it holds a
ledger line no file row claimed, so a day with equal totals can be one
(contract: POST /v1/transactions/import). Each names the file rows it found in no ledger line
(`unmatched_rows`, by spreadsheet row) and the ledger lines no file row claimed
(`unclaimed_lines`, each with its `parts`, a split transaction being one entry with every
part). The preview takes them as they come (`day_mismatches` in
[engine.py](../expense/bank_import/engine.py)) and reads no transaction to fill them. Each part
is its own row, the transaction's title and the part's own amount, signed by `signed_cents`;
nothing adds parts up, and every total is the engine's.

They show **on the preview only**, under the counts: `! 3 days where the file and the ledger
disagree`, then each day as `2026-09-12   file -42.90 · ledger after import -84.90`, and under
it its rows: a file row as `row 4   FARMACIA CENTRAL  -42.90   in the file, not found`, a
ledger part as `Farmacia  -42.00   in the ledger, not in the file`. It is a report only: nothing on
it changes what `⏎` writes. On a file of an account holding two currencies, each day
names its account and its own `currency_code`: `2026-09-12 · BCP Signature · USD`. A line the
import moves to the bank's day counts on that day, so the move leaves no day disagreeing
(contract: POST /v1/transactions/import). A skipped row plays no part in the days.

The upload does nothing to a ledger row no file row claimed: it removes nothing and asks
nothing. Such a row stays out of that month's statement, where it is deleted.

A preview with nothing new keeps the table and the counts and adds dim `nothing to import`.
On the last (or only) file `⏎` does nothing and the footer is `esc Back`. With a file still
to come the footer is `esc Cancel both` / `esc Cancel all` (below) and `⏎ Next file`, and
`⏎` opens the next file's account list, writing nothing. `⏎` on a preview with new rows
sends the same file on the same account as the apply — one `POST /transactions/import`
with `dry_run: false` through the shared HTTP client (its idempotency key covers a retry).

**A refused file** shows on the preview, under its title, in the engine's words
(`refusal_lines` and `failure_lines` in [bank_import.py](../expense/tui/screens/bank_import.py)):
`CODE — message`, then one `!` line per refused key in the engine's order, then
`Nothing was written.` dim. The engine names a refused row by its key, `rows.<row>` or
`rows.<row>.<field>` by spreadsheet row. When the row's words begin `Row <row>:`, as every
refusal made before anything is read from the ledger does, a `FUTURE_DATE` included
(contract: POST /v1/transactions/import, "Rejected up front with `422`"), its line is `! `
and the engine's words alone; when they do not (a `409`'s words need not begin so), the line
keeps the key, `! rows.<row>.<field>: <words>`, so the row is never lost. Any other key
(`file`, refused whole: not a download, unreadable, empty, over 500 rows; `account_id`) shows
as `! <key>: <words>` too (`names_its_row` in [errors.py](../expense/errors.py)). The app's
line for the refusal, when "When the engine says no" gives one, follows after a blank line. The
footer is `esc Back` on the last (or only) file, and keeps `esc Cancel both` / `esc Cancel all`
while files follow; `⏎` sends nothing more. A failure that names no key (a `5xx`, the engine
unreachable) is the shared error text, whole. Every failure of a download is also a `Failed`
toast with the shared error text.

**A ledger line changed while the import ran**: the apply's `409 CONFLICT` with
`CONCURRENT_CHANGE` on a `rows.<row>` key means something else split, deleted or changed a
ledger line a file row matched, and nothing was written
(contract: POST /v1/transactions/import, "Concurrency"). The preview shows the engine's words
as a refused file does, and under a blank line
`It changed while the import ran: ⏎ checks the file against the ledger again.`; the footer
is `esc Cancel  ⏎ Preview again`. `⏎` runs the dry run again on the ledger as it is now, and the
footer returns to `⏎ Import N rows`: nothing is sent again without a fresh preview.

**Several files**, of either kind, go one by one in drop order, each its own way — a download
through the import door, a PDF through the statement upload (`first_screen` in
[bank_import.py](../expense/tui/screens/bank_import.py)), each asking its account — in one
run. The crumb carries `Import ▸ file 1 of 2` (`Upload a statement ▸ file 2 of 2` on a PDF's
account list, `Upload ▸ file 2 of 2` on its preview and result) and each file's name sits
beside the question. `esc` before a file is written cancels it and every file after it, and
its word counts the files still to come, this one included: `esc Cancel all` (three or more),
`esc Cancel both` (two), `esc Cancel` (this one alone — `esc Back` on a nothing-new or refused
preview). File 1 of 2 says `Cancel both`, file 2 of 2 `Cancel`, file 2 of 3 `Cancel both`. A
file already imported stays imported, and `⏎ Next file` follows each written file. The two
previews share their failure, `⏎ Preview again` and `esc` steps (`PreviewScreen`), and the two
screens after an apply their `⏎` and `esc` (`ResultScreen`). **`esc`** on any import screen
lands on the LOG bar with the bar cleared and the staged rows as they were; a row lifted for
editing goes back unchanged when the drop is imported. `⏎ Home` leaves the bar for Home,
through the bar's discard question when rows are staged and unwritten, and Home reads afresh:
this month's window, every category folded, the cursor on the first category
(`HomeScreen.start_fresh`).

**The import screens' keys.** `⏎ Import N rows` on the preview is the one key on an import
screen that changes data (`⏎ Close <name>` on a statement PDF's), named in the footer with
what it writes. There is no `r`: each screen reads once, when it opens, `⏎ Preview again`
reads the dry run afresh, and dropping the file on the LOG bar again reads everything afresh.
There is no `?`: they do not take `HelpBindingMixin`, so the footer is their whole key list.

**A statement PDF closes its month**
([statement_upload.py](../expense/tui/screens/statement_upload.py)). A `.pdf` dropped on the
LOG bar (§4 "A dropped bank file") is a month's statement: the app sends it whole and reads
nothing in it, and the engine reads the paper, matches each of its rows to a ledger line,
creates the lines the ledger lacks, takes out of the month's open statement the lines the
paper does not print, puts every line in the paper's order and completes the statement, the
account's, every currency the paper covers together (on a card, its soles and its dollars),
creating it or filling its open draft
(contract: POST /v1/statements/import). The request is the download's (`request_body` in
[engine.py](../expense/bank_import/engine.py)), sent by `statement_call` in
[flow.py](../expense/bank_import/flow.py) to `POST /statements/import`; the answer reads
through [statement.py](../expense/bank_import/statement.py). The account is the one you pick: the
engine never picks it by the number the paper prints
(contract: POST /v1/statements/import, "Accounts"), and the app matches, adds up and guesses
nothing. Its three full screens replace one another above the LOG bar, as a download's do:

| Screen | Shows | Keys |
|---|---|---|
| **Which account is this statement?** | crumb `Upload a statement`; the file's name dim beside the question; the download's account list ("Which account is this file?" above), an account with no statement code included (the engine refuses it in its words when picked). A dry run refused for the account's number (`NUMBER_REASONS` in [statement_upload.py](../expense/tui/screens/statement_upload.py)) writes nothing and returns here, the cursor on the account picked and the "Failed" note carrying the engine's words (contract: POST /v1/statements/import, "The numbers the paper prints must fit the account's") | `esc Cancel  ⏎ Pick  ↑↓ Move` |
| **Preview · <account> · nothing written yet** | crumb `Capture & ledger ▸ Upload ▸ <file>`; the account is its name, with its currencies when it holds two (`BCP Signature PEN + USD`). Under the title the statement's `name · date_start → date_end ·` and, dim, `a new statement` (the answer's `creates`) or `a draft, filled from the paper` (it fills an open draft); then `begin  end` dim and one line per currency the answer's `balances` holds, its code and the paper's balances, in the engine's order, none for a currency the paper does not cover (contract: POST /v1/statements/import, "Which currencies the statement covers"). Under them each currency's `warnings` as `⚠ USD: <sentence>` in the warning colour, the balances' first and then those of `not_covered` (the account's currencies the paper holds no balances for), in the engine's order. Then the table `#  date  title  amount  cur`, one row per row of the paper in its order, numbered by its `place`, `cur` only on a paper with two balances (a card's), the row's own `currency_code`; a taken-out line shows its own `currency_code`; each row's mark and reason (below), and after a card's undated line (`fee`) dim `· a fee, dated the last day`; after a matched row whose ledger line is one day off it and moves to the row's day on `⏎` (`redated`), dim `· day moved`, no old day, no count (contract: POST /v1/statements/import, "The bank's day wins"); `… N more · pgdn` when the rows outrun the screen. Then `Taken out · in the statement, not on the paper; they stay in the ledger` and each line taken out under the table's columns (`taken_out`), left out when none is; then `⚑ Will be flagged · in no statement, on the last day, which stays open until the next month closes` (warning colour) and the lines the close will flag, each under the table's columns, in the engine's order: every balance's `review_lines`, then every `not_covered` entry's, each id once (a line taken out may show in both blocks), left out with its count when none is named (contract: POST /v1/statements/import, "Response"); then the counts (below), and dim `new ones go under @Pendiente and #Pendiente` while a row is new | `⏎ Close <name>`, `pgdn`/`pgup` (hinted in the body), `esc Cancel` |
| **✓ <name> closed · <account>** | `new ones under @Pendiente and #Pendiente` dim on the same line while a line was created; the counts in the past tense; and, when the engine's count of the completed statement's review list, read once after the apply, is above zero, the `⚑` line a statement shows (§4 "On the statement"). No table | `esc Back  ⏎ Home  f Flagged` (`f` only with lines flagged; `⏎ Next file` while a file follows) |

Each row's mark and reason come from its `outcome`: `✓ In the ledger` (the mark in the success
colour, the reason dim) for `matched`, `+ New` (accent) for `new`, created on `⏎` under
`@Pendiente` and the pending hashtag, `· Empty` (dim) for `empty`, a row of `0.00` whose place
stays empty, its amount in no colour. Every other amount is coloured by its sign. The title
column takes what the screen leaves once the other columns have their room, so no row wraps;
only a screen too narrow for the paper's longest title cuts one, with `…`. The answer names
the lines taken out and the lines to flag by id alone, so the preview's worker reads them once by their ids
(`statement_lines` in [flow.py](../expense/bank_import/flow.py)), never while drawing, and not
at all when there are none. When the read fails, each block keeps its head, and a dim
`! could not read the ledger lines: <why>` sits under the counts.

**The counts** are the engine's `counts` and its rows for the total:
`10 rows · 5 in the ledger · 4 new · 1 empty · 1 taken out`, the `new` count in the accent colour
when not zero, `empty` and `taken out` only when not zero, then, in the warning colour, `2 to flag` (the lines under `⚑ Will be flagged`) only when not zero. After the close they read
`10 rows · 5 were in the ledger · 4 created · 1 empty · 1 taken out`. The screen after the close
reads the apply's answer, not the dry run's.

`⏎ Close <name>` sends the same PDF on the same account as the apply — one
`POST /statements/import` with `dry_run: false` through the shared HTTP client (its
idempotency key covers a retry); a repeated `⏎` while it is on its way sends nothing more, and
`esc` on the preview sends nothing. `f` on the screen after the close opens the flagged lines'
screen on the completed statement, the apply's `statement` ("The lines a complete flagged for
review" in §4), with the picked account's statement code; back from it, the `⚑` line shows the
engine's count of the lines still flagged. A count read that fails leaves the closed result as
it is, toasts the engine's words and shows no `⚑` line.

**A refused upload** shows under `Preview · <account>` the engine's words as a refused
download does: `CODE — message`, a `!` line per refused key (`! file: …` for a paper the
engine cannot read, misread or that does not add up, or a period sharing a day with another
statement (`PERIOD_OVERLAPS`), or a statement written into the paper's month while the upload
ran (`STATEMENT_MONTH_TAKEN`), and for `MONEY_AT_START_NOT_COVERED`, a currency the paper
shows at zero while the account held money in it; `! account_id: …` for an account archived, a person, a cash account, with no
statement code (`NO_STATEMENT_CODE`), not holding a currency the paper shows money in, or none
it prints (`CURRENCY_NOT_HELD`), or holding one the paper does not print at all
(`ACCOUNT_CURRENCY_NOT_ON_PAPER`); a row's `rows.<place>.date` future date as the engine's
`Row <place>: Must not be in the future.` alone), then `Nothing was written.` dim, and the
app's line when "When the engine says no" gives one. The footer and `⏎` are a refused
download's. A refusal met by the apply shows under the preview the same way. When it is a
`409 CONFLICT` with `CONCURRENT_CHANGE` on any key, a matched line (`rows.<place>`) or the
statement's draft (`file`) changed while it ran
(contract: POST /v1/statements/import, "Concurrency"), or the pending category or hashtag a
created row files under was deleted while it was being created (`category_id` or `hashtag_ids`)
(contract: POST /v1/statements/import), the line under it is
`It changed while the upload ran: ⏎ checks the paper against the ledger again.` and the footer
`esc Cancel  ⏎ Preview again`: `⏎` runs the dry run again, and only the next `⏎` writes. A
failed upload, refused or not (a `5xx`, the engine unreachable), shows its words once, on the
screen: no `Failed` toast repeats them.

**An upload refused for leftover lines** (`LOOSE_LINES_ON_SEALED_DAYS` on `file`, dry run or
apply) is not shown on the preview: the lines the refusal names open the screen in
[leftover_lines.py](../expense/tui/screens/leftover_lines.py) in its place.

**Accounts stand in the engine's order everywhere.** Manage ▸ Accounts, the LOG bar's `$`
picker, the Edit form's account field, the ledger's `b` pick, the Statements
browse, the new-statement form and the bank import's "Which account is this file?"
show accounts as `GET /accounts` lists them, every account that is not a person (a bank or
cash account) first, then every person (contract: GET /v1/accounts). No screen sorts them. A
person is an account whose `kind` is `person`, never told by name. A screen that has no use
for people leaves them out and moves nothing else; the bank-only lists hold bank accounts alone
(`reads.takes_statements`). The LOG bar's `$` picker, the Edit form's account
field and the ledger's `b` pick offer no archived account (`QuickAddRefs.quickadd_accounts` in
[reads.py](../expense/reads.py)): the engine refuses an archived account as a transaction's
`account_id` (contract: POST /v1/accounts/{account_id}/archive). A row already on one shows
its name in the ledger's Account column and on its Edit form's ACCOUNT line, and its code in
Cur and on CURRENCY, read-only on its Edit form (below).

**On an archived account's row the ledger offers no `d`.** The engine deletes none of
an archived account's transactions (contract: POST /v1/accounts/{account_id}/archive), so with
the cursor on one, whole ledger or filtered from Home, `d Delete` leaves the footer and the key
does nothing and sends nothing; on the next row of an active account or a person it is back,
the footer following the cursor. `s` stays on the row and opens the same Edit form `⏎` does,
where only what the line's `edit_limits` leaves open changes (below). The row is drawn as any
other, with nothing on it saying why, and `s`, `c`, `b`, `h`, `m`, `⏎` and every other key
stay; the engine still judges each write they send. The ledger learns which accounts are
archived from the same `GET /accounts` that gives it the names, one read per load
(`reads.load_account_index`), so an account unarchived on Manage ▸ Accounts gets its `d` back
at the ledger's next read. The `?` card still lists `d`, as it does while rows are selected:
the ledger's `CARD_NEEDS_A_ROW` keys leave the card only while it has no row (§4 "App-wide keys are `^q` and `?`").

**On an archived account's line the Edit form changes the categorisation alone.**
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
line, and the save sends each part at its current amount. The "no statement" Edit form follows the
same `edit_limits` on a line of an archived account, which only a list read before the account
was archived still shows. When the engine refuses anyway (the account archived after the line
was read), its words stay under the parts.

**Manage ▸ Categories and Manage ▸ Hashtags mark the built-in rows.**
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

**Manage ▸ Accounts is a table of Name, Type, Code, Color, a column per currency and Status**,
every kind together, under the legend `balances are native currency`. It has
one row per account, named by the account's name alone, in the engine's order ("Accounts stand
in the engine's order everywhere" above). Type reads `person` for a person, `cash` for a cash
account (by its `kind`) and `bank` for any other account. The currency columns are the
currencies the engine lists, in its order (`GET /currencies`, read in the list's worker with the
accounts by `fetch_currency_codes` in [reads.py](../expense/reads.py)) (contract: GET /v1/currencies).
The list screen hands the same codes to the New and Edit forms. Each
holds the account's balance in that currency, right-aligned and never summed with another, or a
dim `—` where the account does not hold it. Code is the account's statement code, or a dim `—`
when it has none. An archived account's row is dimmed whole. `e`, `a`, `t` and `d` act on the
account under the cursor, every currency at once, through one call with the account's id
(contract: POST /v1/accounts/{account_id}/archive, "Every currency at once"); `c` and `x` add
and remove one currency of it. After `a`, `t`, `c` or `x` the cursor is back on the same
account (`account_rows` in [accounts.py](../expense/tui/screens/accounts.py)). Archive asks
nothing ([decisions.md](decisions.md) "Archive is a prompt-free toggle").

**`t` turns an account into a person and back.** On Manage ▸ Accounts the footer reads
`t Make person` on a bank account's row and `t Make bank` on a person's, following the cursor,
between `a Archive` and `d Delete`. `t` opens a short question (`QuestionModal` in
[modals.py](../expense/tui/screens/modals.py), whose docstring holds its keys). On a bank
account it reads `Make <name> a person?` with an empty `name` line; on a person, `Make <name> a
bank account?` with a `bank` line, the engine's `GET /banks` in its order, and an optional
`last 4`. `⏎` sends
`POST /accounts/{id}/make-person` with `{"name"}`, or `POST /accounts/{id}/make-account` with
`{"bank_code"}` and `last4` only when typed, never a `name`, through `run_guarded_write` as `a`
does (contract: POST /v1/accounts/{account_id}/make-person, "Body")
(contract: POST /v1/accounts/{account_id}/make-account, "Body"); `esc` sends nothing. The app
checks nothing. A refusal keyed on a line of the question (`name`, `bank_code`, `last4`) keeps
it open: the engine's words show under that line, the cursor goes there and what was typed stays. Any other
refusal closes it and reads as "When the engine says no" below says, titled `Failed`, or
`Not made a person` / `Not made a bank account` once the list is left. Written, the list reads again with the cursor on the account in its
new place, under the name the engine gives it, and the note says `Now a person.` or
`Now a bank account.`. On an archived row and on a cash row `t` leaves the footer. The Edit form's `type` line
stays read-only.

**`c` adds a currency to an account.** On Manage ▸ Accounts the footer reads `c Currency`
after `e Edit`, on every row, a person's and an archived account's too. `c` opens the pick
`Add a currency · <account>` (`PickModal` in
[modals.py](../expense/tui/screens/modals.py)): the account on one line as the delete question
names it, then the engine's currencies it does not hold, in the engine's order
(`currencies_to_add` in [accounts.py](../expense/tui/screens/accounts.py)). `↑↓` move the
highlight, `esc` leaves the list as it was, and `⏎` sends `POST /accounts/{id}/currencies` with
`{"currency_code": …}` at once, with no question, through `run_write` as `a` does
(contract: POST /v1/accounts/{account_id}/currencies). The note says `Currency added: USD.`
and the list reads again with the cursor on the same account, its new currency's column at
`0.00`; its opening balance is set on the Edit form. On an account holding every supported
currency `c` opens nothing, sends nothing and notes `Visa Inventada already holds every
currency.`, naming the account. A refusal leaves the list as it was; an archived account's is
the engine's to refuse, not the app's ("When the engine says no" below).

**`x` removes a currency from an account.** The footer reads `x Remove currency` after
`c Currency`, on every row, a person's and an archived account's too. `x` opens the pick
`Remove a currency · <account>`: the account as `c`'s pick names it, then the currencies it
holds in the engine's order (`currencies_held` in
[accounts.py](../expense/tui/screens/accounts.py)); `esc` leaves the list as it was. `⏎`
asks first with `ConfirmModal`, as a delete does, the question naming the account and the
currency (`removal_question`): `Remove USD from Visa Inventada?`, its body the account with
that currency's balance alone, then what the account keeps, or, for its only currency, `It is
the account's only currency.`. Only `y` sends
`DELETE /accounts/{id}/currencies/{code}`, with no body, through `run_write`
(contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}); `⏎`, `n`, `esc` and
any other key send nothing. The note says `Currency removed: USD.` and the list reads again
with the cursor on the same account, the removed currency's column a dim `—`.
A refusal leaves the list as it was, its note the engine's words ("When the engine says no"
below), the two `404 NOT_FOUND` answers, `account not found.` and `currency <code> not found.`,
included (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals").
`a`, `t`, `c` and `x` share one guard, one write at a time: while one is in flight, the four
do nothing until the engine refuses that write or the list builds from a read that began after
the write was answered; a reload that lands earlier (`r`, a form closing), and another write's
refusal, neither lift nor hold the guard (`run_guarded_write` in
[_base.py](../expense/tui/screens/_base.py)).

**`d` is the TUI's one destructive key.** It deletes the row under the cursor on Manage ▸
Accounts, Categories and Hashtags (a built-in row aside, above), on the ledger (whole or
filtered from Home), in the statement's "no statement" list, on a statement's flagged lines and on an upload's
leftover lines, always the last of the screen's own footer keys but on the flagged lines, whose
footer ends `d Delete  ↑↓ Move`, and the leftover lines, whose footer ends `d Delete  r Read again`; a footer too wide for the screen leaves it out (§5). Cursor row
only, never a selection; when the ledger turns it off: §4 "The ledger's selection keys". On an
empty list it does nothing. On Accounts `a Archive` stays as it is: archive puts an account
away and can be undone, delete is for something made by mistake.
Removing one currency of an account is `x`, which asks first the same way ("`x` removes a
currency from an account" above).

On Accounts the delete acts on the whole account (contract: "What an account is", "An account is deleted whole"):
the body's first line is the account, its kind, then each currency it holds with that
currency's balance: a two-currency account reads
`Visa Inventada · bank · PEN -2,340.50 · USD -185.20`, a one-currency account
`BCP-5678 · bank · PEN 350.00`. `y` sends one
`DELETE /accounts/{id}`, on a cash account's row too; the engine's refusals
(contract: DELETE /v1/accounts/{account_id}, "Refusals") show the shared way.

Every delete asks first with `ConfirmModal` (only `y` deletes; `⏎`, `n` and `esc` cancel
and send nothing). The question names the row, then says the part that matters: **no
screen can bring it back.**

| Screen | Question | Body | Note after |
|---|---|---|---|
| Accounts | `Delete this account?` | `Prueba · bank · PEN 0.00 · USD 0.00` · `It is for an account made by mistake: no screen can bring it back.` | `Account deleted.` |
| Categories | `Delete this category?` | `PRUEBA` · `It is for a category made by mistake: no screen can bring it back.` | `Category deleted.` |
| Hashtags | `Delete this hashtag?` | `#viaje-cusco` · `It is also taken off every transaction that carries it; one with no other hashtag goes to #Pendiente. No screen can bring it back.` | `Hashtag deleted.` |
| Ledger, and a line never split in the "no statement" list or the flagged lines | `Delete this transaction?` | `Cine Plaza · -28.00 · 2026-10-10 · Sueldo Soles` · `It leaves every balance and report, and no screen can bring it back.` | `Transaction deleted.` |
| Ledger, on a part of a split transaction; a split transaction in the "no statement" list or the flagged lines | `Delete this transaction and its 2 parts?` (the line's real part count) | `FARMACIA · -100.00 · 2026-10-11 · Sueldo Soles` · `No screen can bring it back.` | `Transaction deleted.` |
| A statement's screen (`d` deletes the statement itself) | `Delete statement?` | `Detaches its transactions and removes the statement. Its transactions stay. No screen can bring it back.` | `Statement deleted.` |

`y` sends `DELETE /{resource}/{id}` through `run_write` (the shared client's idempotency
key, `EngineWriteMixin.confirm_delete` in [_base.py](../expense/tui/screens/_base.py)).
Deleted, the list reads again from the start, cursor on row 1: a Manage list's first
page, the ledger's newest ten, the "no statement" list's oldest ten, the flagged lines' review
list read again whole. The hashtag question names the
cascade because the engine never refuses that delete for being in use; it takes the tag
off every transaction carrying it, and one left with no hashtag carries the pending hashtag
(contract: DELETE /v1/hashtags/{hashtag_id}). The question names the pending hashtag as the
list gives it (`#Pendiente`), or says `the pending hashtag` while the user has none yet.

**On the ledger, a split transaction goes whole.** Every ledger row names its bank line
(contract: "Transactions (Ledger)", "Bank lines"), but not how many parts the line holds, so
`d` on a row first reads its line once with the shared `reads.fetch_bank_line`
(contract: GET /v1/bank-lines/{bank_line_id}). With `part_count` above 1 the row is a part of
a split transaction: the question names the real part count, its body is the bank line as
the statement lists show it, then its account, and `y` sends one `DELETE /bank-lines/{id}`,
which deletes every part in one write (contract: DELETE /v1/bank-lines/{bank_line_id}),
through the same `confirm_delete`; the ledger reads its newest ten again, cursor on row 1, every part gone. A
line of one part is a row never split: the ledger's own question and
`DELETE /transactions/{id}`, as above. A line that cannot be read asks nothing and sends
nothing: the "Failed" note carries the engine's words, and `d` again reads again. While the
read runs, `d` again does nothing; a read that lands once the ledger is gone or covered by
another screen asks nothing.

**A refused delete** leaves the row and the list as they were and shows the "Failed" note:
the engine's own words, then the line saying what to do instead, when the table below gives
one.

**When the engine says no.** Every refusal with code `CONFLICT`, `FORBIDDEN` or
`LIMIT_REACHED` names the rule that fired in `reasons`, keyed by the thing refused
(contract: "Base Conventions", "`fields`, `reasons` and `details` semantics"); so do the
`VALIDATION_ERROR` an opening balance draws when asked to move or given a hashtag, the one a
system category or the pending hashtag draws when sent a new name, and the one a hashtag draws
when named like the pending hashtag. The note it draws (a toast, a form's block, a LOG bar
row, the bank import's preview, the Edit form's parts, a statement's refused complete) shows the
engine's words whole (`CODE — message`, then one `key: …` line per refused field; a LOG bar row
the engine names reads `key: …` for each refused field, without the code and message, and so
does a ledger row refused by `b`, `c`, `h` or `m`), and for the reasons below a blank line and
one line of the app's saying what to do. A reason the table does not list has no line: the engine's words
show alone.

| Reason (contract: "Error reasons") | Where you meet it | The line under it |
|---|---|---|
| `HAS_TRANSACTIONS` on `account_id` | `d` on Manage ▸ Accounts | `To retire it instead, archive it: press a.` |
| `HAS_TRANSACTIONS` on `currency_code` | `x` on Manage ▸ Accounts, on a currency holding a transaction (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals") | none: the engine's words alone |
| `LAST_CURRENCY` on `currency_code` | `x` on Manage ▸ Accounts, on the account's only currency (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals") | none: the engine's words alone; deleting the account is `d`, a choice of its own |
| `HAS_TRANSACTIONS` on `category_id` | `d` on Manage ▸ Categories | `Move its transactions to another category first.` |
| `SYSTEM_CATEGORY` | `d` on a category, should the engine find it a system one (Manage offers no `d` on `@Pendiente` or `@Opening`) | `System categories cannot be renamed or deleted.` |
| `SYSTEM_HASHTAG` | `d` on a hashtag, should the engine find it the pending one (Manage offers no `d` on it) | `The pending hashtag cannot be renamed or deleted.` |
| `HAS_RECONCILIATION` on `account_id` | `t Make person` on Manage ▸ Accounts, on an account that has ever been in a statement, a deleted one included (contract: POST /v1/accounts/{account_id}/make-person, "Refusals") | none: the engine's words alone |
| `KIND_UNCHANGED` on `account_id` | `t` on Manage ▸ Accounts, on a list read before the account was turned elsewhere | none: the engine's words already say the account is of that kind |
| `IN_LIVE_STATEMENT` on `account_id` | `d` on Manage ▸ Accounts, on an account a live statement holds (contract: DELETE /v1/accounts/{account_id}, "Refusals") | none: the engine's words alone |
| `IN_LIVE_STATEMENT` on `currency_code` | `x` on Manage ▸ Accounts, on a currency a live statement holds | none: the engine's words alone |
| `IN_COMPLETED_RECONCILIATION` on `transaction_id` or `bank_line_id` | `d` on the ledger | none: the engine's message already says to revert the statement to draft first |
| `ACCOUNT_ARCHIVED` (a `CONFLICT` on a delete, complete, revert or `t`; a `VALIDATION_ERROR` on a save, `c` or an opening balance) | `c` and `x` on Manage ▸ Accounts, on an archived account, offered on purpose since the engine judges it (contract: POST /v1/accounts/{account_id}/currencies, "Refusals") (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals"); an opening balance saved on an archived account's Edit form, keyed `opening_balances.<code>` for every code sent (contract: PUT /v1/accounts/{account_id}, "Keys"); a write sent from a screen read before its account was archived: `t` on Manage ▸ Accounts, `d` on the ledger or in "no statement", `b` or `m` on ledger rows, a save on the Edit form or the "no statement" Edit form, and `space`, `c` (its balances' save too), `u` and `d` on a statement's screen | none: the engine's words already say to unarchive the account first, and the screen stays as after any refusal |
| `NAME_EXISTS` | a new account, person, category or hashtag; a rename on an Edit form | `That name is taken: pick another.` |
| `DUPLICATE_CURRENCY` on `currency_code` | `c` on Manage ▸ Accounts, on a list read before the account got that currency elsewhere | none: the engine's words alone |
| `CURRENCY_NOT_HELD` on `currency_code` (a batch item's `transactions.<i>.currency_code`) | a LOG bar save naming a currency its account does not hold; `m` on ledger rows moving a row onto one (contract: "Error reasons") | none: the engine's words already name the currency, and the staged rows stay, or the refused row stays selected |
| `REQUIRED` on `currency_code` (a batch item's `transactions.<i>.currency_code`) | a LOG bar save of a line with no `%` on an account holding several, which routing stops before sending (contract: POST /v1/transactions, "Fields") | none: the engine's words list the codes held, and the staged row stays |
| `UNSUPPORTED_VALUE` on `currency_code` | a LOG bar save naming a currency the engine does not support (contract: "Error reasons") | none: the engine's words say it |
| `STATEMENT_CODE_EXISTS` on `statement_code` | a new bank account, or a bank account's Edit form, given a code another account has (contract: "What an account is", "One account per code") | none: the engine's words already say it |
| `STATEMENT_MONTH_TAKEN` (a `VALIDATION_ERROR`) on `date_end`, or on `file` for a statement PDF | a new statement (`n`) ending in a month another statement of the account holds; a statement PDF, when a statement is written into the paper's month while the upload runs (contract: POST /v1/statements/import, "Concurrency") | none: the engine's words name the statement holding that month |
| `CAP_REACHED` | a new account, person, category or hashtag | `Delete one first.` |
| `CURRENCY_NOT_HELD` on `account_id` | a save on the Edit form, or the "no statement" Edit form, that sent an account alone, and `b` on ledger rows, onto an account holding several currencies, none of them the line's (contract: PUT /v1/transactions/{transaction_id}, "Moving a transaction"); a statement PDF whose paper shows money in a currency the picked account does not hold (contract: POST /v1/statements/import, "Accounts") | none: the engine's words name the currency, and the form stays, or the refused row stays selected, or, for a statement PDF, `Nothing was written.` |
| `OPERATION_CODE_EXISTS` | a transaction's account or currency changed on its Edit form; an operation number, account or currency changed on the "no statement" Edit form; `b` or `m` on ledger rows; a bank file | `That account already has a row with this operation number: look there for a duplicate.` |
| `CONCURRENT_CHANGE`, on a list | `a`, `t` and `d` on an account, `d` on a category, a hashtag or a statement; `c` and `x` on an account's currencies; a tick, or the balances saved at `c`, on a statement (contract: PUT /v1/statements/{statement_id}, "Sent at the same moment as another write") | `It changed at the same moment: press r, then try again.` (`try again.` alone on the leftover lines' screen of a close, which has no `r`) |
| `CONCURRENT_CHANGE`, elsewhere | saving an opening balance, the LOG bar, the Edit form, a new statement, or `h` on ledger rows | `It changed at the same moment: save again.` |
| `CONCURRENT_CHANGE` on `rows.<row>` | a bank file's apply, when a ledger line a file row matched changed while it ran (§2 "The import door") | `It changed while the import ran: ⏎ checks the file against the ledger again.` |
| `CONCURRENT_CHANGE`, on any key | a statement PDF's apply, when a matched line, the statement's draft or a name it files under changed while it ran (§2 "A statement PDF closes its month") | `It changed while the upload ran: ⏎ checks the paper against the ledger again.` |
| `RESERVED_NAME_HELD` | saving an opening balance, the LOG bar, the Edit form, a bank file | `One of your categories has a built-in category's name: rename it on Manage ▸ Categories, then save again.` |
| `RESERVED_NAME_HELD` on `hashtag_ids` or `hashtag_id` | a transaction's hashtags on its Edit form, `h` on ledger rows, the LOG bar; `d` on Manage ▸ Hashtags | none: one of your hashtags holds the pending hashtag's name, and the engine's message names the remedy |
| `OPENING_BALANCE_EXISTS` on `opening_balances.<code>` | saving an opening balance on the account's Edit form (contract: PUT /v1/accounts/{account_id}, "Sent at the same moment") | `It got one meanwhile: close the form and open it again to change it.` |
| `RECONCILIATION_NOT_DRAFT` | `d` on a statement's screen | `Press u to revert it, then d again.` |
| `RECONCILIATION_NOT_DRAFT` on `file` | a statement PDF whose month is already completed, on its dry run or its apply (§2 "A statement PDF closes its month") | `Revert it first, then drop the PDF again.` |
| `OPENING_BALANCE_ACCOUNT_FIXED` (a `VALIDATION_ERROR`) | `b` on ledger rows that include an opening balance, which the engine keys on `account_id`; its Edit form, on a change of account | `To move an opening balance, set it on the other account's Edit form.` |
| `OPENING_BALANCE_ACCOUNT_FIXED` (a `VALIDATION_ERROR`) on `currency_code` | `m` on ledger rows that include an opening balance, which moves a currency alone; its Edit form, on a change of currency alone | none: the engine's words show alone |
| `OPENING_BALANCE_CATEGORY_FIXED` (a `VALIDATION_ERROR`) | `c` on ledger rows that include an opening balance; its Edit form, should the refusal reach it | `An opening balance always stays in @Opening.` |
| `SYSTEM_NAME_FIXED` (a `VALIDATION_ERROR`) on `name` | a new name, letter case alone included, for `@Pendiente`, `@Opening` or the pending hashtag on an Edit form, should one open on it (Manage offers no `e` on them) | `Built-in names never change: press esc to leave it as it is.` |
| `RESERVED_NAME` (a `VALIDATION_ERROR`) on `name` | a new category, or a category renamed on its Edit form, named like a system category (`@Opening`, `@Pendiente`); a new hashtag, or a hashtag renamed on its Edit form, named `Pendiente` in any letter case | `That name belongs to a system row: pick another.` |
| `OPENING_BALANCE_NOT_TAGGED` (a `VALIDATION_ERROR`) on `hashtag_ids` | `h` on ledger rows that include an opening balance | `Leave the opening balance out of the selection.` |
| `OPENING_BALANCE_NOT_TAGGED` (a `VALIDATION_ERROR`) on `parts.<index>.hashtag_ids` | an opening balance's Edit form, should the refusal reach it (its hashtags show read-only) | none: the engine's words alone |
| `ID_EXISTS`, `IDEMPOTENCY_KEY_REUSED` | any save, rarely: both mean the app sent something wrong | `Not your mistake: the app sent it wrong and nothing was saved. Try again; if it happens again, report it.` |

The line is chosen by the error's `code` and reason alone, never by the HTTP status, the
route or the engine's wording ([decisions.md](decisions.md) "Hints are chosen by the
engine's reasons, never its wording"). The choice lives in one table, `NEXT_STEPS` in
[errors.py](../expense/errors.py), read by the shared error text `format_error`; where a key
or the screen picks between two rows of one reason, the function that picks says how:
`list_refusal_text` in [_base.py](../expense/tui/screens/_base.py) (a write sent from a
list), `changed_while_running` in
[bank_import.py](../expense/tui/screens/bank_import.py) and `changed_meanwhile` in
[statement_upload.py](../expense/tui/screens/statement_upload.py) (the import door's two
`CONCURRENT_CHANGE` lines, shown in place of `format_error`'s).

**The engine's words show as text, never as styling.** Every note shows them as sent,
`[` and all: a `[like this]` or a lone `[` in a refusal, a warning or a name is never read
as markup and never vanishes. Lines drawn on a screen (under the parts, the import's
preview, the LOG bar's rows, a question, the "Could not load." banner, a status line) are
Rich `Text`. Lists show names and titles as the engine holds them: every list handing its
table plain cells draws them through `list_cell` in
[cursor_list.py](../expense/tui/widgets/cursor_list.py), so `BCP [like this]`, a `[/]` or a
lone `[` shows as typed; a cell the app styles itself (a swatch, a coloured amount, a mark)
is a `Text` it builds and is drawn as built. A toast whose message is not a fixed sentence of
the app's goes through `toast` in [refusal.py](../expense/tui/widgets/refusal.py), which
shows it as text; the title is always text. The one toast that styles the engine's words on
purpose, the ledger's bulk edit note, writes its lines into content markup through
`as_markup` there. Guards: [test_tui_bracketed_names.py](../tests/unit/test_tui_bracketed_names.py),
[test_toast_words.py](../tests/unit/test_toast_words.py) and
[test_tui_engine_words.py](../tests/unit/test_tui_engine_words.py).

**"Saved" means the engine holds the row.** The LOG bar ticks a row only when the engine
created it, or refused it only because the row's own id is taken (`ID_EXISTS` on its
`transactions.<i>.id` and nothing else): a replay of a save whose answer was lost. Every
other refusal (`CONCURRENT_CHANGE`, `RESERVED_NAME_HELD`, …) is shown on each row it
covers, which keeps no `✓` (`errors.is_own_id_replay`; [runtime.md](runtime.md) "Bulk writes").

**Refused rows read one line per kind of error** under the table (`save_errors`):
what was refused in the error colour, then the rows it hit, unstyled — `row 2`, or
`rows 4, 6` for several — and, last and dim, `ctrl+s retries just the rows without a ✓.`

```
  amount_cents: Must not be zero. row 2
  date: Period 2026-01-01 to 2026-01-30 is sealed by completed statement 'January 2026'. Revert it to draft to change anything inside it. rows 4, 6
  ctrl+s retries just the rows without a ✓.
```

- **A row the engine names** reads in the engine's words for it, and rows refused alike
  share one line, on two sends of one save too
  ([runtime.md](runtime.md) "How refused rows read"). The app's line saying what to do, when
  the refusal has one ("When the engine says no" above), follows dim on the next line.
- **A refusal naming no row** (a `409` keyed `category_id`, a `5xx`) is a line of its own,
  with the app's line under it, dim.
- **A save the connection stopped** puts its words on every row it left unsent: one line,
  those rows after it. A save a refusal of every further write stopped is said once, in a
  toast, on no row ([runtime.md](runtime.md) "Bulk writes").

**The ledger's bulk edit reads its refused rows the same way** (`b`, `c`, `h`, `m`), through
the same grouping (`refusal_notes` in [transactions.py](../expense/tui/screens/transactions.py)):
one toast per kind of refusal, titled `Refused`, or `2 of 3 refused` when more than one row
was refused, holding what was refused in the error colour, the rows under it, unstyled, as the
list numbered them before the write, and the app's line saying what to do, dim. Every row it
hit is named. A refusal with no field words (a `401`, `404` or `5xx`, or a `409`/`422`
naming no key; `errors.is_keyed_refusal`) reads whole, as a refusal naming no row: the
engine's code and message first, the rows it met under them, its field lines and the app's
line after. A lost connection reads in the shared text, the rows it met under it.

```
2 of 3 refused
account_id: Locked by completed statement.
rows 1, 3
```

A refusal of every further write (`SETTINGS_MISSING`) is no row's and is not counted among
them: it shows after them, once, in the note the LOG bar shows when the same refusal stops its
save, one copy for both (`run_stopped` in [refusal.py](../expense/tui/widgets/refusal.py)):
titled `Failed`, the engine's words whole, then, after a blank line, the line saying what to
do. A row refused for its own reason before the stop keeps its own note.

```
Failed
SETTINGS_MISSING — User settings have not been provisioned.
  user_settings: Must be provisioned via POST /v1/auth/bootstrap.

Hint: First-time setup is not done yet. Open System ▸ Auth & profile and press b.
```

Left before the run ends (the second `esc`), every row is still sent and the app shows the
same toasts (`show_bulk_outcome`), except that the rows are named as the ledger showed them,
`DAY · TITLE · AMOUNT`, one per line, four at most, then `and 2 more`
(`named_rows`).

**The New form makes an account, its currencies and their openings in one write** (`n` on
Manage ▸ Accounts; `NewAccountScreen` in [create_forms.py](../expense/tui/screens/create_forms.py),
whose docstring gives each kind's lines and the body). A bank or cash account has no `name`
line: the engine builds its name (contract: POST /v1/accounts, "The name"). Its `bank` picks from
`GET /banks` (`reads.fetch_bank_codes`, read by Manage ▸ Accounts with its currencies); the app
checks nothing typed on `last 4`, the engine judging its shape.

- **`currencies` takes one currency or more,** picked as a part's HASHTAGS line on the Edit
  form picks hashtags, from the currencies not yet picked, in the engine's order; the summary
  lists the picks as `PEN · USD`.
- **The pairs are the Edit form's** (one copy of the lines and of `opening_balance_body`); a
  save with an amount and no day says `PEN as of is required.` and sends nothing.
- **The save is one `POST /accounts`,** whole or not at all
  (contract: POST /v1/accounts, "Required")
  (contract: POST /v1/accounts, "Optional"). With nothing picked in `currencies` it says
  `Currencies is required.` and sends nothing; a code still in the bar at `ctrl+s` is added
  first, as `⏎` would add it (§4 "The bar forms' keys").
- **A refusal** shows the "Failed" note in the engine's words, and the cursor goes back on
  the line its key names, holding what was typed (`NewAccountScreen._line_named`). A name
  already taken by a bank account is keyed `last4` or `bank_code`
  (contract: POST /v1/accounts, "Validation"); `user_settings` (`SETTINGS_MISSING`) shows as a
  note with the setup hint.
- **Left before the answer,** an account with no typed name reads `Not created · Account
  (unnamed)`.

**A bank account's Edit form holds its number on three lines,** `bank` (New's line), `last 4`
and `since`, after `type`, with `cards before`, `new card` and `new card from` for a
replacement; a person's and a cash account's have none, a cash account's `name` reading
its name, read-only. `EditAccountScreen`'s docstring says when each line is on the
form, what it opens holding and what the save sends of it. The app checks nothing typed on
them (contract: PUT /v1/accounts/{account_id}, "The numbers").

- **Emptying `last 4` on an account that has a number removes it,** after `ConfirmModal` asks
  over the form (`EditAccountScreen._removal_question`: `Remove card 5678 from BCP-5678?`).
  Only `y` sends `current_number: null`; any other answer sends nothing. An emptied opening
  balance's question follows this one.
- **A `new card` sends `new_number`** beside whatever else changed; one beside a changed
  `last 4` or `since`, or a removal, is the engine's to refuse.

**A bank account's statement code is a line of its own on New and Edit.**
**`statement code`** sits right after `currencies` on New and Edit, on a bank
account only. The engine lets a person carry a code too
(contract: "What an account is", "A person carries a code like a bank account"); these forms
offer it none. On New, TYPE turned to `person` or `cash` takes the line off the form and the
save sends no code; turned back to `bank`, the line returns holding what was typed, as `bank`
and `last 4` do. A person's Edit form and a cash account's have no such line.

- **Small letters show as capitals while typing,** typed or pasted (`FormScreen._typed`);
  no other line of any form changes what is typed. The app checks nothing else about the
  code: the engine judges its shape.
- **On New,** a code typed is sent as `statement_code` on `POST /accounts`; skipped, the key
  is left out of the body, never sent as `null` (contract: POST /v1/accounts).
- **On Edit,** the line opens holding the account's code. Emptied, the save sends
  `statement_code: null`, which clears the code with no question: nothing is lost, since
  typing the code again brings every statement line back
  (contract: PUT /v1/accounts/{account_id}, "`statement_code`").
- **A refusal** shows the "Failed" note in the engine's words, the cursor back on the code
  line with what was typed, on New and Edit.

**An account's opening balance lives on its Edit form, one per currency** (`e` on Manage ▸
Accounts opens the form on the account). `currencies` lists the currencies the account holds,
read-only (`PEN · USD`; they change on Manage ▸ Accounts). The form ends with two optional
lines per currency after `color`, in the engine's order of the account's currencies
(contract: "Bank Accounts", "Per-currency order"), each named by its currency:
**`PEN opening`**, the amount, and **`PEN as of`**, its day, then **`USD opening`** and
**`USD as of`**; the bar reads `PEN OPENING`. There is no title line; the engine names the
row. Every kind's form has the pairs, and its opening balances are written the same way. A bank account's form has no `name` line: a `name` sent for it is
refused (contract: PUT /v1/accounts/{account_id}).

- **The amount is signed and taken as typed**, in its line's currency; the app never adds or
  flips a sign. On the bar's right `debt` or `credit` follows what is typed, as
  `EditAccountScreen`'s docstring says. An `as of` line takes
  `YYYY-MM-DD`, starts empty, and is
  marked `*` once its currency has an amount.
  The summary draws each `opening` amount coloured by sign, as the ledger does.
- **A currency that has one opens with its pair filled.** Each currency's entry in the
  account's `currencies` names its opening balance by id, or `null` when it has none
  (contract: "Bank Accounts", "`currencies`"),
  and the form reads each named row with `GET /transactions/{id}?debit_as_negative=true`
  (`reads.fetch_transaction`), one at a time, so the amount arrives signed and nothing reads
  the sign off `transaction_type` (contract: "Base Conventions", "Sign convention — responses").
  A save waits for those reads, saying `The PEN opening balance is still loading.` (the first
  currency still loading, in the form's order); a read that fails shows its "Failed" note and
  leaves that currency's pair read-only, so the rest still saves.
- **A save is one `PUT /accounts/{id}`**, all or nothing
  (contract: PUT /v1/accounts/{account_id}, "`opening_balances`"), carrying only what changed
  (`EditAccountScreen`'s docstring): a currency's opening balance is set with a client
  `transaction_id`, changed by only its amount or date, never its `transaction_id`, or cleared
  with `null`. Nothing changed sends `{}`, which the engine answers unchanged.
- **Emptying the amount of an existing one and saving clears it**, after `ConfirmModal` asks
  `Delete this opening balance?` over the form, a line naming the account, currency, amount
  and day, then `It leaves the account's balance, and no screen can bring it back.`; two
  emptied ask once, `Delete these opening balances?`, a line each. Only `y` sends the one
  `PUT`; `⏎`, `n` and `esc` go back to the form with nothing sent.
- **A refusal** shows the "Failed" note in the engine's words (`format_error`) and leaves the
  form open with what was typed; nothing was saved, and the next save sends the whole body
  again, a set with a new `transaction_id`.
  The cursor goes on the line the key names (`EditAccountScreen._line_named`). When the
  engine names several codes (`ACCOUNT_ARCHIVED` names every one sent), the cursor goes to
  the first in the form's order and the note shows the
  engine's words whole. `user_settings` (`SETTINGS_MISSING`) names no line: a note, the cursor
  stays. `esc` just leaves.
- **Saved,** the form closes with `Saved.` and the account list reads again from its first
  page, cursor on row 1. Every Manage Edit form (accounts, categories, hashtags) closes
  this way: one that wrote dismisses with `True` and the list starts over; one closed with
  `esc` before any write keeps the edited row selected (`ResourceListScreen._edited` in
  [_base.py](../expense/tui/screens/_base.py)).

**No cards. No vertical lines. Horizontal rules divide sections.**

- **Nothing is drawn inside a box** — not a modal, not a list panel, not the input bar,
  not a plain yes/no `ConfirmModal`.
- **Horizontal rules are the divider** (the header's `border-bottom` is the pattern).
- **A question that needs room becomes a screen**, not a card.

**List chrome is content.** A list's page status (`rows 21-40 of 133 · page 2 of 7`) is
drawn as ordinary content by `WindowedList.framed()`
([windowed.py](../expense/tui/widgets/windowed.py)), which every repaint of both list widgets
passes through: a plain rule opens the section, the page status sits dim beneath the rows,
and there is no title, the breadcrumb already naming the screen. **The status line is drawn
on every windowed list, blank when there is nothing to say**, except where a screen turns it
off for a mode that never has a status (`set_status_line(False)`, the Statements lines in no
statement): the line is fixed per list or mode, never by rows, since `AdaptiveRowsMixin` measures
the widget's height. **The rule passes an explicit style**: Rich's default `rule.line`
resolves to a literal green that `test_no_literal_color_styles_in_tui` cannot see, because
it greps source rather than renders.

⚠️ **One exception.** A title that is *chrome* disappears; one that is *information*
becomes a line of content above the rule. The Statements browse stacks two lists once a
panel is open, and its caption (`Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest`)
is the only thing tying the lower rows to an account above. Ask "would the screen still be
unambiguous without this?" — not "is this a title?".

---

## 3. Theming — the terminal supplies every colour

**No literal colors in the TUI, and no authored ones either.** CSS uses `$accent` /
`$secondary` / `$error`; Rich content takes the `PALETTE` constant
([theme.py](../expense/tui/theme.py)). Guarded by
`test_no_literal_color_styles_in_tui`.

The tokens themselves are **ANSI slots**, not hexes (`ansi_green` is slot 2 — the
terminal fills it in), so the app reads on dark, light, Solarized and Gruvbox with **no
detection at startup**, no light/dark pair and no `NO_COLOR` mode. A hex in `theme.py` would
pin the app back to one terminal — guarded by `test_theme_is_ansi_slots_not_hexes`. Why, and
the slot picks (pending is `bold`, not yellow): [decisions.md](decisions.md) "The terminal
supplies the palette".

**Amounts.** Every figure shown, and every example amount in a note, is written in the
session's format (§1 "One reader for every typed amount"). Green is money in, the error colour money out. A transaction's or bank line's
amount in a list (ledger, LOG bar peek, bank import and statement upload previews, a
statement's lines, the lines in no statement and their Edit form's heading, the Edit form's
parts and their count line), and wherever one is named (the question before a delete, a note
after you leave), writes a positive figure with its `+` (`+800.00` beside `-36.40`); zero stays
`0.00`. Account balances, Home's grid and its `net` row, a statement's difference, and any
other sum of amounts (the staged total, a day's net, a count line's `… left`) write no `+`
(`12,450.00`, `-234.20`). A statement's beginning and ending balances, and Home's dim `inflow`
and `outflow` rows, are in no colour. The three rules are
`TRANSACTION_RULE`, `AMOUNT_RULE` and `BALANCE_RULE` in [theme.py](../expense/tui/theme.py).

**Theme the foreground, never the base surface.** The app runs in ANSI mode
(`ExpenseApp(ansi_color=True)`): the base fill is `ansi_default` — the terminal's *own*
background — set **structurally** in `app.tcss`, not per theme. **The rule for any future
theme:** recolor the foreground and semantic spans only (text, accents, sign-colors,
selection/diff highlights) — **never** paint a full-screen or base-surface background; a
painted ground brings back the seam against the terminal's padding and breaks any
light/dark theme ([decisions.md](decisions.md) "TUI paints the terminal's own background").
Guard: `test_tui_theme.py::test_base_fills_are_terminal_transparent`.

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

**The cursor is reverse video, applied as a Rich style** ([decisions.md](decisions.md) "The
cursor is reverse video"): `CURSOR_STYLE` in [windowed.py](../expense/tui/widgets/windowed.py)
(re-exported from `cursor_list.py`). `CursorList` / `CheckList` apply it to their Rich table
rows, `suggestion_list` to the picked name, the LOG bar to its staged row, and
`CursorOptionList` (the home menu) to the finished strip.

**Assert on rendered strips, not on styles.** `get_component_styles` can report
`text_style: reverse` for a style that is discarded later. Only `render_line(y)` shows
what the user sees, which is what `test_tui_menu_cursor.py` checks.

---

## 4. The keymap contract

Three cross-screen rules. No screen declares them, so no generated key list can find
them — they are hand-written into the `?` card
([help.py](../expense/tui/screens/help.py) `CONVENTIONS`):

- **`r` always refreshes**, everywhere.
- **`y` alone confirms** — on the questions that delete, complete or revert, the quit
  question while saves are still being sent, a currency's removal (`x` on Manage ▸ Accounts)
  and an emptied opening balance included. Archive asks nothing
  ([decisions.md](decisions.md) "Archive is a prompt-free toggle").
- **`⏎` never changes data.** On the Manage lists it is a literal no-op: no screen
  handles `CursorList.Selected` there, and the help card *drops* the row rather than
  advertise `⏎ Open` falsely.

  A currency pick is the exception, and the card says so (`⏎ never changes data, except on a
  currency pick`): Manage ▸ Accounts' `Add a currency · <account>`, opened by `c`, adds the
  highlighted currency at once (§2 "`c` adds a currency to an account"), and
  `Remove a currency · <account>`, opened by `x`, takes the highlighted currency to the
  question whose `y` removes it (§2 "`x` removes a currency from an account"). Each pick's
  footer is `esc Cancel` alone; the hint line under its list names `⏎`. The import screens'
  `⏎ Import N rows` and `⏎ Close <name>` write too (§2 "The import screens' keys").

**The ledger's selection keys** ([transactions.py](../expense/tui/screens/transactions.py)):
`space` selects / unselects the cursor row without moving it (`↓` then `space` is the
rhythm), `a` selects every loaded row or clears the selection, `c` / `b` / `h` / `m` open the
bulk pick for category / account / hashtags / currency (§2 "The bulk pick is a full screen"),
`esc` clears the selection if there is one, else goes back to the screen that opened the
ledger. `s` and `d` act on the cursor row alone and never follow the selection: they are off,
and out of the footer, while rows are selected, while a bulk write runs and on an empty list,
and `d` is off on an archived account's row too (§2 "On an archived account's row the ledger
offers no `d`").
`space` is declared on `CursorList` but is live — key and footer both — only on a
screen that handles `CursorList.Toggled`, the same `NEEDS_SCREEN_HANDLER` gate `⏎ Open`
goes through on the `?` card, so the Manage lists neither react to it nor advertise it.

**`pgdn` means "more of this list", in three ways.** In the two growing lists, the ledger
and the "no statement" pane, it appends the next 10 rows (§5; [decisions.md](decisions.md)
"Long lists grow, they do not page"). In every other list it is the next page of rows already
loaded (§5). On Home it walks the month window one month older, `pgup` one newer (§2).

**The Statements browse** opens on the **account list alone**, full height, and reads no
statements. The list is the bank accounts of one `GET /accounts`, one row each under its own
name: `Account · Currencies · Balances`, the currencies as `PEN + USD` and
a balance in each, `-234.20 PEN   -30.98 USD`, never added together, every account's first
figure ending in one column (`browse_accounts` and `balances_cells` in
[statements.py](../expense/tui/screens/statements.py)). An archived account is not
in that read, so its statements are not offered until it is unarchived. The statement code is
the account's own, from the same answer
(contract: "What an account is", "Statement code"). Moving the cursor reads nothing.
`⏎ Its statements` reads the account's statements in **one read**,
`GET /statements?account_id=<id>`
(`fetch_statements`; contract: GET /v1/statements, "`?account_id=<id>` is required"), whole,
in the engine's order (`date_start` ascending, then creation time, oldest first
(contract: "Statements", "Ordering")), and opens the **panel** under the accounts with the
cursor in it; the open account keeps an accent `▸` in a two-cell gutter before its name, and
the breadcrumb grows to `Statements ▸ <account>`. An account with none says
`none yet · n to create one`; a read that fails toasts the engine's words and leaves the panel
closed. Coming back from a statement, or `r`, reads the list again and lands on the same row.

The panel lists **one row per statement** (`statement_rows`): `Name · Period`, one
`Diff <CUR>` per currency the account holds, in the account's order (`Diff` alone on an
account of one currency), `Status`, and `Order` on an account with a statement code. Each Diff
is that currency's `difference_cents`, from its own entry in the statement's `balances`, by
the rule of every statement list: a dim `—` when it adds up, the figure when off, blank when
not checked yet
(contract: "Statements", "A balance not entered is `null`, never zero"), and blank for a
currency the statement does not cover
(contract: "Statements", "Which currencies a statement covers"). Status is `completed` (the
row dim) or `draft`; Order is `in order` when the engine's `unplaced_count` and
`shared_place_count` both read 0 and `not in order` (warning) otherwise
(contract: "Statements", "A statement's order"); the engine sends no order for an account
with no statement code, so it has no Order column. The title names the account, its
currencies and its code when it has one:
`Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest`.

Both lists sit tighter than the shared table (`gap` and `edge` on `CursorList`,
`StatementsScreen` in [app.tcss](../expense/tui/app.tcss)): two spaces between columns,
one on the statements list of an account with a statement code (`ORDER_GAP`). On the
statements list the Name is the one column that gives way (`_panel_layout`, `gives_way` on
`CursorList`): a name too long for the room left is cut with `…` (`Noviembre 2026` reads
`Noviembre 20…` at 80 columns), never the period, a Diff, the status or the order, and the
list does not stretch to the card's edge, so the cursor's highlight ends after the last column.
On the account list the Account column gives way, down to 18 cells with its `▸` gutter
(`ACCOUNT_NAME_WIDTH`): a long name is cut with `…` before a balance loses a letter, so both
balances of a two-currency account show whole at 80 columns. The rule under its header is 60
cells of `─` from under the `A` of `Account`, whatever the table's width (`header_rule_span` on
`CursorList`). When the accounts page (`rows 1-5 of 6 · page 1 of 2`), a blank line stands
between that page line and the panel's caption, taken from the room the two lists split
(`_panel_gap`); on one page the page line is itself blank, and no line is added.

**Keys**: `⏎` opens the row's statement on its screen, every currency it covers, none
picked first; `n` creates a statement for the open account, or with no panel for the account
under the cursor, and once saved the panel opens on the new one; `u` swaps the panel to the
account's rows in no statement (§2); `d` deletes a row **in that list only** (off, and out of the
footer and the `?` card, on the statements list: a statement's own delete is on its screen); `esc`
retreats one step — no-statement rows → the panel → the account list (`esc Close the panel`) →
Home. On a statement's screen one keypress away, `u` means *revert*.

**The New statement form** (`n` on an account, or `Statements ▸ New` alone;
`NewStatementScreen`) is one form for every account: `Statements ▸ <account> ▸ New`,
with the lines `name`, `date start`, `date end`, then a `begin balance <CUR>` and an
`end balance <CUR>` line for each currency the account holds, in the engine's order. The
account is stated, never edited, in the summary as `Visa BCP · PEN + USD · VIS` (no
`· <code>` on an account with no statement code); opened alone, the form asks for it second,
after the name, from a picker listing each bank account by its name, and the pick gives it its
currencies' lines. Every balance line is optional: which currency needs one is the engine's
call (contract: POST /v1/statements, "`balances`"). Each begin's hint takes two lines, dim:
`signed decimal · the statement's opening balance in PEN · optional`, then
`0.00 if it holds the account's opening balance, which already counts it`.

`^s Create`, or `⏎` on the last line, sends one `POST /statements` with `account_id` and one
entry in `balances` per currency with a begin typed: its `currency_code`, its
`beginning_balance_cents` and, when typed, its `ending_balance_cents`; a currency left empty is
not sent (contract: POST /v1/statements). An entry takes its begin always, so an end typed
without its begin is not sent: the cursor goes to that begin with a note. A refusal is the
form's `Failed` note with the engine's words whole, and the form stays with what was typed. A
refusal naming a currency's entry (`MONEY_AT_START_NOT_COVERED` on `balances.USD`;
`CURRENCY_NOT_HELD` on `balances.<i>.currency_code`, the i-th entry sent) puts the cursor on
that currency's begin (contract: POST /v1/statements, "Order"). `CONCURRENT_CHANGE` on
`account_id` (a currency joining or leaving the account mid-write) ends the note with the
app's line `It changed at the same moment: save again.` Saved, it says `Statement created.`
and the panel opens on the account's statements, the cursor on the new one.

**A statement's screen** (`⏎` on one in the panel) is the whole statement. Its head is
the name whole, brackets and all (`[VIS] Agosto`), the account, the period and `status`, then a
`begin  end  diff` table (`balance_lines`) with a line for each currency the statement covers,
in the engine's order; a currency it does not cover has no line
(contract: "Statements", "Which currencies a statement covers"). A balance not entered reads a
dim `—`, never zero, and its difference, not checked yet, stays blank
(contract: "Statements", "A balance not entered is `null`, never zero"). The statement is read
again by its id, `GET /statements/{id}` (`fetch_statement` in [reads.py](../expense/reads.py))
(contract: GET /v1/statements/{statement_id}); one deleted elsewhere reads as a `404`, so the
screen says `This statement no longer exists.` and goes back, and any other refused read shows
the engine's words and stays.

Under the head is one list of **bank lines** (`CheckList`), read by `fetch_month_lines` in
[statements.py](../expense/tui/screens/statements.py), every page of each read, by
account and never by one currency:
`account_id=` with `statement_id=` and `sort=statement`, so the statement's lines come in the
paper's order, both currencies together, then those holding no place oldest first
(contract: GET /v1/bank-lines, "Ordering"); the app sorts nothing. Its rows are the "no statement"
rows (§2; `line_rows`): no category, hashtags, note or part count. An opening balance
(`is_opening_balance`) holds no place on the paper, so its rows come last under a dim
`Not on the paper` label. The list holds focus, so `pgdn` and `pgup` page it on every
statement. What it shows, and which keys the screen offers (`check_action` hides the others
from the footer and the `?` card and leaves them dead), depends on the statement:

- **A draft on an account with no statement code** is a tick-list: the statement's lines ticked
  and first, then the account's lines
  in no statement inside the period (`unreconciled=true`, the period's days as `date_from` /
  `date_to`, `sort=date_asc`, oldest first). Keys: `space Toggle`, `c Complete`, `u Revert`,
  `d Delete`.
- **A completed statement** lists its own lines, read-only, with no tick box. On an account
  with a statement code a `#` column leads with each line's number, 1, 2, 3 … down the rows
  with no gaps, a dim `—` on an opening balance's row; on an account with none there is no `#`
  column. Keys: `u Revert`, `d Delete`.
- **An open statement on an account with a statement code waits for its PDF**: its own lines
  alone, read-only, with no tick box and no number, and the dim line
  `closes when its PDF is dropped on the LOG bar` under the balances (the statement code is the
  account's, passed in from the browse). Keys: of the statement's own, `r Refresh` and
  `d Delete` alone.

Every statement also offers `r`, which reads the statement again by its id and its lines, and
`esc`, which goes back.

**`space`** puts the line under the cursor in or out of the statement with one
`PUT /transactions/{id}` of `statement_id` (or `null`) on one of its parts, which moves every
part (contract: PUT /v1/transactions/{transaction_id}, "Statement assignment"). Once every
tick sent is answered the screen reads the statement and its lines again, so the head's `diff`
is the engine's, a currency the tick gave the statement shows its balances as a dim `—` and its
difference blank, and the cursor stays on the line ticked last, now among the ticked ones; a
read that lands while a tick is still unanswered is not drawn, so ticking down a statement
(`space`, `↓`, `space`…) never lands on another row. A refused tick drops the ticks queued
behind it, shows `Couldn't update` with the engine's words and the line §2 "When the engine
says no" gives, and reads the statement and its lines again, the cursor on row 1; so does a refused
complete, revert, delete or balance save that had ticks queued behind it, under its own
`Couldn't …` note.

**`c`, `u` and `d`** act on the whole statement, every currency of its account, in one write:
`POST /statements/{id}/complete`, `POST /statements/{id}/revert` and `DELETE /statements/{id}`
(contract: POST /v1/statements/{statement_id}/complete)
(contract: POST /v1/statements/{statement_id}/revert)
(contract: DELETE /v1/statements/{statement_id}).
`c` asks `Complete statement?` · `Locks the amount, date, title, account, operation number and
statement of the N ticked rows.` (`1 ticked row` for one): completing makes those six
read-only on each ticked row, an empty title or operation number staying fillable
(contract: PUT /v1/transactions/{transaction_id}, "Field locking").
On an account with a statement code the engine completes nothing until every line of the
statement has a place in its order
(contract: POST /v1/statements/{statement_id}/complete), and no screen sets the order
([decisions.md](decisions.md) "A card's statement is one statement, and a month closes from the bank's PDF").
A complete with no transaction in any currency is refused as `NO_TRANSACTIONS_ASSIGNED` on
each currency's `balances.<currency>.transactions`.
A complete refused for lines in no statement on days it seals (`LOOSE_LINES_ON_SEALED_DAYS` on
`statement_id`) is not shown as `Couldn't complete`: it opens the screen in
[leftover_lines.py](../expense/tui/screens/leftover_lines.py) over the statement, and `c` there
asks `Complete statement?` again.

**`c` needs every balance**: the engine completes no statement with a balance blank
(contract: POST /v1/statements/{statement_id}/complete, "Every balance must be entered").
On a draft with any blank balance, `c` first opens a box for each one, currency by currency in
the statement's order, a currency's starting balance before its ending one
(`blank_balances`): `Starting balance first` (`The statement's opening figure for <account>,
in <currency> · signed · e.g. 13,853.20`) or `Ending balance first` (`The statement's closing
figure for <account>, in <currency> · signed · e.g. 13,853.20`), each with
`[enter] save    [esc] cancel`. Each figure is read by the shared money parser exactly as
typed, the sign never added or flipped; text it cannot read keeps the box open with what was
typed and notes `Begin balance USD: a signed decimal, e.g. 9580.00` or
`End balance USD: a signed decimal, e.g. 9460.00`, naming the box's currency as the New
statement form's note names its line's, and nothing is sent. `esc` closes the box with nothing
sent. The boxes and the `Complete statement?` question after them open under the statement's
head, the crumb, the balances and any note staying in sight
(`UnderHead` in [modals.py](../expense/tui/screens/modals.py)), each 60 wide at most and
narrower with the terminal, its words wrapping, never cut; every other modal stays centred.
After the last box one `PUT /statements/{id}` saves everything typed: its `balances`
names only the currencies that change, each with only the balances typed (`balances_body`), so
the engine keeps every other (contract: PUT /v1/statements/{statement_id}, "`balances`"). The
head shows the engine's saved figures, and then `Complete statement?` asks; only `y`
completes, and any other answer leaves a draft with its balances saved, so the next `c` goes
straight to the question, as it does on a draft with every balance.

**A refused complete** shows `Couldn't complete` and the engine's words whole as lines right
under the head, and no toast. They stand until the next key, a key in a box open under them
included (a character typed, `⏎`, `esc`), and the box then moves up into their room. After a
save in the same `c`, the line `The balances are saved. The statement is not completed:` stands
above the engine's words. Every refused complete reads the statement fresh, so the head and the
next `c` go by what the engine holds. One that names a missing balance
(`BEGINNING_BALANCE_REQUIRED`, `ENDING_BALANCE_REQUIRED`) or a currency the statement does not
cover (`MONEY_AT_START_NOT_COVERED`) then opens the same boxes, empty, for the currency the
engine names (`balances_named`, read off the refusal's `reasons` keys
`balances.<currency>[.<field>]`): the named balance's box, or for a currency not covered its
starting then its ending balance. A currency with no movement closes the same way, its ending
balance typed and the engine judging it. Then the question asks again. A refused save toasts
`Couldn't save` with the engine's words.

**The close's notes.** A complete's answer carries each balance's `warnings` and
`coverage_gap` (contract: POST /v1/statements/{statement_id}/complete, "Response"), and the
notes of each currency of the account the statement holds no balances for in `not_covered`
(contract: POST /v1/statements/{statement_id}/complete, "`not_covered`"). Each `warnings`
sentence shows under the head in the engine's words, `  ⚠ <sentence>` in the warning colour,
those of a currency not covered after the others and led by its code, `  ⚠ USD: <sentence>`,
until the next status change. The notes are `close_notes` in [formatting.py](../expense/formatting.py),
drawn by `warning_note` in [refusal.py](../expense/tui/widgets/refusal.py), which the upload's preview
shares. A head line or note too long for the width wraps under its own
first word (`under_itself`), never at column 1.

**The lines a complete flagged for review.**
A complete goes through while lines dated in the statement are in no statement; the app keeps
no rule of which lines those are and treats none as a refusal. When the statement's review list
counts a line after the complete ("On the statement" below), the app pushes a full screen,
`Statements ▸ <statement> ▸ Flagged`
(`FlaggedLinesScreen` in [statements.py](../expense/tui/screens/statements.py)). It
opens on the statement's id, not the lines' ids, and reads the statement's review list, the
lines its close flagged and still unresolved, whole,
`GET /bank-lines?unassigned_in_period_of=<statement id>&sort=statement` page by page, and how
many it holds from `GET /bank-lines/count` on the same filter (`reads.count_bank_lines`)
(contract: GET /v1/bank-lines, "It has no bound"). A line assigned to a statement, moved out of
the account or the days, or deleted drops out of the engine's list. The head reads
`<statement> has 3 flagged lines. 3 lines dated up to its last day are in no statement.`
(`1 flagged line. 1 line dated up to its last day is in no statement.` for one), the first
sentence plain and the engine's count and the rest of the second in the warning colour; the
head and the words under the list stand two cells in and wrap at 75 columns. Under it are the
lines in one list, the "no statement" rows drawn as the statement's own list is (`CheckList`,
read-only, no numbers), every currency of the account together, in the engine's order, the
statement's: its lines hold no place, so they are oldest first, the currencies mixed by date
(contract: GET /v1/bank-lines, "Read in the statement's order, and only in it").

On an account with a statement code (the account's, passed in from the browse), the engine's
two ways to settle a flagged line read as dim words under the list (`FLAGGED_WAYS`): when the
paper prints the line, the upload made the paper's row a line of its own, its twin, and the
owner keeps one, the bank's by deleting the flagged line or their own by reverting, deleting
the twin, setting the line's day to the row's day and uploading the PDF again; when the paper
does not print it, the line waits for a later statement, or is fixed or deleted
(contract: POST /v1/statements/{statement_id}/complete, "What a client does with a flagged line").
The words do none of the steps: each is done on the screen it belongs to (`u` on the
statement, `d` on the twin, the Edit form for the day, the PDF on the LOG bar). On an account
with no statement code no words show.

The screen has no `?`: it does not take `HelpBindingMixin`, so its footer,
`esc Back to the statement  ⏎ Open  d Delete  ↑↓ Move`, is its whole key list. Its list takes
no focus, so the screen holds `⏎`, `d` and `↑↓` itself; `pgdn`/`pgup` page and `r` reads the
list again, none of them in the footer. `⏎` opens the line in the ledger's Edit form
(`EditFormScreen`, which reads the line by its id), crumb `… ▸ Flagged ▸ Edit`; `d` asks the
"no statement" list's question and deletes as it does (`ask_line_delete`). After a save or a
delete the screen reads the review list and its count again, the cursor on row 1, and with none
left it goes back to the statement. The head shows the engine's count as soon as it arrives and
the list fills in when its pages arrive; a read that fails toasts the engine's words and keeps
what is listed. `esc` hands the statement the engine's last count.

**On the statement**, open or completed, the line
`⚑ 3 lines flagged for review: in no statement, dated up to this one's last day  · f shows them`
sits under the head, two cells in, in the warning colour with `· f shows them` dim, and
`f Flagged` is in the footer and on the `?` card, only while the statement's review list counts
a line; `f` opens the flagged lines' screen. The count is the engine's, `GET /bank-lines/count`
with `unassigned_in_period_of=<statement id>`, read each time the screen reads the statement
(when it opens, on `r`, after a tick and after a status change; a read that fails toasts the
engine's words), so a draft shows the lines a complete would flag, and a revert counts again.
After a complete, the screen reads the statement's lines and that count again, and the count
alone decides, never the answer's `review_lines`: the flagged lines' screen opens on its own
when it is above zero (whichever read brings the count, unless `f` has opened it first or
another screen, such as `?`, is on top); a read that fails toasts and opens nothing. Back from
the flagged lines' screen, its last count holds. The lines stay in the ledger, in no statement,
and show in the account's "no statement" list.

**`+` logs a transaction** — Home and Transactions (`LogTransactionMixin` in
[_base.py](../expense/tui/screens/_base.py), splatted into each host's BINDINGS like
`HelpBindingMixin`). It always opens the **LOG bar**: one key, one meaning
([decisions.md](decisions.md) "Logging is a key, not a menu row"). Whether a line stages is
decided by *the line you typed* — refused in place with the reason if it cannot. The numpad
and main-row `+` send the same byte, so one binding catches both.

**The LOG bar's own keys** ([log_bar.py](../expense/tui/screens/log_bar.py)): `↵`
stages the line — or completes the open token, or puts a lifted row back; `↑↓` drive
the completion picker while a token is open and move through staged rows when the bar
is empty; `ctrl+s` writes everything not already written, through `POST /transactions/batch`
([batch_write.py](../expense/batch_write.py); chunking and retries there), a saved row keeping its `✓` until the next line is staged; `ctrl+x` drops the
picked row; `esc` unpicks, then leaves (confirming if rows are staged and unwritten). The bar
always holds focus, which is why no bare letter is a command there and why the screen
has no `?` — a focused `Input` swallows printable keys.

**A dropped bank file.** Dragging a file onto the terminal makes the emulator type its
path into the bar, each emulator in its own shell syntax; one pure function,
`dropped_bank_files` in [dropped.py](../expense/tui/dropped.py), reads every form (its
docstring lists them). The line is bank files only when **every** word is an absolute (or
`~/`) path to an existing `.xlsx` file (the bank's download) or `.pdf` file (a month's
statement), any letter case; one word that is not leaves the whole line quick-add. Which kind
a file is goes by its name alone (`is_statement`). While it
holds, quick-add stands down — no token colouring, no picker, no refusal, no account peek
(hidden, still on its last account), no legend row — and the hint reads
`bank file · <name> · ⏎ import it`, or for a statement PDF `statement PDF · <name> · ⏎ upload it`.
Several downloads read `bank files · <n> · ⏎ import them, one by one` with each name on its own
indented line; several files with a PDF among them read `files · <n> · ⏎ take them, one by one`,
each name followed by its kind, `· bank download` or `· statement PDF`.
The footer reads `esc Cancel  ⏎ Import`, or `esc Cancel  ⏎ Upload` for one statement PDF
(`ctrl+s` is off while files are in the bar). `↵` stages nothing: it hands the paths to
`LogBarScreen.import_bank_files`, which starts each file's way in drop order (§2 "The import
door", "A statement PDF closes its month"). Editing the line back to anything else returns
the bar to quick-add on the same keystroke.

**The Edit form's own keys** ([edit_form.py](../expense/tui/screens/edit_form.py)): the bar
form's keymap ("The bar forms' keys" below) with two more, each shown only
where it works (`check_action`): `ctrl+n` adds a part and `ctrl+x` drops the part the bar is
on, both off where the line's `edit_limits` holds `parts_fixed`, and `ctrl+x` only on a part's
line while the table holds two parts or more. On a part's line `ctrl+x` drops the part in place
of the bar's own cut. The footer reads `esc Cancel  ^s Save  ⇥ Field  ^n Add part`, then
`^x Drop part` where it works. There is no `?`: forms take no `HelpBindingMixin`, and the bar
takes `?` as a character.

**The LOG bar's account is one row per account.** `QuickAddRefs.quickadd_accounts`
(reads.py) hands the parse one row per account, `(id, name, (code, …))`, in the engine's
order, the currencies each holds as the engine gives them. `$` names the account by the
`name` the engine sends ([quickadd/parse.py](../expense/quickadd/parse.py)): a word or part
of one, an exact name winning, so a card holding soles and dollars is one match and the
picker lists accounts by name alone. While `$bcp` is typed and an account is named `BCP`
beside `BCP-5678`, the list still offers `BCP` and every `BCP-…`, and the pick resolves to
itself. `$` and exactly four digits that are the last 4 of one of an account's `numbers`,
current or earlier (read as sent, never parsed from the name), find that account, several
listed when several hold them; any other digits after `$` stay money (`$56` is 56.00). The
currency is the `%` token below. The save sends `account_id` on every batch item, and
`currency_code` on the items whose line typed a `%` (contract: POST /v1/transactions/batch).
The staged table's columns are `date  title  amount  cur  account  category  tags`: `cur` is
the row's `currency_code`, as the Transactions ledger's `Cur` column draws it, and the account
cell names the account alone. The title and tags give way 3:2 when the rows are wider than the
bar, as the ledger's Title and Hashtags do (cut with `…`); the marker, date, amount, `cur`,
account and category keep their whole width (`STAGED_FLEX` in
[log_bar.py](../expense/tui/screens/log_bar.py)). The staged totals add up per currency from
each row's `currency_code`.

**The line's currency is a token of its own, `%`** ([quickadd/parse.py](../expense/quickadd/parse.py)):
`Streamly $visa inventada @suscripcion -12.99 hoy %usd`. It is first-wins like `$` and may stand
anywhere in the line. The parse reads it against the currencies of the account the line names:
a whole or partial code picks one by the same matching as every name, and a bare `%` names
none yet and lists them all. A well-formed code the account does not hold is upper-cased and
sent, and the engine refuses it
(contract: POST /v1/transactions, "`account_id` and `currency_code`"). A line with no `%` sends no `currency_code` (never a `null`) and the
engine fills an account's only currency (contract: POST /v1/transactions, "`account_id` and `currency_code`"); the staged
row still shows it. When the account holds several, routing refuses the line and
never stages it on a guessed currency: under the bar
`! not staged — Visa Inventada holds PEN and USD: pick one` (`route.py`), the hint reads `not
staged — pick a currency and press ↵ again`, and the account's currencies stand under it as a
picker open at the end of the line, so `↑↓` and `↵` write ` %USD` into it and `↵` again stages it.
`%` is pickable like `$`, `@` and `#`: it is painted in the accent, a bare `%` (or a partial code
matching several) opens the picker on the account's own currencies, and `↵` writes the code
(`%USD`) into the line. A `%` word matching none of them (`%zz`) is refused as `"%zz" matches no
currencies`, with nothing to pick. The pick-a-currency hint shows only when the
currency is the line's sole problem; a line refused for anything else as well (no amount, a name
that matches nothing, a date ahead) gets the plain hint `not staged — fix the line and press ↵
again`, the picker staying open under it.

**The legend row.** One fixed row under the bar carrying the whole grammar, on one line at 80
columns and wider: `$account · %currency · @category · #tag · ±amount · //note · when`. It
never changes, so nothing below it moves; everything that *does* change (the amount echo,
the resolved date in words, how many names a token matches, loading/writing) is the
`#hint` row above it. What `↵` does is in the footer, `esc Cancel  ⏎ Stage  ^s Save`.

**The account peek.** Once the typed line names an account and its currency (typed, or the
account's only one), that pick's posted ledger fills the room under the staged list —
`AccountPeek`, five columns (date, title, amount, category, tags; no account column), titled
with the pick's label on one line. The title and the count line both shorten only the account
name with `…` when too long for the panel, the currency whole:
`3 of 48 in VISA Infinite Sapphire · USD · newest first`, `nothing in … yet`,
`48 in … · no room to show them`.

* **Elastic.** The panel draws exactly the rows the staged list leaves, again on every
  resize. The empty-state invitation stands down while it is up.
* **The pick is the bar's**, never a staged row's — while a `%` picker is open, the account
  the line names with the highlighted currency, so the panel swaps as you arrow; while a `$`
  picker is open, the highlighted account if it holds one currency; nothing at all when the
  token resolves to nothing, or the account holds several and none is typed yet.
* **It stays put.** `↵` clears the bar; the panel keeps the last pick the bar named.

Read-only: no cursor, no keys, `↑↓` stay with the staged list. One debounced
`GET /transactions?account_id=…&currency_code=…` (contract: GET /v1/transactions) and its
count per pick, cached for the screen; a save invalidates what it wrote to, and a failed read
shows its message in the panel and is not retried.

**The bar forms' keys** (`form_bindings` in [_form.py](../expense/tui/screens/_form.py),
one copy for every bar form: the Edit form, the create/edit forms, the new-statement form
and Setup; the Edit form adds the keys "The Edit form's own keys" above names):
`⏎` keeps the field and moves one line on, to the next field that can change; when no field
ahead can change (on the last field, or with only read-only fields after it) it saves the form
as `ctrl+s` does (`FormScreen._advance`). Textual runs the `on_input_submitted` of every class
in a screen's MRO on one `⏎`, so a form whose handler overrides an inherited one calls it
itself and prevents the message's default. `ctrl+s` first keeps what was
typed in the bar on the current line exactly as `⏎` does (same reading, same note), without
moving on, then saves the form (`FormScreen._keep_bar`). A value `⏎` would refuse stops the
save the same way: its note shows, the cursor stays and nothing is sent. A line nobody typed
on, or a read-only one, keeps nothing; a suggestion highlighted with `↑`/`↓` but not typed
counts as untouched. `esc` cancels. `tab` moves to the next field and `shift+tab` to the
previous, on every field, whether or not a suggestion list is open; `FormScreen` is
`inherit_bindings=False`, so the bar keeps focus. Plain `↑`/`↓` walk the suggestion list when
the field has a non-empty one and move to the previous/next field when it has none.
`ctrl+↑`/`ctrl+↓` also move fields but are never advertised: macOS claims `⌃↑` (Mission
Control) and `⌃↓` (Application Windows) before the terminal sees them. Every field move skips
read-only fields and stops at either end. On a read-only field, where the bar sits only when
every field is read-only, the bar (`FormBar`) takes nothing typed, pasted or deleted, and `⏎`
keeps nothing and moves on as from any line (with nothing ahead to change, it saves).
**A refused save shows under the form**, below the summary and above the footer: `Failed`
bold, then the engine's words as the shared error text gives them, in the text colour, with
a bar in the error colour down the left of each line, wrapping at the form's width
(`FormScreen._show_refusal`). It stays until the next key, which does what it always does;
nothing typed is lost, and the cursor goes to the line the refusal names. No toast repeats
it. While no suggestion list shows, its rows are gone and one blank line stands under the
hint, so the block fits under the New statement form at 80×24. The Edit forms of the ledger
(a transaction's and a bank line's) and Setup lay their refusal out under their own lines
instead.
**No hint says "save" on a line where `⏎` moves on, and none says "go on" on a line where
`⏎` saves** (`FormScreen._goes_on`; guard:
[test_tui_form_hints.py](../tests/unit/test_tui_form_hints.py), which walks every bar form).
The hints live beside each form (the Manage forms' in
[create_forms.py](../expense/tui/screens/create_forms.py)). Some lines where `⏎` saves say so:
a new category's COLOR, the Edit form's last NOTE, a new statement's END BALANCE, and the Edit
form's TITLE when no line after it can change; others, such as Edit category's COLOR and
Setup's last line, leave it unsaid.
The footer reads `esc Cancel  ^s Save  ⇥ Field` (`Create` on a create form; the Edit form's
own keys after them):
**`⇥ Field` is the form's one navigation footer slot**, because forms have no `?` card
that could list the other keys. Guarded by `test_form_navigation_keys_are_not_advertised`.
**Setup's footer** reads `esc Quit  ^s Connect  ⇥ Field`: there is no screen of its own
under it to go back to, so `esc` leaves the app, and `^s` reads `Create` once the engine
asks for a profile. Its address and key are read-only once the engine has accepted them.

**The footer never advertises the arrow keys.** `Navigate` is declared `show=False` on
`CursorList` and `CheckList`. The keys work unchanged and the `?` card still lists them.
`pgdn`/`pgup` and `→ ←` expand/collapse **stay** in the footer: they are not obvious (the
import preview's `pgdn`/`pgup`, hinted in its body, are the exception). New bindings inherit
this rule — if a key only says "the cursor moves", it does not get a footer slot.

**One key per job.** No movement aliases (`j k h l`, `,` `.`) and no `[`/`]` — a widget
alias silently outranks a screen binding, so letters stay free as *command* keys. Guarded
by [test_tui_help.py](../tests/unit/test_tui_help.py)
(`test_no_duplicate_movement_key_aliases`, `test_square_brackets_are_not_bound_anywhere`).

**A screen key that a focused `Input` also claims needs `priority=True`.** Textual
resolves the focused widget's bindings before the screen's, and `Input` binds more
chords than it looks like — `ctrl+x` is `cut`, `ctrl+k`/`ctrl+u`/`ctrl+w` are line
edits, `ctrl+a`/`ctrl+e` are home/end. The LOG bar's `ctrl+x drop row`
([log_bar.py](../expense/tui/screens/log_bar.py)) would otherwise edit the line
instead of dropping the staged row. Plain `↑`/`↓` and `escape` need nothing — `Input` does not bind them — and `⏎` arrives
as `Input.Submitted`, not as a binding at all.

**Standing constraint:** any future rename action on Manage screens ships as `e`,
never `r`.

**App-wide keys are `^q` and `?`.** `^q` quits, asking first while saves are still being
sent (§1 "Quitting asks while saves are still being sent"). `?` opens `HelpModal`, a
two-column card whose content is **derived** from BINDINGS by walking the screen's and the
focused widget's MRO and keeping only classes declared under `expense.tui`. `Binding.tooltip`
carries the card's fuller wording (`Archive / unarchive`) while `description` stays the
terse footer label (`Archive`). The card lists only bindings in play
([help.py](../expense/tui/screens/help.py) `listed_bindings` says which it leaves out): a key in
`CARD_FOLLOWS_CHECK` follows the footer — the keys that are off in some states on the
Statements screen and its panel, a statement's `space`, `c`, `u` and `f` ("A statement's
screen" above), and the Statements account list's `pgdn` and `pgup` while they page nothing —
and one in `CARD_NEEDS_A_ROW` waits for a row, as in the footer (§5 "A key with no row to act
on leaves the footer"): an empty ledger's card holds only `+`, `r` and `esc  Back`, the wording
`CARD_TEXT_WHILE_EMPTY` gives its `esc` (with rows, `Clear the selection, else go back`), and
an empty Manage list's `n`, `r` and `esc`, with no "Moving around" column. The card covers
what is behind it from its top rule to its bottom one across the full width, so the gutters
beside its frame are blank. A card taller than the room between the head and the footer
spreads out on a terminal wide enough, and only then: the groups three across, no key row
wrapped, inset from the terminal's sides. One still too tall scrolls on `↓` / `↑` between
its two rules, a dim `▲ N lines above` / `▼ N more lines` row saying what is hidden
([help.py](../expense/tui/screens/help.py) `scroll_window`). `?` is bound per screen root via `HelpBindingMixin`,
**never on the App** — letters bubble up from lists, the same reason there is no app-level
`q` (it is scoped to Home). **Forms have no help key**: a focused `Input` swallows printable
keys, so `?` would type a question mark. The Textual command palette is off
([decisions.md](decisions.md) "The command palette is removed"). The mouse is off, and launch
wipes the screen and scrollback ([decisions.md](decisions.md) "TUI is keyboard-only",
"The app clears the terminal scrollback at launch").

---

## 5. Pagination and terminal size

Every `CursorList` / `CheckList` renders one window of **min(`PAGE_ROWS_CAP`, what fits
the terminal)** rows — the page IS the screenful, so the page status and footer never
clip and no dead scrollbar appears; a resize re-measures and keeps the first visible row
([decisions.md](decisions.md) "TUI rows-per-page adapt to the terminal"). `DEFAULT_PAGE_ROWS`
(20, one copy in [reads.py](../expense/reads.py)) is the app-wide cap, except on
**Transactions, which fills the window** in both directions
([decisions.md](decisions.md) "The ledger fills the window"), its Title, Description and
Hashtags giving way 3:3:2 before the numbers on a narrow terminal
([decisions.md](decisions.md) "Ledger cells fill their columns"). `LIST_FRAME_LINES` is
**derived from the render** by `test_the_frame_costs_exactly_list_frame_lines`.

**Transactions is one list that grows**,
through `GrowingRead` in [_growing.py](../expense/tui/screens/_growing.py): it opens with
the newest `GROW_STEP` (10) rows and the count, read together — a count that cannot be
read fails the screen — and `pgdn` (footer: `pgdn 10 more`) appends the next 10 by the
engine's cursor, with no recount, the cursor landing on the first new row; at the end it
leaves the footer. `↑`/`↓` scroll everything loaded and `pgup` goes up a screenful. A resize
reads nothing. After a write (a bulk key, the `⏎` edit, `+`, `s`, `d`) it starts over from
the newest 10 with the cursor on row 1, as `r` does. Leaving the `⏎` form with `esc` is not
a write: nothing is read and the list comes back as it was, the rows `pgdn` loaded and the
cursor on its row. The "no statement" list on Statements grows through the same `GrowingRead`
(§2).

**Full-data screens window locally** — Manage, the Statements account list (full
height alone, an equal split with the open panel), a statement's list at what fits —
with `pgdn` next page and `pgup` previous; `↑`/`↓` walk through and cursor-restore lands on
its page. Exempt: Home's month grid, static tables, System kv-tables.

**`pgup` shows only where there is something before**, on every list, growing or paged: the
footer leaves it off on the first page or screenful. A paged list that one page holds shows
neither page key.

**The frame:** the breadcrumb on the first line with no blank line above it, the rule
directly under it, then one blank line and the content. A statement's screen puts its head
right under the rule.

**The Statements screens fit 80×24.** The browse's panel pages to fit, below the floor
(`panel_page_rows` in [statements.py](../expense/tui/screens/statements.py)):
four accounts and three statements fit on one page, and with five accounts the panel pages
instead of scrolling `#content`, whose scrollbar would cut the Order column; a caption a long
account name wraps is counted. The "no statement" list draws no page status
(`UNFILED_FRAME_LINES`) and fills the room the accounts leave, down to the blank line above
the footer; its caption's `N of M loaded` says the rest. A statement's list is measured again
after every layout of the screen, beneath a box too, so it fills the room the head, a refused
complete's lines, the close's notes and the `⚑` line leave, whichever of them shows; the rows
set apart count toward the page, so its page status always shows.

**A footer too wide for the screen** tightens its spacing first (one space between keys), and
when the keys are still too wide, whole keys leave it from the end, so none is ever drawn cut.
A key left out still works, and the `?` card lists it on a screen that has one. Every screen's
footer is the `FittingFooter` ([footer.py](../expense/tui/widgets/footer.py)).

**A key with no row to act on leaves the footer, and returns with the first row.** On an empty
ledger, Statements account list, Accounts, Categories or Hashtags list the footer is
`esc Back  r Refresh  ? Keys` and the screen's add key (`+ Add` on the ledger, `n New`
elsewhere): no `⏎`, no `space`, no key that acts on a row. The Statements panel keeps its own
keys and loses only the row ones: an account's empty statements read
`esc Close the panel  r Refresh  ? Keys  n New  u No statement`, and its empty rows in no
statement `esc Back  r Refresh  ? Keys` (`d Delete` leaves too). The `?` card leaves out the
same keys (§4 "App-wide keys are `^q` and `?`"). A list screen's `check_action` answers
`False`, not `None`, for such a key, because `None` leaves it in the footer dimmed; `None` is
kept for a key that is off only for a moment (the ledger's `pick` while a bulk write runs). A
list's own keys follow its `CARD_NEEDS_A_ROW` (`waits_for_a_row` in
[cursor_list.py](../expense/tui/widgets/cursor_list.py); guard:
`test_the_footer_and_the_card_agree_on_an_empty_screen` in [test_tui_help.py](../tests/unit/test_tui_help.py)).

**Minimum terminal size: there is no guard.** The screens are designed at 80×24; the app
degrades silently below it, columns ellipsised and rows clipped, never reflowed
([decisions.md](decisions.md) "A terminal too small is the user's to fix").
`PAGE_ROWS_FLOOR = 5` floors the *requested page size*, not the viewport — it cannot make
rows fit that do not. Width has **no** floor of any kind.

---

## 6. Test conventions

Beside [CLAUDE.md](../CLAUDE.md) "Testing conventions". The shared builders, fakes and
waits are in [tests/unit/helpers.py](../tests/unit/helpers.py); each docstring there says
what it does.

- **A pilot test waits on a condition, never on the clock:** `wait_for`, `wait_for_list`,
  `wait_for_loaded`. Wait for the thing the test is about: a save is over when its request
  was sent *and* `_saving` is false again. A **bare** `pilot.pause()` is for asserting a
  *non-event* (an inert key), where no predicate can be written; a timed `pilot.pause(<n>)`
  is a guess at the app's speed, so the test says why.
- **A bar's value goes in through `enter_values`** unless typing is what the test proves (its docstring).
- **Patch `load_*_name_map` at the screen module** (`expense.tui.screens.X.load_…`), not at
  `expense.reads`, when the point is name display; otherwise use the short-id fallback.
- **A test that reads what a toast shows runs with `run_app(..., toasts=True)`** and reads
  `toasts_shown(app)`; a test that only needs what was sent patches `notify`.
- **A test varies an account with `account_with_currencies(base, field=…)`**, passing only
  the fields it is about; no test file defines an account builder of its own.

**Known, accepted:** a screen load may open several short-lived clients (Transactions:
the page and three name maps; the bulk pick's reference lists load once, on the first
bulk key) — harmless on loopback.
