# A bank is a code the owner types, every bank account has a last 4, and the sheet import makes the accounts, categories and hashtags it lists

Shipped 2026-11-14 · ⚠️ breaking · contract `1.1` → `2.0` → `3.0` → `3.1`

Answers:
- "A bank account's bank is a 3–4 letter code the user types, its last 4 is required, and only a bank `GET /banks` lists takes a statement code" (raised 2026-11-13).
- "The sheet import suggests the accounts it is missing and makes the ones the user confirms, with its names and rows, in one write" (raised 2026-11-13).

## Each ask

- **"A bank account's bank is a 3–4 letter code the user types…":** done as asked, with three details.
  - Lowercase is refused (`INVALID_FORMAT`), never upper-cased for you.
  - Removing a bank account's only number is refused with its own reason, `LAST_NUMBER`.
  - A person keeps its statement code as a label. Making that person an account at a bank `GET /banks` does not list is refused (`BANK_TAKES_NO_STATEMENT_CODE` on `bank_code`).
- **"The sheet import suggests the accounts it is missing…":** done as asked. The import makes only what the request's `create` lists. A suggestion is never applied by itself: the client shows it on the dry run's form, and the owner confirms or changes it before the apply.

## What changed

**1. `last4` is required for a bank account (`2.0`, breaking).** On `POST /accounts` and `POST /accounts/{id}/make-account`, a missing or `null` `last4` is `422` on `last4` (`REQUIRED`). A bank account's name is always `CODE-1234`. No account is named by its bank alone.

- Before: `{"kind": "bank", "bank_code": "BCP", "currencies": ["PEN"]}` → `201`, named `BCP`.
- After: the same body → `422`:

  ```json
  {"error": {"code": "VALIDATION_ERROR", "message": "…", "fields": {"last4": "Required for a bank account."}, "reasons": {"last4": "REQUIRED"}, "details": null}}
  ```

  `{"kind": "bank", "bank_code": "BCP", "last4": "5678", "currencies": ["PEN"]}` → `201`, named `BCP-5678`.

**2. `bank_code` is any 3 or 4 capital letters, `A` to `Z` (`2.0`, breaking).** This holds on `POST /accounts`, `PUT /accounts/{id}` and `POST /accounts/{id}/make-account`. No bank has to exist first. The code is compared as sent, never trimmed or upper-cased.

- Before: `"bank_code": "IBK"` → `422` (`UNSUPPORTED_VALUE`), since `GET /banks` lists only `BCP`.
- After: `"bank_code": "IBK", "last4": "4321"` → `201`, named `IBK-4321`. A second `IBK` account with another `last4` is made as usual; the same `last4` again is `409` on `last4` (`NAME_EXISTS`).
- `ibk`, `IB`, `IBKXX`, ` IBK` and `I8K` are each `422` on `bank_code` (`INVALID_FORMAT`).
- `UNSUPPORTED_VALUE` is no longer sent for `bank_code`.

**3. `GET /banks` changes meaning, not shape (`2.0`).** It now lists the banks whose statement PDFs the engine reads, and no longer the banks an account may be at. It still answers `{"items": [{"code": "BCP", "name": "Banco de Crédito del Perú"}]}`. Don't use it to limit the bank field; use it to decide whether the statement-code field applies.

**4. Only a bank `GET /banks` lists takes a statement code (`2.0`).** Otherwise it is `422` (`BANK_TAKES_NO_STATEMENT_CODE`), with the message `"IBK takes no statement code: the engine does not read IBK's statement PDFs."`. The refusal is keyed on the field that caused it:
- `statement_code` on `POST /accounts`, or on a `PUT /accounts/{id}` that sets a code;
- `bank_code` on a `PUT /accounts/{id}` that moves a coded account to such a bank without sending `"statement_code": null` in the same request;
- `bank_code` on `POST /accounts/{id}/make-account` of a person that carries a code.

A `BCP` account takes a code as before.

**5. A bank account never loses its last number (`2.0`).** `PUT /accounts/{id}` with `"current_number": null` on a bank account holding one number is `409` on `current_number` (`LAST_NUMBER`, `"Must not be the account's only number: a bank account always has one."`). With two or more numbers it removes the current one as before. The Edit form should offer removing a number only while another remains.

**6. The sheet import's `names.accounts[]` loses `ambiguous` (`3.0`, breaking).** No two live accounts can share a name now, so it was always `false`.

- Before: `{"name": "BCP PEN", "currencies": ["PEN"], "rows": 120, "proposed_id": null, "ambiguous": false}`
- After (with item 8): `{"name": "BCP PEN", "currencies": ["PEN"], "rows": 120, "proposed_id": null, "suggestion": {"kind": "bank", "bank_code": "BCP", "last4": null, "currencies": ["PEN"]}}`

**7. `POST /transactions/import-sheet` takes an optional `create` (`3.0`, additive).**

```json
{
  "dry_run": false,
  "file": "<base64>",
  "names": {"accounts": [{"name": "BCP PEN", "account_id": "<the new account's id>"}], "categories": [], "hashtags": []},
  "create": {
    "accounts": [{"id": "<uuid>", "kind": "bank", "bank_code": "BCP", "last4": "5678", "currencies": ["PEN"], "archived": false}],
    "categories": [{"id": "<uuid>", "name": "Comida"}],
    "hashtags": [{"id": "<uuid>", "name": "Viaje"}]
  }
}
```

- When `create` is sent, all three lists are required.
- An account entry's fields follow `POST /accounts`: `id`, `kind` and `currencies` (at least one code) always; a bank account adds its `bank_code` and `last4` (and a `statement_code` if it has one), a person its `name`, a cash account none of these. Leave out a field that does not apply, as on `POST /accounts`.
- `archived` is optional and `false` when left out. `true` archives the account once its rows are in, for a closed account that only holds history.
- A category or a hashtag is `{id, name}`. Every id is yours, generated before the send, as on the create routes.
- An opening balance is not sent here. A made account's first `SALDO INICIAL` row in each currency becomes that currency's opening balance, as for an existing account.
- `names` gives the made things' ids exactly as it gives existing ones.
- **Each made thing is judged by its create route's own rules and reasons** (`POST /accounts`, `POST /categories`, `POST /hashtags`). A refusal is keyed `create.accounts.<i>.<field>`, `create.categories.<i>.<field>` or `create.hashtags.<i>.<field>`. A clash between two entries of the same request is refused too, for example `409` on `create.hashtags.1.name` (`NAME_EXISTS`). The route now declares the create routes' reasons: `INVALID_FORMAT`, `NAME_BUILT`, `PERSON_HAS_NO_BANK`, `CASH_TAKES_NO_FIELD`, `CASH_NUMBERS_EXHAUSTED`, `DUPLICATE_CURRENCY`, `UNSUPPORTED_VALUE`, `BANK_TAKES_NO_STATEMENT_CODE`, `RESERVED_NAME`, `ID_EXISTS`, `CAP_REACHED`, `NAME_EXISTS` and `STATEMENT_CODE_EXISTS`.
- **One write, all or nothing.** The made things, the names and the rows land together. Any refusal, of a row or of a made thing, leaves nothing made.
- The answer gains `created: {"accounts": N, "categories": N, "hashtags": N}`: on an apply the number made, on a dry run the number that would be made. Each is `0` when `create` is not sent.
- A request without `create` answers exactly as before, apart from item 6.

**8. The dry run suggests each missing account (`3.1`, additive).** Each entry of `names.accounts` carries `suggestion`, always present. It is `null` when `proposed_id` is set, and otherwise `{kind, bank_code, last4, currencies}`. The rules are published in the contract (*Transactions* → `POST /transactions/import-sheet` → *Names*), so every client shows the same suggestion. The name is split into words at spaces and dashes.
- **`bank_code`:** the first word, when it is a code `GET /banks` lists, compared without regard to case and returned as `GET /banks` writes it. A first word ending in the four digits `last4` takes is read without them, so `BCP5678` gives `BCP`. Otherwise `null`, so `Interbank PEN` gets none.
- **`last4`:** the one run of exactly four digits `0`–`9`, as a word of its own or at the end of the first word (`BCP 5678`, `BCP-5678`, `BCP5678`). Otherwise `null`, including for two such runs or a run of five digits or more.
- **`kind`:** `"bank"` when `bank_code` or `last4` is found, otherwise `null`. It is never `person` or `cash`.
- **`currencies`:** the codes the name's rows use.

On the owner's sheet, the five `BCP …` names suggest `{"kind": "bank", "bank_code": "BCP", "last4": null}`. The other 13 suggest nothing, and the owner fills them in on the form.

**9. A dry run keeps nothing, its idempotency key included (`3.0`, breaking).** This applies to `dry_run: true` on `POST /transactions/import`, `POST /transactions/import-sheet` and `POST /statements/import`. The dry run's response is not stored.
- Before: a dry run sent with key `K`, then the apply sent with the same `K`, gave `409` on `X-Idempotency-Key` (`IDEMPOTENCY_KEY_REUSED`).
- After: the apply under `K` goes through.
- A dry run sent again runs again rather than replaying its first answer.
- A key already used by an apply is still `409` for any other request, a dry run included.

## How it was checked

Each Done-when check ran against the practice engine (contract `3.1`) on 2026-11-14, with the full suite passing (5123 passed):

1. `IBK` with `4321` made `IBK-4321`, and a second `IBK` account with `8765` made `IBK-8765`: pass.
2. `IBK` with no `last4`, and with `"last4": null`, was each `422` (`REQUIRED`): pass.
3. An `IBK` account was refused a statement code (`BANK_TAKES_NO_STATEMENT_CODE`, the message naming `IBK`), and a `BCP` account took `SIG`: pass.
4. `GET /banks` still lists `BCP` alone: pass.
5. A dry run on an empty ledger listed each sheet account with its suggestion. `BCP 5678` suggested `{bank, BCP, "5678"}` and a first name suggested nothing: pass.
6. One apply made two bank accounts, one person, one archived account, three categories and two hashtags, and imported every row. Each account's balance in each currency equalled the sheet's total: pass.
7. Four applies were each refused: by a row, a made account's currency, a made account's statement code, and two made hashtags with one name. Each left no account, category or hashtag made: pass.

The live engine still serves `1.1`. It serves `3.1` once the owner releases v1.0.0, which also applies the ledger update. To check against `3.1` before then, start the practice engine with `deploy/local/client-practice-engine.sh 8002`.

## What the TUI does

- **Account forms (create, edit, make-account):**
  - The bank field takes 3 or 4 capital letters typed by the owner, no longer a pick from `GET /banks`. Show `INVALID_FORMAT` on it as the engine words it.
  - `last4` is required for a bank account.
  - Show the statement-code field only for a bank `GET /banks` lists, and handle `BANK_TAKES_NO_STATEMENT_CODE` on whichever field it is keyed.
  - Offer removing a number only while another remains, and handle `LAST_NUMBER`.
- **The sheet import:**
  - Stop reading `ambiguous`.
  - On the dry run's form, prefill each missing account from its `suggestion` and let the owner confirm or change kind, bank code, last 4, name and archived.
  - Send the confirmed accounts, and any missing categories and hashtags, in `create`, with ids you generate. Point `names` at those ids.
  - Show `created` from the dry run before the apply.
  - Show refusals keyed `create.<list>.<i>.<field>` on the matching row of the form.
- **Dry-run keys:** the apply may reuse its dry run's key. Don't rely on a dry run's key replaying its answer.
- **The stored contract version:** move it to `3.1`.

## Done when

- The TUI's account forms make `IBK-4321` and refuse `ibk` and a missing last 4 with the engine's messages, against the practice engine on `3.1`.
- A dry run of the owner's sheet shows each missing account prefilled from its suggestion. After the owner confirms the form, one apply makes them and imports every row.
- No TUI code reads `ambiguous`, and the TUI's contract check passes against `3.1`.
