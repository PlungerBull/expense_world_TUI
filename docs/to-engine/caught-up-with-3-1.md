# Caught up with contract 3.1: a bank is a typed code with a required last 4, and the sheet import makes what `create` lists (part 1, the contract side)

2026-11-14

## Covers

The hand-off of 2026-11-14 ("A bank is a code the owner types, every bank account has a last 4,
and the sheet import makes the accounts, categories and hashtags it lists"), contract `1.1` →
`2.0` → `3.0` → `3.1`, read in full. This is part 1: the client's contract checks and live tests.
Part 2, the account forms and the sheet import's review, follows as its own reply once those
screens are built.

Checked against the practice engine serving `3.1`: the client's whole live contract suite ran
green, 431 passed, with a test for each of the nine changes the hand-off lists. Among them:

- `IBK` and `IBK` again made with their last 4; `ibk`, `IB`, `IBKXX`, ` IBK` and `I8K` refused on
  the create, the edit and `make-account`.
- A missing or `null` last 4 refused on the create and `make-account`.
- `BANK_TAKES_NO_STATEMENT_CODE` on each field it is keyed on, and `LAST_NUMBER`.
- One apply with `create` making a bank account, a person, a cash account and an archived one,
  with categories and hashtags, each balance matching its rows.
- Four refused `create`s and rows, each leaving nothing made.
- `suggestion` on `BCP 5678`, `BCP5678`, `Interbank PEN` and a name with two runs of four digits.
- A dry run's key reused by its apply, and a dry run sent again running again, on all three
  routes.

## Done when, checked

- **No TUI code reads `ambiguous`, and the TUI's contract check passes against `3.1`:** worked.
  The client records `3.1`, and its fixtures match the import's answer, `suggestion` and `created`
  included.
- **The account forms make `IBK-4321` and refuse `ibk` and a missing last 4 with the engine's
  messages:** not yet; part 2. One difference to expect there: the bank field capitalises as the
  owner types, as the statement code field already does, so a typed `ibk` is sent as `IBK`.
  A malformed code such as `IB` is still refused in the engine's words.
- **A dry run of the owner's sheet shows each missing account prefilled from its suggestion, and
  one apply makes them and imports every row:** not yet; part 2, shown on a made-up sheet of the
  real one's shape before the official import.
- **Dry-run keys:** nothing in the client relied on a dry run's key. Every dry run and every apply
  is a write of its own, under its own key.

## Contract problems found

- **A numberless bank account is still described, though no request can make one since `2.0`.**
  `ACCOUNT_HAS_NO_NUMBER` (`POST /statements/import`) and `NO_NUMBER` (`PUT /accounts/{id}`) are
  still published. So is "To give a numberless account its first number, send `current_number`
  with `last4`". Can a bank account without a number still exist, from before `2.0`?
  - If not, the contract would drop these.
  - If so, it would say where one comes from.

  The client's live test of `ACCOUNT_HAS_NO_NUMBER` can no longer set one up, so it now cites the
  rule rather than driving it.

## Asks this closes

The contract side of both asks the hand-off answers. Part 2 closes their screen side.

- "A bank account's bank is a 3–4 letter code the user types, its last 4 is required, and only a
  bank `GET /banks` lists takes a statement code"
- "The sheet import suggests the accounts it is missing and makes the ones the user confirms, with
  its names and rows, in one write"
