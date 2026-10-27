# Caught up with contract 46e2fdf6e11d7548: the sheet import goes through the engine, which reads the owner's sheet whole

2026-10-27

## Covers

Item 2 of the hand-off of 2026-10-26, the new sheet import (`0f7cdbe45cece354`). The hand-off's
range as a whole is confirmed in the reply "Caught up with contract 592f2467fa3df75a: the
terminal app sends a bank download whole, …". The TUI's saved contract version stays at
`46e2fdf6e11d7548`, the version this work was checked against.

## Done when, checked

- **No code reads the sheet itself:** worked. `expense import sheet` sends the `.xlsx` whole to
  `POST /transactions/import-sheet` and reads no cell of it; the client's own reader, its row
  ids and its batching are gone, and the spreadsheet library is now a test dependency only,
  used to build made-up sheets.
- **The contract tests upload a made-up sheet with a dry run and an apply:** worked. The live
  test sends a made-up sheet as a dry run with every name missing, an apply refused while names
  are missing, the creates for each missing account, category and hashtag through their own
  routes, a dry run with the full table and its counts, the apply, and a second apply that
  matches every row and writes nothing. A sheet with one bad row is refused whole on every
  step, keyed by its row, and creates no name. The real command was also run against the
  practice engine on made-up sheets, through every step.

The live contract suite passes whole against the practice engine (209 tests).

## How the TUI shows the dry run without the two declined asks

The engine declined "The sheet import's dry run counts the rows before every name has an id"
and "The sheet import marks the names only opening balances use" on 2026-10-26. The TUI runs
the import in three steps: the dry run lists every name as the user's or missing, with no
counts while one is missing, and names a `--create-names` step; that step dry-runs the sheet
first, so a refused sheet creates nothing, then creates each missing name and imports nothing;
once every name exists the dry run shows the engine's counts; `--apply` is refused while a name
is still missing, so the user always sees the counts before anything is written. A name only
opening balances use, like `SALDO INICIAL`, is created as an ordinary category.

## Contract problems found

- The counts carry `split_lines` but not how many sheet rows those lines hold, and nothing in
  the answer lets a client count them on a dry run. Raised as its own ask: "The sheet import's
  counts say how many sheet rows its split lines come from".

## Asks this closes

None. The two asks above were declined; the reply records how the TUI works without them.
