# A pasted token is saved without its spaces

**Status: approved 2026-11-13.** When done, the why moves to [decisions.md](../decisions.md) and
this file is deleted.

---

## Why

Setup trims a pasted token; System ▸ Config `t` saves it as pasted. A trailing space from the
paste makes every request fail as a refused header, on every screen, until the token is pasted
again.

## What it must do

1. **`t` in System ▸ Config saves the token without the spaces around it,** as Setup does.
2. **Nothing else the owner sees changes.**

## How the owner knows it is done

1. A token pasted with a space before and after, through `t`, is saved without them, and the
   app's next request carries it.
2. `pytest tests/unit` passes.

---

## Tasks

1. **`t` trims the token as Setup does,** with a unit test for a token pasted with spaces
   around it.

## Found along the way

Not built in this spec; sorted when it is done.
