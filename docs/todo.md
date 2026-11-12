# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks wait in [to-engine/](to-engine/), one file each, until
handed over.

---

## Queue

Approved specs, in the order the loop runs them (the shared loop, `../agent-loop.md` "Specs and tasks"). A spec joins
when the owner approves it and leaves when it retires; one that is blocked says on what, and the
loop skips it until it can run.

A catch-up spec built from the engine's hand-off goes first once that file is in
[from-engine/](from-engine/): the live suite fails until it lands.

1. [Closing a month with leftover lines](specs/closing-with-leftover-lines.md): approved
   2026-11-08, its question 4 answered 2026-11-11. Blocked: tasks 3 and 5 wait on the engine
   asks "A loose-lines refusal names the statement it would close" and "A close can be checked
   before it is sent".
2. [The app the owner runs](specs/going-live.md): approved 2026-11-11. Tasks 5–7 wait on the
   engine's going-live release; tasks 5 and 6 also wait on the owner picking their mockups.
3. [Lean docs](specs/lean-docs.md): approved 2026-11-11. Every task is done; its acceptance check
   waits on the practice engine, off until you say the engine's rebuild is done, since the moved
   contract citations are checked live.
4. [Code conventions A](specs/code-conventions-a.md): approved 2026-11-11.
5. [Code conventions B](specs/code-conventions-b.md): approved 2026-11-11.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes it. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### Your first release, then the old install goes
Asked 2026-11-11 · Blocks: nothing yet; the first install follows the loop preparing v1.0.0
When the loop's summary says v1.0.0 is ready, run `python3 scripts/release.py` in the live
folder (`~/Library/Application Support/expense_world/tui`; it needs `gh` logged in and `pipx`).
Once `expense` opens as v1.0.0, remove the old install: `pipx uninstall expense-cli-menu`.
**Recommended:** none, steps only you can do.

### May the log keep a refusal that repeats what you typed?
Asked 2026-11-12 · Blocks: nothing; the log is built logging refusals in full
You asked for every engine refusal in the log, in full, and for descriptions and amounts to stay
out unless `--verbose` is on. A few refusals repeat a value back, for example `Row 12: Monto holds
'abc', not a number.` from a sheet import. Request lines never hold a description or amount.
- **A.** Keep each refusal as the engine sent it.
- **B.** Leave out a refusal's echoed values unless `--verbose` is on.
**Recommended:** A, because the refusal is what you need to read when something went wrong, and
the log stays on your own Mac.

### tui.md ends at 5,778 words, not 5,000: accept it?
Asked 2026-11-12 · Blocks: [lean docs](specs/lean-docs.md)'s finish
Every task is done. tui.md went from 26,124 words to 5,778; your target was 5,000 or less, and all
the docs together are 33,392 against 32,000. What is left is mostly engine rules quoted with where
the engine says them, and a few rules no code comment says; cutting them means moving each into the
code first. CLAUDE.md (2,241), runtime.md (2,306), decisions.md (17,979) and AGENTS.md (24) meet
theirs, and the new docs/README.md index is 258.
- **A.** Accept 5,778 and finish the spec.
- **B.** One more task: move the engine rules into the code that sends them, then cut tui.md to 5,000.
**Recommended:** A, because each remaining line is a rule someone reading tui.md needs, and moving it
into code only hides it from the next reader.

### Three small screen questions from the finished catch-up
Asked 2026-11-09 · Blocks: nothing yet; each joins a spec in its area once answered
Found while the catch-up to `1002f105c6bacdf1` ran; drawn as panes 1–3 of
[expense-world-open-questions.html](mockups/expense-world-open-questions.html).
1. **`n` on Manage ▸ Accounts while the list shows "Could not load."** It opens a New form whose
   currencies line has nothing to pick (the currencies come with the list's read). Turn `n` off
   until the list loads, or keep it?
2. **A flagged line in a currency a one-currency paper does not cover** shows in the preview's
   `⚑` block with no currency (the column shows only on a two-currency paper). Leave it, show the
   currency on such lines, or show the column whenever the paper misses a currency?
3. **The `⚠` notes:** the preview leads each with its currency (`⚠ USD: …`), the close screen
   leaves a covered currency's bare. One way on both screens, or each as it is?

### Small screen details from the account numbers work
Asked 2026-11-09 · Blocks: nothing; each answer other than "as built" joins a spec in its area
Found while accounts got their numbers; each is built as described; drawn as panes 4–8 of
[expense-world-open-questions.html](mockups/expense-world-open-questions.html).
1. **A New bank account left before the engine refuses it** reads `Not created · Account
   (unnamed)`, since the account has no name until the engine builds it. Keep it, or name it by
   the bank typed (`Account BCP`)?
2. **Removing a card** asks `Remove card 5678 from BCP-5678?` / `1234 is its number again. No
   screen can bring 5678 back.`; the mockup also said `and it shows as BCP-1234`, which only the
   engine can say. Keep it, or ask the engine for the name a removal leaves? Its footer is every
   question's `[y] confirm [enter / n / esc] cancel`, not the mockup's `y removes · any other key
   keeps it`.
3. **Lines the mockup did not draw:** the Edit form's `since` leaves the form while the account has
   no number, and so does `new card`; `new card from` shows once `new card` holds digits; several
   older cards share one `cards before` line, oldest first; the new lines' hints follow the
   form's others (`optional · the replacement card's last 4 digits · enter to go on`). Keep them?
4. **The LOG bar's `$` hint lines:** the mockup drew `"$5678" matches 1 account` and `$56 is an
   amount: 56.00`; today a single match resolves as you type with no line, as `$nic` does, and no
   amount line shows. Add both lines, or keep it as it is?
5. **The upload could skip "Which account is this statement?"** now that accounts carry their
   numbers: the engine would name the account from the number the paper prints. Ask the engine
   for it, or keep asking?
**Recommended:** 1–4 as built, since each follows the app's existing screens and builds no name
in the app; 5 ask the engine, since the paper already says which account it is.

### Small screen details from the cash account
Asked 2026-11-09 · Blocks: nothing; each answer other than "as built" joins a spec in its area
Found while the cash account was built; drawn as panes 9–13 of
[expense-world-open-questions.html](mockups/expense-world-open-questions.html).
1. **The New form's type line** reads `bank, person or cash · enter keeps bank`, the form's own
   hint shape; the mockup drew `bank · person · cash · ←→ picks`, naming keys the form does not
   use. Keep it as built?
2. **The Accounts `?` card lists both `t` lines** (make person, make bank) on every row, the cash
   and archived rows included, though the footer shows only the one the row takes. Showing only
   that one changes the card on every row. Keep it, or show only the `t` the row takes?
3. **Home's ACCOUNTS block for a user with no accounts** shows its heading and no rows; PEOPLE in
   the same state says `none`. Say `none` there too?
4. **`⏎ Open` shows in the Manage lists' footer** (Accounts, Categories), though `⏎` does nothing
   there and the `?` card leaves it out. Drop it from the footer?
**Recommended:** 1 and 2 as built, since each follows the app's other screens; 3 and 4 yes, so
the screen says what is there and offers only keys that work.

### Small screen details from the number format
Asked 2026-11-09 · Blocks: nothing; each answer other than "as built" joins a spec in its area
Found while the number format setting was built; drawn as panes 14–16 of
[expense-world-open-questions.html](mockups/expense-world-open-questions.html).
1. **The words not drawn:** saving reads `Number format saved.`; when the Mac's region cannot be
   named, the row reads `1,234.56  · follows this Mac`, with no region in brackets. Keep both?
2. **Auth & profile's footer** reads `esc Back  r Refresh  ? Keys  b Bootstrap  f Number
   format`, every screen's own keys first; the sketch drew `esc Back  b Bootstrap  f Number
   format  ? Keys`. Keep the app's order?
3. **A new device, right after Setup,** shows amounts in its own region's format until the app
   is opened again, since the account's pick is read at launch. Read it as Setup finishes too?
4. **A pick saved after you left Auth & profile** (the engine answering late) says `Number format
   saved.`, but Home keeps the old format until it next reloads. Redraw Home when it lands?
**Recommended:** 1 and 2 as built, since each follows the app's other screens; 3 and 4 yes, so
every amount on screen follows the pick as soon as it is known.

### The official import, redrafted for built names: approve it?
Asked 2026-11-09 · Blocks: [the official import](specs/before-the-official-import.md)
The spec is rewritten now that the engine names bank accounts itself and lists one bank. Its
questions 15–17 are in the spec, 15 and 16 drawn as panes 17–18 of
[expense-world-open-questions.html](mockups/expense-world-open-questions.html). One reply answers
them and approves the spec and its tasks.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
the shared loop, `../agent-loop.md` "Specs and tasks".

- **After a reload that fails, the ledger's footer and `?` card keep its row keys** (`a`, `c`,
  `b`, `h`, `m`, `s`, `d`) with no list on screen, since `TransactionsScreen.has_rows`
  (`expense/tui/screens/transactions.py`) reads the rows read before; the Manage lists drop them.
- **Two comments in expense/errors.py (:71, :328) cite `POST /v1/accounts/{account_id}/opening-balance`,**
  which the account Edit form no longer uses; point them at `PUT /v1/accounts/{account_id}` if
  they describe it.
- **`scripts/clean_practice_user.py` cannot remove an unnumbered `BCP`** a killed live run leaves
  behind (`owns` matches bank accounts by a number starting 9), so later runs hit `NAME_EXISTS`
  until it is deleted by hand.
- **Small code-comment fixes from the number format:** the launch read takes no `verbose`
  (expense/tui/app.py); `AuthScreen.check_action` returns `True` rather than the base's answer;
  expense/region.py:3 says the region is read once at launch, though Auth & profile reads it on
  every load; `DEFAULT_FORMAT`'s comment (expense/number_format.py:36-37) leaves out that the
  account's pick wins over the region.
- **`written()` in `t`'s question repeats `_currency_write`** (expense/tui/screens/accounts.py:317,
  :382): two copies of one write's body.
- **The upload preview's page budget counts each `⚠` note as one line,** though a long one wraps
  on a narrow window.
- **Two docstrings in tests/contract/test_sealed_periods.py read wider than their test:** :165
  says a draft is "the only place such a row can be" (a row on a sealed day can also sit in the
  completed statement, where a new currency is `LOCKED`); :14-17 says `currency_code` alone is
  `SEALED_PERIOD` "on each of those sent", though the body also sends `statement_id`.
- **Bank files become the intake.** Plan: [file-import-plan.md](file-import-plan.md).
- **Expense World XP [UI]** — an XP layer over the month: a strip on Home, toasts when something
  is earned, a monthly chapter recap, a Character screen, and a one-time role on each account and
  some categories. Sketch: [mockups/expense-world-xp-system.html](mockups/expense-world-xp-system.html),
  not approved, nothing built; XP prices are placeholders. Needs a spec from the owner.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside the TUI
  ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html), which
  also records the ⌘E conflict). Convenience, not access: `+` opens the LOG bar inside the app.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **The "no statement" list under 68 columns.** The Statements screen's list of lines in no
  statement cuts its amount, then its currency, under 68 columns, and under 62 its caption wraps a
  lone `·` onto a line of its own. Parked 2026-11-07: the app is built for 80 columns.
- **`b`'s note when moved rows came from several currencies** gives one sentence per currency, a
  case the engine's two currencies cannot reach; confirm its wording with the owner when a third
  currency comes.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
