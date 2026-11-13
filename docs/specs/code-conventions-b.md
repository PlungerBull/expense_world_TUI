# Engine data travels as typed objects, and tests check what a screen does

**Status: approved 2026-11-11, with every question answered as recommended.** It is v1.3,
last in the Queue. When done, the why moves to
[decisions.md](../decisions.md) and this file is deleted.

---

## Why

Counted 2026-11-09:
1. **Engine data travels as raw dicts.** The app reads fields by string about 600 times
   (`row["name"]`, `.get("name")`).
   - Most are in statements.py, edit_form.py, reads.py, formatting.py and the importers. Form values look the same but are not engine data.
   - When the engine renames or drops a field, the app finds out only on whichever screen trips over it, sometimes as a quiet blank rather than an error.
2. **Tests reach into screens.** About 1,500 uses of screens' private attributes
   (`screen._key`, `screen._list`, `screen._statement_list`, `screen._values`…), heaviest in
   test_tui_statements.py, test_tui_log_bar.py, test_tui_edit_form.py and
   test_tui_statement_detail.py. Changing a screen's insides breaks tests over nothing the
   owner would notice.

## Owner's answers

1. **An engine reply becomes a pydantic model.** Pydantic is already a dependency (the config is
   one). Every field is checked when the reply is read, and the error says which.
2. **The models are hand-written,** holding only the fields the app reads. The drift script
   checks each model against the live `/openapi.json`, as it checks the fixtures. Nothing is
   generated from the contract, which is read live and never copied.

## What it must do

1. **An engine reply becomes a typed object when it is read,** in one place (the client and the
   shared reads), and travels as that object from there on.
   - A reply missing a field the app needs, or holding it under another name, fails at that read. It is shown the way a reply in an unexpected shape is shown today, naming the read and the field, and written to the log.
   - Fields the app does not read are ignored, so an engine adding one breaks nothing.
   - The test fakes' answers go through the same models, so a fake in the wrong shape fails too.
2. **Tests check what a screen does:** keys pressed, what is shown, what is sent to the engine;
   never a screen's private attributes.
   - New tests follow this from the first task.
   - Existing tests convert when their file is next touched.
   - The three worst files convert now.
3. **CLAUDE.md's code rules state both,** in a line each.
4. **Nothing else the owner sees changes.**

## How the owner knows it is done

1. No shared read and no screen handles engine data as a dict. The tester counts two things in
   `expense/tui/` and `expense/reads.py`, and both are zero:
   - read functions returning `dict`, `list[dict]` or `Any`;
   - string-key reads on engine data.

   The summary lists what string-key use remains (payloads being sent, form values) and why.
2. The summary gives private-attribute uses in tests before and after, counted the same way, in
   total and for the three converted files, which hold none.
3. `pytest tests/unit`, the live contract suite and the drift script (now checking the models)
   pass.

---

## Tasks

Each task leaves `pytest tests/unit` green and mypy green.

1. **Re-count and the first models.**
   - Re-count the dict reads and private-attribute uses.
   - CLAUDE.md gains the two rules.
   - Models for the reference lists in reads.py: accounts, categories, hashtags, the user and settings.
   - A reply that fails the model is shown and logged.
   - The drift script checks the models.
2. Models for transactions and bank lines; formatting.py reads them.
3. Models for statements, the dashboard and the rate.
4. The statement screens (statements.py and statement detail) take the models.
5. The other screens (edit_form, transactions, home, accounts, system, and create_forms' engine
   reads) take the models.
6. The writes and importers (bank_line_write.py, batch_write.py, import_/, bank_import/) take
   the models.
7. Convert the worst test file at task 1's re-count.
8. Convert the second worst; then the third worst, in a task of its own if it does not fit.

## Found along the way

Not built in this spec; sorted when it is done.
