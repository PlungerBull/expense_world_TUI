# Lean docs

**Status: approved 2026-11-11, with every question answered as recommended.** It runs after
[The app the owner runs](going-live.md). When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

The docs are about 55,000 words for 22,000 lines of code (2026-11-11).
- docs/tui.md is 26,124 words, most of them walking each screen key by key, which the code and the app's `?` card already say.
- The practice engine's setup is written in four places, and the test conventions in four.

The rule: **docs hold only what the code can't say** (the shared loop's "Docs").
1. Why things are as they are: decisions.md.
2. How to run and repair the app: runtime.md, which becomes the operations doc.
3. What the owner can't see from the code, such as product rules.

Everything else lives in code and docstrings, and docs point to the file.

## Owner's answers

1. **Mockups for built screens are deleted** once their screen is built, and from now on a
   mockup leaves with its spec. Git keeps them, the built screen is the truth, and an archive
   would be a second copy agents read. Account numbers and cash account are built today.
2. **The word-budget check in `test_doc_hygiene.py` goes.** It froze each doc at its size and
   never cut. The provenance check and the link test stay, and the librarian's per-spec word
   report shows growth.

## What it must do

1. **docs/tui.md keeps one short section per screen:** what it is for and the rules that aren't
   obvious. The key-by-key walkthroughs go.
   - On Home, the ledger, Statements, a statement, Manage and System, `?` shows every key, built from the code's bindings ([help.py](../../expense/tui/screens/help.py)). `test_tui_help.py` fails when a key has no text.
   - The forms, the bulk pick, the LOG bar, the import screens and the flagged lines have no `?`; their footer is the key list.
   - A key in neither keeps one line.
2. **CLAUDE.md becomes a map:** layout, exact commands, red lines, and which doc owns what.
   - "How work runs" stays as it is: the import of the shared loop and this repo's own rules.
   - Headings that code cites keep their names: "Dev loop", "Stay inside this repo", "Key documentation", "Product scope and role", "No new terms", "Docs must outlive any one contributor" and "Careful running live".
3. **One home each:**
   - **The practice engine:** runtime.md "Working against the live engine". The guard's tests
     read that heading and its one start line. CLAUDE.md keeps the two commands only.
     README.md and the `scripts/practice-engine` header point there instead of retelling it.
   - **The test conventions:** CLAUDE.md "Testing conventions" says the rule in a few lines.
     The mechanics are in the `helpers.py` and `conftest.py` docstrings. decisions.md entries
     keep their why and stop restating the rule.
4. **runtime.md is the operations doc:** settings, a fresh start, the live and practice engines,
   the contract suite, drift and the version check. Read/write and error semantics shrink to
   their non-obvious rules, pointing to `http.py`, `_base.py` and `errors.py`.
5. **`docs/README.md` is the index:** a "Doc | Read it when" table. AGENTS.md points to it.
6. **No fact is lost.** Each removed passage is either moved to its home or said by a named file.

## How the owner knows it is done

1. The summary gives each doc's words before and after, counted with `wc -w`:

   | Doc | Before | Target |
   |---|---:|---:|
   | docs/tui.md | 26,124 | ≤ 5,000 |
   | CLAUDE.md | 2,632 | ≤ 2,300 (2026-11-11: every rule kept, "How work runs" as it is) |
   | docs/decisions.md | 17,999 | ≤ 17,999 |
   | docs/runtime.md | 3,344 | ≤ 2,600 |
   | AGENTS.md | 91 | ≤ 60 |
   | docs/README.md | — | ≤ 300 |
   | All root and docs/*.md | 54,915 | ≤ 32,000 |

   docs/tui.md by section, now → target:
   - intro 93 → 80
   - §1 Architecture with the rate alert 1,826 → 600
   - §2 Screens 16,247 → 2,850
   - §3 Theming 522 → 250
   - §4 Keymap 6,368 → 700
   - §5 Pagination 822 → 300
   - §6 Tests 360 → 0

   §2 by screen, now → target:
   - Setup 496 → 120
   - Home 580 → 180
   - ledger and bulk pick 985 → 200
   - Edit form 3,115 → 350
   - no statement 858 → 150
   - bank import 2,052 → 250
   - statement PDF 1,398 → 200
   - Statements, from §4 (3,242) → 250
   - Accounts and Manage 1,696 → 250
   - delete 844 → 120
   - refusals 2,631 → 300 (the reason table is `errors.py`'s)
   - account forms 1,319 → 250
   - chrome 273 → 200

   The section counts were taken 2026-11-09, so task 1 re-counts them.
2. `pytest tests/unit` is green, `test_docs_links.py` (every link resolves) and the guard's
   tests that read runtime.md included.
3. Every citation of a tui.md section, by § or by name, in code, docs and decisions.md, names a
   section that still exists. The link test drops anchors, so the librarian checks this by
   search.
4. Each task's moves list accounts for every removed passage: moved to its home, or said by a
   named file and line; the reviewer checks it.
5. The mockups of built screens are gone.

---

## Tasks

Each task keeps `pytest tests/unit` green and reports words before and after for every doc it
touches, with a moves list: each removed passage and where it now lives.

7. **Mockups, the budget check and `docs/README.md`,** as answered; the final word counts. Before
   counting, the trims named in review that lose no fact: the Account forms' opening-balance
   bullets restate `EditAccountScreen`'s docstring; the bank import's "The days where the file
   and the ledger disagree" and "Several files" restate bank_import.py (the date-range export
   warning stays); Accounts and Manage's `x` 404 answers and the `c` archived-account sentence
   restate the contract and accounts.py. help.py:46 cites "the §1.2 capture" of a mockup the
   mockup removal deletes. Statements (about 490 words, target 250) retells
   the statements.py module docstring; the LOG bar's "A dropped bank file", "The legend row" and
   "The account peek", and §1's rate alert, retell log_bar.py, dropped.py, header.py and
   reads.py: each can lose about half once task 6 has re-pointed its citers.

## Found along the way

Not built in this spec; sorted when it is done.

- **expense/http.py's retry comments read looser than the code:** :22-23 say a connect failure
  fails fast, though a connect timeout is retried (:117, `TimeoutException`); docs/runtime.md
  says "5xx", though :31 retries only 500, 502, 503 and 504. check_fixture_drift.py:21 says the
  run fails when the versions differ, leaving out a missing saved version.
- **expense/tui/screens/transactions.py:20-21's docstring says an account move sends
  `account_id` and `currency_code`;** the code sends `account_id` alone (:775), as tui.md says.
- **expense/tui/screens/edit_form.py:4-5's docstring leaves CURRENCY out** of the shared fields
  (`DATE › TITLE › ACCOUNT`), though the form shows it after ACCOUNT (:59).
