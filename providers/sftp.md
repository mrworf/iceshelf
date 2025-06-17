# SFTP Provider

Uploads backup files using the `sftp` command.

## Arguments
- `user` – user to connect as.
- `host` – remote host.
- `dest` – remote directory where files are uploaded.
- `key` – optional SSH private key.
- `password` – optional password or passphrase (requires `sshpass`).

## Pros
- Works over SSH and is widely supported.

## Cons
- Requires SSH access and credentials.
- Transfer speed may be limited by network latency.
