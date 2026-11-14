# A bank account is at a bank from the engine's catalogue or one the user adds, and each bank says what the engine can read for it

2026-11-13

## Why

`GET /banks` lists BCP alone, the same for every user, and adding a bank takes a migration
(contract: GET /v1/banks). The owner's ledger holds two closed accounts at Interbank, and every
other user banks somewhere of their own. The engine's answer to "The engine says why its bank
list is closed" says nothing in the ledger needs the list fixed: the bank is checked when an
account is made and builds its name, and nothing else.

It also says the BCP readers look at the file, not at the account's bank: once a second bank
exists, a BCP download lands on an Interbank account without a word. And a coded account can
only complete a statement from its PDF, so a statement code on an account at a bank the engine
cannot read leaves it unable to close.

A finance app has a list of banks to pick from and a way to add one it lacks. The catalogue
gives every user the common banks, and the names they go by, from the start; a bank the user
adds covers the rest at once.

## The ask

- **A catalogue of known banks,** kept by the engine and the same for every user: the banks of
  Peru, BCP and Interbank at least. Each carries its code (`INTERBANK`), its name ("Interbank"),
  the other names it goes by (`IBK`) and what the engine can read for it: BCP its downloads, its
  savings PDF and its Visa PDF, the others nothing until a reader exists.
- **A bank the user adds:** a code (letters, as the name format allows) and a name, optional
  other names, reading nothing. It is the user's own record: an id, history and soft delete, as an
  account has. Its code cannot be a catalogue bank's, and it cannot claim a catalogue bank's
  readers. One the user's accounts use cannot be deleted.
- **`GET /banks` lists both,** each saying whether it is the catalogue's or the user's and what
  can be read for it, in the order a picker shows them.
- **A bank account points at its bank** as the engine sees fit (by id, as the answer proposes),
  and its name is built from that bank's code as now (`INTERBANK-1234`).
- **Reading follows the bank:** a download or a statement PDF is refused on an account whose bank
  has no reader for that file, with a refusal reason of its own that names the account's bank.
- **A statement code is refused** on an account at a bank with no PDF reader; such an account's
  statements close by hand.
- The change to accounts comes as a hand-off file, as the answer says, so this client catches up
  in one spec.

## Done when

- `GET /banks` lists BCP and Interbank from the catalogue, each with its name, its other names
  and what can be read for it.
- A user adds a bank; an account is made at it and named from its code; the bank cannot be
  deleted while that account lives; another user does not see it.
- A BCP download on an account at Interbank is refused with the new reason, naming Interbank; the
  same file on a BCP account lands as today.
- An account at Interbank, or at a bank the user added, refuses a statement code.

## What this client removes once it lands

Nothing to remove: the account forms show whatever `GET /banks` returns. It replaces the ask
"GET /banks lists every bank the owner's accounts were at", which is withdrawn.
