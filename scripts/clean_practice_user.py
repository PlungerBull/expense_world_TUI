#!/usr/bin/env python3
"""Remove what tests left on the practice user, matched by the names and numbers tests give.

The live contract tests name what they build `contract-…` or `freshman-…`
(`TEST_NAME_PREFIXES`) and undo it at teardown, best-effort; a test whose teardown leaves
a record fails (`leaves_nothing` in tests/contract/conftest.py). A bank account's name is the
engine's (`BCP-9234`), so the suite marks its bank accounts by their number instead: every one
is numbered with last 4 digits starting `9` (`TEST_LAST4_PREFIX`). Records such a test left,
or a probe run by hand against the practice engine, stay on the practice user: accounts
holding statement codes, statements filling an account's list. This script finds them and
removes them through the engine's own API, in the order its deletes need:

  1. every matched archived account is unarchived (an archived account refuses every
     statement write and every transaction delete);
  2. every statement of a matched account, read with `GET /statements?account_id=`
     (contract: GET /v1/statements, "`?account_id=<id>` is required"), is reverted when
     completed (contract: POST /v1/statements/{statement_id}/revert), then deleted
     (contract: DELETE /v1/statements/{statement_id});
  3. every live transaction on a matched account is deleted, on every page, reading past
     a page that holds only deletes the engine refused;
  4. every matched hashtag no live transaction carries any more, every matched category
     and every matched account, whole with all its currencies in one delete
     (contract: DELETE /v1/accounts/{account_id}), is deleted.

A category, hashtag or person is matched only by its own name starting with a prefix; a bank
account only by one of its numbers starting with `TEST_LAST4_PREFIX`, never by its name. A
system category or hashtag, which the engine creates for itself and never deletes, is never
matched, and neither is the practice account `BCP-0000` the seed holds (`PRACTICE_ACCOUNT`),
whatever it is asked to match. The seed gives the practice user no cash account, so every cash
account it holds is one a test made: a default run matches each (`owns`), a `--prefix` run none.
A matched account's
statements and transactions go with it; nothing else is touched. A hashtag still on a
live transaction is left, since deleting it would rewrite that transaction
(contract: DELETE /v1/hashtags/{hashtag_id}). A category or an account the engine refuses
to delete is left. Each is listed as left, and the run exits 1.

Without `--apply` it only reads, and prints what it would remove. It talks only to the
practice engine (`127.0.0.1` or `localhost` on `:8002`) and takes the practice user's key
only from `EXPENSE_PAT`, never from a config file; `--apply` after it removes:

    EXPENSE_PAT=<key> python scripts/clean_practice_user.py --engine-url http://127.0.0.1:8002

`--prefix P` (repeatable) matches names starting with `P` in place of the test prefixes and
numbers, for records a hand-run probe named its own way. How to get a key: docs/runtime.md
"Working against the live engine".
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from expense.config import Config
from expense.errors import EngineError
from expense.http import ExpenseClient
from expense.reads import held_currencies

#: The name prefixes the live contract tests give what they build. A record a test leaves
#: fails that test whatever its name (`leaves_nothing` in tests/contract/conftest.py).
TEST_NAME_PREFIXES = ("contract-", "freshman-")
#: How the last 4 digits of every bank account the live contract tests make start: a bank
#: account's name is built by the engine, so this number is what marks it as the suite's.
TEST_LAST4_PREFIX = "9"
#: The seed's practice account, which no run ever removes.
PRACTICE_ACCOUNT = "BCP-0000"

_PRACTICE_HOSTS = frozenset({"127.0.0.1", "localhost"})
_PRACTICE_PORT = 8002
_COMPLETED = 2
_PAGE = 200
_STATEMENTS = "/statements"


def practice_url(url: str) -> bool:
    """True only for the practice engine: http on 127.0.0.1 or localhost, port 8002."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        return False
    return parts.scheme == "http" and parts.hostname in _PRACTICE_HOSTS and port == _PRACTICE_PORT


def matches(name: str | None, prefixes: tuple[str, ...]) -> bool:
    return bool(name) and any(name.startswith(prefix) for prefix in prefixes)


def owns(account: dict, prefixes: tuple[str, ...], last4_prefix: str | None) -> bool:
    """True for an account a run matches: a person by its name (`prefixes`), a bank account by
    a number starting `last4_prefix` (none given: by no number); a cash account, which has no
    name of its own to match or number, whenever `last4_prefix` is given (a default run); the
    practice account never."""
    if account["name"] == PRACTICE_ACCOUNT:
        return False
    if account["kind"] == "person":
        return matches(account["name"], prefixes)
    if account["kind"] == "cash":
        return last4_prefix is not None
    return last4_prefix is not None and any(
        number["last4"].startswith(last4_prefix) for number in account["numbers"]
    )


def user_rows(client: ExpenseClient, path: str) -> list[dict]:
    """The caller's categories or hashtags at `path`, without the system rows, those with a
    non-null `system_key`, which the engine creates for itself on first need and never
    deletes (contract: "Categories", "Engine-created system categories")
    (contract: "Hashtags", "The built-in pending hashtag")."""
    return [row for row in client.get(path)["items"] if row.get("system_key") is None]


def holdings(client: ExpenseClient) -> dict[str, str]:
    """Every account (people, cash and archived ones too), and every category and hashtag but
    the system rows, the caller holds: id to a label naming its kind and name. What a test may
    leave behind (`leaves_nothing` in tests/contract/conftest.py)."""
    listed = client.get("/accounts", params={"include_people": "true", "include_archived": "true"})
    held = {item["id"]: f"account {item['name']!r}" for item in listed["items"]}
    for kind, path in (("category", "/categories"), ("hashtag", "/hashtags")):
        held |= {row["id"]: f"{kind} {row['name']!r}" for row in user_rows(client, path)}
    return held


@dataclass
class Plan:
    """What one run found: the matched records."""

    accounts: list[dict] = field(default_factory=list)
    statements: list[dict] = field(default_factory=list)
    transactions: dict[str, int] = field(default_factory=dict)
    categories: list[dict] = field(default_factory=list)
    hashtags: list[dict] = field(default_factory=list)


def plan(
    client: ExpenseClient,
    prefixes: tuple[str, ...],
    last4_prefix: str | None = TEST_LAST4_PREFIX,
) -> Plan:
    """Reads the practice user and gathers what `prefixes` and `last4_prefix` match
    (`owns`); writes nothing."""
    found = Plan()
    listed = client.get("/accounts", params={"include_people": "true", "include_archived": "true"})
    found.accounts = [a for a in listed["items"] if owns(a, prefixes, last4_prefix)]
    for account in found.accounts:
        found.statements += client.get(_STATEMENTS, params={"account_id": account["id"]})["items"]
        count = client.get("/transactions/count", params={"account_id": account["id"]})["count"]
        found.transactions[account["id"]] = count
    found.categories = [c for c in user_rows(client, "/categories") if matches(c["name"], prefixes)]
    found.hashtags = [h for h in user_rows(client, "/hashtags") if matches(h["name"], prefixes)]
    return found


def _try(left: list[str], what: str, call, path: str) -> dict | None:
    try:
        return call(path)
    except EngineError as err:
        left.append(f"{what}: {err.status} {err.code} {err.reasons or err.message}")
        return None


def apply(client: ExpenseClient, found: Plan) -> list[str]:
    """Removes what `plan` found, in the order the engine's deletes need; what it left."""
    left: list[str] = []
    for account in found.accounts:
        if account["is_archived"]:
            _try(
                left,
                f"unarchive {account['name']!r}",
                client.post,
                f"/accounts/{account['id']}/unarchive",
            )
    for statement in found.statements:
        if statement["status"] == _COMPLETED:
            _try(
                left,
                f"revert {statement['name']!r}",
                client.post,
                f"{_STATEMENTS}/{statement['id']}/revert",
            )
        _try(
            left,
            f"delete statement {statement['name']!r}",
            client.delete,
            f"{_STATEMENTS}/{statement['id']}",
        )
    for account in found.accounts:
        _delete_transactions(client, account, left)
    for hashtag in found.hashtags:
        held = client.get("/transactions/count", params={"hashtag_id": hashtag["id"]})["count"]
        if held:
            left.append(f"hashtag {hashtag['name']!r}: still on {held} live transaction(s)")
            continue
        _try(
            left, f"delete hashtag {hashtag['name']!r}", client.delete, f"/hashtags/{hashtag['id']}"
        )
    for category in found.categories:
        _try(
            left,
            f"delete category {category['name']!r}",
            client.delete,
            f"/categories/{category['id']}",
        )
    for account in found.accounts:
        _try(
            left, f"delete account {account['name']!r}", client.delete, f"/accounts/{account['id']}"
        )
    return left


def _delete_transactions(client: ExpenseClient, account: dict, left: list[str]) -> None:
    """Deletes every live transaction on `account`, following the list's cursor page by
    page, so a page holding only refused deletes does not hide the rows behind it
    (contract: "Base Conventions", "Cursors, on every cursor-paged list"); each refused
    transaction is listed once."""
    refused: set[str] = set()
    after = None
    while True:
        params = {"account_id": account["id"], "limit": _PAGE}
        if after:
            params["after"] = after
        page = client.get("/transactions", params=params)
        for tx in page["items"]:
            if tx["id"] in refused:
                continue
            what = f"delete transaction {tx['id']} on {account['name']!r}"
            if _try(left, what, client.delete, f"/transactions/{tx['id']}") is None:
                refused.add(tx["id"])
        after = page.get("next_cursor")
        if not after:
            return


def describe(found: Plan) -> list[str]:
    lines = [f"accounts: {len(found.accounts)}"]
    for a in found.accounts:
        archived = ", archived" if a["is_archived"] else ""
        code = a.get("statement_code") or "no code"
        count = found.transactions.get(a["id"], 0)
        held = (
            ", ".join(entry["currency_code"] for _, _, entry in held_currencies([a]))
            or "no currency"
        )
        lines.append(f"  {a['name']!r} ({held}; {code}{archived}), {count} tx")
    lines.append(f"statements: {len(found.statements)}")
    for statement in found.statements:
        state = "completed" if statement["status"] == _COMPLETED else "draft"
        lines.append(f"  {statement['name']!r} ({state})")
    lines.append(f"categories: {len(found.categories)}")
    lines.extend(f"  {c['name']!r}" for c in found.categories)
    lines.append(f"hashtags: {len(found.hashtags)}")
    lines.extend(f"  {h['name']!r}" for h in found.hashtags)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine-url", required=True, help="the practice engine, :8002")
    parser.add_argument("--apply", action="store_true", help="remove; without it, only read")
    parser.add_argument(
        "--prefix", action="append", help="a name prefix to match, in place of the tests'"
    )
    args = parser.parse_args(argv)
    if not practice_url(args.engine_url):
        print(f"refusing {args.engine_url}: only the practice engine on :8002", file=sys.stderr)
        return 2
    token = os.environ.get("EXPENSE_PAT")
    if not token:
        print("EXPENSE_PAT is not set: pass the practice user's key inline", file=sys.stderr)
        return 2
    prefixes = tuple(args.prefix) if args.prefix else TEST_NAME_PREFIXES
    last4_prefix = None if args.prefix else TEST_LAST4_PREFIX
    with ExpenseClient(Config(engine_url=args.engine_url, token=token)) as client:
        found = plan(client, prefixes, last4_prefix)
        print(f"matching names starting with {', '.join(map(repr, prefixes))}")
        if last4_prefix:
            print(f"and bank accounts numbered {last4_prefix}xxx")
        print("\n".join(describe(found)))
        if not args.apply:
            print("read only; --apply removes the above")
            return 0
        left = apply(client, found)
        after = plan(client, prefixes, last4_prefix)
    for reason in left:
        print(f"left {reason}")
    remaining = len(after.accounts) + len(after.categories) + len(after.hashtags)
    print(f"removed; {remaining} matched record(s) remain")
    return 1 if left or remaining else 0


if __name__ == "__main__":
    sys.exit(main())
