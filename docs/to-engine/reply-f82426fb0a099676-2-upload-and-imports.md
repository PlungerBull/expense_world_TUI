# Caught up with contract f82426fb0a099676: the terminal app's statement PDF upload, bank download and sheet import send an account holding its currencies (part 2 of 7)

2026-10-30

## Covers

`e020782e3579d011` → `f82426fb0a099676` (`07475793a38b47b4`, `d5241e52676b19f9`,
`2d7db5f914b565d9`, `b54580104fce4fde`, `394b3a9034b36d98`, `ba0f857bc43b95ce`,
`02fb846290642261`, `4d57bb4f05ecc3b3`, `4329913878f62787`, `3d0afdaa03d87d5c`,
`7aec8f6ed9928caf`, `f82426fb0a099676`), your hand-off of 2026-10-29, "An account holds its
currencies: every route names an account and a currency code; holders are gone": its part on the
statement PDF upload, the bank download and the owner's sheet import. The terminal app's
statement screens (the list of statements, creating one, ticking lines in and out, completing,
reverting, deleting) moved from this part to part 7, which redraws them for one statement per
account; until then they still use the old shapes. Its live contract suite is parts 3 to 5.

## Done when, checked

All checked on 2026-10-30 against the practice engine, on a practice account holding soles and
dollars with a statement code, and on a soles-only account.

- **"A statement is the account's, with a starting and ending balance per currency it covers,
  and the PDF upload closes it":** worked for the PDF upload. Your sample `card` PDF, read from
  `GET /v1/statements/samples/card` and sent for the two-currency account, previewed as a new
  statement with one balance line per currency (`PEN -1,250.00 → -379.59`,
  `USD -80.00 → -104.98`) and 9 new rows, and its apply completed the statement on that account,
  each currency's difference `0`, `not_covered` empty. The same PDF sent for the soles-only
  account was refused, `CURRENCY_NOT_HELD` on `account_id`, shown in your words. The app shows a
  balance line only for each currency your answer holds, and counts the lines a close flags from
  each balance's `review_lines` and each `not_covered` entry's. The statement screens are part 7's.
- **"A transaction names an account and a currency it holds; one in a currency the account does
  not hold is refused, nothing written, and the app shows why":** worked on the bank download
  and the sheet import. The download sends the account alone and files each row under the
  currency of its own `Moneda`: a file of soles and dollar rows previewed each row with its
  currency and imported three rows on the account; a dollar row sent to the soles-only account
  was refused on the dry run and the apply, `CURRENCY_NOT_HELD` on `rows.2.account_id`, nothing
  written. The sheet import sends one `names.accounts` entry per account name, `{name,
  account_id}`; its create step made one account per missing name holding the currencies its
  rows use; the apply wrote the rows, and sending the sheet again matched them all. A name mapped
  to an account lacking one of its currencies was refused, `CURRENCY_NOT_HELD` on
  `names.accounts.0.account_id`, in your words; two names mapped to one account were accepted.
- **"No request in the TUI sends a `/holders` route, `POST /accounts/{id}/move`, `?holder_id=`
  or a per-currency id":** worked for the PDF upload, the bank download and the sheet import:
  each sends the account's id alone. The statement screens' requests follow in part 7.

## Contract problems found

- **A refusal of the PDF upload stated outside its "Concurrency" part.** On
  `POST /statements/import`, the `409 CONCURRENT_CHANGE` on `category_id` or `hashtag_ids`, when
  the pending category or hashtag a created row files under is deleted while it is being
  created, is stated in the paragraph on filing created rows, under no heading of its own, while
  "Concurrency" lists only the matched line (`rows.<place>`) and the draft (`file`). A client
  reading "Concurrency" alone misses it. Worth naming it there too.
- **No sample PDF for a currency the paper does not cover.** Your `card-no-dollars` sample
  prints a non-zero dollar balance, so it is refused on a soles-only account rather than closing
  a statement that leaves dollars out. A sample whose paper shows dollars at zero with no row
  would let a client prove a statement that covers soles alone, through the upload.

## Asks this closes

None. "An account holds its currencies: the holder becomes the account, and each account becomes
one of its currencies" closes with part 7.
