"""scripts/check_fixture_drift.py: the contract-version check and its recording step.

The engine is respx-mocked at the practice engine's address. A route on any other
host is left unmocked on purpose, so a request anywhere else fails the test.

Contracts are built with dict(), not quoted keys: the drift script scans this
folder, and `"info": ...` here would read as a fixture claiming an engine field.
"""

import httpx
import pytest
import respx

from tests.unit.helpers import DRIFT_SCRIPT, load_drift_script

PRACTICE = "http://127.0.0.1:8002"
SAVED = "9d593f48328c0c6a"
MOVED = "0123456789abcdef"


def _contract(version, changelog=None):
    account = dict(properties=dict(name={}, currency={}))
    doc = dict(
        info=dict(title="expense_world_engine", version=version),
        components=dict(schemas=dict(Account=account)),
        paths={},
    )
    if changelog is not None:
        doc["x-changelog"] = changelog
    return doc


def _entry(version, date, *changes):
    return dict(version=version, date=date, changes=[dict(kind=k, text=t) for k, t in changes])


@pytest.fixture
def drift(tmp_path, monkeypatch):
    """The script with its saved-version file and fixture folder moved into tmp_path.

    The fixture folder holds one fixture whose keys the mocked contract serves, so
    the drift half of every run here is clean and the version decides the exit. No
    builder is marked as an endpoint's answer, so the required-field half is clean too.
    """
    module = load_drift_script()
    fixtures = tmp_path / "unit"
    fixtures.mkdir()
    (fixtures / "test_sample.py").write_text('ROW = {"name": "Cash", "currency": "PEN"}\n')
    monkeypatch.setattr(module, "UNIT_TESTS", fixtures)
    monkeypatch.setattr(module, "SAVED_VERSION_FILE", tmp_path / "engine-contract-version")
    monkeypatch.setattr(module, "answer_builders", dict)
    return module


def _serve(version, changelog=None):
    return respx.get(f"{PRACTICE}/openapi.json").mock(
        return_value=httpx.Response(200, json=_contract(version, changelog))
    )


@respx.mock
def test_default_target_is_the_practice_engine(drift):
    route = _serve(SAVED)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.DEFAULT_ENGINE_URL == PRACTICE
    assert drift.main([]) == 0
    assert route.called


@respx.mock
def test_matching_version_passes_quietly(drift, capsys):
    _serve(SAVED)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 0
    out = capsys.readouterr().out
    assert "version" not in out
    assert SAVED not in out
    assert "no fixture claims a field the engine does not serve." in out


@respx.mock
def test_moved_version_fails_with_both_numbers_even_when_fixtures_match(drift, capsys):
    _serve(MOVED)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert f"saved {SAVED}, engine {MOVED}" in out
    assert "no fixture claims a field the engine does not serve." in out
    assert "--record-version" in out


@respx.mock
def test_a_check_never_rewrites_the_saved_version(drift):
    _serve(MOVED)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    drift.main(["--engine-url", PRACTICE])

    assert drift.SAVED_VERSION_FILE.read_text() == SAVED + "\n"


@respx.mock
@pytest.mark.parametrize("content", [None, "", "\n"])
def test_missing_saved_version_fails_and_names_the_recording_step(drift, capsys, content):
    _serve(SAVED)
    if content is not None:
        drift.SAVED_VERSION_FILE.write_text(content)

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert "no saved contract version" in out
    assert f"python scripts/check_fixture_drift.py --engine-url {PRACTICE} --record-version" in out
    assert content is not None or not drift.SAVED_VERSION_FILE.exists()


@respx.mock
def test_record_version_writes_only_the_engine_version_and_checks_nothing(drift, capsys):
    _serve(MOVED, LOG[1:])  # the change log lists MOVED, so it is a released version
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    # A fixture the contract does not serve: a normal check would fail on it.
    (drift.UNIT_TESTS / "test_stale.py").write_text('ROW = {"retired' + '_field": 1}\n')

    assert drift.main(["--engine-url", PRACTICE, "--record-version"]) == 0
    assert drift.SAVED_VERSION_FILE.read_text() == MOVED + "\n"
    out = capsys.readouterr().out
    assert f"recorded contract version {MOVED} (was {SAVED})" in out
    assert "retired_field" not in out


@respx.mock
def test_contract_without_a_version_is_refused(drift):
    respx.get(f"{PRACTICE}/openapi.json").mock(
        return_value=httpx.Response(200, json=dict(info={}, components={}))
    )
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    with pytest.raises(SystemExit, match="published no info.version"):
        drift.main(["--engine-url", PRACTICE])


@respx.mock
def test_unreachable_engine_is_reported(drift):
    respx.get(f"{PRACTICE}/openapi.json").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(SystemExit, match="could not read"):
        drift.main(["--engine-url", PRACTICE])


def test_saved_version_file_holds_only_a_version():
    """The repo keeps the version number and nothing else: one line, one token."""
    lines = (DRIFT_SCRIPT.parent / "engine-contract-version").read_text().splitlines()
    assert len(lines) == 1
    assert lines[0].strip() == lines[0] and lines[0] and " " not in lines[0]


@respx.mock
def test_hook_payload_file_is_not_scanned(drift, capsys):
    """A key used only in test_claude_hooks.py is a hook payload key, not drift."""
    _serve(SAVED)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    payload = 'PAYLOAD = {"tool' + '_name": "Bash"}\n'
    (drift.UNIT_TESTS / "test_claude_hooks.py").write_text(payload)

    assert drift.main(["--engine-url", PRACTICE]) == 0
    assert "tool_name" not in capsys.readouterr().out

    # The same key in any other test file is still reported.
    (drift.UNIT_TESTS / "test_other.py").write_text(payload)
    assert drift.main(["--engine-url", PRACTICE]) == 1
    assert "tool_name" in capsys.readouterr().out


@respx.mock
def test_a_field_passed_by_name_to_a_fields_builder_is_named_but_a_knob_is_not(drift, capsys):
    """A keyword a `**fields` builder spreads into its answer is a key; a named parameter
    of the builder (`dial=`) is a knob, and a builder with no `**fields` is not read."""
    _serve(SAVED)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    (drift.UNIT_TESTS / "helpers.py").write_text(
        "def row(base=None, *, dial=0, **fields):\n"
        "    return {**(base or {}), **fields}\n\n\n"
        "def plain(*, other_knob=0):\n"
        "    return {}\n"
    )
    (drift.UNIT_TESTS / "test_kw.py").write_text(
        "A = row(dial=1, name='x')\nB = row(\n    retired_field=2,\n)\nC = plain(other_knob=1)\n"
    )

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert "retired_field" in out and "test_kw.py:3" in out
    assert "dial" not in out and "other_knob" not in out


NEWEST = "fedcba9876543210"
OLDER = "1111222233334444"
LOG = [
    _entry(NEWEST, "2026-10-02", ("removed", "`GET /legacy`, gone."), ("added", "`sort=amount`.")),
    _entry(MOVED, "2026-10-01", ("changed", "*Date windows*, end date is inclusive.")),
    _entry(SAVED, "2026-09-27", ("added", "`x-changelog` itself.")),
    _entry(OLDER, "2026-09-01", ("added", "an ancient change.")),
]


@respx.mock
def test_moved_version_prints_every_entry_newer_than_saved_newest_first(drift, capsys):
    _serve(NEWEST, LOG)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    expected = "\n".join(
        [
            f"what the contract changed since {SAVED}, newest first:",
            f"  {NEWEST}  2026-10-02",
            "    removed: `GET /legacy`, gone.",
            "    added: `sort=amount`.",
            f"  {MOVED}  2026-10-01",
            "    changed: *Date windows*, end date is inclusive.",
        ]
    )
    assert expected in out
    assert "`x-changelog` itself." not in out
    assert "an ancient change." not in out
    assert "2026-09-27" not in out
    assert "whole contract changed" not in out


@respx.mock
def test_saved_version_absent_from_the_log_means_the_whole_contract_changed(drift, capsys):
    _serve(NEWEST, LOG[:2])
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert "the whole contract changed" in out
    assert f"saved {SAVED}, engine {NEWEST}" in out
    assert "newest first:" not in out


@respx.mock
@pytest.mark.parametrize(
    "changelog",
    [
        None,
        [],
        "not a list",
        dict(version=NEWEST),
        [None],
        [dict(date="2026-10-02")],
        [dict(version=NEWEST, changes=[])],
        [dict(version=NEWEST, date="2026-10-02", changes="added")],
        [dict(version=NEWEST, date="2026-10-02", changes=[dict(kind="added")])],
        [dict(version=NEWEST, date="2026-10-02", changes=["added: text"])],
        [LOG[0], None, LOG[2]],
    ],
    ids=[
        "absent",
        "empty",
        "string",
        "object",
        "null-entry",
        "no-version",
        "no-date",
        "changes-not-a-list",
        "change-without-text",
        "change-not-an-object",
        "later-entry-malformed",
    ],
)
def test_missing_or_malformed_changelog_means_the_whole_contract_changed(drift, capsys, changelog):
    _serve(NEWEST, changelog)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 1
    assert "the whole contract changed" in capsys.readouterr().out


@respx.mock
def test_log_not_starting_at_the_engine_version_means_the_whole_contract_changed(drift, capsys):
    """The engine's first entry is always its current version; if not, the log is not trusted."""
    _serve(NEWEST, LOG[1:])
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert "the whole contract changed" in out
    assert "newest first:" not in out
    assert "*Date windows*" not in out


@respx.mock
def test_matching_version_prints_no_changelog(drift, capsys):
    _serve(SAVED, LOG[2:])
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE]) == 0
    out = capsys.readouterr().out
    assert "changed" not in out
    assert "`x-changelog` itself." not in out


DRAFT = "f00534abdde7fa82"


@respx.mock
@pytest.mark.parametrize(
    "changelog",
    [LOG, None, [], "not a list", [_entry(DRAFT, "2026-10-28"), dict(date="2026-10-01")]],
    ids=["not-listed", "absent", "empty", "string", "listed-beside-an-entry-without-version"],
)
def test_record_version_refuses_a_version_the_change_log_does_not_list(drift, capsys, changelog):
    """A served version the log leaves out may be a draft that never shipped: nothing is saved."""
    _serve(DRAFT, changelog)
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE, "--record-version"]) == 1
    assert drift.SAVED_VERSION_FILE.read_text() == SAVED + "\n"
    out = capsys.readouterr().out
    assert f"not recorded: the engine serves contract version {DRAFT}" in out
    assert "change log (x-changelog) does not list" in out
    assert "may be a draft that never shipped" in out
    assert f"The saved version stays {SAVED}." in out
    assert "recorded contract version" not in out


@respx.mock
def test_record_version_refuses_a_version_listed_but_not_first(drift, capsys):
    _serve(MOVED, LOG)  # LOG's first entry is NEWEST; MOVED is listed second
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    assert drift.main(["--engine-url", PRACTICE, "--record-version"]) == 1
    assert drift.SAVED_VERSION_FILE.read_text() == SAVED + "\n"
    out = capsys.readouterr().out
    assert f"not recorded: the engine serves contract version {MOVED}" in out
    assert "lists it but not as its first entry" in out
    assert f"The saved version stays {SAVED}." in out
    assert "recorded contract version" not in out


@respx.mock
def test_record_version_refused_with_no_saved_version_writes_no_file(drift, capsys):
    _serve(DRAFT, LOG)

    assert drift.main(["--engine-url", PRACTICE, "--record-version"]) == 1
    assert not drift.SAVED_VERSION_FILE.exists()
    assert "The saved version stays none." in capsys.readouterr().out


@respx.mock
@pytest.mark.parametrize("info", ["a string", ["a", "list"], 7])
def test_non_object_info_is_refused_cleanly(drift, info):
    respx.get(f"{PRACTICE}/openapi.json").mock(
        return_value=httpx.Response(200, json=dict(info=info, components={}))
    )
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")

    with pytest.raises(SystemExit, match="published no info.version"):
        drift.main(["--engine-url", PRACTICE])


# ---- a marked answer missing a field its endpoint requires --------------------

CLOSE = "POST /v1/things/{thing_id}/close"


def _answer_contract(version=SAVED):
    """A contract whose `CLOSE` answers a Thing: `name`, `gap` (a Gap or null) and
    `items` (a list of Items) required, and Gap and Item each requiring their own."""
    gap = dict(properties=dict(first={}, count={}), required=["first", "count"])
    item = dict(properties=dict(id={}), required=["id"])
    thing = dict(
        properties=dict(
            name={},
            gap=dict(anyOf=[{"$ref": "#/components/schemas/Gap"}, dict(type="null")]),
            items=dict(type="array", items={"$ref": "#/components/schemas/Item"}),
            locks=dict(type="object", additionalProperties={"$ref": "#/components/schemas/Item"}),
            free=dict(type="object", additionalProperties={}),
        ),
        required=["name", "gap", "items"],
    )
    json_answer = dict(schema={"$ref": "#/components/schemas/Thing"})
    close = dict(responses={"200": dict(content={"application/json": json_answer})})
    doc = _contract(version)
    account = dict(properties=dict(currency={}, more={}))
    doc["components"]["schemas"].update(Thing=thing, Gap=gap, Item=item, Account=account)
    doc["paths"] = {CLOSE.split(" ")[1]: dict(post=close)}
    return doc


def _serve_answers():
    return respx.get(f"{PRACTICE}/openapi.json").mock(
        return_value=httpx.Response(200, json=_answer_contract())
    )


def _mark_close(drift, monkeypatch, answer):
    """One builder, `close_answer`, marked as standing for `CLOSE`'s answer."""

    def close_answer():
        return answer

    monkeypatch.setattr(drift, "answer_builders", lambda: {CLOSE: close_answer})


@respx.mock
def test_an_answer_with_every_required_field_passes(drift, monkeypatch, capsys):
    _serve_answers()
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    _mark_close(drift, monkeypatch, dict(name="x", gap=None, items=[]))

    assert drift.main(["--engine-url", PRACTICE]) == 0
    assert "every marked answer matches its endpoint" in capsys.readouterr().out


@respx.mock
def test_an_answer_missing_a_required_field_fails_and_names_it(drift, monkeypatch, capsys):
    _serve_answers()
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    _mark_close(drift, monkeypatch, dict(name="x", items=[]))

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert "where a marked answer differs from its endpoint's answer in the contract:" in out
    assert f"  {CLOSE}: gap (close_answer)" in out
    assert "no fixture claims a field the engine does not serve." in out  # the other half


@respx.mock
def test_a_nested_object_or_list_item_is_checked_against_its_own_schema(drift, monkeypatch, capsys):
    _serve_answers()
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    _mark_close(drift, monkeypatch, dict(name="x", gap=dict(first="d"), items=[dict(id=1), {}]))

    assert drift.main(["--engine-url", PRACTICE]) == 1
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith(f"  {CLOSE}")]
    assert lines == [
        f"  {CLOSE}: gap.count (close_answer)",
        f"  {CLOSE}: items[1].id (close_answer)",
    ]


@respx.mock
def test_a_key_its_own_endpoint_lacks_is_named_with_its_path_and_builder(
    drift, monkeypatch, capsys
):
    """Each planted key is declared on another schema of the contract (`currency`,
    `more` on Account, `id` on Item, `first` on Gap), so only a check against the
    endpoint's own schema names it. A map's values are checked as its schema says."""
    _serve_answers()
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    answer = dict(
        name="x",
        currency="PEN",
        gap=dict(first="d", count=1, id=2),
        items=[dict(id=1, first=0)],
        locks=dict(a=dict(id=1, more=1)),
        free=dict(anything=1),
    )
    _mark_close(drift, monkeypatch, answer)

    assert drift.main(["--engine-url", PRACTICE]) == 1
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith(f"  {CLOSE}")]
    assert lines == [
        f"  {CLOSE}: currency is not in its answer (close_answer)",
        f"  {CLOSE}: gap.id is not in its answer (close_answer)",
        f"  {CLOSE}: items[0].first is not in its answer (close_answer)",
        f"  {CLOSE}: locks.a.more is not in its answer (close_answer)",
    ]


def test_a_map_values_required_fields_are_checked(drift):
    doc = _answer_contract()
    schema = drift.answer_schema(doc, CLOSE)

    value = dict(name="x", gap=None, items=[], locks=dict(a={}))
    assert drift.missing_required(doc, schema, value) == ["locks.a.id"]


def test_an_object_the_contract_leaves_open_has_no_extra_key(drift):
    doc = _answer_contract()
    doc["components"]["schemas"]["Thing"]["additionalProperties"] = True
    schema = drift.answer_schema(doc, CLOSE)

    assert drift.extra_keys(doc, schema, dict(name="x", gap=None, items=[], anything=1)) == []


@respx.mock
@pytest.mark.parametrize(
    "endpoint", ["POST /v1/things/{thing_id}/open", "GET /v1/things/{thing_id}/close"]
)
def test_an_endpoint_the_contract_does_not_answer_is_reported(drift, monkeypatch, capsys, endpoint):
    _serve_answers()
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    monkeypatch.setattr(drift, "answer_builders", lambda: {endpoint: lambda: dict(name="x")})

    assert drift.main(["--engine-url", PRACTICE]) == 1
    assert f"  {endpoint}: the contract holds no JSON answer for it" in capsys.readouterr().out


@respx.mock
def test_an_answer_in_more_than_one_shape_is_named_apart_from_no_answer(drift, monkeypatch, capsys):
    doc = _answer_contract()
    either = [{"$ref": "#/components/schemas/Gap"}, {"$ref": "#/components/schemas/Item"}]
    union = dict(content={"application/json": dict(schema=dict(anyOf=either))})
    doc["paths"]["/v1/things/{thing_id}/union"] = dict(get=dict(responses={"200": union}))
    respx.get(f"{PRACTICE}/openapi.json").mock(return_value=httpx.Response(200, json=doc))
    drift.SAVED_VERSION_FILE.write_text(SAVED + "\n")
    many = "GET /v1/things/{thing_id}/union"
    none = "GET /v1/things/{thing_id}/close"
    monkeypatch.setattr(drift, "answer_builders", lambda: {many: lambda: {}, none: lambda: {}})

    assert drift.main(["--engine-url", PRACTICE]) == 1
    out = capsys.readouterr().out
    assert f"  {many}: the contract answers it in more than one shape (<lambda>)" in out
    assert f"  {none}: the contract holds no JSON answer for it (<lambda>)" in out


def test_a_value_the_contract_allows_two_object_shapes_for_is_not_guessed():
    drift = load_drift_script()
    doc = _answer_contract()
    other = dict(properties=dict(last={}), required=["last"])
    doc["components"]["schemas"]["Other"] = other
    either = [{"$ref": "#/components/schemas/Gap"}, {"$ref": "#/components/schemas/Other"}]
    doc["components"]["schemas"]["Thing"]["properties"]["gap"] = dict(anyOf=either)
    schema = drift.answer_schema(doc, CLOSE)

    assert drift.missing_required(doc, schema, dict(name="x", gap={}, items=[])) == []


def test_the_script_reads_the_builders_helpers_marks():
    """With no patch, the script's builders are helpers.py's registry, the complete's
    answer among them, each giving a dict when called bare."""
    from tests.unit import helpers

    builders = load_drift_script().answer_builders()

    assert builders == helpers.ANSWER_BUILDERS
    assert "POST /v1/statements/{statement_id}/complete" in builders
    assert all(isinstance(build(), dict) for build in builders.values())


def test_a_marked_builder_refuses_an_answer_with_fewer_keys_than_its_bare_one(monkeypatch):
    from tests.unit import helpers

    monkeypatch.setattr(helpers, "ANSWER_BUILDERS", {})

    @helpers.answer_of("POST", "/v1/things/{thing_id}/close")
    def close_answer(record=None):
        return record if record is not None else dict(name="x", gap=None)

    assert helpers.ANSWER_BUILDERS == {CLOSE: close_answer}
    assert close_answer(dict(name="y", gap=None, more=1)) == dict(name="y", gap=None, more=1)
    with pytest.raises(AssertionError, match=r"close_answer dropped \['gap'\]"):
        close_answer(dict(name="y"))


def test_a_second_builder_for_one_endpoint_is_refused_and_not_registered(monkeypatch):
    from tests.unit import helpers

    monkeypatch.setattr(helpers, "ANSWER_BUILDERS", {})

    @helpers.answer_of("POST", "/v1/things/{thing_id}/close")
    def first():
        return dict(name="x")

    with pytest.raises(ValueError, match="close already has first; second"):

        @helpers.answer_of("POST", "/v1/things/{thing_id}/close")
        def second():
            return dict(name="y")

    assert helpers.ANSWER_BUILDERS == {CLOSE: first}


def test_the_complete_answer_keeps_its_fields_whatever_the_record():
    from tests.unit.helpers import statement_complete_answer

    gap = dict(first_uncovered_day="2026-02-25", last_uncovered_day="2026-03-31", unfiled_count=3)
    noted = dict(account_id="acc1", warnings=["a gap"], coverage_gap=gap)
    answer = statement_complete_answer(dict(id="s9", balances=[noted]))
    (balance,) = answer["balances"]

    assert set(statement_complete_answer()) <= set(answer)
    assert set(statement_complete_answer()["balances"][0]) <= set(balance)
    assert (answer["id"], balance["warnings"], balance["coverage_gap"]) == ("s9", ["a gap"], gap)
    assert statement_complete_answer()["balances"][0]["coverage_gap"] is None
