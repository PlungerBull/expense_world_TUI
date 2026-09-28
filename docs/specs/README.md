# Specs

One spec per piece of work, **written by the owner**. A spec says what the work must achieve
and how the owner will know it is done, in plain language; it does not say how to build it.

- The owner names the current spec in [todo.md](../todo.md) "Current spec". The loop works only
  on that one.
- The orchestrator drafts the spec's tasks into a **Tasks** section at the end of the spec; the
  owner approves them before the loop runs. Everything above that section is the owner's, and
  agents change it only when the owner asks. A finished task is deleted from the section in the
  commit that finishes it.
- Work that belongs to no spec stays in [todo.md](../todo.md).
- When the spec's work ships, its why moves to [decisions.md](../decisions.md) and the spec is
  deleted.

How the loop works: [CLAUDE.md](../../CLAUDE.md) "How work runs (the agent loop)".
