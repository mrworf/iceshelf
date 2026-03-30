# Running iceshelf in Docker

iceshelf ships a Docker image that automatically discovers, configures, and runs
backups on a repeating schedule. You provide a **baseline configuration** and
bind-mount one or more **data directories**. Any folder that contains a
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
    volumes:
      - ./my-iceshelf.conf:/config/iceshelf.conf:ro
      - /srv/data:/data
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
rules, etc.

There is one restriction: **the `[sources]` section must not be defined** in
the baseline. Sources are generated automatically from the discovered folders.

A sample baseline is included at `docker/baseline.sample.conf`.

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
    volumes:
      # Baseline configuration (read-only)
      - ./my-iceshelf.conf:/config/iceshelf.conf:ro
      # SSH key for SFTP/SCP providers (read-only)
      - ~/.ssh/id_ed25519:/config/id_ed25519:ro
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
