# The app the owner runs

**Status: approved 2026-11-11, with every question answered as recommended.**
- It runs before [The official import](before-the-official-import.md), which is done with the released app.
- Its tasks 5–7 are [The app checks its engine](engine-checks.md), in v1.2.
- When done, the why moves to [decisions.md](../decisions.md) and this file is deleted.

---

## What it is

The `expense` the owner types is a **release**: a tagged version, installed from a folder no
agent writes in, that knows which engine it talks to and says plainly what is wrong.

## Why

On 2026-11-09, `expense` was:
- an editable install of the folder agents edit, so a builder's half-written work is what opens on the real ledger;
- installed under the old name `expense-cli-menu`;
- on Python 3.14, which CI never tests;
- running four dependencies at versions CI never ran.

Other gaps:
- There is no version, tag or changelog to go back to.
- An engine upgrade breaks whichever screen first reads a changed shape.
- Nothing says whether the app is on the real ledger, or whether a backup exists.

## Owner's answers

Two long-lived branches:
- **`develop`** is where agents work, in today's folder.
- **`main`** holds releases. It sits in the live folder, a separate clone of the GitHub repo, not a `git worktree`. A release merges `develop` into `main`, tags it `vX.Y.Z` and pushes; the live folder then pulls the tag.

Also settled: a CHANGELOG entry for every release, an exact install that is not editable, the launch check, the REAL/PRACTICE and backup line, and errors that name the fix.

1. **The live folder** is `/Users/ternero/Library/Application Support/expense_world/tui`, beside
   the engine's (`…/expense_world/engine`). It is outside `~/Documents`, which macOS blocks
   background jobs from reading.
2. **A release follows each version** (2026-11-12): only the last spec of a version prepares
   one, numbered `vX.Y.0`. The stop's summary says a release is ready, with its CHANGELOG lines
   and the one command to run.
3. **A release is prepared and tested before the owner runs it** (2026-11-11). The loop commits
   the new version and its CHANGELOG entry on `develop`, the entry with an "Upgrading:" line when
   the engine must go first; once CI passes that commit, the stop's summary says which version is
   ready and gives the one command. The number is the version the work belongs to (answer 2).
4. **The first release is `v1.0.0`** (2026-11-11).

## What it must do

1. **What the owner runs never changes underneath.**
   - `expense` is the last release, whatever is on `develop`.
   - Agents cannot write in the live folder, push `main` or make a tag; the agents' guard covers it.
   - CLAUDE.md's single-branch rule becomes these two branches. The work folder switches to `develop`, and the guard's push rule and CI move with it.
2. **A release is one command the owner runs** in the live folder, and only from a `develop` commit CI passed.
   - It moves `main` to the release commit, tags it and pushes; it writes no commit (answer 3).
   - It reinstalls `expense`.
   - **Going back** to the previous tag is one command too.
3. **The install is exact:**
   - the package's own name, not editable;
   - every dependency, including the ones they pull in, at the version CI ran;
   - Python 3.12, which CI tests and the Mac has.

   The old `expense-cli-menu` install is gone.

## How the owner knows it is done

1. `pipx list` shows `expense-world-tui` at the released version. It is installed from the live folder, not editable, on Python 3.12. `expense-cli-menu` is gone.
2. With unfinished work on `develop`, `expense` opens as the last release.
3. The release command makes a tag and a CHANGELOG entry; going back brings the old version up.

---

## Tasks

Each task leaves `pytest tests/unit` green. Tasks 1–4 are done; 5–7 moved to
[The app checks its engine](engine-checks.md).

## Found along the way

Not built in this spec; sorted when it is done.

- **scripts/release.py's small gaps:** its docstring's "after any refusal past the fetch, the
  live folder is as it was" leaves out a failed reinstall, which `latest` finishes; a
  fast-forward refusal ends "run this again", though only the loop can fix it; a malformed
  pyproject.toml in an old commit escapes `_version_at` as a traceback; its "not above the last
  release" check has no test (prepare_release.py refuses the same earlier, tested).
