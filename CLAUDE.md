# expense_world_TUI — CLAUDE.md

> The interactive surface is the Textual TUI, opened by typing `expense`.

## What this repo is

The Hands. A Python terminal app (a Textual TUI) that talks to the `expense_world_engine` via its HTTPS API. Every screen reads and writes through engine endpoints. Zero business logic lives here — if the engine doesn't do it, the app can't either. Two things are typed: `expense`, which opens the TUI, and `expense import sheet`, the door for the owner's spreadsheet ([docs/decisions.md](docs/decisions.md) "The TUI is the only surface").

## Product scope and role

This app is **the first of four clients** sharing the same engine (engine → terminal app → web dashboard → iOS). It exists to exercise the engine through real human use before web and iOS are built.

- **The app is a contract validator.** Each screen is a real-world test of the endpoints it calls; the live contract suite ([tests/contract/](tests/contract/)) covers the rest, including engine features with no screen. A wrong 422 hint, sign convention, idempotency replay or field lock should surface here, not on mobile.
- **No terminal-only shortcuts.** Anything that only makes sense for this client (e.g. engine logic re-implemented here) is rejected; every pattern must carry over to the next client.
- **Idempotency, the error envelope, the sign convention and date handling are shared infrastructure**, used faithfully so web and iOS inherit working patterns.
- **What stays specific to this client:** [expense/dates.py](expense/dates.py) (date forgiveness), [expense/region.py](expense/region.py) (the machine's number format, followed until the account picks one), [expense/quickadd/](expense/quickadd/) (the LOG bar's one-line grammar), [expense/import_/](expense/import_/) (the sheet import) and [expense/bank_import/](expense/bank_import/) (the import door), both sending their file to the engine whole, and `~/.expense-config` (token storage).

Scale, distribution, multi-tenancy, billing, onboarding and localization land on web and iOS, not here.

## Key documentation

| Doc | Holds |
|---|---|
| [docs/commands.md](docs/commands.md) | The typed surface, the auth model, the error and `--json` formats |
| [docs/runtime.md](docs/runtime.md) | Read/write semantics, error handling, working against the live engine |
| [docs/tui.md](docs/tui.md) | The TUI: architecture, theming, keymap contract, test conventions |
| [docs/todo.md](docs/todo.md) | **The hub for open work:** work in no spec, and everything waiting on the owner. Open items only; closed work is deleted |
| [docs/specs/](docs/specs/) | The owner's specs, one per piece of work — what the loop builds |
| [docs/to-engine/](docs/to-engine/) | **Outbox:** engine asks and catch-up replies not yet handed over, one standalone file each; the owner copies them to the engine's `docs/from-tui/`. Format in its README |
| [docs/from-engine/](docs/from-engine/) | **Inbox:** one file per catch-up, written in the engine's `docs/to-tui/` and copied here by the owner; turned into catch-up specs, then deleted |
| [docs/decisions.md](docs/decisions.md) | Why the current calls were made, and what was rejected |
| [docs/mockups/](docs/mockups/) | HTML mockups — the approval gate for every screen and table |
| The engine contract | Every endpoint, rule and error code. Live: `GET /openapi.json` on the practice engine (`http://127.0.0.1:8002/openapi.json`) |

The engine contract is **read live, never copied**, and never learned from the engine's folder. A doc or code comment that leans on an engine rule cites the part of the live contract stating it, in one of four forms: `(contract: "Part")`, `(contract: "Section", "Part")`, `(contract: METHOD /v1/path)` or `(contract: METHOD /v1/path, "Part")`. A quoted name is a tag, a section or a rule's bold heading as written, without its closing punctuation; the path is bare; in a doc the citation sits on one line. [tests/contract/test_contract_citations.py](tests/contract/test_contract_citations.py) fails on any citation the live contract does not hold, and `test_docs_links.py` on any doc path into the engine's folder. Inside this repo too, **each fact has one home**; when you ship something, update the doc that owns it.

**Docs must outlive any one contributor**, session or AI model: **(1) Fresh-clone test** — every doc works with zero conversation history; rationale goes in decisions.md. **(2) A guard test only where it pays** — a convention gets a guard test (like [test_command_surface.py](tests/unit/test_command_surface.py) or [test_docs_links.py](tests/unit/test_docs_links.py)) only when breaking it would write or show the owner something wrong, or mislead the next contributor (a dead link, a wrong contract citation); otherwise the doc states it. **(3) Absolute dates only.** **(4) Present tense** — what is and why, never how it got there, in docs and code comments. **(5) No provenance** — a doc says what the app does, never who picked it or which mockup drew it: no "as pane 10 draws it", "pick 2 B", "Question 6 B of …" or "(owner, 2026-10-21)". **(6) Point, don't restate** — a doc never retells what code, a test, a script or a hook says in its own docstring; it names the file. Every role that writes a doc cuts as well as adds, and each doc has a word budget in `test_doc_hygiene.py`.

## Dev loop

- **Single branch — `main` only.** Commit and push straight to `main` (this overrides any "branch first" habit); to isolate a change, use a throwaway git worktree.
- **Install:** `pip install -e ".[dev]" -c constraints.txt` (it pins the direct deps CI installs); the entry point is `expense`.
- **Test:** `pytest tests/unit` — hermetic, respx-mocked, parallel by default (`-n0` for one process, e.g. with `--pdb`). An autouse fixture in [tests/unit/conftest.py](tests/unit/conftest.py) redirects `EXPENSE_CONFIG`; never bypass it. Render tests go through `helpers.render_text(...)`, never a bare `Console(...)`. `tests/contract/` hits a real engine, gated on `PYTEST_LIVE=1`, in one process, against the practice engine on **`:8002`** (not `:8001`, which is todo_world_engine's); command and variables: [docs/runtime.md](docs/runtime.md) "Working against the live engine". After any engine change run `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002` (runtime.md "Fixture drift" and "Contract version").
- **Lint/format/types:** `ruff check . && ruff format .` plus scoped `mypy` (its file list in `pyproject.toml`; widen it as modules get annotated). CI (Python 3.11–3.13) runs ruff, mypy and `pytest tests/unit --cov`; pre-commit runs gitleaks, ruff and mypy.
- **Commit and push:** `PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF' … EOF)"` (pre-commit needs the project's mypy; a bare heredoc body is read as commands). Never `--no-verify`: it skips the secret scan. Push with the `PlungerBull` account (`gh auth switch --user PlungerBull`).
- **Careful running live:** a plain `expense` uses the real `~/.expense-config` and the live engine (`127.0.0.1:8000`), the one true ledger. Don't run writes ad hoc ([docs/runtime.md](docs/runtime.md) "Working against the live engine").
- **Guards:** [.claude/settings.json](.claude/settings.json) wires [.claude/hooks/](.claude/hooks/) into every session and worker. `guard.py` blocks what this file forbids that it can read from a command (the live engine, `~/.expense-config`, `expense` without an `EXPENSE_CONFIG=` override, the drift script or contract suite against anything but `:8002`, paths outside the repo but `~/.claude`, the engine checkout and `scripts/practice-engine` in their exact shapes, keys reaching a file, stopping a process by hand (the tester's engine aside), force-push, history rewrites, new branches, skipped pre-commit checks, and a builder, reviewer or librarian running the whole unit suite by hand: a file, a node id, `-k` or `--lf --lfnf=none` pass); its docstring lists every rule and its limits, and [tests/unit/test_claude_hooks.py](tests/unit/test_claude_hooks.py) trips each one. `tests_gate.py` makes a `git commit` and a builder's finish wait for `pytest tests/unit`, skipping code it has already passed. Every `.py` edit is ruff-checked. A tripwire, not a sandbox. `settings.json` pre-approves only the loop's routine commands; `.claude/settings.local.json` stays empty.
- **Env vars:** `EXPENSE_CONFIG` (config path override), `PYTEST_LIVE=1` (contract tests; the rest in runtime.md).

## Tech stack

- Python 3.11+ · Textual (TUI) · Typer (typed entry point) · httpx.
- **Importers** send their file to the engine whole, so `openpyxl` is a dev dependency only, for tests that build made-up sheets.
- **Config:** `~/.expense-config` (chmod 600), the app's only local state.
- **No local cache, no offline write queue.** Every read and write is a live engine call: one source of truth, no conflicts, no staleness, and every client inherits the same `request → wait → done` contract.

## Non-negotiable conventions

**Ask the engine to change — that is not a last resort.** Owner rule: *"DONT BE AFRAID OF ORDERING ENGINE TO CHANGE, its not a problem at all. Its better to get fully scalable and complete solutions over quick fixes or patches."* When the complete solution needs an engine change, propose it; never ship a client-side workaround, and never count "no engine changes needed" in a design's favour, because a missing capability gets reinvented, subtly wrong, in all four clients. Never edit the engine's repo: each ask is its own standalone file in [docs/to-engine/](docs/to-engine/), ending with what this client removes once it lands. It leaves the folder once the owner hands it over; whatever waits on it names it by title.

**Thin wrapper.** Every screen reads from the engine, shows it, and sends back what the user types. No caching, no balance math, no validation beyond "is this input well-formed".

**Sign convention.** Input and output are both signed (`debit_as_negative`): negative = expense, positive = income.

**Idempotency on every write.** The HTTP client mints a UUID per logical write as `X-Idempotency-Key`; timed-out and 5xx writes retry (bounded) with the same key ([docs/runtime.md](docs/runtime.md)).

**Engine errors surface cleanly.** The engine's error shape is rendered to the user; never swallowed, never reformatted lossily.

**Confirm destructive operations.** Deletes and reverts ask first, only `y` confirms, and the question says no screen can bring it back. Archive and unarchive are prompt-free, reversible toggles.

**Config isolation.** The token and engine URL live in `~/.expense-config`, never checked in or shared across machines. The repo (`PlungerBull/expense_world_TUI`) is **public** (free CI minutes), so a committed secret stays in history for good: credentials and real ledger data never enter it.

**Mock every screen before building it — every time.** Before writing or changing any user-facing view (screen, list, form, report, message, or a table's columns), present its HTML mockup in [docs/mockups/](docs/mockups/) and wait, even for a screen approved before. **Showing a mockup is not approval:** never implement, even in auto-accept mode, until the owner explicitly picks one. An unspecified or ambiguous detail means stop and ask.

**One copy of everything shared.** Never duplicate fetch, format or write logic between screens, or between the TUI and the sheet import; extend the shared helper. Shared homes: engine reads in [expense/reads.py](expense/reads.py), formatters in [expense/formatting.py](expense/formatting.py), the number format in [expense/number_format.py](expense/number_format.py), an account's only currency in [expense/currencies.py](expense/currencies.py), `--json` output in [expense/jsonout.py](expense/jsonout.py), the whole-line write in [expense/bank_line_write.py](expense/bank_line_write.py), the bank-import steps in [expense/bank_import/flow.py](expense/bank_import/flow.py); the TUI's shared screen plumbing and widgets are listed in [docs/tui.md](docs/tui.md) §1. Nothing outside `expense/commands/` imports from it.

**No literal colors in the TUI — and no authored ones either.** All color goes through theme tokens (`$accent`, `$secondary`, `$error` in CSS; `PALETTE` in Rich), and the tokens are ANSI slots, not hexes, so the terminal supplies every colour ([theme.py](expense/tui/theme.py), `test_tui_theme.py`, [docs/tui.md](docs/tui.md) §3).

**Themes recolor the foreground, never the base surface.** The base fill is the terminal's own background (`ansi_default` in [app.tcss](expense/tui/app.tcss)); painting a full-screen background breaks light/dark (`test_base_fills_are_terminal_transparent`).

**Testing conventions.** Test what the owner would notice, once. A new screen or write lands with unit tests for its happy path and for each engine refusal that changes what the screen does (a refusal shown the shared way is proven once, by the shared code's tests), driven through [tests/unit/helpers.py](tests/unit/helpers.py) against a fake engine (`FakeClient`, or respx for the real HTTP client); a new engine capability also gets a live contract test. No unit test re-states an engine rule: the engine and the live contract suite judge those. A behaviour proven in one test is not proven again in another, no new test's subject is other tests, and a missing test is a find only when it leaves something the owner would notice unproven. [test_command_surface.py](tests/unit/test_command_surface.py) pins the typed surface: bare `expense` opens the app, `import sheet` is the only command, with its `Example:` docstring and an error-shape test (that guard concludes only on a run of all of `tests/unit`; see [tests/unit/conftest.py](tests/unit/conftest.py)).

## How work runs (the agent loop)

The owner is not a coder. Agents make every technical decision. The owner decides what users see (screens, flows, wording), money or business rules a spec does not cover, and anything touching real data.

**Roles.** The main session is **always the orchestrator**, including a plain chat with the owner. The four workers are defined once for every repo in `~/.claude/agents/` (their job, their report shape, what they never do); this file wins where they differ.

| Role | When | May touch |
|---|---|---|
| **Orchestrator** (main session) | Picks the next task, writes its "passes if…" criteria, delegates, commits and pushes, files questions and rationale. **Never writes code or tests.** | Docs and Claude config; the only role that edits [docs/todo.md](docs/todo.md), [docs/decisions.md](docs/decisions.md) and a spec's "Tasks" section |
| **Builder** | Every task | Code, tests and docs, except todo.md, decisions.md and docs/specs/ |
| **Reviewer** | Every task, after the builder | Read-only |
| **Tester** | Once per spec, after its last task; a check no test proves is reported as such | Runs things, edits nothing; may start the test engine ("Stay inside this repo") |
| **Librarian** | Once per spec, last. Here it also **cuts** restatements, provenance and history, and reports words lost or gained per doc | Docs, except todo.md, decisions.md and docs/specs/ |

**Specs and tasks.** The owner writes one spec per piece of work in [docs/specs/](docs/specs/). **One approval per spec:** the orchestrator brings everything a spec needs from the owner in one message: its open questions (2–3 options, a recommendation), a mockup for each screen question, already drawn and opened, and its tasks drafted on the recommended answers. One reply answers the questions and approves the spec and its tasks together; an answer other than the recommendation gets the affected tasks redrafted, with no second approval. **Approved specs wait in todo.md's "Queue"**, in order. The loop runs the queue top to bottom on its own, exactly each spec's tasks, and starts the next spec as soon as one is done; a spec waiting on the engine or the owner is skipped until it can run. Work found along the way is neither built nor raised mid-run: it goes in the spec's **Found along the way** section and is sorted at the end. Everything above "Tasks" is the owner's. Instead of a spec, the owner may name Backlog items from todo.md; the loop runs each as a task, with one acceptance check and doc sweep at the end.

**Task size.** One step a builder finishes in about 15 minutes (one screen, command or client call, with its tests and doc lines), each step leaving `pytest tests/unit` green. A spec of more than about 8 tasks is split in two. **Small work is merged, not given its own spec:** a spec of fewer than about 4 tasks joins a drafted or queued spec in the same area, or several small ones merge, up to that limit. Every spec pays the same fixed cost (the owner's approval, the acceptance check, the doc sweep), so fewer, fuller specs finish sooner.

**The brief points, it doesn't paste.** It names the spec part, the files, the doc sections and the reviewer checks that matter most; never "read the whole spec" or "read the whole doc".

**Per task:**
1. Take the next approved task and write its "passes if…" criteria. No clear criteria → a question for the owner first.
2. Builder implements → reviewer confirms each criterion → commit and push. A rejection goes back to the builder; **after the second, a fresh builder takes over** with the task, both reports and the files changed so far, unless every remaining point is a small fix named by file and line. Every task starts a fresh builder and reviewer. If the builder needs the live contract, the orchestrator runs `scripts/practice-engine up` before the task and `scripts/practice-engine down` after; no tester is sent for that.
3. After **4 failed rounds**, park the task, add a question for the owner, move on.
4. **Done** = reviewer approved + committed and pushed + deleted from its task list in that same commit.
5. **One task at a time** — the single branch means parallel builders would collide.
6. **Stop** only when the queue is empty or every remaining task in it waits on the owner or the engine. The summary covers every spec finished since the last stop and holds, in that one message, every question waiting and every drafted spec ready for its one approval.

**Per spec,** once all its tasks are done:
1. The tester runs the acceptance check against the practice engine (`:8002`): the drift script, the live contract suite ([docs/runtime.md](docs/runtime.md) "Working against the live engine"), each check in the spec's "How the owner knows it is done", and the app when a screen changed. Each failure becomes a new task; the loop runs it and the tester checks again.
2. The librarian sweeps every doc. The orchestrator gives decisions.md the same pass: the spec's new rationale goes in, whatever it made untrue comes out.
3. A catch-up spec ends with the orchestrator's reply in [docs/to-engine/](docs/to-engine/), from its "Reply to the engine" section and the tester's results.
4. "Found along the way" is sorted: what the owner would see, or a money or business rule, joins a drafted spec in the same area or becomes one, saved for the next stop's summary; the rest goes to todo.md's Backlog.
5. **Done** = acceptance check passed + sweep done + any reply written + finds sorted; the spec retires as [docs/specs/README.md](docs/specs/README.md) says.

**Engine hand-offs become catch-up specs:** the files in [docs/from-engine/](docs/from-engine/) are planned into one spec (or several independent ones) that takes what the live contract does not hold and ends with a reply; the hand-off files are then deleted ([docs/from-engine/README.md](docs/from-engine/README.md)).

**A moved contract version goes to the owner.** When the version check reports a move, start no new task; file a "Waiting on you" question in todo.md with the check's printout and the version this client last caught up to, so the owner can ask for one hand-off file covering the gap. The new version is recorded (`--record-version`) only in the commit that acts on the owner's answer; until then the loop stays stopped ([docs/runtime.md](docs/runtime.md) "Contract version").

Mockups are drawn when a spec is drafted, so their picks travel in its one approval. A task that still needs a screen mid-run does not stall the loop: draw the mockup, park the task, move on, and ask in the next stop's summary.

**What always goes to the owner — never guessed:** anything users see ("Mock every screen before building it"); money or business rules a spec does not cover (usually an engine ask); anything touching real data ("Careful running live"); anything outside this repo. Questions live in todo.md "Waiting on you": plain language, 2–3 options, a recommendation.

**Stay inside this repo.** Read and write nothing outside it unless the owner permits it for that occasion; your own Claude settings and memory are not outside. No agent reads any file in the engine's folder; the contract is the practice engine's `/openapi.json`. Any agent may run `scripts/practice-engine up` and `scripts/practice-engine down`: the script starts the engine's own launcher and reseed, prints the two practice users' keys to the terminal, never to a file, and stops only a practice engine on `:8002`. One exception:

- **The tester may run the test engine** on `:8002` with the engine's own launcher, reseeding the practice users at the start of each check as [docs/runtime.md](docs/runtime.md) "Working against the live engine" gives, and using those keys for that check only. It stops only the engine it started, by its pid, never reads or edits an engine file, never touches `:8000` or `~/.expense-config`, and never writes a key to a file. Each such check starts with the version check, `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002`, whose result goes in its report.

## Status

The TUI (`expense`) is the only surface and covers every engine feature the owner uses; `expense import sheet` brings in the owner's spreadsheet; engine features with no screen are exercised by the live contract suite. **Open work, known defects and questions for the owner live only in [docs/todo.md](docs/todo.md) and the current spec's "Tasks" section; engine asks not yet handed over in [docs/to-engine/](docs/to-engine/).**
