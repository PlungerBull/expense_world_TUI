# The Edit form's words and keys match what it does

**Status: drafted by the orchestrator on 2026-10-25 from what the spec "The Edit form saves a
whole line in one write" found along the way; waiting on the owner to rewrite or approve it, and
to answer its questions.** When done, the why moves to [decisions.md](../decisions.md) and this
file is deleted.

---

## Why

`⏎` and `s` now open one Edit form, with every part of a transaction on it. Three things around
it still describe the screens it replaced:

- On an archived account's row the ledger hides `s`, although `⏎` on that row opens the same
  form, where its parts' categories, hashtags and notes still change.
- Some words still describe the old screens. The ledger's `s` reads "Split the cursor row into
  parts". The `?` card in "no batch" says `⏎` edits "its date, title, operation, amount or
  account", leaving out category, hashtags and note. A refused part names the engine's field for
  category and hashtags (`part 1 (category_id)`, `part 1 (hashtag_ids)`), while the amount reads
  `part 1 (amount)`.
- When the engine refuses a hashtag on an opening balance from the Edit form, the form adds the
  ledger's line "Leave the opening balance out of the selection.", which reads wrong there. It is
  rare, since those hashtags already show read-only.

## What it must do

1. **`s` on an archived account's row** does what question 1 picks.
2. **The words for `s`, for `⏎` in "no batch", and for a refused part's category and hashtags**
   match the form, as question 2 picks.
3. **An opening balance's hashtag refusal on the Edit form** reads as question 3 picks.

## How the owner knows it is done

1. On an archived account's row, `s` behaves as picked.
2. The ledger's key line, the "no batch" `?` card and a refused part's line read as the picked
   mockup draws them.
3. The opening balance's hashtag refusal on the form shows what was picked.

## Questions for the owner

1. **`s` on an archived account's row:**
   - **A.** Show it. It opens the same form `⏎` does, where only what the account still allows
     can change.
   - **B.** Keep it hidden there.

   **Recommended:** A, because `s` and `⏎` are the same form now, so hiding one of them on these
   rows only adds a difference to remember.
2. **The words:**
   - **A.** Reword them to match the form, e.g. `s` and "no batch" `⏎` reading "Edit the
     transaction and its parts", and a refused part reading `part 1 (category)` and
     `part 1 (hashtags)`. A mockup with the exact words comes for a pick first.
   - **B.** Leave them as they are.

   **Recommended:** A, because each one now describes something the app no longer does.
3. **An opening balance's hashtag refusal on the Edit form:**
   - **A.** The engine's words alone, with no line of the app's own.
   - **B.** A line written for the form, drawn in a mockup for a pick first.

   **Recommended:** A, because the engine's words already say what is wrong, and the case is
   rare.

---

## Tasks

Drafted once the owner approves the spec and answers its questions.

## Found along the way

Not built in this spec; drafted into a new spec when it is done.
