# An account holds its currencies: the holder becomes the account, and each account becomes one of its currencies

Raised 2026-10-28.

## Why

In the owner's world, a bank account is one thing that can hold several currencies: a Peruvian
credit card holds soles and dollars, a card elsewhere may hold more. The engine split each
currency into an account of its own, so that amounts in different currencies are never added into
a number with no meaning. Reconciliation then needed the real account back, and the holder was
added on top to group them.

The result is two levels that both behave like an account. Each currency's account has its own
name, colour, order, archived flag and kind (bank or person), and moves between holders; the
holder has a name, a statement code, an archived flag and a kind too. Everything the owner works
with in the app is the holder, and the per-currency account is only a vehicle to keep currencies
apart. That split is what makes pairing and unpairing, moving an account between holders, "a new
holder of its own", person holders, a holder of one account, two names for one Visa, and the rules
that `make-person`, `make-account` and the archive act on "the whole holder". Every client would
have to teach its users that structure, and the web and iOS clients would inherit it.

The two levels are right; which one is the account is not. Every multi-currency ledger has an
account and, inside it, a balance per currency. Done now, before the owner's official import and
before any client builds holder screens, this costs the least it ever will: the terminal app has
built no holder screen yet, and its live tests on holders are not written.

## The ask

Make the holder the account, and each of today's accounts one currency of it.

| Today | After |
|---|---|
| a holder | **the account**: name, colour, order in its list, kind (bank or person), statement code, archived flag, and its currencies |
| an account, one currency of a holder | **a currency of the account**: its currency code, its opening balance and its balance; nothing else |
| the account's own name, colour, order, kind and archived flag | gone: they are the account's |
| moving an account between holders, pairing, unpairing, a person holder, `HOLDER_*` reasons | gone: a currency is added to an account, or removed while nothing is booked in it |
| `make-person`, `make-account`, archive and unarchive on the holder | on the account, which is now the one thing they act on |

What clients need from it:

1. **Reads:** `GET /accounts` lists accounts, each with its currencies and a balance per
   currency, its opening balance per currency, its kind and its statement code. No `/holders`
   routes are left.
2. **Writes on an account:** created with one or more currencies in one write (the Visa in soles
   and dollars, ALEJO in soles and dollars); a currency added later; a currency removed only while
   nothing is booked in it; renamed, recoloured, reordered, archived, unarchived, turned into a
   person and back, and deleted, each on the account, all its currencies at once. Two currencies
   of one account cannot share a currency code.
3. **A currency of an account is named by the account and its currency code** wherever a client
   sends or reads one: a transaction, a bank line, an opening balance, a bank download, a
   statement balance, a report or dashboard row. A transaction in a currency the account does not
   hold is refused, nothing written. How the engine keeps them inside, an id per currency
   included, is the engine's choice; clients never need to handle a currency's own id.
4. **Statements** belong to the account, one per account per month, with a starting and ending
   balance per currency, as a holder's statement does today; the PDF upload and the bank download
   name the account (and, for the bank download, which is in one currency, the currency).
5. **Moving the data:** each holder becomes an account with its name, kind, statement code and
   archived flag; each of its accounts becomes one of its currencies, with the same transactions,
   bank lines, opening balance and statement balances; the account takes the colour and order of
   its first currency's account. Every balance and report total reads the same before and after.
   The owner's ledger is moved the same way.
6. **The change log and the hand-off** say what each route, field and reason became, so every
   client can catch up from the version it last read.

The owner settled two points on 2026-10-28: a currency of an account has no name of its own (it
shows as the account's name and its currency, "VISA Infinite Sapphire · USD"), and colour is the
account's, shared by its currencies.

## Done when

- `GET /accounts` lists the Visa as one account holding PEN and USD, a balance for each, and no
  route or field names a holder.
- The Visa in soles and dollars, and ALEJO in soles and dollars, are each created in one write; a
  third currency is added to an account later, and a currency with nothing booked is removed.
- A transaction names an account and a currency it holds; one in a currency the account does not
  hold is refused, nothing written.
- Archiving, unarchiving, turning into a person and back, and deleting act on the account, all its
  currencies at once.
- A statement is the account's, with a starting and ending balance per currency, and the PDF
  upload closes it.
- After the data moves, every account balance, every report total and every statement reads the
  same as before, on the practice data and on the owner's ledger.

## What this client removes once it lands

The terminal app drops every notion of a holder: grouping its accounts by holder to pair a card's
currencies, reading the holders to find a statement code, the planned holder line on the Edit form
that paired and unpaired accounts, the planned person-holder handling, and the notes that say an
archive or a change of kind reached "every account of the holder". A card shows as one account
with a balance per currency, and a transaction picks the account, then its currency.
