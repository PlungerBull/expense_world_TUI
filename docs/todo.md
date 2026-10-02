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

### Catch up to engine contract 8d2430081e64cd7c — now, or after the import door?
Asked 2026-10-02 · Blocks: the import door's acceptance check, and every new task
The engine coders changed the engine again (saved 84321bd839912a09, engine 8d2430081e64cd7c).
What changed, exactly as the version check prints it:

```
8d2430081e64cd7c  2026-10-02
  changed: wording only, `POST /people`: the refusal of an explicit `null` on `color` or `sort_order`, and the `color` default, are stated once under `POST /accounts`, which `POST /people` shares. The rule is unchanged.
0784eae3d79f37fe  2026-10-02
  changed: `GET /exchange-rates` and `GET /exchange-rates/history` answer `422 SETTINGS_MISSING` (`fields: {"user_settings": "Must be provisioned via POST /v1/auth/bootstrap."}`, reason `NOT_PROVISIONED`) when the caller's settings do not exist yet, whether or not a `date` or window was sent. They used to read "today" in UTC for such a caller. Both are now listed under *Settings preconditions*, and `SETTINGS_MISSING` is in their `x-error-codes` and `NOT_PROVISIONED` in their `x-error-reasons`. A caller with settings gets the same answers as before.
  changed: wording only, *Calendar days*: states that a stored zone the engine does not recognise is read as UTC, which `GET /exchange-rates` used to state for itself alone.
0c56cb602654a20a  2026-10-02
  changed: `POST /accounts` and `POST /people` refuse an explicit `null` on `color` or `sort_order`: `422` on each such field, `"Must not be null."`, reason `NOT_NULL`, and nothing is written. Both nulls in one request report both fields. They used to treat `null` as omitted and apply the default. An omitted `color` still takes `#3b82f6` and an omitted `sort_order` still appends. `NOT_NULL` is now listed in their `x-error-reasons`, and their request schemas no longer offer `null` for either field.
ba0ecb2a0472e990  2026-10-02
  changed: `POST /transactions/batch` accepts at most 500 items, the same bound as the rows of `POST /transactions/import`. A batch of more is `422` on `transactions` (the list itself, not an item), reason `OUT_OF_RANGE`, message `"List should have at most 500 items after validation, not <n>"`, and nothing is written. It used to have no limit. `OUT_OF_RANGE` is now listed in its `x-error-reasons`, and its request schema states `maxItems: 500`.
  changed: wording only, `POST /transactions/import`: the row bound names its `422` on `rows` (`OUT_OF_RANGE`) and that the batch shares it.
28d04decdc632da6  2026-10-02
  changed: `PUT /auth/profile` trims leading and trailing whitespace from `display_name` before storing it, and refuses an empty or whitespace-only `display_name` with `422` on `display_name`, `"Must not be empty."`, reason `EMPTY`; nothing is written. It used to store the value as sent, blank included. `EMPTY` is now listed in its `x-error-reasons`.
  changed: `POST /auth/bootstrap` applies the same rule to `display_name`: a new user's name is stored trimmed, and an empty or whitespace-only `display_name` is `422` on `display_name` (`EMPTY`) on every call, also for an existing user, whose name is still never overwritten. Nothing is written on refusal, `last_login_at` included. It used to store a new user's name as sent and ignore an existing user's.
```

None of it touches importing. The app sends batches of 200 (under the new 500 cap) and its
create forms always send a colour. What is left to check: an empty name at first-time setup is
now refused, and a brand-new user's exchange rates answer with an error.
- **A.** Catch up first (a small spec), then finish the import door's check.
- **B.** Record the new version now, finish the import door's check, then catch up as the next spec.

**Recommended:** B, because nothing in the import door depends on these changes, and the
catch-up is a few checks and hints that fit their own small spec.

### Review the two draft specs
Asked 2026-09-29 · Blocks: each spec's work
[tag-suggestions.md](specs/tag-suggestions.md) and [official-migration.md](specs/official-migration.md)
have no open questions left and their mockups are approved. Approve each one's draft tasks. The
current spec is [tui-import-door.md](specs/tui-import-door.md) (owner, 2026-10-02); its own
question lives in it.

---

## Backlog

Open work. Items with a spec link it; the rest are not yet a spec. Bigger items link their plan doc, which is deleted when the work
ships (its why moves to [decisions.md](decisions.md)).

- **Two flaky unit tests.** Each failed once in a full `pytest tests/unit` run on 2026-10-02
  and passes alone; for each, find whether the test asserts too early or the screen has a race.
  - `test_toggle_error_drops_queued_intents_and_resyncs`
    ([test_tui_reconcile_detail.py](../tests/unit/test_tui_reconcile_detail.py)): 2 PUTs sent,
    1 expected — the queued toggle went out before the failing PUT's error dropped it.
  - `test_config_screen_shows_only_the_engine_connection`
    ([test_tui_system.py](../tests/unit/test_tui_system.py)).
- **Tag suggestions that know the category.** Spec (draft): [specs/tag-suggestions.md](specs/tag-suggestions.md).
- **Move the official data into the app** (sheet re-import, `PENDIENTES`, title alignment).
  Spec (draft): [specs/official-migration.md](specs/official-migration.md).
- **Import bank files from the TUI** (with the after-apply "may be logged twice" wording). Spec
  (current): [specs/tui-import-door.md](specs/tui-import-door.md).
- **The TUI is the only surface** (flat commands deleted except the imports, three new TUI
  features, the repo rename and the engine-coder note). Spec: [specs/tui-only-plan.md](specs/tui-only-plan.md),
  paused behind the import door; its open questions live in the spec.
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
