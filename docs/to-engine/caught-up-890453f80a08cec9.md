# Caught up with contract 890453f80a08cec9: bank lines, splits, the pending hashtag and fixed system names

2026-10-17

## Covers

Contract `42d70a629215928d` (exclusive) to `890453f80a08cec9` (inclusive). It answers your two
hand-offs "Bank lines and splits keep one identity across re-imports, and every transaction now
carries at least one hashtag" and "A bank line can be read, the import's mismatched days show
what each unclaimed line is, and system rows keep their names".

Your later hand-off, up to `7ff6a09d863d6e44`, is our next catch-up. It gets its own reply.

## Done when, checked

Checked on 2026-10-17 against a practice engine serving `7ff6a09d863d6e44`, with the client
built to `890453f80a08cec9`. Every check worked.

1. **Split, re-split and part edits.** The TUI splits a transaction and re-splits a line through
   `POST /transactions/{id}/split`, and edits a part through `PUT /transactions/{id}`. Worked.
2. **Import, split, import again.** A statement imported, split, then imported again shows
   every row as matched and nothing new. This includes a card line with no operation code.
   Worked.
3. **A grouped batch.** It creates one line, and a later import of the bank's row matches it.
   Our spreadsheet import does not group split rows (the owner's choice), so our live contract
   suite proves this instead of a screen: two items sharing a `line_group` get one
   `bank_line_id`, and `GET /bank-lines/{id}` shows net −100.00 over 2 parts. A dry-run import of
   the bank's −100.00 row on that day comes back `matched` (`same_day`) on that line, with
   nothing new. Worked.
4. **The upload's new fields.** The upload reads `bank_line_id`, `retitled` and
   `day_mismatches`. It reads none of `ledger_id`, `excess` or `adjacent_day`. Worked.
5. **Unclaimed lines.** Each unclaimed line is drawn from its `parts` and `net_cents`, with no
   read of `transaction_ids` and no per-transaction read. A day whose totals agree but which
   holds an unclaimed line is listed with that line. Worked.
6. **Finding the pending hashtag.** The pending hashtag is found by `system_key`. "Needs a
   hashtag" lists through `?hashtag_id=`, and the list and `/transactions/count` agree: 4 and 4,
   then 3 and 3 after tagging one row. Worked.
7. **Tagging a pending row.** A transaction created with no hashtag shows the pending one.
   Tagging it with a real hashtag leaves only the real one. No report shows an empty hashtag
   row. Worked.
8. **Re-split and the "reaches every part" note.** Re-split reads `?bank_line_id=` for the parts
   and `GET /bank-lines/{id}` for the total. The note on a part's edit form reads
   `GET /bank-lines/{id}`. Worked, with one thing to know: while the user types new parts, the
   split screen shows how much of `net_cents` the typed parts still leave. That figure is a
   guide only. It never stops a send, and your `SPLIT_TOTAL_MISMATCH` decides whether the parts
   add up.
9. **System rows.**
   - No screen offers a rename or a delete on `@Opening`, `@Pendiente` or the pending hashtag.
   - Our live contract suite proves that `color` and `sort_order` stay editable on both system
     categories, and `sort_order` on the pending hashtag: each `PUT` gives 200 with the new
     values, which are then put back.

   Worked.
10. **The new reasons.** Each new reason has a handled path, and the engine's words are always
    shown.
    - `SPLIT_TOTAL_MISMATCH` shows under the parts on the split screen.
    - `LINE_GROUP_FIELDS_DIFFER` cannot come from this client, because it never sends
      `line_group`; our contract suite produces it and checks it.
    - `SPLIT_LINE_PARTS_DIVERGE`: see the next section.

    Worked.

## Contract problems found

- **Reconciling one part of a split line.** On `890453f80a08cec9`, a `PUT /transactions/{id}`
  with `reconciliation_id` on one part put every part of the line in that reconciliation. The
  contract said it settled `{id}` alone. So `SPLIT_RECONCILIATION_MIXED` could not be produced
  that way. `ce4e5cb642e53fdb` made the whole-line rule the contract; our next catch-up reads it.
- **`SPLIT_LINE_PARTS_DIVERGE`.** The contract lists it, but we found no route that produces it.
  If one can, please say which in the contract.
- **The `OPERATION_CODE_EXISTS` message.** It still speaks of a transaction. On a `POST
  /transactions` with an operation code already on the account, the 409 reads "A transaction
  with operation code 'OP-…' already exists on this account.", with reason
  `OPERATION_CODE_EXISTS`. We choose our hints by reason code, so nothing breaks on our side.

## Asks this closes

- A bank line split into several transactions keeps one identity, so a re-import recognises it.
- A built-in `#Pendiente` hashtag that every row with no hashtag lands on, as `@Pendiente` does
  for categories.
- Let a client read a bank line: its parts, its total and its part count.
- A bank import's unclaimed ledger lines carry their total and their parts.
- The built-in categories and the built-in pending hashtag cannot be renamed.
