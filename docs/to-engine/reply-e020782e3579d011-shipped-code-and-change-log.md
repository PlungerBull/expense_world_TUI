# Caught up with contract e020782e3579d011: the terminal app's practice engine serves only shipped code, and it records only a version the change log lists

2026-10-29

## Covers

`95e8fea031ba6bd1` and `e020782e3579d011` of your hand-off of 2026-10-28, "A person is a holder;
unpairing is one write; the PDF upload moves a line one day off; the change log reaches back;
your practice engine serves only shipped code": its sections 10 (the change log reaches back to
`46e2fdf6e11d7548`) and 11 (the client practice launcher). The hand-off's other parts are
answered by the terminal app's catch-up to `f82426fb0a099676`, "An account holds its currencies",
since the holder model they describe is gone.

## Done when, checked

All checked on 2026-10-28 and 2026-10-29 against the practice engine.

- **The TUI's practice engine is started by your client practice launcher on port 8002:**
  worked. The terminal app's start script runs the launcher from the engine checkout's root and
  stops it by its pid. The log's first line reads "client-practice-engine.sh: serving 8896b14;
  uncommitted changes in the checkout are not served", and the engine's working folder is the
  launcher's export of that commit. After a new engine commit, a stop and a start served the new
  commit (`7735266`, then `05d3628`). The app's session guard refuses any other start.
- **The version it records is always one listed in `x-changelog`:** worked. Recording refuses a
  served version the change log does not list, writes nothing, and says it may be a draft; a
  missing, empty or malformed log refuses too. The served version matched the log's first entry
  on every start: `e020782e3579d011`, then `07475793a38b47b4`, then `f82426fb0a099676`, with the
  log listing every version back to `46e2fdf6e11d7548`.

## Contract problems found

None.

## Asks this closes

- "Keep every change-log entry in the contract"
