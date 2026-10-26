#!/usr/bin/env python3
"""Remove what tests left on the practice user, matched by the names tests give.

The live contract tests name what they build `contract-…` or `freshman-…`
(`TEST_NAME_PREFIXES`) and undo it at teardown, best-effort; a test whose teardown leaves
a record fails (`leaves_nothing` in tests/contract/conftest.py). Records such a test left,
or a probe run by hand against the practice engine, stay on the practice user: accounts
holding statement codes, reconciliations filling the Reconciliations browse. This script
finds them by name and removes them through the engine's own API, in the order its
deletes need:

  1. every matched archived account is unarchived (an archived account refuses every
     reconciliation write and every transaction delete);
  2. every completed statement on a matched account is reverted, then every statement is
     deleted once, both halves of a card together
     (contract: DELETE /v1/reconciliations/{reconciliation_id});
  3. every live transaction on a matched account is deleted;
  4. every matched hashtag no live transaction carries any more, every matched category
     and every matched account is deleted.

A record is matched only by its own name starting with a prefix, and a system category or
hashtag, which the engine creates for itself and never deletes, never. A matched account's
reconciliations and transactions go with it; nothing else is touched. A card statement
whose other half sits on an account that is not matched is left whole, since deleting one
half deletes both. A hashtag still on a live transaction is left, since deleting it would
rewrite that transaction (contract: DELETE /v1/hashtags/{hashtag_id}). A category or an
account the engine refuses to delete is left. Each is listed as left, and the run exits 1.

Without `--apply` it only reads, and prints what it would remove. It talks only to the
practice engine (`127.0.0.1` or `localhost` on `:8002`) and takes the practice user's key
only from `EXPENSE_PAT`, never from a config file; `--apply` after it removes:

    EXPENSE_PAT=<key> python scripts/clean_practice_user.py --engine-url http://127.0.0.1:8002

`--prefix P` (repeatable) matches names starting with `P` in place of the test prefixes,
for records a hand-run probe named its own way. How to get a key: docs/runtime.md
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

#: The name prefixes the live contract tests give what they build. A record a test leaves
#: fails that test whatever its name (`leaves_nothing` in tests/contract/conftest.py).
TEST_NAME_PREFIXES = ("contract-", "freshman-")

_PRACTICE_HOSTS = frozenset({"127.0.0.1", "localhost"})
_PRACTICE_PORT = 8002
_COMPLETED = 2
_PAGE = 200


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


def user_rows(client: ExpenseClient, path: str) -> list[dict]:
    """The caller's categories or hashtags at `path`, without the system rows, those with a
    non-null `system_key`, which the engine creates for itself on first need and never
    deletes (contract: "Categories", "Engine-created system categories")
    (contract: "Hashtags", "The built-in pending hashtag")."""
    return [row for row in client.get(path)["items"] if row.get("system_key") is None]


def holdings(client: ExpenseClient) -> dict[str, str]:
    """Every account (people and archived ones too), and every category and hashtag but
    the system rows, the caller holds: id to a label naming its kind and name. What a
    test may leave behind (`leaves_nothing` in tests/contract/conftest.py)."""
    listed = client.get("/accounts", params={"include_people": "true", "include_archived": "true"})
    held = {item["id"]: f"account {item['name']!r}" for item in listed["items"]}
    for kind, path in (("category", "/categories"), ("hashtag", "/hashtags")):
        held |= {row["id"]: f"{kind} {row['name']!r}" for row in user_rows(client, path)}
    return held


@dataclass
class Plan:
    """What one run found: the matched records, and what it leaves and why."""

    accounts: list[dict] = field(default_factory=list)
    statements: list[list[dict]] = field(default_factory=list)
    transactions: dict[str, int] = field(default_factory=dict)
    categories: list[dict] = field(default_factory=list)
    hashtags: list[dict] = field(default_factory=list)
    left: list[str] = field(default_factory=list)


def plan(client: ExpenseClient, prefixes: tuple[str, ...]) -> Plan:
    """Reads the practice user and gathers what `prefixes` match; writes nothing."""
    found = Plan()
    listed = client.get("/accounts", params={"include_people": "true", "include_archived": "true"})
    found.accounts = [a for a in listed["items"] if matches(a["name"], prefixes)]
    mine = {a["id"] for a in found.accounts}
    seen: set[str] = set()
    for account in found.accounts:
        for recon in client.get("/reconciliations", params={"account_id": account["id"]})["items"]:
            if recon["id"] in seen:
                continue
            halves = [recon]
            if recon.get("twin_id"):
                halves.append(client.get(f"/reconciliations/{recon['twin_id']}"))
            seen.update(half["id"] for half in halves)
            if all(half["account_id"] in mine for half in halves):
                found.statements.append(halves)
            else:
                names = " + ".join(repr(half["name"]) for half in halves)
                found.left.append(f"statement {names}: its other half is on an unmatched account")
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
    left = list(found.left)
    for account in found.accounts:
        if account["is_archived"]:
            _try(
                left,
                f"unarchive {account['name']!r}",
                client.post,
                f"/accounts/{account['id']}/unarchive",
            )
    for halves in found.statements:
        if any(half["status"] == _COMPLETED for half in halves):
            _try(
                left,
                f"revert {halves[0]['name']!r}",
                client.post,
                f"/reconciliations/{halves[0]['id']}/revert",
            )
        _try(
            left,
            f"delete statement {halves[0]['name']!r}",
            client.delete,
            f"/reconciliations/{halves[0]['id']}",
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
    """Deletes every live transaction on `account`, page by page, until a page holds none
    but those already refused; each refused one is listed once."""
    refused: set[str] = set()
    while True:
        page = client.get("/transactions", params={"account_id": account["id"], "limit": _PAGE})
        todo = [tx for tx in page["items"] if tx["id"] not in refused]
        if not todo:
            return
        for tx in todo:
            what = f"delete transaction {tx['id']} on {account['name']!r}"
            if _try(left, what, client.delete, f"/transactions/{tx['id']}") is None:
                refused.add(tx["id"])


def describe(found: Plan) -> list[str]:
    lines = [f"accounts: {len(found.accounts)}"]
    for a in found.accounts:
        archived = ", archived" if a["is_archived"] else ""
        code = a.get("statement_code") or "no code"
        count = found.transactions.get(a["id"], 0)
        lines.append(f"  {a['name']!r} ({a['currency_code']}, {code}{archived}), {count} tx")
    lines.append(f"statements: {len(found.statements)}")
    for halves in found.statements:
        state = "completed" if any(h["status"] == _COMPLETED for h in halves) else "draft"
        lines.append(f"  {' + '.join(repr(h['name']) for h in halves)} ({state})")
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
    with ExpenseClient(Config(engine_url=args.engine_url, token=token)) as client:
        found = plan(client, prefixes)
        print(f"matching names starting with {', '.join(map(repr, prefixes))}")
        print("\n".join(describe(found)))
        if not args.apply:
            for reason in found.left:
                print(f"would leave {reason}")
            print("read only; --apply removes the above")
            return 1 if found.left else 0
        left = apply(client, found)
        after = plan(client, prefixes)
    for reason in left:
        print(f"left {reason}")
    remaining = len(after.accounts) + len(after.categories) + len(after.hashtags)
    print(f"removed; {remaining} matched record(s) remain")
    return 1 if left or remaining else 0


if __name__ == "__main__":
    sys.exit(main())
