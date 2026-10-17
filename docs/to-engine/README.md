# To the engine (outbox)

What this client sends the engine: one file per thing it needs the engine to do. The owner
copies each file as is into the engine repo's `docs/from-tui/`. The other direction, what the
engine sends back, lands in [from-engine/](../from-engine/).

- **Written for the engine coders.** No links into this repo and no client internals; it says
  what the engine should do, why every client needs it, and how the engine coders know it is
  done.
- **Shape:** `# <the ask, as one sentence>`, the date it was raised, then **Why**, **The ask**,
  **Done when**, and last **What this client removes once it lands** (the client workaround the ask
  retires, in words, no paths into this repo).
- **This folder is the list of open asks.** Nothing else lists them.
- **Deleted when it lands**, in the same commit as the client code it replaces.

Raising asks is encouraged, not a last resort (CLAUDE.md "Ask the engine to change").
