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


def _contract(version):
    account = dict(properties=dict(name={}, currency={}))
    return dict(
        info=dict(title="expense_world_engine", version=version),
        components=dict(schemas=dict(Account=account)),
        paths={},
    )


@pytest.fixture
def drift(tmp_path, monkeypatch):
    """The script with its saved-version file and fixture folder moved into tmp_path.

    The fixture folder holds one fixture whose keys the mocked contract serves, so
    the drift half of every run here is clean and the version decides the exit.
    """
    module = load_drift_script()
    fixtures = tmp_path / "unit"
    fixtures.mkdir()
    (fixtures / "test_sample.py").write_text('ROW = {"name": "Cash", "currency": "PEN"}\n')
    monkeypatch.setattr(module, "UNIT_TESTS", fixtures)
    monkeypatch.setattr(module, "SAVED_VERSION_FILE", tmp_path / "engine-contract-version")
    return module


def _serve(version):
    return respx.get(f"{PRACTICE}/openapi.json").mock(
        return_value=httpx.Response(200, json=_contract(version))
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
    _serve(MOVED)
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
