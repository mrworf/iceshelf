# SFTP Provider

Uploads backup files over SFTP using `paramiko`. Supports resumable uploads,
automatic retries, and post-upload hash verification.

## Arguments

- `host` – **(required)** remote hostname or IP.
- `port` – SSH port (default `22`).
- `user` – user to connect as (default: current OS user).
- `key` – path to an SSH private key file.
- `password` – used for password auth, or as the passphrase to decrypt an
  encrypted key file.
- `path` – remote directory where files are uploaded (default `.`).
- `retries` – number of times to retry a failed upload (default `3`).
- `resume` – `yes`/`no` — resume partial uploads instead of restarting
  (default `yes`). Before resuming, the existing partial file is hash-checked
  against the local source; if corrupt the remote file is deleted and the
  upload restarts from scratch.
- `verify` – `yes`/`no` — after each upload, run `sha256sum` on the remote
  via SSH to verify integrity (default `yes`). Falls back to a size-only check
  with a warning if `sha256sum` is not available on the remote host.

## Authentication

Authentication is strictly non-interactive. If the server requires a password
or the key file is passphrase-protected and neither a password nor an ssh-agent
is available, the provider will fail immediately with a clear error rather than
hanging on a prompt.

Supported methods (tried in order by paramiko):
1. Explicit key file (`key`), optionally decrypted with `password`.
2. SSH agent keys.
3. Password auth (`password`).

## Pros

- Pure Python — no external `sftp` or `sshpass` binaries needed.
- Resumable uploads with integrity verification.
- Configurable retries with automatic reconnect.

## Cons

- Requires `paramiko` (`pip install paramiko`).
- Remote hash verification requires `sha256sum` (and `head` for partial
  checks) on the remote host; falls back to size-only if unavailable.
