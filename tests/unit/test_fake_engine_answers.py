"""Every default answer the fake gives is one the drift script checks.

Each default answer is built by the endpoint's `answer_of` builder, the one
scripts/check_fixture_drift.py checks against the contract's required fields.
"""

import pytest

from tests.unit import helpers
from tests.unit.helpers import (
    ANSWER_BUILDERS,
    FAKE_ANSWERS,
    statement_complete_answer,
    statement_create_answer,
    statement_delete_answer,
    statement_list,
    statement_put_answer,
    statement_record,
    statement_revert_answer,
    statement_upload_answer,
)


def test_each_default_answer_and_statement_read_has_a_marked_builder():
    """The drift script checks every builder `answer_of` marks; each default answer
    the fake gives has one, and the fake answers no reconciliation route."""
    assert ANSWER_BUILDERS["POST /v1/statements"] is statement_create_answer
    assert ANSWER_BUILDERS["POST /v1/statements/{statement_id}/revert"] is statement_revert_answer
    assert (
        ANSWER_BUILDERS["POST /v1/statements/{statement_id}/complete"] is statement_complete_answer
    )
    assert ANSWER_BUILDERS["DELETE /v1/statements/{statement_id}"] is statement_delete_answer
    assert ANSWER_BUILDERS["GET /v1/statements"] is statement_list
    assert ANSWER_BUILDERS["GET /v1/statements/{statement_id}"] is statement_record
    assert ANSWER_BUILDERS["PUT /v1/statements/{statement_id}"] is statement_put_answer
    assert ANSWER_BUILDERS["POST /v1/statements/import"] is statement_upload_answer
    assert not [endpoint for endpoint in ANSWER_BUILDERS if "/reconciliations" in endpoint]
    assert {(method, pattern.pattern) for method, pattern, _ in FAKE_ANSWERS} == {
        ("POST", "/statements"),
        ("POST", "/statements/(?P<statement_id>[^/]+)/revert"),
        ("POST", "/statements/(?P<statement_id>[^/]+)/complete"),
        ("DELETE", "/statements/(?P<statement_id>[^/]+)"),
    }


def test_a_default_answer_needs_a_marked_builder():
    with pytest.raises(AssertionError, match="POST /v1/things has no answer_of builder"):
        helpers.fake_answer("POST", "/v1/things")
