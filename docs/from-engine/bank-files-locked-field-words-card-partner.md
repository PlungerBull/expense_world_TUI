# The engine reads the bank's files and the owner's sheet, a bank PDF closes its statement, a locked field says why, and a card account names its other account

Shipped 2026-10-26 · ⚠️ breaking · contract `309e31fd5c266941` through `592f2467fa3df75a`

Answers:
- "A bank line's edit limits say why each field is locked, in words" (raised 2026-10-25)
- "The account read names a card's other account" (raised 2026-10-25)
- "Probes on the practice engine clean up after themselves" (raised 2026-10-25)
- "The practice engine seeds a second practice user whose own category and hashtag hold the reserved
  names" (raised 2026-10-25)

The bank files (items 1–6 below) answer no ask: they are the owner's own work. They also set up the
TUI's coming ask to upload a statement PDF, whose route now exists.

## Each ask

- **A locked field says why, in words:** done as asked. Each entry is `{reason, message}`, and the
  message is the write's own refusal message, word for word (item 7).
- **The account read names a card's other account:** done, as the id only:
  `statement_partner_id`, not the name and currency the ask offered. A reference to another resource
  carries only its id; read the account it names (item 8).
- **Probes clean up after themselves:** done another way. The engine's checks run as a practice user
  of their own, so they never write to the shared practice user (item 9).
- **A second practice user holds the reserved names:** done as asked (item 9).

## What changed

Read `x-changelog` for every version from `309e31fd5c266941` to `592f2467fa3df75a` (the last a
wording-only edit of the `edit_limits` example), and the live
sections it names. In short:

1. **`POST /transactions/import` takes the bank's Excel download itself** (breaking, `309e31fd5c266941`).
   The client no longer reads the file.
   - Before: `{"dry_run": true, "rows": [{"id": "…", "account_id": "…", "date": "…", "amount_cents": -1250, "title": "…", "operation_code": "…"}]}`
   - After: `{"dry_run": true, "account_id": "<the account the download is from>", "file": "<the .xlsx in standard base64, at most 5 MB decoded>"}`
   - Sending `rows` is now `422` `UNKNOWN_FIELD`. `ZERO_AMOUNT` and `ID_EXISTS` are no longer sent by
     this route.
   - The engine mints the id of every transaction it creates and answers it as `transaction_id`. A
     replay under the same key answers the same ids.
   - Each answer row carries `row`, the spreadsheet row number with `2` the first data row, in
     place of `id`. Every refusal of a row is keyed `rows.<row>.<field>`.
   - New outcome `skipped`, for a row of `0`, counted in `counts.skipped`.
   - A card's download sends its rows in the other currency to the card's other account.
   - Tax and account-fee rows (`IMPUESTO ITF`, `MANT. CUENTA`) carry no operation code, so their
     reused numbers are never duplicates.
   - New reasons: `UNREADABLE_FILE`, `UNEXPECTED_LAYOUT`, `NOT_WHOLE_CENTS` and
     `NO_ACCOUNT_FOR_CURRENCY`.
2. **`POST /transactions/import-sheet`** (new, `0f7cdbe45cece354`) brings in the owner's own
   spreadsheet: `{"dry_run": bool, "file": "<base64>", "names": {...}}`.
   - The dry run lists every account, category and hashtag name the sheet uses, each with a
     `proposed_id`. The apply requires `names`, the confirmed table from each name to an id the
     client chose. The engine never looks a resource up by name.
   - New reasons: `NAME_NOT_MAPPED`, `NAME_NOT_IN_FILE` and `CURRENCY_MISMATCH`.
3. **A closed statement's last day stays open until the next statement is closed** (`e244c09829b443b7`).
   - A completed reconciliation seals every day of its period but the last.
   - The last day seals once the reconciliation beginning the day after is completed too.
   - Until then, a new row on that day is no longer refused (`SEALED_PERIOD`).
4. **The close flags instead of refusing** (breaking, `e244c09829b443b7`).
   - `POST /reconciliations/{id}/complete` no longer refuses a statement while lines dated in its
     period are in no reconciliation: `UNASSIGNED_IN_PERIOD` is sent by no operation.
   - The answer, and its `twin`, now carry `review_lines`: the ids of the bank lines the close
     flagged for the owner to look at, `[]` when none.
   - `GET /bank-lines?unassigned_in_period_of=` lists exactly those lines.
5. **`POST /reconciliations/import` closes a statement from the bank's PDF** (new, `9063fab000b2e3d6`):
   `{"dry_run": bool, "account_id": uuid, "file": "<the BCP statement PDF in base64, at most 5 MB>"}`.
   For a card, either of its two accounts will do.
   - The engine reads the paper and checks it against the paper's own totals (`TOTALS_MISMATCH`).
   - It creates the month's statement, both halves of a card with ids it mints, or fills its draft.
   - It matches each paper row to a ledger line by day and amount.
   - It creates each row the ledger lacks under `@Pendiente`, a fee or interest dated on the last
     day.
   - It takes out of the draft every line the paper does not print.
   - It places every line in the paper's order, then completes the statement, both halves of a card
     in one write.
   - A card half with no row on the paper still closes, empty. It is the one reconciliation that
     completes with no transaction.
   - The dry run answers the same shape and writes nothing. Each row carries its `outcome`
     (`matched`, `new`, `empty`) and its `near_misses`, the lines one day off with the same amount,
     never paired.
   - A completed statement is `409` `RECONCILIATION_NOT_DRAFT`: revert it first.
6. **Identical lines are claimed in the order they were made**, in all three imports: the line whose
   first transaction was created first, then the lowest `line_code`.
7. **A locked field says why** (breaking, `f7a0a0bbcfe62975`). On every route that answers a bank
   line, each entry in `edit_limits.locked_fields` and in each part's `locked_part_fields` is an
   object.
   - Before: `"locked_fields": {"title": "LOCKED"}`
   - After: `"locked_fields": {"title": {"reason": "LOCKED", "message": "Locked by completed reconciliation."}}`
   - The six sentences: `LOCKED` "Locked by completed reconciliation."; `ACCOUNT_ARCHIVED` "The
     account is archived. Unarchive it first."; `OPENING_BALANCE_ACCOUNT_FIXED` "Must not move an
     opening balance to another account."; `SPLIT_TOTAL_MISMATCH` "The parts must add up to the
     line's total."; `OPENING_BALANCE_CATEGORY_FIXED` "Must not move an opening balance out of the
     opening-balance category."; `OPENING_BALANCE_NOT_TAGGED` "Must be empty: an opening balance
     carries no hashtag."
   - The writes' wording changes to match. On `PUT /bank-lines/{id}` and `PUT /transactions/{id}`,
     a field refused because of one part no longer starts "Part <id> of this bank line is the
     cause: "; it reads its rule's own sentence, and the top-level `message` names the part. A
     part's `amount_cents` refused `SPLIT_TOTAL_MISMATCH` reads "The parts must add up to the line's
     total."; the refusal on `parts` still states both totals.
8. **`statement_partner_id` on every account answer** (additive, `8604c83b03c1302b`): `GET /accounts`,
   `GET /accounts/{id}` and every write's answer.
   - It is the id of the other live account that `twin` on `POST /reconciliations` accepts for a
     reconciliation on this one: a card's account in the other currency.
   - It is `null` with no statement code, when no other live account holds the code, for a person,
     and while either account is archived.
   - It moves on the next read when a code is set, changed or cleared, or an account archived,
     unarchived or deleted.
   - A card's file sent to `POST /transactions/import` or `POST /reconciliations/import` puts its
     other-currency rows on the account it names.
9. **Practice users** (no contract change). The engine's practice-user seed, run from the engine's
   repo, on `expense_world_test`
   seeds three users:
   - the TUI's shared practice user (`00000000-0000-4000-8000-00000000c11e`), unchanged, its key
     printed as `EXPENSE_PAT=`;
   - the reserved-names practice user (`00000000-0000-4000-8000-00000000c12e`), its key printed as
     `EXPENSE_RESERVED_PAT=` on the same run. It holds its own categories `@Pendiente` and
     `@Opening` and its own hashtag `Pendiente`, and no system category or pending hashtag. Every
     reseed with `--force` empties its books and writes those three back;
   - the engine's own practice user, which every engine-side check runs as. It never touches the
     TUI's two users.

## How it was checked

Items 1–6 on the practice engine, contract `9063fab000b2e3d6`, with the owner's real statements,
downloads and sheet:

- The full engine suite passes.
- All 62 statement PDFs read and pass their totals check: 42 current-account and 20 card.
- All 25 Excel downloads read. A card's download lands on both card accounts. A zero row is skipped
  and listed.
- On top of the downloads, the September 2026 soles PDF creates its 9 missing rows, matches the 56
  already there and completes with difference zero, every line in the paper's order. The September
  card PDF closes both halves in one write and flags the two dollar purchases it does not print.
- The owner's January–February example holds on a current account and on a card, through every write
  that creates or moves a row. After January closes, 15 January is refused and 31 January allowed.
  After February closes, 31 January and 1 February are refused and 28 February allowed.
- The owner's whole sheet, 4,191 rows, imports in one apply in 3.6 s. All 62 PDFs then close their
  statements, every difference zero, the slowest in 0.8 s. 2,270 of the sheet's 2,275 hand-typed
  statement codes match the engine's; the other 5 are mistakes in the sheet.

Items 7–9 on the practice engine, contract `8604c83b03c1302b`, each of the asks' **Done when**:

- The full engine suite passes.
- Every field `edit_limits` names comes with its code and its sentence, for all six reasons, on
  line fields and part fields. For each reason, the read's sentence equals the write's `message` on
  that field (65 checks). The live contract describes the sentence beside the code.
- Each account of a card reads the other, on the list and by id. These read `null`: no code, a code
  no other account holds, a person, an archived account, and the live account whose partner is
  archived. A code change, a cleared code, an archive, an unarchive and a delete move the field on
  both accounts (83 checks). `twin` accepts exactly the account named. The contract states the
  field, when it is `null`, and that it names exactly what `twin` accepts.
- The engine's checks ran as its own practice user. The shared practice user's rows were identical
  before and after; only its key was reissued, by the seed's `--force`.
- After `--force`, the reserved-names user holds exactly its three rows. As that user:
  - `POST /transactions` with a category and no `hashtag_ids` → `409` `RESERVED_NAME_HELD` on
    `hashtag_ids`;
  - with a hashtag and no category → `409` on `category_id`;
  - `POST /accounts/{id}/opening-balance` → `409` on `category_id`;
  - `PUT /bank-lines/{id}` with `parts` leaving a part with no hashtag → `409` on `hashtag_ids`,
    the line unchanged.

  Nothing was written by any of them. A further `--force` restored the user after its names were
  renamed or deleted and system rows had appeared.

## What the TUI does

- **Bank download import:** send the file as base64 with the account, and delete the client's own
  Excel reader. Show results by `row` number. Show the `skipped` outcome and `counts.skipped`. Read
  refusals at `rows.<row>.<field>`.
- **Owner's sheet:** delete any client-side sheet reading. Run the dry run, show the names table with
  each `proposed_id`, let the owner confirm or change each id, then apply with `names`.
- **Statement PDF:** offer the upload on a statement, as a dry run first.
  - Show its rows with `outcome` and `near_misses`, and the lines `taken_out`.
  - Apply on the owner's word.
  - Show each new reason on its key.
- **Closing:** stop treating `UNASSIGNED_IN_PERIOD` as a refusal of complete. Show `review_lines`
  from the answer and from its `twin`, and link each to its bank line.
- **Sealed days:** nothing to compute. Show the engine's `SEALED_PERIOD` as it comes; it no longer
  comes for a statement's open last day.
- **Locked fields:** read `reason` where you read the bare code, and show `message` beside the field
  as is. Delete any table from code to sentence.
- **Card partner:** read `statement_partner_id` instead of grouping the account list by statement
  code, e.g. for `twin` on `POST /reconciliations`.
- **Practice users:** run the engine's practice-user seed with `--force`, from the engine's repo,
  before a live run; it
  prints `EXPENSE_PAT=` and `EXPENSE_RESERVED_PAT=`. Add the live tests drawing
  `RESERVED_NAME_HELD` as the reserved-names user on each route in item 9's check.

## Done when

- The TUI reads `x-changelog` up to `592f2467fa3df75a`, and the owner confirms it to the engine.
- No TUI code sends `rows` to `POST /transactions/import` or reads an Excel or PDF file itself.
- Against the practice engine, the TUI's contract tests upload a made-up download, sheet and
  statement PDF, each with a dry run and an apply.
- Complete shows `review_lines`, and nothing handles `UNASSIGNED_IN_PERIOD` from it.
- The TUI shows each locked field's `message` and keeps no table of its own from code to sentence.
- The TUI finds a card's other account only through `statement_partner_id`.
- The TUI's live tests draw `RESERVED_NAME_HELD` as the reserved-names user.
