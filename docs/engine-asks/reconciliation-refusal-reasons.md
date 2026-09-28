# Reconciliation refusals say which rule was broken in a published, stable way

Raised 2026-09-27 by the CLI client.

## Why

`POST /v1/reconciliations` and `PUT /v1/reconciliations/{reconciliation_id}` refuse a period in
two ways the contract describes only by the field they name:

- the end day is before the start day: a `422` naming `date_end`;
- the period overlaps another reconciliation on the same account: a `422` naming `date_start`.

A badly formatted day (the "Date inputs" rule) is also a `422` on those same fields. So a
client that wants to tell the person *why* the period was refused ("ends before it starts",
"overlaps another period") can only match the error's message wording, which the contract does
not publish. Any rewording on the engine side silently breaks that, and web and iOS would each
have to copy the same fragile match.

`POST /v1/reconciliations/{reconciliation_id}/complete` refuses in two ways, both under
`fields["transactions"]`: the batch has no transactions ("At least one transaction must be
assigned."), and transactions dated inside the period are not assigned to any reconciliation.
Those texts are published, but they are prose, not reasons: telling the two apart still means
matching words, and any rewording breaks it.

## The ask

Each of these refusals carries a stable, machine-readable reason that the contract lists, so
clients switch on the reason and never on message wording. For example, a distinct
`error.code` per refusal (`period_inverted`, `period_overlaps`, `period_empty`,
`period_has_unassigned`), or a per-field reason alongside the `fields` text. Whatever the
shape, it is documented on each operation in `/openapi.json`, and it appears in the contract's
change log when it lands.

## Done when

- The inverted period, the overlapping period and the badly formatted day each produce a
  different, documented reason on `POST` and `PUT /v1/reconciliations`.
- The two `complete` refusals (no transactions in the batch; unassigned transactions in the
  period) each have a different, documented reason.
- The reasons are listed in `/openapi.json` on the operations that return them, and an engine
  test pins each one.

## What the CLI removes once it lands

Its matching on the refusal messages' wording to pick a hint for the person. It switches on the
published reason instead.
