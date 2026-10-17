# From the engine (inbox)

What the engine sends this client: one file per engine change this client has to catch up with.
The engine coders write the files in the engine repo's `docs/to-tui/` and the owner copies them
here. This repo reads them as input and never writes one. The other direction, what this client
needs from the engine, goes out from [to-engine/](../to-engine/).

- **One file per change,** named by its slug (`published-contract.md`). Each stands alone: it
  names routes, fields, statuses and contract versions, never engine file paths or internal names.
- **Every file has this shape:**

  ```
  # <what changed, one sentence>

  Shipped <date> · <⚠️ breaking | ➕ additive> · contract <info.version or x-changelog range>

  ## What changed
  ## What the TUI does   (older notes say "What the CLI does"; read it as this client)
  ## Done when
  ```

- **A file is a pointer, not the contract.** Every rule it names is read from the live contract
  before anything is built on it ([CLAUDE.md](../../CLAUDE.md) "Key documentation").
- **The orchestrator plans from it:** a change becomes a task in the spec that catches up with
  that contract version, or a spec of its own ([specs/](../specs/)).
- **Deleted when the client has caught up,** by the orchestrator, in the commit that retires the
  spec covering it. Git history keeps it.
