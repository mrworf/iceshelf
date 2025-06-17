# iceshelf-retrieve

`iceshelf-retrieve` downloads archives stored in AWS Glacier by
[iceshelf](README.md). Retrieval from Glacier is asynchronous which means files
cannot be fetched immediately. This helper keeps track of pending retrieval jobs
and can be re-run until everything is downloaded and verified.

## Features

- Handles Glacier inventory requests automatically.
- Initiates archive retrieval jobs and resumes interrupted downloads.
- Multi-threaded downloads with configurable thread count.
- Verifies files using the Glacier SHA256 tree hash.
- Provides progress information and clear error reporting.

## Usage

```
iceshelf-retrieve VAULT BACKUP [BACKUP ...] [--database FILE] [--dest DIR] [--threads N]
iceshelf-retrieve VAULT --all [--database FILE] [--dest DIR] [--threads N]
```

- `VAULT` – name of the Glacier vault where archives are stored.
- `--database` – path to the `checksum.json` database. This file is optional when using `--all`.
- `BACKUP` – name of a backup set to retrieve (for example
  `20230101-123456-00000`). Multiple backups can be listed.
- `--dest` – directory where files are stored (defaults to `retrieved/`).
- `--threads` – number of concurrent downloads.
- `--all` – download every backup in the vault using only the Glacier inventory.

Running the tool the first time will start an inventory retrieval job if no
recent inventory exists. Once the inventory is available it will request
retrieval for each file in the selected backup. With `--all`, the inventory
is scanned to locate every backup in the vault and each one is downloaded in
turn. Re-run the tool periodically until all files report `Finished`.

## Example

```
./iceshelf-retrieve myvault 20230101-123456-00000 --dest restore --threads 4
```

Errors are printed with hints whenever possible. Ensure that your AWS
credentials are configured for the account that owns the Glacier vault.
