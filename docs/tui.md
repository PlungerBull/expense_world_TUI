# The TUI — `expense world`

What the Textual app **is**, in present tense. The interactive front door over the
same fetch/write layer the flat commands use; it implements **zero** business logic
(repo thin-wrapper rule). It replaced the questionary `expense menu`, deleted
2026-07-02.

Companions: [cli-spec.md](cli-spec.md) (command surface) ·
[cli-runtime.md](cli-runtime.md) (read/write semantics, which apply to the TUI
unchanged) · [decisions.md](decisions.md) (why the calls below went the way they did) ·
[mockups/](mockups/) (the approval gate for every screen).

Built with **Textual** — Python, by the Rich authors; the direct analog to the Ink
stack Claude Code uses.

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
    cells.py        # cell renderers: color swatch, sign-colored right-aligned amount_cell
                    #   absent-value marks: `—` for a null amount, BLANK for a null
                    #   difference_cents — see decisions.md 2026-09-14, the two are
                    #   different states and must not share a glyph
    windowed.py     # CURSOR_STYLE (reverse video, app-wide) + WindowedList — the
                    #   window/cursor/page arithmetic both list widgets stand on
                    #   + page_indicator() — `rows 21-40 of 133 · page 2 of 7`
    cursor_list.py  # CursorList — arrow-key list (pickers), window + fetched-page
                    #   modes + CursorOptionList — the home menu
    checklist.py    # CheckList — multi-select (hashtag picker)
    picker.py       # suggestion_list() — the scrolling name list both quick-add
                    #   surfaces drop under their input
  screens/
    _base.py        # EngineWriteMixin.run_write + SectionScreen (fetch workers, confirm, keymap)
    _form.py        # FormScreen base — fields, validation, bar-cycle plumbing
    help.py         # HelpModal — the `?` card, derived from BINDINGS (§4)
    home.py         # four months × categories, balances today, then every screen (Overview folded in)
    transactions.py # the ledger — whole, or filtered by Home; `space` + `c`/`b`/`h` bulk edits
    accounts.py     categories.py  hashtags.py
    reconciliations.py               # full lifecycle
    system.py       # Config / Auth / Activity / Rates screens
    quick_log.py    # the transaction EDIT form (`⏎` on a row). Its create
                    #   mode moved to the LOG bar 2026-08-25 — `record` is required now
    log_bar.py      # the LOG bar — what `+` opens. One typed line, a staged batch,
                    #   the named account's ledger below it (AccountPeek, 2026-08-29),
                    #   one save. Parses through expense/quickadd/; `↵` stages a line or
                    #   refuses it in place (2026-09-12 — the Inbox it used to route to
                    #   is gone); ctrl+s writes every row in ONE POST /transactions/batch
                    #   (via expense/batch_write.py). Saved rows keep a ✓ until the
                    #   next line is staged; a partial failure re-sends only the rest.
    create_forms.py # BarFormScreen + New{Account,Category,Hashtag} small forms
                    #   New account carries a TYPE field (bank/person, prefilled
                    #   bank) that picks POST /accounts vs POST /people
    modals.py       # SnapshotModal, ConfirmModal, PromptModal, DiscardStagedModal
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
remainder ([decisions.md](decisions.md)).

**Invariant: `build()` runs on the UI thread and must never do HTTP.** Where a render
needs resolved names, resolve them in `fetch()` and hand `build()` precomputed cells —
`ActivityScreen` is the worked example (`fetch()` opens one client for the whole page,
returns `{"rows": [...], "by_id": {...}}`).

**Name resolution is live HTTP and fails silently by design.**
`load_account_name_map` / `load_category_name_map` / `load_hashtag_name_map` each open
their own client and page the reference list; on **any** failure they return `{}` and
renderers fall back to 8-char short ids. No toast, no error. If a user ever reports
"my tables show hex ids", the cause is the engine rejecting reference-list reads
(auth/config), never data loss. Every call site must be inside a worker thread.

### The header rate alert

Every header carries a `!` when today has no exchange rate of its own — meaning every
home-currency figure on screen is priced at an older day's rate. Owner decision
2026-08-13; the deliberately-sensitive trigger was chosen over a 2-day grace period,
so it also shows on an ordinary morning before the engine's fetch job has run.

- **No new engine surface.** `GET /exchange-rates` already returns the day you asked
  about (`date`) and the day it actually used (`rate_date`); the whole signal is
  `rate_date < date` — which covers every failure mode (provider down, Mac asleep, job
  crashed, or a rate the engine refused as implausible). `rates_cmd.rate_is_stale`
  applies it; `fetch_rate_staleness` adds the `404` case (no rate at all → stale).
  The signal is date-only, so the 2026-08-29 wire change (`rate: float` →
  `rate_e8: int`, engine `sql/036`) did not touch it — only the Rates screen's
  value column, which renders through `format_rate`.
- **App-owned, fetched once per launch.** `ExpenseApp.rate_stale` holds `True` /
  `False` / `None`, filled by one worker on mount. It lives on the app because the
  indicator is in every header and screens come and go: a screen pushed after the fetch
  reads the value itself, one already mounted is repainted (breadcrumbs by query, home
  via its `repaint_header` hook).
- **`None` renders nothing.** Offline, unconfigured, pre-fetch, or an unexpected body
  shape all mean "don't know", and an indicator that fires when it cannot reach the
  engine is reporting on the connection, not on the rate. Warning-colored, not error:
  a carried-forward rate is the engine's designed fallback.
- Guard: [tests/unit/test_rate_alert.py](../tests/unit/test_rate_alert.py).

---

## 2. Screens

**Home is four months of the ledger** (2026-09-13, mockup
[expense-world-home-absorbs-overview.html](mockups/expense-world-home-absorbs-overview.html),
option A — the Overview screen folded in and deleted; the 2026-09-12 single-month Home,
[expense-world-home-as-ledger.html](mockups/expense-world-home-as-ledger.html), is what it
grew from). One worker reads `/dashboard` and `/reports/monthly` and draws:

| Section | Rows | `⏎` |
|---|---|---|
| **CATEGORIES** · four month columns, the newest marked `▸` | every category with activity somewhere in the window, home currency, `—` for a month with none, `3 unrated` when unpriceable — **a category with nothing in the whole window is hidden** (owner pick). `→` unfolds its hashtag rows, `←` folds them; a category whose only combo is untagged has no caret. Under them: `inflow`, `outflow`, `net` | the ledger filtered to that category, every month |
| hashtag row (unfolded) | the category's spend on that hashtag, per month | the ledger filtered to **that category and that hashtag** (`?category_id=&hashtag_id=`). A combo of several hashtags or none is drawn so the sums add up, but `⏎` on it says it cannot be filtered — the engine filters by one hashtag and has no untagged filter. No such row exists outside `@Pendiente` today |
| **BANK ACCOUNTS** · *balance today* | every account with `current_balance_cents` in its own currency, the code beside it | the ledger filtered to that account |
| **PEOPLE** | outstanding people in their own currency; settled ones folded behind `▶ N settled` (`⏎`/`→` opens it); `none` when there is nobody | the ledger filtered to that person |
| **LEDGER** | Transactions · Reconciliations, each a row of its own | `⏎` on an entry pushes the screen |
| **MANAGE** | Accounts · Categories · Hashtags | as above |
| **SYSTEM** | Config · Auth & profile · Activity · Rates | as above |

`pgdn` walks the window one month back, `pgup` one month forward and never past this
month. Balances do not move with it — there is no balances-as-of-date endpoint — which is
why their header says `balance today` permanently. The window and fold keys are
`priority=True` because the menu is an `OptionList`, which binds `pgdn`/`pgup` to its own
page scroll. LEDGER, MANAGE and SYSTEM never fold — their screens are always rows
(owner, 2026-09-13; they opened in place for one day). The screens are there before the reads land and after they fail — a failure is
one dim row with the reason, and `r` re-reads. The first month to land moves the cursor to
the first category; later re-reads leave it where it was. The wordmark line carries the
window's newest month on the right. `_SCREENS` in
[home.py](../expense/tui/screens/home.py) maps entry id → screen, kept in lockstep by
`test_screens_map_covers_every_door_entry`. `Log a transaction` was a menu row until
2026-08-20; it is now **`+`** — see §4. At 120×34 the collapsed page fits whole with this
ledger's 11 categories and 6 accounts; each unfolded category costs its hashtag count in
lines, and past the terminal's height the list scrolls.

**The filtered ledger is the categorising pass.** `⏎` on a Home row pushes
[transactions.py](../expense/tui/screens/transactions.py) with a `LedgerFilter`: the
crumb reads `Ledger ▸ @Pendiente`, the panel is titled for the filter, the fetch is the
engine's own `?category_id=` / `?account_id=`, and the legend says `filter: category
@Pendiente · 57 rows · 3 selected`. `space` selects rows (a `●` in the title gutter,
the row in the accent), `a` selects the page or clears it, and `c` / `b` / `h` open
`PickerModal` over the selection — or over the cursor row when nothing is selected —
to set the category, move to an account, or **replace** the hashtag set. The write is
one `PUT /transactions/{id}` per row, in order, on one client, then one reload: on a
filtered list the changed rows **leave at once** (pick C), the toast `3 rows → KORAKUEN`
is the receipt, and a refused row (an account move a completed reconciliation locks)
is named by number, stays selected, and does not stop the others. `esc` clears the
selection if there is one, and otherwise goes back — to Home, for a filter Home opened
(2026-09-13; it used to clear the filter first, which left you on the whole ledger). Title, description, amount
and date stay single-row edits behind `⏎`. No suggestions and no same-merchant
spreading, by decision — [decisions.md](decisions.md) "Home is the month".

Aggregates are **nullable** — a group holding an unconvertible row reports `3 unrated`
rather than a partial total ([decisions.md](decisions.md)). Opening balances are
excluded engine-side — an `@Opening` seed is where tracking starts, not money that
moved.

**Overview was deleted 2026-09-13.** Its band was Home's accounts and people, its grid's
newest column was Home's month, and what it alone carried — three earlier months, the
hashtag rows, inflow/outflow and the month keys — moved onto Home. The flat
`expense dashboard` and `expense reports monthly --from --to` are unchanged; the grid
builder they share with Home, `reports_cmd.build_range_grid`, is covered by
[test_range_grid.py](../tests/unit/test_range_grid.py).

**Every new screen starts with an HTML mockup in [mockups/](mockups/) for review before
code** — every time, including screens approved before (CLAUDE.md "Mock every screen").

**New surfaces are full screens, not modals** *(owner rule, 2026-09-20)*. Anything
carrying **content** — a list of rows, a set of reasons, a choice you need context to
make — is a pushed `Screen`, never a card floating over the one behind it. Two reasons,
both about a terminal rather than about taste: a modal costs the width its border and
inset take, and that is exactly the width the explaining column needs (the refusal
screen's *which period refused this* was the case that produced the rule — boxed, it
shrinks to three letters); and it hides the screen that supplies the context for the
question it is asking.

The modals that already ship stay: `ConfirmModal`'s plain yes/no, `PickerModal`'s
single-field pick, `HelpModal`'s `?` card, `SnapshotModal`. None of them lists rows —
they are a *question*, not content, and a question is what a card is for. The rule
governs what is built from 2026-09-20 onward, so a new modal now needs a reason rather
than a precedent.

---

## 3. Theming — the terminal supplies every colour

**No literal colors in the TUI, and no authored ones either.** CSS uses `$accent` /
`$secondary` / `$error`; Rich content takes the `PALETTE` constant
([theme.py](../expense/tui/theme.py)). Guarded by
`test_no_literal_color_styles_in_tui`.

Since 2026-08-19 the tokens themselves are **ANSI slots**, not hexes (`ansi_green` is
slot 2 — the terminal fills it in), so the app reads on dark, light, Solarized and
Gruvbox with **no detection at startup**, no light/dark pair and no `NO_COLOR` mode
(the flat CLI honours that variable on its own). A hex in `theme.py` would pin the app
back to one terminal — guarded by `test_theme_is_ansi_slots_not_hexes`. Rationale and
what it cost (the tuned sage-and-rose palette; louder sign colours on a stock profile):
[decisions.md](decisions.md) "The terminal supplies the palette"; picks in
[mockups/expense-world-ansi-palette.html](mockups/expense-world-ansi-palette.html).

**Theme the foreground, never the base surface.** The app runs in ANSI mode
(`ExpenseApp(ansi_color=True)`): the base fill is `ansi_default` — the terminal's *own*
background — set **structurally** in `app.tcss`, not per theme. So there is no seam
against the terminal's window padding. **The rule for any future theme:** recolor the
foreground and semantic spans only (text, accents, sign-colors, selection/diff
highlights) — **never** paint a full-screen or base-surface background. A painted
ground reintroduces the seam *and* breaks any light/dark/auto theme, because one fixed
surface cannot match every terminal. Guard:
`test_tui_theme.py::test_base_fills_are_terminal_transparent`; mockup
[mockups/tui-ansi-transparent-background.html](mockups/tui-ansi-transparent-background.html).
This is how Claude Code keeps a full theme menu while staying seamless.

Three things only rendering revealed, all load-bearing:

- `$surface` / `$panel` generate to **`transparent`** under an ANSI theme, so the
  header rule, the quiet list border and the modal card were invisible or see-through
  → structural rules take `$secondary`, the modal card a literal `ansi_default`.
- **Alpha is dropped** on `ansi_default`, so a modal scrim became an opaque fill that
  *wiped* the screen behind it while every unit test still passed → literal
  `black 60%`, now guarded by `test_modal_scrim_dims_rather_than_wipes`.
- An `ansi=True` theme must ship Textual's whole `variables` block or the app dies at
  startup on `$ansi-background`.
- **`text-style: reverse` does not survive CSS** when foreground and background are
  both `ansi_default` — Textual 8.2.7 drops it in `get_visual_style()`. This is what
  made the home menu's cursor invisible (see below).

**The cursor is reverse video, and it must be applied as a Rich style.** "You are here"
is drawn the same way everywhere: the terminal's own foreground and background, swapped
— colour-free, so it is correct on any ground by construction rather than by detection.
The shared constant is `CURSOR_STYLE` in
[windowed.py](../expense/tui/widgets/windowed.py) (re-exported from `cursor_list.py`
for the import path that already pointed there); `CursorList` / `CheckList` apply it
to their Rich table rows, `suggestion_list` to the picked name, the LOG bar to its
staged row and the field modal to its candidate, and `CursorOptionList` applies it to
the finished strip.

That last one exists because the theme gives the block cursor **no colour of its own**
(`block-cursor-foreground` and `-background` are both `ansi_default`), so all its
contrast comes from `reverse` — and the CSS path drops it. The home menu was the only
list routed through CSS, so it was the only one with an invisible cursor: the
highlighted row rendered `default on default`, byte-identical to its neighbours, and no
test noticed for a day. Reported and fixed 2026-08-20; pick A of
[mockups/expense-world-menu-cursor.html](mockups/expense-world-menu-cursor.html).

**Assert on rendered strips, not on styles.** `get_component_styles` reported
`text_style: reverse` throughout that bug — the style resolved fine and was discarded
later. Only `render_line(y)` shows what the user sees, which is what
`test_tui_menu_cursor.py` checks.

Slot 3 (yellow) is the one slot that fails on white, so the pending role carries
`bold` rather than a colour. Content cards use the **quiet border** treatment
([mockups/expense-world-panelled-dossier.html](mockups/expense-world-panelled-dossier.html));
home's menu stays deliberately boxless.

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

**The ledger's selection keys** ([transactions.py](../expense/tui/screens/transactions.py),
2026-09-12): `space` selects / unselects the cursor row without moving it (`↓` then
`space` is the rhythm), `a` selects every row on the page or clears the selection,
`c` / `b` / `h` open the picker for category / account / hashtags, `esc` clears the
selection if there is one, else goes back to the screen that opened the ledger. `space` is declared on
`CursorList` but is live — key and footer both — only on a screen that handles
`CursorList.Toggled`, the same `NEEDS_SCREEN_HANDLER` gate `⏎ Open` goes through on the
`?` card, so the Manage lists neither react to it nor advertise it. `h` is a *command*
letter here, which is exactly what deleting the vim aliases on 2026-08-27 freed it for.

**`+` logs a transaction** — Home and Transactions (`LogTransactionMixin` in
[_base.py](../expense/tui/screens/_base.py), splatted into each host's BINDINGS like
`HelpBindingMixin`). It always opens the same capture screen — the **LOG bar**, since
quick-add phase 4 (2026-08-25): one key, one meaning. Whether a line stages is decided
by *the line you typed* — refused in place with the reason if it cannot (2026-09-12),
never parked somewhere by which screen you were standing on. Plain `+`,
no modifier — `shift`+`+` is not
bindable at all, and the numpad and main-row keys send the same byte, so one binding
catches both ([decisions.md](decisions.md)).

**The LOG bar's own keys** ([log_bar.py](../expense/tui/screens/log_bar.py)): `↵`
stages the line — or completes the open token, or puts a lifted row back; `↑↓` drive
the completion picker while a token is open and move through staged rows when the bar
is empty; `ctrl+s` writes everything not already written; `ctrl+x` drops the picked
row; `esc` unpicks, then leaves (confirming if rows are staged and unwritten). The bar
always holds focus, which is why no bare letter is a command there and why the screen
has no `?` — a focused `Input` swallows printable keys.

**The legend row** ([log_bar.py](../expense/tui/screens/log_bar.py), 2026-08-29). One
fixed row under the bar carrying the whole grammar and what `↵` does:
`$account · @category · #tag · ±amount · //note · when     ↵ stages the line`. It never
changes — it describes the grammar, not the moment — so nothing below it moves; everything
that *does* change (the amount echo, the resolved date in words, how many names a token
matches, loading/writing) is the `#hint` row above it, which no longer repeats the grammar.
Pick A of
[mockups/expense-world-log-legend-and-picker.html](mockups/expense-world-log-legend-and-picker.html).

**The account peek** ([log_bar.py](../expense/tui/screens/log_bar.py), 2026-08-29). The
moment the typed line names an account, that account's posted ledger fills the room under
the staged list — `AccountPeek`, a quiet-border panel with the same treatment as
`CursorList`, five columns (date, title, amount, category, tags; no account column, every
row names the same one). Three properties are the whole design, and each was a pick:

* **Elastic.** `#peek` is `height: 1fr` and everything above it is `height: auto`, so the
  panel gets exactly the rows the staged list leaves and draws that many; it re-renders on
  its own `Resize`. The empty-state invitation stands down while it is up.
* **The account is the bar's**, never a staged row's — the highlighted candidate while a
  picker is open, nothing at all when the token resolves to nothing.
* **It stays put.** `↵` clears the bar; the panel keeps the last account the bar named.

Read-only: no cursor, no keys, `↑↓` stay with the staged list. One debounced
`GET /transactions?account_id=…` per account, cached for the life of the screen, and a
save invalidates what it wrote to. Mockup:
[mockups/expense-world-log-account-peek.html](mockups/expense-world-log-account-peek.html);
why, with the rejected shapes: [decisions.md](decisions.md).

**The footer never advertises the arrow keys.** `Navigate` is declared `show=False` on
`CursorList`, `CheckList` and `MonthGridView` (user, 2026-08-20 —
*"its obvious and it just occupies space unnecessarily"*). The keys work unchanged and
the `?` card still lists them. `pgdn`/`pgup` paging and `→ ←` expand/collapse **stay** in
the footer: they are not obvious. New bindings inherit this rule — if a key only says
"the cursor moves", it does not get a footer slot.

**One key per job — the vim aliases and the brackets are gone (2026-08-27).** `j k h l`
and `,` `.` were deleted: every one was a second name for a key that was already bound
and already in the footer, so removing them cost no capability and handed `j k h l` back
as *command* letters (a widget alias silently outranks a screen binding, which is what
made them unusable before). `[`/`]` went too — the month window rides `pgdn`/`pgup`,
which were unbound on that screen and already meant "the next window of data": 4 more
months instead of 20 more rows. Both are guarded by
[test_tui_help.py](../tests/unit/test_tui_help.py)
(`test_no_duplicate_movement_key_aliases`, `test_square_brackets_are_not_bound_anywhere`).
Inventory that drove it, with the delete test per key family:
[mockups/expense-world-movement-keys.html](mockups/expense-world-movement-keys.html).

**A screen key that a focused `Input` also claims needs `priority=True`.** Textual
resolves the focused widget's bindings before the screen's, and `Input` binds more
chords than it looks like — `ctrl+x` is `cut`, `ctrl+k`/`ctrl+u`/`ctrl+w` are line
edits, `ctrl+a`/`ctrl+e` are home/end. The LOG bar's `ctrl+x drop row`
([log_bar.py](../expense/tui/screens/log_bar.py)) would otherwise edit the line
instead of dropping the staged row. Plain `↑`/`↓` and `escape` need nothing — `Input`
does not bind them — and `⏎` arrives as `Input.Submitted`, not as a binding at all.

**Standing constraint:** any future rename action on Manage screens ships as `e`,
never `r` — two older mockups showing `r rename` are superseded. Mockup:
[mockups/expense-world-keymap-4.1.html](mockups/expense-world-keymap-4.1.html).

**App-wide keys are `^q` and `?`.** `?` opens `HelpModal`, a two-column card whose
content is **derived** from BINDINGS by walking the screen's and the focused widget's
MRO and keeping only classes declared under `expense.tui` — which is what keeps
Textual's own `home`/`end`/`tab` out without a suppression list. `Binding.tooltip`
carries the card's fuller wording (`Archive / unarchive`) while `description` stays the
terse footer label (`Archive`): one declaration, two audiences. `?` is bound per screen
root via `HelpBindingMixin`, **never on the App** — letters bubble up from lists, the
same reason there is no app-level `q` (it is scoped to Home). **Forms have no help
key** by decision: a focused `Input` swallows printable keys, so `?` would type a
question mark.

**The Textual command palette is removed** (`ENABLE_COMMAND_PALETTE = False`), which
also drops the `^p palette` strip from every footer. `?` is the one discoverability
surface — [decisions.md](decisions.md).

**Mouse is off** (`run(mouse=False)`) — the TUI is keyboard-only. Corollary:
terminal-level scrolling reaches the terminal itself, and Terminal.app will scroll into
scrollback *above* the running app. Launch therefore wipes screen and scrollback
(`CSI 2J 3J H` in `run_world`) so there is nothing to reveal.

---

## 5. Pagination and terminal size

Every `CursorList` / `CheckList` renders one window of **min(`PAGE_ROWS_CAP`, what fits
the terminal)** rows — the page IS the screenful, so the panel border/subtitle/footer
never clip and no dead scrollbar appears. A resize re-measures
(`SectionScreen.measure_list_rows`, floor 5) and keeps the first visible row.
`DEFAULT_PAGE_ROWS` (20, one copy shared with the CLI) is the app-wide cap and the
pre-layout fallback everywhere except **Transactions, which fills the window**
(2026-08-29): it sets `PAGE_ROWS_CAP = ENGINE_PAGE_CAP` (200, the engine's own `limit`
ceiling) and `CARD_WIDTH = None`, so its card spans the full width too — the screen
you sit in takes the terminal you gave it (the Inbox did the same until 2026-09-12). Every other screen keeps its
20-row cap and its tidy `CARD_WIDTH`. Its cells fill that width too (2026-09-12,
[mockups/expense-world-ledger-column-fit.html](mockups/expense-world-ledger-column-fit.html)
option A): `transaction_rows` hands the table whole strings and `CursorList(flex={0: 3, 1: 3, 6: 2})`
makes Title, Description and Hashtags Rich ratio columns — Amount, Date, Account and Cat take
their natural width first, the three text columns share what is left 3:3:2, and each cell is cut
by the table at the edge of the column it actually has. So the column edges follow the terminal,
not the page's longest cell, and on a narrow terminal the free text gives way before the numbers.
Every other list leaves `flex` empty and keeps Rich's content-proportional spread. Page keys: `pgdn` next, `pgup` previous — hidden when one page holds it all.
They carry Home's month window too (`pgdn` older, `pgup` newer): one
meaning, "the next window of data", whether the window is rows or months.

Transactions / Activity / Rates fetch real `limit`/`offset` pages sized to the
window via `PagedListMixin` (`↑`/`↓` clamp at the fetched edge; a resize refetches with
the offset re-anchored). Full-data screens window locally — Manage, the two
Reconciliations panes splitting the space equally, the recon checklist at fit÷2 items —
where `↑`/`↓` walk through and cursor-restore lands on its page. Lists are quiet-border
panels: border title carries the screen title, border subtitle the page status
(`rows 21-40 of 133 · page 2 of 7`). Exempt: Home's month grid, static tables,
System kv-tables. Picks:
[mockups/expense-world-pagination.html](mockups/expense-world-pagination.html),
[mockups/expense-world-adaptive-rows.html](mockups/expense-world-adaptive-rows.html).

**Minimum terminal size: there is no guard, and that is the decision** (2026-08-20).
The app degrades and says nothing; the terminal is the user's to size. Two reference
sizes, both **measured**:

- **80×24 — everything correct.** No truncation anywhere, panel closes, full footer.
  The size the screens were designed at, and the classic terminal default.
- **60×20 — still workable, already lossy.** Every row draws, but columns are
  ellipsised (`R…`, `-1…`). Fine for navigating, poor for reading.

| dimension | measured behaviour |
|---|---|
| w ≥ 80 | no ellipsis in any cell |
| **w ≈ 75** | **truncation begins** — the first cells start eliding |
| w ≈ 50 | title column is a bare `…`, amount `-…`; every row still drawn |
| w ≤ 40 | date goes too — rows of pure ellipsis |
| height | **the panel clips when content exceeds the viewport, so the threshold moves with the page size**: a 4-row page closes down to h=18, a full 8-row page already clips at h=20. Rows are cut off, never reflowed. Above the floor the page is measured to fit exactly — `LIST_FRAME_LINES` counts 6 (border 2, header, rule, and the two blank edge lines `box.SIMPLE` draws); it read 4 until 2026-08-29, which overflowed every fitted list by those two lines. |
| h ≤ 10 | no data rows at all, while the footer still offers to page through them |

`PAGE_ROWS_FLOOR = 5` floors the *requested page size*, not the viewport — it cannot
make rows fit that do not. Width has **no** floor of any kind. Captures and the four
rejected shapes (launch refusal, notice screen, warning banner, size in the footer):
[mockups/expense-world-min-terminal-size.html](mockups/expense-world-min-terminal-size.html);
rationale: [decisions.md](decisions.md) "A terminal too small is the user's to fix".

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

**Known, accepted, not worth fixing at this scale:** a screen load may open several
short-lived clients (Transactions: the page and three name maps; the bulk pickers'
reference lists load once, on the first bulk key) — harmless on loopback.
