# Provider Reference

This document is the canonical reference for all built-in backup providers in
iceshelf.

Provider sections must be named using the pattern `[provider-<name>]`, where
the part after `provider-` is only a label for your own reference. The section
name does not affect behavior. The required `type` option selects the provider
implementation.

You may define multiple provider sections in one config file. Every configured
provider receives the generated backup files.

Example:

```ini
[provider-local]
type: cp
dest: /mnt/backup

[provider-cloud]
type: s3
bucket: my-archive-bucket
region: us-east-1
profile: iceshelf
```

## Quick comparison

| Type | Stores data in | Main required options | Best for |
| --- | --- | --- | --- |
| `cp` | Local directory or mounted share | `dest` | Simple local copies or mounted storage |
| `scp` | Remote host over SCP | `user`, `host` | Basic SSH-based uploads |
| `sftp` | Remote host over SFTP | `host` | Resumable SSH-based uploads with verification |
| `s3` | Amazon S3 or compatible API | `bucket`, AWS options | Durable object storage |
| `glacier` | Amazon Glacier vault | `vault`, AWS options | Low-cost long-term archival storage |

## Shared AWS options

The `s3` and `glacier` providers both support the same AWS-related options.
They require `region` plus either explicit credentials or a named `profile`.

| Option | Required | Purpose |
| --- | --- | --- |
| `region` | Yes | AWS region used when creating the client, for example `us-east-1`. |
| `access key id` | Conditional | AWS access key for explicit credentials. Use together with `secret access key`. |
| `secret access key` | Conditional | AWS secret key for explicit credentials. Use together with `access key id`. |
| `session token` | No | Temporary session token when using temporary AWS credentials. |
| `profile` | Conditional | Named AWS profile to load through boto3 instead of explicit keys. |
| `endpoint url` | No | Override the AWS API endpoint, useful for S3-compatible services or custom endpoints. |
| `aws config` | No | Path to a YAML file containing AWS settings. Values in the provider section override values from the file. |

`aws config` YAML files may contain these keys:

```yaml
region: us-east-1
access_key_id: AKIAIOSFODNN7EXAMPLE
secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
session_token: EXAMPLESESSIONTOKEN
profile: iceshelf
endpoint_url: https://s3.example.com
```

## `cp` provider

Copies backup files to a local directory using the system `cp` command. This is
useful for storing archives on the same machine or on a mounted network share.

### Options

| Option | Required | Default | Purpose |
| --- | --- | --- | --- |
| `dest` | Yes | None | Destination directory where backup files are copied. |
| `create` | No | `no` | Create `dest` automatically if it does not already exist. Accepts `yes` or `true`. |

### Notes

- The destination directory must already exist unless `create` is enabled.
- The provider fails verification if the `cp` command is not available.

### Example

```ini
[provider-local]
type: cp
dest: /srv/backups/iceshelf
create: yes
```

## `scp` provider

Uploads backup files to a remote host using the system `scp` command.

### Options

| Option | Required | Default | Purpose |
| --- | --- | --- | --- |
| `user` | Yes | None | SSH username used for the remote connection. |
| `host` | Yes | None | Remote hostname or IP address. |
| `dest` | No | `.` | Remote directory where files are uploaded. |
| `key` | No | None | Path to an SSH private key file used with `scp -i`. |
| `password` | No | None | Password passed through `sshpass` for password auth. |

### Notes

- Password-based uploads require the `sshpass` command to be installed.
- Key-based auth is usually the safer and simpler option.
- SCP uploads are straightforward, but they do not support resume or post-upload
  verification in iceshelf.

### Example

```ini
[provider-scp-offsite]
type: scp
user: backup
host: backup.example.com
dest: /srv/iceshelf
key: /home/ha/.ssh/id_ed25519
```

## `sftp` provider

Uploads backup files over SFTP using `paramiko`. This provider supports
resumable uploads, retries, and optional post-upload verification.

### Options

| Option | Required | Default | Purpose |
| --- | --- | --- | --- |
| `host` | Yes | None | Remote hostname or IP address. |
| `port` | No | `22` | SSH port used for the connection. |
| `user` | No | Current OS user | SSH username. If omitted, iceshelf uses the local login name. |
| `key` | No | None | Path to an SSH private key file. |
| `password` | No | None | Password for password auth, or the passphrase for an encrypted key file. |
| `path` | No | `.` | Remote directory where files are uploaded. |
| `retries` | No | `3` | Number of retry attempts after the initial upload attempt fails. |
| `resume` | No | `yes` | Resume partial uploads instead of restarting from zero. |
| `verify` | No | `yes` | Run remote verification after upload. |

### Notes

- Authentication is non-interactive only. If the server or key requires a
  prompt and neither `password` nor a working SSH agent can satisfy it, the
  provider fails instead of hanging.
- Authentication is attempted with an explicit key first, then SSH agent keys,
  then password auth.
- When `resume` is enabled, partial remote files are hash-checked before upload
  resumes. If the remote partial file looks corrupt, it is deleted and the
  upload restarts.
- When `verify` is enabled, the provider tries to run `sha256sum` on the remote
  host. If that command is unavailable, iceshelf falls back to a size-only
  check and logs a warning.
- This provider requires the Python package `paramiko`.

### Example

```ini
[provider-sftp-simple]
type: sftp
host: sftp.example.com
user: backup
path: /srv/iceshelf
key: /home/ha/.ssh/id_ed25519
```

### Example with retries, resume, and verification

```ini
[provider-sftp-verified]
type: sftp
host: sftp.example.com
port: 2222
user: backup
path: /srv/iceshelf
key: /home/ha/.ssh/id_ed25519
retries: 5
resume: yes
verify: yes
```

## `s3` provider

Uploads backup files to an Amazon S3 bucket using boto3. This also works with
S3-compatible services when `endpoint url` is set appropriately.

### Options

| Option | Required | Default | Purpose |
| --- | --- | --- | --- |
| `bucket` | Yes | None | Name of the destination bucket. |
| `prefix` | No | Empty | Prefix added before uploaded object names inside the bucket. |
| Shared AWS options | Yes | Varies | See the shared AWS options above. |

### Notes

- `region` is required.
- You must provide either `access key id` and `secret access key`, or `profile`.
- `aws config` can hold the shared AWS settings in YAML form.

### Example with explicit credentials

```ini
[provider-s3]
type: s3
bucket: my-archive-bucket
prefix: family/photos
region: us-east-1
access key id: AKIAIOSFODNN7EXAMPLE
secret access key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

### Example with `aws config`

```ini
[provider-s3-compatible]
type: s3
bucket: iceshelf
prefix: archives
aws config: /etc/iceshelf/aws-s3.yaml
endpoint url: https://s3.example.com
```

## `glacier` provider

Uploads backup files to an Amazon Glacier vault using boto3 multipart uploads.
This is optimized for archival storage rather than fast retrieval.

### Options

| Option | Required | Default | Purpose |
| --- | --- | --- | --- |
| `vault` | Yes | None | Name of the Glacier vault. |
| `threads` | No | `4` | Number of upload worker threads used for multipart uploads. |
| Shared AWS options | Yes | Varies | See the shared AWS options above. |

### Notes

- `region` is required.
- You must provide either `access key id` and `secret access key`, or `profile`.
- The provider tries to create the vault before uploading.
- Glacier retrieval is slow and may incur additional cost, so it fits long-term
  archival storage better than routine restores.

### Example with explicit credentials

```ini
[provider-glacier]
type: glacier
vault: my-iceshelf-vault
threads: 4
region: us-east-1
access key id: AKIAIOSFODNN7EXAMPLE
secret access key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

### Example with profile-based credentials

```ini
[provider-glacier-profile]
type: glacier
vault: my-iceshelf-vault
threads: 8
region: us-east-1
profile: iceshelf
```
