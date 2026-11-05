# A statement PDF's dry run names the lines the close will flag

Raised 2026-11-05.

## Why

`POST /v1/statements/import` with `dry_run: true` is the preview: the owner reads it before
anything is written. It names the lines the close would take out (`taken_out`), but not the
lines the close would flag for review. Those come back only on the apply, in
`statement.balances[].review_lines` and `statement.not_covered[].review_lines`, because
`statement` is `null` on a dry run.

A flagged line is a ledger line in no statement, dated on a day the close reviews, that the paper
does not print. It is often a mistyped amount, or a purchase the bank books next month. The
preview is the one place to catch it before the month is completed; after the close, fixing it
means revert, fix, upload again.

## The ask

On a dry run, the response names the lines the apply's close would flag, exactly as the apply
would compute them, per currency, in the review list's order: the same lines the apply returns
in `review_lines`, with the same rules (the days reviewed, `@Opening` seeds never flagged, a line
in the draft never flagged, a currency the statement does not cover listed as `not_covered`
lists it). One way, for the engine to choose: a `review_lines` key on each entry of the
response's `balances`, plus the uncovered currencies' lines, present on the dry run and the
apply alike, `[]` when none.

## Done when

- A dry run of a PDF whose period holds a ledger line in no statement that the paper does not
  print names that line, under its currency, and writes nothing.
- The apply of the same PDF flags the same lines in `statement`'s `review_lines`.
- A dry run with nothing to flag names none (`[]`), and the dry run's other keys are unchanged.
- The contract states the new key under `POST /v1/statements/import` → **Response**.

## What this client removes once it lands

Nothing: the client has no workaround today. The preview shows only the lines taken out, and the
lines to review appear after the close. Once this lands, the preview lists them before the owner
confirms.
