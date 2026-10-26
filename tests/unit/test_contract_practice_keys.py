"""The contract suite's second practice key: `reserved_client` in tests/contract/conftest.py
signs in as the reserved-names practice user with EXPENSE_RESERVED_PAT, and a test asking
for it without that key fails, never skips (docs/runtime.md "Working against the live
engine"). Hermetic: no engine is called."""

import pytest
from _pytest.outcomes import Skipped

from tests.contract import conftest as contract


def test_without_the_key_the_test_fails_naming_the_variable(monkeypatch):
    monkeypatch.setattr(contract, "RESERVED_PAT", None)
    with pytest.raises(pytest.fail.Exception) as excinfo:
        contract.reserved_target()
    assert not isinstance(excinfo.value, Skipped)
    message = str(excinfo.value)
    assert "EXPENSE_RESERVED_PAT is not set" in message
    assert 'docs/runtime.md "Working against the live engine"' in message


def test_with_the_key_it_targets_the_suite_engine_with_that_key(monkeypatch):
    monkeypatch.setattr(contract, "RESERVED_PAT", "ewe_pat_reserved")
    monkeypatch.setattr(contract, "ENGINE_URL", "http://127.0.0.1:8002")
    target = contract.reserved_target()
    assert (target.engine_url, target.token) == ("http://127.0.0.1:8002", "ewe_pat_reserved")
