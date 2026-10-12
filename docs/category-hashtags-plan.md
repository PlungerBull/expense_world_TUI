# Tags that know the category — CLI/TUI plan

**Status: not built.** The shape is pane **D**: the category's tags first, every other tag
below a divider. §5 holds the settled choices. Spec: [tag-suggestions.md](specs/tag-suggestions.md). It answers the
owner's ask *"can we only suggest hashtags that exist on the category if a category exists?"*. When
it ships, its why moves to [decisions.md](decisions.md) and this file is deleted.

**[UI].** [expense-world-log-legend-and-picker.html](mockups/expense-world-log-legend-and-picker.html)
is re-shown and re-picked before any TUI code; it predates the endpoint, so it does not show an
empty result or a >50-tag category.

---

## 1. What the engine now does

`GET /v1/categories/{category_id}/hashtags` — the hashtags this category has been
used with, most-used first; the full order is under "Field rules" below. Read-only
(contract: GET /v1/categories/{category_id}/hashtags).
**Returns the whole list, unpaged**
(contract: "Base Conventions", "Lists come in three shapes, and none of them is paged by position").
The route declares no query parameter, so `?limit=` / `?offset=` are a `422`
(contract: "Base Conventions", "Unknown query parameters").

```json
{ "items": [ {"id": "<uuid>", "name": "ALQUILER", "uses": 142},
             {"id": "<uuid>", "name": "LUZ",      "uses": 25} ] }
```

Field rules that matter to this repo:

- **`uses` counts transactions.** A row carrying two tags adds 1 to each
  (contract: GET /v1/categories/{category_id}/hashtags, "`uses` counts transactions").
  Safe to show as a transaction count.
- **Ordering is `uses` descending, then the hashtag's creation time, oldest first**
  (contract: GET /v1/categories/{category_id}/hashtags, "Ordering").
- **An empty list is not a 404**; `404` means the category is not yours or is deleted
  (contract: GET /v1/categories/{category_id}/hashtags). This plan reads an empty list as
  "no tags used here yet".
- Removed tag links, deleted transactions and deleted hashtags are excluded
  (contract: GET /v1/categories/{category_id}/hashtags, "Exclusions"), so a retired tag is
  never suggested.
- A tag never used on the category is not returned; the client appends those from
  `GET /hashtags` (contract: GET /v1/categories/{category_id}/hashtags, "The relationship is derived from the ledger").

> ⚠️ **Never cache this as a mapping.** There is no declared link between a category and a
> hashtag; the relationship is derived from the ledger
> (contract: GET /v1/categories/{category_id}/hashtags, "The relationship is derived from the ledger").
> This plan therefore treats the answer as able to change the moment something is tagged: a
> local table would be a stale copy of a fact the engine computes. An **in-session** cache is
> a different thing and is required — see §4.

## 2. What exists today

- **No surface at all.** Only the contract suite calls the endpoint
  ([test_category_hashtags.py](../tests/contract/test_category_hashtags.py)), which pins the rules in §1
  against the practice engine.
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

## 3. The flat command

`expense categories hashtags <id>` — a read, with `--json`. No paging flags: the endpoint returns every row.

An endpoint with no flat surface is an untested contract, and the command answers "why is this
tag not in my picker?" without the TUI.

Columns (signed off): **Name** only, in the order the engine returns them (§1); `--json` carries
`id` and `uses` for anyone who needs them.

`test_typer_tree_walk_finds_expected_command_count` holds a count constant that a
new command bumps.

## 4. The picker

**The shape (pane D):** with a category named in the line, `#` offers that category's tags
first, in the order the engine returns them (§1), then a dim divider, then every other tag alphabetically. Nothing is
hidden, so a first cross-category use of a tag is a few `↓` away, and typing filters both
groups as it does today. With no category named — or an ambiguous one — the full list stands,
exactly as today.

Label pickers in apps like Todoist and Gmail rank rather than hide, and hiding (pane E) needed
an escape hatch, an empty-list case and a legend change that ranking does not.

### 4a. The ordering is display-only — the one thing that must not go wrong

`parse()` decides what **resolves**. The picker decides what is **offered**. These
must stay separate.

If the ranked pool were fed back into `parse()`, a typed `#DERMA` on a category
that has never carried `#DERMA` would stop resolving, become an unresolved token,
and the LOG bar's `↵` would **refuse the line** ([quickadd/route.py](../expense/quickadd/route.py)
is the one rule for both surfaces, and the flat `expense log` exits 1 on the same
lines). That turns a suggestion feature into a data-entry wall.

So: `parse()` keeps the full pool and is not touched. The ranking happens in
`log_bar._picker_at`, over `token.candidates`, after the category is known from
the same parse. Any test suite for this must pin that a full tag name typed
against an unrelated category still stages.

### 4c. Fetching, and the cache that is allowed

The category changes per keystroke, so this cannot ride the one-shot
`load_quickadd_refs` that runs on mount. It needs the account-peek pattern:

- fetch lazily, when the caret opens a `#` token **and** a category is resolved;
- debounce, so typing a category name does not fire a request per character;
- cache per category id **for the life of the screen** — this is not the
  forbidden mapping, it is one screen's session, and without it every keystroke
  is an HTTP call;
- one plain GET: the list comes back whole, bounded by the hashtag create cap of 500
  (contract: "Base Conventions", "Create caps"), so there is nothing to page.

### 4d. The states the mockup does not draw

| State | Proposed behaviour |
|---|---|
| Category named, has tags | Those tags first, the divider, then the rest |
| Category named, **no tags yet** | Full list, exactly as today — no divider with nothing above it |
| No category in the line | Full list, exactly as today |
| Category typed but ambiguous | Full list — nothing has been chosen to filter by |
| Fetch fails or is still in flight | Full list, exactly as today; the ranking appears when the fetch lands |

## 5. Settled choices

- **Only the LOG bar ranks.** It is the one surface where category and tags are chosen in one
  breath. The bulk `h` pick sets tags on rows whose categories may differ, so there is no single
  category to rank by; the edit form's category can change after the tags are chosen.
- **No usage counts on screen.** The list already arrives most-used first (§1), so the number costs width
  and says nothing new — in the picker and in the flat command's table alike.

## 6. Non-goals

| Not doing | Why |
|---|---|
| Category **suggestions** from tags (the reverse) | Merchant memory and category suggestion were rejected 2026-09-13 |
| Counting deleted transactions as uses | A deleted row no longer uses its tags; this is the engine's rule (§1) and what the owner expects |
| Persisting the ranking anywhere | §1's warning — it is derived, not stored |
| Using `uses` to reorder the tags below the divider | That group stays alphabetical and predictable; only the category's group is ranked |

## 7. Tests

- `categories hashtags` happy path + error shape + `--json` passthrough;
  no pagination hint (the list is whole).
- **The critical one:** a full tag name typed against a category that has never
  used it still resolves and still stages. §4a is the regression this guards.
- `#` with a resolved category offers that category's tags first, then the divider, then every
  other tag; no tag is missing from the list.
- No category in the line → full list, byte-identical to today's behaviour.
- Empty result → the full list with no divider.
- A failed or in-flight fetch leaves the full list.
- The per-category cache is consulted on the second keystroke (one request, not
  two) and is not shared between categories.

## 8. Sequence

1. `fetch_category_hashtags` in [categories_cmd.py](../expense/commands/categories_cmd.py),
   shaped for both surfaces — flat table and picker pool.
2. The flat command, with the column sign-off.
3. The LOG bar: lazy fetch, debounce, per-category cache, the fallbacks in §4d.
