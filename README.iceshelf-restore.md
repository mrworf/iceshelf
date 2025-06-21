# iceshelf-restore

A helper tool for iceshelf, allowing a somewhat easier way of restoring backups created by it.

# Features

- Quick validation of backup
- Able to check for parent backup to avoid extacting in the wrong order (`--lastbackup`)
- Can show contents of backup (`--list`)
- Validate or restore a backup without needing the original config file
- Allows for restore even when some files are missing (`--force`)
- Initial validation of files using `filelist.txt` if available (will still confirm signatures)
- Can attempt parity repair using `--repair`

# Known issues

Backup must be alone in a directory, you cannot store multiple backups in a folder since it simply picks the first manifest. This is on the todo list to fix

# Usage

The tool accepts either a single file from the backup or just the prefix of the backup files. Configuration is optional, but can be provided using `--config` if you have it available. Without it you may supply the passphrase using `--passphrase`.
Running the command with no extra arguments will validate the backup and return `0` on success.

Note! If the archive is corrupt, it will only tell you if there is the possibility to repair it. It is *NO GUARANTEE* that you actually can.

## Listing the contents

Adding `--list` will print the contents of the backup as specified by the manifest, including the parent backup (if available).

## Validating the backup

`--validate` performs a full validation of the backup without extracting any files. Combine with `--repair` to fix corrupted archives if parity files are available.

## Restoring the backup

Add `--restore` with a folder where you want the backup restored. The tool will automatically locate the necessary files based on the provided prefix or file path. Extra verification is performed to ensure the archive matches the manifest. If a file is present in the archive but not in the manifest, it will error out. This is by design to avoid causing unexpected issues after restoring.

Note! Once the restore process has started, a failure to remove or rename/move an existing file will only cause a warning, restore will still continue.

## Corrupt backup

If one or more files are missing (such as the manifest), you can still make `iceshelf-restore` try to process it by specifying `--force`.

If the archive is corrupt but parity files are available you can try fixing it using `--repair`.

Note! It will *NOT* extract any file, it will simply verify as many files as possible as well as repair and decrypt if possible.

## What does `--debug` do?

It will give you some extra information while running, which normally isn't needed but can be helpful in understanding what's going wrong if `iceshelf-restore` isn't behaving as expected.
