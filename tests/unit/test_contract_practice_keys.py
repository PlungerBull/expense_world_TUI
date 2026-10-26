"""The contract suite's second practice key: `reserved_client` in tests/contract/conftest.py
signs in as the reserved-names practice user with EXPENSE_RESERVED_PAT, and a test asking
for it without that key fails, never skips (docs/runtime.md "Working against the live
engine"); the leak check (`leaves_nothing`) counts that user's records only for such a test,
and lists a leftover under whose it is. Hermetic: no engine is called."""

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


def test_the_leak_check_needs_no_reserved_key_for_a_test_not_asking_for_it(monkeypatch):
    monkeypatch.setattr(contract, "RESERVED_PAT", None)
    monkeypatch.setattr(contract, "PAT", "ewe_pat_shared")
    targets = contract.leak_targets(["client", "scratch", "leaves_nothing"])
    assert [(whose, target.token) for whose, target in targets] == [("", "ewe_pat_shared")]


def test_the_leak_check_counts_the_reserved_user_for_a_test_asking_for_it(monkeypatch):
    monkeypatch.setattr(contract, "RESERVED_PAT", "ewe_pat_reserved")
    monkeypatch.setattr(contract, "PAT", "ewe_pat_shared")
    targets = contract.leak_targets(["reserved_client", "leaves_nothing"])
    assert [(whose, target.token) for whose, target in targets] == [
        ("", "ewe_pat_shared"),
        (contract.RESERVED_WHOSE, "ewe_pat_reserved"),
    ]


def test_the_leak_check_fails_a_reserved_test_without_the_key(monkeypatch):
    monkeypatch.setattr(contract, "RESERVED_PAT", None)
    monkeypatch.setattr(contract, "PAT", "ewe_pat_shared")
    with pytest.raises(pytest.fail.Exception, match="EXPENSE_RESERVED_PAT is not set"):
        contract.leak_targets(["reserved_client"])


def test_a_leftover_is_what_the_test_added_listed_under_whose_it_is():
    before = {"a1": "account 'kept'", "c1": "category 'kept'"}
    after = {**before, "h9": "hashtag 'contract-h'", "a9": "account 'contract-a'"}
    assert contract.left_behind(before, after) == ["account 'contract-a'", "hashtag 'contract-h'"]
    assert contract.left_behind(before, after, contract.RESERVED_WHOSE) == [
        "the reserved-names user's account 'contract-a'",
        "the reserved-names user's hashtag 'contract-h'",
    ]
    assert contract.left_behind(after, before) == []
