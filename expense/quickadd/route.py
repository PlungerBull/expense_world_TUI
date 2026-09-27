"""Whether a parsed line can be staged: the ledger, or refused.

One copy of the rule for both surfaces — the flat `expense log "…"` asks it
once per line, the TUI LOG bar asks it on `↵` and either stages the row or
leaves the line in the bar with the reason under it.

The rule (docs/decisions.md "A sparse line is a ledger row"): a
row reaches the ledger when it has an **amount** and an **account**, every
name it typed resolved, and its date is not ahead of today. A missing title
or category is not a reason — the engine stores a titleless row as null and
files an uncategorised one under `@Pendiente`, and both count. Everything
else is **refused**: the line stays where you can fix it.

Deliberately not a method on `ParsedLine`: routing needs `today`, and the
parser's job ends at "what does this line say".
"""

from dataclasses import dataclass
from datetime import date as date_cls

from expense.quickadd.parse import ParsedLine, Unresolved

LEDGER = "ledger"
REFUSED = "refused"

_SIGIL = {"account": "$", "category": "@", "hashtag": "#"}
_MISSING_PHRASE = {
    "amount": "the line has no amount — a number needs a sign to be one",
    "account": "the line names no account",
}


@dataclass(frozen=True)
class Routing:
    """Where the row goes, and the phrases that say why it is not the ledger.

    `reasons` is empty for a ledger row. Each reason is a finished sentence
    fragment a caller can print as-is — the flat command puts them under the
    echo, the LOG bar puts them under the bar.
    """

    target: str
    reasons: tuple[str, ...] = ()

    @property
    def refused(self) -> bool:
        return self.target == REFUSED


def route(parsed: ParsedLine, today: date_cls) -> Routing:
    """Ledger when it has an amount and an account, resolves, and is not dated
    ahead; refused otherwise."""
    reasons: list[str] = []

    for field in parsed.missing:
        # An unresolved name already explains itself below — reporting the
        # same account twice ("names no account" + "matches 2") reads as two
        # problems when there is one.
        if any(u.kind == field for u in parsed.unresolved):
            continue
        reasons.append(_MISSING_PHRASE[field])

    for token in parsed.unresolved:
        reasons.append(describe(token))

    if parsed.date > today.isoformat():
        reasons.append("it is dated ahead")

    return Routing(REFUSED if reasons else LEDGER, tuple(reasons))


def describe(token: Unresolved) -> str:
    """One unresolved token as a phrase: `"$sig" matches 2 accounts`.

    Zero candidates and several read differently on purpose — one is a typo,
    the other is a name that needs more of itself typed. A **bare sigil** names
    nothing, so it gets its own phrase — it is not a failed match, it is a
    token you have not finished. One wording has to serve both
    readers: the picker header above the list, and the refusal under the bar.
    """
    if token.kind == "date":
        return f'"{token.text}" is not a real date'

    plural = f"{token.kind}s" if token.kind != "category" else "categories"
    if not token.text:
        return f'"{_SIGIL[token.kind]}" names no {token.kind} yet'

    typed = f"{_SIGIL[token.kind]}{token.text}"
    if not token.candidates:
        return f'"{typed}" matches no {plural}'
    return f'"{typed}" matches {len(token.candidates)} {plural}'
