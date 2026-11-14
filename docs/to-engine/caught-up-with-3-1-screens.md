# Caught up with contract 3.1: the account forms and the sheet import's review (part 2, the screen side)

2026-11-14

## Covers

The hand-off of 2026-11-14 ("A bank is a code the owner types, every bank account has a last 4,
and the sheet import makes the accounts, categories and hashtags it lists"). Part 1, "Caught up
with contract 3.1: a bank is a typed code with a required last 4, and the sheet import makes what
`create` lists (part 1, the contract side)", covered the contract checks and live tests. This
part covers the screens, built on `3.1` and run against the practice engine serving it.

## Done when, checked

- **The account forms make `IBK-4321` and refuse `ibk` and a missing last 4 with the engine's
  messages:** worked, with one difference that part 1 announced.
  - BANK is a typed code with no list. LAST 4 is required.
  - The statement code line shows only while BANK is a code `GET /banks` lists. An Edit that
    moves a coded account to a bank the engine reads no statements of sends
    `statement_code: null` with the move.
  - The engine's refusals show in its own words under the line they are keyed on.
  - **The difference:** the field capitalises as it is typed, as the statement code field does, so a typed `ibk` is sent as `IBK`
    and made (`IBK-2718` on the rehearsal). A malformed code such as `IB` still comes back in the engine's words.
- **A dry run of the owner's sheet shows each missing account prefilled from its suggestion, and
  one apply makes them and imports every row:** worked, on a made-up sheet of the real one's shape
  (38 rows: a card in soles and dollars on one sheet name, two savings accounts, cash, four
  people, two split purchases, eight opening balances, a row of zero, a closed Interbank account).
  - **The review:** `expense import sheet <file>` opens a review listing each sheet name with
    no account, filled from `suggestion`. Each row is set on the New account form, and the
    closed account is marked archived.
  - **The dry run and its question:** the dry run is sent with `create`, and the answer's
    counts come back as one question: "Ready: 9 accounts, 6 categories and 3 hashtags made;
    37 rows imported and 1 row of zero skipped." / "Among them 2 split transactions of 5 rows
    and 8 opening balances."
  - **The apply:** one apply of the same body made every account under its built name
    (`BCP-3146`, the BCP ones with their statement code), the people as people and `IBK-2718`
    archived, and imported every row.
  - **The balances:** all 12 account-and-currency balances equal the sheet's totals, and each
    split purchase is one split transaction.
  - **Refusals:** a refusal keyed `create.<list>.<i>.<field>` marks its row with the engine's
    words.

## Contract problems found

None beyond part 1's question about numberless bank accounts. On the made-up sheet the review made a
`SALDO INICIAL` category no transaction uses. The ask "The sheet import says which names only
opening balances use, so a client never makes a category or hashtag no transaction needs", already
handed over, covers it.

## Asks this closes

The screen side of both asks the hand-off answers:

- "A bank account's bank is a 3–4 letter code the user types, its last 4 is required, and only a
  bank `GET /banks` lists takes a statement code"
- "The sheet import suggests the accounts it is missing and makes the ones the user confirms, with
  its names and rows, in one write"
