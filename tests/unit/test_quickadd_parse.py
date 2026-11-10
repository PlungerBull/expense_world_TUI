"""Pure grammar tests for expense/quickadd/ — no Textual, no network, no clock.

The checklist is docs/decisions.md "Three quick-add grammar rules". `today` is passed in, so
nothing here depends on the machine's date.
"""

from datetime import date

import pytest

from expense.number_format import NumberFormat
from expense.quickadd.money import amount_to_text, parse_amount
from expense.quickadd.names import fold, matches
from expense.quickadd.parse import named_on, parse
from expense.quickadd.payload import transaction_payload
from expense.quickadd.when import format_date_words, parse_date

TODAY = date(2026, 8, 20)
DOT = NumberFormat.DOT_DECIMAL
COMMA = NumberFormat.COMMA_DECIMAL

# Two accounts share "Signature" so `$sig` is genuinely ambiguous;
# "CAJA" is a prefix of "CAJA CHICA" so exact-beats-contains gets exercised.
ACCOUNTS = [
    ("a1", "BCP Signature Platinum", ("USD",)),
    ("a2", "BCP Plus", ("PEN",)),
    ("a3", "Mi Signature", ("PEN",)),
    ("a4", "Nico", ("PEN",)),
    ("a5", "Efectivo", ("PEN",)),
]
CATEGORIES = [("c1", "KORAKUEN"), ("c2", "TRANSPORTE"), ("c3", "WANTS")]
HASHTAGS = [("t1", "CAJA"), ("t2", "TAXI"), ("t3", "CAJA CHICA"), ("t4", "Viajes")]


def _p(line: str, *, today: date = TODAY):
    return parse(line, accounts=ACCOUNTS, categories=CATEGORIES, hashtags=HASHTAGS, today=today)


# --- money ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("-99.92", -9992),
        ("99", 9900),
        ("+12.5", 1250),
        ("0", 0),
        ("abc", None),
        ("", None),
        ("999999999.99", 99999999999),  # no bound of the app's own (contract: "Money amounts")
        ("9" * 25, int("9" * 25) * 100),
        ("+.5", 50),
        ("5.", 500),
    ],
)
def test_parse_amount(text, expected):
    """Signed amounts parse to cents."""
    assert parse_amount(text, DOT) == expected


# --- the amount token -------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("tottus -38.60", -3860),  # the canonical example
        ("bonus +2450", 245000),  # + is income, literally
        ("mercado -1,311.97", -131197),  # thousands separator is part of the charset
        ("alquiler -$1800", -180000),  # $ + digits is decoration, not a currency
        ("coca-cola", None),  # a sign mid-word is a title, not money
        ("T-800", None),
        ("covid-19", None),
        ("recibo 2450", None),  # no sign, no amount
        ("recibo $1800", None),  # ...not even with the money sigil
    ],
)
def test_amount_shapes(line, expected):
    assert _p(line).amount_cents == expected
    if line == "recibo 2450":
        assert _p(line).title == "recibo 2450"  # an unsigned number stays in the title


def test_a_comma_after_the_dot_leaves_the_line_with_no_amount():
    """`-13.853,20` is no amount, so it stays a title word and the line has
    none, as any other unreadable signed number does; a later amount still
    reads."""
    result = _p("tottus -13.853,20")
    assert result.amount_cents is None
    assert result.title == "tottus -13.853,20"
    assert "amount" in result.missing
    assert result.unreadable_amount == "-13.853,20"
    assert _p("tottus -13.853,20 -13853.20").amount_cents == -1385320


@pytest.mark.parametrize("line", ["recibo 2450", "coca-cola", "tottus -38.60", "apparka"])
def test_no_unreadable_amount_when_none_was_typed(line):
    """Only a signed, amount-shaped token the reader refused is recorded: an
    unsigned number, a mid-word sign and a readable amount are not."""
    assert _p(line).unreadable_amount is None


def test_first_sign_wins():
    """`hoy +30 no -30` is +30; the loser stays in the title (docs/todo.md)."""
    result = _p("hoy +30 no -30")
    assert result.amount_cents == 3000
    assert result.title == "no -30"


# --- the reference tokens ---------------------------------------------------


def test_sigils_resolve_to_ids():
    result = _p("tottus -38.60 $efectivo @korakuen #caja")
    assert (result.account_id, result.category_id, result.hashtag_ids) == (
        "a5",
        "c1",
        ("t1",),
    )


def test_dollar_splits_on_the_next_character():
    """Letters name an account, digits are money — no account starts with one."""
    assert _p("x -1 $nico").account_id == "a4"
    assert _p("x -1 $1800").account_id is None


# The engine's names: `<bank_code>-<last4>`, the bank alone with no number yet. `NUMBERS` is
# each account's `numbers` last 4 digits, the current card last, an earlier one before.
BANK_ACCOUNTS = [
    ("b1", "BCP-5678", ("PEN",)),
    ("b2", "BCP-4471", ("PEN",)),
    ("b3", "BCP", ("PEN",)),
    ("b4", "IBK-5678", ("PEN",)),
]
NUMBERS = {"b1": ("1234", "5678"), "b2": ("4471",), "b4": ("5678",)}


def _bank(line: str):
    return parse(
        line,
        accounts=BANK_ACCOUNTS,
        categories=CATEGORIES,
        hashtags=HASHTAGS,
        today=TODAY,
        numbers=NUMBERS,
    )


def test_dollar_finds_a_built_name_by_either_word():
    assert _bank("x -24 $bcp-4471").account_id == "b2"
    assert _bank("x -24 $ibk").account_id == "b4"
    several = _bank("x -24 $bcp-")
    assert several.account_id is None
    assert [c[1] for c in several.unresolved[0].candidates] == ["BCP-5678", "BCP-4471"]


def test_the_exact_name_resolves_beside_names_built_on_it():
    """`$BCP` is the line's text for the account named `BCP`, so it resolves to it."""
    assert _bank("x -24 $BCP").account_id == "b3"


def test_named_on_offers_the_exact_name_and_every_name_built_on_it():
    assert [n for _, n in named_on("bcp", BANK_ACCOUNTS)] == ["BCP-5678", "BCP-4471", "BCP"]
    assert named_on("bcp-", BANK_ACCOUNTS) == []
    assert named_on("nico", ACCOUNTS) == []  # nothing is built on it
    assert named_on("ibk", BANK_ACCOUNTS) == []  # no account is named `IBK`


def test_an_exact_account_name_wins_over_a_name_not_built_on_it():
    """`$nico` is Nico alone; an exact `BC` wins over `BCP-5678`, which is not `BC-…`;
    an exact name beside a longer one that merely contains it still wins."""
    assert _p("x -1 $nico").account_id == "a4"
    parsed = parse(
        "x -1 $bc",
        accounts=[("p1", "BC", ("PEN",)), ("p2", "BCP-5678", ("PEN",))],
        categories=CATEGORIES,
        hashtags=HASHTAGS,
        today=TODAY,
    )
    assert parsed.account_id == "p1"


def test_dollar_and_four_digits_of_a_current_or_earlier_card_find_its_account():
    assert _bank("x -24 $4471").account_id == "b2"  # the current card
    assert _bank("x -24 $1234").account_id == "b1"  # an earlier card of b1


def test_dollar_and_four_digits_shared_by_two_accounts_list_both():
    parsed = _bank("x -24 $5678")
    assert parsed.account_id is None
    assert [c[0] for c in parsed.unresolved[0].candidates] == ["b1", "b4"]


def test_dollar_and_four_digits_matching_no_card_stay_money():
    parsed = _bank("x -24 $9999")
    assert parsed.account_id is None
    assert not parsed.unresolved


def test_dollar_and_other_digits_stay_money():
    """`$56` is not four digits, so it is not a card; a card's last 4 with more digits
    after them is not either."""
    for line in ("x -1 $56", "x -1 $567", "x -1 $56789", "x -1 $5678.5"):
        parsed = _bank(line)
        assert parsed.account_id is None, line
        assert not parsed.unresolved, line
    assert _bank("x $56").title == "x $56"


def test_the_four_digit_match_reads_numbers_not_the_name():
    """An account named like a card but holding no such number is not found by it."""
    parsed = parse(
        "x -24 $5678",
        accounts=BANK_ACCOUNTS,
        categories=CATEGORIES,
        hashtags=HASHTAGS,
        today=TODAY,
        numbers={},
    )
    assert parsed.account_id is None
    assert not parsed.unresolved


def test_multi_word_names_need_no_quotes():
    assert _p("pago -5 $bcp plus").account_id == "a2"
    assert _p("pago -5 #caja chica").hashtag_ids == ("t3",)


def test_exact_name_beats_a_longer_one_that_contains_it():
    """`#caja` is CAJA, not CAJA CHICA — equality wins before contains."""
    assert _p("pago -5 #caja").hashtag_ids == ("t1",)


def test_a_name_never_swallows_the_next_token():
    """The lookahead stops at a sigil or an amount, so `$bcp` cannot eat `-5`."""
    result = _p("$bcp plus -5 @wants")
    assert (result.account_id, result.amount_cents, result.category_id) == ("a2", -500, "c3")


def test_hashtags_repeat_and_the_rest_are_first_wins():
    result = _p("x -5 #caja #taxi #caja $nico $efectivo @wants @korakuen")
    assert result.hashtag_ids == ("t1", "t2")
    assert (result.account_id, result.category_id) == ("a4", "c3")
    # The losing tokens are not silently applied — they read as title text.
    assert result.title == "x $efectivo @korakuen"


@pytest.mark.parametrize(
    ("line", "kind", "text", "candidates"),
    [
        ("x -5 $sig", "account", "sig", 2),  # ambiguous — the picker's case
        ("x -5 $zzz", "account", "zzz", 0),  # nothing matches
        ("x -5 @zzz", "category", "zzz", 0),
        ("x -5 #zzz", "hashtag", "zzz", 0),  # never created behind your back
    ],
)
def test_unresolved_names_are_reported_with_their_candidates(line, kind, text, candidates):
    """No match and several matches both go unresolved, carrying
    whatever was found, so a caller can open a picker on it."""
    (found,) = _p(line).unresolved
    assert (found.kind, found.text, len(found.candidates)) == (kind, text, candidates)


def test_matching_is_contains_anywhere_and_case_insensitive():
    """Contains-anywhere, not whole-name or starts-with, matching every
    existing TUI picker."""
    assert _p("x -5 $ECTIV").account_id == "a5"


# --- the note ---------------------------------------------------------------


def test_note_runs_to_the_end_of_the_line():
    result = _p("cena -5 // pagué yo, dividir después")
    assert result.note == "pagué yo, dividir después"
    assert result.title == "cena"


def test_a_pasted_url_survives():
    """`//` only opens a note after a space — that is what protects https://."""
    result = _p("mira https://x.com/y -12")
    assert result.note is None
    assert result.title == "mira https://x.com/y"


def test_note_at_the_start_of_the_line():
    assert _p("// solo una nota").note == "solo una nota"


# --- the date ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("hoy", "2026-08-20"),
        ("today", "2026-08-20"),
        ("ayer", "2026-08-19"),
        ("yesterday", "2026-08-19"),
        ("mañana", "2026-08-21"),
        ("manana", "2026-08-21"),  # unaccented spelling accepted
        ("tomorrow", "2026-08-21"),
        ("HOY", "2026-08-20"),  # case-insensitive
        ("18/08/2026", "2026-08-18"),  # dd/mm/yyyy
        ("2026/08/18", "2026-08-18"),  # yyyy/mm/dd — 4-digit-first disambiguates
        ("2026-08-18", "2026-08-18"),  # the dashed ISO form
        ("18/08/26", "2026-08-18"),  # yy -> 20yy
        ("28Aug", "2026-08-28"),  # day + month name, this year
        ("28/Aug", "2026-08-28"),  # the separator is optional
        ("28-Aug", "2026-08-28"),  # …and may be a dash, unlike dd-mm-yyyy
        ("28agosto", "2026-08-28"),  # Spanish, like every other date word
        ("28ago", "2026-08-28"),  # any prefix from three letters up
        ("1set", "2026-09-01"),  # setiembre, as it is written in Peru
        ("15DEC", "2026-12-15"),  # case-blind, like the word forms
        ("28Aug26", "2026-08-28"),  # an explicit year still wins
        ("28/ago/2025", "2025-08-28"),
        ("32Aug", None),  # date-shaped but impossible
        ("28Xyz", None),  # not a month — an ordinary word
        ("28/08", None),  # NOT a date: `1/2` and `1/4` are title text
        ("1/2", None),
        ("32/13/2026", None),  # date-shaped but impossible
        ("18-08-2026", None),  # dashes are ISO-only, so this is not a date
        ("tottus", None),  # ordinary word
    ],
)
def test_date_words_and_shapes(word, expected):
    found, _ = parse_date(word, TODAY)
    assert found == expected


def test_omitted_date_is_today_and_says_so():
    result = _p("tottus -5")
    assert (result.date, result.date_given) == ("2026-08-20", False)


def test_first_date_wins():
    assert _p("x -5 ayer mañana").date == "2026-08-19"


def test_an_impossible_date_is_reported_not_swallowed():
    """It neither becomes a title word nor silently defaults to today."""
    result = _p("x -5 32/13/2026")
    assert result.date_given is False
    assert [(u.kind, u.text) for u in result.unresolved] == [("date", "32/13/2026")]
    assert result.title == "x"


# --- the title, and what is left --------------------------------------------


def test_the_rest_is_the_title_in_order():
    assert _p("tottus porongoche -5 $efectivo hoy").title == "tottus porongoche"


def test_missing_lists_only_the_required_fields():
    # amount and account are all a row needs; title and
    # category are optional (docs/decisions.md "A sparse line is a ledger row")
    assert _p("").missing == ("amount", "account")
    assert _p("-5 $efectivo").missing == ()
    assert _p("tottus -5 $efectivo @wants").missing == ()


def test_is_complete_needs_every_name_resolved_too():
    """A row with all four fields but an ambiguous account is not complete —
    routing is still the screen's call."""
    assert _p("tottus -5 $efectivo @wants").is_complete is True
    assert _p("tottus -5 $sig @wants").is_complete is False


# --- spans ------------------------------------------------------------------


def test_spans_cover_every_token_in_source_order():
    """A caller colours the line off these without parsing it again."""
    line = "tottus -38.60 $sig @korakuen #caja hoy // nota"
    spans = [(s.kind, line[s.start : s.end], s.resolved) for s in _p(line).spans]
    assert spans == [
        ("title", "tottus", True),
        ("amount", "-38.60", True),
        ("account", "$sig", False),  # ambiguous -> the error slot
        ("category", "@korakuen", True),
        ("hashtag", "#caja", True),
        ("date", "hoy", True),
        ("note", "// nota", True),
    ]


def test_a_multi_word_span_covers_every_word_it_took():
    (span,) = [s for s in _p("pago -5 $bcp plus").spans if s.kind == "account"]
    assert (span.start, span.end, span.text) == (8, 17, "$bcp plus")


# --- shape of the reference arguments ---------------------------------------


def test_extra_columns_on_a_reference_row_are_ignored():
    """A row's columns past the currencies are ignored."""
    rows = [("a2", "BCP Plus", ("PEN",), "extra", 7)]
    result = parse("x -5 $bcp plus", accounts=rows, categories=[], hashtags=[], today=TODAY)
    assert (result.account_id, result.shown_currency) == ("a2", "PEN")


def test_malformed_reference_rows_are_skipped_not_crashed_on():
    result = parse(
        "x -5 $ok",
        accounts=[("a1",), (None, "Bad"), ("a2", None), ("a3", "  "), ("a4", "OK")],
        categories=[],
        hashtags=[],
        today=TODAY,
    )
    assert result.account_id == "a4"


def test_an_empty_line_parses_to_nothing():
    result = _p("   ")
    assert (result.title, result.amount_cents, result.spans) == ("", None, ())


# --- format_date_words ------------------------------------------------------
# The echo two-digit years lean on: the resolved date is always spelled out
# before the row is committed, so a misread is visible (docs/decisions.md).


@pytest.mark.parametrize(
    ("iso", "words"),
    [
        ("2026-08-18", "Tue 18 Aug 2026"),
        ("2026-01-01", "Thu 1 Jan 2026"),
        ("2026-12-31", "Thu 31 Dec 2026"),
    ],
)
def test_format_date_words(iso, words):
    assert format_date_words(iso) == words


def test_format_date_words_passes_junk_through():
    assert format_date_words("not a date") == "not a date"


# ---- day + month, this year -----------------------------------------------
def test_day_and_month_take_the_current_year_not_a_fixed_one():
    """`28Aug` is August 2026 today and August 2027 next year."""
    assert parse_date("28Aug", date(2027, 1, 5))[0] == "2027-08-28"


def test_a_month_name_that_reaches_two_months_is_not_a_date():
    """Two letters is not enough to name a month, so it stays title text."""
    assert parse_date("28ju", TODAY) == (None, False)


def test_a_bare_month_number_pair_is_not_a_date_because_fractions_exist():
    """`1/2 kilo` must not log a February row."""
    result = _p("medio pollo 1/2 -18")
    assert result.date_given is False
    assert "1/2" in result.title


# ---- the picker's two gaps ------------------------------------------------
def test_a_bare_sigil_stands_unresolved_carrying_every_candidate():
    """Typing `#` alone means *show me what there is* — the picker's input."""
    for sigil, kind, count in (("$", "account", 5), ("@", "category", 3), ("#", "hashtag", 4)):
        result = _p(f"tottus -5 {sigil}")
        assert [(u.kind, len(u.candidates)) for u in result.unresolved] == [(kind, count)]
        assert result.title == "tottus"  # the sigil is not swallowed as a word


def test_names_match_through_accents_both_ways():
    """`#banos` finds `BAÑOS`, and `#baños` still finds itself."""
    tags = [("h9", "BAÑOS")]
    for typed in ("#banos", "#baños", "#BAÑOS"):
        result = parse(
            f"gasfitero -50 {typed}",
            accounts=ACCOUNTS,
            categories=CATEGORIES,
            hashtags=tags,
            today=TODAY,
        )
        assert result.hashtag_ids == ("h9",), typed


def test_fold_is_the_one_copy_every_picker_matches_through():
    """The TUI form pickers import this too — one rule, three call sites."""
    assert fold("BAÑOS") == fold("banos") == "banos"
    assert fold("Café") == "cafe"
    assert matches("nut", "NUTRICIONISTA") and matches("SALUD", "salud")
    assert not matches("xyz", "SALUD")


def test_a_bare_sigil_opens_the_picker_even_when_one_candidate_exists():
    """A bare sigil names nothing, so it cannot resolve — not even against a
    reference list of one, which is the ordinary state of a new ledger. It
    must not pick that sole entry and skip the picker it was typed to open."""
    one_each = dict(
        accounts=[("a1", "BCP Plus", ("PEN",))],
        categories=[("c1", "WANTS")],
        hashtags=[("t1", "TAXI")],
    )
    for sigil, kind in (("$", "account"), ("@", "category"), ("#", "hashtag")):
        result = parse(f"tottus -5 {sigil}", today=TODAY, **one_each)
        assert [(u.kind, len(u.candidates)) for u in result.unresolved] == [(kind, 1)]
    # the account and category are still unset — nothing was silently picked
    result = parse("tottus -5 $", today=TODAY, **one_each)
    assert result.account_id is None


# --- an account is one row, holding its currencies ----------------------------------


def test_a_name_resolves_to_its_one_account_whatever_it_holds():
    result = _banks("-10 $visa")
    assert (result.account_id, result.account_name) == ("v1", "Visa Inventada")
    assert result.unresolved == ()
    assert result.account_currencies == ("PEN", "USD")


# --- the currency: its own token, `%`, from the account's own currencies --------

BANKS = [
    ("v1", "Visa Inventada", ("PEN", "USD")),
    ("c1", "Caja Chica", ("PEN",)),
]


def _banks(line: str):
    return parse(line, accounts=BANKS, categories=CATEGORIES, hashtags=HASHTAGS, today=TODAY)


def test_a_line_naming_an_account_and_a_currency_carries_both():
    result = _banks("Streamly $visa inventada @wants -12.99 hoy %usd")
    assert (result.account_id, result.currency_code) == ("v1", "USD")
    assert result.unresolved == () and result.missing == ()
    assert result.account_currencies == ("PEN", "USD")
    assert [s.kind for s in result.spans if s.kind == "currency"] == ["currency"]


def test_the_currency_token_may_come_before_the_account():
    result = _banks("-5 %pen $visa inventada")
    assert (result.account_id, result.currency_code, result.unresolved) == ("v1", "PEN", ())


def test_a_partial_code_picks_like_every_other_name():
    assert _banks("-5 $visa %u").currency_code == "USD"
    assert _banks("-5 $visa %E").currency_code == "PEN"


def test_a_partial_code_two_currencies_share_is_unresolved_with_both_candidates():
    result = parse(
        "-5 $x %pe",
        accounts=[("x1", "X", ("PEN", "PEX"))],
        categories=CATEGORIES,
        hashtags=HASHTAGS,
        today=TODAY,
    )
    assert result.currency_code is None
    (found,) = result.unresolved
    assert (found.kind, found.text) == ("currency", "pe")
    assert found.candidates == (("PEN", "PEN"), ("PEX", "PEX"))


def test_a_bare_percent_names_no_currency_and_offers_the_accounts_own():
    result = _banks("-5 $visa %")
    assert result.currency_code is None
    (found,) = result.unresolved
    assert (found.kind, found.text) == ("currency", "")
    assert found.candidates == (("PEN", "PEN"), ("USD", "USD"))
    assert found.span.resolved is False


def test_a_one_currency_account_names_no_currency_and_shows_its_only_one():
    result = _banks("Pan $caja chica @wants -4.50 hoy")
    assert (result.account_id, result.currency_code) == ("c1", None)
    assert result.shown_currency == "PEN"
    assert result.missing == () and result.unresolved == ()


def test_a_multi_currency_account_with_no_currency_is_missing_it_never_guessed():
    result = _banks("Streamly $visa inventada -12.99")
    assert result.account_id == "v1" and result.currency_code is None
    assert result.missing == ("currency",)
    assert result.account_currencies == ("PEN", "USD")
    assert not result.is_complete


def test_a_well_formed_code_the_account_does_not_hold_is_carried_for_the_engine():
    result = _banks("-18 $caja chica %usd")
    assert (result.account_id, result.currency_code, result.unresolved) == ("c1", "USD", ())


def test_a_percent_word_that_is_no_code_and_matches_nothing_is_unresolved():
    result = _banks("-18 $caja chica %xx")
    assert result.currency_code is None
    (found,) = result.unresolved
    assert (found.kind, found.candidates) == ("currency", ())


def test_the_currency_is_first_wins_and_a_second_percent_word_is_title():
    result = _banks("a %pen %usd -5 $visa")
    assert result.currency_code == "PEN" and result.title == "a %usd"


def test_a_percent_with_no_account_still_carries_a_well_formed_code():
    result = _banks("-5 %usd")
    assert result.account_id is None and result.currency_code == "USD"
    assert result.missing == ("account",)


def test_an_account_name_does_not_swallow_the_currency_token():
    # "caja chica %usd" would match a three-word name if `%usd` were read as a name word
    result = parse(
        "-5 $caja chica %usd",
        accounts=[("c1", "Caja Chica %usd", ("PEN", "USD")), ("c2", "Caja Chica", ("PEN",))],
        categories=CATEGORIES,
        hashtags=HASHTAGS,
        today=TODAY,
    )
    assert (result.account_id, result.currency_code) == ("c2", "USD")


def test_the_payload_carries_the_account_and_only_a_typed_currency():
    lines = ["-12.99 $visa inventada %usd", "-4.50 $caja chica", "-3 $visa inventada %pen"]
    sent = [transaction_payload(_banks(line), row_id="r", date="2026-10-31") for line in lines]
    assert [(p["account_id"], p.get("currency_code")) for p in sent] == [
        ("v1", "USD"),
        ("c1", None),
        ("v1", "PEN"),
    ]
    assert "currency_code" not in sent[1]  # left out, never a null


@pytest.mark.parametrize(
    "text",
    [
        "1e5000",
        "1e5",
        "-1E+3",
        "inf",
        "-nan",
        "Infinity",
        "1_000",
        "١٢٣",
        "0x10",
        "--5",
        "1.2.3",
        "nan",
        "1e999999",
        "-1E+999999999",
        ".",
        "+",
    ],
)
def test_only_a_plain_number_is_read(text):
    assert parse_amount(text, DOT) is None


def test_a_number_too_long_for_python_to_print_is_unreadable_not_a_crash():
    assert parse_amount("9" * 5000, DOT) is None


@pytest.mark.parametrize("cents", [10**25, -(10**30) - 7, 10**4290, -5, 5, 0, 250])
def test_amount_to_text_is_exact_at_any_size(cents):
    """Integer arithmetic: a large figure never turns to exponent form, so it reads back."""
    text = amount_to_text(cents)
    assert "E" not in text and "e" not in text
    assert parse_amount(text, DOT) == cents


# --- the number format ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("-1,500", -150000),
        ("-1500", -150000),
        ("13,853.20", 1385320),
        ("-1,311.97", -131197),
        ("1,000", 100000),
        ("1,000,000,000", 100000000000),
        ("123,456,789.5", 12345678950),
        ("-0.5", -50),
        ("1,234.", 123400),
        (".5", 50),
        ("1.005", 101),  # the third decimal rounds the cents up
        ("1.004", 100),
    ],
)
def test_dot_decimal_reads_a_group_of_exactly_three_digits(text, cents):
    assert parse_amount(text, DOT) == cents


@pytest.mark.parametrize(
    "text",
    [
        "-1,5",
        "-12,34",
        "-1,23,456",
        "1,2345",
        ",500",
        "1,,000",
        "-1.234,56",
        "13.853,20",
        "+1.000,00",
        "1,234,",
        "1,000.5,0",
        "-0,500",
        "000,500",
        "-01,500",
    ],
)
def test_dot_decimal_refuses_a_misgrouped_or_foreign_mark(text):
    assert parse_amount(text, DOT) is None


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("-1.500", -150000),
        ("-1500", -150000),
        ("13.853,20", 1385320),
        ("-1,5", -150),
        ("+1.000", 100000),
        ("1.234.567,891", 123456789),
        ("1.234,", 123400),
        (",5", 50),
        ("1,005", 101),
        ("0,50", 50),
    ],
)
def test_comma_decimal_mirrors_dot_decimal(text, cents):
    assert parse_amount(text, COMMA) == cents


@pytest.mark.parametrize(
    "text",
    [
        "-1.5",
        "-12.34",
        "-1.23.456",
        "-1,234.56",
        "1.2345",
        ".500",
        "1,2,3",
        "1e5",
        "nan",
        "-inf",
        "0.500",
        "-0.500",
        "000.500",
        "-01.500",
    ],
)
def test_comma_decimal_refuses_a_misgrouped_or_foreign_mark(text):
    assert parse_amount(text, COMMA) is None


@pytest.mark.parametrize("number_format", [DOT, COMMA])
def test_either_format_reads_any_size_and_refuses_what_python_cannot_print(number_format):
    group = number_format.group
    huge = "9" * 25
    grouped = "-" + group.join([huge[:1]] + [huge[i : i + 3] for i in range(1, 25, 3)])
    assert parse_amount(grouped, number_format) == -int(huge) * 100
    assert parse_amount("9" * 5000, number_format) is None


def test_a_format_names_itself_by_example():
    assert DOT.example == "1,234.56"
    assert COMMA.example == "1.234,56"


def test_the_current_format_is_one_session_value():
    from expense import number_format as nf

    assert nf.current_format() is DOT
    nf.set_current_format(COMMA)
    try:
        assert nf.current_format() is COMMA
        assert nf.amounts_are() == "amounts are 1.234,56"
        assert _p("tottus -1.500 $efectivo").amount_cents == -150000
    finally:
        nf.set_current_format(DOT)
