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


def merge_configs(baseline_path, override_path, folder_path, folder_name):
    """
    Merge baseline and per-folder configs.

    Returns the path to the written merged config file.
    Raises ValueError on validation failures.
    """
    baseline = configparser.ConfigParser()
    baseline.read(baseline_path)

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

    has_provider = any(s.lower().startswith("provider-") for s in baseline.sections())
    if not has_provider:
        raise ValueError("No [provider-*] section found in merged config -- backup has nowhere to go")

    merged_path = os.path.join(iceshelf_dir, ".merged.conf")
    os.makedirs(os.path.dirname(merged_path), exist_ok=True)
    with open(merged_path, "w") as f:
        baseline.write(f)

    return merged_path


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

    if not os.path.isfile(baseline_config):
        log.error("Baseline config not found: %s", baseline_config)
        sys.exit(1)
    if not os.path.isdir(data_dir):
        log.error("Data directory not found: %s", data_dir)
        sys.exit(1)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

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
                merged = merge_configs(baseline_config, cfg_path, folder, name)
            except ValueError as e:
                log.error("Config error for %s: %s", name, e)
                all_ok = False
                continue

            if not run_iceshelf(merged, folder):
                all_ok = False

        overran = time.monotonic() > deadline
        if overran:
            elapsed = time.monotonic() - run_start
            log.warning(
                "Backup run took %.0fs but interval is %ds -- missed next scheduled run",
                elapsed, interval,
            )

        set_healthy(all_ok and not overran)

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
