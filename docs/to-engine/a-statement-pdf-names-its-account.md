# A statement PDF's upload names its account from the card number the paper prints

2026-11-13

## Why

Every statement PDF prints the card or account number it belongs to, and every bank account
now carries its number (its last 4, and the earlier cards' numbers). Yet the upload still
needs the client to send the account, so the owner picks it from a list on every paper: one more
step that the paper already answers, and a wrong pick that the engine then refuses. Every client
(terminal, web, iOS) would build the same picker.

## The ask

- The PDF upload, its dry run and its apply, accepts no account. When none is sent, the engine
  reads the number printed on the paper and takes the owner's account that holds that number,
  as its current card or an earlier one.
- The answer names the account it took, so a client can show it on the preview.
- A paper whose number matches no account is refused with its own code and a message meant to
  be shown as sent, naming the number it read. A paper the engine can't read a number from is
  refused the same way. A number two accounts share is refused too, naming both.
- An upload that sends an account keeps working as today, so the change only adds.
- The contract says how the number is matched (the last 4 against the current and earlier
  cards), and the dry run and the apply answer the same way.

## Done when

- A dry run and an apply sent with no account, on a paper printing a card one account holds,
  answer with that account named, and the apply writes the statement to it.
- A paper printing an earlier card's number lands on the account that held that card.
- A paper whose number matches no account, or two, is refused with its code, nothing written.
- An upload that sends the account behaves as it does today.

## What this client removes once it lands

The "Which account is this statement?" question asked before every upload's preview: a dropped
PDF goes straight to the preview of the account the engine names, and a paper it can't name an
account for shows the engine's refusal.
