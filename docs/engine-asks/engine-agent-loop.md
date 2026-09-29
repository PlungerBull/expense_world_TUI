# The engine repo runs the same agent loop as the client repo

Raised 2026-09-29.

For the Claude Code session opened in `expense_world_engine`. The owner has given this session
permission to work on this repo. Everything you need is in this file. Do not read the client
repo (`expense_world_CLI`); it has the same loop, described here.

## Why

The owner is not a coder. Work runs through agents that build, check, commit and push without
asking about each task. The owner keeps four things: what users see, money or business rules a
spec does not cover, anything touching real data, and anything outside the repo. The client
repo has run this loop since 2026-09-27; this repo gets its own copy. One loop per repo keeps
"done" meaningful (tests pass, committed and pushed means something only inside one repo) and
keeps the wall between client and engine automatic.

## The ask

### What already exists (do not copy or edit)

- **The four workers** are defined once for every repo in `~/.claude/agents/`: `builder.md`,
  `reviewer.md`, `tester.md`, `librarian.md`. They hold nothing repo-specific. Each one begins
  with *"Your repo's CLAUDE.md is the rulebook — read it first; where this file and it differ,
  it wins."* Everything this repo needs goes into its CLAUDE.md.
- **The orchestrator** is not a file. It is the main session, told its job by CLAUDE.md.
- **The practice engine**: the engine running on `:8002` over the disposable
  `expense_world_test` database, with the practice user recreated by
  the engine's practice-user seed script run with `--force`. The real ledger is the engine on `:8000` and its
  real database.

### What to build, in this order

The guards go first. Until they exist, nothing but instructions stands between an agent and
the real ledger.

1. **The guards**: `.claude/settings.json` and `.claude/hooks/`, with a test for every rule.
2. **The rulebook**: the loop sections in this repo's `CLAUDE.md`. If a CLAUDE.md exists, add
   to it; do not replace what it already says about the engine.
3. **The work files**: `docs/todo.md`, `docs/specs/README.md`, `docs/decisions.md` (create
   or extend).
4. **`AGENTS.md`**: a pointer for tools other than Claude Code.

Run this setup as the repo's first piece of work, with the owner approving the task list before
you start. Commit and push after each item. When all four are in, the loop is live.

---

### 1. The guards

`.claude/settings.json` wires three hooks and pre-approves only routine commands (this repo's
unit tests, its linter and type checker, read-only git, `git add`, the commit form, `git push`
to `main`). `.claude/settings.local.json` is per-machine and stays empty.

- **Guard** (PreToolUse on Bash, Read, Write, Edit, MultiEdit, NotebookRead, NotebookEdit,
  Glob, Grep, WebFetch). Reads the hook JSON on stdin. A blocked call exits 2 with a one-line
  reason on stderr that names the CLAUDE.md section it enforces; an allowed call exits 0
  silently. For this repo it blocks at least:
  - the real ledger: any command or URL naming `:8000`, and any database URL or connection
    that is not `expense_world_test`;
  - migrations, wipes, seeds or resets aimed at anything but `expense_world_test`;
  - a practice-engine start whose database URLs do not all name `expense_world_test` (a start
    that leaves a URL out may fall back to `.env`, which names the real ledger);
  - the practice user's key reaching a file;
  - paths in the home folder outside this repo (except `~/.claude`);
  - stopping any process except the practice engine the tester started;
  - force-push, history rewrites, new branches, `--no-verify`.
  Its docstring states what it blocks and its limits: it is a tripwire, not a sandbox.
- **Tests gate** (PreToolUse on Bash when the command is `git commit`, and SubagentStop for
  `builder`). Runs this repo's fast test suite; a failure exits 2 with the last 40 lines of
  output, which blocks the commit or keeps the builder working. It skips when
  `stop_hook_active` is true, so it cannot loop. It has a time limit inside the hook's budget.
- **Lint on edit** (PostToolUse on Edit, Write, MultiEdit). Runs the linter and formatter
  check on the one file just edited. It reports problems back as `additionalContext` and never
  blocks.
- **Tests for the hooks**: one test that trips each rule and one that shows the allowed form
  passing, so a broken guard fails CI.

### 2. The rulebook: sections CLAUDE.md must have

Adapt the wording to this repo; keep the substance.

- **Key documentation**: which doc owns which fact. The builder updates "the doc that owns
  what it changed" and the librarian checks every fact has one home, so both need this map.
- **Dev loop**: install, the fast test command, lint, format, types, how to commit (single
  branch `main`, pre-commit never skipped, pushing needs the `PlungerBull` GitHub account via
  `gh auth switch --user PlungerBull`), and the guards and what they block.
- **Careful with real data**: the real ledger (`:8000` and its database) is never touched by
  an agent.
- **Doc rules**: each fact has one home and the others link to it; every doc works for a
  reader with no conversation history; absolute dates only; present tense (no history of how
  things got there); a convention that can be checked by a test gets a test.
- **How work runs (the agent loop)**, below.

#### How work runs (the agent loop)

**Roles.** The main session is always the orchestrator, even in a plain chat with the owner.
The others are workers it delegates to.

| Role | Does | May touch |
|---|---|---|
| Orchestrator (main session) | Picks the next task, writes its "passes if…" criteria, delegates, reads reports, commits and pushes, files questions and reasons. Never writes code or tests. | Docs and Claude config; the only role that edits `docs/todo.md`, `docs/decisions.md` and a spec's "Tasks" section |
| Builder | Implements one task and updates the doc that owns what it changed | Code, tests, docs, except todo.md, decisions.md and docs/specs/ |
| Tester | Once per spec, after its last task: the acceptance check, pass/fail/unproven per check with evidence. Starts and stops the practice engine when a task needs it | Runs things; edits nothing |
| Reviewer | Every task: reads the change for correctness, quality, security and CLAUDE.md's rules, and confirms each "passes if…" criterion with evidence | Read-only |
| Librarian | Once per spec, last: one sweep of every doc (one home per fact, no two docs disagreeing, docs matching code, links resolving). Asks instead of picking when it cannot tell which doc is right | Docs, except todo.md, decisions.md and docs/specs/ |

A worker has no owner to ask. When something is unclear or belongs to the owner, it stops and
puts the question in its report. Every worker reports as: **verdict · what was checked · what
is wrong · where**.

**Specs and tasks.** The owner writes one spec per piece of work in `docs/specs/` and names the
current one when starting the loop. The orchestrator drafts the spec's tasks into a "Tasks"
section at the end of the spec; the owner approves them; then the loop runs on its own, on that
spec only. Everything above "Tasks" belongs to the owner.

**Per task:**
1. Take the next approved task and write its "passes if…" criteria. No clear criteria → a
   question for the owner first.
2. Builder implements → reviewer reads and confirms each criterion → orchestrator commits and
   pushes (the commit hook runs the fast tests). A rejection goes back to the builder with the
   report. When the builder needs the practice engine, the tester starts it before and stops
   it after.
3. After 4 failed rounds, park the task, add a question for the owner, move on.
4. Done = reviewer approved + committed and pushed + deleted from the task list in that same
   commit.
5. One task at a time (single branch).
6. When every remaining task waits on the owner, stop and give the owner a short summary.

**Per spec,** once all its tasks are done:
1. The tester runs the acceptance check against the practice engine: the full test suite,
   anything that must run against `expense_world_test`, and each check in the spec's "how the
   owner knows it is done". Each failure becomes a new task; the loop runs it; the tester
   checks again.
2. The librarian sweeps every doc.
3. Done = acceptance check passed + sweep done. The spec's why moves to decisions.md and the
   spec file is deleted.

**What always goes to the owner, never guessed:**
- Money or business rules a spec does not cover.
- Anything touching the real ledger.
- Any change to the published contract that breaks existing clients. Additive changes (a new
  field, a new endpoint) are the agents' call.
- Anything outside this repo.

**Stay inside this repo.** Read and write nothing outside it without the owner's permission for
that occasion; your own Claude settings and memory are not outside. The tester's one exception
is running the practice engine: it recreates the practice user at the start of each check, uses
that fresh key for that check only, never writes it to a file, and stops only what it started.

**Asks from the client.** The client repo writes each thing it needs from the engine as a
standalone file (a title sentence, the date raised, **Why**, **The ask**, **Done when**, **What
the client removes once it lands**). The owner hands them over. Each one becomes a spec, or an
item in todo.md, here. The client learns the engine only from the live `/openapi.json`, so a
landed ask is finished when the contract states it.

### 3. The work files

#### docs/todo.md — how it is organised

The single home for open work that belongs to no spec, and for everything waiting on the owner.
No issue tracker, no `TODO:` comments in code. Only the orchestrator edits it; workers put
tasks and questions in their reports. **Closed items are deleted, not ticked**: git history is
the archive. Items are cited by their title.

It has three sections, in this order:

**1. Waiting on you.** Everything that needs the owner: questions, and things only the owner
can do. The orchestrator adds an entry instead of guessing, acts on the answer, then deletes
the entry. The section opens with the question format:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

Questions are written from the owner's point of view, without jargon, with 2–3 options. An
entry that is a job for the owner rather than a question (for example, "check these five things
by hand and report") uses a numbered list instead of options, and says when it is deleted.

**2. Backlog.** Open work that is not yet a spec. One bold-titled bullet each, saying what it
is and what it waits on. A big item links its own plan doc, which is deleted when the work
ships (its why moves to decisions.md). Tags: **[bug]**, and any tag this repo needs.

**3. Parked.** No commitment. Declined ideas stay listed, with the date they were declined, so
they are not proposed again.

A short header above the three sections says what the file is, who edits it, that closed items
are deleted, and what each tag means.

#### docs/specs/README.md

One spec per piece of work, written by the owner, saying what the work must achieve and how the
owner will know it is done, in plain language, not how to build it. The rules in "Specs and
tasks" above, and: work that belongs to no spec stays in todo.md; when a spec ships, its why
moves to decisions.md and the spec is deleted.

#### docs/decisions.md

Why the repo is the way it is, including rejected alternatives so nobody re-argues them. Only
decisions that govern current code live here; an undone decision is deleted. One home per fact
(link, don't copy); absolute dates; present tense. Entry template:
`## <decision> (<date>)` → **Context** / **Decision** / **Rejected** (short paragraphs; a
rejected alternative only if someone would plausibly propose it again). Its first entries record
this loop: one loop per repo with the main session as orchestrator, and review per task with
test and doc sweep once per spec.

### 4. AGENTS.md

A few lines at the repo root: everything an agent needs lives in CLAUDE.md, which is
tool-agnostic despite its name; this file exists so tools that look for `AGENTS.md` find it.
Then which docs to read next, and a pointer to CLAUDE.md "How work runs" for roles.

---

## Done when

- Every guard rule has a test that trips it, and the suite passes.
- A commit with a failing test is blocked; a builder cannot finish with a failing test.
- CLAUDE.md has the sections in part 2; todo.md, specs/README.md, decisions.md and AGENTS.md
  exist as described.
- Everything is committed and pushed to `main`.
- The owner has a short summary: what was built, and any questions in todo.md "Waiting on you".

## What the CLI removes once it lands

No client code. The client's open-work list drops its entry for copying the loop to the engine
repo; the idea of a read-only board over both repos' loops stays there, parked.
