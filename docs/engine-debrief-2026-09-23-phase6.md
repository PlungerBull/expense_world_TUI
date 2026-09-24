# Engine debrief: Phase 6, part 1 (restore gone, create caps, lists come back whole)

**For:** whoever changes the CLI/TUI next. **Status:** shipped and pushed in the engine
(`545872f`, `5a32e97`, `013e18d`, `9b8ae28`, all 2026-09-23). **The running engine on `:8000` is
still the old process.** Nothing breaks until it is restarted, and it should be restarted only
once this work lands (same rule as `cursor-uptake-plan.md`).
**Authority:** `expense_world_engine/docs/engine-spec.md`. If this note and the spec disagree,
the spec wins. The design reasoning is in `expense_world_engine/docs/transaction-pagination-plan.md`
§4.1 and §4.4.
**When done:** delete this file, and tell the engine side to delete its `docs/open-bugs.md` entry
`phase-6-lists`, or the parts of it that are done.

This is **separate from** `engine-debrief-2026-09-23.md` (the transaction cursor). That work is
unchanged by anything here. Do either one first; they touch different call sites, apart from
`fetch_all_pages`, which §3.1 covers.

---

## 0. At a glance

| Commit | What | For the CLI |
|---|---|---|
| `545872f` **6.1** | **Deleted is deleted.** The five `POST …/restore` routes and `?include_deleted=` are gone | ⚠️ Breaking. §1 |
| `5a32e97` **6.2** | **Create caps**: accounts 100, categories 100, hashtags 500 | ➕ Additive. §2 |
| `013e18d` **6.3** | **Accounts, categories, hashtags and a category's hashtags come back whole.** No `limit`, `offset` or `total` | ⚠️ Breaking. §3 |
| `9b8ae28` **6.4** | **`GET /reconciliations` requires `account_id` and comes back whole. `GET /reconciliations/{id}` is gone** | ⚠️ Breaking. §4 |

**All the breakage is loud.** Every one of these fails with a `422` (an unknown or missing param)
or a `404`/`405` (a removed route). None of them returns wrong data with a 200. Since `724c3fc`,
unknown query params are a `422` on every route, and that is what makes a stale `limit=` or
`include_deleted=` fail rather than be silently ignored.

**The shape of the change.** Every list is now one of three shapes, and none is paged by position:

| Shape | Response | Lists |
|---|---|---|
| **Unpaged** | `{items}`, the whole set | `/accounts`, `/categories`, `/hashtags`, `/categories/{id}/hashtags`, `/reconciliations?account_id=` |
| **Cursor** | `{items, limit, next_cursor}` | `/transactions` (the other debrief) |
| **Still offset, for now** | `{items, total, limit, offset}` | `/activity`, `/exchange-rates/history`. They move to a cursor in 6.5–6.6, not built yet, and a later debrief will cover them |

---

## 1. Deleted is deleted (6.1)

### 1.1 What changed

- **`POST /{accounts,categories,hashtags,transactions,reconciliations}/{id}/restore` are gone.**
  They now return `404`.
- **`?include_deleted=` is gone** from `/accounts`, `/categories`, `/hashtags`, `/transactions`,
  `/transactions/count` and `/reconciliations`. Sending it, even as `false`, is a `422` with
  `fields: {"include_deleted": …}`.
- **A deleted row is invisible to every client.** No list returns it, and a get-by-id is a `404`.
- **What did not change:** `DELETE` still soft-deletes, and the row stays in its table.
  **`GET /activity` still shows deleted rows' history**, including every `deleted` entry. That is
  on purpose: hiding a row from lists is not the same as hiding that it happened.
- **Undoing a delete is now an operator task,** SQL run as the owner. It is documented in
  `expense_world_engine/deploy/local/README.md` → "Undeleting a row". There is nothing for the
  CLI to call.
- `POST /reconciliations/{id}/complete` is now the **only** endpoint that returns `warnings`.
  Transaction restore was the other one.

### 1.2 Site by site

| Site | Change |
|---|---|
| `commands/accounts_cmd.py:379` `restore` | Delete the command. |
| `commands/categories_cmd.py:220` `restore` | Delete the command. |
| `commands/hashtags_cmd.py` `restore` | Delete the command. |
| `commands/transactions_cmd.py:408` `restore` | Delete the command. |
| `commands/reconcile_cmd.py:535` `restore` | Delete the command. |
| `commands/_resource.py:30` `INCLUDE_DELETED_OPT`, and every `include_deleted` parameter on the `fetch_*` helpers and `list` commands (accounts, categories, hashtags, transactions, reconcile; 26 references) | Delete. |
| `commands/_resource.py:723` `print_warnings` docstring | Stop naming transaction restore as a producer. |
| `commands/_resource.py:904` comment mentioning "archive/restore" | Reword. |
| TUI | Nothing found that calls restore or sends `include_deleted`. Re-check after the command removals. |
| `tests/unit/test_command_surface.py` and the `test_cmd_*` restore cases | Update or delete to match. |

---

## 2. Create caps (6.2)

**Additive: nothing breaks.** `POST /accounts`, `POST /people`, `POST /categories` and
`POST /hashtags` refuse a create once the collection is full:

```json
{"error": {"code": "LIMIT_REACHED",
           "message": "You already have 500 hashtags, the most allowed. Delete one to add another.",
           "fields": null}}
```

| Collection | Cap | What counts |
|---|---|---|
| Accounts | 100 | Bank **and** person accounts together, **archived ones included** |
| Categories | 100 | The owner's own categories only. `@Pendiente` / `@Opening` never count and are never refused |
| Hashtags | 500 | All |

Deleted rows never count. Reconciliations have no cap. The status is `422`, but the code is
`LIMIT_REACHED`, not `VALIDATION_ERROR`, and `fields` is `null`: no field in the form is wrong.

**CLI:** nothing required. The generic error rendering already shows the message. If a form
highlights fields on a `422`, check that it copes with `fields: null` on this code. Today's use
(about 9 accounts, 11 categories, 56 hashtags) is far from any cap.

---

## 3. Accounts, categories, hashtags come back whole (6.3)

### 3.1 What changed

`GET /accounts`, `GET /categories`, `GET /hashtags` and `GET /categories/{id}/hashtags` return

```json
{"items": [ … every row … ]}
```

There is **no `total`, `limit` or `offset`** in the response, and **sending `?limit=` or `?offset=`
is a `422`**. There is no read-side ceiling: the caps in §2 bound the collection. The filters that
existed are unchanged (`/accounts`'s `include_people`, `include_archived`), and so are ordering and
row shape.

This also fixes a live bug. With 56 hashtags and a default page of 50, any caller that forgot to
page lost 6 tags.

### 3.2 `fetch_all_pages` (`commands/_resource.py:286`)

**Keep it for now.** `/activity` and `/exchange-rates/history` still page by offset until 6.5–6.6.
Every caller that uses it on the four unpaged lists must stop, because the loop's first request
sends `limit` and `offset` and gets a `422`.

### 3.3 Site by site

| Site | Today | Change |
|---|---|---|
| `tui/screens/categories.py:44` | `fetch_all_pages` over `fetch_categories` | One `fetch_categories(cfg, **kw)` call. The 20-row window still pages client-side over the full set. |
| `tui/screens/hashtags.py:38` | `fetch_all_pages` over `fetch_hashtags` | One call. Same. |
| `commands/_resource.py:508, 511` (the picker loaders) | `fetch_all_pages` for categories and hashtags | One call each. |
| `commands/_resource.py:342` `_load_name_map` (used for `/accounts`, `/categories`, `/hashtags` at :364, :369, :395) | `fetch_all_pages` with `limit` / `offset` | One `client.get(path, params=params)`. |
| `import_/apply.py:70` (sheet importer's reference fetch: accounts, categories, hashtags) | `fetch_all_pages` with `limit` / `offset` | One `client.get`. |
| `commands/{accounts,categories,hashtags}_cmd.py` `fetch_*` + `list` | Accept `limit` / `offset`; `list` has `--limit` / `--offset` (`OFFSET_OPT`) and prints offset hints | Drop them. `OFFSET_OPT` stays for `activity` (and `transactions` until the cursor work removes it). |
| `tui/screens/accounts.py:56`, `tui/screens/reconciliations.py:214, 599`, `bank_import_cmd.py:470` | Plain `fetch_accounts` (one page, no paging params) | Works, and now really is the whole set. Check `screen_fetch_kwargs` sends no `limit`. |
| Category-hashtag picker (not built) | — | `GET /categories/{id}/hashtags` is `{items}` with no `total`. Build it against that. |

---

## 4. Reconciliations (6.4)

### 4.1 What changed

- **`GET /reconciliations` requires `?account_id=`.** Without it the response is a `422` with
  `fields: {"account_id": "Field required"}`. It returns **that account's** reconciliations, all of
  them, as `{items}`, in period order: `date_start ASC NULLS LAST, created_at ASC`.
  `?limit=` / `?offset=` are a `422`. The cross-account listing (`created_at DESC`) is gone.
  - Why: reconciliations grow with time, so no create cap can bound them. One account's
    statements (about 12 a year) can.
- **`GET /reconciliations/{id}` is gone.** A GET on that path is a `405`, because `PUT` and
  `DELETE` still live there. That takes away two things:
  - **The embedded transaction page** (`transactions`, `transactions_total`, `_limit`, `_offset`,
    `_truncated`). A batch's transactions are `GET /transactions?reconciliation_id=` on the
    cursor, plus `/transactions/count` for the number.
  - **The single-record read.** Use the account's list, which always contains the row, or the row
    that every mutation (`PUT`, `complete`, `revert`, `DELETE`) already returns.
- Engine `open-bugs.md` **D14** is updated: the browse screen's "fetch everything, slice client-side"
  design is over, and the refusal of `?status=` stands.

### 4.2 Site by site

| Site | Today | Change |
|---|---|---|
| **Browse screen** `tui/screens/reconciliations.py:209` `fetch` | `fetch_all_pages` over `fetch_reconciliations` with no account, then slices per account in `_rebuild_batches` | Fetch `?account_id=<selected>` when the account cursor moves, or once per account up front and merge. The list is already in period order, so `_batch_sort_key` may be redundant. **Moving the account cursor costs a request now, and D14 did not assume that.** Fetching all accounts up front (about 9) keeps cursor moves free, if that matters. |
| `commands/reconcile_cmd.py:65` `fetch_reconciliations` | `account_id` optional; `include_deleted`, `limit`, `offset` | `account_id` required; drop the other three. Update the docstring's ordering note. |
| `commands/reconcile_cmd.py` `reconcile list` | Works without an account | Require `--account` (or loop over accounts if an "all" view is wanted). Drop `--offset` / `--limit` / `--include-deleted`. |
| `commands/reconcile_cmd.py:352` `reconcile get` and `fetch_reconciliation` (:102) | `GET /reconciliations/{id}` with an embedded page | **Delete the command.** To show a batch's transactions, use `transactions list --reconciliation <id>` (cursor). |
| **Working screen refresh** `tui/screens/reconciliations.py:878` | `fetch_reconciliation(cfg, self._id, limit=1)` by id; treats `404` as "record gone" (backlog 6.2b) | Re-read the batch's account list (the screen knows `account_id`) and find the row by id. **Not found there** now means it is gone (deleted). That check is reliable, because the list is whole and not paged, which was 6.2b's original worry. |
| **`reconcile complete` hint** `commands/reconcile_cmd.py:286` | After a `422` for unassigned rows, reads the record by id to fill in account and window for the hint | ⚠️ **No by-id read any more, and the command knows only the id.** See §4.3. |
| Checklist `tui/screens/reconciliations.py:713` `_fetch_all_txns` | Already covered by the cursor debrief | No change here. |
| Unfiled pane `!` hint | Uses `GET /reconciliations` fields per account | Needs the per-account fetch like the browse screen. Nothing else changes. D13's caveat still applies. |

### 4.3 One open gap: the `complete` hint

`reconcile complete <id>` gets a `422` when rows in the window are unassigned. That `422` carries
the count but not the account or the window, so the command used to spend one by-id read to fill
in its hint. That read is gone, and the flat command has only the id. Options, in order of
preference:

1. **Ask the engine** to put `account_id`, `date_start` and `date_end` in that `422`'s
   `fields`/message. It is the refusal's own subject, so it arguably belongs there. **This is
   an engine ask. It is not decided yet.**
2. Until then, fall back to `_UNASSIGNED_HINT_BARE`. The code already does this when the read
   fails, so today it degrades to the bare hint on its own. It does not crash.
3. Take `--account` on `reconcile complete` and read the list. This adds a flag for the sake of a
   hint.

The TUI working screen is unaffected: it already knows the record.

---

## 5. Checking it works (after the engine restart)

- `expense accounts list`, `categories list`, `hashtags list`: every row, no paging hints. Hashtags
  shows all 56.
- TUI categories and hashtags screens: "page N of M" is right, and no `422` appears in the log.
- Reconciliations browse: switching accounts shows each account's full history, oldest period
  first.
- Working screen: `r` refresh keeps the header current, and deleting the batch from another
  terminal shows "record gone".
- Sheet and bank importers: a dry run resolves every account, category and hashtag name as before.
- `grep -rn "include_deleted\|/restore\|reconciliations/{" expense/`: only the `PUT` / `DELETE` /
  `complete` / `revert` paths remain.

---

## 6. Checklist

- [ ] Delete the five `restore` commands and their tests *(6.1)*
- [ ] Delete `INCLUDE_DELETED_OPT` and every `include_deleted` param *(6.1)*
- [ ] `print_warnings` docstring and the `_resource.py:904` comment *(6.1)*
- [ ] *(optional)* Forms cope with `LIMIT_REACHED` and `fields: null` *(6.2)*
- [ ] Categories and hashtags TUI screens, picker loaders, `_load_name_map` and sheet importer: one GET each, no `fetch_all_pages` *(6.3)*
- [ ] Accounts, categories and hashtags `fetch_*` and `list`: drop `limit` / `offset` *(6.3)*
- [ ] Reconciliations browse screen: per-account fetch *(6.4)*
- [ ] `fetch_reconciliations` requires `account_id`; `reconcile list` requires `--account` *(6.4)*
- [ ] Delete `reconcile get` / `fetch_reconciliation`; point users at `transactions list --reconciliation` *(6.4)*
- [ ] Working-screen refresh: read the account list, not by id *(6.4)*
- [ ] `reconcile complete` hint: decide §4.3 (engine ask vs bare hint) *(6.4)*
- [ ] Run §5 after the engine restart
- [ ] Delete this file; tell the engine side to delete `open-bugs.md` → `phase-6-lists`
