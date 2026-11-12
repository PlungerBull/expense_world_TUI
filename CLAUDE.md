# expense_world_TUI — CLAUDE.md

> The interactive surface is the Textual TUI, opened by typing `expense`.

## What this repo is

The Hands: a Textual TUI that talks to the `expense_world_engine` over HTTPS. Zero business logic lives here. Two things are typed: `expense` (the TUI) and `expense import sheet` (spreadsheet door; [docs/decisions.md](docs/decisions.md) "The TUI is the only surface").

## Product scope and role

The **first of four clients** of the engine (engine → terminal → web → iOS), built to exercise it before web and iOS exist.

- **A contract validator.** Each screen tests its endpoints; [tests/contract/](tests/contract/) covers the rest. A wrong 422 hint, sign convention, replay or field lock should surface here, not on mobile.
- **No terminal-only shortcuts.** Engine logic re-implemented here is rejected; every pattern must carry over to the next client. Idempotency, the error envelope, the sign convention and date handling are shared infrastructure, used faithfully so web and iOS inherit working patterns.
- **Specific to this client:** [dates.py](expense/dates.py) (date forgiveness), [region.py](expense/region.py), [quickadd/](expense/quickadd/), [import_/](expense/import_/) and [bank_import/](expense/bank_import/) (both send files whole), and `~/.expense-config`.

Scale, distribution, multi-tenancy, billing, onboarding and localization land on web and iOS.

## Key documentation

- [docs/README.md](docs/README.md): the index of every doc, "Doc | Read it when". [docs/todo.md](docs/todo.md) holds **open work**; [docs/to-engine/](docs/to-engine/) is the **outbox**, [docs/from-engine/](docs/from-engine/) the **inbox**.
- The engine contract, live: `GET /openapi.json` on the practice engine (`http://127.0.0.1:8002/openapi.json`).

The contract is **read live, never copied**, and never learned from the engine's folder. A doc or code comment that leans on an engine rule cites it in one of four forms: `(contract: "Part")`, `(contract: "Section", "Part")`, `(contract: METHOD /v1/path)` or `(contract: METHOD /v1/path, "Part")`, the quoted name as written, without its closing punctuation, on one line in a doc. [test_contract_citations.py](tests/contract/test_contract_citations.py) says how each is looked up and fails on any the live contract does not hold; `test_docs_links.py` fails on any doc path into the engine's folder. **Each fact has one home**, and a doc changes only for what the code cannot say (the loop's "Docs").

**Docs must outlive any one contributor**, session or AI model: **(1) Fresh-clone test** — every doc works with no conversation history; rationale goes in decisions.md. **(2) A guard test only where it pays** — only when breaking the convention would write or show the owner something wrong, or mislead the next contributor; otherwise the doc states it. **(3) Absolute dates only.** **(4) Present tense** — what is and why, never how it got there, in docs and code comments. **(5) No provenance** — a doc says what the app does, never who picked it or which mockup drew it: no "as pane 10 draws it", "pick 2 B", "Question 6 B of …" or "(owner, 2026-10-21)". **(6) Point, don't restate** — a doc never retells what code, a test, a script or a hook says in its own docstring; it names the file. Every doc writer cuts as well as adds; the librarian's per-spec word report shows growth.

## Dev loop

- **Two branches.** Agents commit and push straight to `develop` (this overrides any "branch first" habit); to isolate a change, use a throwaway git worktree. `main` holds releases, and only the owner's `scripts/release.py`, run in the live folder, moves it or makes a tag.
- **Install:** `pip install -e ".[dev]" -c constraints.txt`; the entry point is `expense`.
- **Test:** `pytest tests/unit` — hermetic, respx-mocked, parallel (`-n0` for one process); the autouse fixtures in [conftest.py](tests/unit/conftest.py) redirect `EXPENSE_CONFIG` and block the network; never bypass them. `tests/contract/` hits the practice engine on **`:8002`** (`:8001` is another project's), gated on `PYTEST_LIVE=1`. After any engine change run `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002`. Details: [docs/runtime.md](docs/runtime.md) "Working against the live engine", "Fixture drift", "Contract version".
- **Lint/format/types:** `ruff check . && ruff format .` plus `mypy`, which checks all of `expense/`. CI (Python 3.11–3.13) runs ruff, mypy and `pytest tests/unit --cov`; pre-commit adds gitleaks.
- **Commit and push:** `PATH="$PWD/.venv/bin:$PATH" git commit -m "$(cat <<'EOF' … EOF)"` (pre-commit needs the project's mypy; a bare heredoc body is read as commands). Never `--no-verify`: it skips the secret scan. Push `develop` with the `PlungerBull` account (`gh auth switch --user PlungerBull`).
- **Careful running live:** a plain `expense` uses the real `~/.expense-config` and the live engine (`127.0.0.1:8000`), the one true ledger. Don't run writes ad hoc ([docs/runtime.md](docs/runtime.md) "Working against the live engine").
- **Guards:** [.claude/hooks/](.claude/hooks/) (wired by [settings.json](.claude/settings.json)) hold `guard.py`, which blocks what this file forbids that it can read from a command: the live engine and `~/.expense-config`, the drift script or contract suite against anything but `:8002`, paths outside the repo, keys reaching a file, force-push, history rewrites, new branches, the live folder, `scripts/release.py`, pushing `main` or a tag, skipped pre-commit checks, and a builder, reviewer or librarian running the whole unit suite by hand. Its docstring lists every rule; [test_claude_hooks.py](tests/unit/test_claude_hooks.py) trips each. `tests_gate.py` makes a `git commit` and a builder's finish wait for `pytest tests/unit`; `lint_edit.py` ruff-checks every `.py` edit. `settings.json` pre-approves only the loop's routine commands; `.claude/settings.local.json` stays empty.

## Tech stack

Python 3.11+ · Textual · Typer · httpx; `openpyxl` is dev-only. **No local cache, no offline write queue:** every read and write is a live engine call.

## Non-negotiable conventions

**Ask the engine to change — that is not a last resort.** Owner rule: *"DONT BE AFRAID OF ORDERING ENGINE TO CHANGE, its not a problem at all. Its better to get fully scalable and complete solutions over quick fixes or patches."* Propose the engine change; never ship a client-side workaround, and never count "no engine changes needed" in a design's favour: a missing capability gets reinvented, subtly wrong, in all four clients. Never edit the engine's repo: each ask is its own standalone file in [docs/to-engine/](docs/to-engine/), ending with what this client removes once it lands. It leaves once the owner hands it over; whatever waits on it names it by title.

**Thin wrapper.** Every screen reads from the engine, shows it, and sends back what the user types. No caching, no balance math, no validation beyond "is this input well-formed".

**Sign convention.** Input and output are both signed (`debit_as_negative`): negative = expense, positive = income.

**Idempotency on every write.** One UUID per logical write as `X-Idempotency-Key`; timed-out and 5xx writes retry (bounded) with the same key ([docs/runtime.md](docs/runtime.md)).

**Engine errors surface cleanly.** The engine's error shape is rendered to the user; never swallowed, never reformatted lossily.

**No new terms.** The app's words are the engine's and the owner's: "transaction", never "purchase"; a new user-facing term or screen name is asked first.

**Confirm destructive operations.** Deletes and reverts ask first, only `y` confirms, and the question says no screen can bring it back. Archive and unarchive are prompt-free toggles.

**Config isolation.** The token and engine URL live in `~/.expense-config` (chmod 600), the app's only local state, never checked in or shared across machines. The repo is **public**, so a committed secret stays in history for good: credentials and real ledger data never enter it.

**Mock every screen before building it — every time.** Before writing or changing any user-facing view (screen, list, form, report, message, or a table's columns), present its HTML mockup in [docs/mockups/](docs/mockups/) and wait, even for a screen approved before. **Showing a mockup is not approval:** never implement, even in auto-accept mode, until the owner explicitly picks one. An unspecified or ambiguous detail means stop and ask.

**One copy of everything shared.** Never duplicate fetch, format or write logic between screens or the sheet import; extend the shared helper: [reads.py](expense/reads.py) (engine reads), [formatting.py](expense/formatting.py), [number_format.py](expense/number_format.py), [currencies.py](expense/currencies.py) (an account's only currency), [jsonout.py](expense/jsonout.py) (`--json`), [bank_line_write.py](expense/bank_line_write.py) (the whole-line write), [bank_import/flow.py](expense/bank_import/flow.py); shared TUI plumbing and widgets: [docs/tui.md](docs/tui.md) §1. Nothing outside `expense/commands/` but [expense/__main__.py](expense/__main__.py) imports from it.

**Colour comes from the terminal.** No literal or authored colours in the TUI: all colour goes through theme tokens (`$accent`, `$secondary`, `$error` in CSS; `PALETTE` in Rich), which are ANSI slots, not hexes ([theme.py](expense/tui/theme.py), [docs/tui.md](docs/tui.md) §3). Themes recolor the foreground, never the base surface: its fill is `ansi_default` ([app.tcss](expense/tui/app.tcss)); a full-screen background breaks light/dark. `test_tui_theme.py` guards both.

**Testing conventions.** Test what the owner would notice, once. A new screen or write lands with unit tests for its happy path and each engine refusal that changes what the screen does (a refusal shown the shared way is proven once, by the shared code), driven through [helpers.py](tests/unit/helpers.py) against a fake engine (`FakeClient`, or respx for the real HTTP client); a new engine capability also gets a live contract test. No unit test re-states an engine rule: the engine and the live contract suite judge those. A behaviour proven in one test is not proven again in another, no new test's subject is other tests, and a missing test is a find only when it leaves something the owner would notice unproven. A pilot test waits on a condition (`wait_for`), never the clock; render tests go through `render_text`, never a bare `Console(...)`; an account comes from `account_with_currencies`, never a builder of a test's own. Mechanics: the docstrings of helpers.py and conftest.py. [test_command_surface.py](tests/unit/test_command_surface.py) pins the typed surface: bare `expense` opens the app, `import sheet` is the only command, with its `Example:` docstring and an error-shape test (it concludes only on a run of all of `tests/unit`).

## How work runs (the agent loop)

The loop shared by both expense_world repos (roles, specs and tasks, per task, per spec, docs, commits, what goes to the owner) is loaded from the file below; no agent here edits it. This section adds what is this repo's own, and wins where the two differ.

@../agent-loop.md

**This repo's loop.**
- **Files only the orchestrator edits:** [docs/todo.md](docs/todo.md), [docs/decisions.md](docs/decisions.md) and a spec's "Tasks" section. The builder and the librarian edit every other doc, but not docs/specs/.
- **Mockups travel with the approval.** The one approval message carries a mockup for each screen question, already drawn and opened. A task that still needs a screen mid-run does not stall the loop: draw the mockup, park the task, move on, and ask in the next stop's summary.
- **Backlog items instead of a spec:** the owner may name items from todo.md's Backlog; the loop runs each as a task, with one acceptance check and doc sweep at the end.
- **Each task leaves `pytest tests/unit` green.** After the second rejection a fresh builder takes over, unless every remaining point is a small fix named by file and line. If the builder needs the live contract, the orchestrator runs `scripts/practice-engine up` before the task and `scripts/practice-engine down` after; no tester is sent for that. One task at a time: one working branch means parallel builders would collide.
- **A finished spec ends with a release prepared:** `scripts/prepare_release.py X.Y.Z` on `develop`, committed and pushed on its own so CI runs on that commit; once CI passes it, the stop's summary names the version and the owner's command (`scripts/release.py`). Their docstrings say the rest.
- **The tester** reports a check no test proves as such, and may start the test engine ("Stay inside this repo"). **The acceptance check** runs against the practice engine (`:8002`): the drift script, the live contract suite ([docs/runtime.md](docs/runtime.md) "Working against the live engine"), each check in the spec's "How the owner knows it is done", and the app when a screen changed.
- **Engine hand-offs become catch-up specs:** the files in [docs/from-engine/](docs/from-engine/) are planned into one spec (or several independent ones) that takes what the live contract does not hold and ends with a reply in [docs/to-engine/](docs/to-engine/), from its "Reply to the engine" section and the tester's results; the hand-off files are then deleted ([docs/from-engine/README.md](docs/from-engine/README.md)).
- **A moved contract version goes to the owner.** When the version check reports a move, start no new task; file a "Waiting on you" question in todo.md with the check's printout and the version this client last caught up to, so the owner can ask for one hand-off file covering the gap. The new version is recorded (`--record-version`) only in the commit that acts on the owner's answer; until then the loop stays stopped ([docs/runtime.md](docs/runtime.md) "Contract version").

**Stay inside this repo.** Read and write nothing outside it unless the owner permits it for that occasion; your own Claude settings and memory are not outside, and `../agent-loop.md` reaches the session through the import above, never through a tool call. No agent reads any file in the engine's folder; the contract is the practice engine's `/openapi.json`. Any agent may run `scripts/practice-engine up` and `scripts/practice-engine down`: the script starts the engine's own launcher and reseed, prints the two practice users' keys to the terminal, never to a file, and stops only a practice engine on `:8002`. One exception:

- **The tester may run the test engine** on `:8002` with the engine's own launcher, reseeding the practice users at the start of each check as [docs/runtime.md](docs/runtime.md) "Working against the live engine" gives, and using those keys for that check only. It stops only the engine it started, by its pid, never reads or edits an engine file, never touches `:8000` or `~/.expense-config`, and never writes a key to a file. Each such check starts with the version check, `python scripts/check_fixture_drift.py --engine-url http://127.0.0.1:8002`, whose result goes in its report.

## Status

The TUI (`expense`) is the only surface and covers every engine feature the owner uses; `expense import sheet` brings in the owner's spreadsheet; engine features with no screen are exercised by the live contract suite. **Open work, known defects and questions for the owner live only in [docs/todo.md](docs/todo.md) and the current spec's "Tasks" section; engine asks not yet handed over in [docs/to-engine/](docs/to-engine/).**
