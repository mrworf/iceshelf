# iceshelf-restore

A helper tool for iceshelf, allowing a somewhat easier way of restoring backups created by it.

# Requirements

iceshelf-restore requires the **gpg** binary (GnuPG command-line tool) to be installed and on your PATH for signature verification and decryption. It does not use the python-gnupg library; all GPG operations are performed via the system `gpg` command. If gpg is not available, the tool will exit with an error at startup (help is still shown when you pass `--help`).

# Features

- Quick validation of backup
- Able to check for parent backup to avoid extacting in the wrong order (`--lastbackup`)
- Can show contents of backup (`--list`)
- Validate or restore a backup without needing the original config file
- Allows for restore even when some files are missing (`--force`)
- Initial validation of files using `filelist.txt` if available (will still confirm signatures)
- Can attempt parity repair using `--repair`
- Use a key from a file with `--key-file` (key is not written to your keyring)
- Multi-archive restore: when a folder contains multiple backups, list them or restore all in order with `--all`
- Conflict handling when a file already exists at the destination (`--conflict`)

# Usage

The tool accepts either a single file from the backup or just the prefix of the backup files. Configuration is optional, but can be provided using `--config` if you have it available. Without it you may supply the GPG user using `--user` and the passphrase using `--passphrase`. To use a key from a file instead of your keyring, use `--key-file`.
Running the command with no extra arguments will validate the backup and return `0` on success.

Note! If the archive is corrupt, it will only tell you if there is the possibility to repair it. It is *NO GUARANTEE* that you actually can.

## Using a key from a file

Use `--key-file PATH` to verify or decrypt using a key stored in a file (e.g. an exported public or secret key in `.asc` format) instead of your default GnuPG keyring. For full operation the key file should contain both the public key (for signature verification) and the private key (for decryption). The key is used only for this run: it is not written to your keyring. The program imports the key into a temporary directory, runs all GPG operations there, then securely wipes that directory before exit (files are overwritten then removed). Your key file is only read; it is not copied elsewhere. If you interrupt the run (e.g. Ctrl+C), the same cleanup runs so no key material is left on disk. Use `--skip-signature` to skip signature verification when signatures cannot be validated or are missing (e.g. key file has no public key, or backup was created without signing).

## Listing the contents

Adding `--list` will print the contents of the backup as specified by the manifest, including the parent backup (if available). `--list` only works when a single backup is selected (e.g. by specifying a backup prefix or file); if you point at a directory that contains multiple backups, the tool lists the backup names and exits without showing manifest contents.

## Validating the backup

`--validate` performs a full validation of the backup without extracting any files. Combine with `--repair` to fix corrupted archives if parity files are available.

## Restoring the backup

Add `--restore` with a folder where you want the backup restored. The tool will automatically locate the necessary files based on the provided prefix or file path. Extra verification is performed to ensure the archive matches the manifest. If a file is present in the archive but not in the manifest, it will error out. This is by design to avoid causing unexpected issues after restoring.

**Multiple backups in a folder:** If the path points to a directory that contains more than one backup (different basenames with both `.json` and `.tar`), the tool lists all available backups and exits without restoring. When listing, it also reports any gaps in the chain (backups referenced as parent by a manifest but not present in the folder). To restore from all of them in chronological order (merged state: final paths, deletes and renames applied), use `--all` together with `--restore`. A warning is emitted if the backup chain has gaps (e.g. a manifest references a previous backup that is not in the folder).

**Conflict handling (`--conflict`):** Before writing any file, the tool checks if the destination path already exists. Default is to skip existing files (`skipall`). You can set `--conflict replace` to always overwrite, `--conflict skipsame` to skip only when the existing file has the same contents (by checksum) and abort when it differs, or `--conflict abort` to abort the restore on the first existing path.

Note! Once the restore process has started, a failure to remove or rename/move an existing file will only cause a warning, restore will still continue.

## Corrupt backup

If one or more files are missing (such as the manifest), you can still make `iceshelf-restore` try to process it by specifying `--force`.

If the archive is corrupt but parity files are available you can try fixing it using `--repair`.

Note! It will *NOT* extract any file, it will simply verify as many files as possible as well as repair and decrypt if possible.

## What does `--debug` do?

It will give you some extra information while running, which normally isn't needed but can be helpful in understanding what's going wrong if `iceshelf-restore` isn't behaving as expected.

## What does `--verbose` do?

In restore mode, without `--verbose` the tool updates a single progress line (e.g. `Extracted 42 files of 100 (42% complete)`) so the screen is not filled with one line per file. With `--verbose`, each extracted or skipped file is logged. `--verbose` can be used in any mode.
