# The TUI is the only surface

The current spec. **When done:** the why
moves to [decisions.md](../decisions.md), and this file is deleted.

---

## The decision

**The owner only ever uses the TUI and never types a flat command.** The flat
commands (`expense <group> <verb> --flag`) are deleted. Every feature is built once, in the TUI.

**Why.** The TUI never runs a command: both surfaces are faces on the same Python code (the
engine reads, the formatters, the write plumbing, [expense/http.py](../../expense/http.py)).
About 4,500 of the ~5,400 lines under `expense/commands/`, and about 310 unit tests, exist only
for the typed commands. Keeping them means building and approving every feature twice for a
surface nobody reads.

**What stays true.** The engine is still the only home of business logic. Every engine endpoint
is still exercised before web and iOS exist: **the owner through the TUI, for real use**, and
**the automated tests**, most of all the live contract suite against the practice engine, which
calls the engine directly. Neither the iOS app nor the web dashboard will ever call this repo;
both talk to the engine's HTTPS API directly.

## What stays typed

- **`expense`**, alone — it opens the TUI. Today that is `expense world`; the word `world` goes.
- **`expense import sheet`** — the door for the owner's spreadsheet (PRESUPUESTO);
  [official-migration.md](official-migration.md) runs on it.

Everything else typed goes, `expense import bank` included (the TUI import door brings bank
files in), along with its tests, its human tables and [cli-spec.md](../cli-spec.md) (except what
still describes the sheet import and the config file).

**Agents get no typed commands.** Everything done to the ledger is done by the owner, in the
app. Agents build the app with code and tests, which needs no command.

## What the TUI gains

Today these can only be done with a typed command. Each becomes a TUI feature, and each gets an
HTML mockup the owner picks before any code:

1. **First-time setup.** Enter the engine address and key in the TUI on a fresh machine. Today
   the TUI can change them but cannot create the settings file, so it cannot start without
   `expense config set`.
2. **Delete.** Delete an account, a category, a hashtag, and a ledger transaction. Today the TUI
   can only archive them, and deletes a transaction only from a reconciliation's "no batch" list.
3. **Opening balance.** Set an account's starting balance.

## What is left with no screen

These engine features have no surface in this client. They are the engine's own to keep working,
and the contract suite keeps exercising them, until the owner decides one is needed in the TUI:

1. Activity history.
2. Exchange-rate history.
3. Editing a reconciliation's details (name, dates, balances) after it is created.
4. Updating the profile and the settings.
5. The single-month report (the TUI's Home shows the four-month grid).
6. Posting a JSON file of transactions (`transactions batch`), clearing the config file, and the
   engine ping.

Adding a screen for any of them later is new work of its own.

## The rename

The repo is named `expense_world_TUI` in both places: on GitHub (renamed
2026-10-14) and as the local folder (today `expense_world_CLI`). The same
repo is renamed, not replaced, so its history and its CI carry over. The command is still
`expense`.

- **GitHub** forwards the old address to the new one, so old links keep working.
- **The local folder** takes three things with it: the `.venv` is rebuilt (it stores the old
  path), Claude's memory and session history for this project are moved to the new path, and
  the engine repo's mentions of the old folder are updated by the engine coders (the brief
  below).

## The brief to the engine coders

One standalone `.md` in [engine-asks/](../engine-asks/), written last, which the owner hands
over as is. It says:

- The terminal client is named `expense_world_TUI`, on GitHub and as the sibling folder; every
  mention of the old names in the engine repo is updated.
- The owner uses only the TUI. The flat `expense …` commands are gone apart from the spreadsheet
  import. The TUI calls the same endpoints, so nothing changes in the contract. Where the engine
  docs call "the CLI" the first client, they mean the TUI.
- The six features in "What is left with no screen" have no client surface. They are the
  engine's domain: real use no longer exercises them, only the contract suite does.

## How the owner knows it is done

1. With no settings file (a fresh machine, or the app pointed at an empty location with
   `EXPENSE_CONFIG`), `expense` opens the app, asks for the engine address and
   the key, and then works. No typed command is needed first.
2. In the app, an account, a category, a hashtag and a transaction can each be deleted, and each
   asks before it deletes.
3. In the app, an account's opening balance can be set.
4. A bank file is imported from the app.
5. `expense` alone opens the app, `expense world` no longer exists, and `expense --help` lists
   `import sheet` and nothing else.
6. The repo is `PlungerBull/expense_world_TUI` on GitHub, the old GitHub address lands on it,
   and the local folder is `expense_world_TUI`.
7. [engine-asks/](../engine-asks/) holds the brief, and it lists the six features with no screen.
8. Every automated check passes: the unit tests, and the live suite against the practice engine.

## Consequences that follow directly

- **Rules to rewrite:** CLAUDE.md "What this repo is", "Product scope and role", "Human default,
  JSON opt-in", "Confirm destructive operations" (it describes the TUI's confirm step, no longer
  `--yes`), "Mock every screen" (no more flat tables), "One copy of everything shared" and
  "Testing conventions" (the per-command guards go), "Status". [cli-runtime.md](../cli-runtime.md)
  becomes the runtime doc for the TUI and the sheet import.
- **todo.md items that lose their reason:** Backlog "Shell completions", "Human-name resolution
  for reference flags", "`expense import csv`", and Parked "Flat-CLI color conventions" and
  "`auth pat create/revoke`".
- **New work goes TUI-only.** A new engine capability gets its TUI screen and its contract test,
  and nothing typed.

## Tasks

Approved by the owner on 2026-10-13; the catch-up tasks added from the owner's answers on
2026-10-14. **[UI]** tasks start with a mockup the owner picks.

1. **Fix the acceptance check's small failures** (tester, 2026-10-15). The drift check flags four
   test-local keys (`own`, `other`, `none`, `refused`, tests/unit/test_cmd_import.py:386-389);
   they go into `KNOWN_LOCAL`, and the contract version `42d70a629215928d` is recorded, since the
   owner chose (2026-10-15) to catch up with it in its own spec,
   [engine-catch-up-42d70a6.md](engine-catch-up-42d70a6.md), which also owns the eight live tests
   that fail on `ENDING_BALANCE_REQUIRED`. `expense import sheet` reads its settings file twice,
   so the pipe form [cli-runtime.md](../cli-runtime.md) gives fails; it reads the file once. The
   brief names exchange-rate history `GET /v1/exchange-rates`; the route is
   `GET /v1/exchange-rates/history`.
2. **Rename the local folder** to `expense_world_TUI`: rebuild the `.venv`, move Claude's memory
   and session history to the new path, update the mentions of the folder in this repo. It
   reaches outside the repo, so it runs when the owner says so, in a session of its own.
