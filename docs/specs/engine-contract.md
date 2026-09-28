# Spec: learn the engine only from its published contract

Written 2026-09-27. The loop's first spec and its trial run.

## Why

This repo learns how the engine behaves by reading files inside the engine's folder
(`../expense_world_engine`): docs link to them, code comments cite them, and agents are allowed
to open them. That breaks the rule that agents stay inside this repo, and it will not work for
the web and iOS clients, which never see the engine's folder.

The engine now publishes its whole contract (every endpoint, rule and error code) at
`GET /openapi.json` on any running engine, with a version number that changes whenever the
contract changes. This spec makes that contract the only way this repo learns about the engine.

## What must be true when it is done

1. **The contract comes from the practice engine, live.** Whenever an agent or a script needs
   to know how the engine behaves, it reads `/openapi.json` from the practice engine (`:8002`).
   No copy of the contract is kept in this repo. When the practice engine is not running, only
   the tester starts it, as today.
2. **The repo remembers which contract version it last checked against.** Only the version
   number is saved in the repo, not the contract. When the practice engine reports a
   different version, the difference is noticed and reported. It is never silently accepted.
3. **An engine change goes to the owner, not straight into work.** When the version has moved,
   the loop adds a question to [todo.md](../todo.md) "Questions for the owner" saying what
   changed in the contract. The owner decides whether catching up becomes the next spec. The
   loop does not fix it on its own, even when it is between tasks.
4. **No doc links into the engine's folder.** CLAUDE.md, README, cli-spec.md, cli-runtime.md,
   decisions.md, todo.md, the plan docs and every other doc point at the contract instead. The
   link checker stops checking links into the engine's folder, because none remain.
5. **No code comment cites an engine file.** Comments that cite `engine-spec.md` or an engine
   migration (`sql/015`, `sql/026`, `sql/036` and the rest) cite the part of the contract
   that states the rule instead.
6. **Agents read nothing in the engine's folder.** The only access left is the tester
   starting and reseeding the practice engine there, exactly as today. No agent reads any file
   there, including the tester. The guards block reads, and the repo's pre-approved reads of
   the engine docs are removed. The guard tests prove the block.
7. **Nothing else changes.** Screens, commands and their output stay the same. The unit tests
   pass, and the check comparing test data to the engine passes against the practice engine.

## How the owner knows it is done

- A search of the repo for `expense_world_engine` finds only the commands that start the
  practice engine and the program's name.
- An agent that tries to open an engine file is stopped by the guard.
- The saved version matches what the practice engine reports.
- When the owner changes the engine's contract and runs the check again, a question about the
  change appears in todo.md.

## Not in this spec

- Changing any command, screen or engine behaviour.
- Setting the loop up in the engine repo (a later step of
  [agent-loop-plan.md](../agent-loop-plan.md)).

## Tasks

Drafted by the orchestrator and approved by the owner 2026-09-27. One at a time, in
this order. Each is deleted here in the commit that finishes it.

The practice engine (`:8002`) must be running for any task that reads the contract. Only the
tester starts it; the orchestrator has the tester start it before handing such a task to the
builder, and it is stopped after the task.

### The loop checks the version, and a change goes to the owner
Passes if:
- CLAUDE.md says the tester runs the version check at the start of every check and puts the
  result in its report.
- CLAUDE.md says that on a moved version, the orchestrator stops starting new tasks and files
  a question for the owner in todo.md listing what changed: the contract's own change-log
  entries (`x-changelog` in `/openapi.json`) newer than the saved version, or "the whole
  contract changed" when the saved version is not in the log.
- The version check prints those entries when the version has moved, so the tester's report
  carries them.
- The engine ask `docs/engine-asks/contract-change-log.md` is deleted in the same commit; it has
  landed.
- The link checker and the guard tests still pass.

### Code comments cite the contract, not engine files
Passes if:
- No comment or docstring under `expense/`, `tests/` or `scripts/` cites `engine-spec`, an
  engine migration (`sql/0NN`), or an engine module.
- Each rewritten citation names the part of the live contract that states the rule (the
  operation, like `POST /transactions/import`, or the section tag, like "Date windows"), and
  the reviewer spot-checks that the named part really states it.
- No code behaviour changes: `pytest tests/unit` passes unchanged.

### Docs stop linking into the engine's folder
Passes if:
- No doc in the repo (CLAUDE.md, README, `docs/`) links to or cites a path in
  `../expense_world_engine`, apart from the commands the tester uses to start and reseed the
  practice engine.
- Where a doc used such a link to state an engine rule, it points at the live contract instead.
- `tests/unit/test_docs_links.py` no longer checks links into the engine's folder, and a guard
  test fails if such a link comes back.
- The orchestrator rewrites the todo.md and decisions.md mentions in the same commit.

### Close the engine folder to reading
Passes if:
- The guard blocks every agent, the tester included, from reading any file in the engine's
  folder, while the tester can still start and reseed the practice engine there exactly as the
  ops guide says.
- `.claude/settings.json` no longer pre-approves reads of the engine docs.
- `tests/unit/test_claude_hooks.py` proves both: a read is blocked, and the start and reseed
  commands are allowed.
- CLAUDE.md "Stay inside this repo" no longer lists reading the engine as an exception.
- Finally, a search of the repo for `expense_world_engine` finds only the practice-engine
  commands and the program's name. That is the spec's first done-check.
