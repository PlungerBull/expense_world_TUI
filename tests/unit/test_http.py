from uuid import UUID

import httpx
import pytest
import respx

from expense.config import Config
from expense.errors import EngineConnectionError, EngineError
from expense.http import ExpenseClient
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response


@pytest.fixture
def config():
    return Config(
        engine_url=BASE,
        token="ewe_pat_test123",
        main_currency="USD",
    )


@pytest.mark.parametrize(
    ("asked", "sent", "auth"),
    [
        ("/health", "/health", False),  # bypasses the /v1 prefix
        ("/auth/me", "/v1/auth/me", True),
        ("/v1/auth/me", "/v1/auth/me", True),  # never double-prefixed
    ],
)
@respx.mock
def test_paths_get_the_v1_prefix_and_the_token_goes_only_on_auth_requests(
    config, asked, sent, auth
):
    route = respx.get(f"{BASE}{sent}").mock(return_value=httpx.Response(200, json={}))
    with ExpenseClient(config) as client:
        client.get(asked, auth=auth)

    request = route.calls.last.request
    assert request.url.path == sent
    assert request.headers.get("Authorization") == (f"Bearer {config.token}" if auth else None)


@respx.mock
def test_writes_get_unique_idempotency_keys(config):
    route = respx.post(f"{BASE}/v1/auth/bootstrap").mock(
        return_value=httpx.Response(200, json={"user": {}, "settings": {}})
    )
    with ExpenseClient(config) as client:
        client.post("/auth/bootstrap", json_body={"display_name": "a"})
        client.post("/auth/bootstrap", json_body={"display_name": "a"})

    keys = [call.request.headers["X-Idempotency-Key"] for call in route.calls]
    assert len(keys) == 2
    assert keys[0] != keys[1]


@pytest.mark.parametrize("verb", ["post", "put", "delete"])
@respx.mock
def test_every_write_verb_sends_a_wellformed_idempotency_key(config, verb):
    """Idempotency on every write (CLAUDE.md non-negotiable) — every verb the
    client exposes must mint a key the engine can replay, not just POST."""
    route = getattr(respx, verb)(f"{BASE}/v1/accounts/a1").mock(
        return_value=httpx.Response(200, json={})
    )
    with ExpenseClient(config) as client:
        if verb == "delete":
            client.delete("/accounts/a1")
        else:
            getattr(client, verb)("/accounts/a1", json_body={"name": "x"})

    UUID(route.calls.last.request.headers["X-Idempotency-Key"])  # raises if malformed


@respx.mock
def test_reads_do_not_send_idempotency_key(config):
    route = respx.get(f"{BASE}/v1/auth/me").mock(return_value=httpx.Response(200, json={}))
    with ExpenseClient(config) as client:
        client.get("/auth/me")

    assert "x-idempotency-key" not in route.calls.last.request.headers


#: A 422 names its field; the only reason `GET /v1/auth/me` can give is an
#: unknown query parameter (contract: GET /v1/auth/me).
_UNKNOWN_PARAM = {"limit": "Not a parameter of this endpoint."}


@pytest.mark.parametrize(
    "status,code,fields,reasons",
    [
        (404, "NOT_FOUND", None, None),
        (422, "VALIDATION_ERROR", _UNKNOWN_PARAM, {"limit": "UNKNOWN_PARAMETER"}),
    ],
)
@respx.mock
def test_engine_errors_translate_by_status(config, status, code, fields, reasons):
    respx.get(f"{BASE}/v1/auth/me").mock(
        return_value=error_response(status, code, "bad", fields, reasons)
    )
    with ExpenseClient(config) as client, pytest.raises(EngineError) as exc:
        client.get("/auth/me")

    assert exc.value.code == code
    assert exc.value.status == status
    assert exc.value.fields == fields
    assert exc.value.reasons == reasons
    assert exc.value.raw_body["error"]["reasons"] == reasons


@pytest.mark.parametrize(
    "error",
    [
        {"code": "NOT_FOUND", "message": "gone", "fields": None, "reasons": None},
        {"code": "NOT_FOUND", "message": "gone"},
    ],
    ids=["reasons-null", "reasons-absent"],
)
@respx.mock
def test_engine_error_without_reasons_is_none(config, error):
    respx.get(f"{BASE}/v1/auth/me").mock(return_value=httpx.Response(404, json={"error": error}))
    with ExpenseClient(config) as client, pytest.raises(EngineError) as exc:
        client.get("/auth/me")

    assert exc.value.reasons is None


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("connection refused"),
        httpx.TimeoutException("timed out"),
        httpx.ReadError("server closed mid-response"),
        httpx.WriteError("broken pipe"),
        httpx.RemoteProtocolError("premature close"),
        httpx.ProxyError("proxy refused"),
        httpx.UnsupportedProtocol("scheme-less engine_url"),
    ],
)
@respx.mock
def test_connection_error_on_full_transport_family(config, exc):
    """Every httpx transport failure renders cleanly, not as a traceback."""
    respx.get(f"{BASE}/v1/auth/me").mock(side_effect=exc)
    with ExpenseClient(config) as client, pytest.raises(EngineConnectionError) as caught:
        client.get("/auth/me")

    assert BASE in caught.value.url


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500, text="<html>Internal Server Error</html>"),
        httpx.Response(500, json={"unexpected": "shape"}),
    ],
    ids=["non-json", "malformed-envelope"],
)
@respx.mock
def test_an_answer_that_is_no_envelope_is_a_connection_error(config, answer):
    respx.get(f"{BASE}/v1/auth/me").mock(return_value=answer)
    with ExpenseClient(config) as client, pytest.raises(EngineConnectionError):
        client.get("/auth/me")


# --- bounded same-key write retry ------------------------------


def _envelope(status: int, code: str) -> httpx.Response:
    return error_response(status, code, "boom", None)


@respx.mock
def test_write_timeout_is_retried_with_same_idempotency_key(config, capsys):
    route = respx.post(f"{BASE}/v1/accounts").mock(
        side_effect=[httpx.TimeoutException("timed out"), httpx.Response(201, json={"id": "a"})]
    )
    with ExpenseClient(config) as client:
        result = client.post("/accounts", json_body={"name": "x"})

    assert result == {"id": "a"}
    assert route.call_count == 2
    keys = {call.request.headers["X-Idempotency-Key"] for call in route.calls}
    assert len(keys) == 1  # the retry replays, it does not re-mint
    assert "idempotency key" in capsys.readouterr().err


@respx.mock
def test_write_5xx_is_retried_with_same_idempotency_key(config):
    route = respx.post(f"{BASE}/v1/accounts").mock(
        side_effect=[_envelope(503, "UNAVAILABLE"), httpx.Response(201, json={"id": "a"})]
    )
    with ExpenseClient(config) as client:
        result = client.post("/accounts", json_body={"name": "x"})

    assert result == {"id": "a"}
    assert route.call_count == 2
    keys = {call.request.headers["X-Idempotency-Key"] for call in route.calls}
    assert len(keys) == 1


@respx.mock
def test_write_retry_is_bounded_then_raises_connection_error(config):
    route = respx.post(f"{BASE}/v1/accounts").mock(side_effect=httpx.TimeoutException("timed out"))
    with ExpenseClient(config) as client, pytest.raises(EngineConnectionError):
        client.post("/accounts", json_body={"name": "x"})

    assert route.call_count == 3


@respx.mock
def test_write_5xx_exhaustion_surfaces_the_engine_error(config):
    route = respx.post(f"{BASE}/v1/accounts").mock(return_value=_envelope(503, "UNAVAILABLE"))
    with ExpenseClient(config) as client, pytest.raises(EngineError) as exc:
        client.post("/accounts", json_body={"name": "x"})

    assert route.call_count == 3
    assert exc.value.status == 503  # the final envelope still renders verbatim


@respx.mock
def test_write_connect_error_fails_fast(config):
    """Connect-refused means the engine isn't there — no retry, no ambiguity."""
    route = respx.post(f"{BASE}/v1/accounts").mock(side_effect=httpx.ConnectError("refused"))
    with ExpenseClient(config) as client, pytest.raises(EngineConnectionError):
        client.post("/accounts", json_body={"name": "x"})

    assert route.call_count == 1


@respx.mock
def test_write_4xx_is_not_retried(config):
    route = respx.post(f"{BASE}/v1/accounts").mock(
        return_value=error_response(
            422, "VALIDATION_ERROR", "boom", {"name": "Must not be empty."}, {"name": "EMPTY"}
        )
    )
    with ExpenseClient(config) as client, pytest.raises(EngineError):
        client.post("/accounts", json_body={"name": "x"})

    assert route.call_count == 1


@pytest.mark.parametrize(
    ("mock", "raises"),
    [
        ({"side_effect": httpx.TimeoutException("timed out")}, EngineConnectionError),
        ({"return_value": _envelope(500, "INTERNAL")}, EngineError),
    ],
    ids=["timeout", "5xx"],
)
@respx.mock
def test_a_read_is_never_retried(config, mock, raises):
    route = respx.get(f"{BASE}/v1/auth/me").mock(**mock)
    with ExpenseClient(config) as client, pytest.raises(raises):
        client.get("/auth/me")

    assert route.call_count == 1


@respx.mock
def test_verbose_dump_redacts_authorization(config, capsys):
    respx.get(f"{BASE}/v1/auth/me").mock(
        return_value=httpx.Response(200, json={"user": {"id": "u_xyz"}})
    )
    with ExpenseClient(config, verbose=True) as client:
        client.get("/auth/me")

    captured = capsys.readouterr()
    assert "Bearer [REDACTED]" in captured.err
    assert config.token not in captured.err
    assert "GET" in captured.err and "200" in captured.err and "u_xyz" in captured.err


def test_connect_timeout_is_ten_seconds_unless_the_caller_bounds_it(config):
    with ExpenseClient(config) as default, ExpenseClient(config, timeout_connect=3.0) as bounded:
        assert default._client.timeout.connect == 10.0
        assert bounded._client.timeout.connect == 3.0
        assert bounded._client.timeout.read == 60.0


@respx.mock
@pytest.mark.parametrize(
    "send", [lambda c: c.post("/accounts/a1/archive"), lambda c: c.get("/accounts/a1")]
)
def test_a_bodyless_operation_carries_no_bytes(config, send):
    """(contract: POST /v1/accounts/{account_id}/archive)"""
    route = respx.route().mock(return_value=httpx.Response(200, json={}))
    with ExpenseClient(config) as client:
        send(client)
    request = route.calls.last.request
    assert request.content == b""
    assert "content-type" not in request.headers
