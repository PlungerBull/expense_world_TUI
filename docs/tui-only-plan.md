# The TUI is the only human surface; the flat CLI is for the agent

**For:** whoever builds this repo's next pass after the engine uptake. **Written:** 2026-09-26.
**Starts after:** item 0 in [todo.md](todo.md) *Now* ("Engine uptake"), and after whatever else is
in flight when it closes. Nothing here is started before then.
**When done:** the why moves to [decisions.md](decisions.md), and this file is deleted.

---

## The decision (owner, 2026-09-26)

**The owner only ever uses the TUI (`expense world`).** The flat commands
(`expense <group> <verb> --flag`) stay only as **thin commands the agent uses to check things**:
Claude verifying a change against the engine, the contract suite, and anything that wants
`--json`. They are no longer a product for a person.

**What prompted it.** The owner had understood that the TUI worked by calling the flat commands,
so the CLI had to exist for the TUI to work. That was never true. Both are faces on the same Python
functions (`fetch_*`, the formatters, `EngineWriteMixin.run_write`, [expense/http.py](../expense/http.py)),
and the TUI never runs a command. The repo was therefore building and polishing each feature twice
(a Typer command with human tables, pagination lines, docstrings and tests, plus a TUI screen) for
a flat surface nobody reads.

**What stays true.** The engine is still the only home of business logic. Every engine endpoint
is still exercised before web and iOS exist. The difference is who does it: **the owner, through
the TUI, for real use**, and **the agent, through the flat commands, for checks**. Neither the
iOS app nor the web dashboard will ever call this repo; both talk to the engine's HTTPS API
directly.

**What it replaces:** decisions.md "Dual-UX strategy — flat commands + TUI + quick-add
(2026-04-25)", which made flat commands "canonical … always the source of truth for behavior".
That entry is superseded, not deleted, and the new entry says why.

## Open questions for the owner

None of these is decided. Each gets an answer before its step starts. The "leaning" lines are
the builder's suggestion, not a decision.

1. **Human output.** Should the flat commands print `--json` only, which means deleting the human
   tables, pagination footers, colour swatches and name columns? Or should they keep a plain human
   mode? *Leaning: JSON only. The agent reads JSON, and the TUI is the human view.*
2. **Coverage.** Should every engine endpoint keep one thin command, or only the ones the agent
   actually uses? *Leaning: one per endpoint, so the agent can check any of them.*
3. **Imports and `expense log`.** `import bank` and `import sheet` are flat-only today. There is
   no TUI door until [file-import-plan.md](file-import-plan.md) §3 (C1) ships, and `import bank`
   asks the owner which account a file belongs to. Do they stay as human commands until C1 lands?
   What happens to them after that? The same question applies to `expense log "<line>"`, which is
   the flat twin of the LOG bar.
4. **Guard tests and prompts.** [test_command_surface.py](../tests/unit/test_command_surface.py)
   requires an `Example:` docstring and an error-shape test for every command, `--json` on every
   read and `--yes` on every destructive write. Confirmation prompts are for people, and the agent
   always passes `--yes`. Which guards stay?
5. **Where the shared layer lives.** The TUI imports its reads and formatters from
   `expense/commands/*` (e.g. `_resource.py`, `transactions_cmd`, `dashboard_cmd`). If the commands
   shrink, should the shared code move to a package that isn't named after them?
6. **The repo's new name.** GitHub `PlungerBull/expense_CLI_menu`, local folder
   `expense_world_CLI`. What should it be? Does the `expense` entry point keep its name?
7. **The note to the engine coder.** Does the draft below say what you want said?

## Consequences that follow directly

These follow from the decision as stated. They are listed so the owner can check them.

- **Rules to rewrite:** CLAUDE.md "What this repo is", "Product scope and role" (the contract
  validator is now the owner using the TUI plus the agent using flat commands) and "Status".
  [cli-spec.md](cli-spec.md) "Principles" ("human-readable by default") and "Output conventions"
  (the table process rule). The mockup rule stops covering flat tables. It still covers every
  TUI screen.
- **todo.md items that lose their reason:** Ergonomics "Shell completions", "Human-name
  resolution for reference flags", "Move between accounts convenience", and Parked "Flat-CLI
  color conventions". "`expense import csv`" depends on question 3.
- **New work goes TUI-first.** A new engine capability gets its TUI screen, plus a flat command
  only as thin as the answer to question 1 allows.

## Steps

1. **Record the decision.** Add a decisions.md entry (Context / Decision / Rejected) that
   supersedes "Dual-UX strategy". Rewrite the CLAUDE.md and cli-spec.md sections above.
2. **Trim the flat surface** to the answers to questions 1–5. That means human renderers,
   pagination footers and prompts, their tests, and the guards in `test_command_surface.py`.
   Move the shared layer if question 5 says so. The unit suite stays green at every commit.
3. **Clean todo.md.** Delete the items listed above.
4. **Rename the repo** (question 6): `gh repo rename` on GitHub (push access needs
   `gh auth switch --user PlungerBull`), update the local remote, rename the local folder if the
   owner wants that, and update the references in this repo: [CLAUDE.md](../CLAUDE.md),
   [README.md](../README.md), [cli-spec.md](cli-spec.md) and the "Repo name note" at the top of
   CLAUDE.md. `test_docs_links.py` catches any broken relative link.
5. **Notify the engine coder.** The owner hands over the note below. This repo never edits the
   engine. As of 2026-09-26, the engine files that name this repo are `deploy/local/README.md`,
   `deploy/local/seed-test-user.sh`, `docs/open-bugs.md`, `docs/file-import-plan.md` and
   `docs/currency-model-decision.md`.
6. **Delete this file**, and its row in todo.md.

## Draft note to the engine coder

> The terminal client (`PlungerBull/expense_CLI_menu`) is being renamed to **<new name>**.
> Please update the references in `deploy/local/README.md`, `deploy/local/seed-test-user.sh`,
> `docs/open-bugs.md`, `docs/file-import-plan.md` and `docs/currency-model-decision.md`, plus
> any sibling-checkout paths.
>
> What else changed: the owner uses only the TUI (`expense world`). The flat `expense …` commands
> are now thin agent-verification tools, not a human surface. Nothing changes for the engine:
> the TUI calls the same endpoints and still exercises them through real use. When the engine
> docs call "the CLI" the first client, they now mean the TUI plus its agent-facing commands.
