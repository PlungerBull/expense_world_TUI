# TODO — the workpad

**The hub for open work in this repo.** A spec's tasks live in that spec's "Tasks" section;
everything else open lives here, and nowhere else (no issue tracker, no `TODO:` comments). How
the work runs: CLAUDE.md "How work runs (the agent loop)".

Only the orchestrator edits this file; workers put tasks and questions in their reports. Closed
items get deleted, not ticked ([decisions.md](decisions.md) "The open-work list holds only open
work"). Cite items by title. **[UI]** means an HTML mockup in [mockups/](mockups/) must be
picked before any code. Engine asks live in [engine-asks/](engine-asks/), one file each.

---

## Waiting on you

Everything that needs the owner: questions, and things only the owner can do. The orchestrator
adds an entry instead of guessing, acts on the answer, then deletes the entry. After a round of
answers it tells the owner what each answer unlocked, and drafts a spec in [specs/](specs/) for
work that is now unblocked. A question reads:

```
### <title>
Asked <date> · Blocks: <task or spec>
<the question, in plain language>
- **A.** <option>
- **B.** <option>
**Recommended:** <letter>, because <why> — or "none", when it is a fact only the owner knows
```

### Review the three draft specs
Asked 2026-09-29 · Blocks: each spec's work
[tag-suggestions.md](specs/tag-suggestions.md), [official-migration.md](specs/official-migration.md)
and [tui-import-door.md](specs/tui-import-door.md) are first drafts. Each ends with its open
questions and draft tasks. Correct what is wrong, answer the questions, and name the one the loop
starts on.

### Catch up to engine contract 93a62b40ae9751d8 now?
Asked 2026-09-29 · Blocks: Catch up to engine contract 93a62b40ae9751d8
The engine coders changed the engine (list in the Backlog item of that name). Two of the changes
break the app: moving a transaction that sits in an open reconciliation to another account is now
refused, and some error hints stop showing because the engine reworded its messages.
- **A.** Make the catch-up the next spec, ahead of the three drafts above.
- **B.** Finish the current spec first, then catch up.

**Recommended:** A, because the app is out of step with the engine until this is done, and every
later spec would be built and checked against the new contract anyway.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Catch up to engine contract 93a62b40ae9751d8** (engine changes reported by the engine coders
  2026-09-29). Waits on the question above; the new version is recorded (`--record-version`)
  only in the commit that acts on the answer.
  1. **Moving an assigned transaction names its reconciliation** (breaking).
     `PUT /v1/transactions/{id}` changing `account_id` on a transaction assigned to a draft
     reconciliation, without `reconciliation_id`, returns `422` on `account_id` with reason
     `ASSIGNED_TO_RECONCILIATION` and changes nothing
     (contract: "Assigning transactions") (contract: PUT /v1/transactions/{id}).
     Every CLI/TUI path that moves a transaction between accounts also sends `reconciliation_id`:
     `null` to unassign, or a draft reconciliation on the new account. The reason gets a hint
     (e.g. "this transaction is in reconciliation X; unassign it or pick a draft on the new
     account"). Done when no command can send an account change on an assigned transaction
     without `reconciliation_id`.
  2. **Match on error reasons, not wording** (breaking). Every error carries `reasons`, keyed like
     `fields`, each value a published reason code; each operation lists its reasons under
     `x-error-reasons` (contract: "Error format") (contract: "Error reasons"). Switch on reasons in
     `reconcile_cmd.py` `_period_hint` (`RANGE_INVERTED`, `PERIOD_OVERLAPS`), `_complete_hint`
     (`NO_TRANSACTIONS_ASSIGNED`, `UNASSIGNED_IN_PERIOD`), `_is_field_locked_422` (`LOCKED`), and
     the lock/sealed hint in `transactions_cmd.py` (`LOCKED`, `SEALED_PERIOD`,
     `RECONCILIATION_COMPLETED`); then delete `error_haystack`. Also breaking: the sealed-period
     top-level message is no longer fixed (`SEALED_PERIOD` identifies it);
     `POST /v1/transactions/batch` reports an unknown hashtag under
     `transactions.<i>.hashtag_ids`, not bare `hashtag_ids`; `GET /v1/reports/monthly` field texts
     are full sentences; date/datetime format errors no longer start with "Value error, ". Done
     when the CLI reads error wording nowhere.
  3. **The engine checks the test-engine database itself** (additive). It refuses to start when
     `SUPABASE_DB_URL` and `ADMIN_DB_URL` name different databases or either names none. Drop the
     repo's own check that a test-engine start command sets both URLs; keep only the `:8002`
     rule. Done when that check is gone.
- **Tag suggestions that know the category.** Spec (draft): [specs/tag-suggestions.md](specs/tag-suggestions.md).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft): [specs/official-migration.md](specs/official-migration.md).
- **Import bank files from the TUI** (with the after-apply "may be logged twice" wording). Spec
  (draft): [specs/tui-import-door.md](specs/tui-import-door.md).
- **The TUI is the only surface** (flat commands deleted except the imports, three new TUI
  features, the repo rename and the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md),
  the current spec; its open questions live in the spec.
- **Shell completions** — zsh, bash, fish. `expense <TAB>` shows commands, `expense auth
  <TAB>` shows subcommands. No design questions open.

- **Human-name resolution for reference flags.** Accept a UUID or a name on every
  `--account-id` / `--category-id` / `--hashtag-id` / `--reconciliation-id`, via the existing
  list endpoints: case-insensitive exact match, ambiguous matches rejected with a "be more
  specific" error pointing at `expense <resource> list`; UUIDs pass through. Deserves its own
  plan-mode session. Decide deliberately whether it reuses the quick-add matcher
  (contains-anywhere over `load_quickadd_refs`, [quickadd/parse.py](../expense/quickadd/parse.py))
  or keeps a stricter exact match.

- **"Move between accounts" convenience** — one command writing the two ordinary
  `POST /transactions` a transfer consists of. Purely client-side sugar over two writes, which
  is also the argument against it. **[UI]** — needs a mockup covering naming, flags, and the
  two legs' default titles and categories. See [decisions.md](decisions.md) "Transfers are two
  ordinary transactions".

- **`expense import csv`** — only if a real migration needs it. Only a reader would be new; the
  write half is shared ([batch_write.py](../expense/batch_write.py)).

- **`PickerModal` carries rows but is still a modal.** A surface carrying rows should be a
  pushed screen (the bulk `c`/`b`/`h` picks). The other modals (`HelpModal`, `PromptModal`,
  `DiscardStagedModal`, `ConfirmModal`) are short questions and stay modals. **[UI]** — the
  replacement needs drawing.

---

## Parked

No commitment. Declined ideas stay listed so they are not proposed again.

- **A read-only board over every repo's loop**, at the `productivity_world` level, showing what
  each loop is doing and what waits on the owner. Worth it once more than two repos run a loop.
  Copying the loop itself to the engine is an open ask:
  [engine-asks/engine-agent-loop.md](engine-asks/engine-agent-loop.md).
- **The quick-add launcher hotkey.** A global chord that opens the LOG bar from outside the TUI
  ([mockups/quick-add-launcher-options.html](mockups/quick-add-launcher-options.html), which
  also records the ⌘E conflict). Convenience, not access: `+` and `expense log "<line>"` exist.
- **The quick-add "recents" row** (numbered last-N templates). **Declined 2026-08-25**; listed
  only so it is not re-proposed.
- **TUI live niceties.** Auto-refresh / watch mode, search-as-you-type, richer dashboards.
  Mouse stays **off** — see [tui.md](tui.md) §4.
- **Flat-CLI color conventions** beyond what ships. No demand established.
- **`auth pat create` / `auth pat revoke`.** PATs are issued out-of-band; a future web dashboard
  is expected to issue them. See [cli-spec.md](cli-spec.md) "Auth model".
