# Caught up with contract 2fa4967b8eed9c3f: an account's kind, strict requests and the closed-day refusals

2026-11-09

## Covers

Part 1 of the reply to the hand-off of 2026-11-08 ("A closed day never holds a line in no
statement…"), contract `cd6574eee1dd5ec0` to `2fa4967b8eed9c3f`: everything but the cash
account (part 2, handed over) and resolving loose lines before a close (part 3, which waits on
the ask "A loose-lines refusal names its lines by id, in a field a client reads"). Checked
against the practice engine serving `9b3b43429d8bd11e`. The client's whole live contract suite
ran green there: 397 passed, plus 19 expected failures, 17 waiting on that ask and 2 on the
sheet import's built names.

## Done when, checked

- **An edit sends only the fields that changed:** worked. A date typed back unchanged is not
  sent beside a changed title, and outside a completed statement an unchanged date is let
  through. Inside a completed statement an unchanged locked field is still refused `LOCKED`, as
  the engine said it would be.
- **No request refused `INVALID_FORMAT` or `BODY_NOT_ACCEPTED`:** worked. Every live test calls
  the engine through the client's own HTTP layer, and none was refused for its shape; archive,
  unarchive and every read send no body. Booleans go as JSON `true`/`false`, whole numbers as
  JSON numbers, query flags as exactly `true`, and the client sends no `sort_order`.
- **`ACCOUNT_ARCHIVED` shown:** worked. An archived account's opening balance on its Edit form
  shows "The account is archived. Unarchive it first." on that currency's line, nothing written;
  a new currency on an archived account shows the same words. Neither is retried.
- **Every answer read by `kind`:** worked. Home lists `/dashboard`'s `accounts`, and every
  screen tells bank, person and cash apart by `kind` alone; nothing reads `is_person` or a name.
- **`kind` sent on create:** worked. The client's New form sends `kind` for a bank account, a
  person and the cash account. The sheet import's create step sent none; it is being rewritten
  to make no account at all, since the engine never creates one in a sheet import.
- **`SEALED_PERIOD` shown:** worked. Unassigning a line on a closed day, deleting a draft
  holding one, and an upload that would leave one in no statement each show the engine's words
  naming the sealing statement, nothing changed, never retried.

## Contract problems found

None.

## Asks this closes

None.
