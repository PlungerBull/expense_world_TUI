import json

import httpx
import pytest
import respx
import typer
from typer.testing import CliRunner

from expense import config as config_module
from expense.commands.auth_cmd import app as auth_app
from expense.commands.auth_cmd import whoami as whoami_impl
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app

cli_app = make_cli_app(auth_app, "auth", commands={"whoami": whoami_impl})

runner = CliRunner()


BOOTSTRAP_RESPONSE = {
    "user": {
        "id": "u_123",
        "display_name": "Alex",
        "last_login_at": "2026-04-23T10:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-04-23T10:00:00Z",
    },
    "settings": {
        "user_id": "u_123",
        "main_currency": "USD",
        "display_timezone": "America/Lima",
        "version": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-04-23T10:00:00Z",
    },
}


@respx.mock
def test_bootstrap_caches_main_currency(configured):
    respx.post(f"{BASE}/v1/auth/bootstrap").mock(
        return_value=httpx.Response(200, json=BOOTSTRAP_RESPONSE)
    )
    result = runner.invoke(
        cli_app,
        [
            "auth",
            "bootstrap",
            "--display-name",
            "Alex",
            "--timezone",
            "America/Lima",
        ],
    )
    assert result.exit_code == 0, result.output

    cfg = config_module.load()
    assert cfg.main_currency == "USD"


@respx.mock
def test_me_refreshes_main_currency_cache(configured):
    updated_response = {
        **BOOTSTRAP_RESPONSE,
        "settings": {**BOOTSTRAP_RESPONSE["settings"], "main_currency": "PEN"},
    }
    respx.get(f"{BASE}/v1/auth/me").mock(return_value=httpx.Response(200, json=updated_response))
    result = runner.invoke(cli_app, ["auth", "me"])
    assert result.exit_code == 0

    cfg = config_module.load()
    assert cfg.main_currency == "PEN"


@respx.mock
def test_me_404_prints_bootstrap_hint(configured):
    respx.get(f"{BASE}/v1/auth/me").mock(
        return_value=error_response(404, "NOT_FOUND", "User not found", None)
    )
    result = runner.invoke(cli_app, ["auth", "me"])
    assert result.exit_code == 1
    assert "bootstrap" in result.output


@respx.mock
def test_whoami_equivalent_to_me(configured):
    route = respx.get(f"{BASE}/v1/auth/me").mock(
        return_value=httpx.Response(200, json=BOOTSTRAP_RESPONSE)
    )
    me_result = runner.invoke(cli_app, ["auth", "me", "--json"])
    whoami_result = runner.invoke(cli_app, ["whoami", "--json"])

    assert me_result.exit_code == 0
    assert whoami_result.exit_code == 0
    assert me_result.output == whoami_result.output
    assert route.call_count == 2


def test_settings_no_flags_errors(configured):
    result = runner.invoke(cli_app, ["auth", "settings"])
    assert result.exit_code == 1
    assert "No settings to update" in result.output


@respx.mock
def test_settings_display_timezone_updates(configured):
    updated_settings = {**BOOTSTRAP_RESPONSE["settings"], "display_timezone": "America/Bogota"}
    route = respx.put(f"{BASE}/v1/auth/settings").mock(
        return_value=httpx.Response(200, json=updated_settings)
    )
    result = runner.invoke(cli_app, ["auth", "settings", "--display-timezone", "America/Bogota"])
    assert result.exit_code == 0, result.output

    req_body = json.loads(route.calls.last.request.content)
    assert req_body == {"display_timezone": "America/Bogota"}
    assert "display_timezone: America/Bogota" in result.output


@respx.mock
def test_settings_422_invalid_timezone_renders_engine_error(configured):
    respx.put(f"{BASE}/v1/auth/settings").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Invalid input.",
            {"display_timezone": "Not a valid IANA timezone."},
            {"display_timezone": "UNSUPPORTED_VALUE"},
        )
    )
    result = runner.invoke(cli_app, ["auth", "settings", "--display-timezone", "Mars/Olympus"])
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "display_timezone" in result.output


@respx.mock
def test_me_json_mode(configured):
    respx.get(f"{BASE}/v1/auth/me").mock(return_value=httpx.Response(200, json=BOOTSTRAP_RESPONSE))
    result = runner.invoke(cli_app, ["auth", "me", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == BOOTSTRAP_RESPONSE


def test_profile_no_flags_errors(configured):
    result = runner.invoke(cli_app, ["auth", "profile"])
    assert result.exit_code == 1
    assert "No profile fields to update" in result.output


@respx.mock
def test_profile_display_name_success(configured):
    updated_user = {**BOOTSTRAP_RESPONSE["user"], "display_name": "Alex"}
    route = respx.put(f"{BASE}/v1/auth/profile").mock(
        return_value=httpx.Response(200, json=updated_user)
    )
    result = runner.invoke(cli_app, ["auth", "profile", "--display-name", "Alex"])
    assert result.exit_code == 0, result.output

    req_body = json.loads(route.calls.last.request.content)
    assert req_body == {"display_name": "Alex"}
    assert "display_name: Alex" in result.output


@respx.mock
def test_profile_json_mode(configured):
    updated_user = {**BOOTSTRAP_RESPONSE["user"], "display_name": "Alex"}
    respx.put(f"{BASE}/v1/auth/profile").mock(return_value=httpx.Response(200, json=updated_user))
    result = runner.invoke(cli_app, ["auth", "profile", "--display-name", "Alex", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == updated_user


@respx.mock
def test_profile_422_renders_engine_error(configured):
    respx.put(f"{BASE}/v1/auth/profile").mock(
        return_value=error_response(
            422,
            "VALIDATION_ERROR",
            "Invalid input.",
            {"display_name": "Must not be null."},
            {"display_name": "NOT_NULL"},
        )
    )
    result = runner.invoke(cli_app, ["auth", "profile", "--display-name", "Alex"])
    assert result.exit_code == 1
    assert "VALIDATION_ERROR" in result.output
    assert "display_name" in result.output


_EMPTY_NAME = (
    422,
    "VALIDATION_ERROR",
    "Invalid input.",
    {"display_name": "Must not be empty."},
    {"display_name": "EMPTY"},
)
_NAME_WRITES = {
    "bootstrap": ("POST", "/v1/auth/bootstrap", ["--timezone", "America/Lima"]),
    "profile": ("PUT", "/v1/auth/profile", []),
}


@respx.mock
@pytest.mark.parametrize("command", list(_NAME_WRITES))
@pytest.mark.parametrize("typed", ["  Alex Tern  ", "", "   "], ids=["padded", "empty", "spaces"])
def test_display_name_is_sent_exactly_as_typed(configured, command, typed):
    """No local trim and no local blank check; the engine owns both
    (contract: POST /v1/auth/bootstrap) (contract: PUT /v1/auth/profile)."""
    method, path, extra = _NAME_WRITES[command]
    route = respx.request(method, f"{BASE}{path}").mock(
        return_value=httpx.Response(200, json=BOOTSTRAP_RESPONSE)
    )
    result = runner.invoke(cli_app, ["auth", command, "--display-name", typed, *extra])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content)["display_name"] == typed


@respx.mock
@pytest.mark.parametrize("command", list(_NAME_WRITES))
def test_blank_display_name_shows_the_engines_refusal(configured, command):
    method, path, extra = _NAME_WRITES[command]
    route = respx.request(method, f"{BASE}{path}").mock(return_value=error_response(*_EMPTY_NAME))
    result = runner.invoke(cli_app, ["auth", command, "--display-name", "   ", *extra])
    assert result.exit_code == 1
    assert json.loads(route.calls.last.request.content)["display_name"] == "   "
    assert result.output == (
        "Error: VALIDATION_ERROR — Invalid input.\n  display_name: Must not be empty.\n"
    )


@respx.mock
@pytest.mark.parametrize("command", list(_NAME_WRITES))
def test_blank_display_name_json_is_the_engines_raw_body(configured, command):
    method, path, extra = _NAME_WRITES[command]
    refusal = error_response(*_EMPTY_NAME)
    respx.request(method, f"{BASE}{path}").mock(return_value=refusal)
    result = runner.invoke(cli_app, ["auth", command, "--display-name", "", "--json", *extra])
    assert result.exit_code == 1
    assert json.loads(result.output) == json.loads(refusal.content)


@respx.mock
def test_bootstrap_timezone_auto_detected_from_tz_env(configured, monkeypatch):
    monkeypatch.setenv("TZ", "America/Lima")
    route = respx.post(f"{BASE}/v1/auth/bootstrap").mock(
        return_value=httpx.Response(200, json=BOOTSTRAP_RESPONSE)
    )
    result = runner.invoke(cli_app, ["auth", "bootstrap", "--display-name", "Alex"])
    assert result.exit_code == 0, result.output
    assert "Using timezone: America/Lima" in result.output

    req_body = json.loads(route.calls.last.request.content)
    assert req_body == {"display_name": "Alex", "timezone": "America/Lima"}


def test_detect_timezone_failure_is_a_clean_usage_error(tmp_path, monkeypatch):
    """No TZ env and no /etc/localtime symlink must not traceback."""
    from expense.commands import auth_cmd

    monkeypatch.delenv("TZ", raising=False)
    with pytest.raises(typer.BadParameter) as exc:
        auth_cmd._detect_timezone(localtime=tmp_path / "missing")
    assert "Pass --timezone" in exc.value.message


@respx.mock  # no routes registered: the failure must happen before any request
def test_bootstrap_undetectable_timezone_errors_cleanly(configured, monkeypatch, tmp_path):
    from functools import partial

    from expense.commands import auth_cmd

    monkeypatch.delenv("TZ", raising=False)
    real = auth_cmd._detect_timezone
    monkeypatch.setattr(auth_cmd, "_detect_timezone", partial(real, localtime=tmp_path / "missing"))

    result = runner.invoke(cli_app, ["auth", "bootstrap", "--display-name", "Alex"])
    assert result.exit_code == 2
    assert "Could not detect system timezone" in result.output
    assert "Traceback" not in result.output
    assert not respx.calls


@respx.mock
def test_whoami_surfaces_an_engine_refusal(configured):
    """`whoami` is the command people run to find out whether their token works,
    so a bad token has to produce a sentence, not an empty record."""
    respx.get(f"{BASE}/v1/auth/me").mock(
        return_value=error_response(401, "UNAUTHORIZED", "Token is not valid.")
    )
    result = runner.invoke(cli_app, ["whoami"])
    assert result.exit_code == 1
    assert "UNAUTHORIZED" in result.output
