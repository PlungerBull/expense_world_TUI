"""The app's log file: what the HTTP client writes to it, where it lives, and that a
location that cannot be written never stops the app."""

import os
from pathlib import Path

import httpx
import pytest
import respx
from textual.worker import WorkerFailed

from expense import applog
from expense.config import Config
from expense.errors import EngineConnectionError, EngineError, format_error, handle_errors
from expense.http import ExpenseClient
from tests.unit.helpers import ENGINE_TOKEN, error_response, run_app, wait_for
from tests.unit.helpers import ENGINE_URL as BASE


@pytest.fixture
def log_file():
    """The log, configured at the redirect conftest sets; read back as text."""
    applog.configure()
    return lambda: Path(os.environ["EXPENSE_LOG"]).read_text()


@pytest.fixture
def client():
    with ExpenseClient(Config(engine_url=BASE, token=ENGINE_TOKEN)) as c:
        yield c


@respx.mock
def test_a_request_writes_its_method_path_status_and_time_but_not_the_token(client, log_file):
    respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json={}))
    client.get("/accounts", params={"limit": 5})

    text = log_file()
    assert "GET /v1/accounts?limit=5 200" in text
    assert "ms" in text
    assert ENGINE_TOKEN not in text
    assert "Bearer" not in text


@respx.mock
def test_a_refusal_writes_the_engines_envelope(client, log_file):
    respx.post(f"{BASE}/v1/accounts").mock(
        return_value=error_response(422, "VALIDATION_ERROR", "name is taken", {"name": "taken"})
    )
    with pytest.raises(EngineError):
        client.post("/accounts", json_body={"name": "x"})

    text = log_file()
    assert "refused 422" in text
    assert "VALIDATION_ERROR" in text
    assert "name is taken" in text


@respx.mock
def test_a_write_retry_writes_the_attempt_the_cause_and_the_key(client, log_file):
    route = respx.post(f"{BASE}/v1/accounts").mock(
        side_effect=[error_response(503, "UNAVAILABLE"), httpx.Response(201, json={"id": "a"})]
    )
    client.post("/accounts", json_body={"name": "x"})

    key = route.calls.last.request.headers["X-Idempotency-Key"]
    assert f"POST /v1/accounts got HTTP 503; retry 2/3, X-Idempotency-Key {key}" in log_file()


def test_an_unexpected_error_writes_its_traceback(log_file):
    try:
        raise KeyError("surprise")
    except KeyError as exc:
        assert format_error(exc) == "'surprise'"

    text = log_file()
    assert "unexpected error" in text
    assert "Traceback" in text


def test_the_log_is_at_the_redirect_or_in_the_mac_logs_folder(monkeypatch):
    assert applog.log_path() == Path(os.environ["EXPENSE_LOG"])
    monkeypatch.delenv("EXPENSE_LOG")
    assert applog.log_path() == Path.home() / "Library" / "Logs" / "expense_world" / "tui.log"


def test_a_location_that_cannot_be_written_leaves_the_app_running(
    tmp_path, monkeypatch, client, capsys
):
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    monkeypatch.setenv("EXPENSE_LOG", str(blocker / "tui.log"))

    applog.configure()
    with respx.mock:
        respx.get(f"{BASE}/v1/accounts").mock(return_value=httpx.Response(200, json={}))
        assert client.get("/accounts") == {}

    assert capsys.readouterr().err == ""


@respx.mock
def test_a_transport_failure_line_holds_neither_the_token_nor_bearer(log_file):
    # h11 refuses a header value with a trailing space and quotes it in its message.
    token = "ewe_pat_secret "
    message = f"Illegal header value b'Bearer {token}'"
    respx.get(f"{BASE}/v1/accounts").mock(side_effect=httpx.LocalProtocolError(message))
    with ExpenseClient(Config(engine_url=BASE, token=token)) as client:
        with pytest.raises(EngineConnectionError):
            client.get("/accounts")

    text = log_file()
    assert "GET /v1/accounts failed: LocalProtocolError" in text
    assert "ewe_pat_secret" not in text
    assert "Bearer" not in text


def test_a_crashed_worker_writes_its_own_traceback(log_file):
    def boom():
        raise KeyError("worker-secret-spot")

    async def body(pilot, app):
        app.run_worker(boom, thread=True, exit_on_error=True)
        await wait_for(pilot, lambda: "unhandled error" in log_file())

    with pytest.raises(WorkerFailed):
        run_app(body)

    text = log_file()
    assert "in boom" in text
    assert "worker-secret-spot" in text


def test_an_unexpected_crash_of_a_command_is_logged_and_still_propagates(log_file):
    @handle_errors
    def command():
        raise KeyError("command-crash")

    with pytest.raises(KeyError):
        command()

    assert "command-crash" in log_file()
