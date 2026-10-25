"""The body of the whole-line write, `PUT /bank-lines/{id}`.

One home for every screen that rewrites a bank line's parts: the split screen
now, the Edit form with its parts next, so neither builds the body its own way.

**`parts` is the line's complete new set**, each part deciding by its `id`
what happens to it (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"):

- a part the line keeps goes under its own id and is updated in place, a field
  left out staying as it is
  (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part of this line is updated in place");
- a part under a fresh id is created on the line
  (contract: PUT /v1/bank-lines/{bank_line_id}, "An id no record holds creates a part");
- a part left out is deleted
  (contract: PUT /v1/bank-lines/{bank_line_id}, "A live part not sent is deleted").

**A kept part sends only what changed**: its signed amount whenever it has one,
and its category, note and hashtags only when they differ from what the
engine holds. The hashtags matter most: a kept part sent with `hashtag_ids` is
always written, even with the set it already has, so they go only when the
set changed. A kept part's category is never sent as `null`, which the write
refuses (`NOT_NULL`); an emptied note goes as `""`.

**A new part is sparse**, as every create: only what it holds. With no
category it is filed under `@Pendiente`, with no hashtag it is put on the
pending hashtag, and with no note it has none
(contract: PUT /v1/bank-lines/{bank_line_id}, "An id no record holds creates a part").

**The line fields** go beside `parts` only when the screen changed them, and
only the five the write takes; `statement_line` and `statement_place` never go
(contract: PUT /v1/bank-lines/{bank_line_id}, "Body").
"""

from collections.abc import Iterable, Mapping
from uuid import uuid4

from expense.reads import hashtags_to_send

#: The line fields the whole-line write takes beside `parts`
#: (contract: PUT /v1/bank-lines/{bank_line_id}, "Body").
LINE_FIELDS = frozenset({"title", "date", "account_id", "operation_code", "reconciliation_id"})


def new_part(
    *,
    amount_cents: int | None,
    category_id: str | None = None,
    description: str | None = None,
    hashtag_ids: Iterable[str] = (),
) -> dict:
    """A part the write creates: a fresh id and only what it holds. The
    `hashtag_ids` given are sent as they are, none when empty."""
    body: dict = {"id": str(uuid4())}
    if amount_cents is not None:
        body["amount_cents"] = amount_cents
    if category_id is not None:
        body["category_id"] = category_id
    if description:
        body["description"] = description
    tags = list(hashtag_ids)
    if tags:
        body["hashtag_ids"] = tags
    return body


def kept_part(
    held: Mapping,
    *,
    amount_cents: int | None,
    category_id: str | None,
    description: str | None,
    hashtag_ids: Iterable[str],
    pending_hashtag_id: str | None,
) -> dict:
    """A part the line keeps, under `held["id"]`: `held` is the part as
    `GET /bank-lines/{id}` lists it among `parts`.

    The signed amount goes whenever there is one. `category_id` goes when it
    is given and differs from the held one (None keeps the held one);
    `description` when it differs, empty or None going as `""`; `hashtag_ids`
    only when the set differs from the held one, the pending hashtag left out
    on both sides, since it is what a part with no real hashtag carries."""
    body: dict = {"id": str(held["id"])}
    if amount_cents is not None:
        body["amount_cents"] = amount_cents
    if category_id is not None and category_id != held.get("category_id"):
        body["category_id"] = category_id
    if (description or "") != (held.get("description") or ""):
        body["description"] = description or ""
    tags = hashtags_to_send(hashtag_ids, pending_hashtag_id, pending_alone=False)
    held_tags = hashtags_to_send(
        (str(t) for t in held.get("hashtag_ids") or ()), pending_hashtag_id, pending_alone=False
    )
    if set(tags) != set(held_tags):
        body["hashtag_ids"] = tags
    return body


def line_body(parts: list[dict], line_fields: Mapping[str, object] | None = None) -> dict:
    """The whole body: the line fields given, each one the screen changed,
    then `parts`. A key that is not one of `LINE_FIELDS` is a bug in the
    caller, refused here before anything is sent."""
    fields = dict(line_fields or {})
    unknown = set(fields) - LINE_FIELDS
    if unknown:
        raise ValueError(f"not a line field of PUT /bank-lines/{{id}}: {sorted(unknown)}")
    return {**fields, "parts": parts}
