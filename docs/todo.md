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

1. [The app on contract `2fa4967b8eed9c3f`: an account's kind, strict requests and the closed-day refusals](specs/catch-up-to-2fa4967b8eed9c3f.md):
   approved 2026-11-08.
2. [The app on contract `1002f105c6bacdf1`, and the preview names the lines the close will flag](specs/catch-up-to-1002f105c6bacdf1.md):
   approved 2026-11-08; tasks 1–7 done. Task 8 runs once spec 1's live suite sends an
   account's `kind` (its task 2).
3. [Accounts carry their numbers, the account form saves in one write](specs/accounts-carry-their-numbers.md):
   approved 2026-11-08.
4. [The cash account](specs/the-cash-account.md): approved 2026-11-08.
5. [Closing a month with leftover lines](specs/closing-with-leftover-lines.md): approved
   2026-11-08. Tasks 1 and 2 wait on the engine ask "A loose-lines refusal names its lines by id,
   in a field a client reads".
6. [Amounts follow your number format](specs/amounts-follow-your-number-format.md):
   approved 2026-11-08. Tasks 1–3 done; tasks 4 and 5 wait on the engine ask "A user's
   settings hold their number format".

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

### The engine moved past its latest hand-off: ask for one more file?
Asked 2026-11-08 · Blocks: the whole queue (the loop is stopped)
This client is catching up to `2fa4967b8eed9c3f`, the hand-off's last version (recorded:
`1002f105c6bacdf1`, until the catch-up spec retires). The practice engine now serves
`c15201ee50485e56`, one version later. The version check prints:
`c15201ee50485e56 2026-11-08 — changed: a timezone is accepted in any capitals and stored and
answered in its listed spelling: POST /auth/bootstrap (timezone) and PUT /auth/settings
(display_timezone) answer America/Lima for america/lima. … An unknown zone is still 422
UNSUPPORTED_VALUE.` The app does nothing with a timezone's capitals, so it likely needs nothing.
- **A.** Ask the engine coders for one hand-off file covering `2fa4967b8eed9c3f` →
  `c15201ee50485e56`, and drop it in docs/from-engine/; the loop folds it into the running
  catch-up and resumes.
- **B.** Fold it into the running catch-up now, as a live contract test only, without a file.
**Recommended:** A, because it is the agreed path (each hand-off file covers every version
since the last one, so nothing is skipped), and the file will be short.

[The official import](specs/before-the-official-import.md) is rewritten for built names once
the numbers spec is done, and comes for approval then.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
CLAUDE.md "Specs and tasks".

- **After a reload that fails, the ledger's footer and `?` card keep its row keys** (`a`, `c`,
  `b`, `h`, `m`, `s`, `d`) with no list on screen, since `TransactionsScreen.has_rows`
  (`expense/tui/screens/transactions.py`) reads the rows read before; the Manage lists drop them.
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
