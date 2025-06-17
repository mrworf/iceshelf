# Copy Provider

Copies backup files to a local destination using the `cp` command. Useful when
keeping archives on the same system or on a mounted network share.

## Arguments
- `dest` – path to the target directory where files will be placed.
- `create` – set to `yes` to create `dest` if it does not exist.

## Pros
- Simple and uses basic tools available on any system.
- No network transfer required.

## Cons
- Provides no remote storage or redundancy.
