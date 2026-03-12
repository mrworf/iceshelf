# iceshelf-restore

Restores and validates backups created by iceshelf.

# Requirements

iceshelf-restore requires the **gpg** binary (GnuPG command-line tool) to be installed and on your PATH for signature verification and decryption. It does not use the python-gnupg library; all GPG operations are performed via the system `gpg` command. If gpg is not available, the tool will exit with an error at startup (help is still shown when you pass `--help`).

# Features

- Quick validation of backup
- Able to check for parent backup to avoid extracting in the wrong order (`--lastbackup`)
- Can show contents of backup (`--list`)
- Validate or restore a backup without needing the original config file
- Allows for restore even when some files are missing (`--force`)
- Initial validation of files using a filelist (`.lst`/`.lst.asc` or legacy `filelist.txt`) if available (will still confirm signatures)
- Can attempt parity repair using `--repair`
- Use a key from a file with `--key-file` (key is not written to your keyring)
- Multi-archive restore: when a folder contains multiple backups, list them or restore all in order with `--all`
- Conflict handling when a file already exists at the destination (`--conflict`; default: skip if same content, abort if different)
- Resumable restore: progress is recorded in `.restore/completed.lst`; re-run to skip already-extracted files (single- and multi-archive)
- Audit report written on every restore: `iceshelf-restore-report-YYYYMMDD-HHMMSS.txt` in the restore destination

# Usage

The tool accepts either a single file from the backup or just the prefix of the backup files. Configuration is optional, but can be provided using `--config` if you have it available. Without it you may supply the GPG user using `--user` and the passphrase using `--passphrase`. To use a key from a file instead of your keyring, use `--key-file`.
Running the command with no extra arguments will validate the backup and return `0` on success.

If the archive is corrupt, the tool only indicates whether repair may be possible; it does not guarantee that repair will succeed.

## Using a key from a file

Use `--key-file PATH` to verify or decrypt using a key stored in a file (e.g. an exported public or secret key in `.asc` format) instead of your default GnuPG keyring. For full operation the key file should contain both the public key (for signature verification) and the private key (for decryption). The key is used only for this run: it is not written to your keyring. The program imports the key into a temporary directory, runs all GPG operations there, then securely wipes that directory before exit (files are overwritten then removed). Your key file is only read; it is not copied elsewhere. If you interrupt the run (e.g. Ctrl+C), the same cleanup runs so no key material is left on disk. Use `--skip-signature` to skip signature verification when signatures cannot be validated or are missing (e.g. key file has no public key, or backup was created without signing).

## Listing the contents

Adding `--list` will print the contents of the backup as specified by the manifest, including the parent backup (if available). `--list` only works when a single backup is selected (e.g. by specifying a backup prefix or file); if you point at a directory that contains multiple backups, the tool lists the backup names and exits without showing manifest contents.

## Validating the backup

`--validate` performs a full validation of the backup without extracting any files. Combine with `--repair` to fix corrupted archives if parity files are available. If the backup folder contains less-wrapped versions of the chosen files (e.g. leftover `.json` from a prior run), the tool logs a warning and continues using the chosen file (e.g. `.json.gpg`).

## Restoring the backup

Add `--restore` with a folder where you want the backup restored. The tool will automatically locate the necessary files based on the provided prefix or file path. Extra verification is performed to ensure the archive matches the manifest. If a file is present in the archive but not in the manifest, it will error out. This is by design to avoid causing unexpected issues after restoring. For a single backup, manifest "moved" entries are not applied (only noted in the report); use `--all` with a directory of backups to restore a chain with renames applied.

**Multiple backups in a folder:** If the path points to a directory that contains more than one backup (different basenames with both `.json` and `.tar`), the tool lists all available backups and exits without restoring. When listing, it also reports any gaps in the chain (backups referenced as parent by a manifest but not present in the folder). To restore from all of them in chronological order (merged state: final paths, deletes and renames applied), use `--all` together with `--restore`. A warning is emitted if the backup chain has gaps (e.g. a manifest references a previous backup that is not in the folder).

**Conflict handling (`--conflict`):** Before writing any file, the tool checks if the destination path already exists. Default is `skipsame`: skip if the existing file has the same contents (by checksum), abort if it differs. Use `--conflict replace` to always overwrite, or `--conflict abort` to abort the restore on the first existing path.

**Audit report:** On every restore the tool writes an audit report to the restore destination: `iceshelf-restore-report-YYYYMMDD-HHMMSS.txt`. It lists restored files, skipped files, and deleted paths. Use `--show-extras` to add a section listing files in the restoration folder that were not part of the backup (helps spot leftovers or stray files). The extras list is written only to the report file, not to the command line.

**Resumable restore:** Both single- and multi-archive restore record progress in `.restore/completed.lst`. If you re-run the same restore (e.g. after an interrupt), already-extracted files (matching size) are skipped. For a single backup the archive may be decrypted again, but only missing files are restored.

**Restore temp directory (`--restore-temp-dir`):** Temporary decrypted archives and `completed.lst` are stored under a directory that defaults to `.restore` under the restore destination. Use `--restore-temp-dir DIR` to override (absolute path, or relative to the restore destination). Applies to both single- and multi-archive restore.

Once the restore process has started, a failure to remove or rename an existing file will only cause a warning; the restore continues.

## Corrupt backup

If one or more files are missing (such as the manifest), you can still make `iceshelf-restore` try to process it by specifying `--force`.

If the archive is corrupt but parity files are available you can try fixing it using `--repair`.

With `--repair` and no manifest, the tool does not extract files; it verifies as many files as possible and repairs/decrypts if possible.

## What does `--debug` do?

It will give you some extra information while running, which normally isn't needed but can be helpful in understanding what's going wrong if `iceshelf-restore` isn't behaving as expected.

## What does `--verbose` do?

In restore mode, without `--verbose` the tool updates a single progress line (e.g. `Extracted 42 files of 100 (42% complete)`) so the screen is not filled with one line per file. With `--verbose`, each extracted or skipped file is logged. `--verbose` can be used in any mode.

## Logging

Use `--logfile FILE` to write log output to a file instead of stdout.

## Known issues and limitations

- **No partial restore:** Restore is all-or-nothing per backup (or full chain with `--all`); there is no option to restore only selected paths or globs.
- **No path remapping:** Restore destination is a single root; backup paths cannot be mapped to different locations.
- **Moved files in single-backup mode:** With a single backup, entries in the manifest’s "moved" section are only reported in the audit report, not applied; use `--all` with a directory of backups to apply renames.
- **When repair is not possible:** The tool’s `--repair` option works when PAR2 parity files exist and are sufficient. If the archive is corrupt and PAR2 files are missing, or PAR2 repair fails, the tool can only report the problem; there is no other recovery path.
- **Disk full / very large restores:** Both single- and multi-archive restore are resumable via `completed.lst`; on rerun, already-extracted files are skipped. Single-archive may decrypt the archive again but only missing files are restored. There is no special handling for out-of-disk (restore may fail partway; re-run to resume).
- **Concurrent restores:** Restoring to the same destination from two processes could conflict on `completed.lst` and the temp dir; not supported.
- **Key file with only public key:** For full operation (decrypt and verify) the key file should contain both public and secret key; public-only allows verification only. Use `--skip-signature` when signatures cannot be validated or are missing (e.g. backup created without signing).
