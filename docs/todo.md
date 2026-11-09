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

Approved specs, in the order the loop runs them (CLAUDE.md "Specs and tasks"). A spec joins
when the owner approves it and leaves when it retires; one that is blocked says on what, and the
loop skips it until it can run.

1. [The app on contract `1002f105c6bacdf1`, and the preview names the lines the close will flag](specs/catch-up-to-1002f105c6bacdf1.md):
   approved 2026-11-08; tasks 1–7 done.
2. [Accounts carry their numbers, the account form saves in one write](specs/accounts-carry-their-numbers.md):
   approved 2026-11-08. Its cash part waits on the engine ask "Every user holds one cash account,
   named `Efectivo`, with no bank and no number".

The engine's hand-off of 2026-11-08 is planned up to `1002f105c6bacdf1`, the version recorded.
The engine already serves `eb3082ec9723ec4f`; its five later versions (a statement upload or
close refused while a line in no statement sits on a day it would seal, and sealed-day edits
judged only on changed fields) go to the next catch-up, so the version check reporting them
stops nothing.

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

[The official import](specs/before-the-official-import.md) is rewritten for built names once
the numbers spec is done, and comes for approval then.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **No test proves the leave guards** in the base list screen's draw and error steps, the guards
  after taking the content lock, or the statement lines' guard after their list mounts; each could
  be forced to always pass and every test would stay green. Nothing you see changes.
- **The `?` card's row rule reads a little unevenly in code.** The ledger's list names
  `CARD_NEEDS_A_ROW` on its instance where `_AccountList` names it on its class; `listed_bindings`
  reads the owner's private `_rows`; the `_stub_engine` docstring in test_tui_help.py says every
  card drops its list keys on an empty list. Nothing you see changes.
- **Amounts follow your number format.** The app reads the Mac's region by default, and an
  optional setting on the owner's account wins when set, so every device agrees (an engine
  ask). The format is used both for amounts typed and for every amount shown.
  Under English (Peru), `1,5` is not a number, so it is refused instead of saved as 15.00.
  Needs a spec.
- **The drift check reads a nested union of lists the old way.** `_list_items` in
  [check_fixture_drift.py](../scripts/check_fixture_drift.py) reads `anyOf [A[], anyOf [B[],
  C[]]]` as A's items alone, where `_object_schema` reads nested unions whole. No marked answer
  has such a shape today. Nothing you see changes.
- **No unit test pins a union that contains itself.** `_alternatives` in
  [check_fixture_drift.py](../scripts/check_fixture_drift.py) drops a `$ref` already seen on its
  path, so such a union ends; nothing in
  [test_fixture_drift_script.py](../tests/unit/test_fixture_drift_script.py) proves it.
- **The theme's rule comment repeats tui.md "Amounts" and gets one detail wrong.** The comment
  in [theme.py](../expense/tui/theme.py) says `AMOUNT_RULE` covers dashboard totals, but Home's
  inflow and outflow rows are plain; only the net uses it. Cut it to a pointer at
  [tui.md](tui.md) "Amounts", its one home. Nothing you see changes.
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
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **An MCP server for agents.** The way for an agent to read or write the ledger on the owner's
  behalf, talking to the engine as every client does. It belongs beside the engine, not in this
  repo, and is a piece of work of its own.
