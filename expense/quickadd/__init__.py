"""One-line quick-add grammar — the parser behind the LOG bar.

Client-specific input forgiveness (like dates.py and import_/): turns a single
typed line into the fields a transaction needs. Pure — no Textual, no HTTP, no
config — so every TUI screen that reads a typed line shares one grammar and
one copy of every rule.

No business logic lives here. Names are matched against reference lists the
caller already holds; nothing is created, nothing is validated beyond shape.
The engine remains the only authority on whether a row is acceptable.

The matching rules: docs/decisions.md "Three quick-add grammar rules".
"""
