# CLI answers

Engine changes the CLI has to catch up with, one file per change, ready for the owner to hand over. A file is the engine's half of the conversation. A client's ask comes in as a standalone file (CLAUDE.md → "Asks from the client"), and the reply or follow-up goes out from here.

- **Only the orchestrator writes here,** like `docs/todo.md`. Workers name a client break in their report.
- **One file per change,** named by its slug (`published-contract.md`). Each file stands alone for a reader with no engine context: it names routes, fields, statuses and contract versions, never engine file paths or internal names.
- **Every file has this shape:**

  ```
  # <what changed, one sentence>

  Shipped <date> · <⚠️ breaking | ➕ additive> · contract <info.version or x-changelog range>

  ## What changed
  ## What the CLI does
  ## Done when
  ```

- **Delete the file once the owner says the CLI has caught up.** Git history keeps it.
