# An error's `details` has a published shape for each refusal that carries one

Raised 2026-11-11.

## Why

Contract `3a4ff8dac458cf83` publishes `ErrorBody.details` as an open object
(`anyOf: [{type: object, additionalProperties: true}, null]`). The one shape it carries today,
`{"bank_line_ids": [...], "count": N}` on `LOOSE_LINES_ON_SEALED_DAYS`, is stated only in the
prose of `POST /statements/{id}/complete` and `POST /statements/import`. A client reads those
keys with nothing in the schema naming them, so it cannot check that the keys it reads exist,
and a renamed or retyped key would surface only as a broken screen. This client's check that
every field its tests expect is one the engine publishes flags `bank_line_ids` as unknown, and
every later client meets the same gap with each new refusal that fills `details`.

## The ask

1. **Each `details` shape is a named schema in `/openapi.json`,** for example
   `LooseLinesDetails` with `bank_line_ids` (array of ids, at most 200) and `count` (integer, the
   full number), both required.
2. **The error body says which schema `details` takes,** on the operations whose refusal fills
   it (`POST /statements/{id}/complete`, `POST /statements/import`, dry run and apply), for
   example as a `oneOf` of the published shapes and `null`, or a schema per refusal named in the
   operation's responses.
3. **Every later refusal that fills `details`** publishes its shape the same way.

## Done when

- `/openapi.json` names `bank_line_ids` and `count` as properties of a published schema, with
  their types and the 200 cap.
- The two operations' error responses point at that schema for `LOOSE_LINES_ON_SEALED_DAYS`.

## What this client removes once it lands

Its fixture check exempts `bank_line_ids` as a key the engine sends but does not publish; with the
schema published, the exemption goes and the check proves the key like any other field.
