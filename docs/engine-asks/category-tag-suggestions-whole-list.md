# The engine sends a category's tag suggestions as one whole list: the category's own tags first, then every other tag

Raised 2026-10-12.

## Why

When a person has picked a category and reaches for a tag, every client shows the same list:
the tags that category's transactions already use, most-used first, then a divider, then every
other tag the person owns. Nothing is hidden, because any tag may go on any category.

Today the engine answers only the first half. `GET /v1/categories/{category_id}/hashtags`
returns the tags the category has used and leaves out the rest, so each client has to read
`GET /v1/hashtags` as well, subtract one list from the other, and decide the order of what is
left. Three clients (terminal, web, iOS) would each write that merge and each pick an order, and
the same person would see three different lists. The order of a list is the engine's to decide.

## The ask

One read that answers, for one category, **every tag the person can put on a transaction**, in
two groups, each already in its final order:

1. **Used with this category** — exactly what `GET /v1/categories/{category_id}/hashtags`
   returns today, under the same rules: `uses` counts transactions, ordered by `uses`
   descending then the hashtag's creation time, oldest first; removed tag links, deleted
   transactions and deleted hashtags excluded.
2. **Every other tag** — the rest of the person's hashtags, in the order `GET /v1/hashtags`
   lists them, none of them repeated from the first group.

The answer tells the client where the first group ends (two named lists, or one list with a
marker on each row; the engine coders choose). Each row carries at least `id` and `name`.

It is whole and unpaged, like the existing route: the hashtag create cap bounds it.

A category nobody has tagged yet answers with an empty first group and every tag in the second.
A category that does not exist, is deleted or belongs to someone else stays a `404`.

Whether this is a new route or a declared parameter on the existing one is the engine coders'
call. If the existing route keeps its present answer, clients that want only the used tags are
not disturbed.

## Done when

- The published contract (`/openapi.json`) states the read, its two groups, the order inside
  each, the exclusions, and that the list is whole.
- For a category with tagged transactions, the first group equals today's
  `GET /v1/categories/{category_id}/hashtags` answer row for row, and the two groups together
  hold exactly the hashtags `GET /v1/hashtags` lists, each once.
- For a never-tagged category, the first group is empty and the second holds every tag.
- Tagging a transaction, or deleting one, moves a tag between the groups on the next read.

## What the CLI removes once it lands

Nothing is built on the client yet; this ask is what keeps it that way. The terminal client
does not write the second read of the hashtag list, the subtraction of one list from the
other, or a sort of its own for the lower group. Its tag picker draws the engine's answer in
the order it arrives.
