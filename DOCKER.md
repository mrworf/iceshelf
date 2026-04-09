# Running iceshelf in Docker

iceshelf ships a Docker image that automatically discovers, configures, and runs
backups on a repeating schedule. You can provide a **baseline configuration**
either as a mounted INI file or directly through Docker environment variables,
then bind-mount one or more **data directories**. Any folder that contains a
`.iceshelf/config` file is picked up as a backup target.

## Quick start

```yaml
# docker-compose.yml
services:
  iceshelf:
    image: ghcr.io/mrworf/iceshelf:latest
    restart: unless-stopped
    environment:
      BACKUP_INTERVAL: "24h"
      BACKUP_START_TIME: "03:00"
      CFG_OPTIONS_MAX_SIZE: "50G"
      CFG_OPTIONS_COMPRESS: "yes"
      CFG_PROVIDER_LOCAL_TYPE: "cp"
      CFG_PROVIDER_LOCAL_DEST: "/backups"
    volumes:
      - /srv/data:/data
      - /srv/backups:/backups
```

```
/srv/data/
├── documents/
│   ├── .iceshelf/
│   │   └── config          # per-folder overrides (can be empty)
│   ├── taxes/
│   └── contracts/
└── photos/
    ├── .iceshelf/
    │   └── config
    └── 2025/
```

With the layout above the container will run two sequential iceshelf backups
on every cycle: one for `documents` and one for `photos`.

## Concepts

### Baseline configuration

The baseline config is a standard iceshelf INI file mounted at
`/config/iceshelf.conf` (configurable via `ICESHELF_CONFIG`). It sets defaults
that apply to **all** backup targets: providers, security, options, exclusion
rules, etc. Docker can also synthesize this baseline from `CFG_*` environment
variables.

There is one restriction: **the `[sources]` section must not be defined** in
the baseline. Sources are generated automatically from the discovered folders.

A sample baseline is included at `docker/baseline.sample.conf`.

#### Baseline from environment variables

Docker-specific env vars use this naming scheme:

- `CFG_OPTIONS_MAX_SIZE` -> `[options] max size`
- `CFG_OPTIONS_CHANGE_METHOD` -> `[options] change method`
- `CFG_SECURITY_ENCRYPT` -> `[security] encrypt`
- `CFG_CUSTOM_PRE_COMMAND` -> `[custom] pre command`
- `CFG_PROVIDER_LOCAL_TYPE` -> `[provider-local] type`
- `CFG_PROVIDER_LOCAL_DEST` -> `[provider-local] dest`

Rules:

- `CFG_<section>_<option>` maps to simple sections such as `options`, `security`, and `custom`.
- `CFG_PROVIDER_<name>_<option>` maps to provider sections named `[provider-<name>]`.
- Env names are case-insensitive in effect; generated sections and options are lowercased.
- Remaining underscores become spaces in the generated option name.
- Malformed or unknown `CFG_*` names are ignored with a warning in the container log.

Precedence:

- If `ICESHELF_CONFIG` exists, it is loaded first.
- Any `CFG_*` values then override matching keys from the file baseline.
- Per-folder `.iceshelf/config` files still override the merged baseline as before.

Limitations:

- `CFG_*` does not support defining `[sources]`; the entrypoint still generates sources from discovered folders only.
- Ordered user-defined `[exclude]` rules are not a good fit for flat env vars and are best kept in mounted or per-folder config files.
- Per-folder `.iceshelf/config` remains the right place for target-specific overrides that do not fit well in env vars.

### Per-folder configuration

Each folder under the data root that contains `.iceshelf/config` becomes a
backup target. The per-folder config is layered on top of the baseline --
any key it sets overrides the corresponding baseline value.

Like the baseline, the per-folder config **must not define `[sources]`**.
The folder itself is automatically registered as the sole source.

A per-folder config can be completely empty (just touch the file) if the
baseline already provides everything needed. Common uses for per-folder
overrides include:

- Pointing at a different provider or bucket.
- Changing the encryption key or prefix.
- Adding extra exclusion rules.

### Prefix behavior

When a target omits the `prefix` option entirely, the Docker entrypoint uses
the folder name as the prefix. That is usually the easiest way to back up
multiple folders into one destination without filename collisions.

If you really want no prefix at all, define `prefix:` explicitly in either the
baseline or the per-folder config. An explicit blank value is preserved and is
not replaced by the folder name.

### Shared key files

When several targets use the same GPG or SSH keys, bind them into `/config/`
once and reference those paths from the baseline or per-folder configs. That
keeps key material in one place instead of copying it into every backup folder.

Typical examples:

```ini
[security]
key file: /config/iceshelf-keys.asc

[provider-remote]
type: sftp
host: backup.example.com
user: backup
key: /config/id_ed25519
path: /srv/iceshelf
```

### Automatic path management

The entrypoint forces the following paths for every target, regardless of what
the configs say:

| Path setting | Value |
|---|---|
| `prep dir` | `<folder>/.iceshelf/inprogress/` |
| `data dir` | `<folder>/.iceshelf/metadata/` |
| `done dir` | *(empty -- disabled)* |
| `create paths` | `yes` |

An exclusion rule (`?.iceshelf/`) is also injected so iceshelf never backs up
its own working directories.

### Logging

Each iceshelf run writes a timestamped log to `<folder>/.iceshelf/logs/` **and**
to stdout simultaneously. Container-level logs (`docker logs`) therefore show
the full output of every run, while per-folder logs remain available on the
bind-mounted volume for later inspection.

```
/srv/data/photos/.iceshelf/
├── config
├── logs/
│   ├── 20260327-030012.log
│   └── 20260328-030008.log
├── metadata/
│   └── checksum.json
└── inprogress/
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ICESHELF_CONFIG` | `/config/iceshelf.conf` | Path to the baseline config inside the container. |
| `ICESHELF_DATA_DIR` | `/data` | Root directory to scan for backup targets (top-level subdirectories with `.iceshelf/config`). |
| `BACKUP_INTERVAL` | `24h` | How often to run a full backup cycle. Accepts a number with an optional suffix: `s` (seconds), `m` (minutes), `h` (hours), `d` (days). Plain digits are treated as seconds. |
| `BACKUP_START_TIME` | *(unset)* | Optional UTC wall-clock time in `HH:MM` format. When set, the first backup is delayed until this time. Combined with `BACKUP_INTERVAL=24h`, backups run daily at a fixed hour. When omitted, the first backup starts as soon as the container is ready. |
| `ICESHELF_DUMP_CONFIG` | *(unset)* | Set to `1`, `yes`, or `true` to print the full merged configuration for each target to the container log before running iceshelf. Useful for debugging config merging issues. |
| `ICESHELF_AUTO_PREFIX` | *(unset)* | Set to `1`, `yes`, or `true` to force the backup file prefix to the folder name (e.g. `/data/photos` produces prefix `photos`) even when the config already defines a prefix. When unset, omitted `prefix` values still auto-prefix, but an explicitly blank `prefix:` is preserved. |
| `CFG_*` | *(unset)* | Docker-only baseline config override namespace. Example: `CFG_OPTIONS_MAX_SIZE`, `CFG_SECURITY_KEY_FILE`, `CFG_PROVIDER_LOCAL_DEST`. |

## Health checking

The container exposes a Docker `HEALTHCHECK`. The rules are simple:

- The container starts **unhealthy** (before the first run completes).
- After a backup cycle finishes, the container becomes **healthy** only if
  **every** target succeeded **and** the run finished before the next scheduled
  slot.
- If **any** backup fails, the container goes **unhealthy** until a subsequent
  cycle completes with all targets succeeding.
- If a cycle takes longer than `BACKUP_INTERVAL` (i.e. the schedule is too
  aggressive), the overrun is logged and the container goes **unhealthy**. It
  returns to healthy once a full cycle completes within the interval.

You can query health with `docker inspect` or let your orchestrator (Compose,
Swarm, Kubernetes) act on it automatically.

## Provider requirement

Because the `done dir` is always disabled inside the container, every target
**must** have at least one `[provider-*]` section in its merged configuration.
If a target lacks a provider, the entrypoint logs an error for that target and
continues to the next one. The failed target counts as a backup failure for
health purposes.

## Building locally

To build the image from source instead of pulling from GHCR:

```bash
docker build -t iceshelf .
```

Or use the compose file with the `build` directive:

```yaml
services:
  iceshelf:
    build: .
    # image: ghcr.io/mrworf/iceshelf:latest
    ...
```

## Full docker-compose example

```yaml
services:
  iceshelf:
    image: ghcr.io/mrworf/iceshelf:latest
    restart: unless-stopped
    environment:
      BACKUP_INTERVAL: "24h"
      BACKUP_START_TIME: "03:00"
      CFG_OPTIONS_MAX_SIZE: "50G"
      CFG_OPTIONS_COMPRESS: "yes"
      CFG_OPTIONS_CHANGE_METHOD: "data"
      CFG_SECURITY_KEY_FILE: "/config/iceshelf-keys.asc"
      CFG_PROVIDER_ARCHIVE_TYPE: "s3"
      CFG_PROVIDER_ARCHIVE_BUCKET: "mybucket"
      CFG_PROVIDER_ARCHIVE_REGION: "us-east-1"
      CFG_PROVIDER_ARCHIVE_STORAGE_CLASS: "DEEP_ARCHIVE"
    volumes:
      # Shared GPG key file for encrypt/sign (read-only)
      - ./iceshelf-keys.asc:/config/iceshelf-keys.asc:ro
      # Data directories
      - /srv/documents:/data/documents
      - /srv/photos:/data/photos
    healthcheck:
      test: ["CMD", "/app/docker/healthcheck.sh"]
      interval: 60s
      timeout: 5s
      start_period: 300s
      retries: 1
```

## Graceful shutdown

On `SIGTERM` or `SIGINT` the entrypoint waits for the currently running
iceshelf subprocess to finish, then exits. Remaining targets in the cycle are
skipped.

## CI / Container registry

The Docker image is built and pushed to the GitHub Container Registry
automatically on every push to `master`. Pull requests trigger a build but
do not push. The image is tagged as `latest` and with the short git SHA.
