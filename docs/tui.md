# The TUI — `expense`

What the Textual app **is**. `expense`, run alone, opens it: the one surface of this client
([decisions.md](decisions.md) "The TUI is the only surface"), over the shared fetch/write layer,
with **zero** business logic. Companions: [commands.md](commands.md) (the typed surface),
[runtime.md](runtime.md) (read/write semantics, which apply here unchanged),
[decisions.md](decisions.md) (why). Every screen is mocked before it is built
([CLAUDE.md](../CLAUDE.md) "Mock every screen before building it — every time").

---

## 1. Architecture

Under `expense/tui/`, one screen per module in `screens/`; each module's docstring says what it
holds. The shared plumbing: `app.py` (ExpenseApp: screen stack, global keys, launch),
`theme.py`, `dropped.py`; `widgets/` (`header.py`, `cells.py`, `windowed.py`, `cursor_list.py`,
`checklist.py`, `footer.py`, `picker.py`, `refusal.py`, `parts_table.py`, `typed_input.py`); and in `screens/`
`_base.py` (SectionScreen, EngineWriteMixin, ResourceListScreen, NewestReadMixin,
`call_while_attached`, keymap mixins), `_form.py` (FormScreen, `form_bindings`), `_growing.py`
(GrowingRead), `help.py` (the `?` card), `modals.py`, `create_forms.py`, `edit_form.py`.

**The fetch/draw split is the anti-duplication guardrail.** Every engine read is a pure
`fetch_*(cfg, …) -> dict` the screens call; a screen never reimplements one. The shared homes
are in [CLAUDE.md](../CLAUDE.md) "One copy of everything shared"; none is under
`expense/commands/`, which holds only what `expense import sheet` alone uses.

**One reader for every typed amount.** `parse_amount` in
[quickadd/money.py](../expense/quickadd/money.py) reads every typed amount in the session's
format ([number_format.py](../expense/number_format.py)): the account's `number_format` setting
at launch, else the machine's region (`launch_format` in [region.py](../expense/region.py));
System ▸ Auth & profile `f` changes it. An amount it cannot read is refused, never guessed, and
nothing is sent. A plain number is read at any size and sent as whole cents, so the engine's
`OUT_OF_RANGE` shows in its words (contract: "Money amounts"). A spreadsheet's cells are the
engine's to read: a bank download's (§2 "The import door") and the owner's sheet's
([commands.md](commands.md) "`expense import sheet`").

**Async / workers.** The engine client is synchronous and runs inside a Textual worker
(`@work(thread=True)`), so the UI never blocks. Read screens override `fetch()` (the worker) and
`build(data)`; writes go through `EngineWriteMixin.run_write`, one in flight and an error
dropping the queued rest ([decisions.md](decisions.md) "TUI writes: FIFO queue in
EngineWriteMixin, error drops the queue"). **A thread worker hands back through
`call_while_attached`**, which drops a hand-back whose screen has left
([_base.py](../expense/tui/screens/_base.py) says why). **A read a newer one replaced paints
nothing** (`NewestReadMixin`; [decisions.md](decisions.md) "The app holds its settings from
launch, and only the newest read hands back"). **Invariant: `build()` runs on the UI thread and
must never do HTTP**; names resolve in `fetch()`.

**A write answered after its screen has left still says how it ended** when it carries a
`LeftBehind` ([_base.py](../expense/tui/screens/_base.py)): success as the screen's own toast, a
refusal as a 10-second error toast titled `Not <what did not happen> · <what it was>`; a write
without one is dropped with its screen ([decisions.md](decisions.md) "A save you left still says
how it ended"). Each write that carries one names its words where it is sent, and every write
queued behind a refusal is still sent and shown. When the screen the write changed is the one
shown, it reads again: a Manage form's list from its first page, cursor on row 1, after a save
that landed or whose ending is not known (`may_have_landed`), never after a clear refusal.

**Quitting asks while saves are still being sent.** `ctrl+q`, or `q` on Home, asks first when
any screen, a left one included, has a save sent and not answered; only `y` quits
(`action_quit` in [app.py](../expense/tui/app.py) holds the words).

**Name resolution is live HTTP and fails silently by design.** The `load_*_name_map` functions
return `{}` on any failure ([reads.py](../expense/reads.py) `_load_rows`) and renderers fall back
to 8-char short ids; `load_account_index` also gives the archived ids, so on a failure no `d`
shows in the ledger's footer. No toast, no error: "my tables show hex ids" means the engine is
rejecting reference-list reads (auth or config), never data loss.

### The header rate alert

Every header carries a `!` when today has no exchange rate of its own, so every home-currency
figure on screen is priced at an older day's rate. There is no grace period: it also shows on an
ordinary morning before the engine's fetch job has run. `rate_alert` in
[header.py](../expense/tui/widgets/header.py) says the rest, `reads.rate_is_stale` how it is
read. Guard: [tests/unit/test_rate_alert.py](../tests/unit/test_rate_alert.py).

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

**The Statements browse,** the New statement form and a statement's screen: the module
docstring of [statements.py](../expense/tui/screens/statements.py) holds them, and `?` the keys. Balances
stand per currency, never added together. An archived account is not offered until it is
unarchived. Statements stand in the engine's order, oldest first (contract: "Statements",
"Ordering"). Every balance on the New form is optional: which currency needs one is the engine's
call (contract: POST /v1/statements, "`balances`"). A statement's screen shows a balance not
entered as a dim `—`, never zero (contract: "Statements", "A balance not entered is `null`,
never zero"), over the bank lines in the paper's order, which the app does not sort (contract:
GET /v1/bank-lines, "Ordering"). A tick is one `PUT /transactions/{id}` of `statement_id` on one
part, which moves every part (contract: PUT /v1/transactions/{transaction_id}, "Statement
assignment"). `c`, `u` and `d` act on the whole statement, every currency, in one write each
(contract: POST /v1/statements/{statement_id}/complete) (contract: POST
/v1/statements/{statement_id}/revert) (contract: DELETE /v1/statements/{statement_id}). On an
account with a statement code the engine completes nothing until every line has a place in its
order, and no screen sets the order ([decisions.md](decisions.md) "A card's statement is one
statement, and a month closes from the bank's PDF").

**`c` needs every balance** (contract: POST /v1/statements/{statement_id}/complete, "Every
balance must be entered"). **A refused complete** shows `Couldn't complete` and the engine's
words whole under the head, no toast, until the next key. One naming a missing balance or an
uncovered currency opens the balance boxes for it (`balances_named`); one for lines in no
statement on days it seals opens [leftover_lines.py](../expense/tui/screens/leftover_lines.py).

**The lines a complete flagged for review.** A complete goes through while lines dated in the
statement are in no statement; the app keeps no rule of which and treats none as a refusal. The
count is the engine's, `GET /bank-lines/count` with `unassigned_in_period_of=<statement id>`,
never the answer's `review_lines`; while it is above zero the `⚑` line and `f` show, and after a
complete `FlaggedLinesScreen` opens on its own. The lines stay in the ledger, in no statement.
The flagged lines' screen: `pgdn`/`pgup` page and `r` reads again, none in the footer.

**`u` on the Statements browse swaps the panel for the account's bank lines in no statement,**
any day, every currency together (`account_id` and `unreconciled=true`) (contract: GET
/v1/bank-lines, "Filters"). Why not a filtered ledger: [decisions.md](decisions.md) "Rows in no
statement live in the Statements view, not in a filtered ledger". The list is oldest first
(contract: GET /v1/bank-lines, "Ordering"), grows like the ledger (§5, `GrowingRead`), and M is
`GET /bank-lines/count`, a split transaction counted once (contract: GET /v1/bank-lines/count);
a count that cannot be read fails the pane. `r`, an edit and a delete start again from the
oldest ten. An emptied OPERATION sends `operation_code: null` (contract: PUT
/v1/bank-lines/{bank_line_id}, "Body"). `d` asks with the line the list holds ("`d` is the TUI's
one destructive key" below): a split transaction goes whole in one `DELETE /bank-lines/{id}`
(contract: DELETE /v1/bank-lines/{bank_line_id}), a line never split as its one transaction.

**`+` logs a transaction** — Home and Transactions (`LogTransactionMixin` in
[_base.py](../expense/tui/screens/_base.py)) always open the **LOG bar**: one key, one meaning
([decisions.md](decisions.md) "Logging is a key, not a menu row"). The docstring of
[log_bar.py](../expense/tui/screens/log_bar.py) holds what it stages, refuses and saves, and its
footer is the key list; the grammar is `expense/quickadd/` ([parse.py](../expense/quickadd/parse.py)
for the tokens, `%` included). Whether a line stages is decided by *the line you typed*, refused
in place with the reason. The bar always holds focus, which is why no bare letter is a command
there and why the screen has no `?`.

**A dropped bank file** is a line of nothing but absolute (or `~/`) paths to existing `.xlsx`
or `.pdf` files; one word that is not leaves the whole line quick-add. `↵` then hands the paths
to `LogBarScreen.import_bank_files`, which starts each file's way in drop order (§2 "The import
door", "A statement PDF closes its month"). [dropped.py](../expense/tui/dropped.py) and the
[log_bar.py](../expense/tui/screens/log_bar.py) docstring say the rest.

**The LOG bar's account is one row per account.** `QuickAddRefs.quickadd_accounts` (reads.py)
hands the parse one row per account, `(id, name, (code, …))`, in the engine's order. `$` names the
account by the `name` the engine sends, so a card holding soles and dollars is one match and the
picker lists accounts by name alone; `$` and exactly four digits that are the last 4 of one of an
account's `numbers`, current or earlier, find that account. The currency is the `%` token. The
save sends `account_id` on every batch item, and `currency_code` on the items whose line typed a
`%` (contract: POST /v1/transactions/batch). The staged table's `cur` column is the row's
`currency_code`, and its totals add up per currency.

**The legend row** is `LEGEND` in log_bar.py.

**The account peek** (`AccountPeek`) shows the bar's pick, read through
`GET /transactions?account_id=…&currency_code=…` (contract: GET /v1/transactions).

**The import door — a dropped bank file into the ledger**
([bank_import.py](../expense/tui/screens/bank_import.py)).
The app sends the bank's download whole and reads no cell of it: the engine reads the file,
matches its rows against the ledger and refuses what it cannot take (contract: POST
/v1/transactions/import). Every row of the file goes in, whatever its date. **Export the
download with an explicit date range covering everything since the last import, never the
bank's default view:** BCP's current-account default is the last 20 movements, about twelve
days on `BCP PEN`, nothing can detect rows a file does not contain, and the month's statement
is the only backstop.

`↵` on the LOG bar's dropped files (§2 "A dropped bank file") goes through three full screens
above the LOG bar, each file in drop order: which account (asked every time), the preview, the
result ([bank_import.py](../expense/tui/screens/bank_import.py) says what each draws). A pick
sends `account_id` and the engine files each row under the currency the file names (contract:
POST /v1/transactions/import, "Accounts"). **A row's mark and reason come from the engine's
`outcome`, never from the reason's words** (`row_verdict`); every count is the engine's. A
refused file shows on the preview in the engine's words, nothing written; a `CONCURRENT_CHANGE`
on a `rows.<row>` key means a matched ledger line changed while the import ran (contract: POST
/v1/transactions/import, "Concurrency").

**The import screens' keys.** `⏎ Import N rows` on the preview is the one key on an import
screen that changes data (`⏎ Close <name>` on a statement PDF's), named in the footer. There is
no `r` and no `?`: they do not take `HelpBindingMixin`, so the footer is their whole key list.

**A statement PDF closes its month**
([statement_upload.py](../expense/tui/screens/statement_upload.py)). A `.pdf` dropped on the
LOG bar (§2 "A dropped bank file") is a month's statement: the app sends it whole and reads
nothing in it, and the engine matches each row to a ledger line, creates the lines the ledger
lacks, takes out of the month's open statement the lines the paper does not print, orders every
line as the paper does and completes the statement, every currency the paper covers together,
creating it or filling its open draft (contract: POST /v1/statements/import). The account is
the one you pick: the engine never picks it by the number the paper prints
(contract: POST /v1/statements/import, "Accounts"). Three full screens work as a download's;
the module docstring says what they draw.

`f` on the screen after the close opens the flagged lines' screen ("The lines a complete flagged
for review"). A refused upload shows the engine's words under the preview once, with no
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
name, or a bank code typed in capitals and the last 4 (`QuestionModal`). The app checks
nothing; a refusal keyed on a line of the question keeps it open
(contract: POST /v1/accounts/{account_id}/make-person, "Body")
(contract: POST /v1/accounts/{account_id}/make-account, "Body").

**`c` adds a currency to an account** from the engine's currencies it does not hold, at once,
with no question (contract: POST /v1/accounts/{account_id}/currencies). **`x` removes a currency from an account,** after
`ConfirmModal` asks (`removal_question`); only `y` sends it (contract: DELETE
/v1/accounts/{account_id}/currencies/{currency_code}).

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
asks first as [CLAUDE.md](../CLAUDE.md) "Confirm destructive operations" says, its
`ConfirmModal` naming the row (each screen's code holds its question). A hashtag's question
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
`last4` (contract: POST /v1/accounts, "Validation").

**A bank account's Edit form holds its number on three lines,** `bank`, `last 4` and `since`,
with `cards before`, `new card` and `new card from` for a replacement
(`EditAccountScreen`'s docstring). The app checks nothing typed on them
(contract: PUT /v1/accounts/{account_id}, "The numbers"). Emptying `last 4` removes the number
only while another stays, after `ConfirmModal` asks; only `y` sends `current_number: null`.

**A bank account's statement code is a line of its own on New and Edit,** only while BANK is a
code `GET /banks` lists, the banks whose statement PDFs the engine reads
(contract: "What an account is", "Statement code"). It is on a bank account only: the engine
lets a person carry a code too
(contract: "What an account is", "A person carries a code like a bank account"), and these
forms offer it none. BANK and the code show small letters as capitals while typing
(`FormScreen._typed`); `NewAccountScreen`'s docstring holds the lines. On New a skipped or
hidden code is left out of the body, never sent as `null` (contract: POST /v1/accounts). On
Edit, emptying it sends `statement_code: null`, which clears the code with no question: typing
it again brings every statement line back
(contract: PUT /v1/accounts/{account_id}, "`statement_code`"); a move to a bank the engine
reads no statements of is in `EditAccountScreen`'s docstring.

**An account's opening balance lives on its Edit form, one per currency:** two optional lines
per currency, in the engine's order (contract: "Bank Accounts", "Per-currency order"), `PEN
opening` and `PEN as of`. A bank account's form has no `name` line: a `name` sent for it is
refused (contract: PUT /v1/accounts/{account_id}).

`EditAccountScreen`'s docstring holds the pair's mechanics. **Every Manage Edit form that wrote**
dismisses with `True` and the list starts over; one closed with `esc` before any write keeps the
edited row selected (`ResourceListScreen._edited`).

**No cards. No vertical lines. Horizontal rules divide sections.** Nothing is drawn inside a
box, not a modal, a list panel, the input bar or a plain yes/no `ConfirmModal`; a horizontal rule
is the divider (the header's `border-bottom` is the pattern); a question that needs room becomes
a screen, not a card.

**List chrome is content.** A list's page status (`rows 21-40 of 133 · page 2 of 7`) is drawn
as ordinary content by `WindowedList.framed()`
([windowed.py](../expense/tui/widgets/windowed.py), which says why the status line is fixed per
list or mode and why the rule passes an explicit style): a rule opens the section, the status
sits dim beneath the rows, and there is no title, the breadcrumb already naming the screen.

⚠️ **One exception.** A title that is *chrome* disappears; one that is *information*
becomes a line of content above the rule: the Statements browse's caption
(`Statements · Visa BCP · PEN + USD · VIS   ·   oldest → newest`) is the only thing tying the
lower rows to an account above. Ask "would the screen still be unambiguous without this?" — not
"is this a title?".

---

## 3. Theming — the terminal supplies every colour

The rule, its tokens and its guards are [CLAUDE.md](../CLAUDE.md) "Colour comes from the
terminal"; nothing is detected at startup ([decisions.md](decisions.md) "The terminal supplies
the palette", "TUI paints the terminal's own background"). What only rendering revealed is said
by the comments of `theme.py` and `app.tcss`.

**Amounts.** Every figure shown, and every example amount in a note, is written in the session's
format (§1 "One reader for every typed amount"). Green is money in, the error colour money out.
A transaction's or bank line's amount in a list (ledger, LOG bar peek, bank import and statement
upload previews, a statement's lines, the lines in no statement and their Edit form's heading,
the Edit form's parts and their count line), and wherever one is named (the question before a
delete, a note after you leave), writes a positive figure with its `+`; zero stays `0.00`.
Account balances, Home's grid and its `net` row, a statement's difference, and any other sum of
amounts (the staged total, a day's net, a count line's `… left`) write no `+`. A statement's
beginning and ending balances, and Home's dim `inflow` and `outflow` rows, are in no colour. The
three rules are `TRANSACTION_RULE`, `AMOUNT_RULE` and `BALANCE_RULE` in
[theme.py](../expense/tui/theme.py).

**The cursor is reverse video, applied as a Rich style** ([decisions.md](decisions.md) "The
cursor is reverse video"): `CURSOR_STYLE` in [windowed.py](../expense/tui/widgets/windowed.py)
is the one copy, and tests assert on rendered strips (`render_line`), never on styles
(`test_tui_menu_cursor.py`).

---

## 4. The keymap contract

Three cross-screen rules. No screen declares them, so no generated key list can find them; they
are hand-written into the `?` card ([help.py](../expense/tui/screens/help.py) `CONVENTIONS`):

- **`r` always refreshes**, everywhere.
- **`y` alone confirms** — on the questions that delete, complete or revert, the quit question
  while saves are still being sent, a currency's removal and an emptied opening balance included.
- **`⏎` never changes data.** On the Manage lists it is a literal no-op: no screen handles
  `CursorList.Selected` there, and the card *drops* the row rather than advertise `⏎ Open`
  falsely. The exception is a currency pick (Manage ▸ Accounts' `c` and `x`, §2 "`c` adds a
  currency to an account", "`x` removes a currency from an account"), which the card says; the
  import screens' `⏎ Import N rows` and `⏎ Close <name>` write too (§2 "The import screens' keys").

**`pgdn` means "more of this list", in three ways.** In the two growing lists, the ledger and the
"no statement" pane, it appends the next 10 rows (§5; [decisions.md](decisions.md) "Long lists
grow, they do not page"). In every other list it is the next page of rows already loaded (§5). On
Home it walks the month window one month older, `pgup` one newer (§2).

**The ledger's selection keys** ([transactions.py](../expense/tui/screens/transactions.py)):
`s` and `d` act on the cursor row alone and never follow the selection, so they are off, and out
of the footer, while rows are selected, while a bulk write runs and on an empty list; `d` is
off on an archived account's row too (§2 "On an archived account's row the ledger offers no
`d`"). `space` is declared on `CursorList` but live, key and footer both, only on a screen that
handles `CursorList.Toggled` (`NEEDS_SCREEN_HANDLER` in help.py), so the Manage lists neither
react to it nor advertise it. The other keys are on the `?` card.

**The bar forms' keys** (`form_bindings` in [_form.py](../expense/tui/screens/_form.py), one copy
for every bar form; its docstring and `_advance` say how `⏎` and `ctrl+s` move and save). **A
refused save shows under the form** as `Failed` and the engine's words, loses nothing typed, and
puts the cursor on the line it names; no toast repeats it. **No hint says "save" on a line where
`⏎` moves on, and none says "go on" on a line where `⏎` saves** (guard:
[test_tui_form_hints.py](../tests/unit/test_tui_form_hints.py), which walks every bar form).
**`⇥ Field` is the form's one navigation footer slot**, because forms have no `?` card (guard:
`test_form_navigation_keys_are_not_advertised`).

**The footer never advertises the arrow keys**; the `?` card lists them. `pgdn`/`pgup` and `→ ←`
stay in the footer: they are not obvious. A key that only says "the cursor moves" gets no footer
slot.

**One key per job.** No movement aliases (`j k h l`, `,` `.`) and no `[`/`]`: a widget alias
silently outranks a screen binding, so letters stay free as command keys. Guarded by
[test_tui_help.py](../tests/unit/test_tui_help.py) (`test_no_duplicate_movement_key_aliases`,
`test_square_brackets_are_not_bound_anywhere`).

**A screen key that a focused `Input` also claims needs `priority=True`**: Textual resolves the
focused widget's bindings first, and `Input` binds `ctrl+x` (cut) and the line edits `ctrl+k`,
`ctrl+u`, `ctrl+w`, `ctrl+a`, `ctrl+e` ([log_bar.py](../expense/tui/screens/log_bar.py) is the
worked example). `↑`/`↓` and `escape` need nothing, and `⏎` arrives as `Input.Submitted`.

**Standing constraint:** any future rename action on Manage screens ships as `e`, never `r`.

**App-wide keys are `^q` and `?`.** `^q` quits, asking first while saves are still being sent
(§1 "Quitting asks while saves are still being sent"). `?` opens `HelpModal`, whose content is
**derived** from BINDINGS under `expense.tui` ([help.py](../expense/tui/screens/help.py) says
how, which bindings the card leaves out, and its layout); `Binding.tooltip` carries the card's
fuller wording while `description` stays the terse footer label. `?` is bound per screen root via
`HelpBindingMixin`, **never on the App** — letters bubble up from lists, the same reason there is
no app-level `q` (it is scoped to Home). **Forms have no help key**: a focused `Input` swallows
printable keys. The command palette is off ([decisions.md](decisions.md) "The command palette is
removed"); the mouse is off, and launch wipes the screen and scrollback ([decisions.md](decisions.md)
"TUI is keyboard-only", "The app clears the terminal scrollback at launch").

---

## 5. Pagination and terminal size

Every `CursorList` / `CheckList` renders one window of **min(`PAGE_ROWS_CAP`, what fits the
terminal)** rows — the page IS the screenful, so the page status and footer never clip and no
dead scrollbar appears ([decisions.md](decisions.md) "TUI rows-per-page adapt to the terminal").
`DEFAULT_PAGE_ROWS` (20, one copy in [reads.py](../expense/reads.py)) is the app-wide cap, except
on **Transactions, which fills the window** ([decisions.md](decisions.md) "The ledger fills the
window", "Ledger cells fill their columns"). `LIST_FRAME_LINES` is derived from the render by
`test_the_frame_costs_exactly_list_frame_lines`.

**Transactions and the "no statement" list grow**, through `GrowingRead`
([_growing.py](../expense/tui/screens/_growing.py) says how): `pgdn` appends the next 10 rows. A
write starts the list over from the newest 10, cursor on row 1; leaving the `⏎` form with `esc`
is not a write, so the list comes back as it was. **Full-data screens window locally** (Manage,
the Statements account list, a statement's list); exempt are Home's month grid, static tables
and System kv-tables. **`pgup` shows only where there is something before**, and a paged list
that one page holds shows neither page key.

**The frame:** the breadcrumb on the first line with no blank line above it, the rule directly
under it, then one blank line and the content; a statement's screen puts its head right under
the rule. The Statements screens fit 80×24 without scrolling
(`panel_page_rows` in [statements.py](../expense/tui/screens/statements.py)).

**A key with no row to act on leaves the footer, and returns with the first row.** An empty list
shows only its add key, `r`, `esc` and `?`, and the `?` card leaves out the same keys. A list's own keys follow its
`CARD_NEEDS_A_ROW` (`waits_for_a_row` in [cursor_list.py](../expense/tui/widgets/cursor_list.py); guard:
`test_the_footer_and_the_card_agree_on_an_empty_screen` in
[test_tui_help.py](../tests/unit/test_tui_help.py)).

**Minimum terminal size: there is no guard.** The screens are designed at 80×24; the app degrades
silently below it, columns ellipsised and rows clipped, never reflowed ([decisions.md](decisions.md)
"A terminal too small is the user's to fix"). `PAGE_ROWS_FLOOR = 5` floors the requested page
size, not the viewport. Width has no floor of any kind.
