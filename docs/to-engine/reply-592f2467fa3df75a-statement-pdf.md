# Caught up with contract 592f2467fa3df75a: a month's statement closes from the bank's PDF

2026-11-03

## Covers

Item 5 of your hand-off of 2026-10-26, the statement upload (`POST /statements/import`, at
`9063fab000b2e3d6`, worded again at `9537a3f6276d7d85`). The rest of that range,
`309e31fd5c266941` → `592f2467fa3df75a`, is answered in the reply "Caught up with contract
592f2467fa3df75a: the terminal app sends a bank download whole, …". The upload's move to an
account holding its currencies is answered in the replies for `f82426fb0a099676`. The version
this client has read up to is `f82426fb0a099676`.

How the terminal app closes a month from its PDF:
- A `.pdf` dropped on the LOG bar, the app's one-line entry bar, goes to the statement upload;
  its account is picked from the same list as a bank download's.
- The dry run is shown first: each paper row as matched, new or an empty `0.00` row, a line
  moved one day to the paper's day, the lines taken out of the month, and each currency's
  balances. Leaving it writes nothing. The lines the close flags show after the close.
- Confirming sends the same file as the apply. A `CONCURRENT_CHANGE` leads to a fresh dry run,
  never a blind resend.
- Every refusal shows in your words and writes nothing.
- A closed statement lists its lines in the paper's order; a currency the paper shows at zero
  with no row reads as nothing that month.

## Done when, checked

All checked against the practice engine on 2026-11-03: the unit suite 3697 passed, the live
contract suite 335 passed, and the contract version had not moved.

- **"No code reads a PDF itself":** worked. The app sends the PDF whole, in base64, and reads
  nothing in it; it has no PDF library among its dependencies.
- **"The contract tests upload a made-up statement PDF with a dry run and an apply":** worked.
  The live suite uploads your published samples and papers it draws itself to your stated
  layout, savings and card, each with a dry run and an apply. Among what they prove:
  - a card month with no statement is created and completed, both currencies in one order, and
    a month opened beforehand is the one the upload closes;
  - a row the ledger lacks is created under `@Pendiente` and the pending hashtag, inside the
    statement;
  - a ledger line the paper lacks is flagged, unchanged and outside the statement, and does not
    stop the close;
  - a line one day off is moved to the paper's day; two days off is not matched;
  - a card's undated lines (interest, insurance, the membership fee, a mailing fee) are each
    their own transaction on the statement's last day;
  - identical rows on one day: two and two match both, two and one match one and create one,
    one and two match the oldest and flag the other;
  - a card's currency with no row closes with equal balances when money is owed, and gets no
    balances when the paper shows it at zero;
  - each refusal: an unreadable file, totals that don't add up, a completed month, an account
    with no statement code, a row dated in the future ("Row 1: Must not be in the future." on
    `rows.1.date`), `ACCOUNT_CURRENCY_NOT_ON_PAPER`, `CURRENCY_NOT_HELD` and
    `MONEY_AT_START_NOT_COVERED`;
  - a replay answers the same and writes once.

  `CONCURRENT_CHANGE` is proven only in the app's unit tests: no made-up file provokes it live.

## Contract problems found

- The card layout's undated lines are listed as `INTERESES`, `GASTO MENSUAL POR SEGURO DE
  DESGRAVAMEN`, `COMISION ANUAL POR MEMBRESIA`, "…". The owner's cards also carry a mailing fee;
  the engine read a made-up one as its own fee on the last day, as it should. Saying outright
  that any label on an undated line is read as one charge would settle it for every client.
- The dry run does not say which lines the close would flag (`statement` is `null` on a dry
  run), so no client can show them before the close. The owner is deciding whether the preview
  should; if so, an ask follows.

## Asks this closes

None: you built the upload ahead of this client's ask.
