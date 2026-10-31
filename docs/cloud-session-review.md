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

## Points for the local review

- **Practice keys pasted into the chat.** On 2026-10-31 the owner pasted that run's two
  practice keys into the cloud chat. They open only the practice database, and the next `up`
  revokes them. Nothing was written to a file.
- **A clash between instructions.** The cloud session was given a branch,
  `claude/expense-world-tui-status-y13c9y`, but pushes to `main` as CLAUDE.md says, at the
  owner's word (2026-10-31). The branch still exists on GitHub at commit 9ab470d. Delete it
  once this review is done.
