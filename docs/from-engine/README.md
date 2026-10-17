# From the engine (inbox)

What the engine sends this client: the changes this client has to catch up with. The engine
coders write the files in the engine repo's `docs/to-tui/` and the owner copies them here. This
repo reads them as input and never writes one. The other direction, what this client needs from
the engine and its replies, goes out from [to-engine/](../to-engine/).

- **One file per catch-up, from one version to the engine's current one.** The owner asks the
  engine coders for one file covering every contract change after the version this client last
  caught up with, so no version is skipped and nothing is caught up twice. That version is the
  one the newest catch-up spec catches up to ([specs/README.md](../specs/README.md)); once that
  spec retires, its reply to the engine names it.
- **Every file has this shape:**

  ```
  # <what changed, one sentence>

  Shipped <date> · <⚠️ breaking | ➕ additive> · contract <info.version or x-changelog range>

  ## What changed
  ## What the TUI does   (older notes say "What the CLI does"; read it as this client)
  ## Done when
  ```

  It names routes, fields, statuses and contract versions, never engine file paths or internal
  names.
- **A file is a pointer, not the contract.** Every rule it names is read from the live contract
  before anything is built on it ([CLAUDE.md](../../CLAUDE.md) "Key documentation").
- **The orchestrator turns it into specs.** All the files waiting here are planned together:
  one spec when the work is one piece, several when parts are independent (a small fix that
  should not wait for screens still being picked). The spec takes what the live contract does not
  hold: the engine's "What the TUI does", its "Done when", and what it declined and why. It ends
  with its reply to the engine ([specs/README.md](../specs/README.md)).
- **Deleted once its specs are written,** in the commit that adds them. Git history keeps it.
