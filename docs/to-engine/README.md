# To the engine (outbox)

What this client sends the engine: one file per thing to hand over. The owner copies each file
as is into the engine repo's `docs/from-tui/`. The other direction, what the engine sends back,
lands in [from-engine/](../from-engine/).

Two kinds of file, both **written for the engine coders**: no links into this repo and no client
internals.

**An ask** — something this client needs the engine to do.

- **Shape:** `# <the ask, as one sentence>`, the date it was raised, then **Why**, **The ask**,
  **Done when**, and last **What this client removes once it lands** (the client workaround the ask
  retires, in words, no paths into this repo).
- **Deleted as soon as an engine hand-off covering it arrives**, in the commit that folds that
  hand-off into a catch-up spec, so an answered ask is never handed over twice. The spec carries
  what is left to do, and its reply names the ask by title.

**A reply** — this client caught up with an engine change.

- **Shape:** `# Caught up with contract <version>: <what the change was, one sentence>`, the date,
  then **Covers** (the contract range and the engine's hand-off it answers), **Done when, checked**
  (each of the engine's "Done when" checks: worked, or what happened instead), **Contract
  problems found** (anything the live contract got wrong or left unclear; "none" when none), and
  **Asks this closes** (by title).
- **Written last,** from its spec's "Reply to the engine" section, once the spec is done
  ([specs/README.md](../specs/README.md)). Its version is the one the owner quotes when asking
  the engine for the next catch-up file.
- **Deleted when the owner says it is handed over.**

**This folder is the list of open asks and unsent replies.** Nothing else lists them. Raising
asks is encouraged, not a last resort (CLAUDE.md "Ask the engine to change").
