# Update the engine repo for the terminal client's new name, own six features no client shows, and move your drop box

Raised 2026-10-14; point 3 added 2026-10-15.

## Why

Three things change for the terminal client:

1. **It is renamed `expense_world_TUI`**, both on GitHub (`PlungerBull/expense_world_TUI`,
   formerly `PlungerBull/expense_CLI_menu`; GitHub forwards the old address) and as the folder
   beside the engine checkout (formerly `expense_world_CLI`). The engine repo mentions the old
   names: at least its local-deployment guide, the practice-user seed script and its decisions
   log, plus any path that reaches the client through the sibling folder.
2. **It is a TUI only.** The owner uses only the app (opened by typing `expense`). The typed
   commands are deleted, apart from `expense import sheet`, which brings in the owner's
   spreadsheet. Nothing changes in the contract: the app calls the same endpoints. Where the
   engine docs call "the CLI" the first client, they now mean this TUI.
3. **Your drop box moves.** The folder in the client repo where you leave a note for each
   engine change it must catch up with moves from `docs/cli-answers/` to `docs/engine-answers/`
   once you confirm you have read this brief. Until the owner tells you it has moved, keep
   writing to `docs/cli-answers/`. Notes you have already left move with the folder, unchanged.

Until now every engine endpoint had a typed command, so real use could exercise all of them.
Six features now have no screen in any client. Real use no longer exercises them; only the
client's live contract suite does:

1. Activity history (`GET /v1/activity`).
2. Exchange-rate history (`GET /v1/exchange-rates/history`).
3. Editing a reconciliation's details (name, dates, balances) after it is created.
4. Updating the profile and the settings.
5. The single-month report (the app shows a four-month grid).
6. Posting a batch of transactions in one request, and the engine ping (`GET /health` is still
   called by the app's first-time setup, to tell "engine not answering" apart from "key
   refused").

## The ask

- Replace every mention of `expense_CLI_menu` and of the `expense_world_CLI` folder in the
  engine repo with `expense_world_TUI`, including paths that reach the client through the
  sibling folder.
- Treat the six features above as the engine's own domain: keep them working and covered by the
  engine's own tests, without counting on a client's day-to-day use to catch a regression. A
  client screen for any of them is new work the owner asks for when it is needed.
- Tell the owner you have read this brief. Once the owner says the drop box has moved, point
  every engine instruction, guide or habit that writes to `docs/cli-answers/` in the client repo
  at `docs/engine-answers/`. Call the client "the TUI" in new notes.

## Done when

The engine repo names the client only as `expense_world_TUI`, every engine script or guide that
reaches the client's folder works with the renamed folder, the engine's own tests cover the
six features, and, once the drop box has moved, new notes for the client go to
`docs/engine-answers/`.

## What this client deletes once it lands

Nothing in its code. Once the engine coders confirm they have read this brief, the client renames
`docs/cli-answers/` to `docs/engine-answers/`; this file is deleted once they confirm every point.
