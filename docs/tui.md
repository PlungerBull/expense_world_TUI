# The TUI — `expense world`

What the Textual app **is**, in present tense. The interactive front door over the
same fetch/write layer the flat commands use; it implements **zero** business logic
(repo thin-wrapper rule).

Companions: [cli-spec.md](cli-spec.md) (command surface) ·
[cli-runtime.md](cli-runtime.md) (read/write semantics, which apply to the TUI
unchanged) · [decisions.md](decisions.md) (why the calls below went the way they did) ·
[mockups/](mockups/) (the approval gate for every screen).

---

## 1. Architecture

```
expense/tui/
  app.py            # ExpenseApp(App): screen stack, global bindings, worker helper
  app.tcss          # Textual CSS — layout + the structural ANSI fills (§3)
  theme.py          # the ANSI Theme + the PALETTE constant Rich content styles with
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
    checklist.py    # CheckList — multi-select (hashtag picker)
    picker.py       # suggestion_list() — the scrolling name list both quick-add
                    #   surfaces drop under their input
  screens/
    _base.py        # EngineWriteMixin.run_write + SectionScreen (fetch workers, confirm, keymap)
    _form.py        # FormScreen base — fields, validation, bar-cycle plumbing
    _growing.py     # GrowingRead — a list that grows by cursor (ledger, "no batch" pane)
    help.py         # HelpModal — the `?` card, derived from BINDINGS (§4)
    home.py         # four months × categories, balances today, then every screen
    transactions.py # the ledger — whole, or filtered by Home; `space` + `c`/`b`/`h` bulk edits
    accounts.py     categories.py  hashtags.py
    reconciliations.py               # full lifecycle
    system.py       # Config / Auth screens
    edit_form.py    # the transaction EDIT form (`⏎` on a row); `record` is required
    log_bar.py      # the LOG bar — what `+` opens. One typed line, a staged batch,
                    #   the named account's ledger below it (AccountPeek), one save.
                    #   Parses through expense/quickadd/; `↵` stages a line or refuses
                    #   it in place; ctrl+s writes every row in ONE POST
                    #   /transactions/batch (via expense/batch_write.py). Saved rows
                    #   keep a ✓ until the next line is staged; a partial failure
                    #   re-sends only the rest.
    create_forms.py # BarFormScreen + New{Account,Category,Hashtag} small forms
                    #   New account carries a TYPE field (bank/person, prefilled
                    #   bank) that picks POST /accounts vs POST /people
    modals.py       # ConfirmModal, PromptModal, PickerModal, DiscardStagedModal
                    #   (the LOG bar's one confirmation)
```

**The fetch/print split is the anti-duplication guardrail.** Every command that
fetched *and* printed has a pure `fetch_*(cfg, …) -> dict`; the typer command and
the TUI both call it. The TUI imports `fetch_*` — it never reimplements one. Shared
read/format helpers live in [_resource.py](../expense/commands/_resource.py), write
plumbing in [_base.py](../expense/tui/screens/_base.py), form scaffolding in
[_form.py](../expense/tui/screens/_form.py).

**Async / workers.** Textual runs on asyncio; the engine client is synchronous, and
stays that way. It is called inside a Textual worker (`@work(thread=True)`) so the UI
never blocks. Read screens subclass `SectionScreen` and override `fetch()` (runs in
the worker) + `build(data)`; writes go through `EngineWriteMixin.run_write` in its own
worker group — a FIFO queue, one write in flight, and an error drops the queued
remainder.

**Invariant: `build()` runs on the UI thread and must never do HTTP.** Where a render
needs resolved names, resolve them in `fetch()` and hand `build()` precomputed cells —
`TransactionsScreen` is the worked example (`fetch()` reads the page and the three name
maps, and `build()` only looks names up in them).

**Name resolution is live HTTP and fails silently by design.**
`load_account_name_map` / `load_category_name_map` / `load_hashtag_name_map` each open
their own client and page the reference list; on **any** failure they return `{}` and
renderers fall back to 8-char short ids. No toast, no error. If a user ever reports
"my tables show hex ids", the cause is the engine rejecting reference-list reads
(auth/config), never data loss. Every call site must be inside a worker thread.

### The header rate alert

Every header carries a `!` when today has no exchange rate of its own — meaning every
home-currency figure on screen is priced at an older day's rate. The trigger is
deliberately sensitive (no grace period), so it also shows on an ordinary morning before
the engine's fetch job has run.

- **No dedicated engine surface.** `GET /exchange-rates` returns the day you asked about
  (`date`) and the day it actually used (`rate_date`); the whole signal is
  `rate_date < date`, which covers every failure mode. `rates_cmd.rate_is_stale`
  applies it; `fetch_rate_staleness` adds the `404` case (no rate at all → stale).
  There is no TUI screen behind the mark; `expense rates list` shows what is stored.
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

**Home is four months of the ledger.** One worker reads `/dashboard` and `/reports/monthly` and draws:

| Section | Rows | `⏎` |
|---|---|---|
| **CATEGORIES** · four month columns, the newest marked `▸` | every category with activity somewhere in the window, home currency, `—` for a month with none, `3 unrated` when unpriceable — **a category with nothing in the whole window is hidden**. `→` unfolds its hashtag rows, `←` folds them; a category whose only combo is untagged has no caret. Under them: `inflow`, `outflow`, `net` | the ledger filtered to that category, every month |
| hashtag row (unfolded) | the category's spend on that hashtag, per month | the ledger filtered to **that category and that hashtag** (`?category_id=&hashtag_id=`). A combo of several hashtags or none is drawn so the sums add up, but `⏎` on it says it cannot be filtered — the engine filters by one hashtag and has no untagged filter |
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
It stays selected only if the fresh read brings it back among the newest 10; further down
it drops out of the selection.
`esc` clears the selection if there is one, and otherwise goes back to the screen that
opened the ledger. Title, description, amount and date stay single-row edits behind `⏎`.
No suggestions and no same-merchant spreading — [decisions.md](decisions.md) "Home is the
month".

Aggregates are **nullable** — a group holding an unconvertible row reports `3 unrated`
rather than a partial total. Opening balances are excluded engine-side. The grid builder
Home shares with the flat `expense reports monthly`, `reports_cmd.build_range_grid`, is
covered by [test_range_grid.py](../tests/unit/test_range_grid.py).

**`u` on the Reconciliations browse — the account's rows in no batch**.
The **panel swaps**: same screen, same place, and the open account's reconciliations
are replaced by its transactions belonging to no reconciliation
(`GET /transactions?account_id=&unreconciled=true`). `u` works only while an account's
panel is open — on the plain account list it does nothing and is not in the footer.
`esc` swaps it back to the panel, `⏎ Edit` opens the ledger's edit form (date and account
are the two remedies for a row in no batch), and `d` deletes the cursor row after a
confirm. It is deliberately not a filtered ledger: reconciliation work stays in the
reconciliation view.

The pane **lands on the oldest rows** — old orphans are the problem — so it reads with
`sort=date_asc`, ten rows at a time, growing like the ledger (§5). The caption's
`N of M loaded` takes M from `GET /transactions/count`, read together with the first rows;
a count that cannot be read fails the pane. `r`, an edit and a delete all start again
from the oldest ten, cursor on row 1. The **`!` flag is a hint, not a ruling** — it marks
a row whose date falls inside a batch window this screen already holds, so it costs no
request; the engine stays the authority at close time.

**`d` is the TUI's one destructive key.** Cursor row only, never a selection, and the
confirm says the part that matters: **no screen or command can bring the row back.**

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
detection at startup**, no light/dark pair and no `NO_COLOR` mode (the flat CLI honours
that variable on its own). A hex in `theme.py` would pin the app back to one terminal —
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
  advertise `⏎ Open` falsely.

**The ledger's selection keys** ([transactions.py](../expense/tui/screens/transactions.py)):
`space` selects / unselects the cursor row without moving it (`↓` then `space` is the
rhythm), `a` selects every loaded row or clears the selection, `c` / `b` / `h` open the
picker for category / account / hashtags, `esc` clears the selection if there is one,
else goes back to the screen that opened the ledger. `space` is declared on `CursorList`
but is live — key and footer both — only on a screen that handles `CursorList.Toggled`,
the same `NEEDS_SCREEN_HANDLER` gate `⏎ Open` goes through on the `?` card, so the Manage
lists neither react to it nor advertise it.

**`pgdn` means "more of this list", in three ways.** In the two growing lists, the ledger
and the "no batch" pane, it appends the next 10 rows by cursor and puts the cursor on the
first new one (footer `pgdn 10 more`; gone at the end), and `pgup` just goes up a
screenful ([decisions.md](decisions.md) "Long lists grow, they do not page"). In every
other list it is the next page of rows already loaded (§5). On Home it walks the month
window one month older, `pgup` one newer (§2).

**The Reconciliations browse** opens on
the **account list alone**, full height, and reads no reconciliations: the engine lists
them one account at a time (`GET /reconciliations?account_id=`, whole, in period order),
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
one copy for the edit form, the create/edit forms and the new-reconciliation form):
`⏎` saves the field and moves on (saving the form on the last field), `ctrl+s` saves the
form, `esc` cancels. `tab` moves to the next field and `shift+tab` to the previous, on
every field, whether or not a suggestion list is open. `FormScreen` is declared
`inherit_bindings=False`, so Textual's focus-cycling `tab` never applies and the bar
keeps focus; Screen's hidden `ctrl+c` copy key is declared again in `form_bindings`.
Plain `↑`/`↓` walk the suggestion list when the field has a non-empty one and move to the
previous/next field when it has none. `ctrl+↑`/`ctrl+↓` also move fields but are never
advertised: macOS claims `⌃↑` (Mission Control) and `⌃↓` (Application Windows) before the
terminal sees them. Every field move skips read-only fields and stops at either end.
The footer reads `esc Cancel  ^s Save  ⇥ Field` (`Create` on a create form):
**`⇥ Field` is the form's one navigation footer slot**, because forms have no `?` card
that could list the other keys (below). Guarded by `test_form_navigation_keys_are_not_advertised`.

**The footer never advertises the arrow keys.** `Navigate` is declared `show=False` on
`CursorList` and `CheckList`. The keys work unchanged and the `?` card still lists them.
`pgdn`/`pgup` and `→ ←` expand/collapse **stay** in the footer: they are not obvious. New
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
(`CSI 2J 3J H` in `run_world`) so there is nothing to reveal.

---

## 5. Pagination and terminal size

Every `CursorList` / `CheckList` renders one window of **min(`PAGE_ROWS_CAP`, what fits
the terminal)** rows — the page IS the screenful, so the page status and footer never
clip and no dead scrollbar appears. A resize re-measures
(`SectionScreen.measure_list_rows`, floor 5) and keeps the first visible row.
`DEFAULT_PAGE_ROWS` (20, one copy shared with the CLI) is the app-wide cap and the
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
resize reads nothing. After a write (a bulk key, the `⏎` edit, `+`) it starts over from
the newest 10 with the cursor on row 1, as `r` does. Leaving the `⏎` form with `esc` is
not a write: nothing is read and the list comes back as it was — the rows `pgdn` loaded
and the cursor on its row (owner, 2026-09-27); the form dismisses with `True` only on a
save. The "no batch" pane on
Reconciliations grows through the same `GrowingRead`, oldest first — one copy of the
cursor, the count, the `pgdn` read and the rule that a `pgdn` read never lands on a list a
fresh read replaced.

**Full-data screens window locally** — Manage, the Reconciliations account list (full
height alone, an equal split with the open panel), the recon checklist at fit÷2 items —
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
  [tests/unit/helpers.py](../tests/unit/helpers.py). A **bare** `pilot.pause()` is the
  pump-drain for asserting a *non-event* (an inert key, a confirm that must not fire),
  where no predicate can be written. Timed `pilot.pause(<n>)` is rejected by
  [tests/unit/test_suite_hygiene.py](../tests/unit/test_suite_hygiene.py), which carries
  exactly one documented exemption (the cancelled-worker window in
  `test_tui_reconcile_detail.py`, keyed on the whole source line so editing it re-opens
  the question).
- **Patch `load_*_name_map` at the screen module** (`expense.tui.screens.X.load_…`),
  not at `_resource` — when the test's point is name display. Use the short-id fallback
  when it isn't.
- **`fake_client` (conftest) patches the lazy-import seams only** —
  `expense.http.ExpenseClient` and `expense.config.ensure_loaded`. Assert on
  `client.calls` / `.posts` / `.puts` ordering.
- **`test_command_surface.py` gives no signal when a command disappears.** The Typer
  walker only checks commands it finds. The backstops are the total-count floor and the
  destructive count — adjust them deliberately when adding or removing commands.

**Known, accepted:** a screen load may open several short-lived clients (Transactions:
the page and three name maps; the bulk pickers' reference lists load once, on the first
bulk key) — harmless on loopback.
