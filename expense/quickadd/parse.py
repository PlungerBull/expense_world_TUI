"""Pure parsing: one typed line -> ParsedLine. No I/O, no HTTP, no Textual.

The grammar:

    tottus -38.60 $signature %usd @korakuen #caja hoy
    title  amount $account   %cur @category #tag  when

`//` opens a note that runs to the end of the line. A sign is what *makes* a
number an amount, and the first sign wins. `$`, `%`, `@` and the date are
first-wins; `#` is the only repeatable token. Whatever is left, in order, is
the title.

`%` names the currency, from the currencies of the account the line names. A
whole or partial code picks one of them; a well-formed code the account does not
hold is upper-cased and sent, and the engine refuses it (`CURRENCY_NOT_HELD`). A
line with no `%` names no currency (`ParsedLine.currency_code` is None and the write leaves
it out for the engine to fill), and is `missing` its currency when it holds several
(`ParsedLine.account_currencies` lists them): the parser never guesses between currencies.

Names are matched against the reference lists the caller already holds —
nothing is created here, and an unmatched name is reported rather than
guessed. Spans come back with every token so a caller can colour the line
without parsing it again.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as date_cls

from expense.currencies import only_currency
from expense.number_format import DEFAULT_FORMAT, NumberFormat, current_format
from expense.quickadd.money import parse_amount
from expense.quickadd.names import fold
from expense.quickadd.when import parse_date

# A sign only starts an amount at a token boundary, which is what keeps
# `coca-cola`, `T-800` and `covid-19` titles while `-30` is money. The `$` is
# decoration the account already settles, so `-$1800` is `-1800`.
# A signed exponent form (`-1e5`) or `inf`/`nan` is amount-shaped too, so it is
# reported as an amount `parse_amount` cannot read, never left in the title.
_AMOUNT = re.compile(
    r"^[+-]\$?(?:[0-9][0-9,.]*(?:e[+-]?[0-9]+)?|inf(?:inity)?|nan)$", re.IGNORECASE
)
_SIGILS = ("$", "%", "@", "#")
# A currency code as the engine takes one: three letters. What a `%` word that
# names none of the account's currencies may still be, to be sent as typed.
_CODE = re.compile(r"^[A-Za-z]{3}$")

# What a line needs to become a ledger row: a signed amount and an account.
# Title and category are optional — a row with no category
# is filed under @Pendiente by the engine, and a row with no title is a
# titleless row (docs/decisions.md "A sparse line is a ledger row").
REQUIRED = ("amount", "account")


@dataclass(frozen=True)
class Span:
    """One token's place in the source line, for colouring.

    `kind` is amount | account | currency | category | hashtag | note | date | title.
    `resolved` is False only for a reference name that found no single match,
    or a date-shaped word that is not a real date — the error slot.
    """

    kind: str
    start: int
    end: int
    text: str
    resolved: bool = True


@dataclass(frozen=True)
class Unresolved:
    """A token that named something the reference lists do not contain.

    `candidates` is empty when nothing matched and holds every hit when
    several did — the picker's input either way. A candidate is `(id, name)`; a
    currency's is `(code, code)`.
    """

    kind: str
    text: str
    span: Span
    candidates: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class ParsedLine:
    title: str
    amount_cents: int | None
    account_id: str | None
    category_id: str | None
    hashtag_ids: tuple[str, ...]
    note: str | None
    date: str
    date_given: bool
    spans: tuple[Span, ...]
    unresolved: tuple[Unresolved, ...]
    missing: tuple[str, ...]
    # The first signed, amount-shaped token `parse_amount` could not read
    # (`-13.853,20`), as typed; it stays a title word. None when there is none.
    unreadable_amount: str | None = None
    # The line's currency as typed: the `%` token's. None when the line names none; the
    # write then leaves `currency_code` out and the engine fills an account's only
    # currency (`currency` is in `missing` when the account holds several).
    currency_code: str | None = None
    # The currencies the named account holds, in the order given; empty until the
    # line names an account. The picker's list for `%`, and the refusal's.
    account_currencies: tuple[str, ...] = ()
    # The named account's name as the account list gives it; empty until the line
    # names one. The refusal for a missing currency says whose currencies they are.
    account_name: str = ""
    # The format the amount was read in; the refusal for an unreadable one names it.
    number_format: NumberFormat = DEFAULT_FORMAT

    @property
    def shown_currency(self) -> str | None:
        """The currency the line shows: the typed one, else the only one its account
        holds. A display read; the write sends only the typed one."""
        return self.currency_code or only_currency(self.account_currencies)

    @property
    def is_complete(self) -> bool:
        """Every required field present and every name resolved.

        Routing is the screen's call, not this module's: a complete row is
        still refused when it is dated ahead (docs/decisions.md "A sparse line
        is a ledger row").
        """
        return not self.missing and not self.unresolved


@dataclass(frozen=True)
class _Entry:
    id: str
    name: str
    key: str
    words: int
    # The codes the account holds; empty for a category or a hashtag.
    currencies: tuple[str, ...] = ()


def _entries(rows: Sequence[Sequence]) -> list[_Entry]:
    """`(id, name, …)` rows -> match entries. An account row is `(account_id, name,
    (code, …))`, the account with the currencies it holds; any other extra column is
    ignored."""
    out: list[_Entry] = []
    for row in rows:
        if len(row) < 2:
            continue
        ident, name = row[0], row[1]
        if not isinstance(ident, str) or not isinstance(name, str):
            continue
        key = fold(" ".join(name.split()))
        if not key:
            continue
        third = row[2] if len(row) > 2 else None
        held = (
            tuple(c for c in third if isinstance(c, str))
            if isinstance(third, (tuple, list))
            else ()
        )
        out.append(_Entry(id=ident, name=name, key=key, words=len(key.split()), currencies=held))
    return out


def _lookahead(words: list[tuple[int, int, str]], start: int, limit: int) -> int:
    """How many words after `start` a multi-word name may swallow.

    Stops at another sigil or at an amount, so a name never eats `-38.60` or
    the `@category` that follows it.
    """
    taken = 0
    index = start + 1
    while taken < limit - 1 and index < len(words):
        text = words[index][2]
        if text[0] in _SIGILS or _AMOUNT.match(text):
            break
        taken += 1
        index += 1
    return taken


def _resolve(
    words: list[tuple[int, int, str]], start: int, head: str, entries: list[_Entry]
) -> tuple[int, list[_Entry]]:
    """Longest-first name matching. Returns (words consumed, hits).

    An exact name wins outright at the longest length that has one; failing
    that, "contains anywhere" at the longest length with any hit (the rule
    every existing picker already uses).
    """
    limit = max((e.words for e in entries), default=1)
    extra = _lookahead(words, start, limit)
    phrases: list[tuple[int, str]] = []
    for k in range(extra, -1, -1):
        parts = [head] + [words[start + i][2] for i in range(1, k + 1)]
        phrases.append((k + 1, fold(" ".join(" ".join(parts).split()))))

    for count, phrase in phrases:
        hits = [e for e in entries if phrase == e.key]
        if hits:
            return count, hits
    for count, phrase in phrases:
        hits = [e for e in entries if phrase in e.key]
        if hits:
            return count, hits
    return 1, []


def parse(
    line: str,
    *,
    accounts: Sequence[Sequence],
    categories: Sequence[Sequence],
    hashtags: Sequence[Sequence],
    today: date_cls,
    number_format: NumberFormat | None = None,
) -> ParsedLine:
    """Read one quick-add line into the fields a transaction needs.

    The three reference arguments are `(id, name)` sequences the caller
    already holds; `today` is injected so the result is deterministic. The amount
    is read in `number_format`, the session's current one when not given.
    """
    number_format = number_format or current_format()
    spans: list[Span] = []
    unresolved: list[Unresolved] = []

    body, note, note_span = _split_note(line)
    if note_span is not None:
        spans.append(note_span)

    refs = {
        "account": _entries(accounts),
        "category": _entries(categories),
        "hashtag": _entries(hashtags),
    }
    sigil_kind = {"$": "account", "%": "currency", "@": "category", "#": "hashtag"}

    words = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", body)]
    title_words: list[str] = []
    amount_cents: int | None = None
    picked: dict[str, str | None] = {"account": None, "category": None}
    held: tuple[str, ...] = ()
    account_name = ""
    typed_currency: tuple[int, int, str] | None = None
    hashtag_ids: list[str] = []
    iso: str | None = None
    bad_date = False
    unreadable_amount: str | None = None

    index = 0
    while index < len(words):
        start, end, text = words[index]
        head = text[1:]
        kind = sigil_kind.get(text[0])

        # `$` splits on the next character: digits are money decoration the
        # account already settles, letters name an account. Safe because no
        # account name starts with a digit.
        if kind == "account" and head[:1].isdigit():
            kind = None

        # The currency is read once the account is known, whichever comes first.
        if kind == "currency" and typed_currency is None:
            typed_currency = (start, end, text)
            index += 1
            continue

        if kind in ("account", "category", "hashtag") and (
            kind == "hashtag" or picked.get(kind) is None
        ):
            if head:
                count, hits = _resolve(words, index, head, refs[kind])
            else:
                # A bare sigil means *show me what there is*. It
                # names nothing, so it can never resolve — it stands unresolved
                # carrying every candidate, which is exactly a picker's input.
                # No lookahead: the token is the one character.
                count, hits = 1, list(refs[kind])
            last = words[index + count - 1][1]
            typed = body[start:last]
            # A name is required before anything can resolve. `len(hits) == 1`
            # alone let a bare `$` pick the only account there is instead of
            # opening the picker the sigil was typed to open — and a one-entry
            # reference list is the ordinary state of a new ledger.
            resolved = bool(head) and len(hits) == 1
            span = Span(kind, start, last, typed, resolved=resolved)
            spans.append(span)
            if resolved:
                if kind == "hashtag":
                    # The same tag twice is a slip, not an error — dedupe it.
                    if hits[0].id not in hashtag_ids:
                        hashtag_ids.append(hits[0].id)
                else:
                    picked[kind] = hits[0].id
                    if kind == "account":
                        held = hits[0].currencies
                        account_name = hits[0].name
            else:
                unresolved.append(
                    Unresolved(
                        kind=kind,
                        text=typed[1:],
                        span=span,
                        candidates=tuple((h.id, h.name) for h in hits),
                    )
                )
            index += count
            continue

        if amount_cents is None and _AMOUNT.match(text):
            cents = parse_amount(text.replace("$", ""), number_format)
            if cents is not None:
                amount_cents = cents
                spans.append(Span("amount", start, end, text))
                index += 1
                continue
            if unreadable_amount is None:
                unreadable_amount = text

        if iso is None and not bad_date:
            found, looked = parse_date(text, today)
            if looked:
                iso = found
                bad_date = found is None
                span = Span("date", start, end, text, resolved=not bad_date)
                spans.append(span)
                if bad_date:
                    unresolved.append(Unresolved(kind="date", text=text, span=span))
                index += 1
                continue

        title_words.append(text)
        spans.append(Span("title", start, end, text))
        index += 1

    currency_code = None
    if typed_currency is not None:
        c_start, c_end, c_text = typed_currency
        currency_code, c_hits = _pick_currency(c_text[1:], held)
        c_span = Span("currency", c_start, c_end, c_text, resolved=currency_code is not None)
        spans.append(c_span)
        if currency_code is None:
            unresolved.append(
                Unresolved(
                    kind="currency",
                    text=c_text[1:],
                    span=c_span,
                    candidates=tuple((c, c) for c in c_hits),
                )
            )

    title = " ".join(title_words)
    values = {
        "amount": amount_cents,
        "account": picked["account"],
    }
    missing = [k for k in REQUIRED if values[k] is None]
    if typed_currency is None and len(held) > 1 and picked["account"] is not None:
        missing.append("currency")
    return ParsedLine(
        title=title,
        amount_cents=amount_cents,
        account_id=picked["account"],
        category_id=picked["category"],
        hashtag_ids=tuple(hashtag_ids),
        note=note,
        date=iso or today.isoformat(),
        date_given=iso is not None,
        spans=tuple(sorted(spans, key=lambda s: s.start)),
        unresolved=tuple(unresolved),
        missing=tuple(missing),
        unreadable_amount=unreadable_amount,
        number_format=number_format,
        currency_code=currency_code,
        account_currencies=held if picked["account"] is not None else (),
        account_name=account_name,
    )


def _pick_currency(word: str, held: tuple[str, ...]) -> tuple[str | None, tuple[str, ...]]:
    """A `%` word against the account's currencies -> (code, candidates).

    The same matching as every name (`_resolve`). One hit resolves. A bare `%` names
    nothing and offers every currency the account holds. A word that hits none of
    them but is a well-formed code is upper-cased and carried, for the engine to
    refuse if the account does not hold it; anything else is unresolved, with the
    hits as candidates.
    """
    if not word:
        return None, held
    _, found = _resolve([(0, len(word), word)], 0, word, _entries([(c, c) for c in held]))
    hits = [e.id for e in found]
    if len(hits) == 1:
        return hits[0], ()
    if not hits and _CODE.match(word):
        return word.upper(), ()
    return None, tuple(hits)


def _split_note(line: str) -> tuple[str, str | None, Span | None]:
    """Everything after the first space-preceded `//` is the description.

    The space is what lets a pasted `https://…` stay in the title.
    """
    for i in range(len(line) - 1):
        if line[i : i + 2] == "//" and (i == 0 or line[i - 1].isspace()):
            text = line[i + 2 :].strip()
            return line[:i], text or None, Span("note", i, len(line), line[i:])
    return line, None, None
