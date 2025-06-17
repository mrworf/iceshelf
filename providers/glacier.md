# Glacier Provider

Stores backups in Amazon Glacier using the `aws` CLI.

## Arguments
- `vault` – name of the Glacier vault.
- `threads` – optional number of upload threads.

## Pros
- Data is stored immutably which offers strong protection against ransomware.
- Very low storage cost for large archives.

## Cons
- Retrieval can take many hours and incurs additional cost.
- Requires AWS CLI and configured credentials.
