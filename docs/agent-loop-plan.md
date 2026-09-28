# Agent loop setup — plan

**Status:** The rules, the four workers, the guards and the loop's pre-approved commands are
built (CLAUDE.md "How work runs", "Dev loop" → "Guards (hooks)"); §6.5 in progress: its spec
is written and its tasks are approved. Written 2026-09-27. Delete this doc when the setup ships; its lasting rules move to [CLAUDE.md](../CLAUDE.md), its why to
[decisions.md](decisions.md).

The roles, the loop per task and per spec, and what goes to the owner live in [CLAUDE.md](../CLAUDE.md)
"How work runs (the agent loop)".

## 2. Decisions already made

| Decision | Date |
|---|---|
| **One loop per repo**, not one loop over the whole `productivity_world` folder. "Done" (tests pass, committed) only means something inside one repo, and the wall between this client and the engine stays automatic. The worker roles are written once and shared by every repo; each repo supplies its own rules through its own CLAUDE.md. | 2026-09-27 |
| **Start with this repo.** It has the most tests and guard rules, so it is the safest place to prove the setup. The engine repo copies it afterwards. | 2026-09-27 |
| **A spec's tasks live in that spec**, in a "Tasks" section the orchestrator drafts and the owner approves; [todo.md](todo.md) stays the hub for work that belongs to no spec. "Done" still means *deleted from its list in the same commit* (the existing rule — git history is the archive). | 2026-09-27 |
| **[decisions.md](decisions.md) is the official decision log.** | 2026-09-27 |
| **Agents never look outside the current repo** unless the owner permits it for that occasion. | 2026-09-27 |
| **The engine publishes its whole contract** at `GET /openapi.json` (every endpoint, rule and error code; a version that moves on any change; readable without login; no pointers into the engine repo; no secrets). Shipped (engine commit `fd7243c`). Clients read the contract from a running engine, never from the engine's folder. | 2026-09-27 |
| **The loop runs on its own** once the owner approves the task list: it builds, tests and commits without checking in per task, and stops only for what CLAUDE.md "How work runs" sends to the owner, and escalations. | 2026-09-27 |
| **Push to GitHub after every finished task**, so GitHub's checks run on each one. | 2026-09-27 |
| **Screen tasks don't stall the loop:** the loop draws the mockup, parks the task, adds a question for the owner, and moves on. | 2026-09-27 |
| **Questions for the owner live in [todo.md](todo.md) "Questions for the owner"**, a section of their own; every existing owner question moved there. | 2026-09-27 |
| **Every session is the orchestrator, always** — a plain chat with the owner included. The main session never writes code or tests. | 2026-09-27 |
| **The tester never writes tests or code.** When a criterion has no test that proves it, the tester says so in its report and the builder writes the test. | 2026-09-27 |
| **A fourth worker, the librarian, keeps the docs aligned.** Every fact lives in exactly one doc and the others link to it, because a fact written in two places drifts: one copy gets changed and the other is forgotten. It fixes docs itself (never code, never todo.md or decisions.md). When it runs: [CLAUDE.md](../CLAUDE.md) "How work runs". | 2026-09-27 |
| **One spec per piece of work, written by the owner** (in `docs/specs/`). The owner tells the orchestrator which spec is current; the orchestrator drafts that spec's tasks into the spec and the owner approves them before the loop runs. The existing agent-written plan docs become drafts the owner rewrites or approves before their work starts. | 2026-09-27 |
| **Workers run on the same model as the main session** (`model: inherit`), whichever the owner picked for it. | 2026-09-27 |
| **The tester may start the test engine** (`:8002`, from the engine folder) — the one standing exception to "never outside this repo"; it never reads or edits an engine file. It **recreates the practice user each check** and uses that fresh key for that check only, so nothing is stored and practice data starts clean. | 2026-09-27 |

## 6. What gets built

Every session is the orchestrator, so the main session builds only docs and Claude config. A
test or any other code waits for the builder. 6.5 is the loop's first job.

### 6.5 Take up the engine's published contract (the loop's first spec and trial run)

The loop's first spec and trial run: [specs/engine-contract.md](specs/engine-contract.md).

## 7. Rollout

1. Owner answers the open questions (§8).
2. **Trial run:** the loop runs §6.5 as its first spec, owner watching.
3. Adjust, record the setup in decisions.md, delete this doc.
4. Later: copy to the engine repo (with guards for its own real database); optionally a
   read-only status board at the `productivity_world` level showing each repo's loop and
   what waits on the owner.

## 8. Open questions for the owner

None. Owner questions live in [todo.md](todo.md) "Questions for the owner".
