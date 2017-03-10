# iceshelf-restore

A helper tool for iceshelf, allowing a somewhat easier way of restoring backups created by it.

# Features

- Quick validation of backup
- Able to check for parent backup to avoid extacting in the wrong order (`--lastbackup`)
- Can show contents of backup (`--list`)
- Allows for restore even when some files are missing (`--force`)
- Initial validation of files using `filelist.txt` if available (will still confirm signatures)

# Known issues

Backup must be alone in a directory, you cannot store multiple backups in a folder since it simply picks the first manifest. This is on the todo list to fix

# Usage

In it's simplest form, you must provide the same configuration file as used by `iceshelf` and one of the files from the backup. This will simply validate your backup and if valid, the exit code will be `0` while if there is an issue, you'll be told what and it also returns a non-zero exit code.

Note! If the archive is corrupt, it will only tell you if there is the possibility to repair it. It is *NO GUARANTEE* that you actually can.

## Listing the contents

Adding `--list` will print the contents of the backup as specified by the manifest, including the parent backup (if available).

## Restoring the backup

Add `--restore` with a folder where you want the backup restored. This also adds additional verification, making sure that the archive contains all files listed in the manifest. If a file is present in the archive but not in the manifest, it will cause it to error out. This is by design to avoid causing unexpected issues after restoring.

Note! Once the restore process has started, a failure to remove or rename/move an existing file will only cause a warning, restore will still continue.

## Corrupt backup

If one or more files are missing (such as the manifest), you can still make `iceshelf-restore` try to process it by specifying `--force`.

Note! It will *NOT* extract any file, it will simply verify as many files as possible as well as repair and decrypt if possible.

## What does `--debug` do?

It will give you some extra information while running, which normally isn't needed but can be helpful in understanding what's going wrong if `iceshelf-restore` isn't behaving as expected.