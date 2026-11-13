"""Contract smoke: hits a real engine's /health endpoint. Gated in conftest.py."""

import httpx

from tests.contract.conftest import ENGINE_URL

HEALTH_KEYS = {"status", "release", "contract_version", "mode", "structure", "backup"}
STRUCTURE_KEYS = {"newest_update", "updates_recorded", "fixes_recorded"}
BACKUP_KEYS = {"state", "time", "age_seconds"}


def test_health_live():
    """`GET /health` answers 200 with every field the contract lists, as a practice engine.

    The required fields are present; fields this client does not know are tolerated
    (contract: "Base Conventions"). The 503 (database unreachable, or structure no longer
    matching the engine's code) cannot be caused from this client, so it is cited, not
    driven (contract: GET /health).
    """
    # Timeout needs a positional default (httpx requires default-or-all-four).
    with httpx.Client(timeout=httpx.Timeout(10.0, read=60.0)) as client:
        response = client.get(f"{ENGINE_URL}/health")
        contract_version = client.get(f"{ENGINE_URL}/openapi.json").json()["info"]["version"]
    assert response.status_code == 200
    body = response.json()

    assert HEALTH_KEYS <= set(body), f"missing: {HEALTH_KEYS - set(body)}"
    assert body["status"] == "ok"
    assert body["release"] is None or isinstance(body["release"], str)  # nullable
    assert body["contract_version"] == contract_version
    assert body["mode"] == "PRACTICE"

    structure = body["structure"]
    assert STRUCTURE_KEYS <= set(structure), f"missing: {STRUCTURE_KEYS - set(structure)}"
    assert structure["newest_update"] is None or isinstance(structure["newest_update"], str)
    assert isinstance(structure["updates_recorded"], int)
    assert isinstance(structure["fixes_recorded"], int)

    backup = body["backup"]
    assert BACKUP_KEYS <= set(backup), f"missing: {BACKUP_KEYS - set(backup)}"
    assert backup["state"] == "not_kept"
    # `time` and `age_seconds` are null when the state leaves them unknown, as `not_kept` does
    # (contract: GET /health).
    assert backup["time"] is None
    assert backup["age_seconds"] is None
