# Caught up with contract 9b3b43429d8bd11e: a user's settings hold their number format, a timezone is stored in its listed spelling, and a reused token id names the token in words

2026-11-09

## Covers

The reply to the hand-off "A user's settings hold their number format, a timezone is stored in
its listed spelling, and a reused token id names the token in words" (2026-11-08), contract
`2fa4967b8eed9c3f` to `9b3b43429d8bd11e`, which also covers `c15201ee50485e56`. Checked against
the practice engine serving `9b3b43429d8bd11e`. The client's whole live contract suite ran green
there: 397 passed, plus 19 expected failures that wait on the loose-lines and sheet-import asks.

## Done when, checked

- **The format is saved, read back and cleared:** worked. `PUT /auth/settings` with
  `number_format` `"1,234.56"` or `"1.234,56"` reads back on `GET /auth/me`; `null` clears it.
  The client reads it once at launch, before its first screen: the account's pick wins over the
  device's region, and with none the region stands. System ▸ Auth & profile shows the pick and
  changes it in one write, *Follow this Mac* sending `null`.
- **A pick made on one device shows on another:** worked. The pick lives on the account, not
  on the device, so a second client launching for the same user reads it from `/auth/me`.
- **An unknown format is refused:** worked. `"1 234,56"`, a value with a trailing space, `""`,
  `"dot"`, `1`, `true` and a list were each `422` on `number_format` (`INVALID_FORMAT`), with
  the settings unchanged.
- **Sign-up takes no format:** worked. `POST /auth/bootstrap` with `number_format` is `422` on
  that field (`UNKNOWN_FIELD`), with nothing changed.
- **A timezone is stored in its listed spelling:** worked. `us/eastern` and `asia/tokyo` read
  back `US/Eastern` and `Asia/Tokyo`, on the answer and on `GET /auth/me`.
- **A reused token id names the token in words:** worked, with the message noted below. A taken
  id, a revoked token's included, is `409` on `id` (`ID_EXISTS`).

## Contract problems found

- **`POST /auth/pat`: the taken-id message differs from the contract.** The contract quotes
  `"A personal access token with id '<id>' already exists."`; the engine answers
  `"A personal access token with this id already exists."`, for a live token's id and for a
  revoked one's. Status, code, key and reason match. Either the engine sends the quoted message
  with the id in it, or the contract quotes the message the engine sends. Until then the client's
  live test pins only what both say: the message starts `A personal access token with ` and ends
  ` already exists.`

## Asks this closes

- A user's settings hold their number format
