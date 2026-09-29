# The TUI is the only human surface; the flat CLI is for the agent

**Deferred.** Nothing here starts until the owner picks this spec up. Then it starts after
[todo.md](../todo.md) "Check the TUI after the engine update" and whatever else is in flight. **When done:** the why moves to [decisions.md](../decisions.md), and this
file is deleted.

---

## The decision (owner, 2026-09-26)

**The owner only ever uses the TUI (`expense world`).** The flat commands
(`expense <group> <verb> --flag`) stay only as **thin commands the agent uses to check things**:
Claude verifying a change against the engine, the contract suite, and anything that wants
`--json`. They are no longer a product for a person.

**Why.** The TUI never runs a command: both surfaces are faces on the same Python functions
(`fetch_*`, the formatters, `EngineWriteMixin.run_write`, [expense/http.py](../../expense/http.py)),
so polishing a flat human surface nobody reads was building every feature twice.

**What stays true.** The engine is still the only home of business logic. Every engine endpoint
is still exercised before web and iOS exist. The difference is who does it: **the owner, through
the TUI, for real use**, and **the agent, through the flat commands, for checks**. Neither the
iOS app nor the web dashboard will ever call this repo; both talk to the engine's HTTPS API
directly.

**What it replaces:** decisions.md "Dual-UX strategy — flat commands + TUI + quick-add
(2026-04-25)", which made flat commands canonical.

## Open questions for the owner

Each gets an answer before its step starts. They wait here, not in todo.md, while the spec is
deferred.

### Should the flat commands print JSON only?
Asked 2026-09-26
- **A.** JSON only. The human tables, page footers, colour swatches and name columns go.
- **B.** Keep a plain human mode.

**Recommended:** A. The agent reads JSON, and the TUI is the human view.

### One flat command per engine endpoint, or only the ones the agent uses?
Asked 2026-09-26
- **A.** One per endpoint.
- **B.** Only the ones the agent actually uses.

**Recommended:** A, so the agent can check any endpoint.

### What happens to `import bank`, `import sheet` and `expense log`?
Asked 2026-09-26
The imports are flat-only until the TUI import door ships, and `import bank` asks you which
account a file belongs to. `expense log "<line>"` is the flat twin of the LOG bar.
- **A.** They stay as human commands until the TUI import door ships, then shrink like the
  rest.
- **B.** They stay as human commands for good.

**Recommended:** none yet.

### Which command guard tests stay?
Asked 2026-09-26
Every flat command must have an `Example:`, an error test, `--json` on reads and `--yes` on
deletes ([test_command_surface.py](../../tests/unit/test_command_surface.py)). Confirmation prompts
are for people, and the agent always passes `--yes`.
- **A.** Keep them all.
- **B.** Drop the people-only ones (prompts, `Example:`). Keep the error test and `--json`.

**Recommended:** none yet.

### Where does the shared code live?
Asked 2026-09-26
The TUI takes its reads and formatters from `expense/commands/*`. If the commands shrink, that
name stops fitting.
- **A.** It stays in `expense/commands/`.
- **B.** It moves to a package not named after the commands.

**Recommended:** none yet.

### What is the repo's new name?
Asked 2026-09-26
Today it is `PlungerBull/expense_CLI_menu` on GitHub and `expense_world_CLI` locally. Name it,
and say whether the `expense` command keeps its name:
- **A.** `expense` stays.
- **B.** `expense` changes too, to a name you give.

**Recommended:** A. It is what you type every day.

### Is the note to the engine coder right?
Asked 2026-09-26
The draft is "Draft note to the engine coder" below.
- **A.** Send it as written, with the new name filled in.
- **B.** Change it. Say how.

**Recommended:** A.

## Consequences that follow directly

- **Rules to rewrite:** CLAUDE.md "What this repo is", "Product scope and role" (the contract
  validator is now the owner using the TUI plus the agent using flat commands) and "Status".
  [cli-spec.md](../cli-spec.md) "Principles" ("human-readable by default") and "Output conventions"
  (the table process rule). The mockup rule stops covering flat tables. It still covers every
  TUI screen.
- **todo.md items that lose their reason:** Backlog "Shell completions", "Human-name
  resolution for reference flags", "Move between accounts convenience", and Parked "Flat-CLI
  color conventions". "`expense import csv`" depends on the imports question.
- **New work goes TUI-first.** A new engine capability gets its TUI screen, plus a flat command
  only as thin as the answer on human output allows.

## Steps

1. **Record the decision.** Add a decisions.md entry (Context / Decision / Rejected) that
   supersedes "Dual-UX strategy". Rewrite the CLAUDE.md and cli-spec.md sections above.
2. **Trim the flat surface** to the answers on output, coverage, imports, guard tests and shared code. That means human renderers,
   pagination footers and prompts, their tests, and the guards in `test_command_surface.py`.
   Move the shared layer if the shared-code answer says so. The unit suite stays green at every commit.
3. **Clean todo.md.** Delete the items listed above.
4. **Rename the repo** (the new-name question): `gh repo rename` on GitHub (push access needs
   `gh auth switch --user PlungerBull`), update the local remote, rename the local folder if the
   owner wants that, and update the references in this repo: [CLAUDE.md](../../CLAUDE.md),
   [README.md](../../README.md), [cli-spec.md](../cli-spec.md) and the "Repo name note" at the top of
   CLAUDE.md. `test_docs_links.py` catches any broken relative link.
5. **Notify the engine coder.** The owner hands over the note below. This repo never edits the
   engine; the engine coder finds the references to the old name in the engine repo.
6. **Delete this file**, and its row in todo.md.

## Draft note to the engine coder

> The terminal client (`PlungerBull/expense_CLI_menu`) is being renamed to **<new name>**.
> Please update every reference to the old name in the engine repo (its local-deployment guide,
> the practice-user seed script and its decisions log), plus any sibling-checkout paths.
>
> What else changed: the owner uses only the TUI (`expense world`). The flat `expense …` commands
> are now thin agent-verification tools, not a human surface. Nothing changes for the engine:
> the TUI calls the same endpoints and still exercises them through real use. When the engine
> docs call "the CLI" the first client, they now mean the TUI plus its agent-facing commands.
