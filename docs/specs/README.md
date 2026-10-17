# Specs

One spec per piece of work, **written by the owner**. A spec says what the work must achieve
and how the owner will know it is done, in plain language; it does not say how to build it.

- The owner names the current spec when starting the loop. The loop works only on that one.
- The orchestrator drafts the spec's tasks into a **Tasks** section after the owner's part; the
  owner approves them before the loop runs. Everything above that section is the owner's, and
  agents change it only when the owner asks. A finished task is deleted from the section in the
  commit that finishes it.
- Work that belongs to no spec stays in [todo.md](../todo.md).
- When the spec's work ships, its why moves to [decisions.md](../decisions.md) and the spec is
  deleted.

**A catch-up spec** answers an engine hand-off from [from-engine/](../from-engine/):

- Its opening line names the contract range it catches up to, from the version after the last
  catch-up to the hand-off's last version. That last version is the one this client has caught
  up to while the spec is open.
- It holds what the live contract does not: the engine's "What the TUI does" as tasks, its
  "Done when" checks, and what the engine declined and why. The hand-off file is then deleted.
- It ends with a **Reply to the engine** section, after "Tasks", drafted with the tasks: the
  range it covers, the engine's "Done when" checks to report on, and the asks it closes. Once the
  spec is done, the orchestrator writes the reply file from it into
  [to-engine/](../to-engine/) for the owner to hand over.

How the loop works: [CLAUDE.md](../../CLAUDE.md) "How work runs (the agent loop)".
