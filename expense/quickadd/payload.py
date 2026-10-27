"""A parsed line as a `POST /transactions` body.

The TUI's `ctrl+s` batch builds each body from its row here. Pure: `date`
arrives already canonicalised (RFC 3339 with an offset), because
`expense.dates.to_canonical_aware` raises `typer.BadParameter` and this package
stays free of typer.

**Sparse by omission, never by null.** A line with no title sends no `title`;
a line with no category sends no `category_id`, and the engine files the row
under `@Pendiente` (docs/decisions.md "A sparse line is a ledger row"). An
explicit null would be a 422 on `category_id` and a *clear* on `title`, so
the app never sends one on a create.

**The pending hashtag never rides beside a real one.** A line that names the
pending hashtag together with a real hashtag sends only the real ones
(`reads.hashtags_to_send`); a line with no hashtag sends no `hashtag_ids`, and
the engine files the row under the pending hashtag
(contract: "Transactions (Ledger)", "Hashtags on a transaction").
"""

from expense.quickadd.parse import ParsedLine
from expense.reads import hashtags_to_send


def transaction_payload(
    parsed: ParsedLine, *, row_id: str, date: str, pending_hashtag_id: str | None = None
) -> dict:
    """`POST /transactions` body. Only valid for a line routing did not refuse.

    `row_id` is client-minted so a replayed write cannot double-apply — the
    same contract every other create already uses.
    `pending_hashtag_id` is `QuickAddRefs.pending_hashtag_id`, None when the
    user has none yet.
    """
    payload: dict = {
        "id": row_id,
        "amount_cents": parsed.amount_cents,
        "account_id": parsed.account_id,
        "date": date,
    }
    if parsed.title:
        payload["title"] = parsed.title
    if parsed.category_id is not None:
        payload["category_id"] = parsed.category_id
    if parsed.note is not None:
        payload["description"] = parsed.note
    if parsed.hashtag_ids:
        payload["hashtag_ids"] = hashtags_to_send(parsed.hashtag_ids, pending_hashtag_id)
    return payload
