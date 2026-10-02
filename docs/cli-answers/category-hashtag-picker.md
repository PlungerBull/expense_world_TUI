# A category ranks the hashtags used with it

Shipped 2026-09-20 · ➕ additive · contract `GET /categories/{id}/hashtags`

## What changed

`GET /categories/{id}/hashtags` lists the hashtags used on that category's transactions, most used first. `uses` is a transaction count and is safe to display.

## What the CLI does

The hashtag picker lists the ranked tags first, then the rest of `GET /hashtags` after them.

## Done when

The CLI's picker uses the ranking.
