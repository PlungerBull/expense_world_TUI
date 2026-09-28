"""One CRUD contract, run against every resource that shares it.

Accounts, categories and hashtags are three spellings of the same command set —
`_resource.py` generates most of it — and their test files had grown into three
copies of the same thirteen tests, differing only in a noun, a flag and a
fixture. test_cmd_categories.py and test_cmd_hashtags.py had the *same test
names in the same order*.

Three copies is not three times the safety. It is one contract asserted three
times and, in practice, extended once: a flag gained a marked column on
categories and accounts and never on hashtags; the pagination hint is
checked with a different total in each file for no reason anyone recorded. A
rule with three homes drifts in two of them.

So the shared shape lives here, parametrized by `ResourceSpec`, and each
per-resource file keeps exactly what is its own — the hints it prints, the flags
only it has, and the arms only it can take (accounts archive and unarchive;
categories and hashtags have no such routes).

**What this deliberately does NOT do:** collapse the resources' *response
fixtures* into one. Those dicts are what `scripts/check_fixture_drift.py` reads
to find engine drift — it greps `"key":` literals out of tests/unit — so a
fixture replaced by a builder is a fixture the drift check can no longer see.
Each spec therefore carries a real, whole response body, written out.
"""

import json
from dataclasses import dataclass, field
from uuid import UUID

import httpx
import pytest
import respx
import typer
from typer.testing import CliRunner

from expense.commands.accounts_cmd import app as accounts_app
from expense.commands.categories_cmd import app as categories_app
from expense.commands.hashtags_cmd import app as hashtags_app
from tests.unit.helpers import ENGINE_URL as BASE
from tests.unit.helpers import error_response, make_cli_app, whole

runner = CliRunner()


@dataclass(frozen=True)
class ResourceSpec:
    """One resource's answers to the questions the shared contract asks."""

    #: URL segment and command group name — they are the same word by design.
    name: str
    app: typer.Typer
    #: A whole engine response body, as the engine sends it. Kept literal so the
    #: fixture-drift script can still read its keys — see the module docstring.
    sample: dict
    #: Flags `create` requires, ready to splice into the argv.
    create_flags: list[str]
    #: What those flags must become in the request body — the resource's own
    #: half of the create contract (a currency, a colour), asserted here so it
    #: does not need a per-resource copy of the whole test to carry it.
    create_expects: dict
    #: Fields `update` may change, as (flag, value, expected payload).
    update_flag: tuple[str, str] = ("--name", "renamed")
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        """The human name the list and get renderings must print."""
        return self.sample["name"]

    def __str__(self) -> str:  # pytest id
        return self.name


ACCOUNT = ResourceSpec(
    name="accounts",
    app=accounts_app,
    sample={
        "id": "11111111-1111-1111-1111-111111111111",
        "user_id": "u1",
        "name": "BCP Soles",
        "currency_code": "PEN",
        "color": "#3b82f6",
        "is_person": False,
        "is_archived": False,
        "current_balance_cents": 125000,
        "sort_order": 1,
        "deleted_at": None,
        "version": 1,
        "created_at": "2026-04-24T10:00:00Z",
        "updated_at": "2026-04-24T10:00:00Z",
    },
    create_flags=["--name", "BCP Soles", "--currency-code", "PEN"],
    create_expects={"name": "BCP Soles", "currency_code": "PEN"},
)

CATEGORY = ResourceSpec(
    name="categories",
    app=categories_app,
    sample={
        "id": "22222222-2222-2222-2222-222222222222",
        "user_id": "u1",
        "name": "Food",
        "color": "#00FF00",
        "sort_order": 1,
        "is_system": False,
        "system_key": None,
        "deleted_at": None,
        "version": 1,
        "created_at": "2026-04-24T10:00:00Z",
        "updated_at": "2026-04-24T10:00:00Z",
    },
    create_flags=["--name", "Food", "--color", "#00FF00"],
    create_expects={"name": "Food", "color": "#00FF00"},
)

HASHTAG = ResourceSpec(
    name="hashtags",
    app=hashtags_app,
    sample={
        "id": "33333333-3333-3333-3333-333333333333",
        "user_id": "u1",
        "name": "lunch",
        "sort_order": 1,
        "deleted_at": None,
        "version": 1,
        "created_at": "2026-04-24T10:00:00Z",
        "updated_at": "2026-04-24T10:00:00Z",
    },
    create_flags=["--name", "lunch"],
    create_expects={"name": "lunch"},
)

RESOURCES = [ACCOUNT, CATEGORY, HASHTAG]

#: Every parametrized test takes `spec`; `ids=str` prints the resource name, so a
#: failure says `test_get_404[hashtags]` and not `test_get_404[spec2]`.
resource = pytest.mark.parametrize("spec", RESOURCES, ids=str)


def _cli(spec: ResourceSpec):
    return make_cli_app(spec.app, spec.name)


def _run(spec: ResourceSpec, *args: str):
    return runner.invoke(_cli(spec), [spec.name, *args])


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@resource
@respx.mock
def test_list_bare_sends_no_include_params(spec, configured):
    """A default list asks the engine for the default scope — no include_* flags.

    Archived rows are opt-in on every resource that has them; a flag
    that leaked into the default would quietly change what the command means.
    """
    route = respx.get(f"{BASE}/v1/{spec.name}").mock(
        return_value=httpx.Response(200, json=whole([spec.sample]))
    )
    result = _run(spec, "list")

    assert result.exit_code == 0, result.output
    assert spec.label in result.output
    params = route.calls.last.request.url.params
    assert params.get("include_archived") is None


@resource
@respx.mock
def test_list_prints_every_row_and_no_footer(spec, configured):
    """The engine returns these lists whole and refuses `limit`/`offset`:
    the request carries neither, every row is printed — 56 rows
    is the hashtag count that lost 6 tags to a default page of 50 — and there
    is no `showing N of M` line, because there is nothing more to fetch."""
    rows = [{**spec.sample, "id": f"id-{i}", "name": f"row{i:02d}"} for i in range(56)]
    route = respx.get(f"{BASE}/v1/{spec.name}").mock(
        return_value=httpx.Response(200, json=whole(rows))
    )
    result = _run(spec, "list")

    assert result.exit_code == 0, result.output
    params = route.calls.last.request.url.params
    assert "limit" not in params and "offset" not in params
    assert all(f"row{i:02d}" in result.output for i in range(56))
    assert "showing" not in result.output
    assert "--offset" not in result.output


@resource
@respx.mock
def test_list_json_is_the_engine_body_verbatim(spec, configured):
    """CLAUDE.md "Human default, JSON opt-in": `--json` is a pass-through, never
    a re-rendering."""
    body = whole([spec.sample])
    respx.get(f"{BASE}/v1/{spec.name}").mock(return_value=httpx.Response(200, json=body))
    result = _run(spec, "list", "--json")

    assert result.exit_code == 0
    assert json.loads(result.output) == body


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@resource
@respx.mock
def test_get_renders_the_record(spec, configured):
    respx.get(f"{BASE}/v1/{spec.name}/abc").mock(return_value=httpx.Response(200, json=spec.sample))
    result = _run(spec, "get", "abc")

    assert result.exit_code == 0, result.output
    assert spec.label in result.output


@resource
@respx.mock
def test_get_404_surfaces_the_engine_envelope(spec, configured):
    """The error-shape half of the rule in CLAUDE.md "Testing conventions"."""
    respx.get(f"{BASE}/v1/{spec.name}/missing").mock(
        return_value=error_response(404, "NOT_FOUND", "not found")
    )
    result = _run(spec, "get", "missing")

    assert result.exit_code == 1
    assert "NOT_FOUND" in result.output


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@resource
@respx.mock
def test_create_mints_the_id_client_side(spec, configured):
    """Ids are the client's to mint — that is what makes a retried write safe
    (CLAUDE.md "Idempotency on every write"). The engine never assigns one.
    """
    route = respx.post(f"{BASE}/v1/{spec.name}").mock(
        return_value=httpx.Response(201, json=spec.sample)
    )
    result = _run(spec, "create", *spec.create_flags)

    assert result.exit_code == 0, result.output
    assert "Created:" in result.output
    body = json.loads(route.calls.last.request.content)
    UUID(body["id"])  # a real UUID, not an echo of the response
    for key, value in spec.create_expects.items():
        assert body[key] == value


@resource
@respx.mock
def test_create_json_prints_the_body_and_nothing_else(spec, configured):
    """A `Created:` line above the JSON would break every caller that parses it."""
    respx.post(f"{BASE}/v1/{spec.name}").mock(return_value=httpx.Response(201, json=spec.sample))
    result = _run(spec, "create", *spec.create_flags, "--json")

    assert result.exit_code == 0
    assert json.loads(result.output) == spec.sample
    assert "Created:" not in result.output


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@resource
def test_update_with_no_flags_is_refused_before_any_request(spec, configured):
    """An empty PUT would be a write that means nothing; `build_update_payload`
    stops it client-side, so there is no respx route here on purpose."""
    result = _run(spec, "update", "abc")

    assert result.exit_code == 1
    assert "No fields to update" in result.output


@resource
@respx.mock
def test_update_sends_only_the_flags_given(spec, configured):
    """Partial update: an unset flag is absent from the payload, never null.

    Null means "clear this field" to the engine, so a command that sent every
    flag would wipe whatever the user did not mention.
    """
    flag, value = spec.update_flag
    route = respx.put(f"{BASE}/v1/{spec.name}/abc").mock(
        return_value=httpx.Response(200, json=spec.sample)
    )
    result = _run(spec, "update", "abc", flag, value)

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {flag.lstrip("-"): value}


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@resource
def test_delete_refuses_without_yes_off_a_tty(spec, configured):
    """CLAUDE.md "Confirm destructive operations" — with nobody to answer the
    prompt, the write must not happen. No route: it must never be reached."""
    result = _run(spec, "delete", "abc")

    assert result.exit_code == 1
    assert "non-interactive" in result.output


@resource
@respx.mock
def test_delete_with_yes_soft_deletes(spec, configured):
    deleted = {**spec.sample, "deleted_at": "2026-04-24T10:00:00Z"}
    route = respx.delete(f"{BASE}/v1/{spec.name}/abc").mock(
        return_value=httpx.Response(200, json=deleted)
    )
    result = _run(spec, "delete", "abc", "--yes")

    assert result.exit_code == 0, result.output
    assert route.called


# ---------------------------------------------------------------------------
# the error shape, on every verb
# ---------------------------------------------------------------------------
#
# CLAUDE.md asks every command for a happy path AND an error shape. The error
# half was missing on `list` and `create` across all three resources
# — the verbs whose happy path is the nicest to write. Parametrized here, the
# rule is satisfied for six commands by two tests, and a fourth resource
# would inherit them by appearing in RESOURCES.


@resource
@respx.mock
def test_list_surfaces_an_engine_refusal(spec, configured):
    """A read that fails must exit non-zero, not print an empty table.

    An empty list and a refused list look identical on screen unless the
    command says so — and "you have no accounts" is a very different answer
    from "the engine would not tell me".
    """
    respx.get(f"{BASE}/v1/{spec.name}").mock(
        return_value=error_response(401, "UNAUTHORIZED", "Token is not valid.")
    )
    result = _run(spec, "list")

    assert result.exit_code == 1
    assert "UNAUTHORIZED" in result.output
    assert "Token is not valid." in result.output


@resource
@respx.mock
def test_create_conflict_surfaces_the_engine_envelope(spec, configured):
    """Names are unique per resource, so a 409 on create is the everyday
    refusal — the one a user meets by typing a name they already used."""
    respx.post(f"{BASE}/v1/{spec.name}").mock(
        return_value=error_response(409, "CONFLICT", "That name is already taken.")
    )
    result = _run(spec, "create", *spec.create_flags)

    assert result.exit_code == 1
    assert "CONFLICT" in result.output
    assert "That name is already taken." in result.output


@resource
@respx.mock
def test_create_refusal_keeps_reasons_off_screen_and_in_json(spec, configured):
    """A 422 carries a reason per field (contract: "Error reasons"). The human
    display is the engine's message and field messages only; `--json` prints the
    envelope as sent, reasons included."""
    reply = error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed.",
        {"name": "Name must not be empty."},
        {"name": "EMPTY"},
    )
    respx.post(f"{BASE}/v1/{spec.name}").mock(return_value=reply)

    human = _run(spec, "create", *spec.create_flags)
    assert human.exit_code == 1
    assert "Error: VALIDATION_ERROR — Request validation failed.\n" in human.output
    assert "  name: Name must not be empty." in human.output
    assert "EMPTY" not in human.output

    as_json = _run(spec, "create", *spec.create_flags, "--json")
    assert as_json.exit_code == 1
    assert json.loads(as_json.output) == reply.json()
    assert json.loads(as_json.output)["error"]["reasons"] == {"name": "EMPTY"}
