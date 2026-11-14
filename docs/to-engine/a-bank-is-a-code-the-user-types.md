# A bank account's bank is a short code the user types, and the engine says which codes it can read

2026-11-13

## Why

`GET /banks` lists BCP alone, the same for every user, and adding a bank takes a migration
(contract: GET /v1/banks). The owner's ledger holds two closed accounts at Interbank. The engine's
answer to "The engine says why its bank list is closed" says the bank does two things: it is
checked when an account is made, and it builds the account's name (`BCP-5678`). The only
behaviour tied to a bank is reading its files, and those readers look at the file, not at the
account's bank, so once a second bank exists a BCP download lands on an Interbank account without
a word. A coded account can only complete a statement from its PDF.

So a bank is a label: the letters in an account's name, plus whether the engine reads its papers.
It needs no list of its own, no record, no full name and no screen.

## The ask

- **`bank_code` is any short code the user types:** letters, up to the 10 the name format allows,
  in `POST /accounts`, `PUT /accounts/{id}` and `make-account`. The name is built from it as now
  (`IBK-4321`, or `IBK` until it has a number). No bank has to exist first.
- **`GET /banks` lists the codes the engine can read** (BCP), each with what it reads (its
  downloads, its savings PDF, its Visa PDF), and the codes the user's accounts already use,
  reading nothing, so every client suggests the same codes and shows the same "reads" note.
- **Reading follows the code:** a download or a statement PDF is refused on an account whose code
  has no reader for that file, with a refusal reason of its own that names the account's code.
- **A statement code is refused** on an account whose code has no PDF reader; its statements close
  by hand.

## Done when

- `POST /accounts` with `bank_code: "IBK"` and a last 4 makes `IBK-4321`; two such accounts with
  different last 4s both exist; `GET /banks` then lists `IBK` beside BCP, reading nothing.
- A BCP download on the `IBK` account is refused with the new reason; the same file on a BCP
  account lands as today.
- An `IBK` account refuses a statement code.

## What this client removes once it lands

Nothing to remove: the BANK line takes what is typed and suggests what `GET /banks` returns. It
replaces the ask "GET /banks lists every bank the owner's accounts were at", which is withdrawn.
