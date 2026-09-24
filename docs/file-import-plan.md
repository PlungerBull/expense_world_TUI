# File import as the intake — CLI/TUI plan (accepted 2026-09-19)

**Status: accepted 2026-09-19 by the owner, not yet built.** Every rule below is a
decision, not a suggestion — settled item by item in the design conversation of that date.
Two things are still open, and neither is scope: the naming check in §3, and the mockup
gate on the import screen (CLAUDE.md, "Mock every screen before building it" — the screen
is decided, its layout is not).

As each item ships, its why moves to [decisions.md](decisions.md) (with the rejected
alternatives recorded here) and any residue to [todo.md](todo.md), and this file is
deleted — per the "each fact has one home" rule.

The engine half of the same plan is
[expense_world_engine/docs/file-import-plan.md](../../expense_world_engine/docs/file-import-plan.md).

**This file is two asks, not one** *(split 2026-09-20, [todo.md](todo.md)
"Now")*. They are separated by the mockup gate, and by the fact that the first
is what the first real import rests on while the second is convenience over it:

| Ask | Sections | Gate |
|---|---|---|
| **2 of 4** — the import rules that need no screen | §4 C2, §5 C3, §6 C4, §7 C5 | none — build on review |
| **4 of 4** — the TUI import door | §3 C1 | **[UI]**, no mockup drawn yet |

§1–§2 and §8–§10 are context for both. **§6's one-time floor is superseded**: it
is a `--since YYYY-MM-DD` flag, not the constant this file implies — the owner
decided 2026-09-20, on the grounds that the hand-typed stretch ends wherever the
spreadsheet ends and the spreadsheet is being updated before the first import, so
the date is not knowable while the code is being written. The permanent
2026-01-01 floor is unaffected.

---

## 1. The change

Rows stop being typed and start arriving as BCP `.xlsx` downloads: drop the file on the TUI,
pick the account, review, apply. The rows land under `@Pendiente` and the remaining manual
work is classification, which Home already does in bulk (`space` + `c`/`b`/`h`). The LOG bar
stays for what has no bank row — cash, people, anything off-statement.

**BCP only.** No second bank, no CSV, no PDF, no format abstraction. Two export shapes:

| Export | Columns | Dates | Operation number |
|---|---|---|---|
| Card (`VISA Infinite Sapphire.xlsx`) | Fecha, Descripcion, Moneda, Monto | `2026-09-16` | **no** |
| Current account (`Sueldo Soles.xlsx`, `Cuenta Digital Dólares.xlsx`) | + Numero de Operacion | `16/09/2026` | yes |

Both already parse ([bank_import/parse.py](../expense/bank_import/parse.py)); the card file
mixes PEN and USD rows in one file and is already routed to two accounts.

---

## 2. What is already built (verified 2026-09-19 — do not rebuild)

- `expense import bank <file.xlsx>` — parse, account pick, ledger match, preview, `--apply`.
- `operation_code` end to end: `sql/039` (nullable column, blank CHECK, partial UNIQUE on
  `(user_id, account_id, operation_code)` over live rows), engine create/update/batch, and
  the CLI writing it plus backfilling it onto rows that predate it.
- Row-level duplicate matching **against the ledger, never against file history** — no
  hashing, no "files I have seen" record ([decisions.md](decisions.md), "Bank downloads are
  matched against the ledger, not hashed"). This is already the owner's stated rule: the
  question is always "is this row in the database", never "was this file processed".
- Account routing: accounts folded by base name so one file feeds the PEN and USD legs of the
  same card (`BCP PEN`/`BCP USD`, `BCP Signature PEN`/`BCP Signature USD`), with each row's
  `Moneda` column choosing the leg.
- Recovery from a wrong pick: select the rows in Home, `b`, move them to the right account.

---

## 3. C1 — the TUI import door **[UI — mockup required before code]**

`+` opens the LOG bar; dragging an `.xlsx` onto the terminal window makes the emulator insert
the file's path as text into the bar. The bar notices the line is a path to an existing
`.xlsx` and switches from "parse this as a quick-add line" to "import this file".

Mechanics, all verified:

- Textual 8.2.7 emits paste events and the LOG bar is a plain `Input`
  ([log_bar.py](../expense/tui/screens/log_bar.py)); `run(mouse=False)` is irrelevant —
  this is the terminal inserting text, not mouse tracking.
- **Escaping differs by emulator**: Terminal.app backslash-escapes spaces and parentheses,
  VS Code wraps the path in quotes. Unescape and strip quotes.
- **Several files dropped at once** arrive as several paths, space-separated.
- Typing or pasting a path must do the same thing, which keeps the decision a pure function
  (text in → import or quick-add) and testable without a terminal.

Then: account list → preview → apply.

**The account list replaces the filename memory.** Today the chosen account is remembered
under `Path(file).stem`, so `Sueldo Soles (1).xlsx` — what the browser produces on every
re-download — is a new key that prompts again and grows the config forever. Ask every time,
delete the `bank_files` config key. The list shows the legs folded:

```
  1  BCP              PEN + USD
  2  BCP Signature    PEN + USD
```

Naming note for whoever builds this: the bank's product names do not match the account names
(`VISA Infinite Sapphire` vs `BCP Signature`, `Sueldo Soles`/`Cuenta Digital Dólares` vs
`BCP PEN`/`BCP USD`). Worth checking with the owner whether the Signature account *is* the
Infinite card renamed, or whether a card is missing from the system.

---

## 4. C2 — the parser stores the bank's string verbatim, whitespace collapsed

Today: `title` = the merchant cut out of the descriptor, `description` = the raw string.

**Change:** `title` = the bank's descriptor with runs of whitespace collapsed to single
spaces and nothing else removed; `description` = not written at all.

```
bank:   'MAR DE COLAS           LIMA          PE'
title:  'MAR DE COLAS LIMA PE'
```

- Delete `clean_title()` and `MERCHANT_WIDTH` from
  [bank_import/parse.py](../expense/bank_import/parse.py).
- Stop setting `description` in `payload_for()`
  ([bank_import_cmd.py](../expense/commands/bank_import_cmd.py)). **`description` is the
  notes field** — the TUI labels it "note" and the spreadsheet's `NOTAS` column imports into
  it (701 of the live ledger's 3,895 rows have one). Filling it with a copy of the title
  would put bank padding in a column the owner writes in.

**Known consequence, accepted by the owner 2026-09-19.** The bank pads the merchant to a
fixed width and fills the remainder with as much of the city as fits, so one merchant
produces several strings — in the 2026-09-16 card export, 80 rows gave 59 distinct
descriptors where the cleaned form gave 56:

```
'DLC*UBER RIDES'          vs  'DLC*UBER RIDES            LIMA'
'EXPERTDENT                Lima'  vs  'EXPERTDENT             Miraflores    PE'
'MAR DE COLAS'            vs  'MAR DE COLAS           LIMA          PE'
```

Those rows will read as different merchants in the ledger. Reports group by category, so
they are unaffected. *Rejected alternative:* keep the cleaned merchant as the title (stable
per merchant) — rejected because the title is meant to be exactly what the bank sent.

**This does not weaken matching.** The two `Sueldo Soles` downloads of 2026-09-16 share 10
movements and **zero fields differ between them**: the bank renders a given transaction
identically every time. The variation above is between *different* purchases.

---

## 5. C3 — matching: delete rule 4

Rules kept, in order, each ledger row claimable once:

1. operation code (exact, per account)
2. same day + account + amount + title
3. ±1 day + account + amount + title

**Rule 4 (`±1 day, amount only`, title ignored) is deleted.** It is the only rule that can
make the ledger *miss* a real row: it claims any ledger row of the same amount within a day
regardless of description, so a genuinely new charge can be declared already-present and
never written. The owner's rule is the opposite — **more rows beats fewer**, because a
duplicate shows up at reconciliation and in the account balance, while a row that never
arrived is invisible.

Rule 4 existed to bridge hand-typed wording to the bank's. After the 2026 backfill seals
January–August and the one-time floor skips September 1–11 (§6), no import ever compares a
bank row against a hand-typed row again, and rules 1–3 have both sides in the bank's own
words.

**What still produces a duplicate, accepted:** a charge that changes amount between
authorisation and settlement, or moves more than a day. Reconciliation is the backstop.
*Deferred alternative:* a per-row fingerprint column (date + raw text + amount + occurrence)
with a UNIQUE index, which would make re-import impossible at the database and be immune to
any edit. Not needed while the exposure is one open month.

---

## 6. C4 — the two floors

- **Permanent: 2026-01-01.** Nothing dated earlier is ever considered. Cheap backstop; the
  engine's wall does the real work.
- **One-time: 2026-09-11, on the first real bank import.** The live ledger's last row is
  2026-09-11 and every row in it came from the spreadsheet bootstrap. Importing only
  2026-09-12 onward means the first import never meets a hand-typed row. September 1–11 stays
  as the owner typed it — no operation codes, no bank wording — and the September
  reconciliation still ties, because it ties on amounts.

---

## 7. C5 — closed periods are shown, not hidden

The importer asks the engine for the account's completed reconciliations and drops every file
row dated inside one *before* matching. Those rows appear in the preview as their own
**visible skipped block**, not silently — it is how the owner would notice the bank restating
something inside a month already closed. The engine rule
([engine plan §2](../../expense_world_engine/docs/file-import-plan.md)) is the floor under
this, not the mechanism.

The read is `GET /reconciliations?account_id=<id>`, which since 2026-09-23 returns the
account's whole list, unpaged, so no paging loop is needed; keep the `status == "completed"`
rows (`?status=` was declined, engine `open-bugs.md` D14).

---

## 8. Settled non-goals

| Not doing | Why |
|---|---|
| Merchant memory / category suggestions | Import already removes the typing; classification stays manual, as it is today. Home suggestions were rejected 2026-09-13 and that stands. |
| Transfer / card-payment / ITF detection | `TRAN.CTAS.PROP.BM`, `PAG.T.PROP.VISA.BM` and `IMPUESTO ITF` import as ordinary rows and are classified by hand, exactly as they are now. Transfers are already two ordinary transactions (2026-08-16). |
| Import provenance + undo | A wrong-account import is fixed with bulk `b` in Home. |
| A per-row override in the preview | Once rule 4 is gone every verdict is a fact (matching code, or identical text + amount + date), not a guess. Nothing left to overrule. |
| Bulk "assign everything shown" on the reconciliation screen | The owner is doing the 2026 backfill by hand (≈1,100 toggles). Revisit if monthly closing proves tedious — the draft screen already lists exactly the account's unassigned rows inside the period's dates, so it is a single action away. |
| Other banks, CSV, PDF | BCP only. |

`expense import bank` **stays** as a flat command beside the TUI door: it is the reference
implementation the TUI calls into, it is what the tests point at, it is scriptable
(`--json`, `--account`) and it is the way in if the TUI has a problem.

---

## 9. Operating rule to write down

**Always export with an explicit date range covering everything since the last import —
never the default view.** BCP's current-account export returns the **last 20 movements**: the
two `Sueldo Soles` downloads of 2026-09-16 hold 20 rows each and share only 10 (06/09–12/09
and 09/09–16/09). On `BCP PEN`, which sees roughly 50 rows a month, 20 movements is about
twelve days. Import less often than that with the default export and rows fall off the bottom
of the window — and nothing in the importer can detect what a file does not contain. The
month-end reconciliation difference is the only backstop.

---

## 10. Sequence

1. Owner creates the 2026 reconciliations by hand and closes through the last EECC.
   (Statement dates come from the EECC; the spreadsheet's `ESTADO_CUENTA` column — 1,646 of
   3,927 rows marked by cycle-closing month — is the cross-check on what each card statement
   actually contained, since a card cycle closes mid-month and cannot be derived from dates.)
2. Engine: the wall + `operation_code` frozen
   ([engine plan](../../expense_world_engine/docs/file-import-plan.md)).
3. CLI: verbatim titles (§4), rule 4 deleted (§5), floors (§6), closed-period skip (§7).
4. TUI import door (§3) — **mockup first**, per CLAUDE.md "Mock every screen before building
   it".
5. First real bank import.

The spreadsheet importer (`expense import sheet`) is bootstrap scaffolding and is retired
once the database becomes the record — the owner expects that within days of 2026-09-19, after
testing. Nothing in this plan should keep it working.
