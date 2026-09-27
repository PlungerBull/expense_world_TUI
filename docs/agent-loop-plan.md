# Agent loop setup — plan

**Status:** §6.1 is built — its rules are in CLAUDE.md "How work runs (the agent loop)"; §6.2–6.4
next. Written 2026-09-27. Delete this doc when the setup
ships; its lasting rules move to [CLAUDE.md](../CLAUDE.md), its why to
[decisions.md](decisions.md).

## 1. What we are building, in one paragraph

The owner is not a coder. AI agents make every technical decision; the owner decides only
what users see (screens, flows, wording), business rules the spec does not cover, and anything
touching real data. Work runs as a **loop**: a main session (the *orchestrator*) takes a task
from the task list, hands it to a *builder*, has a *tester* check it, has a *reviewer* check
it, and only then commits it. Anything that needs the owner goes into a question list instead
of being guessed.

## 2. Decisions already made

| Decision | Date |
|---|---|
| **One loop per repo**, not one loop over the whole `productivity_world` folder. "Done" (tests pass, committed) only means something inside one repo, and the wall between this client and the engine stays automatic. The worker roles are written once and shared by every repo; each repo supplies its own rules through its own CLAUDE.md. | 2026-09-27 |
| **Start with this repo.** It has the most tests and guard rules, so it is the safest place to prove the setup. The engine repo copies it afterwards. | 2026-09-27 |
| **[todo.md](todo.md) is the official task list.** "Done" still means *deleted from the list in the same commit* (the existing rule — git history is the archive). | 2026-09-27 |
| **[decisions.md](decisions.md) is the official decision log.** | 2026-09-27 |
| **Agents never look outside the current repo** unless the owner permits it for that occasion. | 2026-09-27 |
| **The engine publishes its whole contract** at `GET /openapi.json` (every endpoint, rule and error code; a version that moves on any change; readable without login; no pointers into the engine repo; no secrets). Asked 2026-09-27; **shipped and verified 2026-09-27** (engine commit `fd7243c`). Clients read the contract from a running engine, never from the engine's folder. | 2026-09-27 |
| **The loop runs on its own** once the owner approves the task list: it builds, tests and commits without checking in per task, and stops only for §5 items and escalations. | 2026-09-27 |
| **Push to GitHub after every finished task**, so GitHub's checks run on each one. | 2026-09-27 |
| **Screen tasks don't stall the loop:** the loop draws the mockup, parks the task, adds a question for the owner, and moves on. | 2026-09-27 |
| **Questions for the owner live in [todo.md](todo.md) "Questions for the owner"**, a section of their own; every existing owner question moved there. | 2026-09-27 |
| **Every session is the orchestrator, always** — a plain chat with the owner included. The main session never writes code or tests. | 2026-09-27 |
| **The tester never writes tests or code.** When a criterion has no test that proves it, the tester says so in its report and the builder writes the test. | 2026-09-27 |
| **A fourth worker, the librarian, keeps the docs aligned.** Every fact lives in exactly one doc and the others link to it, because a fact written in two places drifts: one copy gets changed and the other is forgotten. It fixes docs itself (never code, never todo.md or decisions.md). It checks the docs each task touched, and sweeps every doc when a spec finishes. | 2026-09-27 |
| **One spec per piece of work, written by the owner** (in `docs/specs/`). The owner tells the orchestrator which spec is current; the orchestrator drafts that spec's tasks into todo.md and the owner approves them before the loop runs. The existing agent-written plan docs become drafts the owner rewrites or approves before their work starts. | 2026-09-27 |

## 3. The roles

| Role | What it does | What it may touch |
|---|---|---|
| **Orchestrator** (the main session) | Picks the next task, writes its acceptance criteria, delegates, reads reports, decides the next step, commits, updates todo.md / decisions.md / the question list. **Never writes code.** | Docs only |
| **Builder** | Implements one task, following CLAUDE.md. Reports what changed and why. | Code, tests, docs of this repo |
| **Tester** | Checks the work against the task's acceptance criteria: runs the test suite, runs the app against the test engine, reports pass/fail with evidence. When a criterion has no test proving it, says so, and the builder writes one. | Runs things; never edits code or tests |
| **Reviewer** | Reads the change for quality, security and this repo's rules (thin wrapper, no business logic, no literal colours, no secrets, one copy of shared code). Doc structure is the librarian's. | Read-only |
| **Librarian** | Keeps the docs aligned: every fact in one home with the other docs linking to it, no two docs disagreeing, docs matching the code, broken pointers fixed, the repo's doc rules (present tense, absolute dates, finished work deleted) kept. Where it can't tell which conflicting doc is right, it asks instead of picking. Reports what it moved or cut. | Docs of this repo, except todo.md and decisions.md (what those need goes in its report) |

All four workers answer in the same fixed report shape (verdict, what was checked, what is
wrong, where), so the orchestrator reads them reliably.

## 4. The loop, per task

1. The orchestrator works only on the spec the owner named as current. It takes the next
   approved task for that spec from todo.md and writes its **"passes if…"**
   criteria. A task without clear criteria goes to the owner as a question first.
2. **Builder** implements.
3. **Tester** checks. Fail → back to the builder with the tester's report.
4. **Reviewer** checks. Rejection → back to the builder with the reviewer's report.
5. **Librarian** checks the docs the task touched, and every doc that covers the same things,
   and fixes them. When the task is the last of its spec, it sweeps every doc instead.
6. After **4 failed rounds**, the task is parked, a question goes to the owner, and the loop
   moves on.
7. **Done** = tester passed + reviewer approved + librarian done + committed and pushed + deleted from todo.md
   in that same commit.
8. **When every remaining task is waiting on the owner** (a mockup to pick, a question to
   answer), the loop stops and hands the owner a short summary: what finished, and what is
   waiting in todo.md "Questions for the owner". It does not keep running with nothing to do. The owner
   answers, and restarts the loop.

One task at a time: the repo has a single branch, so parallel builders would collide.

## 5. What always goes to the owner

- **Anything users see** — screens, flows, wording. The existing rule stays: an HTML mockup in
  [mockups/](mockups/), and nothing is built until the owner explicitly picks one.
- **Money or business rules the spec does not cover.** In this repo those usually become an
  engine ask (the engine owns every business rule), which the owner hands to the engine coder.
- **Anything touching real data** — the live engine on `127.0.0.1:8000` and
  `~/.expense-config` are the real ledger.
- **Anything outside this repo.**

Every question is written in plain language with 2–3 options and a recommendation.

## 6. What gets built

Every session is the orchestrator, so the main session builds only docs and Claude config:
the worker files (6.2), the hook settings (6.3) and the settings cleanup (6.4). A hook *script*,
a test, or any other code waits for the builder that 6.2 creates. 6.5 is the loop's first job.

### 6.2 The four worker files

Builder, tester, reviewer and librarian, written once in the owner's personal Claude settings
so every repo shares them. Each one's tool limits are set in its file (§3). Each reads the
repo's CLAUDE.md for that repo's rules, so the files hold only what is the same everywhere.

The librarian's file carries the one-home rule in general terms (which doc owns what comes
from each repo's CLAUDE.md). Building 6.2 also updates CLAUDE.md "How work runs": the librarian
joins the roles table and the per-task loop (§4 steps 5 and 7), and the reviewer's row stops
covering doc structure.

### 6.3 Automatic guards (hooks)

Kept in a shared settings file inside this repo, so they travel with it:

- **After every edit:** tidy-check (`ruff`) the edited file; problems go straight back to the
  builder.
- **Before a commit or "done":** the fast tests (`pytest tests/unit`) must pass.
- **Blocked outright:**
  - any `expense …` command using the real config, and any call to the live engine (`:8000`);
  - reading `~/.expense-config`;
  - reading or writing outside this repo;
  - force-push, history rewrites, new branches, and skipping the pre-commit checks
    (`--no-verify` would skip the secret scan).
- Guards run with the project's own tools (`.venv/bin` on the path — already needed for
  commits today).
- Each guard is tested once by deliberately tripping it.

### 6.4 Cleanup

- Trim `.claude/settings.local.json`: it pre-approves blanket actions (reading anything in the
  home folder, any `git push`, a stored cloud-database login command) that would undermine
  the guards.
- Confirm the fast tests are green before the first loop run.

### 6.5 Take up the engine's published contract (the loop's first spec and trial run)

Built by the loop itself, once 6.1–6.4 exist: it is the first spec the owner writes, and the
trial run. Today this repo still reads the engine's folder. Once this lands, it doesn't:

1. Agents and `scripts/check_fixture_drift.py` read the contract from the **test engine**
   (`:8002`), and record the contract version last checked against, so a version change is
   noticed.
2. Remove every link into `../expense_world_engine` — CLAUDE.md, README, cli-spec.md, other
   docs, and the engine half of `tests/unit/test_docs_links.py`.
3. Code comments that cite engine files (`sql/015` in `expense/currencies.py`, `sql/026` in
   `expense/http.py`, and any others) cite the contract instead.
4. Then "never read outside this repo" becomes absolute.

## 7. Rollout

1. Owner answers the open questions (§8).
2. Build §6.1–6.4.
3. **Trial run:** the loop runs §6.5 as its first spec, owner watching.
4. Adjust, record the setup in decisions.md, delete this doc.
5. Later: copy to the engine repo (with guards for its own real database); optionally a
   read-only status board at the `productivity_world` level showing each repo's loop and
   what waits on the owner.

## 8. Open questions for the owner

In [todo.md](todo.md) "Questions for the owner" ("Which spec does the loop run first?").
