# Change-log entries are added, never replaced

Raised 2026-09-28 by the CLI client.

## Why

A client saves the contract version it last checked and, when `info.version` moves, lists every
`x-changelog` entry above the one it holds. That only works if every version a client may have
seen stays in the log. On 2026-09-28 the practice engine served `ef2132c3c3b2ff6f`, with its own
change-log entry; a few hours later it served `fa88ffe22f4e86f2`, and the log went straight from
`fa88ffe22f4e86f2` to `b2405c2af20fb7e6`: the `ef2132c3c3b2ff6f` entry was replaced, not added
to. A client that had recorded `ef2132c3c3b2ff6f` can no longer find it and is told the whole
contract changed, which is the one outcome the change log exists to avoid.

## The ask

Once a version has been served, its change-log entry stays. A new version adds a new entry on
top, even when it only rewords the previous one ("wording only, …"), as the log already does for
wording changes.

## Done when

- Every `info.version` the engine has served appears in `x-changelog`.
- The engine's tests fail if an entry for a previously published version is removed or its
  version renamed.

## What the CLI removes once it lands

Nothing in code. It stops asking the owner to confirm a version whose history is missing from
the log.
