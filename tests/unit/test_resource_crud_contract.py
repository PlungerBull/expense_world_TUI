"""One CRUD contract, run against every resource that shares it.

Accounts, categories and hashtags are three spellings of the same command set —
`_resource.py` generates most of it — and their test files had grown into three
copies of the same thirteen tests, differing only in a noun, a flag and a
fixture. test_cmd_categories.py and test_cmd_hashtags.py had the *same test
names in the same order*.

Three copies is not three times the safety. It is one contract asserted three
times and, in practice, extended once: `--include-deleted` gained a marked
column on categories and accounts and never on hashtags; the pagination hint is
checked with a different total in each file for no reason anyone recorded. A
rule with three homes drifts in two of them.

So the shared shape lives here, parametrized by `ResourceSpec`, and each
per-resource file keeps exactly what is its own — the hints it prints, the flags
only it has, and the arms only it can take (accounts archive and unarchive;
categories and hashtags lost those routes on 2026-08-06).

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
from tests.unit.helpers import error_response, make_cli_app, page

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
    #: A second, soft-deleted row: what `--include-deleted` has to surface.
    deleted_name: str
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
    deleted_name="Closed Account",
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
    deleted_name="Old Hobby",
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
    deleted_name="retired-tag",
)

RESOURCES = [ACCOUNT, CATEGORY, HASHTAG]

#: Every parametrized test takes `spec`; `ids=str` prints the resource name, so a
#: failure says `test_get_404[hashtags]` and not `test_get_404[spec2]`.
resource = pytest.mark.parametrize("spec", RESOURCES, ids=str)


def _cli(spec: ResourceSpec):
    return make_cli_app(spec.app, spec.name)


def _run(spec: ResourceSpec, *args: str):
    return runner.invoke(_cli(spec), [spec.name, *args])


def _deleted_row(spec: ResourceSpec) -> dict:
    return {
        **spec.sample,
        "id": "99999999-9999-9999-9999-999999999999",
        "name": spec.deleted_name,
        "deleted_at": "2026-06-01T09:00:00Z",
    }


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@resource
@respx.mock
def test_list_bare_sends_no_include_params(spec, configured):
    """A default list asks the engine for the default scope — no include_* flags.

    Archived and deleted rows are opt-in on every resource that has them; a flag
    that leaked into the default would quietly change what the command means.
    """
    route = respx.get(f"{BASE}/v1/{spec.name}").mock(
        return_value=httpx.Response(200, json=[spec.sample])
    )
    result = _run(spec, "list")

    assert result.exit_code == 0, result.output
    assert spec.label in result.output
    params = route.calls.last.request.url.params
    assert params.get("include_archived") is None
    assert params.get("include_deleted") is None


@resource
@respx.mock
def test_list_include_deleted_marks_the_rows_it_brings_back(spec, configured):
    """The flag reaches the engine, the row reaches the screen, and the screen
    says which row is the dead one.

    All three matter. Asserting only the query param would pass on a command
    that fetched the deleted rows and filtered them back out; asserting only the
    name would pass on a list that showed a tombstone as if it were live.

    This assertion existed twice — accounts and categories, written out
    identically — and never for hashtags, which is the drift the shared contract
    exists to stop: hashtags had the column all along and nothing said so.
    """
    route = respx.get(f"{BASE}/v1/{spec.name}").mock(
        return_value=httpx.Response(200, json=[spec.sample, _deleted_row(spec)])
    )
    result = _run(spec, "list", "--include-deleted")

    assert result.exit_code == 0, result.output
    assert "Deleted" in result.output

    lines = result.output.splitlines()
    live_row = next(line for line in lines if spec.label in line)
    dead_row = next(line for line in lines if spec.deleted_name in line)
    assert live_row.rstrip().endswith("no")
    assert dead_row.rstrip().endswith("yes")

    assert route.calls.last.request.url.params.get("include_deleted") == "true"


@resource
@respx.mock
def test_list_pagination_hint_when_truncated(spec, configured):
    """`render_pagination_hint` is shared, but each command has to call it."""
    respx.get(f"{BASE}/v1/{spec.name}").mock(
        return_value=httpx.Response(200, json=page([spec.sample], total=5, limit=1, offset=0))
    )
    result = _run(spec, "list")

    assert result.exit_code == 0, result.output
    assert "showing 1 of 5" in result.output


@resource
@respx.mock
def test_list_json_is_the_engine_body_verbatim(spec, configured):
    """CLAUDE.md "Human default, JSON opt-in": `--json` is a pass-through, never
    a re-rendering."""
    body = [spec.sample]
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
# delete / restore
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


@resource
@respx.mock
def test_restore_is_prompt_free(spec, configured):
    """Restore is reversible, so it asks nothing — the same call the archive
    toggles get (docs/decisions.md, archive reclassified 2026-07-11)."""
    route = respx.post(f"{BASE}/v1/{spec.name}/abc/restore").mock(
        return_value=httpx.Response(200, json=spec.sample)
    )
    result = _run(spec, "restore", "abc")

    assert result.exit_code == 0, result.output
    assert route.called


# ---------------------------------------------------------------------------
# the error shape, on every verb
# ---------------------------------------------------------------------------
#
# CLAUDE.md asks every command for a happy path AND an error shape. The error
# half was missing on `list`, `create` and `restore` across all three resources
# — the verbs whose happy path is the nicest to write. Parametrized here, the
# rule is satisfied for nine commands by three tests, and a fourth resource
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
def test_restore_refusal_surfaces_the_engine_envelope(spec, configured):
    """Restoring into a name a live row now holds is refused.

    Categories print an extra hint on this shape and hashtags do not; what both
    owe the user is the engine's own sentence, which is what this asserts.
    """
    respx.post(f"{BASE}/v1/{spec.name}/abc/restore").mock(
        return_value=error_response(409, "CONFLICT", "A live row holds that name.")
    )
    result = _run(spec, "restore", "abc")

    assert result.exit_code == 1
    assert "CONFLICT" in result.output
