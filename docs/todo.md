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

Each line carries its version; a version's specs run in the order listed, and its last spec
prepares the release (CLAUDE.md "This repo's loop").

1. **v1.0** · [The app the owner runs](specs/going-live.md): approved 2026-11-11. Every task is
   done; its acceptance check needs the v1.0.0 release installed.
2. **v1.0** · [The official import](specs/before-the-official-import.md): questions 15–17
   answered by 2026-11-13; tasks 1–4 and 6 are done. Its question 18 (2026-11-13) replaces 15 A:
   a bank is a code the owner types, and the import's review makes the accounts. Its new
   tasks wait on the mockup picks and on the engine asks "A bank account's bank is a short code the user
   types, and the engine says which codes it can read"
   and "The sheet import suggests the accounts it is missing and makes the ones the user
   confirms, with its names and rows, in one write"; task 5 waits on both. v1.0.0 is prepared
   after its rehearsal.
3. **v1.1** · [Closing a month with leftover lines](specs/closing-with-leftover-lines.md): approved
   2026-11-08, its question 4 answered 2026-11-11. Blocked: tasks 3 and 5 wait on the engine
   asks "A loose-lines refusal names the statement it would close" and "A close can be checked
   before it is sent".
4. **v1.2** · [The app checks its engine](specs/engine-checks.md): the old tasks 5–7 of the app
   the owner runs, split out 2026-11-12. The engine shipped what they read in contract 1.1;
   tasks 1 and 2 wait on the owner picking their mockups.
5. **v1.3** · [Code conventions B](specs/code-conventions-b.md): approved 2026-11-11.

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
Asked 2026-11-11 · Blocks: the app the owner runs' acceptance check
v1.0.0 is prepared after the official import's rehearsal, as the last spec of v1.0; until then
`scripts/release.py` finds no prepared release and refuses. When the loop's summary says v1.0.0
is ready, run `python3 scripts/release.py` in the live folder
(`~/Library/Application Support/expense_world/tui`; it needs `gh` logged in and `pipx`). Once
`expense` opens as v1.0.0, remove the old install: `pipx uninstall expense-cli-menu`.
**Recommended:** none, steps only you can do.

### Pick the banks and the import's review
Asked 2026-11-13 · Blocks: the official import
[expense-world-banks-and-import-review.html](mockups/expense-world-banks-and-import-review.html)
draws the BANK line taking a typed code, the statement code line at a code the app can't read,
and the import's review. Pane 3 B names a new screen ("Import sheet"). Then hand over the two
engine asks in
[to-engine/](to-engine/), and give the engine coders the account names your sheet uses: they
asked for them to pick the guessing rules, and this repo is public.
**Recommended:** 1A 2B 3B 4A, because a typed code says up front whether the app reads its
papers, and every account is set on one screen, fixable in any order before anything is written.

### Approve "Small screen details"
Asked 2026-11-13 · Blocks: Small screen details
Your picks on panes 1–16 of [expense-world-open-questions.html](mockups/expense-world-open-questions.html)
became [Small screen details](specs/small-screen-details.md): six changes, five of them screens
only, and the upload going straight to its preview once the engine ask "A statement PDF's
upload names its account from the card number the paper prints" lands (it waits in
[to-engine/](to-engine/) for you to hand over). Pane 13 needs nothing: since several cash
accounts, the engine names each `CASH-0001` and up, skipping a taken name, so no person can hold
the cash account's name.
- **A.** Approve it as v1.1, beside closing with leftover lines.
- **B.** Approve it into v1.0, before the official import.
**Recommended:** A, because v1.0 is the import and its release, and none of the six blocks it.

### Build Code conventions B while v1.0 waits?
Asked 2026-11-13 · Blocks: Code conventions B
Everything else in the Queue waits on the engine or on you, and v1.0.0 waits on the rehearsal,
which waits on the engine listing Interbank. Code conventions B (v1.3) could run now, but
v1.0.0 is prepared from `develop`, so whatever is built there first ships in v1.0.0. B changes
how every screen reads the engine's answers, nothing you see.
- **A.** Wait: build nothing past v1.0 until v1.0.0 is prepared.
- **B.** Build it now; it ships in v1.0.0, and the rehearsal then runs on the reworked code.
**Recommended:** A, because v1.0.0 should hold the code the import was rehearsed and reviewed
on, and the wait is only for one engine change.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)). What lands here and how it runs:
the shared loop, `../agent-loop.md` "Specs and tasks".

- **A kind of account for an investment [UI]** — PARDO, the owner's apartment, is a person
  until one exists, then converts in place, keeping its rows and balance. Needs a spec from the
  owner, and an engine ask with it.
- **Four code comments read differently from the code:** expense/http.py:26-27 says a connect
  failure fails fast, though a connect timeout is retried (`TimeoutException`);
  scripts/check_fixture_drift.py:20 says the run fails when the versions differ, leaving out a
  missing saved version; expense/tui/screens/transactions.py:20-21 says an account move sends
  `currency_code` too, though it sends `account_id` alone; expense/tui/screens/edit_form.py:4
  leaves CURRENCY out of the shared fields, though the form shows it after ACCOUNT.
- **Twelve live contract tests check a response's exact key set,** so a compatible `1.x` addition,
  which Base Conventions says a client tolerates, fails them: tests/contract/test_account_reads.py:137,
  :140, :263, :275, test_cash_account.py:181, test_resources_lifecycle.py:67,
  test_transactions_cursor.py:49, :244, test_bank_import.py:306, :351, :381,
  test_reports_and_dashboard.py:133. Each would check its required fields as a subset, as
  test_auth_smoke.py's `/health` test does.
- **About 15 `except Exception` blocks show nothing and log nothing** (the rate check, the header
  stats, the name maps: reads.py:645, :662; _base.py:757, :869, :980, :1029; transactions.py:525,
  :533, :546, :706; statements.py:578, :2158, :2727; header.py:97; cursor_list.py:487; app.py:156),
  so a bug inside one never reaches the log.
- **A 5xx whose body is not the engine's error shape logs only its request line**
  (expense/http.py:159-179), not the body the engine sent.
- **Older `# type: ignore`s mypy no longer needs:** `self.app.after_quit_question(...)` at
  expense/tui/screens/log_bar.py:1051 and setup.py:375 could go through `expense_app(...)` as
  bank_import.py does; modals.py:38-50 keeps four that a Screen-host base could clear.
- **`self._name` shadows Textual's `DOMNode._name`** in `AccountPeek` (log_bar.py:687),
  `EditAccountScreen` (create_forms.py:907) and `StatementLeftoverScreen` (leftover_lines.py:468);
  harmless today, but a rename such as `_account_name` keeps the two apart.

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
