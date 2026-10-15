# Engine asks

One file per thing this client needs the engine to do. The owner hands the file straight to
the engine coders, so each one stands on its own:

- **Written for the engine coders.** No links into this repo and no client internals; it says
  what the engine should do, why every client needs it, and how the engine coders know it is
  done.
- **Shape:** `# <the ask, as one sentence>`, the date it was raised, then **Why**, **The ask**,
  **Done when**, and last **What this client deletes once it lands** (the client workaround the ask
  retires, in words, no paths into this repo).
- **This folder is the list of open asks.** Nothing else lists them.
- **Deleted when it lands**, in the same commit as the client code it replaces.

Raising asks is encouraged, not a last resort (CLAUDE.md "Ask the engine to change").
