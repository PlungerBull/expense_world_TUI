"""The whole-line write's body, `expense/bank_line_write.py`: a kept part under
its own id with only what changed, a new part sparse under a fresh id, the line
fields beside `parts` and nothing else
(contract: PUT /v1/bank-lines/{bank_line_id}, "Parts").
"""

import re
import subprocess
import uuid
from pathlib import Path

import pytest

from expense.bank_line_write import LINE_FIELDS, kept_part, line_body, new_part
from tests.contract.test_contract_citations import repo_files
from tests.unit.helpers import import_part

PACKAGE = Path(__file__).resolve().parents[2] / "expense"

#: A part as `GET /bank-lines/{id}` lists it: COMIDA, #casa, a note.
HELD = import_part(
    "p1", -6000, line="bl-9", category_id="c-com", hashtag_ids=("h-casa",), description="verduras"
)
#: A part under `@Pendiente`, on the pending hashtag alone, with no note.
HELD_PENDING = import_part("p2", -4000, line="bl-9", category_id="c-pend", hashtag_ids=("h-pend",))


def _kept(held=HELD, **changes) -> dict:
    values = {
        "amount_cents": -6000,
        "category_id": "c-com",
        "description": "verduras",
        "hashtag_ids": ("h-casa",),
        **changes,
    }
    return kept_part(held, pending_hashtag_id="h-pend", **values)


def test_a_kept_part_left_alone_sends_its_id_and_amount_alone():
    assert _kept() == {"id": "p1", "amount_cents": -6000}


def test_a_kept_part_on_the_pending_hashtag_left_alone_sends_no_hashtags():
    """The pending hashtag alone is what a part with no real hashtag carries,
    so an untouched part holding it sends none."""
    assert kept_part(
        HELD_PENDING,
        amount_cents=-4000,
        category_id=None,
        description=None,
        hashtag_ids=("h-pend",),
        pending_hashtag_id="h-pend",
    ) == {"id": "p2", "amount_cents": -4000}


@pytest.mark.parametrize(
    ("changes", "sent"),
    [
        ({"amount_cents": -7000}, {"amount_cents": -7000}),
        ({"category_id": "c-hog"}, {"category_id": "c-hog"}),
        ({"description": "fruta"}, {"description": "fruta"}),
        ({"description": None}, {"description": ""}),
        ({"description": ""}, {"description": ""}),
        ({"hashtag_ids": ("h-casa", "h-merc")}, {"hashtag_ids": ["h-casa", "h-merc"]}),
        ({"hashtag_ids": ()}, {"hashtag_ids": []}),
    ],
    ids=["amount", "category", "note", "note-none", "note-empty", "hashtags", "no-hashtags"],
)
def test_a_kept_part_sends_each_field_it_changed(changes, sent):
    assert _kept(**changes) == {"id": "p1", "amount_cents": -6000, **sent}


def test_a_kept_part_s_hashtags_in_another_order_are_no_change():
    held = {**HELD, "hashtag_ids": ["h-a", "h-b"]}
    assert "hashtag_ids" not in _kept(held, hashtag_ids=("h-b", "h-a"))


def test_a_kept_part_s_category_none_keeps_the_one_it_holds():
    """`null` on a kept part's category is refused (`NOT_NULL`), so None is
    never sent."""
    assert "category_id" not in _kept(category_id=None)


def test_a_kept_part_with_no_amount_sends_none_and_the_engine_answers():
    assert _kept(amount_cents=None) == {"id": "p1"}


def test_a_new_part_is_sparse_under_a_fresh_id():
    full = new_part(
        amount_cents=-1000, category_id="c-hog", description="papel", hashtag_ids=["h-casa"]
    )
    assert uuid.UUID(full.pop("id"))
    assert full == {
        "amount_cents": -1000,
        "category_id": "c-hog",
        "description": "papel",
        "hashtag_ids": ["h-casa"],
    }
    bare = new_part(amount_cents=-1000)
    assert set(bare) == {"id", "amount_cents"}
    assert new_part(amount_cents=None, description="")["id"] != bare["id"]
    assert set(new_part(amount_cents=None, description="")) == {"id"}


def test_the_body_is_the_line_fields_given_then_parts():
    parts = [{"id": "p1", "amount_cents": -6000}]
    assert line_body(parts) == {"parts": parts}
    assert line_body(parts, {"title": "Tottus"}) == {"title": "Tottus", "parts": parts}
    assert LINE_FIELDS == {
        "title",
        "date",
        "account_id",
        "currency_code",
        "operation_code",
        "statement_id",
    }
    # a currency moves the line beside, or without, the account
    # (contract: PUT /v1/bank-lines/{bank_line_id}, "Body")
    assert line_body(parts, {"currency_code": "USD", "statement_id": None}) == {
        "currency_code": "USD",
        "statement_id": None,
        "parts": parts,
    }


@pytest.mark.parametrize("key", ["statement_line", "statement_place", "amount_cents"])
def test_the_body_refuses_any_key_the_write_does_not_take_as_a_line_field(key):
    with pytest.raises(ValueError, match=key):
        line_body([], {key: "x"})


#: A path or a citation naming the split route: a transaction's own path under
#: `/transactions/` ending in `/split`. The id stops at a quote, so this
#: pattern's own line names nothing.
SPLIT_ROUTE = re.compile(r"/transactions/[^\s\"'`]*/split")


def _split_route_hits(root: Path) -> list[str]:
    """`file:line` for each line under `root`, a git work tree, naming the split
    route, over every file `repo_files` reads."""
    return [
        f"{rel}:{number}"
        for rel, text in sorted(repo_files(root).items())
        for number, line in enumerate(text.splitlines(), 1)
        if SPLIT_ROUTE.search(line)
    ]


def test_nothing_in_the_repo_names_the_split_route():
    """Every rewrite of a line's parts goes through the whole-line write
    (contract: PUT /v1/bank-lines/{bank_line_id}, "Parts"), so no file in the
    repo (code, tests, scripts, docs, mockups) names a per-transaction split
    route, as a call or as a citation. The files are the ones the citation check
    reads: every tracked or new text file but docs/from-engine/, the engine's own
    words, and the citation check itself."""
    assert _split_route_hits(PACKAGE.parent) == []


def test_the_scan_names_each_file_and_line_holding_the_split_route(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    route = "/transactions/t-1" + "/split"
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text(f"one\nsee `POST /v1{route}`\n")
    (tmp_path / "app.py").write_text(f'client.post("{route}")\n')
    (tmp_path / "clean.py").write_text('client.put("/bank-lines/bl-1")\n')
    assert _split_route_hits(tmp_path) == ["app.py:1", "docs/notes.md:2"]
