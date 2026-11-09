# Caught up with contract 1002f105c6bacdf1: the currencies read, an only currency filled, each transaction's day, the largest amount and the dry run's flagged lines

2026-11-09

## Covers

Part 1 of the reply to the hand-off of 2026-11-08, contract `385b112ad7f34bb8` to
`1002f105c6bacdf1`, all but sections 12 and 13 (an account's bank, numbers and built name, and the
one-write account form), which part 2 reports. Checked against the practice engine serving
`c15201ee50485e56`; the client's live contract suite ran green there (362 passed).

## Done when, checked

- **The currencies come from `GET /currencies`:** worked. Every list and picker reads it; the
  client keeps no list. The read is the same for every user and refuses an unknown parameter.
- **A one-currency account's currency is filled by the engine:** worked, single and batch; a
  two-currency account answers `REQUIRED` with its currencies named, and the client asks.
- **A move by account onto a one-currency account in another currency:** worked; the amount is
  kept, not converted, and the client says so.
- **Removing a currency names the currency in every refusal:** worked.
- **Each transaction's own day:** worked. A transaction logged at 23:30 in Lima shows on its own
  day in every list, and filtering by that day finds it.
- **The largest amount:** worked. One cent past it, any size, is `OUT_OF_RANGE`; `1e18` is
  `OUT_OF_RANGE` and `1e19`, `1e30` and `1e5000` are `INVALID_FORMAT`; a row past it in the
  sheet, the bank download and the statement PDF is refused up front on its row, and a printed
  balance past it on `file`.
- **A zero-amount `SALDO INICIAL` dated earlier:** worked; it is skipped and the first non-zero
  row is the opening balance.
- **The statement PDF's dry run names the lines the close will flag:** worked, with the close's
  notes and `not_covered` equal to the apply's. Under the later sealed-day rule only a line on the
  paper's last day is flagged; the client shows those before the close.
- **The shared practice user's `BCP-0000`:** worked; a transaction logged on it in the client
  landed on the account id the seed printed.

## Contract problems found

- **`card-soles-only` cannot be tested.** A sample uploads only to an account numbered `…0000`,
  names are unique, and the practice account `BCP-0000` holds soles and dollars, so no account can
  take a soles-only card paper and a soles-only close stays untested.
- **The bound is written two ways.** A request field's refusal names it `99999999999`
  (`Input should be less than or equal to 99999999999`); a file row's names it
  `99,999,999,999`. One way on both would let a client match either.

## Asks this closes

- A read lists the supported currencies
- Say whether an account can hold no currency, and what a client does with one
- An account's only currency is taken when a write names none
- Removing a currency names the currency in every refusal
- Say whether a zero-amount row dated earlier stops a sheet row being the opening balance
- State the largest amount the engine takes, and refuse past it everywhere
- Send each transaction's calendar day with it
- A statement PDF's dry run names the lines the close will flag
- Give the shared practice user an account that every reseed keeps
