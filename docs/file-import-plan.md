# File import as the intake — CLI/TUI plan (accepted 2026-09-19)

**Status: accepted 2026-09-19 by the owner; C2–C5 built 2026-09-26, C1 and §6 still open.** Every rule below is a
decision, not a suggestion — settled item by item in the design conversation of that date.
Two things are still open, and neither is scope: the naming check in §3, and the mockup
gate on the import screen (CLAUDE.md, "Mock every screen before building it" — the screen
is decided, its layout is not).

As each item ships, its why moves to [decisions.md](decisions.md) (with the rejected
alternatives recorded here) and any residue to [todo.md](todo.md), and this file is
deleted — per the "each fact has one home" rule.

The engine half of the same plan is
[expense_world_engine/docs/file-import-plan.md](../../expense_world_engine/docs/file-import-plan.md).

**What is left here** *(2026-09-27)*: C1, the TUI import door (§3), and the one-time title
alignment (§6), plus the warning in §11. C2–C5 shipped in the engine uptake (Phase 10b,
2026-09-26) on the engine's `POST /transactions/import`: titles verbatim, no amount-only rule,
the 2026-01-01 floor, closed periods shown. Their sections are deleted and their why is in
[decisions.md](decisions.md) "Bank downloads are matched against the ledger" (the 2026-09-26
amendment). The section numbers are kept, because other docs cite §3, §6 and §8.

| Ask | Sections | Gate |
|---|---|---|
| **4 of 4** — the TUI import door | §3 C1 | **[UI]**, no mockup drawn yet; built on [bank_import/engine.py](../expense/bank_import/engine.py) |
| One-time title alignment | §6 | After the official migration, before the 2026 periods are completed |

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

## 2. What is already built (2026-09-26 — do not rebuild)

- `expense import bank <file.xlsx>` — parse, account pick, one `POST /transactions/import`
  (dry run by default), preview, `--apply` ([cli-spec.md](cli-spec.md) `expense import bank`).
  The request and the response → rows live once, in
  [bank_import/engine.py](../expense/bank_import/engine.py), for the TUI door to call.
- `operation_code` end to end (`sql/039`); the engine writes it onto a matched ledger row that
  lacks one.
- Duplicates are matched **against the ledger, never against file history**, by the engine.
  The question is always "is this row in the database", never "was this file processed".
- Account routing: accounts folded by base name so one file feeds the PEN and USD legs of the
  same card, with each row's `Moneda` column choosing the leg.
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

## 4–5. C2 and C3 — shipped 2026-09-26

Verbatim titles and the deleted amount-only rule; the why is in [decisions.md](decisions.md).

---

## 6. The one-time title alignment

The floor (2026-01-01, `IMPORT_FLOOR` in [bank_import/engine.py](../expense/bank_import/engine.py))
is built, and there is no `--since` (why: [decisions.md](decisions.md)). What stood in for a
second floor is this alignment: the ledger's rows up to the end of the spreadsheet are
hand-typed, with no operation codes and the owner's wording (`MAR DE COLAS LIMA` against the
bank's `MAR DE COLAS LIMA PE`). The engine matches only identical titles, so a bank file
overlapping those days would import them a second time. Giving those rows the bank's wording
once removes the overlap at the source.

**What the overlap is (measured read-only 2026-09-26, on the test ledger):**
- BCP's Excel export holds the **last 20 movements** of a current account and the **last 80** of
  a card, so a download can never reach far back. The oldest row in the 2026-09 downloads was
  2026-07-06 (`BCP USD`, which moves little); the card's was 2026-08-13.
- The January–August statements exist only as **PDFs**, which cut the description to 18
  characters and carry no operation number (`DE CONSTRUCTORA KO`, `CLAR000074096613`). Their
  wording is not the Excel's, so they are **no use** for aligning titles.
- So the overlap is only the few weeks before the spreadsheet ends. On the test ledger: 122
  bank rows, of which 38 already identical, 69 with exactly one ledger row of the same account
  and amount on the same or the adjacent day, 14 with several, 1 with none.

### One-time title alignment (todo.md "One-time title alignment after the official migration")

**When:** after the official migration (the sheet updated and re-imported), **before** any 2026
period is completed — a completed period locks its rows' `title` (engine-spec *Field locking*),
and before the first real bank import. Not now: the current ledger is test data.

**How (owner, 2026-09-26: "app proposes, I approve"; no new screen, since it runs once):**
1. Re-download every export the bank offers (they reach back as far as they reach), and read
   them against the migrated ledger — reads only.
2. Pair each bank row with the ledger rows of the same account and signed amount on the same or
   the adjacent day. Identical titles need nothing. Exactly one candidate becomes a proposal
   `ledger title → bank title`. Several candidates, or none, are listed with what there is.
3. The list is a **local file outside the repo** (the repo is public; this is the owner's
   financial data). The owner answers with the exceptions and the picks for the unclear rows.
4. Apply exactly what was approved: one `PUT /transactions/{id}` with `title` only. **The old
   title is dropped** (owner); the note (`description`) is untouched.
5. Operation codes are not written here. The first real import writes them itself (the
   engine's backfill on a `same_day` / `adjacent_day` match), and its dry run is the check:
   every aligned row must read `in ledger · … · +code`, none `new`.

## 7. C5 — shipped 2026-09-26

The engine returns a row inside a completed period as `sealed`; the preview shows it in its
own block and never writes it. Why: [decisions.md](decisions.md).

---

## 8. Settled non-goals

| Not doing | Why |
|---|---|
| Merchant memory / category suggestions | Import already removes the typing; classification stays manual, as it is today. Home suggestions were rejected 2026-09-13 and that stands. |
| Transfer / card-payment / ITF detection | `TRAN.CTAS.PROP.BM`, `PAG.T.PROP.VISA.BM` and `IMPUESTO ITF` import as ordinary rows and are classified by hand, exactly as they are now. Transfers are already two ordinary transactions (2026-08-16). |
| Import provenance + undo | A wrong-account import is fixed with bulk `b` in Home. |
| A per-row override in the preview | With no amount-only rule, every verdict is a fact (matching code, or identical text + amount + date), not a guess. Nothing left to overrule. |
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
2. After the official migration, the one-time title alignment (§6), **before** step 1's
   periods are completed.
3. TUI import door (§3) — **mockup first**, per CLAUDE.md "Mock every screen before building
   it".
4. First real bank import.

The spreadsheet importer (`expense import sheet`) is bootstrap scaffolding and is retired
once the database becomes the record — the owner expects that within days of 2026-09-19, after
testing. Nothing in this plan should keep it working.

---

## 11. Before any import writes a time of day

*(Moved here 2026-09-27 from the engine debrief of 2026-09-23, §6.1, which is deleted at the
uptake's cutover.)*

The "no batch" pane's `!` flag (a row dated inside a reconciliation window) is computed
client-side: the engine declined a per-row flag (engine `open-bugs.md` D13), because the
engine makes the real decision at close time. The engine treats a period as whole calendar
days in the user's timezone; the client compares the ISO date prefix of the row's `date`.
**The two agree only because every live row is stored at exactly 00:00 America/Lima** (3,895
of 3,895, checked 2026-09-23), and Lima has no daylight saving. Nothing enforces midnight.

The bank importer sends bare days today, so it keeps the rule. **The first import, or any
other writer, that stores a real time of day makes the `!` wrong on rows near midnight.** That
is the point to ask the engine again: D13 names it as the condition for reopening the per-row
flag.
