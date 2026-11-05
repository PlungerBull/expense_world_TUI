# Send each transaction's calendar day with it

Raised 2026-11-05.

## Why

A transaction's `date` comes back as a UTC datetime (contract: "Base Conventions", "Datetime
inputs"), while the engine counts the transaction on its calendar day in the user's
`display_timezone` (contract: "Base Conventions", "Calendar days"): sealed periods, statement
windows, day filters, monthly reports and conversion all use that day. A client that lists
transactions by day has to work out that day itself. The obvious shortcut, the first ten
characters of `date`, is wrong for a user west of UTC: in Lima (UTC−5) a transaction timed
after 19:00 shows as the next day, even though the engine counts it on its own day. A row dated
by day alone (00:00 in the user's time zone) happens to show correctly, which hides the bug.

Each client could convert the time with `display_timezone` itself, but then four clients (the
terminal app, web, iOS, and any later one) each carry their own copy of the engine's day rule,
including the fallback ("a stored zone the engine does not recognise is read as UTC"), and a
client that gets it wrong shows a different day from the one its filters and reports count.

## The ask

Every answer that carries a transaction's `date` (`GET /transactions`, `GET /bank-lines`, a
single transaction's read, and the answers of the creates and updates that return a
transaction) also carries that transaction's calendar day, a bare `YYYY-MM-DD`, worked out the
same way the engine counts it everywhere else: in the user's `display_timezone` at the time of the
request, with the same fallback for an unrecognised zone. The contract names the field, says it
is read-only, and says it is the day every day filter, sealed period, statement window and
report counts the transaction on.

If other answers show a row by its day (an activity entry, for example), they carry the same
field under the same name.

## Done when

- A transaction dated `2026-11-04T23:30:00-05:00` for a user in `America/Lima` comes back with
  `date` `2026-11-05T04:30:00Z` and its day `2026-11-04`.
- Changing `display_timezone` changes the day on the next read, with no write.
- The day a transaction carries is always the day a day filter (`?date_from=` / `?date_to=` given
  as days) finds it on.

## What this client removes once it lands

The client stops cutting the first ten characters off `date` to show a transaction's day, and
shows the engine's day instead on every list and form that shows one.
