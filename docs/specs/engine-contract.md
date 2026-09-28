# Spec: learn the engine only from its published contract

Written 2026-09-27. The loop's first spec and its trial run.

## Why

This repo learns how the engine behaves by reading files inside the engine's folder:
docs link to them, code comments cite them, and agents are allowed
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
5. **No code comment cites an engine file.** Comments that cite the engine's spec file or one of
   its database migrations cite the part of the contract
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

All tasks are done. Next: the tester's acceptance check, then the librarian's sweep
(CLAUDE.md "How work runs", "Per spec").
