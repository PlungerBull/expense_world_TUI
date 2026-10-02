# The TUI is the only surface

**Paused** behind [tui-import-door.md](tui-import-door.md) (owner, 2026-10-02). Tasks are drafted into a "Tasks" section at the end once
the open questions below are answered. **When done:** the why moves to
[decisions.md](../decisions.md), and this file is deleted.

---

## The decision (owner, 2026-09-26, sharpened 2026-09-30)

**The owner only ever uses the TUI (`expense world`) and never types a flat command.** The flat
commands (`expense <group> <verb> --flag`) are deleted. Every feature is built once, in the TUI.

**Why.** The TUI never runs a command: both surfaces are faces on the same Python code (the
engine reads, the formatters, the write plumbing, [expense/http.py](../../expense/http.py)).
About 4,500 of the ~5,400 lines under `expense/commands/`, and about 310 unit tests, exist only
for the typed commands. Keeping them meant building and approving every feature twice for a
surface nobody reads.

**What stays true.** The engine is still the only home of business logic. Every engine endpoint
is still exercised before web and iOS exist: **the owner through the TUI, for real use**, and
**the automated tests**, most of all the live contract suite against the practice engine, which
already calls the engine directly and not through commands (10 of its 11 files). Neither the
iOS app nor the web dashboard will ever call this repo; both talk to the engine's HTTPS API
directly.

**What it replaces:** decisions.md "Dual-UX strategy — flat commands + TUI + quick-add
(2026-04-25)", which made flat commands canonical.

## What stays typed

- **`expense world`** — it is how the TUI opens.
- **`expense import sheet`** — stays for good (owner, 2026-09-30). It is the door for the
  owner's spreadsheet (PRESUPUESTO) and [official-migration.md](official-migration.md) runs on it.
- **`expense import bank`** — stays until the TUI import door ([tui-import-door.md](tui-import-door.md))
  ships, then it is deleted (owner, 2026-09-30). Until then it is the only way to bring bank
  files in.

Everything else typed goes, along with its tests, its human tables and [cli-spec.md](../cli-spec.md)
(except what still describes the two imports and the config file).

## What the TUI gains

Today these can only be done with a typed command. Each becomes a TUI feature, and each gets an
HTML mockup the owner picks before any code (owner, 2026-09-30):

1. **First-time setup.** Enter the engine address and key in the TUI on a fresh machine. Today
   the TUI can change them but cannot create the settings file, so it cannot start without
   `expense config set`.
2. **Delete.** Delete an account, a category, a hashtag, and a ledger transaction. Today the TUI
   can only archive them, and deletes a transaction only from a reconciliation's "no batch" list.
3. **Opening balance.** Set an account's starting balance.

## What is left with no screen

These engine features lose their only surface. The contract suite keeps exercising them:

- Activity history and exchange-rate history (already out of the TUI: decisions.md "Activity and
  Rates leave the TUI").
- Editing a reconciliation's details (name, dates, balances) after it is created.
- Updating the profile and the settings.
- The single-month report (the TUI's Home shows the four-month grid).
- Posting a JSON file of transactions (`transactions batch`), clearing the config file, and the
  engine ping.

Adding a screen for any of them later is new work of its own.

## Open questions for the owner

Each gets an answer before its step starts.

### When you ask an agent to do something with your data, what does it use?
Asked 2026-09-30
Changing the app's code needs no commands: agents write code and tests. But a request like "log
these ten receipts" or "how much did I spend on food in August?" acts on your ledger, and today
an agent would type `expense …` commands for that. (Agents only ever touch the real ledger when
you allow it for that occasion.)
- **A.** One small typed command, `expense api`, that sends any request straight to the engine
  (for example `expense api GET /reports/monthly` or `expense api POST /transactions
  --data …`) and prints the engine's raw answer. It reuses the app's own connection, so it gets
  the same key handling, retry safety and error messages. One command covers every engine
  feature, forever, with nothing to keep in sync.
- **B.** No typed commands. The agent writes a small one-off program for each request.
- **C.** Keep every current command, printing raw data only, for agents.

**Recommended:** A. It keeps agents able to act for you with tested, retry-safe plumbing, at a
fraction of the cost of C, and without the untested one-off programs of B.

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

- **Rules to rewrite:** CLAUDE.md "What this repo is", "Product scope and role", "Human default,
  JSON opt-in", "Confirm destructive operations" (it describes the TUI's confirm step, no longer
  `--yes`), "Mock every screen" (no more flat tables), "One copy of everything shared" and
  "Testing conventions" (the per-command guards go), "Status". [cli-runtime.md](../cli-runtime.md)
  becomes the runtime doc for the TUI and the imports.
- **Specs that shrink:** [tag-suggestions.md](tag-suggestions.md) drops its new flat command and
  the question about its columns. [tui-import-door.md](tui-import-door.md) leaves the typed
  `import bank` wording alone, since the command goes.
- **todo.md items that lose their reason:** Backlog "Shell completions", "Human-name resolution
  for reference flags", "Move between accounts convenience" (unless wanted as a TUI feature),
  "`expense import csv`", and Parked "Flat-CLI color conventions" and "`auth pat create/revoke`".
- **New work goes TUI-only.** A new engine capability gets its TUI screen and its contract test,
  and nothing typed.

## Steps

1. **Record the decision.** Add a decisions.md entry (Context / Decision / Rejected) that
   supersedes "Dual-UX strategy". Rewrite the rules listed above.
2. **Move the shared code** out of `expense/commands/` into a home not named after commands.
   Nothing the owner sees changes.
3. **Build the three TUI features** in "What the TUI gains", each after its mockup is picked.
   First-time setup comes before step 4, so the app can always start with no typed command.
4. **Delete the typed commands** that "What stays typed" does not keep, with their tests, guards
   and docs. The one contract test that walks through commands is rewritten to call the engine
   directly. The unit suite stays green at every commit.
5. **Clean todo.md.** Delete the items listed above.
6. **Rename the repo** (the new-name question): `gh repo rename` on GitHub (push access needs
   `gh auth switch --user PlungerBull`), update the local remote, rename the local folder if the
   owner wants that, and update the references in this repo. `test_docs_links.py` catches any
   broken relative link.
7. **Notify the engine coder.** The owner hands over the note below. This repo never edits the
   engine; the engine coder finds the references to the old name in the engine repo.
8. **Delete `expense import bank`** once the TUI import door ships.
9. **Delete this file**, and its row in todo.md.

## Draft note to the engine coder

> The terminal client (`PlungerBull/expense_CLI_menu`) is being renamed to **<new name>**.
> Please update every reference to the old name in the engine repo (its local-deployment guide,
> the practice-user seed script and its decisions log), plus any sibling-checkout paths.
>
> What else changed: the owner uses only the TUI (`expense world`), and the flat `expense …`
> commands are gone apart from the spreadsheet and bank imports. Nothing changes for the engine:
> the TUI calls the same endpoints and still exercises them through real use, and the contract
> suite exercises the rest. When the engine docs call "the CLI" the first client, they now mean
> the TUI.
