# Name a flagged line's twin wherever the flagged lines are read

Raised 2026-10-28.

## Why

On a holder with a statement code, the advice for a flagged line (`POST /statements/{id}/complete`,
*What a client does with a flagged line*) starts from its twin: the line `POST /statements/import`
created from the paper's row. Keeping the paper's line deletes the flagged one; keeping the
owner's deletes the twin, fixes the owner's line to the row's day and total, and uploads the paper
again.

A client can only follow that advice if it knows which line is the twin. Today only the upload's
own answer says so, through the row's `near_misses` and `bank_line_id`. The flagged lines are read
later, page by page, from `GET /bank-lines?unassigned_in_period_of=<id>&sort=statement` and its
count, often in another session or on another device, and nothing on that read names a line's
twin or the paper's row. A client would have to match lines itself, by amount and day, which is
the engine's rule to apply, and every client would apply it a little differently.

## The ask

On the review list (`GET /bank-lines?unassigned_in_period_of=<id>`), give each flagged line its
twin when it has one: the id of the line the upload created from the paper's row it nearly
matches, and that row's day and total, or `null` when the paper prints no such row. One field per
line, on the read every client already makes, so the two paths the advice names are offered only
where they apply.

## Done when

A client reading a completed statement's flagged lines, in a later session, can tell for each one
whether the paper printed it, and if so which line is its twin and what day and total the paper
gives it, with no other read.

## What this client removes once it lands

Nothing it builds today: the terminal app's flagged-lines screen offers "keep the bank's" and
"keep mine" only once it can name the twin from the engine. Without this, the screen can only
show the advice as words.
