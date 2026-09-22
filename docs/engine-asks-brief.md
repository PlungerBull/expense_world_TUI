# Engine asks from the CLI — brief for the engine repo (2026-09-22)

**From:** `expense_world_CLI` (the Hands), after building ask 1 of the 2026-09-20 queue
— sealed periods reaching the user.
**To:** whoever works `expense_world_engine`.
**Nothing here has been written in the engine repo.** The CLI repo never edits it; this
is a request, with evidence.

**Why these arrive as a batch.** The CLI's stated job is to exercise every endpoint
through real human use before the web and iOS clients exist, so that a contract fault is
found here rather than by mobile users. Each item below is a place where the CLI could
only reach the correct behaviour by working around the engine, and where the workaround
would have to be copied into every later client.

**How to read the priorities.** **A1 is the one worth doing.** A2 is a genuine
capability gap but the need behind it has since been met another way. A3 and A4 are
recorded honestly as *probably not worth your time* — they are listed because the CLI
side raised them and it is better to say why they are weak than to leave them implied.
**A5 is not a feature request at all — it is a wording bug**, cheap, and the CLI cannot
fix it without lying to the user.

The CLI's own record of these lives in `expense_world_CLI/docs/todo.md` ("Engine asks");
this file is the hand-over copy and is deleted once they are resolved.

---

## A1 — `GET /transactions` cannot be asked for oldest-first  ·  **please do this one**

### The ask

An opt-in ordering parameter on `GET /transactions`. Default unchanged.

```
GET /transactions?sort=date_asc      → date ASC, created_at ASC
GET /transactions                    → date DESC, created_at DESC   (today, unchanged)
```

Name and spelling are yours. What the CLI needs is only *a documented way to ask for
ascending date order with working pagination*.

### Why no client can do this today

`app/routers/transactions.py:148` passes `order_by="t.date DESC, t.created_at DESC"` as a
literal, and the endpoint takes no ordering parameter (`docs/engine-spec.md`,
`GET /transactions` — the filter list has `account_id`, `category_id`, `hashtag_id`,
`reconciliation_id`, `unreconciled`, `date_from`, `date_to`, `search`, and pagination).
So **ascending order is not expressible by any caller**, at any page size.

### What the CLI is doing instead, and what is wrong with it

The TUI grew a pane (2026-09-22) that answers one question: *which rows on this account
belong to no reconciliation, oldest first?* Oldest-first is the entire point — a row from
a month whose statement closed long ago is a problem, while a recent unfiled row is just
waiting for the next statement. With no way to ask, the pane:

1. reads `total` from a `limit=1` probe,
2. requests `offset = total - limit` to get the tail,
3. reverses that one page client-side for display.

`expense_world_CLI/expense/tui/screens/reconciliations.py` (`unfiled_offset`,
`unfiled_rows`). Three faults, in order of seriousness:

- **It races.** Any write between the probe and the page read shifts the window, so a row
  at the page edge can be missed or shown twice. Single-user today; still wrong, and not
  something a client can fix.
- **It cannot page.** Walking further back means computing offsets downward by hand
  against a total that may have moved. The pane is therefore **capped at one page** — a
  deliberate limit that exists only because of this gap. On the live ledger this list is
  ~3553 rows until the 2026 backfill closes its periods.
- **It costs two round trips** for what is one query.

And it does not generalise: the web dashboard and iOS will want the same view, and would
each reimplement the same trick. That is the specific thing the CLI is supposed to catch.

### Your own counter-argument, addressed

`app/constants.py:58-69` states it plainly: *"A list's order is part of its contract; two
orders is two contracts."* Written after `@Pendiente` appeared at the top of
`GET /categories` and mid-grid on `/dashboard` for the same user at the same instant.

That principle is about **accidental divergence between endpoints on the same
collection** — two endpoints disagreeing about one collection's order, with no caller
able to tell which they would get. An explicit, documented, opt-in parameter with an
unchanged default is a different thing: the contract stays single-valued, and the caller
states which of two documented orders it is asking for.

Worth noting alongside it: `constants.py` defines `ACCOUNT_ORDER_BY`,
`CATEGORY_ORDER_BY`, `HASHTAG_ORDER_BY` and `CATEGORY_HASHTAG_ORDER_BY`, but there is
**no `TRANSACTION_ORDER_BY`** — the ledger's order is the one hard-coded inline at the
call site. If you take this ask, hoisting it into `constants.py` beside the others (as
two named clauses) would put the collection with the most callers under the same rule as
the rest.

### Acceptance, from the CLI side

- `?sort=date_asc` returns the same rows as the default in the exact reverse order,
  including across pages: page 1 of ascending equals the last page of descending,
  reversed, for a ledger that is not being written to.
- The tie-break is stated in the spec (`created_at ASC` mirrors the file's existing
  convention).
- Combines with every existing filter, notably `?unreconciled=true&account_id=`.
- An unknown `sort` value is a `422` naming `sort`, not a silent fallback to the default
  — a silent fallback would read as "your sort worked" while returning the opposite
  order, which is the one failure mode a client cannot detect.

### What the CLI deletes when it lands

`unfiled_offset`, the `limit=1` probe read, the `reversed()` in `unfiled_rows`, the
one-page cap, and their tests. The pane then pages backwards like every other list.

---

## A2 — the uncovered-period gap is prose only, so no client can act on it

### The ask

Carry the gap's **two dates as fields** on the `complete` response, beside the existing
sentence. Optionally the count of unfiled rows inside that stretch, if it is cheap where
you already stand.

Shape is yours; the CLI needs only that the days exist as data. For example:

```json
{ "...": "...",
  "warnings": ["2026-06-25 to 2026-07-24 is not covered by ..."],
  "coverage_gap": { "first_uncovered_day": "2026-06-26",
                    "last_uncovered_day":  "2026-07-23",
                    "unfiled_count": 3 } }
```

### Why

`app/helpers/periods.py:373-377` returns the gap as one English sentence, and
`warnings` is `list[str]`. The dates therefore exist nowhere a client can read.

The CLI wanted to show the rows sitting in that uncovered stretch — the warning's
obvious follow-up question is *"is anything actually in there?"*, and
`?unreconciled=true&account_id=&date_from=&date_to=` would answer it exactly. To build
that query a client must know the two days, which leaves only two options, both refused:

- **Parse the sentence.** Prose is not a contract; a reworded message silently breaks
  every client, or worse, makes it query the wrong days.
- **Re-derive the rule client-side** — previous *completed*, non-deleted, fully-dated
  period on that account, resolved in the user's `display_timezone`. That is a copy of an
  engine rule in a client, which this repo does not do, and it would drift the day your
  definition moved.

### Honest priority: lower than A1

The need that motivated it — *review everything unfiled, spot rows from long-closed
months* — is now served by the CLI's new pane (see A1), which asks per account rather
than per gap. So this buys a better warning (naming the rows, and distinguishing "a gap
with three rows in it" from "a gap with nothing in it", which is most of them), not a
missing capability. Do A1 first.

### What the CLI deletes when it lands

Nothing — it *adds*: a count on the warning line and a door to those rows.

---

## A3 — a coverage/window flag on transaction reads  ·  **probably not worth it**

Recorded for completeness, with the argument against it, which the CLI now thinks is the
stronger one.

The new pane marks a row with `!` when its date falls inside one of that account's
reconciliation windows, meaning *this row will refuse that batch's close*. It computes
that client-side by comparing the row's date against windows it already holds from
`GET /reconciliations?account_id=` — `date_start`, `date_end` and `status` are all
structured fields on that response, so **no prose is parsed and no rule is duplicated**;
the comparison is the definition of "inside a date range".

The only gap is **day-boundary parity**: the engine resolves a window as calendar days in
the user's `display_timezone` (`engine-spec.md`, "The window is a closed range of
calendar days"), and the client compares ISO date prefixes. A row timestamped near
midnight in another offset could be flagged one day differently from how the engine will
judge it. The CLI treats the flag as a *hint* and says so in its own docs; the engine
stays the authority at close time, so a wrong hint costs nothing but a second look.

**Unless a second client wants the same marker and you would rather state it once, skip
this.**

---

## A4 — `?status=` on `GET /reconciliations`  ·  **probably not worth it**

Also recorded with its counter-argument. The CLI's browse screen fetches every batch
unscoped, pages through them all, and slices per account client-side — deliberately, so
that moving the account cursor is instant with no request per keystroke
(`GET /reconciliations` is `created_at DESC` unscoped, `date_start ASC NULLS LAST,
created_at ASC` when `account_id` is given — `engine-spec.md`). A status filter would not
change that design, and `?account_id=` already exists. **Skip unless it is trivial and
you want the filter surface to be uniform.**

---

## A5 — the gap message names the fences, not the gap  ·  **a wording bug, cheap**

Not a feature request. `app/helpers/periods.py:370-377`:

```python
first_day = previous["first_day"]     # this window's FIRST day
covered_to = previous["last_day"]     # the previous window's LAST day
...
f"{covered_to} to {first_day} is not covered by any completed reconciliation ..."
```

With June closed at `2026-06-25` and August starting `2026-07-24`, the user is told:

> **2026-06-25 to 2026-07-24** is not covered by any completed reconciliation on this
> account — the days after 'June 2026' and before this period are sealed by nothing.

But `2026-06-25` **is** covered (it is June's last day) and `2026-07-24` **is** covered
(it is this period's first day). The uncovered days are `2026-06-26` to `2026-07-23`. The
sentence's second half is correct — "the days after X and before this period" — so the
message contradicts itself, and the figures a reader will copy into a date filter are
both off by one.

Suggested fix, whichever reads better to you:

- `f"The days between {covered_to} and {first_day} are not covered ..."` — makes the
  existing numbers exclusive, and is a one-line change; or
- report `covered_to + 1 day` and `first_day - 1 day` as an inclusive range, which is
  also what A2's fields should carry.

**Why the CLI cannot fix it:** its rule is that the engine's message is rendered
verbatim, never reworded — and rewording it client-side is exactly the prose-parsing A2
argues against. It currently ships this sentence as-is, to the user, with the wrong dates
in it.

---

## Summary

| # | Ask | Priority | CLI deletes on landing |
|---|---|---|---|
| A1 | `?sort=date_asc` on `GET /transactions` | **do this** | probe read, `unfiled_offset`, the page reversal, the one-page cap |
| A2 | gap's two dates as fields on `complete` | worth doing, after A1 | nothing — adds a count and a door |
| A3 | a window/coverage flag on transaction reads | skip unless convenient | the client-side `!` comparison |
| A4 | `?status=` on `GET /reconciliations` | skip unless trivial | nothing |
| A5 | gap message off-by-one wording | **cheap, please fix** | nothing |

**Nothing here blocks the CLI.** Everything above is shipped and usable as it stands;
these are the places where it is right for the wrong reasons, or right at a cost every
future client would pay again.
