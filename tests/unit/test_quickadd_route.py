"""Whether a parsed line can be staged — the rule both quick-add surfaces share.

The routing table, not the grammar: `test_quickadd_parse.py` owns what a line
*says*, this file owns what happens to it. Pure — no HTTP, no config.

There are two answers (docs/decisions.md "A sparse line is a ledger row"): the ledger,
or refused. A missing title or category is not a reason — the engine stores
the one as null and files
the other under @Pendiente.
"""

from datetime import date

import pytest

from expense.quickadd.parse import Span, Unresolved, parse
from expense.quickadd.route import (
    LEDGER,
    REFUSED,
    describe,
    route,
)

ACCOUNTS = [
    ("a-pen", "BCP Signature PEN", "PEN"),
    ("a-usd", "BCP Signature USD", "USD"),
    ("a-bcp", "BCP PEN", "PEN"),
]
CATEGORIES = [("c-kor", "KORAKUEN"), ("c-tra", "TRANSPORTE")]
HASHTAGS = [("h-caja", "CAJA CHICA"), ("h-taxi", "TAXI")]
TODAY = date(2026, 8, 20)


def _route(line, *, today=TODAY):
    parsed = parse(line, accounts=ACCOUNTS, categories=CATEGORIES, hashtags=HASHTAGS, today=today)
    return route(parsed, today)


def test_complete_and_dated_today_reaches_the_ledger():
    result = _route("tottus -38.60 $BCP Signature PEN @korakuen #caja hoy")
    assert result.target == LEDGER
    assert result.reasons == ()
    assert not result.refused


def test_a_past_date_is_still_the_ledger():
    assert _route("tottus -38.60 $BCP PEN @korakuen 18/8/2026").target == LEDGER


def test_no_category_is_the_ledger_it_lands_under_pendiente():
    result = _route("apparka mall -3.50 $BCP PEN #taxi")
    assert result.target == LEDGER
    assert result.reasons == ()


def test_no_title_is_the_ledger_a_titleless_row():
    result = _route("-6.60 $BCP PEN")
    assert result.target == LEDGER
    assert result.reasons == ()


def test_dated_ahead_is_refused_even_when_complete():
    result = _route("alquiler -1800 $BCP PEN @hogar manana")
    assert result.target == REFUSED
    assert "it is dated ahead" in result.reasons


def test_each_missing_required_field_is_its_own_reason():
    result = _route("apparka")
    assert result.target == REFUSED
    assert result.reasons == (
        "the line has no amount — a number needs a sign to be one",
        "the line names no account",
    )


def test_a_number_without_a_sign_is_not_an_amount():
    """The sign is what makes a number money — 'gasté 38' is a title."""
    result = _route("gaste 38 $BCP PEN @korakuen")
    assert result.target == REFUSED
    assert "the line has no amount — a number needs a sign to be one" in result.reasons


@pytest.mark.parametrize(
    ("line", "token"),
    [
        ("tottus -13.853,20 $BCP PEN", "-13.853,20"),
        ("bonus +1.000,00 $BCP PEN", "+1.000,00"),
        ("tottus -$13.853,20 $BCP PEN", "-$13.853,20"),  # named as typed
        ("tottus -1.2.3 -13.853,20 $BCP PEN", "-1.2.3"),  # the first one is named
    ],
)
def test_a_signed_number_it_cannot_read_is_named(line, token):
    """The number has its sign, so the note names what it could not read
    instead of saying a number needs a sign."""
    result = _route(line)
    assert result.target == REFUSED
    assert result.reasons == (f"can't read {token} as an amount",)


def test_a_readable_amount_after_an_unreadable_one_routes_to_the_ledger():
    """A later amount still reads, so the line has one and nothing is refused."""
    assert _route("tottus -13.853,20 -13853.20 $BCP PEN").reasons == ()


def test_an_ambiguous_name_says_how_many_it_matched():
    result = _route("tottus -38.60 $signature @korakuen")
    assert result.reasons == ('"$signature" matches 2 accounts',)


def test_a_name_that_matched_nothing_reads_differently():
    """A typo and a too-short name are different problems with different fixes."""
    result = _route("tottus -38.60 $nowhere @korakuen")
    assert result.reasons == ('"$nowhere" matches no accounts',)


def test_an_unresolved_name_is_not_also_reported_as_missing():
    """`missing` and `unresolved` both name the account; the reader sees one."""
    result = _route("tottus -38.60 $signature")
    assert result.reasons == ('"$signature" matches 2 accounts',)


def test_an_unmatched_hashtag_refuses_the_line():
    """Optional, but never invented — a typo would otherwise become a tag."""
    result = _route("tottus -38.60 $BCP PEN @korakuen #nope")
    assert result.target == REFUSED
    assert result.reasons == ('"#nope" matches no hashtags',)


def test_the_plural_of_category_reads_as_english():
    """ "2 categorys" would be the giveaway that a machine wrote the sentence."""
    result = _route("tottus -38.60 $BCP PEN @o")
    assert result.reasons == ('"@o" matches 2 categories',)


def test_an_impossible_date_refuses_rather_than_sliding_into_the_title():
    result = _route("tottus -38.60 $BCP PEN @korakuen 32/13/2026")
    assert result.target == REFUSED
    assert '"32/13/2026" is not a real date' in result.reasons


def test_several_problems_are_all_reported():
    result = _route("-3.50 $signature manana")
    assert result.target == REFUSED
    assert len(result.reasons) == 2  # ambiguous account, dated ahead


def test_a_bare_sigil_reads_as_unfinished_not_as_a_failed_match():
    """One phrase for two readers: the picker header and the refusal line."""
    token = Unresolved(
        kind="hashtag",
        text="",
        span=Span("hashtag", 0, 1, "#", resolved=False),
        candidates=(("h1", "TAXI"), ("h2", "CAJA")),
    )
    assert describe(token) == '"#" names no hashtag yet'
