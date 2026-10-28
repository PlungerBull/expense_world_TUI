# Keep every change-log entry in the contract

Raised 2026-10-28.

## Why

Every client checks the contract's version when it starts work. When the version has moved, it
prints what changed by reading `x-changelog` in `/openapi.json`: every entry newer than the last
version it caught up to. That list tells the owner what to ask the engine coders a hand-off for.

On contract `88333696fca6a504`, `x-changelog` holds only its five newest entries, back to
`e7393dd869963db1`. A client that last caught up to anything older, such as `e06456a20aca6e4c`,
finds its version missing from the log. It can then only say "the whole contract changed", and
the owner cannot see which changes to ask about. With four clients catching up at their own pace,
a client five or more versions behind is the normal case, not the rare one.

## The ask

Keep every entry in `x-changelog`, newest first, from the first version a client may have
recorded, instead of only the newest five. If the log has to stay short, keep it back to a stated
version, and say in `info.description` which version that is, so a client further behind knows to
ask for a hand-off rather than read a partial list.

## Done when

`/openapi.json` lists every change-log entry back to at least `46e2fdf6e11d7548`, and a client
whose recorded version is any of them reads, in order, every change since it.

## What this client removes once it lands

Nothing it builds: the terminal app already reads the whole log. What goes is the case where its
version check falls back to "the whole contract changed" for a client a few versions behind.
