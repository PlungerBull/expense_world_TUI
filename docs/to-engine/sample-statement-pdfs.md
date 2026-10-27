# Publish one made-up sample statement PDF per paper, so every client can test the statement upload

Raised 2026-10-27.

## Why

POST /v1/reconciliations/import reads the BCP papers, a savings account's (`Estado de Cuenta de
Ahorros`) and a Visa card's (`Estado de Cuenta Tarjeta Visa`). The contract describes each in
words: its rows, columns, period, balances and totals. It does not give the layout precisely
enough to build a PDF that the engine reads. A client's live tests cannot use a real statement
(this client's repo is public, and a statement holds the owner's money), so they have to build
made-up ones.

The terminal app's live tests built a savings paper the engine accepts, on contract
`46e2fdf6e11d7548`, by probing dry runs and reading the engine's `UNEXPECTED_LAYOUT` messages.
Almost none of what they needed is in the contract:

1. The title is exactly `Estado de Cuenta de Ahorros <word>` / `Estado de Cuenta Tarjeta Visa`,
   in that capitalisation.
2. The column header is exactly `FECHA PROC. FECHA VALOR DESCRIPCION CARGOS / DEBE ABONOS /
   HABER` (spaces collapsed). A word added before, inside or after it breaks the match.
3. Every page carries `n DE m`, a `MONEDA` line with `SOLES` / `US DOLARES` on the line under it,
   and `DEL dd/mm/yy AL dd/mm/yy`.
4. The page is read as a grid of fixed-width cells. The processing date sits at cell 14, the
   value date at 20 and the description from 26, up to 18 characters. An amount out ends at 67,
   an amount in at 86.
5. Days print as `05MAR`, with Spanish months (`SET`, `DIC`).
6. `SALDO ANTERIOR` is the table's first line, its amount in the in column, on page 1 only.
7. `TOTAL MOVIMIENTO` and `SALDO` each stand alone on their line, their amounts printed about
   2–5 pt off the label's baseline (on the same baseline the label is not found), under the
   header's `CARGOS` / `ABONOS`. Every page carries both labels; the amounts are on the last page
   only.
8. Lines closer than about 12 pt are read as one.

The **card** paper could not be built at all. Every made-up card PDF is refused with
`422 UNEXPECTED_LAYOUT`, `Page 1: it holds no column header.`. The engine matches the header
exactly, and the contract never prints it. About 225,000 candidate headers were tried (variants
of the processing date, purchase date, description, type and currency columns); all were refused.
So no client can test, live:

- a card's two halves closed by one paper;
- a card's half with no row closing empty;
- the card's undated fee lines dated the statement's last day;
- `NO_ACCOUNT_FOR_CURRENCY` for a card whose other-currency account is missing.

Each of the four clients would otherwise repeat this probing, and their made-up papers would break
silently whenever the reader changes.

## The ask

Publish one made-up sample PDF per paper the engine reads: a savings account's and a Visa card's.
Each holds invented names, numbers and amounts, adds up to its own totals, and is read by the
engine as is. Each should come with its rows as the engine reads them, so a client can check a
dry run against them. Put them where clients can fetch them through the engine or its published
contract (for example, linked from the operation's description), and keep them in step with the
reader: a change to the layout the engine reads changes the samples in the same release.

Better still, also state each paper's layout in the operation's description: the exact title and
column header text, where each column and amount sits, and the page furniture every page needs.
Then a client can make variants of the sample (another month, a future-dated row, a total that
does not add up) without probing.

## Done when

- A client fetches a savings sample and a card sample, and a dry run of each on an account with a
  statement code answers `200` with the rows the sample states.
- The contract states each paper's layout precisely enough that a client can change the sample's
  rows, dates and totals and still have the engine read it, or it names how clients make variants.
- The card sample has rows in both currencies and at least one undated fee line. A second card
  sample, or a stated way to vary the first, has no dollar row, so the empty half can be tested.

## What this client removes once it lands

The terminal app's live tests stop carrying their own probed copy of the savings layout (its
cell positions, title, header and page furniture). They build their papers from the published
samples or the stated layout instead, and they add the card tests the missing header blocks
today: both halves closed together, the empty dollar half, the undated fees, and the card's
missing other-currency account.
