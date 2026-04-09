#!/usr/bin/env python3
"""
iceshelf Docker entrypoint.

Discovers backup targets under a data directory by scanning for
.iceshelf/config files, merges each with a baseline configuration,
and runs iceshelf sequentially for every target on a repeating schedule.
"""

import configparser
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

ICESHELF_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "iceshelf")
HEALTH_FILE = "/tmp/iceshelf-healthy"

log = logging.getLogger("iceshelf-docker")

shutting_down = False
current_proc = None
CFG_ENV_PREFIX = "CFG_"
CFG_SIMPLE_SECTIONS = {"options", "security", "custom", "paths", "sources", "exclude"}


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root.addHandler(handler)


def parse_interval(raw):
    """Parse a human-readable interval like '30m', '6h', '1d', or plain seconds."""
    raw = raw.strip().lower()
    m = re.fullmatch(r"(\d+)\s*([smhd])?", raw)
    if not m:
        raise ValueError(f"Invalid interval format: {raw!r}  (examples: 30m, 6h, 1d, 3600)")
    value = int(m.group(1))
    unit = m.group(2) or "s"
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]


def seconds_until(time_str):
    """Seconds from now until the next occurrence of HH:MM (UTC)."""
    hh, mm = (int(x) for x in time_str.strip().split(":"))
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    delta = (target - now).total_seconds()
    if delta <= 0:
        delta += 86400
    return delta


def discover_targets(data_dir):
    """Return sorted list of (name, folder_path, config_path) for folders with .iceshelf/config."""
    targets = []
    try:
        entries = sorted(os.listdir(data_dir))
    except OSError as e:
        log.error("Cannot list data directory %s: %s", data_dir, e)
        return targets
    for entry in entries:
        folder = os.path.join(data_dir, entry)
        if not os.path.isdir(folder):
            continue
        cfg = os.path.join(folder, ".iceshelf", "config")
        if os.path.isfile(cfg):
            targets.append((entry, folder, cfg))
    return targets


def _read_config(config_source):
    """Return a ConfigParser from a file path or an existing parser."""
    if isinstance(config_source, configparser.ConfigParser):
        cfg = configparser.ConfigParser()
        cfg.read_dict({section: dict(config_source.items(section)) for section in config_source.sections()})
        return cfg

    cfg = configparser.ConfigParser()
    if config_source:
        cfg.read(config_source)
    return cfg


def _set_config_value(cfg, section, option, value):
    if not cfg.has_section(section):
        cfg.add_section(section)
    cfg.set(section, option, value)


def _build_env_baseline(env=None):
    """Build a ConfigParser from CFG_* environment variables."""
    env = env or os.environ
    cfg = configparser.ConfigParser()

    for key, value in sorted(env.items()):
        if not key.startswith(CFG_ENV_PREFIX):
            continue

        remainder = key[len(CFG_ENV_PREFIX):]
        if not remainder:
            log.warning("Ignoring malformed config env var %s", key)
            continue

        parts = remainder.split("_")
        section_kind = parts[0].lower()

        if section_kind in {"provider", "providers"}:
            if len(parts) < 3 or not parts[1] or not parts[2]:
                log.warning("Ignoring malformed provider config env var %s", key)
                continue
            provider_name = parts[1].lower()
            option = " ".join(p.lower() for p in parts[2:] if p)
            if not option:
                log.warning("Ignoring malformed provider config env var %s", key)
                continue
            _set_config_value(cfg, f"provider-{provider_name}", option, value)
            continue

        if section_kind not in CFG_SIMPLE_SECTIONS:
            log.warning("Ignoring unknown Docker config env var %s", key)
            continue

        if len(parts) < 2:
            log.warning("Ignoring malformed config env var %s", key)
            continue

        option = " ".join(p.lower() for p in parts[1:] if p)
        if not option:
            log.warning("Ignoring malformed config env var %s", key)
            continue

        _set_config_value(cfg, section_kind, option, value)

    return cfg


def _compose_baseline_config(baseline_path, env=None):
    """Load file baseline when present and overlay Docker env config."""
    baseline = configparser.ConfigParser()

    if baseline_path and os.path.isfile(baseline_path):
        baseline.read(baseline_path)

    env_cfg = _build_env_baseline(env=env)
    for section in env_cfg.sections():
        if not baseline.has_section(section):
            baseline.add_section(section)
        for key, value in env_cfg.items(section):
            baseline.set(section, key, value)

    return baseline


def merge_configs(baseline_path, override_path, folder_path, folder_name, auto_prefix=False):
    """
    Merge baseline and per-folder configs.

    Returns (merged_config_path, prefix_was_auto).
    Raises ValueError on validation failures.
    """
    baseline = _read_config(baseline_path)

    if baseline.has_section("sources") and any(
        baseline.get("sources", k).strip() for k in baseline.options("sources")
    ):
        raise ValueError("Baseline config must not define [sources] entries")

    override = configparser.ConfigParser()
    override.read(override_path)

    if override.has_section("sources") and any(
        override.get("sources", k).strip() for k in override.options("sources")
    ):
        raise ValueError("Per-folder config must not define [sources] entries")

    for section in override.sections():
        if not baseline.has_section(section):
            baseline.add_section(section)
        for key, value in override.items(section):
            baseline.set(section, key, value)

    if not baseline.has_section("sources"):
        baseline.add_section("sources")
    baseline.set("sources", folder_name, folder_path)

    iceshelf_dir = os.path.join(folder_path, ".iceshelf")

    if not baseline.has_section("paths"):
        baseline.add_section("paths")
    baseline.set("paths", "prep dir", os.path.join(iceshelf_dir, "inprogress"))
    baseline.set("paths", "data dir", os.path.join(iceshelf_dir, "metadata"))
    baseline.set("paths", "done dir", "")
    baseline.set("paths", "create paths", "yes")

    if not baseline.has_section("exclude"):
        baseline.add_section("exclude")
    baseline.set("exclude", "_iceshelf_internal", "?.iceshelf/")

    prefix_was_auto = False
    has_prefix = baseline.has_section("options") and baseline.has_option("options", "prefix")
    explicit_blank_prefix = has_prefix and baseline.get("options", "prefix") == ""

    if auto_prefix or (not has_prefix and not explicit_blank_prefix):
        if not baseline.has_section("options"):
            baseline.add_section("options")
        baseline.set("options", "prefix", folder_name)
        prefix_was_auto = True

    has_provider = any(s.lower().startswith("provider-") for s in baseline.sections())
    if not has_provider:
        raise ValueError("No [provider-*] section found in merged config -- backup has nowhere to go")

    merged_path = os.path.join(iceshelf_dir, ".merged.conf")
    os.makedirs(os.path.dirname(merged_path), exist_ok=True)
    with open(merged_path, "w") as f:
        baseline.write(f)

    return merged_path, prefix_was_auto


def run_iceshelf(merged_config, folder_path):
    """Run iceshelf as a subprocess. Returns True on success (exit 0 or 10)."""
    global current_proc

    iceshelf_dir = os.path.join(folder_path, ".iceshelf")
    log_dir = os.path.join(iceshelf_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    logfile = os.path.join(log_dir, f"{timestamp}.log")

    cmd = [sys.executable, ICESHELF_BIN, "--logfile", logfile, merged_config]
    log.info("Running: %s", " ".join(cmd))

    try:
        current_proc = subprocess.Popen(cmd)
        rc = current_proc.wait()
        current_proc = None
    except Exception:
        current_proc = None
        log.exception("Failed to run iceshelf for %s", folder_path)
        return False

    if rc in (0, 10):
        if rc == 10:
            log.warning("iceshelf exited 10 (size limit reached) for %s -- counted as success", folder_path)
        else:
            log.info("iceshelf completed successfully for %s", folder_path)
        return True

    log.error("iceshelf failed for %s with exit code %d", folder_path, rc)
    return False


def set_healthy(healthy):
    if healthy:
        try:
            open(HEALTH_FILE, "w").close()
        except OSError:
            pass
    else:
        try:
            os.remove(HEALTH_FILE)
        except FileNotFoundError:
            pass


def interruptible_sleep(seconds):
    """Sleep in small increments so we can react to SIGTERM promptly."""
    end = time.monotonic() + seconds
    while not shutting_down:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 2.0))


def handle_signal(signum, _frame):
    global shutting_down
    name = signal.Signals(signum).name
    log.info("Received %s, finishing current backup then exiting...", name)
    shutting_down = True


def main():
    setup_logging()

    baseline_config = os.environ.get("ICESHELF_CONFIG", "/config/iceshelf.conf")
    data_dir = os.environ.get("ICESHELF_DATA_DIR", "/data")
    interval_raw = os.environ.get("BACKUP_INTERVAL", "24h")
    start_time = os.environ.get("BACKUP_START_TIME", "").strip()
    dump_config = os.environ.get("ICESHELF_DUMP_CONFIG", "").strip().lower() in ("1", "yes", "true")
    auto_prefix = os.environ.get("ICESHELF_AUTO_PREFIX", "").strip().lower() in ("1", "yes", "true")

    try:
        interval = parse_interval(interval_raw)
    except ValueError as e:
        log.error("Bad BACKUP_INTERVAL: %s", e)
        sys.exit(1)

    log.info("iceshelf Docker entrypoint starting")
    log.info("  Baseline config : %s", baseline_config)
    log.info("  Data directory  : %s", data_dir)
    log.info("  Backup interval : %s (%d seconds)", interval_raw, interval)
    if start_time:
        log.info("  Start time      : %s UTC", start_time)
    if auto_prefix:
        log.info("  Auto prefix     : enabled")
    if dump_config:
        log.info("  Dump config     : enabled")

    if not os.path.isdir(data_dir):
        log.error("Data directory not found: %s", data_dir)
        sys.exit(1)

    baseline_cfg = _compose_baseline_config(baseline_config)
    has_env_baseline = any(k.startswith(CFG_ENV_PREFIX) for k in os.environ)

    if not os.path.isfile(baseline_config):
        if has_env_baseline:
            log.info("  Baseline source : Docker env only")
        else:
            log.error("Baseline config not found: %s", baseline_config)
            log.error("Provide %s or define CFG_* environment variables", baseline_config)
            sys.exit(1)
    elif has_env_baseline:
        log.info("  Baseline source : file + Docker env overrides")

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Report healthy during startup and while a backup cycle is in progress.
    # Health only flips unhealthy after an actual cycle failure.
    set_healthy(True)

    if start_time:
        try:
            wait = seconds_until(start_time)
        except (ValueError, IndexError):
            log.error("Bad BACKUP_START_TIME: %r  (expected HH:MM)", start_time)
            sys.exit(1)
        log.info("Waiting %.0f seconds until %s UTC for first run...", wait, start_time)
        interruptible_sleep(wait)
        if shutting_down:
            log.info("Shutdown requested before first run, exiting.")
            return

    while not shutting_down:
        run_start = time.monotonic()
        deadline = run_start + interval

        targets = discover_targets(data_dir)
        if not targets:
            log.warning("No backup targets found under %s (looking for .iceshelf/config)", data_dir)

        all_ok = True

        for name, folder, cfg_path in targets:
            if shutting_down:
                log.info("Shutdown requested, skipping remaining targets.")
                all_ok = False
                break

            log.info("=== Processing target: %s (%s) ===", name, folder)
            try:
                merged, prefix_was_auto = merge_configs(baseline_cfg, cfg_path, folder, name, auto_prefix)
            except ValueError as e:
                log.error("Config error for %s: %s", name, e)
                all_ok = False
                continue

            if prefix_was_auto:
                log.info("Auto-prefix for %s: \"%s\"", name, name)

            if dump_config:
                log.info("--- Merged config for %s ---", name)
                with open(merged) as _f:
                    for _line in _f:
                        log.info("  %s", _line.rstrip())
                log.info("--- End merged config ---")

            if not run_iceshelf(merged, folder):
                all_ok = False

        overran = time.monotonic() > deadline
        if overran:
            elapsed = time.monotonic() - run_start
            log.warning(
                "Backup run took %.0fs but interval is %ds -- missed next scheduled run",
                elapsed, interval,
            )

        set_healthy(all_ok)

        if shutting_down:
            break

        remaining = deadline - time.monotonic()
        if remaining > 0:
            log.info("Sleeping %.0f seconds until next run...", remaining)
            interruptible_sleep(remaining)
        else:
            log.info("Starting next run immediately (overran schedule).")

    log.info("iceshelf Docker entrypoint exiting.")


if __name__ == "__main__":
    main()
