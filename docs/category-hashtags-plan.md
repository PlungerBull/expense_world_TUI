# Tags that know the category — CLI/TUI plan

**Status: not built.** The shape is decided (owner picked mockup pane **E**, 2026-09-20); §5 holds
four forks that are not, and §6 points at the questions only the owner can answer. It answers the
owner's ask *"can we only suggest hashtags that exist on the category if a category exists?"*. When
it ships, its why moves to [decisions.md](decisions.md) and this file is deleted.

**[UI].** [expense-world-log-legend-and-picker.html](mockups/expense-world-log-legend-and-picker.html)
is re-shown and re-picked before any TUI code; it predates the endpoint, so it does not show an
empty result or a >50-tag category.

---

## 1. What the engine now does

`GET /v1/categories/{category_id}/hashtags` — the hashtags this category has been
used with, most-used first. Read-only. **Returns the whole list, unpaged** (engine-spec *Base
Conventions*, [../../expense_world_engine/docs/engine-spec.md](../../expense_world_engine/docs/engine-spec.md)):
`?limit=` / `?offset=` are a `422`.

```json
{ "items": [ {"id": "<uuid>", "name": "ALQUILER", "uses": 142},
             {"id": "<uuid>", "name": "LUZ",      "uses": 25} ] }
```

Field rules that matter to this repo:

- **`uses` counts transactions, not junction rows.** A row carrying two tags adds
  1 to each, never 2 to either. Safe to show as a transaction count.
- **Ordering is `uses DESC, created_at ASC`** (not name: a name is mutable).
- **An empty list is not a 404.** It means "no tags used here yet", which is what
  every category returns before it has history. `404` means the category is not
  yours or is deleted.
- Soft-deleted junction rows, transactions and hashtags are excluded, so a retired tag is
  never suggested.

> ⚠️ **Never cache this as a mapping.** There is no category→hashtag link in the
> schema and deliberately never will be; the answer is derived from the ledger on
> every read and changes the moment something is tagged. A local table would be a
> stale copy of a fact the engine computes correctly. An **in-session** cache is
> a different thing and is required — see §4.

## 2. What exists today

- **No surface at all.** Nothing in this repo calls the endpoint.
- **The tag pool is global and flat.** `load_quickadd_refs`
  ([_resource.py](../expense/commands/_resource.py)) reads `GET /hashtags` once
  and hands the full list to `parse()`.
- **`parse()` is pure and takes the pool as an argument**
  ([quickadd/parse.py](../expense/quickadd/parse.py)). A bare `#` "means *show me
  what there is*" — it resolves to nothing and stands unresolved carrying every
  candidate, which is exactly a picker's input.
- **The picker draws whatever `token.candidates` holds**
  ([log_bar.py](../expense/tui/screens/log_bar.py) `_picker_at` →
  [widgets/picker.py](../expense/tui/widgets/picker.py) `suggestion_list`).
- **Name matching is accent-blind and shared** ([quickadd/names.py](../expense/quickadd/names.py)).
- **Precedent for the fetch shape:** the LOG bar's account peek keeps `_peek_cache` per
  account plus a debounce timer.

## 3. H1 — the flat command

`expense categories hashtags <id>` — a read, with `--json`. No paging flags: the endpoint returns every row.

An endpoint with no flat surface is an untested contract, and the command answers "why is this
tag not in my picker?" without the TUI.

Columns, for the sign-off the process requires ([cli-spec.md](cli-spec.md)):
**Name · Uses · Id.** Nothing else is in the payload, and deliberately so — the
row is not a full hashtag record.

`test_typer_tree_walk_finds_expected_command_count` holds a count constant that a
new command bumps.

## 4. H2 — the picker

**The shape, picked 2026-09-20:** with a category named in the line, `#` offers
**only** that category's tags. `##` opens the full list. With no category named —
or an ambiguous one — the full list stands, because there is nothing to filter by.

Pane D (the category's tags first, the rest below a divider) was the written recommendation;
the owner picked E ("make them invisible"). **`##` is what makes E safe**: a first
cross-category use of a tag is one keystroke away, not unreachable.

### 4a. The filter is display-only — the one thing that must not go wrong

`parse()` decides what **resolves**. The picker decides what is **offered**. These
must stay separate.

If the narrowed pool were fed back into `parse()`, a typed `#DERMA` on a category
that has never carried `#DERMA` would stop resolving, become an unresolved token,
and the LOG bar's `↵` would **refuse the line** ([quickadd/route.py](../expense/quickadd/route.py)
is the one rule for both surfaces, and the flat `expense log` exits 1 on the same
lines). That turns a suggestion feature into a data-entry wall.

So: `parse()` keeps the full pool and is not touched. The narrowing happens in
`log_bar._picker_at`, over `token.candidates`, after the category is known from
the same parse. Any test suite for this must pin that a full tag name typed
against an unrelated category still stages.

### 4b. `##` costs a parser change

A bare `#` already means "everything". Under E, `#` means "this category's tags"
and `##` means "everything" — and `##` is **not** free: `parse()` would read
`text[0] == "#"` with `head == "#"` and try to match a tag whose name contains
`"#"`, finding none. It needs explicit handling. See decision **H3** for whether
the escape hatch is a character at all.

### 4c. Fetching, and the cache that is allowed

The category changes per keystroke, so this cannot ride the one-shot
`load_quickadd_refs` that runs on mount. It needs the account-peek pattern:

- fetch lazily, when the caret opens a `#` token **and** a category is resolved;
- debounce, so typing a category name does not fire a request per character;
- cache per category id **for the life of the screen** — this is not the
  forbidden mapping, it is one screen's session, and without it every keystroke
  is an HTTP call;
- one plain GET: the list comes back whole (bounded by the 500-hashtag cap), so there is
  nothing to page.

### 4d. The states the mockup does not draw

| State | Proposed behaviour |
|---|---|
| Category named, has tags | Only those tags; hint says `## for all N` |
| Category named, **no tags yet** | See **H2** — an empty filtered list is a dead end |
| No category in the line | Full list, exactly as today |
| Category typed but ambiguous | Full list — nothing has been chosen to filter by |
| Fetch fails or is still in flight | Full list, never a blank picker; a picker that empties on a slow request is worse than one that never narrowed |

## 5. Decisions to review

**H1 — which surfaces narrow?** The LOG bar is certain. Three others pick hashtags.

| | Scope | Notes |
|---|---|---|
| **A** *(recommended)* | LOG bar only | Where the ask came from, and the only surface where category and tags are chosen in one breath |
| **B** | LOG bar + Home/Transactions bulk `h` | The bulk modal sets tags on rows whose categories may **differ from each other** — there is no single category to filter by |
| **C** | Every hashtag picker | Includes the edit form, where the category field can change after the tags are chosen — the pool would need to re-narrow mid-form |

**A**, and B is arguably incoherent rather than merely bigger.

**H2 — a category with no tags yet.** The engine returns an empty list, which is
the normal state of every new category.

| | Behaviour | Notes |
|---|---|---|
| **A** *(recommended)* | Fall back to the full list, with a hint saying why | An empty picker under a bare `#` reads as "you have no tags", which is false |
| **B** | Show `no tags used here yet — ## for all N` and nothing else | Literal, honest, and a dead end requiring a second keystroke on every new category |

**A** — the fallback is invisible when it is not needed and correct when it is.

**H3 — is the escape hatch `##`?** It is what pane E drew, and §4b is its cost.

| | Shape | Notes |
|---|---|---|
| **A** *(recommended)* | `##`, as drawn | Discoverable from the legend row, typed in the same breath, no new key |
| **B** | A key (e.g. `ctrl+n` to widen the open picker) | No parser change — but forms have no `?` card, so a key here has no discovery surface ([todo.md](todo.md) "Field navigation in the edit form") |
| **C** | Auto-widen when the narrowed pool matches nothing typed | Zero keystrokes, and it makes the pool change under the user mid-word |

**A**, and the parser change is small and testable as a pure function.

**H4 — does `uses` show in the picker?** The endpoint returns it and pane E does
not draw it.

Recommended: **no** in the picker, **yes** in the flat command. Under E the list
is already short and already ordered by use, so the number is decoration that
costs width; in `categories hashtags` it is the whole point of the read.

## 6. Open questions for the owner

In [todo.md](todo.md) "Questions for the owner", the entries titled "Tags that know the category:
…" — including one for the §5 choices.

## 7. Non-goals

| Not doing | Why |
|---|---|
| Category **suggestions** from tags (the reverse) | Merchant memory and category suggestion were rejected 2026-09-13 |
| Persisting the ranking anywhere | §1's warning — it is derived, not stored |
| Using `uses` to reorder the *full* list | The full list is alphabetical and predictable; re-ranking it would make the escape hatch's contents move around |

## 8. Tests

- `categories hashtags` happy path + error shape + `--json` passthrough;
  no pagination hint (the list is whole).
- **The critical one:** a full tag name typed against a category that has never
  used it still resolves and still stages. §4a is the regression this guards.
- `#` with a resolved category offers only that category's tags; `##` offers all.
- No category in the line → full list, byte-identical to today's behaviour.
- Empty result → H2's chosen fallback.
- A failed or in-flight fetch leaves the full list, never a blank picker.
- The per-category cache is consulted on the second keystroke (one request, not
  two) and is not shared between categories.

## 9. Sequence

1. H1–H4 answered; the mockup re-shown and re-picked (**[UI] gate**).
2. `fetch_category_hashtags` in [categories_cmd.py](../expense/commands/categories_cmd.py),
   shaped for both surfaces — flat table and picker pool.
3. The flat command, with the column sign-off.
4. `##` in `parse()`, as a pure function with its own tests.
5. The LOG bar: lazy fetch, debounce, per-category cache, the fallbacks in §4d.
6. Contract test against the disposable engine — nothing in this repo calls the endpoint yet.
