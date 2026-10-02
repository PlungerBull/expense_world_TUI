# The engine's docs were reorganised, and the test engine moved to port 8002

Shipped 2026-09-27 · ⚠️ breaking · no contract change

## What changed

- `docs/open-bugs.md` is now `docs/todo.md`.
- Its decisions table, `currency-model-decision.md`, `file-import-plan.md` and `transaction-pagination-plan.md` are now sections of `docs/decisions.md`.
- `design-philosophy.md` is now `expense-world-design-philosophy.md` at the workspace root.
- The test engine runs on port `8002`.

## What the CLI does

Replace the old names and the old port:

- `docs/file-import-plan.md` (D13) and `docs/tui-only-plan.md` name the old engine docs.
- `docs/todo.md` cites "engine plan §9", which is now the engine's `docs/decisions.md` → "Import first, reconcile second".
- `docs/cli-runtime.md:63` and `scripts/check_fixture_drift.py:16` use port `8001`.

## Done when

None of the old names or the old port remain in the CLI.
