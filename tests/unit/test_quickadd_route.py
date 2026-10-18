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
    PART_KEEPS_LINE,
    PART_KEEPS_TITLE,
    REFUSED,
    describe,
    route,
    route_part,
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


# ---- one part of a split purchase (expense-world-split-action.html screen 2 B) ----


def _part(line):
    parsed = parse(line, accounts=ACCOUNTS, categories=CATEGORIES, hashtags=HASHTAGS, today=TODAY)
    return route_part(parsed)


def test_a_part_with_an_amount_category_tags_and_note_joins_the_parts():
    result = _part("-40 @korakuen #caja #taxi //lejía y papel")
    assert (result.target, result.reasons) == (LEDGER, ())


def test_a_part_needs_only_its_amount():
    assert _part("-40").target == LEDGER
    assert _part("+20").target == LEDGER


def test_a_part_with_no_amount_is_refused_with_the_bars_own_phrase():
    result = _part("@korakuen")
    assert result.refused
    assert result.reasons == ("the line has no amount — a number needs a sign to be one",)


@pytest.mark.parametrize(
    "line",
    ["-40 $BCP PEN", "-40 $nowhere", "-40 hoy", "-40 18/8/2026", "-40 31/02/2026"],
    ids=["account", "unknown-account", "date-word", "date", "not-a-real-date"],
)
def test_a_part_naming_an_account_or_a_date_is_refused(line):
    """Every part keeps the transaction's account and date, so a line naming
    either, even one that matches nothing, says so once."""
    result = _part(line)
    assert result.refused
    assert result.reasons == (PART_KEEPS_LINE,)
    assert PART_KEEPS_LINE == "a part keeps the transaction's account and date"


def test_a_part_with_title_words_is_refused():
    result = _part("-40 lejía")
    assert result.refused
    assert result.reasons == (PART_KEEPS_TITLE,)


def test_an_unresolved_category_or_tag_is_described_as_on_the_bar():
    result = _part("-40 @nada #nunca")
    assert result.refused
    assert result.reasons == ('"@nada" matches no categories', '"#nunca" matches no hashtags')


def test_a_part_never_checks_the_total():
    """Whether the parts add up is the engine's: any signed amount joins."""
    assert _part("-999999.99").target == LEDGER
