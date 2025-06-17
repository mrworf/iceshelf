# SCP Provider

Transfers files using the `scp` command.

## Arguments
- `user` – user to connect as.
- `host` – remote host.
- `dest` – remote directory for the uploaded files.
- `key` – optional SSH private key for authentication.
- `password` – optional password or passphrase (requires `sshpass`).

## Pros
- Easy to use and available on most systems.

## Cons
- Requires SSH credentials.
- Does not resume interrupted uploads.
