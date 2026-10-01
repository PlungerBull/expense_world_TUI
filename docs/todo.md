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

### Record engine contract 84321bd839912a09?
Asked 2026-10-01 · Blocks: Catch up to engine contract 84321bd839912a09, task 1
The engine's contract moved from `5f65d4448df149d4` to `84321bd839912a09`. The version check
prints, newest first:

```
84321bd839912a09  2026-09-30
  changed: wording only, *Client-supplied UUIDs*: names `POST /transactions/import` as the one exception to the `409` on a taken `id` — a row it would create whose `id` is already one of your transactions is `422` (`ID_EXISTS`), as its own section states.
b56ee45232ac44e0  2026-09-30
  changed: `POST /auth/pat` with an `id` that is already taken answers `409` `CONFLICT` with `"A personal_access_token with id '<id>' already exists."`, naming the token by its `resource_type` like the `404` of `DELETE /auth/pat/{pat_id}`. It used to say `"A personal access token with id '<id>' already exists."`. The status, code and `fields: null` are unchanged.
504242bad48e3996  2026-09-30
  changed: `PUT /categories/{id}` refuses renaming a system category to the other system category's default name (`@Pendiente` to `@Opening`, or `@Opening` to `@Pendiente`): `422` on `name`, reason `RESERVED_NAME`, and nothing is written. Names are compared after trimming, case-insensitively, so `" @opening "` is refused too. It used to accept the rename while the other system category did not exist yet, and the write that later needed it then failed with `409`. A system category may still take its own default name back, and any other free name.
  changed: wording only, `POST /categories` *Reserved names*: names are compared after trimming.
5b7836a18917d7f1  2026-09-30
  changed: `POST /accounts/{id}/opening-balance` answers `404` `NOT_FOUND` when no active account of yours has that id (unknown, deleted or another user's), like every other route addressed by an id, and writes nothing. It used to answer `422` on `account_id` (`INVALID_REFERENCE`). An archived account still answers `422` on `account_id` (`INVALID_REFERENCE`), and a person account `422` on `account_id` (`PERSON_ACCOUNT`).
b0b944a97a0bd3e7  2026-09-30
  added: reason `ID_EXISTS`. `POST /transactions/import` refuses a row it would create (outcome `new`) whose `id` already belongs to one of your transactions, deleted ones included: `422` on `rows.<index>.id`, in the dry run and the apply alike, and nothing is written. The dry run used to report such a row as `new`, and the apply then failed with `409`. A `matched` or `sealed` row is never refused for its `id`, so re-running an applied file with the same ids still matches every row and writes nothing. An `id` taken by another user still previews as `new` and fails the apply with `409`, as on every create.
ee34e2bf828b9d4f  2026-09-30
  changed: `POST /transactions`, `POST /transactions/batch` and `PUT /transactions/{id}` refuse a `hashtag_ids` list that names the same id twice: `422` on `hashtag_ids` (on `transactions.<index>.hashtag_ids` in a batch), reason `DUPLICATE_IN_REQUEST`, and nothing is written. It used to fail with `500`. `DUPLICATE_IN_REQUEST` is now listed in the `x-error-reasons` of `POST /transactions` and `PUT /transactions/{id}`.
  changed: wording only, `PUT /transactions/{id}` *Field locking*: only the request's shape is checked before the lock, so a malformed or unknown field, an explicit `null` on a field that refuses it, or a repeated hashtag id is reported instead of `LOCKED`.
93a62b40ae9751d8  2026-09-29
  changed: wording only, *Assigning transactions* and `PUT /transactions/{id}`: the engine never unassigns a *moved* transaction on its own (deleting a reconciliation still unassigns); *Assigning transactions* points to `DELETE /reconciliations/{id}` for which transactions a delete unassigns.
d5cb8b7561bb128f  2026-09-29
  added: reason `ASSIGNED_TO_RECONCILIATION`. `PUT /transactions/{id}` that changes `account_id` on a transaction assigned to a draft reconciliation, without `reconciliation_id` in the same request, is now `422` on `account_id` and changes nothing. It used to move the transaction and leave it assigned to the old account's draft. Send `reconciliation_id: null` to move and unassign, or a draft on the new account to move and assign there. The rule is checked before the new account is validated, so a move to a missing or archived account reports it first (*Assigning transactions*).
```

Only `d5cb8b7561bb128f` needed app work, and it has shipped; the rest need none (the spec's
"What it must do" says why each). The live contract suite passes against it, the move test
included.
- **A.** Record `84321bd839912a09` and finish the spec.
- **B.** Hold, and look at a change first.

**Recommended:** A, because every change is handled and the live suite passes.

### Review the three draft specs
Asked 2026-09-29 · Blocks: each spec's work
[tag-suggestions.md](specs/tag-suggestions.md), [official-migration.md](specs/official-migration.md)
and [tui-import-door.md](specs/tui-import-door.md) have no open questions left and their mockups
are approved. Approve each one's draft tasks, and name the one the loop starts on.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Catch up to engine contract 84321bd839912a09** — runs before the other draft specs.
  Spec (current): [specs/engine-catch-up-84321bd8.md](specs/engine-catch-up-84321bd8.md).
- **Tag suggestions that know the category.** Spec (draft): [specs/tag-suggestions.md](specs/tag-suggestions.md).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft): [specs/official-migration.md](specs/official-migration.md).
- **Import bank files from the TUI** (with the after-apply "may be logged twice" wording). Spec
  (draft): [specs/tui-import-door.md](specs/tui-import-door.md).
- **The TUI is the only surface** (flat commands deleted except the imports, three new TUI
  features, the repo rename and the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md),
  next after the catch-up; its open questions live in the spec.
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
