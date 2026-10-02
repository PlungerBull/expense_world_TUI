# expense_CLI_menu — CLAUDE.md

> The `_menu` suffix in the repo name is historical; the interactive surface is the Textual TUI (`expense world`).

## What this repo is

The Hands. A Python (Typer) CLI that talks to the `expense_world_engine` via its HTTPS API. Every command is a thin wrapper around one or more engine endpoints. Zero business logic lives here — if the engine doesn't do it, the CLI can't either.

## Product scope and role

This CLI is **the first of four clients** sharing the same engine (engine → CLI → web dashboard → iOS). The engine is the source of truth for every business rule; the CLI exists to exercise every engine endpoint through real human use before web/iOS development begins.

- **The CLI is a contract validator.** Each command is a real-world test of an engine endpoint. If a 422 hint, sign convention, idempotency replay, or field-locking semantic is wrong, we want to find out here, not via mobile users.
- **No CLI-only shortcuts.** Anything that would only make sense for a CLI user (e.g. re-implementing engine logic client-side) is rejected. The pattern has to generalize to the next client.
- **Idempotency, error envelope, sign convention, date handling are shared infrastructure** (RFC 3339, signed amounts, structured error envelope) — used faithfully so iOS and web inherit working patterns.
- **What stays CLI-specific:** [expense/dates.py](expense/dates.py) (date forgiveness), [expense/quickadd/](expense/quickadd/) (the one-line quick-add grammar, shared by both surfaces), [expense/import_/](expense/import_/) and [expense/bank_import/](expense/bank_import/) (the `.xlsx` readers), `~/.expense-config` (token storage).

Scale, distribution, multi-tenancy, billing, onboarding, localization are not this repo's concern — they land on web/iOS.

## Key documentation

| Doc | What it contains | Location |
|---|---|---|
| [docs/cli-spec.md](docs/cli-spec.md) | Command groups, output conventions | Local |
| [docs/cli-runtime.md](docs/cli-runtime.md) | Runtime behavior — read/write semantics, error handling, working against the live engine | Local |
| [docs/tui.md](docs/tui.md) | Textual TUI (`expense world`) — architecture, theming, keymap contract, test conventions | Local |
| [docs/todo.md](docs/todo.md) | The **hub for open work**: work that belongs to no spec, and everything waiting on the owner. Open items only; closed work is deleted, git history is the archive | Local |
| [docs/specs/](docs/specs/) | The owner's specs, one per piece of work — what the loop builds | Local |
| [docs/engine-asks/](docs/engine-asks/) | Every open engine ask, one standalone file each, handed as is to the engine coders; format in its README | Local |
| [docs/cli-answers/](docs/cli-answers/) | The engine coders' drop box: one file per engine change this client must catch up with, written by them; read it as input when planning catch-up work | Local |
| [docs/decisions.md](docs/decisions.md) | Why the current big calls were made, including rejected alternatives | Local |
| [docs/mockups/](docs/mockups/) | HTML mockups — the approval gate for every screen and table | Local |
| The engine contract | Every endpoint, every business rule, every error code — the API contract (sections in `info.description`, rules per tag and per operation) | Live: `GET /openapi.json` on the practice engine (`http://127.0.0.1:8002/openapi.json`) |

The engine contract is **read live, never copied**, and never learned from the engine's folder. A doc or code comment that leans on an engine rule cites the part of the live contract stating it — `(contract: "Part")`, `(contract: "Section", "Part")`, `(contract: METHOD /v1/path)` or `(contract: METHOD /v1/path, "Part")`, where a quoted name is a section or a rule's bold heading copied as written without its closing colon or full stop, the path is bare (no code span), and in a doc the whole citation sits on one line — never an engine file; `test_docs_links.py` fails on a doc path into the engine's folder. Inside this repo too, **each fact has one home** — commands in cli-spec, the TUI in tui.md, open work in todo.md (a spec's tasks in that spec, engine asks in engine-asks/), rationale in decisions.md. When you ship something, update the owning doc.

Docs must outlive any one contributor, session, or AI model: **(1) fresh-clone test** — every doc must work with zero conversation history; write needed context down (rationale goes in [docs/decisions.md](docs/decisions.md)). **(2) Executable beats prose** — when a convention can be checked mechanically, add a guard test next to the existing ones ([tests/unit/test_command_surface.py](tests/unit/test_command_surface.py), [tests/unit/test_tui_theme.py](tests/unit/test_tui_theme.py), [tests/unit/test_docs_links.py](tests/unit/test_docs_links.py)). **(3) Absolute dates only** — never "recently" or "last week". **(4) Present tense** — state what is and why; no history of how it got there, in docs or code comments.

## Dev loop

- **Single branch — `main` only.** Commit and push straight to `main` (this overrides any default "branch first" habit). CI runs on push to `main`; to isolate a change, use a throwaway git worktree, not a branch.
- **Install:** `pip install -e ".[dev]" -c constraints.txt` — entry point is `expense` (TUI via `expense world`). `constraints.txt` pins the direct deps CI installs.
- **Test:** `pytest tests/unit` (fast, respx-mocked, hermetic — an autouse fixture in [tests/unit/conftest.py](tests/unit/conftest.py) redirects `EXPENSE_CONFIG`; never bypass it). `tests/contract/` hits a **real engine**, gated on `PYTEST_LIVE=1` (+ `EXPENSE_PAT`); it refuses to run against the real ledger and expects the disposable `expense_world_test` engine on **`:8002`** — *not* `:8001`, which is todo_world_engine's (setup and the full command: [docs/cli-runtime.md](docs/cli-runtime.md) "Working against the live engine"). Unit tests mock the engine, so run `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002` after any engine change (diffs fixture keys against the engine's `openapi.json` and checks the saved contract version — [docs/cli-runtime.md](docs/cli-runtime.md) "Contract version"). Render tests go through `helpers.render_text(renderable, width=..., ansi=...)`, never a bare `Console(...)` (guarded by `test_suite_hygiene.py`).
- **Lint/format/types:** `ruff check . && ruff format .` plus scoped `mypy` (`[tool.mypy]` covers `http.py`/`config.py`/`errors.py` — widen as modules get annotated). CI (3.11/3.12/3.13) enforces ruff, mypy and `pytest tests/unit --cov`; pre-commit runs gitleaks + ruff + mypy. Line length 100, target py311.
- **Commit and push:** commit with `PATH="$PWD/.venv/bin:$PATH" git commit` so pre-commit finds the project's mypy; never `--no-verify` (it skips the gitleaks secret scan). Pushing needs the `PlungerBull` GitHub account (`gh auth switch --user PlungerBull`).
- **Careful running live:** plain `expense …` commands use the real `~/.expense-config` and hit the live local engine (`127.0.0.1:8000`) — the one true ledger. Don't run writes ad hoc. Ops guide: [docs/cli-runtime.md](docs/cli-runtime.md) "Working against the live engine".
- **Guards (hooks):** [.claude/settings.json](.claude/settings.json) wires the scripts in [.claude/hooks/](.claude/hooks/) into every session and worker. They block the live engine (`:8000`), the drift script run without an explicit `--engine-url …:8002`, the contract suite run without a `:8002` target, `expense` without an `EXPENSE_CONFIG=` override, `~/.expense-config`, paths in the home folder outside this repo (except `~/.claude`; paths outside the home folder, such as the harness scratchpad, pass), any read or write in the engine checkout beyond the tester's start, reseed and stop of the test engine, the reseed's key reaching a file, stopping processes (only the tester, only by `kill <pid>` or `lsof -ti :8002 | xargs kill`), force-push, history rewrites, new branches and skipped pre-commit checks. A `git commit` and a builder's finish both wait for `pytest tests/unit` to pass; every `.py` edit in the repo is ruff-checked and problems are reported back (not blocked). They are a tripwire, not a sandbox: each script's docstring states its limits, and [tests/unit/test_claude_hooks.py](tests/unit/test_claude_hooks.py) trips every rule. Write commit messages as `-m "$(cat <<'EOF' … EOF)"` — a bare heredoc body is read as commands. The same file pre-approves only the loop's routine commands (unit tests, ruff, mypy, read-only git, `git add`, the `PATH=… git commit` form, `git push` to `main`); `.claude/settings.local.json` is per-machine and stays empty.
- **Env vars:** `EXPENSE_CONFIG` (config path override), `PYTEST_LIVE=1` (contract tests; the suite's other variables are in [docs/cli-runtime.md](docs/cli-runtime.md) "Working against the live engine").

## Tech stack

- **Language:** Python 3.11+ · **CLI:** Typer · **TUI:** Textual · **HTTP:** httpx
- **Importers:** `expense import sheet` ([expense/import_/](expense/import_/)) and `expense import bank` ([expense/bank_import/](expense/bank_import/)); `.xlsx` via `openpyxl`, optional extra `[import]`
- **Config storage:** `~/.expense-config` (chmod 600) — the CLI's only local state
- **No local cache, no offline write queue.** Every read and write is a live call against the engine: one source of truth means no conflict resolution and no staleness, and every client inherits the same `request → wait → done` contract.

## Non-negotiable conventions

**Ask the engine to change — that is not a last resort**
Owner rule: *"DONT BE AFRAID OF ORDERING ENGINE TO CHANGE, its not a problem at all. Its better to get fully scalable and complete solutions over quick fixes or patches."* When the complete solution needs an engine change, **propose it.** Never quietly ship a client-side workaround, and never count "no engine changes needed" as a point in a design's favour. A capability the engine lacks gets reinvented in all four clients, usually subtly wrong (extra round trips, races, no pagination, a drifting copy of an engine rule). Never edit the engine's repo — write the ask up for the owner to hand to the engine coder. **Each ask is its own file** in [docs/engine-asks/](docs/engine-asks/), standing on its own so the owner can give it to the engine coders as is, and ending with what the CLI deletes once it lands. The folder is the list of open asks.

**Thin wrapper**
Every command parses args → calls an engine endpoint → formats output. No caching, no balance math, no validation beyond "do these flags make sense together." When logic is needed and the engine lacks it, the answer is an engine ask, never logic smuggled in here.

**Sign convention**
Input and output are both signed (`debit_as_negative`): negative = expense, positive = income.

**Human default, JSON opt-in**
Every read command supports `--json`; `--json` is always the raw engine response, passed through verbatim.

**Idempotency on every write**
The HTTP client mints a UUID per logical write and sets `X-Idempotency-Key`; timed-out/5xx writes auto-retry (bounded) with the **same** key, so a retry must never double-apply. Details in [docs/cli-runtime.md](docs/cli-runtime.md).

**Engine errors surface cleanly**
The engine's error shape (`{ error: { code, message, fields } }`) is rendered to the user. Never swallow, never reformat lossily.

**Confirm destructive operations**
Deletes and reverts prompt for confirmation unless `--yes` is passed; a delete is final from every client. Archive and unarchive are prompt-free — reversible toggles, not destruction.

**Config isolation**
Auth token + engine URL live in `~/.expense-config`. Never checked in, never shared across machines. The GitHub repo (`PlungerBull/expense_CLI_menu`) is **public** by deliberate choice, so any committed secret is public and permanent in git history; credentials must never enter the repo.

**Mock every screen before building it — every time**
Before writing or changing UI code for any user-facing view — menu, dashboard, list, form, report, TUI screen — first present its **HTML mockup in [docs/mockups/](docs/mockups/)** and wait for the user's review, **every time, even for a screen approved before** (the user re-reads the mockup each session). **Showing mockups is not approval:** never implement (even in auto-accept mode) until the user explicitly picks one. This includes CLI tables: a new `<resource> list` renderer or column change needs a proposed column set + sign-off first ([docs/cli-spec.md](docs/cli-spec.md)). When a detail is unspecified or ambiguous, **stop and ask** — the orchestrator asks the owner; a worker stops and puts the question in its report ("How work runs" below).

**One copy of everything shared**
Never duplicate fetch/format/write logic between CLI and TUI; extend the shared helper instead. The TUI imports `fetch_*` and formatters from `expense/commands/*`. Shared homes: read/format helpers in [expense/commands/_resource.py](expense/commands/_resource.py), `--json` serialisation in [expense/jsonout.py](expense/jsonout.py), TUI write plumbing in [expense/tui/screens/_base.py](expense/tui/screens/_base.py), list arithmetic in [expense/tui/widgets/windowed.py](expense/tui/widgets/windowed.py), cursor-grown list reads in [expense/tui/screens/_growing.py](expense/tui/screens/_growing.py), the quick-add suggestion list in [expense/tui/widgets/picker.py](expense/tui/widgets/picker.py), form scaffolding in [expense/tui/screens/_form.py](expense/tui/screens/_form.py).

**No literal colors in the TUI — and no authored ones either**
All TUI color goes through theme tokens — CSS uses `$accent`/`$secondary`/`$error`; Rich content takes the `PALETTE` constant ([theme.py](expense/tui/theme.py)). The tokens themselves are **ANSI slots**, not hexes, so the terminal supplies every colour and the app reads on light and dark terminals alike. Guarded by `test_tui_theme.py` (incl. `test_theme_is_ansi_slots_not_hexes`); see [docs/tui.md](docs/tui.md) §3.

**Themes recolor the foreground, never the base surface**
The base fill is the terminal's own background (`ansi_default`, set in [expense/tui/app.tcss](expense/tui/app.tcss)). A theme changes foreground and semantic-span colors only; painting a full-screen background brings back the terminal seam and breaks light/dark. Guard: `test_base_fills_are_terminal_transparent`; see [docs/tui.md](docs/tui.md) §3.

**Testing conventions**
Every new command lands with at least one happy-path + one error-shape unit test (`test_command_surface.py::test_every_command_has_an_error_shape_test` enforces the second half; a parametrized test counts). The CRUD shape every resource shares lives once, in [tests/unit/test_resource_crud_contract.py](tests/unit/test_resource_crud_contract.py); a per-resource file holds only what is that resource's own. [tests/unit/test_command_surface.py](tests/unit/test_command_surface.py) requires every command to have a docstring with an `Example:` block, `--json` on reads, `--yes` on destructive writes.

## How work runs (the agent loop)

The owner is not a coder. Agents make every technical decision. The owner decides what users see (screens, flows, wording), money or business rules a spec does not cover, and anything touching real data.

**Roles.** The main session is **always the orchestrator**, including a plain chat with the owner. Builder, tester, reviewer and librarian are **workers** it delegates to.

| Role | Does | May touch |
|---|---|---|
| **Orchestrator** (main session) | Picks the next task, writes its "passes if…" criteria, delegates, reads the reports, commits and pushes, files questions and rationale. **Never writes code or tests.** | Docs and Claude config; the only role that edits [docs/todo.md](docs/todo.md), [docs/decisions.md](docs/decisions.md) and a spec's "Tasks" section |
| **Builder** | Implements one task under this file's rules, and updates the doc that owns what it changed (cli-spec, tui.md, README, …) | Code, tests and docs of this repo, except todo.md, decisions.md and docs/specs/ |
| **Tester** | Runs once per spec, after its last task: the acceptance check ("Per spec" below), pass/fail per check with evidence. A check no test proves is reported as such; the builder writes that test. Also starts and stops the practice engine whenever a task needs it | Runs things; edits nothing. May start the test engine ("Stay inside this repo" below) |
| **Reviewer** | Runs on every task: reads the change for correctness, quality, security and this file's conventions, and confirms each "passes if…" criterion with evidence; doc structure is the librarian's | Read-only |
| **Librarian** | Runs once per spec, last: one sweep of every doc. Keeps the docs aligned: each fact in one home with the others linking to it ("Key documentation" above), no two docs disagreeing, docs matching the code, links resolving, the doc rules above kept. Where it can't tell which conflicting doc is right, it asks instead of picking | Docs of this repo, except todo.md, decisions.md and docs/specs/ |

The workers are defined once for every repo in `~/.claude/agents/` (`builder`, `tester`, `reviewer`, `librarian`) and take this repo's rules from this file.

**If you are a worker,** you have no owner to ask and you are not the orchestrator. When something is unclear, a rationale belongs in decisions.md, or a choice belongs to the owner, stop and put it in your report; the orchestrator files it. Every worker reports in one shape: **verdict · what was checked · what is wrong · where**.

**Specs and tasks.** The owner writes one spec per piece of work in [docs/specs/](docs/specs/) and names the current one when starting the loop. The orchestrator drafts that spec's tasks into the spec's own "Tasks" section, the owner approves them, and then the loop runs on its own. It works only on the current spec. Everything above "Tasks" is the owner's; agents change it only when the owner asks. Work that belongs to no spec stays in todo.md.

**Per task:**
1. Take the next approved task and write its "passes if…" criteria. No clear criteria → a question for the owner first.
2. Builder implements → reviewer reads the change and confirms each "passes if…" criterion → commit and push (the commit hook runs `pytest tests/unit`). A rejection goes back to the builder with that report. When the builder needs the contract live, the tester starts the practice engine before the task and stops it after.
3. After **4 failed rounds**, park the task, add a question for the owner, and move on.
4. **Done** = reviewer approved + committed and pushed + deleted from its task list (the spec's "Tasks" section, or todo.md) in that same commit.
5. **One task at a time** — the single branch means parallel builders would collide.
6. When every remaining task waits on the owner, **stop** and give the owner a short summary: what finished and which questions wait. The owner answers and restarts the loop.

**Per spec,** once all its tasks are done:
1. The tester runs the acceptance check against the practice engine (`:8002`): the drift script (version check and fixture check — "Stay inside this repo" below), the live contract suite (`tests/contract`, with the practice key and target as [docs/cli-runtime.md](docs/cli-runtime.md) "Working against the live engine" gives the command), each check in the spec's "How the owner knows it is done", and the app when the spec changed a screen. Each failure becomes a new task in the spec, added by the orchestrator; the per-task loop runs it, then the tester checks again.
2. The librarian sweeps every doc.
3. **Done** = the tester's acceptance check passed + the librarian's sweep done. The spec then retires as [docs/specs/README.md](docs/specs/README.md) says.

**A moved contract version goes to the owner.** When the tester's version check reports a moved version, the orchestrator starts no new task and files a question in todo.md "Waiting on you" listing what changed exactly as the check prints it ([docs/cli-runtime.md](docs/cli-runtime.md) "Contract version"). The owner decides whether catching up becomes the next spec. The new version is recorded (`--record-version`) only in the commit that acts on the owner's answer, whatever the answer is; until then the check keeps failing and the loop stays stopped.

A task that needs a screen does not stall the loop: draw the mockup, park the task, add a question asking the owner to pick, and move on.

**What always goes to the owner — never guessed:**
- Anything users see — "Mock every screen before building it" above.
- Money or business rules a spec does not cover. In this repo these usually become an engine ask ("Ask the engine to change" above).
- Anything touching real data — the live engine and `~/.expense-config` ("Careful running live" above).
- Anything outside this repo.

**Questions for the owner** live in todo.md "Waiting on you", in the format given there: plain language, 2–3 options, a recommendation.

**Stay inside this repo.** Read and write nothing outside it unless the owner permits it for that occasion. Not outside: your own Claude settings and memory. No agent reads any file in the engine's folder; the contract is the practice engine's `/openapi.json`. One exception:

- **The tester may run the test engine.** It starts the engine on `:8002` from `../expense_world_engine` over the disposable `expense_world_test` database, recreates the practice user with `deploy/local/seed-test-user.sh --force` at the start of each check, and uses that fresh key for that check only — exactly as [docs/cli-runtime.md](docs/cli-runtime.md) "Working against the live engine" describes. It stops only the engine it started, never reads or edits an engine file, never touches `:8000` or `~/.expense-config`, and never writes the key to a file. At the start of every check that uses the practice engine it runs the version check, `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002` ([docs/cli-runtime.md](docs/cli-runtime.md) "Contract version"), and puts its result in its report.

## Status

Both surfaces are complete: the flat CLI wraps every engine endpoint that has a CLI surface (and is the canonical contract-validator surface), and the TUI `expense world` — the owner's day-to-day surface — covers the same ground on the same fetch/write layer. What exists: [docs/cli-spec.md](docs/cli-spec.md) (commands), [docs/tui.md](docs/tui.md) (TUI), [docs/cli-runtime.md](docs/cli-runtime.md) (runtime); why: [docs/decisions.md](docs/decisions.md). **Open work, known defects and questions for the owner live only in [docs/todo.md](docs/todo.md) and the current spec's "Tasks" section; open engine asks in [docs/engine-asks/](docs/engine-asks/).**
