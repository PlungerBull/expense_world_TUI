# A bank line's read says which of its fields a write would refuse

Raised 2026-10-25.

## Why

A line editor shows a line's fields at the top (title, date, account, operation code) and every
part below (amount, category, hashtags, description). The fields the engine would refuse are
shown read-only before the person types, so nobody types a change that can only come back
refused. The editor needs that for three kinds of line:

- **A line in a completed reconciliation:** its title, date, account and operation code are
  locked, and its parts must keep the line's total. On a line of one part, that part's amount is
  the total, so it is locked too. Parts can still be added, dropped and their amounts moved
  between them.
- **A line on an archived account:** only its parts' category, hashtags and description change,
  and a title or operation code still empty may be filled once.
- **A line holding an opening balance:** its account, category and hashtags never change.

Today a client learns none of this from the line. `GET /v1/bank-lines/{id}` names each part's
`reconciliation_id` but not whether that reconciliation is completed, so the client has to read
`GET /v1/reconciliations/{id}` for every line it opens. Then it has to copy three of the engine's
rules (*Field locking*, *Archived accounts*, *Opening balances stay put*) to work out which
fields they lock. Every client (terminal, web, iOS) would copy the same rules. A copy drifts the
day the engine changes a rule, and the person then sees a field as editable that the engine
refuses, or the other way round.

## The ask

`GET /v1/bank-lines/{id}`, and each row of `GET /v1/bank-lines`, say what a
`PUT /v1/bank-lines/{id}` would refuse on the line as it stands, by the same rules the write
applies:

1. **The line fields a write would refuse**: the ones of `title`, `date`, `account_id`,
   `operation_code` and `reconciliation_id` that would be refused if sent (for example a
   `locked_fields` list, `[]` when none). A title or operation code that is still empty and may
   be filled is not listed.
2. **Whether `parts` may change the line's total**: false inside a completed reconciliation,
   where the parts must add up to the current total.
3. **Whether parts may be added or dropped**, and **for each part, the fields a write would
   refuse on it** (`amount_cents`, `category_id`, `hashtag_ids`, `description`): for example an
   opening balance's `category_id` and `hashtag_ids`, or every part field but the categorisation
   on an archived account's line.

The exact shape is the engine's call. What matters is that a client reads it off the line and
never derives it.

## Done when

- A line in a completed reconciliation reads its title, date, account and operation code as
  refused, its total as kept, and parts as addable and droppable. Reverted, the next read says
  none of it.
- A one-part line in a completed reconciliation reads that part's amount as refused.
- An archived account's line reads every line field and every part's amount as refused, and
  each part's category, hashtags and description as open. A title still empty is not refused.
- An opening balance's line reads its account, and its part's category and hashtags, as refused.
- Every refusal the read announces is the one the write gives, and nothing the read leaves open
  is refused as locked.

## What this client removes once it lands

The line editor reads no reconciliation when it opens a line. It keeps no copy of which fields a
completed reconciliation, an archived account or an opening balance locks: it shows read-only
what the line's read names.
