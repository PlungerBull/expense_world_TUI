# Cloud session review — work to check

The owner asked for this file on 2026-10-31, so that a later local session can review the work
done in a Claude Code cloud session. It is a log, so unlike the other docs it records history.
It is deleted once that review is done; anything the review keeps goes to its usual home
(todo.md, a spec, decisions.md).

## How the cloud session works

- **Where the work happens.** The cloud session has no practice engine. It builds and reviews
  code there, commits, and pushes straight to `main`. The owner pulls, runs the round's live
  tests on their Mac with `scripts/practice-engine up`, then `down`, and pastes back the result.
- **The rounds.** They are saved in part 4's spec,
  [catch-up-currencies-4-live-suite-upload-lines-kinds.md](specs/catch-up-currencies-4-live-suite-upload-lines-kinds.md)
  ("How the tasks run"). A task leaves the spec's list only once its live tests pass.
- **Roles.** The loop's roles are kept. `~/.claude/agents/` is not in the cloud box, so each
  builder and reviewer is a general-purpose agent briefed from CLAUDE.md. Every task gets a
  fresh builder and a fresh reviewer.
- **Checks run in the cloud.** Ruff, mypy and gitleaks run through pre-commit, and the unit
  suite through the commit hook. The project is installed into `.venv` with
  `pip install -e ".[dev]" -c constraints.txt`.

## Log, one entry per commit

Each entry gives the commit, what changed, who reviewed it, and the live result.

### 9ab470d — Save progress before moving to Claude cloud session (2026-10-31, local)
The previous local agent's unfinished task 3 of part 4, committed by hand when credits ran out.
It adds `CardRow`, `CardCharge` and `card_paper` to `tests/contract/conftest.py`, three tests to
`tests/contract/test_statement_import.py`, and one line to `docs/runtime.md`. Neither reviewed
nor run live when committed.

### 8ac13fa — the rounds saved in part 4's spec
Docs only: the "How the tasks run" paragraph in part 4's spec.

### 4ffaaa7 — task 3's review fixes
- **First review:** rejected on two wrong comments. The arithmetic, signatures and the refusal
  message were all checked and right.
- **The fixes, made by a builder:**
  - the comment on the soles-only March now says S/ 1,350.00 billed;
  - the module docstring names the published samples and both drawn papers;
  - the drawn `card` sample test signs its dated rows, interest and fees through one helper,
    `_card_cents`. This one was asked for by the owner: the test used to take the interest and
    fee amounts unsigned.
- **Second review:** approved.

### cc63887 — task 3 done
- **Live run on the owner's Mac (2026-10-31):** `test_statement_import.py` passed 22 of 22.
- **The live citation test failed, as expected.** Every broken citation is in files that tasks
  4–8 or part 7 rewrite, apart from `docs/runtime.md` line 94. That line was broken before task
  3, and it now sits under part 4's "Found along the way".

### ba60b54 — this review log
This file, and the "Review the cloud session's work" question in todo.md.

### The owner moves the cloud session to the features (2026-10-31)
The builders cannot read the live contract from the cloud box. At the owner's ask, part 4's
tasks 4 to 8 and part 5 wait for local credits, and the cloud session turns to the feature
specs, parts 6 and 7. Their first step is drawing the mockups their questions wait on. Parts 6
and 7 are still drafts that the owner has not approved.

### af40497, 595a4d5 and the next commit — mockups for parts 6 and 7
Three pages, each drawn by a builder agent from the spec's questions and today's screens in
tui.md, with made-up data:
- `expense-world-currencies-accounts-picks.html`: part 6, questions 1, 2, 3, 5, 6 and 7;
- `expense-world-currencies-transaction-picks.html`: part 6, questions 8 to 11;
- `expense-world-statement-form-picks.html`: part 7, questions 1 and 4.

Each spec question now links its page. The gaps the drawers filled, to check at review:
- **Placeholder keys and marks:** `c` adds a currency, `%` marks the LOG bar's currency token
  and `m` moves rows to another currency in bulk.
- **Choices the drawers made:**
  - under 1 B, the accounts table drops its `Cur` column;
  - in 1 B, a picked currency's starting balance is required;
  - in 4 A, only an uncovered currency's note is led by its code;
  - a two-currency account with no currency typed is refused in the LOG bar.
- **Two cases the spec does not cover:**
  - what the add-a-currency key says on an account that already holds every currency;
  - under 6 B, whether a new currency's opening balance lines show before the save.
- **Every engine sentence on the three pages is illustrative,** not the engine's wording.

### The owner's answers to parts 6 and 7 (2026-10-31)
Recorded under each question of the two specs. Every answer follows the recommendation except
two: Manage ▸ Accounts takes a column per currency (6.1 C), and Home a line per currency (6.2 B),
both "for now". Since 6.1 C leaves no currency line, a currency is removed through its own key
on the account's row (6.7), mirroring the add key; that pick is not drawn yet. The placeholder
keys `c`, `%` and `m` stay.

### Parts 6 and 7 approved; part 6a's tasks revised (2026-10-31)
The owner approved both specs. Part 6a's drafted tasks 1, 2, 6 and 7 now follow the answers:
- task 1: the columns Name, Type, Code, Color, PEN, USD and Status;
- task 2: Home's line per currency and the settled fold;
- task 6: `c` on the account's row;
- task 7: its own remove key, waiting on its mockup.

The owner approves the task list before any build.

### Part 6a task 1 — Manage ▸ Accounts, one row per account
- **What changed:** one row per account, with the columns Name, Type, Code, Color, a column per
  supported currency and Status. A dim `—` shows where a currency is not held, the `Cur` column
  is gone, and an archived account is dimmed whole.
- **Where:** `expense/tui/screens/accounts.py`; tests in `test_tui_accounts.py` and five other
  screen test files whose cursor keys are now account ids; tui.md §2.
- **Interim narrowing, accepted by the reviewer:** `e` opens the Edit form on the account's
  first currency, so a second currency's opening balance is out of reach until task 5.
  decisions.md says so.
- **Review:** approved on the first round. The 15 test files touching the screen pass (396
  tests).
- **The `x` mockup** (`expense-world-currencies-remove-key.html`), drawn for task 7, rides along
  in the same commit, waiting for the owner's OK.
- **Not done:** the outbox reply `to-engine/reply-f82426fb0a099676-1-reads-and-writes.md`
  line 35 still speaks of "either row" and "the dollars row" of Manage ▸ Accounts. It is left
  as sent, being a record of what part 1 shipped.

### Part 6a task 2 — Home's BANK ACCOUNTS and PEOPLE
- **What changed:** each account is a row with an indented line per currency, balances as sent.
  A person folds into `▶ N settled` only when every currency is exactly 0, counted per person
  (`split_settled` in formatting.py).
- **`⏎`** on the row or on a currency's line opens the ledger on the whole account. Before, it
  filtered by account and currency; filtering a currency's line by that currency comes back in
  task 12.
- **Review:** rejected in round 1 for a stale test (`test_tui_bracketed_names.py`), approved in
  round 2. 409 tests pass across the 14 files that drive Home.
- **decisions.md:** three stale lines updated (the settled rule, Home's rows, and the "one row
  named <account> · <code>" entry).
- **Note for review:** the reviewer judged the fold rule display logic, not business logic. An
  engine-sent "settled" flag per person would be a possible engine ask.

### Part 6a task 3 — the New form's currencies line
- **What changed:** CURRENCY becomes a `currencies` line, picked as the Edit form's HASHTAGS line
  picks (the shared `picker.matching` and `suggestion_list`).
- **What is sent:** one `POST /accounts` with `currencies` in the order picked, `is_person: true`
  for a person, and `statement_code` only on a bank account.
- **Refusals:** the cursor lands on the line the engine names, through a new `_refusal_text`
  hook on `FormScreen` that defaults to `format_error`. Edit account inherits the landing.
- **The line is required on the client,** as the old CURRENCY line was; the reviewer judged that
  a well-formedness check.
- **Review:** approved on the first round, with 762 tests passing.
- **Follow-ups** under part 6's "Found along the way": no un-pick, `ctrl+s` dropping a typed
  code, and an untested `color` refusal.

### Part 6a task 4 — the Edit form's account write
- **Already met by the code:** name, colour and code go in one `PUT /accounts/{id}`, an emptied
  code as `null`, and `STATEMENT_CODE_EXISTS` reads in the engine's words alone.
- **What the task added:** two tests pinning the single PUT, the `EditAccountScreen` docstring,
  and tui.md wording.
- **Review:** approved on the first round. A mislabelled mockup pane ("3·2 B" for 3·2 A) goes
  under "Found along the way".

### Part 6a task 5 — the opening balance per currency
- **What changed:** the account Edit form opens on the account, with a `PEN opening` / `PEN as
  of` pair per held currency, in the engine's order. Each pair reads its own opening
  transaction. A failed read locks only that pair.
- **The save:** the account PUT first, then one request per changed currency. A refusal stops
  what is behind it, and a currency already saved is not sent again.
- **`debt` / `credit` / nothing** shows on the right of the bar (`#bar-word`, a new
  `_form.py` hook).
- **Lifted:** task 1's first-currency limit; decisions.md updated.
- **Review:** rejected in round 1. Two typed-input notes went through a markup-read notify,
  failing `test_toast_words.py`, and the read loop handed back without `call_while_attached`.
  Approved in round 2, with 740 tests passing and two extra tests (one read failing; a POSTed
  row changed by its id).
- **New wording** is built as proposed and waits on the owner's OK, under part 6's "Found along
  the way".

### Part 6a task 6 — `c` adds a currency
- **The key:** `c` on Manage ▸ Accounts (footer `c Currency`) opens a new shared `PickModal`
  listing the supported currencies the account does not hold.
- **The write:** `⏎` sends one `POST /accounts/{id}/currencies` with `{"currency_code": …}`
  through `run_write`, and the list reads fresh. On a full account it shows the owner-approved
  note.
- **Refusals** read in the engine's words.
- **Review:** approved on the first round, with 2184 tests passing across every file using
  modals or the screen.
- **Unconfirmed:** the request body is not checkable here. It follows part 5's plan for the
  live test.
- **Waiting on the owner:** three wording points, under part 6's "Found along the way".

### Part 6a task 8 — `a`, `t` and `d` on the whole account; the holder mockups go
- **Already met by the handlers:** `a`, `t` and `d` act on the account by id. New tests pin one
  request each and the whole row redrawn; the delete question names each currency as pane 1
  draws it; `IN_LIVE_STATEMENT` reads in the engine's words alone.
- **Removed:** `HAS_STATEMENT_CODE` from tui.md's refusal table, errors.py and the unit tests.
  It stays in part 4's contract test and runtime.md line 94 until part 4 rewrites them.
- **Mockups deleted:** the 11 holder-era mockups and `expense-world-person-opening-hint.html`.
  Part 6's spec link was repointed to the 5 A panes.
- **Still on the holder routes,** untouched by this task: `reads.fetch_holders` and
  `reconciliations.py`. Part 7 replaces them.
- **Review:** approved on the first round.

## Points for the local review

- **Practice keys pasted into the chat.** On 2026-10-31 the owner pasted that run's two
  practice keys into the cloud chat. They open only the practice database, and the next `up`
  revokes them. Nothing was written to a file.
- **A clash between instructions.** The cloud session was given a branch,
  `claude/expense-world-tui-status-y13c9y`, but pushes to `main` as CLAUDE.md says, at the
  owner's word (2026-10-31). The branch still exists on GitHub at commit 9ab470d. Delete it
  once this review is done.
