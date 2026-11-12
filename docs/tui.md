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

**Stepping past ACCOUNT, CURRENCY or CATEGORY keeps them:** the highlight opens on the line's
own value, so `⏎` with nothing typed keeps it, and `⏎` on every line then `ctrl+s` send nothing
and say `No changes to save.` The "no statement" form works the same (`_recompute` in
[edit_form.py](../expense/tui/screens/edit_form.py)).

**A move takes a row out of its statement.** The engine wants the assignment said on an account
change, so `b` and the Edit form send `statement_id: null` for a row whose account or currency
changes, and a currency move alone keeps the statement (`unassign_on_move`, `bulk_writes`). The
form sends no `null` except `operation_code` and that `statement_id`; an emptied note goes as
`description: ""` (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is
updated in place").

**A date the form can't read is refused at `⏎`,** on both Edit forms, with the reader the save
uses (`is_readable_date` in [dates.py](../expense/dates.py)); the line keeps its value, so a
`ctrl+s` after it never sends the unread date.

**An opening balance stays on its account and in @Opening.** The engine refuses to move such a
row to another account or category, `@Pendiente` included (contract: PUT
/v1/transactions/{transaction_id}, "Opening balances stay put"), gives it no hashtag, not even
the pending one (contract: PUT /v1/transactions/{transaction_id}), and keeps its bank line's one
part (contract: PUT /v1/bank-lines/{bank_line_id}, "A line holding an opening balance keeps its
parts"). `b`, `c`, `h` and `m` send such a row like any other: the engine refuses it, the other
rows go and it stays selected. The LOG bar cannot name @Opening.

**A split transaction says what reaches every part.** The engine writes a line's date, title,
operation, account and currency onto every part, while amount, category, hashtags and note stay
each part's own (contract: "Transactions (Ledger)", "Bank lines"). In the ledger's bulk keys `c`
and `h` change only the selected parts, `b` on one part moves the whole transaction, every part
leaving its statement, and `m` moves every part to the currency, each keeping its statement
(contract: PUT /v1/transactions/{transaction_id}, "Line fields"). One `PUT` per selected row;
with every part selected a later `PUT` finds the line already moved and is accepted as it is,
since it carries no `version`.

**A refused save stays under the parts** until something changes (`refusal_lines`).
`SPLIT_TOTAL_MISMATCH` is keyed `parts`, and every `parts.<i>.amount_cents` says only that the
parts must add up to the line's total (contract: PUT /v1/bank-lines/{bank_line_id}, "The
total"). **What is read-only is the line's `edit_limits`, and nothing else**; the app keeps no
copy of the engine's locking rules (contract: GET /v1/bank-lines/{bank_line_id}, "Response
fields").

**The pending hashtag never rides beside a real one.** The engine refuses it together with
another hashtag (`PENDING_HASHTAG_NOT_ALONE`) and replaces it when a real set is written
(contract: "Transactions (Ledger)", "Hashtags on a transaction"); `hashtags_to_send` in
[reads.py](../expense/reads.py) is the one helper.

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
matches its rows against the ledger and refuses what it cannot take (contract: POST
/v1/transactions/import). Every row of the file goes in, whatever its date. **Export the
download with an explicit date range covering everything since the last import, never the
bank's default view:** BCP's current-account default is the last 20 movements, about twelve
days on `BCP PEN`, nothing can detect rows a file does not contain, and the month's statement
is the only backstop.

`↵` on the LOG bar's dropped files (§4 "A dropped bank file") reads every file first, so an
unreadable one stops the run before any is written. Each file then goes through three full
screens above the LOG bar: which account (asked every time), the preview, the result; the
module docstring says what each draws. A pick sends `account_id` and the engine files each row
under the currency the file names (contract: POST /v1/transactions/import, "Accounts"). **A
row's mark and reason come from the engine's `outcome`, never from the reason's words**
(`row_verdict`); every count is the engine's.

**The days where the file and the ledger disagree** are the engine's `day_mismatches`, a report
on the preview alone that changes nothing `⏎` writes. A day is reported when its file total and
its ledger total after the import differ, or when it holds a ledger line no file row claimed,
so a day with equal totals can be one (contract: POST /v1/transactions/import). The upload
removes nothing and asks nothing about such a row; it stays out of that month's statement,
where it is deleted.

**A refused file** shows on the preview in the engine's words (`refusal_lines`,
`names_its_row`), nothing written. A `CONCURRENT_CHANGE` on a `rows.<row>` key means a matched
ledger line changed while the import ran (contract: POST /v1/transactions/import,
"Concurrency"); `⏎ Preview again` asks for a fresh dry run, and nothing is sent again without
one.

**Several files**, of either kind, go one by one in drop order in one run. `esc` before a file
is written cancels it and every file after it (`cancel_label`); a file already imported stays
imported. `⏎ Home` leaves through the LOG bar's discard question when rows are staged, and Home
reads afresh (`HomeScreen.start_fresh`).

**The import screens' keys.** `⏎ Import N rows` on the preview is the one key on an import
screen that changes data (`⏎ Close <name>` on a statement PDF's), named in the footer. There is
no `r` and no `?`: they do not take `HelpBindingMixin`, so the footer is their whole key list.

**A statement PDF closes its month**
([statement_upload.py](../expense/tui/screens/statement_upload.py)). A `.pdf` dropped on the
LOG bar (§4 "A dropped bank file") is a month's statement: the app sends it whole and reads
nothing in it, and the engine matches each row to a ledger line, creates the lines the ledger
lacks, takes out of the month's open statement the lines the paper does not print, orders every
line as the paper does and completes the statement, every currency the paper covers together,
creating it or filling its open draft (contract: POST /v1/statements/import). The account is
the one you pick: the engine never picks it by the number the paper prints
(contract: POST /v1/statements/import, "Accounts"). Three full screens work as a download's;
the module docstring says what they draw.

`f` on the screen after the close opens the flagged lines' screen ("The lines a complete flagged
for review" in §4). A refused upload shows the engine's words under the preview once, with no
`Failed` toast; a `CONCURRENT_CHANGE` on any key (`changed_meanwhile`) offers `⏎ Preview again`.
One refused for leftover lines (`LOOSE_LINES_ON_SEALED_DAYS` on `file`) opens
[leftover_lines.py](../expense/tui/screens/leftover_lines.py) in place of the preview.

**Accounts stand in the engine's order everywhere.** Every screen shows accounts as
`GET /accounts` lists them, every account that is not a person first, then every person
(contract: GET /v1/accounts); no screen sorts them, and a person is an account whose `kind` is
`person`, never told by name. The LOG bar's `$` picker, the Edit form's account field and the
ledger's `b` pick offer no archived account (`QuickAddRefs.quickadd_accounts`): the engine
refuses one as a transaction's `account_id` (contract: POST /v1/accounts/{account_id}/archive).

**On an archived account's row the ledger offers no `d`.** The engine deletes none of
an archived account's transactions (contract: POST /v1/accounts/{account_id}/archive), so with
the cursor on one `d Delete` leaves the footer and the key does nothing; every other key
stays, and the engine judges each write. The ledger learns which accounts are archived from
the same `GET /accounts` that gives it the names (`reads.load_account_index`).

**On an archived account's line the Edit form changes the categorisation alone.**
Such a line keeps its parts and their amounts, and every line field sent is refused but a title
or operation code filled while it is empty
(contract: PUT /v1/bank-lines/{bank_line_id}, "A line with a part on an archived account keeps its parts and their amounts")
(contract: PUT /v1/bank-lines/{bank_line_id}, "Rules"). The form reads it from the line's
`edit_limits`.

**Manage ▸ Categories and Manage ▸ Hashtags mark the built-in rows**, the ones with a
`system_key`, never found by name (`reads.is_system_row`). They keep their names and are never
deleted (contract: PUT /v1/categories/{category_id}, "A system category keeps its name")
(contract: PUT /v1/hashtags/{hashtag_id}, "The pending hashtag keeps its name"), so with the
cursor on one the footer offers neither `e Edit` nor `d Delete` (`ResourceListScreen.is_fixed`).

**Manage ▸ Accounts** lists every account, people and archived ones too, with a balance column
per currency the engine lists, never summed (contract: GET /v1/currencies); the module
docstring of [accounts.py](../expense/tui/screens/accounts.py) holds the columns and keys.
`e`, `a`, `t` and `d` act on the whole account, every currency at once
(contract: POST /v1/accounts/{account_id}/archive, "Every currency at once"). Archive asks
nothing ([decisions.md](decisions.md) "Archive is a prompt-free toggle"). `a`, `t`, `c` and `x`
share one guard, one write at a time (`run_guarded_write`).

**`t` turns an account into a person and back,** asking for what the engine needs: a person's
name, or a bank and an optional last 4 (`QuestionModal`). The app checks nothing; a refusal
keyed on a line of the question keeps it open
(contract: POST /v1/accounts/{account_id}/make-person, "Body")
(contract: POST /v1/accounts/{account_id}/make-account, "Body").

**`c` adds a currency to an account** from the engine's currencies it does not hold, at once,
with no question (contract: POST /v1/accounts/{account_id}/currencies). An archived account's
refusal is the engine's to give, not the app's.

**`x` removes a currency from an account,** after `ConfirmModal` asks (`removal_question`); only
`y` sends it (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}). The two
`404 NOT_FOUND` answers, `account not found.` and `currency <code> not found.`, show as any
refusal (contract: DELETE /v1/accounts/{account_id}/currencies/{currency_code}, "Refusals").

**Stepping past COLOR keeps it** on the Edit screens of Manage ▸ Categories and Manage ▸
Accounts: the highlight opens on the row's own swatch, and the save sends `color` only when
another swatch was picked (`_edit_payload` in
[create_forms.py](../expense/tui/screens/create_forms.py)). On New account and New category
COLOR is optional, and a skipped colour is left out of the body, never sent as null, so the
engine gives its default (contract: POST /v1/categories). Edit category keeps it required, so
a `PUT` never sends null.

**`d` is the TUI's one destructive key.** It deletes the row under the cursor, never a
selection, on Manage ▸ Accounts, Categories and Hashtags (a built-in row aside), on the ledger,
in the statement's "no statement" list, on a statement's flagged lines and on an upload's
leftover lines; when the ledger turns it off: §4 "The ledger's selection keys". Every delete
asks first with `ConfirmModal`: only `y` deletes, and the question names the row and says
**no screen can bring it back** (each screen's code holds its question). A hashtag's question
names the cascade, since the engine never refuses that delete for being in use
(contract: DELETE /v1/hashtags/{hashtag_id}). On Accounts the delete acts on the whole account
(contract: "What an account is", "An account is deleted whole"). On the ledger `d` reads the
row's line first (`reads.fetch_bank_line`, contract: GET /v1/bank-lines/{bank_line_id}), and a
split transaction goes whole in one `DELETE /bank-lines/{id}`
(contract: DELETE /v1/bank-lines/{bank_line_id}). A refused delete leaves the row and the list
as they were.

**When the engine says no.** Every refusal with code `CONFLICT`, `FORBIDDEN` or
`LIMIT_REACHED` names the rule that fired in `reasons`, keyed by the thing refused
(contract: "Base Conventions", "`fields`, `reasons` and `details` semantics"). The note shows
the engine's words whole, and for a reason `NEXT_STEPS` in [errors.py](../expense/errors.py)
lists, a blank line and one line of the app's saying what to do (contract: "Error reasons");
that table holds every line and the reason's key. The line is chosen by the error's `code` and
reason alone, never by the HTTP status, the route or the engine's wording
([decisions.md](decisions.md) "Hints are chosen by the engine's reasons, never its wording").
Where the screen picks between two lines of one reason: `list_refusal_text`,
`changed_while_running` and `changed_meanwhile`.

**The engine's words show as text, never as styling.** A `[like this]` in a refusal, a warning or
a name is never read as markup: lines are Rich `Text`, lists draw names through `list_cell`, a
toast of the engine's words goes through `toast` in
[refusal.py](../expense/tui/widgets/refusal.py), and the ledger's bulk edit note alone styles
them, through `as_markup`. Guards:
[test_tui_bracketed_names.py](../tests/unit/test_tui_bracketed_names.py),
[test_toast_words.py](../tests/unit/test_toast_words.py) and
[test_tui_engine_words.py](../tests/unit/test_tui_engine_words.py).

**"Saved" means the engine holds the row.** The LOG bar ticks a row only when the engine
created it, or refused it only because the row's own id is taken (`ID_EXISTS` on its
`transactions.<i>.id` and nothing else): a replay of a save whose answer was lost. Any other
refusal keeps no `✓` (`errors.is_own_id_replay`; [runtime.md](runtime.md) "Bulk writes").

**Refused rows read one line per kind of error** under the table (`save_errors`), the rows it hit
beside it ([runtime.md](runtime.md) "How refused rows read").

**The ledger's bulk edit reads its refused rows the same way** (`b`, `c`, `h`, `m`), one toast
per kind (`refusal_notes` in [transactions.py](../expense/tui/screens/transactions.py)); a
refusal of every further write (`SETTINGS_MISSING`) is no row's and shows once, after them
(`run_stopped`).

**The New form makes an account, its currencies and their openings in one write** (`n` on
Manage ▸ Accounts; `NewAccountScreen` in [create_forms.py](../expense/tui/screens/create_forms.py)).
A bank or cash account has no `name` line: the engine builds its name (contract: POST
/v1/accounts, "The name"). The save is one `POST /accounts`, whole or not at all
(contract: POST /v1/accounts, "Required")
(contract: POST /v1/accounts, "Optional"). A name already taken by a bank account is keyed
`last4` or `bank_code` (contract: POST /v1/accounts, "Validation").

**A bank account's Edit form holds its number on three lines,** `bank`, `last 4` and `since`,
with `cards before`, `new card` and `new card from` for a replacement
(`EditAccountScreen`'s docstring). The app checks nothing typed on them
(contract: PUT /v1/accounts/{account_id}, "The numbers"). Emptying `last 4` on an account that
has a number removes it, after `ConfirmModal` asks; only `y` sends `current_number: null`.

**A bank account's statement code is a line of its own on New and Edit,** on a bank account
only: the engine lets a person carry a code too
(contract: "What an account is", "A person carries a code like a bank account"), and these
forms offer it none. Small letters show as capitals while typing (`FormScreen._typed`). On New
a skipped code is left out of the body, never sent as `null` (contract: POST /v1/accounts). On
Edit, emptying it sends `statement_code: null`, which clears the code with no question: typing
it again brings every statement line back (contract: PUT /v1/accounts/{account_id},
"`statement_code`").

**An account's opening balance lives on its Edit form, one per currency:** two optional lines
per currency, in the engine's order (contract: "Bank Accounts", "Per-currency order"), `PEN
opening` and `PEN as of`. A bank account's form has no `name` line: a `name` sent for it is
refused (contract: PUT /v1/accounts/{account_id}).

- **The amount is signed and taken as typed**; the app never adds or flips a sign.
- **A currency that has one opens with its pair filled:** the account's `currencies` name each
  opening balance by id, or `null` (contract: "Bank Accounts", "`currencies`"), and the form
  reads it with `GET /transactions/{id}?debit_as_negative=true` (`reads.fetch_transaction`),
  so the amount arrives signed and nothing reads the sign off `transaction_type`
  (contract: "Base Conventions", "Sign convention — responses").
- **A save is one `PUT /accounts/{id}`**, all or nothing
  (contract: PUT /v1/accounts/{account_id}, "`opening_balances`"), carrying only what changed.
  Emptying the amount of an existing one clears it, after `ConfirmModal` asks.
- **Every Manage Edit form that wrote** dismisses with `True` and the list starts over; one
  closed with `esc` before any write keeps the edited row selected
  (`ResourceListScreen._edited`).

**No cards. No vertical lines. Horizontal rules divide sections.** Nothing is drawn inside a
box, not a modal, a list panel, the input bar or a plain yes/no `ConfirmModal`; a horizontal rule
is the divider (the header's `border-bottom` is the pattern); a question that needs room becomes
a screen, not a card.

**List chrome is content.** A list's page status (`rows 21-40 of 133 · page 2 of 7`) is
drawn as ordinary content by `WindowedList.framed()`
([windowed.py](../expense/tui/widgets/windowed.py)): a plain rule opens the section, the page
status sits dim beneath the rows, and there is no title, the breadcrumb already naming the
screen. The status line is drawn on every windowed list, blank when there is nothing to say (off
in the Statements "no statement" mode, `set_status_line(False)`),
fixed per list or mode, never by rows, since `AdaptiveRowsMixin` measures the widget's height.
**The rule passes an explicit style**: Rich's default `rule.line` resolves to a literal green
that `test_no_literal_color_styles_in_tui` cannot see, because it greps source rather than
renders.

⚠️ **One exception.** A title that is *chrome* disappears; one that is *information*
becomes a line of content above the rule: the Statements browse's caption
(`Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest`) is the only thing tying the
lower rows to an account above. Ask "would the screen still be unambiguous without this?" — not
"is this a title?".

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
