# A bank account's bank is a 3–4 letter code the user types, its last 4 is required, and only a bank `GET /banks` lists takes a statement code

2026-11-13

## Why

A bank account must be at a bank `GET /banks` lists, and it lists BCP alone, so the owner's two
closed Interbank accounts can't be made (contract: GET /v1/banks). The engine's answer to "The
engine says why its bank list is closed" says the bank does two things: it is checked when an
account is made, and it builds the account's name (`BCP-5678`). The one thing a bank changes is
whether the engine reads its statement PDFs, which only BCP's are, and a coded account completes
a statement only from its PDF.

So for the owner a bank is the letters in an account's name. Making one takes a code and the last
4 digits (`IBK` and `4321` make `IBK-4321`), and BCP's accounts also take a statement code. This
is how Firefly III and the big apps work: you make an account, then pick it when logging or
importing, with no list of banks to keep. The one difference is the name, always `CODE-1234`
here.

## The ask

- **`bank_code` is any code of 3 or 4 letters the user types,** in `POST /accounts`,
  `PUT /accounts/{account_id}` and `POST /accounts/{account_id}/make-account`. No bank has to exist
  first. Whether lowercase is refused or upper-cased is the engine's call, written in the contract.
- **A bank account's last 4 is required** in all three. Its name is always `CODE-1234`, built by
  the engine; there is no account named `IBK` alone. A write that would leave a bank account with
  no number is refused, so the Edit form can remove a number only while another stays. What
  becomes of an existing bank account with no number is the engine's call, said in the hand-off.
- **`GET /banks` does not change:** it lists BCP alone. Its meaning changes from "the banks you
  may use" to "the banks whose statement PDFs the engine can read".
- **A statement code is refused** on an account whose bank `GET /banks` does not list, with a
  refusal reason of its own that names the code.
- **No new check on bank downloads.** The check that exists stays: a statement PDF's card number
  must be one of the account's numbers.
- People and cash keep their names as now; the code and last 4 are for bank accounts only.

## Done when

- `IBK` with `4321` makes `IBK-4321`, and a second `IBK` account with another last 4 is made too.
- `IBK` with no last 4 is refused.
- An `IBK` account refuses a statement code, with the new reason naming `IBK`; a BCP account
  takes one as today.
- `GET /banks` still lists BCP alone.

## What this client removes once it lands

The BANK line's pick from `GET /banks` becomes a typed code; `GET /banks` is then read only to
decide whether the account form shows its statement code line. The ask "GET /banks lists every
bank the owner's accounts were at" is withdrawn.
