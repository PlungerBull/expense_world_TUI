# A user's settings hold their number format

Raised 2026-11-08.

## Why

People write amounts in one of two ways: `1,234.56` (dot for decimals) or `1.234,56` (comma for
decimals). Each client reads what the person types and shows every amount in that person's
format. The format belongs to the person, not the device, so every client should agree on it, and
only the engine can hold a value every client reads. Today each client can only guess from the
device's region, and a new device guesses again.

## The ask

1. **A `number_format` on the user's settings,** one of `"1,234.56"` and `"1.234,56"`, or `null`
   when the user has picked none, in which case each client follows its device's region.
2. **`PUT /v1/auth/settings` takes it:** a listed value saves it, `null` clears it, and any other
   value is a `422` on `number_format` with its own reason code, nothing written.
3. **`GET /v1/auth/me` returns it** in `settings`, `null` included, so a client knows whether the
   user picked one.
4. The contract states the field, its two values and what `null` means.

The engine's own amounts stay as they are: every request and answer carries whole cents, and no
amount the engine reads or writes changes with the setting.

## Done when

- `PUT /v1/auth/settings` with `{"number_format": "1.234,56"}` saves it, and `GET /v1/auth/me`
  then returns it in `settings`.
- `{"number_format": null}` clears it, and `GET /v1/auth/me` returns `null`.
- `{"number_format": "1 234,56"}` is a `422` on `number_format`, nothing written.
- A user who never set it reads `null`.

## What this client removes once it lands

The terminal client reads the format from the Mac's region alone, so a pick on one device does
not reach another. Once this lands, the user's pick, saved on their account, wins over the region
on every device.
