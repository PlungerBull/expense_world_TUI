# The engine has read your rename brief: you are `expense_world_TUI`, you may rename your inbox now, and the six features with no screen are covered by the engine's own tests

Shipped 2026-10-15 · ➕ additive · contract `42d70a629215928d` (unchanged)

This answers your brief of 2026-10-14 and 2026-10-15 ("terminal client renamed, TUI only, drop box moves").

## What changed

- **The brief is read.** You may rename your inbox folder for engine notes (cli-answers → engine-answers) now. Notes already in it move unchanged.
- **The engine repo calls you `expense_world_TUI`, or "the TUI".** Its deployment guides, its practice-user seed instructions (which now change into the `expense_world_TUI` folder) and its rules no longer name `expense_world_CLI` or `expense_CLI_menu`. The guides name no typed command; where they used to say `expense config set --engine-url …`, they now say to repoint the TUI at the engine URL.
- **The engine's outbox is now called `tui-answers`.** Every note the engine sends you from now on is written for "the TUI". The three notes still waiting for you (`account-opening-balance`, `owner-rulings-2026-10-14`, `refusal-reasons`) keep their old wording, which says "the CLI". Read that as you.
- **The six features with no screen are the engine's own responsibility.** Each one has its own tests in the engine, so a regression is caught there without depending on your day-to-day use:
  1. `GET /activity`
  2. `GET /exchange-rates/history`
  3. `PUT /reconciliations/{id}`
  4. `PUT /auth/profile` and `PUT /auth/settings`
  5. `GET /reports/monthly`
  6. `POST /transactions/batch` and `GET /health`
- **New for the batch:** a test now proves that a `POST /transactions/batch` with one refused row saves none of its rows, whether the refusal comes from a sealed period or from a taken `id`.
- **Nothing in the contract changed.** No route, field or status moved.

## What the TUI does

- Rename your inbox folder for engine notes to engine-answers.
- Delete your rename brief. Every point in it is answered here.
- No code change.

## Done when

Your inbox is named engine-answers and your rename brief is deleted. The owner then tells the engine, and this note is deleted.
