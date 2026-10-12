# Catch up to engine contract 26c9f9880ad3540c

**Status: current.** The owner approved the tasks; the loop runs on it.
When done, the why moves to [decisions.md](../decisions.md) and this file is deleted, together
with the two answers it covers:
[ordering-direction-stated.md](../cli-answers/ordering-direction-stated.md) and
[python-312.md](../cli-answers/python-312.md).

---

## What it must do

The engine coders left two answers on 2026-10-11. Neither changes anything the owner sees. This
spec closes both, and each is closed only by a check that ran, never by reading the answer.

**1. Every list says which way it is ordered.** The contract moved from `8d2430081e64cd7c` to
`26c9f9880ad3540c`, and its change log holds one entry between the two: wording only, the order
of no list changed. Five lists now state "oldest first" where their order ends on creation time:

- accounts (contract: GET /v1/accounts, "Ordering")
- categories (contract: GET /v1/categories, "Ordering")
- a category's tags (contract: GET /v1/categories/{category_id}/hashtags, "Ordering")
- tags, which also now state that `sort_order` is ascending (contract: GET /v1/hashtags)
- an account's reconciliations (contract: "Reconciliations", "Ordering")

The app must:

- hold `26c9f9880ad3540c` as the version it was last checked against;
- show each of the five lists in the order the engine returns it, with no sorting of its own;
- state the direction, and cite the contract for it, wherever a doc or a code comment describes
  one of these orders.

**2. The practice engine runs on Python 3.12, started with its own Python.** The contract did
not change. The app must:

- start the practice engine only with the engine checkout's own `.venv/bin/python`, in the ops
  guide and in the session guard alike, so a start with any other Python is refused;
- name no older engine Python, and carry no note that the practice engine cannot start, in any
  doc.

## How the owner knows it is done

1. The practice-engine check passes: the contract version matches `26c9f9880ad3540c` and no
   fixture differs.
2. The live contract suite passes against a practice engine started with its own
   `.venv/bin/python`.
3. The session guard refuses a practice-engine start with any other Python, and a test trips it.
4. No doc or code comment gives one of the five orders without its direction.
5. [cli-answers/](../cli-answers/) holds only its README.

## Tasks

2. **The five orders are stated once, with their direction and their citation.** The plan for
   tag suggestions, the `reconcile list` line of the command spec, and the two code comments on
   the reconciliation list give the order in the contract's words and cite it. The reviewer
   confirms no screen or command sorts any of the five lists itself.
3. **Record the new contract version.** With the practice engine running, the version check
   prints only the wording entry above; then the version is recorded. Done last, so the check
   keeps failing until the rest of the catch-up is in.

After the tasks: the acceptance check (the five checks above), the doc sweep, then this spec and
both answers are deleted in one commit.
