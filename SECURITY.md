# Security

VesperHood asks people to run a Python file that creates a keypair. That deserves
plainer language than most threat models get.

## What the kit does and does not do

- `init` writes a keypair to `~/.vesperhood/key.json`, mode 600. It is an identity
  for signing quotes. **Do not fund it.**
- Nothing in the kit signs a transaction, moves a balance, or reads any other
  wallet on the machine.
- No command phones home except `checkin`, which you run deliberately and which
  publishes your quoting address to a public endpoint. `doctor`, `session`,
  `pairs` and `demo` send nothing about your machine anywhere.
- `demo` needs no network at all.
- `run` refuses to operate while the settlement contract is unpublished.

## What the venue does and does not hold

The Book is not deployed. `/v1/contracts` verifies that by asking the chain for
code at the claimed addresses rather than asserting a status. No contract in
this project custodies funds, and no endpoint accepts capital.

## What the desk stores

`/v1/checkin` stores one record per agent address: the address and a version
string. Nothing else — no IP, no machine details. `/v1/agents` returns counts
only; the roster is never served. Records age out of the online count after
24 hours.

## Reporting

Open a private security advisory on this repository, or an issue if the finding
is not sensitive. Please include what you ran and what you observed.

Things worth reporting even if they seem minor:

- Any way to make the desk serve a token address that failed its on-chain check.
- Any path where the kit would sign or transmit something a command did not
  announce.
- Any way to make `/v1/contracts` report a venue as live when it is not.

That last one matters most: the kit's refusal to quote depends on it.

## Known and accepted

- The check-in rate limit is per serverless instance, not distributed. It stops
  accidental loops, not a determined flood across regions.
- The registry's discovery step reads a public block explorer over HTTPS. A
  compromised explorer could propose bad addresses — which is why every address
  is confirmed by direct `eth_call` before it is served, and why the builder
  drops anything that does not answer.
- The embedded market calendar is verified only through a stated date. Past it
  the kit warns rather than guessing.
