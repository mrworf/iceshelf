# iceshelf [![Build Status](https://github.com/mrworf/iceshelf/actions/workflows/python-app.yml/badge.svg)](https://github.com/mrworf/iceshelf/actions/workflows/python-app.yml) [![Docker Image](https://github.com/mrworf/iceshelf/actions/workflows/docker.yml/badge.svg)](https://github.com/mrworf/iceshelf/actions/workflows/docker.yml)

This tool allow you to backup data, it's intended to be used with services that store such data in an immutable state. This means, for backing up data which is changing on a daily basis, this isn't the tool since it would generate a lot of data.

The design goal for this backup was to leverage known tools and standards, allowing recovery of data, even if you don't have access to iceshelf, a viable option.

To that end, this tool uses
- par2
- tar
- bzip2-compatible compressors (`lbzip2`, `pbzip2`, or `bzip2`)
- gpg
- json

All of these will allow you restore backups even if you don't have this tool anymore.

If used with immutable storage, then it also provides protection against ransomware.

# Features

- Encrypts all backups using GPG private/public key
- Signs all files it uploads (tamper detection)
- Streams archive creation through tar, optional compression, optional encryption, and optional signing to avoid extra full-size temporary copies
- Can upload separate PAR2 file for parity correction (allows for a certain amount of bitrot)
- Supports segmentation of upload (but not of files, yet)
- Pluggable provider system supporting legacy Glacier vaults, S3, SFTP, SCP and local copy
  with the ability to upload to multiple destinations in one run
- Tracks backups locally to help locate the file needed to restore
- Keeps the exact directory structure of the backed up files
- Provides paper-based GPG key backup/restore solution
- Most features can be turned on/off and customized

## What's in this repo

- `iceshelf` - the main backup tool
- `iceshelf-restore` - validate and restore backups
- `iceshelf-retrieve` - retrieve archives from Glacier
- [PROVIDERS.md](PROVIDERS.md) - canonical provider reference
- [DOCKER.md](DOCKER.md) - running iceshelf in Docker
- `extras/analog-key.sh` - make a paper backup of a GPG key
- `extras/testsuite/` - end-to-end backup/restore tests

## Backup providers

Define one or more `provider` sections in the configuration file. Each section
specifies a `type` and any provider-specific arguments. All configured
providers will receive the generated archive for storage. The legacy `[glacier]`
section has been removed; using it will now cause the tool to abort so that you
review the new provider documentation.

Provider sections must be named using the pattern `[provider-<name>]` where the
portion after `provider-` is arbitrary. The name only helps you identify the
section. A minimal configuration might look like:

```
[provider-local]
type: cp
dest: backup/done/

[provider-cloud]
type: s3
bucket: mybucket
```

Refer to [PROVIDERS.md](PROVIDERS.md) for the canonical provider reference.

For new AWS setups, prefer the `s3` provider and set an Amazon S3 storage class
such as `GLACIER`, `GLACIER_IR`, or `DEEP_ARCHIVE`. AWS documents S3 storage
class uploads here:
https://docs.aws.amazon.com/AmazonS3/latest/userguide/sc-howtoset.html

If you currently use the older Amazon Glacier vault service, the `glacier`
provider remains available as a legacy compatibility path. AWS's migration
guidance for moving Glacier vault archives into S3 storage classes is here:
https://docs.aws.amazon.com/solutions/latest/data-transfer-from-amazon-s3-glacier-vaults-to-amazon-s3/overview.html

#### Migrating from older versions

Older configurations used a dedicated `[glacier]` section. This section has been
removed. Replace it with a provider block:

```
[provider-glacier]
type: glacier
vault: myvault
threads: 4
```

Remove the old `[glacier]` section to avoid startup errors.

Due to the need to work well with immutable storage (for example, Amazon S3
archival storage classes or the legacy AWS Glacier service), any change to a
file will cause it to reupload the same file with the new content. For this
reason, this tool isn't recommended to use with data sources which change
frequently as it will produce a tremendous amount of data over time.

This is an archiving solution for long-term storage which is what cold storage
on AWS has traditionally excelled at. Also the reason it's called iceshelf. To
quote from wikipedia:

> An ice shelf is a thick floating platform of ice that forms where a glacier or ice sheet flows down to a coastline and onto the ocean surface

*and yes, this would probably mean that time runs in reverse, but bear with
me, finding cool names (phun intended) for projects is not always easy*

# How does it all work?

1. Loads backup database if available
2. Empties prep directory of any files
3. Streams the archive through `tar` (recreating directory structure) until no more files are found or the limit is hit. If this wasn't the first run, only new or changed files are added
4. Depending on options, the tar stream is compressed with a bzip2-compatible compressor (`lbzip2`, `pbzip2`, then `bzip2`)
5. The archive stream is encrypted with a public key of your choice
6. The archive stream is signed with a public key of your choice (not necessarily the same as in #5)
7. A manifest of all files in the archive + checksums is stored as a JSON file
8. The manifest is signed (using ASCII instead of binary to keep it readable)
9. Parity file(s) are created to allow the archive to be restored should bitrot happen
10. Filelist with checksums is created
11. All extra files (filelist, parity, etc) files are signed
12. Resulting files are uploaded using the configured providers (remote uploads may take a while)
13. Backup is copied to safe keeping (if done directory is specified)
14. Prep directory is emptied
15. New backup is added to local database
16. Local database is saved as JSON

A lot of things here can be customized, but in a nutshell, this is what the tool does with all the bells and whistles enabled.

All filenames generated by the tool are based on date and time (YYYYMMDD-HHMMSS-xxxxx, time is in UTC), which helps you figure out where data might hide if you need to find it and have lost the original local database. Also allows you to restore files in the *correct* order (since the tool may have more than one copy of the same file, see `--modified`).

If you have the local database, you find that each file also points out which archive it belongs to. When a file is modified, it adds a new memberof entry. By sorting the backups field you can easily find the latest backup. Same applies to the an individual file, by sorting the memberof field you can find the latest version (or an old one).

# Disclaimer

I use this backup tool myself to safely keep a backup of my family's private email (I run the server so it seemed prudent). It's also used for all our photos and homevideos, not to mention all scanned documents (see LagerDox, another pet project on github).

**BUT!**<br>
If you loose any content as a result of using this tool (directly or indirectly) you cannot hold me responsible for your loss or damage.

There, I said it. Enough with disclaimers now :-)

## Docker

iceshelf is available as a Docker image on the GitHub Container Registry. The
container automatically discovers backup targets, merges configuration, and runs
on a configurable schedule with built-in health checking. The image ships the
runtime tools needed for compression, GPG, parity, and SSH-based providers, and
intentionally prefers `lbzip2` for compression.

```bash
docker pull ghcr.io/mrworf/iceshelf:latest
```

See [docker.md](DOCKER.md) for full documentation on running iceshelf in Docker.

## Requirements

In order to be able to run this, you need a few other parts installed.

- tar - required for backup creation
- A bzip2-compatible compressor (`lbzip2`, `pbzip2`, or `bzip2`) - required when compression is enabled; iceshelf prefers them in that order
- OpenPGP / GNU Privacy Guard (the `gpg` command-line tool) - for encryption and signatures
- par2 - Parity tool (optional, only needed for parity support)
- Python packages: `boto3`, `PyYAML` (install with `pip3 install -r requirements.txt`)

### Installing on Ubuntu

1. Archiving and encryption tools
  ```
  sudo apt-get install tar bzip2 gnupg
  ```

2. Python dependencies
  ```
  sudo apt-get install python3-dev python3-pip
  pip3 install -r requirements.txt
  ```

3. PAR2 for parity (optional)
  ```
  sudo apt-get install par2
  ```

For more details, see the [step-by-step guide](https://github.com/mrworf/iceshelf/wiki) in the wiki.

## Configuration file

Iceshelf requires a config file to work. You may name it whatever you want and it may exist wherever you want. The important part is that you point it out to the tool.

Here's what it all does...

### Section [sources]

Contains all the directories you wish to backup. Can also be individual files. You define each source by name=path/file, for example:

```
my home movies=/mnt/storage/homemovies
my little file=/mnt/documents/birthcertificate.pdf
```

*default is... no defined source*

### Section [paths]

Iceshelf needs some space for both temporary files and the local database.

#### prep dir

The folder to hold the temporary files and final artifacts before upload. Archive creation is streamed, so iceshelf no longer needs separate full-size tar/compress/encrypt/sign intermediates there, but uploads to remote storage may still take quite a while. A ram-backed storage (such as tmpfs) is still a **VERY BAD IDEA** for real backups.

*default is `backup/inprogress/`*

#### data dir

Where to store local data needed by iceshelf to function. Today that's a checksum database, tomorrow, who knows? Might be good to back up (yes, you can do that).

*default is `backup/metadata/`*

#### done dir

Where to store the backup once it's been completed. If this is blank, no backup is stored. Also see `max keep` under `[options]` for additional configuration. By setting this option and not defining any provider sections, you can use iceshelf purely for local backups.

Please note that it copies the data to the new location and only on success will it delete the original archive files.

*default is `backup/done/`*

#### create paths

By default, iceshelf does not create the done, data or preparation directories, it leaves this responsibility to the user. However, by setting this option to yes, it will create the needed structure as described in the configuration file.

*default is `no`*

### Section [options]

There are quite a few options for you to play with. Unless otherwise specified, the options are toggled using `yes` or `no`.

#### check update

Will try to detect if there is a new version of iceshelf available and if so, print out the changes. It's done as the first operation before starting the backup. It requires you run iceshelf from its git repository and that `git` is available. If there is no new version or it's not run from the git repository, then it fails silently.

*default is no, don't check for updates*

#### max size

Defines the maximum amount of source data that may be packed into one backup slice. Iceshelf counts the sizes of the files selected for the current slice, so this also becomes the largest single file that can fit in that slice. Depending on compression, encryption, signatures, and parity, the generated backup artifacts may still exceed this size on disk.

This option is defined in bytes, but can also be suffixed with K, M, G or T to indicate the unit. We're using true powers of 2 here, so 1K = 1024.

A value of zero or simply blank (or left out) will make it unlimited (unless `add parity` is in-effect)

With the default `loop slices = yes`, iceshelf will keep creating, uploading, and committing slices in the same run until everything that fits has been backed up.

If you disable `loop slices`, then a run stops after the first full slice. In that mode, if more files remain, iceshelf exits with code 10 and a rerun continues from the last committed slice.

This behavior is what allows you to segment uploads into a specific per-slice size.

*default is blank, no limit*

#### loop slices

Controls whether iceshelf should continue creating additional slices in the same invocation when `max size` is reached.

If `yes`, iceshelf will upload the current slice, save the local database, clear temporary files, and continue with the remaining files automatically.

If `no`, iceshelf keeps the older one-slice-per-run behavior. When more files remain that would fit in another slice, it exits with code 10 so you can rerun it later.

This option only matters when `max size` is greater than zero.

*default is `yes`*

#### change method

How to detect changes. You have a few different modes, the most common is `data`, but also `sha1` (same as data actually), `sha256` and `sha512` works. Iceshelf uses hashes of the data which is then compared to see changes. While sha1 usually is good enough, you can also specify `sha256` or `sha512` if you feel it is warranted.

Note that switching between various methods will not upgrade all checksum on the next run, only files which have changes will get the new checksum to avoid unnecessary changes.

*default is `data`*

#### delta manifest

Save a delta manifest with the archive as separate file. This is essentially a JSON file with the filenames and their checksums. Handy if you ever loose the entire local database since you can download all your manifests in order to locate the missing file.

Please keep in-mind that this is a *delta* manifest, it does not contain anything but the files in this backup, there are no references to any other files from previous backups.

*default is `yes`*

#### compress

Controlling compression, this option can be `yes`, `no`, `force`. While `no` is obvious (never compress), `yes` is somewhat more clever. It will calculate how many of the files included in the backup are considered compressible (see `incompressible` as well) and engage compression if 20% or more is considered compressible.

Now, `force` is probably more obvious, but we cover it anyway for completeness. It essentially overrides the logic of `yes` and compresses regardless of the content.

*default is `yes`*

#### persuasive

While a fun name for an option, it essentially says that even if the next file won't fit within the max size limits, it should continue and see if any other file fits. This is to try and make sure that all archives are of equal size. If no, it will abort the moment a it gets to a file which won't fit the envelope.

*default is `yes`*

#### ignore overlimit

If `yes`, this will make iceshelf return a success code once all files are backed up, even if it has skipped files that are larger than the max size. So if you have 10 files and one is larger than max size, then 9 files will be backed up and it will still return OK (exit code 0), without this option, it would have failed and had a non-zero exit code.

*default is `no`*

#### incompressible

Using this option, you can add additional file extensions which will be considered incompressible by the built-in logic.

*default is blank, relying only on the built-in list*

#### max keep

Defines how many backups to keep in the `done dir` folder. If it's zero or blank, there's no limit. Anything else defines the number of backups to keep. It's based on FIFO, oldest backup gets deleted first. This option is pointless without defining a `done dir`.

*default is zero, unlimited storage*

#### prefix

Optional setting, allows you to add the selected prefix to all files produced by the tool. If not set, then no prefix is added.

*default is no prefix*

#### detect move

This is an *experimental* feature which tries to detect when you've just moved a file or renamed it. It will only log the change to the JSON manifest and will not upload the file, since it's the same file.

It's a very new feature and should be used with caution. It will track what backup the original file was in and what the name was, so it should be able to provide details for restore of moved files, but it's not 100% tested.

*default is `no`*

#### skip broken links

If `yes`, iceshelf will log a warning and skip symbolic links whose targets do not exist at scan time.

This applies only to broken symlinks. Other file access problems still fail the run. Valid symbolic links are still followed and backed up as usual.

*default is `no`*

#### ignore unavailable files

If `yes`, iceshelf will log a warning and skip files that were discovered during
scan but become unavailable while `tar` is building the archive. This is meant
for cases where files are moved or disappear between scan and archive creation.

This applies only to archive-time `tar` read/open/stat failures. Scan-time
inspection and hashing errors still fail the run. Skipped files are removed from
the manifest and local backup database so restore metadata stays consistent with
what actually made it into the archive.

*default is `no`*

#### tolerate unreconcilable files

If `yes` (and `ignore unavailable files` is also `yes`), iceshelf will keep
going even when `tar` reports an unavailable file whose path cannot be matched
back to the scan state. A best-effort reconciliation is attempted first; any
remaining entries are logged as warnings and the archive is still written and
uploaded.

This is useful for live data sets where files shift around during the backup
window (e.g. mail servers, queues, spool directories). For such a path:

- If it was part of a previous backup, the local state is left untouched so
  restore metadata keeps pointing at the last good archive — it is treated as
  if the file never changed in this run.
- If it was new to this run, it is simply not recorded, as if it had not been
  scanned.

A follow-up backup run will rescan and either record the current state of the
file correctly or observe that it has been deleted/moved. It is recommended to
run the backup again until no such warnings appear.

This option has no effect unless `ignore unavailable files` is also enabled.

*default is `no`*

#### show delta

If `yes`, iceshelf prints the detected changes for the current run after scan
and change detection but before archive creation starts, then continues with the
backup normally.

Each line is printed as `action size path`, or `action size oldpath -> newpath`
for rename and move detection. Deleted entries intentionally leave the size
blank because the local database does not store historical file sizes.

Possible actions are `new`, `changed`, `deleted`, `renamed`, `moved`, and
`renamed+moved`.

*default is `no`*

#### upload activity log

If `yes`, iceshelf snapshots the run log from process start through the point
just before providers begin uploading the prepared files. That snapshot is
stored as an additional backup sidecar named like
`<backup>.activity.log.bz2`.

If `encrypt` is enabled, the activity log sidecar is encrypted. If `sign` is
enabled, it is also signed. This follows the main backup security settings and
does not depend on `encrypt manifest`.

When `--debug` is enabled, the uploaded log artifact contains the same verbose
debug output as the rest of the run log. If you do not encrypt backups, keep
in mind that this may expose sensitive configuration values in remote storage.

*default is `no`*

#### create filelist

Adds an additional file, called `filelist.txt` which is a shasum compatible file which details the hash of each file in the backup (the produced backup files, not the backed up files) as well as their corresponding sha1 which can be checked with shasum, like so `shasum -c filelist.txt`. This is to tell you what files belong to the backup. It's used by iceshelf-restore. File will also be signed if signature is enabled (see security).

*default is `yes`*

### Section [exclude]

This is an optional section, by default iceshelf will backup every file it finds in the source. But sometimes that's not always appreciated. This section allows you to define some exclusion rules.

You define rules the same way you do sources, by name=rule, for example:

```
no zip files=*.zip
no cache tree=/home/user/cache/*
...
```

Rules are matched against the full path of each file. In the simplest form, a rule is an exact path match. Matching is case-sensitive by default.

#### Prefixes

You can however make it more expressive with wildcards and modifiers:

- `foo*` matches any path starting with `foo`
- `*foo` matches any path ending with `foo`
- `?foo` matches any path containing `foo`
- `*foo*` also matches any path containing `foo`
- `&lt;123` or `&gt;123` excludes by size only

You can also add modifiers before the pattern. Prefix order is flexible, so `^?/MyFolder/` and `?^/MyFolder/` mean the same thing.

- `!` inverts the rule and makes it inclusive instead
- `^` makes the match CaSe-InSeNsItIvE

Finally, use `\` to escape special characters when you need them literally. This includes `!`, `^`, `?`, `*`, `&lt;`, `&gt;`, and `\` itself.

But wait, there's more. You can on top of these prefixes add an additional prefix (a pre-prefix) in the shape of an exclamationmark. This will *invert* the rule and make it inclusive instead.

Why would you want to do this?

Consider the following:
```
[exclude]
alldocs=!*.doc
no odd dirs=/some/odd/dir/*
```

In a structure like this:

```
/some/
/some/data.txt
/some/todo.doc
/some/odd/dir/
/some/odd/dir/moredata.txt
/some/odd/dir/readme.doc
```

It will backup the following:

```
/some/data.txt
/some/todo.doc
/some/odd/dir/readme.doc
```

Notice how it snagged a file from inside an excluded folder? Pretty convenient. However, in order for this to work, you must consider the order of the rules. If you change the order to:

```
[exclude]
no odd dirs=/some/odd/dir/*
alldocs=!*.doc
```

The `no odd dirs` would trigger first and the second rule would never get a chance to be evaluated. If you're having issues with the rules, consider running iceshelf with `--changes` and `--debug` to see what it's doing.

Finally, you can also reference external files containing exclusion rules. This makes it easy to use readymade rules for various items you'd like to backup. Including a external rule file is done by prefixing the filename with a pipe ```|``` character. For example, to include "my-rules.excl", you'd write the following:

```
[exclude]
my rules=|/some/path/my-rules.excl
```

What essentially happens is that the "my rules" line is replaced with all the rules defined inside my-rules.excl. The only restriction of the external rules reference is that you are not able to reference other external rule files from an external rule file (yes, no recursion for you).

### Section [provider-*]

Providers control where your backups are stored. Create one or more sections with
names beginning with `provider-`. Each section must define a `type` matching one
of the built‑in providers (cp, sftp, scp, s3 or glacier) and any additional
options documented in [PROVIDERS.md](PROVIDERS.md).

Example:

```
[provider-local]
type: cp
dest: /mnt/backup/
create: yes
```

All provider sections are processed in order and the backup files will be
uploaded to each destination.

### Section [security]

From here you can control everything which relates to security of the content and the parity controls. Make sure you have GPG installed or this will not function properly.

#### encrypt

Specifies the GPG key to use for encryption. Usually an email address. This option can be used independently from sign and can also use a different key.

Only the archive file is encrypted.

*default is blank*

#### encrypt phrase

If your encryption key needs a passphrase, this is the place you put it.

*default is blank*

#### sign

Specifies the GPG key to use for signing files. Usually an email address. This option can be used independently from encrypt and can also use a different key.

Using signature will sign *every* file associated with the archive, including the archive itself. It gives you the benefit of being able to validate the data as well as detecting if the archive has been damaged/tampered with.

See `add parity` for dealing with damaged archive files.

*default is blank*

#### sign phrase

If your signature key needs a passphrase, this is the place you put it.

*default is blank*

#### key file

Path to a GPG key file containing the OpenPGP material needed for encryption
and/or signing. The file may be ASCII-armored or a binary export. When set,
iceshelf creates an isolated temporary keyring so your existing keyring is
never touched.

For `encrypt`, the key file must contain the recipient public key. For `sign`,
it must contain the signing secret key. If you use both options, include both
the required public and secret key material. If encryption and signing use
different identities, the file must contain the keys needed for both.

This can also be overridden from the command line with `--key-file`.

If you rely on a key file, make an offline copy of it or of the secret key it
contains. [`extras/analog-key.sh`](extras/analog-key.sh)
can turn a GPG secret key into printable QR pages so you still have a recovery
path when disks or other media fail.

*default is blank (use the system keyring)*

#### encrypt manifest

If you're worried that the use of a manifest file (which describes the changes contained in the backup, see `delta manifest` under `options`), specifying this option will encrypt the manifest as well (using the same key as `encrypt` above). If you haven't enabled `delta manifest`, this option has no effect.

*default is `yes`*

#### add parity

Adds a PAR2 parity file, allowing you to recover from errors in the archive, should that have happened. These files will never be encrypted, only signed if you've enabled signature. The value for this option is the percentage of errors in the archive that you wish to be able to deal with.

The value ranges from 0 (off) to 100 (the whole file).

Remember, if you ask for 50%, the resulting archive files *will* be roughly 50% larger.

For security people, this option is acting upon the already encrypted and signed version of the archive, so even at 100%, there won't be any data which can be used to get around the encryption.

There is unfortunately also a caveat with using parity. Due to a limitation of the PAR2 specification, `max size` will automatically be set to 32GB, regardless if you have set it to unlimited or >32GB.

*default is zero, no parity, to avoid the 32GB limit*

## Commandline

You can also provide a few options via the commandline, these are not available in the configuration file.

`--changes` will show you what *would* be backed up, if you were to do it

`--logfile` also writes the run log to a file while keeping normal console output. It uses the same log format as the active run mode and captures startup and configuration errors as well. It does not automatically enable `--debug`.

`--find <string>` will show any file and backup which contains the `<string>`

`--modified` shows files which have changed and the number of times, helpful when you want to find what you need to exclude from your backup (such as index files, cache, etc)

`--show <archive>` lists all files components which makes up a particular backup. This is refering to the archive file, manifest, etc. Not the contents of the actual backup. Helpful when you need to retreive a backup and you want to know all the files.

`--full` forces a complete backup, foregoing the incremential logic.

`--key-file <file>` use GPG keys from the given file instead of the default keyring. The file may be ASCII-armored or a binary OpenPGP export. Include the recipient public key for encryption, the signing secret key for signing, and both if you use both operations or separate identities. When set, an isolated temporary keyring is created for all GPG operations so your existing keyring is never modified. This overrides the `key file` option in the config's `[security]` section.

`--list files` shows the current state of your backup, as iceshelf knows it

`--list members` shows the files that are a part of your backup and where to find the latest copy of that file

`--list sets` shows the backups you need to retrieve to restore a complete backup (please unpack in old->new order)

No matter what options you add, you *must* point out the configuration file, or you will not get any results.

## Return codes

Depending on what happened during the run, iceshelf will return the following exit codes:

0 = All good, operation finished successfully

1 = Configuration issue

2 = Unable to gather all data, meaning that while creating the archive to upload, some kind of I/O related error happened. The log should give you an idea of what. Can happen when files disappear during archive creation unless `ignore unavailable files` is enabled. When `tar` reports unavailable paths that cannot be matched back to the scan state, the run also exits with 2 unless `tolerate unreconcilable files` is enabled

3 = Remaining files are larger than the effective `max size`, so they can never fit in a slice

10 = Backup was successful, but there are more files to back up. This happens when `max size` is enabled, `loop slices` is disabled, and more files remain for a later slice

255 = Generic error, see log output

# Retrieving backups

To download archives stored in the legacy Amazon Glacier vault service use the [iceshelf-retrieve](README.iceshelf-retrieve.md) helper. It manages Glacier jobs and verifies files automatically. You can fetch one or more backups, or use `--all` to restore everything directly from the vault inventory.

# FAQ

## I keep getting "Signature not yet current" errors when uploading

This is caused by your system clock being off by more than 5 minutes. It's highly recommended that you run a time synchronization daemon such as NTPd on the machine which is responsible for uploading the backup to AWS.

## I get "Filename '&lt;some file&gt;' is corrupt, please rename it. Will be skipped for now" warnings

This happens, in particular on Unix filesystems where you might, at one point, have stored filename information encoded in a non-UTF8 format (such as Latin1, or similar). When you then upgraded to UTF8, these files remained. Usually doing a `ls -la <some file's folder>` it will show up but with a questionmark where the character should be. This is because it's not compatible with UTF8.

To fix it, simply rename the file and it will work as expected.

## What about the local database?

Yes, it's vulnerable to tampering, bitrot and loss. But instead of constructing something to solve that locally, I would recommend you simply add an entry to the [sources] section of the config:

```
iceshelf-db=/where/i/store/the/checksum.json
```

And presto, each copy of the archive will have the previous database included. Which is fine because normally the `delta manifest` option is enabled which means that you got it all covered.

If this turns out to be a major concern/issue, I'll revisit this question.

## How am I supposed to restore a full backup?

Using the `--list sets` option, iceshelf will list the necessary backups you need to restore and in the order to do it. If a file was moved, the tool will display what the original name was and what the new name is supposed to be.

There is also a tool called [iceshelf-restore](README.iceshelf-restore.md) which you can use to more easily extract a backup. The tool can validate or restore a backup directly from the files and will attempt repairs if parity data is available. 

`iceshelf-restore --analyze <backup-or-folder>` can also inspect manifests only and report churn-heavy file lifecycles plus folders with transient traffic. This analysis is action-only because manifests do not contain file sizes. Use `--analyze-activity <count-or-percent>` to control the minimum activity threshold.

## After doing some development on the code, how will I know something didn't break?

Please use the testsuite and run a complete iteration with GPG and PAR2. Also
extend the suite if needed to cover any specific testcase which was previously
missed.

The tests rely on the `par2` and `gpg` tools being available in the PATH, so
make sure they are installed before running `bash extras/testsuite/test_backup.sh`
and `bash extras/testsuite/test_restore.sh`.
