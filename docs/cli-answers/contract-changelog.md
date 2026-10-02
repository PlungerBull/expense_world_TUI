# `/openapi.json` carries a change log of every contract version

Shipped 2026-09-27 (a CLI request) · ➕ additive · contract section *The contract*

## What changed

`/openapi.json` carries `x-changelog`, newest first. Its first entry is always the current `info.version`.

## What the CLI does

When the version moves, list the entries above the one the CLI holds, instead of using its fixture-drift fallback. A version the log doesn't list means everything is treated as changed.

## Done when

The CLI reads `x-changelog`.
