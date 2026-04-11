"""Unit tests for docker/entrypoint.py -- runs without a container."""

import configparser
import os
import sys
from collections import deque

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "docker"))
import entrypoint


# ---------------------------------------------------------------------------
# parse_interval
# ---------------------------------------------------------------------------

class TestParseInterval:
    def test_seconds_plain(self):
        assert entrypoint.parse_interval("3600") == 3600

    def test_seconds_suffix(self):
        assert entrypoint.parse_interval("90s") == 90

    def test_minutes(self):
        assert entrypoint.parse_interval("30m") == 1800

    def test_hours(self):
        assert entrypoint.parse_interval("6h") == 21600

    def test_days(self):
        assert entrypoint.parse_interval("1d") == 86400

    def test_case_insensitive(self):
        assert entrypoint.parse_interval(" 24H ") == 86400

    def test_invalid_empty(self):
        with pytest.raises(ValueError):
            entrypoint.parse_interval("")

    def test_invalid_letters(self):
        with pytest.raises(ValueError):
            entrypoint.parse_interval("abc")

    def test_invalid_unit(self):
        with pytest.raises(ValueError):
            entrypoint.parse_interval("10x")


# ---------------------------------------------------------------------------
# seconds_until
# ---------------------------------------------------------------------------

class TestSecondsUntil:
    def test_returns_positive(self):
        result = entrypoint.seconds_until("13:00")
        assert 0 < result <= 86400

    def test_returns_at_most_one_day(self):
        result = entrypoint.seconds_until("00:00")
        assert 0 < result <= 86400

    def test_invalid_hour_raises(self):
        with pytest.raises(ValueError):
            entrypoint.seconds_until("25:00")

    def test_invalid_format_raises(self):
        with pytest.raises(Exception):
            entrypoint.seconds_until("abc")


# ---------------------------------------------------------------------------
# discover_targets
# ---------------------------------------------------------------------------

class TestDiscoverTargets:
    def test_empty_dir(self, tmp_path):
        assert entrypoint.discover_targets(str(tmp_path)) == []

    def test_skips_dirs_without_iceshelf(self, tmp_path):
        (tmp_path / "folderA").mkdir()
        assert entrypoint.discover_targets(str(tmp_path)) == []

    def test_skips_dirs_with_iceshelf_but_no_config(self, tmp_path):
        (tmp_path / "folderA" / ".iceshelf").mkdir(parents=True)
        assert entrypoint.discover_targets(str(tmp_path)) == []

    def test_finds_target(self, tmp_path):
        cfg_dir = tmp_path / "mybackup" / ".iceshelf"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config").write_text("")
        targets = entrypoint.discover_targets(str(tmp_path))
        assert len(targets) == 1
        assert targets[0][0] == "mybackup"

    def test_skips_plain_files(self, tmp_path):
        (tmp_path / "plainfile.txt").write_text("hello")
        cfg_dir = tmp_path / "real" / ".iceshelf"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config").write_text("")
        targets = entrypoint.discover_targets(str(tmp_path))
        assert len(targets) == 1
        assert targets[0][0] == "real"

    def test_sorted_order(self, tmp_path):
        for name in ["charlie", "alpha", "bravo"]:
            d = tmp_path / name / ".iceshelf"
            d.mkdir(parents=True)
            (d / "config").write_text("")
        names = [t[0] for t in entrypoint.discover_targets(str(tmp_path))]
        assert names == ["alpha", "bravo", "charlie"]

    def test_nonexistent_dir(self, tmp_path):
        assert entrypoint.discover_targets(str(tmp_path / "nope")) == []


# ---------------------------------------------------------------------------
# Helper: write an INI file from a string
# ---------------------------------------------------------------------------

def _write_conf(path, text):
    with open(path, "w") as f:
        f.write(text)


def _read_cfg(source):
    cfg = configparser.ConfigParser()
    if isinstance(source, configparser.ConfigParser):
        cfg.read_dict({section: dict(source.items(section)) for section in source.sections()})
    else:
        cfg.read(source)
    return cfg


# ---------------------------------------------------------------------------
# env baseline synthesis
# ---------------------------------------------------------------------------

class TestEnvBaseline:
    def test_builds_simple_sections(self):
        cfg = entrypoint._build_env_baseline({
            "CFG_OPTIONS_MAX_SIZE": "1G",
            "CFG_OPTIONS_CHANGE_METHOD": "data",
            "CFG_OPTIONS_LOOP_SLICES": "no",
            "CFG_OPTIONS_SKIP_BROKEN_LINKS": "yes",
            "CFG_OPTIONS_IGNORE_UNAVAILABLE_FILES": "yes",
            "CFG_SECURITY_ENCRYPT": "me@example.com",
            "CFG_CUSTOM_PRE_COMMAND": "/usr/local/bin/prep",
        })

        assert cfg.get("options", "max size") == "1G"
        assert cfg.get("options", "change method") == "data"
        assert cfg.get("options", "loop slices") == "no"
        assert cfg.get("options", "skip broken links") == "yes"
        assert cfg.get("options", "ignore unavailable files") == "yes"
        assert cfg.get("security", "encrypt") == "me@example.com"
        assert cfg.get("custom", "pre command") == "/usr/local/bin/prep"

    def test_builds_provider_sections(self):
        cfg = entrypoint._build_env_baseline({
            "CFG_PROVIDER_LOCAL_TYPE": "cp",
            "CFG_PROVIDER_LOCAL_DEST": "/backups",
            "CFG_PROVIDER_S3MAIN_TYPE": "s3",
            "CFG_PROVIDER_S3MAIN_BUCKET": "mybucket",
        })

        assert cfg.get("provider-local", "type") == "cp"
        assert cfg.get("provider-local", "dest") == "/backups"
        assert cfg.get("provider-s3main", "type") == "s3"
        assert cfg.get("provider-s3main", "bucket") == "mybucket"

    def test_ignores_malformed_provider_vars(self, caplog):
        cfg = entrypoint._build_env_baseline({
            "CFG_PROVIDER": "bad",
            "CFG_PROVIDER__TYPE": "bad",
            "CFG_PROVIDER_NAME_": "bad",
        })

        assert cfg.sections() == []
        assert "Ignoring malformed provider config env var" in caplog.text

    def test_ignores_unknown_sections(self, caplog):
        cfg = entrypoint._build_env_baseline({
            "CFG_FOO_BAR": "baz",
        })

        assert cfg.sections() == []
        assert "Ignoring unknown Docker config env var" in caplog.text

    def test_compose_baseline_env_overrides_file(self, tmp_path):
        baseline = tmp_path / "baseline.conf"
        _write_conf(
            baseline,
            "[options]\ncompress: yes\n[provider-local]\ntype: cp\ndest: /old\n",
        )

        cfg = entrypoint._compose_baseline_config(str(baseline), {
            "CFG_OPTIONS_COMPRESS": "no",
            "CFG_OPTIONS_SKIP_BROKEN_LINKS": "yes",
            "CFG_PROVIDER_LOCAL_DEST": "/new",
        })

        assert cfg.get("options", "compress") == "no"
        assert cfg.get("options", "skip broken links") == "yes"
        assert cfg.get("provider-local", "dest") == "/new"
        assert cfg.get("provider-local", "type") == "cp"

    def test_compose_baseline_supports_env_only(self, tmp_path):
        missing = tmp_path / "missing.conf"

        cfg = entrypoint._compose_baseline_config(str(missing), {
            "CFG_PROVIDER_LOCAL_TYPE": "cp",
            "CFG_PROVIDER_LOCAL_DEST": "/backups",
        })

        assert cfg.get("provider-local", "type") == "cp"
        assert cfg.get("provider-local", "dest") == "/backups"


# ---------------------------------------------------------------------------
# merge_configs
# ---------------------------------------------------------------------------

class TestMergeConfigs:
    @pytest.fixture()
    def layout(self, tmp_path):
        """Create a minimal baseline + folder structure and return paths."""
        baseline = str(tmp_path / "baseline.conf")
        folder = tmp_path / "photos"
        iceshelf_dir = folder / ".iceshelf"
        iceshelf_dir.mkdir(parents=True)
        override = str(iceshelf_dir / "config")
        _write_conf(baseline, "[provider-s3]\ntype: s3\nbucket: mybucket\n")
        _write_conf(override, "")
        return {
            "baseline": baseline,
            "override": override,
            "folder": str(folder),
            "name": "photos",
            "iceshelf_dir": str(iceshelf_dir),
        }

    def _read_merged(self, path):
        return _read_cfg(path)

    # -- basic merging --

    def test_baseline_values_carry_through(self, layout):
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("provider-s3", "type") == "s3"
        assert cfg.get("provider-s3", "bucket") == "mybucket"

    def test_override_wins(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\ncompress: yes\n[provider-s3]\ntype: s3\nbucket: b\n")
        _write_conf(layout["override"], "[options]\ncompress: no\nignore unavailable files: yes\n")
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "compress") == "no"
        assert cfg.get("options", "ignore unavailable files") == "yes"

    def test_new_section_from_override(self, layout):
        _write_conf(layout["override"], "[security]\nencrypt: me@example.com\n")
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("security", "encrypt") == "me@example.com"

    # -- sources rejected --

    def test_sources_in_baseline_rejected(self, layout):
        _write_conf(layout["baseline"],
                     "[sources]\nstuff=/some/path\n[provider-cp]\ntype: cp\ndest: /x\n")
        with pytest.raises(ValueError, match="Baseline"):
            entrypoint.merge_configs(
                layout["baseline"], layout["override"], layout["folder"], layout["name"]
            )

    def test_sources_in_override_rejected(self, layout):
        _write_conf(layout["override"], "[sources]\nstuff=/some/path\n")
        with pytest.raises(ValueError, match="Per-folder"):
            entrypoint.merge_configs(
                layout["baseline"], layout["override"], layout["folder"], layout["name"]
            )

    def test_sources_from_env_baseline_rejected(self, layout):
        baseline = entrypoint._compose_baseline_config(None, {
            "CFG_SOURCES_STUFF": "/some/path",
            "CFG_PROVIDER_LOCAL_TYPE": "cp",
            "CFG_PROVIDER_LOCAL_DEST": "/x",
        })
        with pytest.raises(ValueError, match="Baseline"):
            entrypoint.merge_configs(
                baseline, layout["override"], layout["folder"], layout["name"]
            )

    # -- auto-generated sources --

    def test_auto_sources(self, layout):
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("sources", "photos") == layout["folder"]

    # -- forced paths --

    def test_forced_paths(self, layout):
        _write_conf(layout["baseline"],
                     "[paths]\nprep dir: /wrong\ndata dir: /wrong\ndone dir: /wrong\n"
                     "[provider-cp]\ntype: cp\ndest: /x\n")
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("paths", "prep dir") == os.path.join(layout["iceshelf_dir"], "inprogress")
        assert cfg.get("paths", "data dir") == os.path.join(layout["iceshelf_dir"], "metadata")
        assert cfg.get("paths", "done dir") == ""
        assert cfg.get("paths", "create paths") == "yes"

    # -- exclusion rule --

    def test_iceshelf_exclusion_injected(self, layout):
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("exclude", "_iceshelf_internal") == "?.iceshelf/"

    def test_existing_exclude_rules_preserved(self, layout):
        _write_conf(layout["baseline"],
                     "[exclude]\nbigfiles=*.iso\n[provider-s3]\ntype: s3\nbucket: b\n")
        _write_conf(layout["override"], "[exclude]\ntmpfiles=*.tmp\n")
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("exclude", "bigfiles") == "*.iso"
        assert cfg.get("exclude", "tmpfiles") == "*.tmp"
        assert cfg.get("exclude", "_iceshelf_internal") == "?.iceshelf/"

    # -- provider validation --

    def test_no_provider_raises(self, tmp_path):
        baseline = str(tmp_path / "b.conf")
        folder = tmp_path / "data"
        (folder / ".iceshelf").mkdir(parents=True)
        override = str(folder / ".iceshelf" / "config")
        _write_conf(baseline, "[options]\ncompress: yes\n")
        _write_conf(override, "")
        with pytest.raises(ValueError, match="provider"):
            entrypoint.merge_configs(baseline, override, str(folder), "data")

    def test_provider_from_baseline_preserved(self, layout):
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.has_section("provider-s3")
        assert cfg.get("provider-s3", "type") == "s3"

    def test_provider_from_env_only_baseline(self, layout):
        baseline = entrypoint._compose_baseline_config(None, {
            "CFG_PROVIDER_LOCAL_TYPE": "cp",
            "CFG_PROVIDER_LOCAL_DEST": "/backups",
        })
        merged, _ = entrypoint.merge_configs(
            baseline, layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("provider-local", "type") == "cp"
        assert cfg.get("provider-local", "dest") == "/backups"

    def test_env_baseline_overrides_file_values(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\ncompress: yes\nignore unavailable files: no\n[provider-local]\ntype: cp\ndest: /old\n")
        baseline = entrypoint._compose_baseline_config(layout["baseline"], {
            "CFG_OPTIONS_COMPRESS": "no",
            "CFG_OPTIONS_IGNORE_UNAVAILABLE_FILES": "yes",
            "CFG_PROVIDER_LOCAL_DEST": "/new",
        })
        merged, _ = entrypoint.merge_configs(
            baseline, layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "compress") == "no"
        assert cfg.get("options", "ignore unavailable files") == "yes"
        assert cfg.get("provider-local", "dest") == "/new"

    def test_folder_override_replaces_env_baseline_option(self, layout):
        baseline = entrypoint._compose_baseline_config(None, {
            "CFG_OPTIONS_IGNORE_UNAVAILABLE_FILES": "yes",
            "CFG_PROVIDER_LOCAL_TYPE": "cp",
            "CFG_PROVIDER_LOCAL_DEST": "/backups",
        })
        _write_conf(layout["override"], "[options]\nignore unavailable files: no\n")

        merged, _ = entrypoint.merge_configs(
            baseline, layout["override"], layout["folder"], layout["name"]
        )

        cfg = self._read_merged(merged)
        assert cfg.get("options", "ignore unavailable files") == "no"

    def test_provider_override_replaces_values(self, layout):
        _write_conf(layout["override"],
                     "[provider-s3]\ntype: s3\nbucket: other-bucket\n")
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        cfg = self._read_merged(merged)
        assert cfg.get("provider-s3", "bucket") == "other-bucket"

    # -- output file location --

    def test_merged_file_location(self, layout):
        merged, _ = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"]
        )
        expected = os.path.join(layout["iceshelf_dir"], ".merged.conf")
        assert merged == expected
        assert os.path.isfile(merged)

    # -- auto prefix --

    def test_auto_prefix_env_overrides_existing(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\nprefix: general\n[provider-s3]\ntype: s3\nbucket: b\n")
        merged, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=True,
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "prefix") == "photos"
        assert was_auto is True

    def test_auto_prefix_env_overrides_empty(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\nprefix:\n[provider-s3]\ntype: s3\nbucket: b\n")
        merged, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=True,
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "prefix") == "photos"
        assert was_auto is True

    def test_missing_prefix_auto_generated(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\ncompress: yes\n[provider-s3]\ntype: s3\nbucket: b\n")
        merged, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=False,
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "prefix") == "photos"
        assert was_auto is True

    def test_missing_options_section_auto_generates_prefix(self, layout):
        _write_conf(layout["baseline"], "[provider-s3]\ntype: s3\nbucket: b\n")
        merged, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=False,
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "prefix") == "photos"
        assert was_auto is True

    def test_explicit_prefix_preserved(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\nprefix: general\n[provider-s3]\ntype: s3\nbucket: b\n")
        merged, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=False,
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "prefix") == "general"
        assert was_auto is False

    def test_empty_prefix_preserved(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\nprefix:\n[provider-s3]\ntype: s3\nbucket: b\n")
        merged, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=False,
        )
        cfg = self._read_merged(merged)
        assert cfg.get("options", "prefix") == ""
        assert was_auto is False

    def test_auto_prefix_returns_flag_true(self, layout):
        _, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=True,
        )
        assert was_auto is True

    def test_explicit_prefix_returns_flag_false(self, layout):
        _write_conf(layout["baseline"],
                     "[options]\nprefix: myprefix\n[provider-s3]\ntype: s3\nbucket: b\n")
        _, was_auto = entrypoint.merge_configs(
            layout["baseline"], layout["override"], layout["folder"], layout["name"],
            auto_prefix=False,
        )
        assert was_auto is False


# ---------------------------------------------------------------------------
# set_healthy
# ---------------------------------------------------------------------------

class TestSetHealthy:
    @pytest.fixture(autouse=True)
    def _patch_health_file(self, tmp_path, monkeypatch):
        self.health_file = str(tmp_path / "iceshelf-healthy")
        monkeypatch.setattr(entrypoint, "HEALTH_FILE", self.health_file)

    def test_set_healthy_creates_file(self):
        entrypoint.set_healthy(True)
        assert os.path.isfile(self.health_file)

    def test_set_unhealthy_removes_file(self):
        entrypoint.set_healthy(True)
        assert os.path.isfile(self.health_file)
        entrypoint.set_healthy(False)
        assert not os.path.exists(self.health_file)

    def test_set_unhealthy_when_missing_no_error(self):
        entrypoint.set_healthy(False)
        assert not os.path.exists(self.health_file)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

class TestMainHealthBehavior:
    @pytest.fixture(autouse=True)
    def _reset_globals(self, monkeypatch, tmp_path):
        monkeypatch.setattr(entrypoint, "shutting_down", False)
        monkeypatch.setattr(entrypoint, "current_proc", None)
        monkeypatch.setattr(entrypoint.signal, "signal", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(entrypoint, "setup_logging", lambda: None)
        monkeypatch.setattr(entrypoint.os.path, "isdir", lambda _path: True)
        monkeypatch.setattr(entrypoint.os.path, "isfile", lambda _path: True)
        monkeypatch.setattr(
            entrypoint,
            "_compose_baseline_config",
            lambda *_args, **_kwargs: configparser.ConfigParser(),
        )
        self.health_states = []
        monkeypatch.setattr(entrypoint, "set_healthy", lambda healthy: self.health_states.append(healthy))

    def _configure_env(self, monkeypatch, **env):
        values = {
            "ICESHELF_CONFIG": "/config/iceshelf.conf",
            "ICESHELF_DATA_DIR": "/data",
            "BACKUP_INTERVAL": "10s",
        }
        values.update(env)
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    def test_startup_marks_healthy_before_any_backup_finishes(self, monkeypatch):
        self._configure_env(monkeypatch)
        monkeypatch.setattr(entrypoint, "discover_targets", lambda _data_dir: [])
        monkeypatch.setattr(entrypoint, "run_iceshelf", lambda *_args, **_kwargs: True)
        monotonic_values = deque([0.0, 1.0, 2.0])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: monotonic_values.popleft())

        def fake_sleep(_seconds):
            entrypoint.shutting_down = True

        monkeypatch.setattr(entrypoint, "interruptible_sleep", fake_sleep)

        entrypoint.main()

        assert self.health_states == [True, True]

    def test_waiting_for_start_time_remains_healthy(self, monkeypatch):
        self._configure_env(monkeypatch, BACKUP_START_TIME="03:00")
        monkeypatch.setattr(entrypoint, "seconds_until", lambda _value: 30)
        monkeypatch.setattr(entrypoint, "discover_targets", lambda _data_dir: [])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: 0.0)

        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) == 2:
                entrypoint.shutting_down = True

        monkeypatch.setattr(entrypoint, "interruptible_sleep", fake_sleep)

        entrypoint.main()

        assert sleep_calls[0] == 30
        assert self.health_states == [True, True]

    def test_first_long_cycle_stays_healthy_when_successful(self, monkeypatch):
        self._configure_env(monkeypatch, BACKUP_INTERVAL="5s")
        discover_calls = {"count": 0}

        def fake_discover(_data_dir):
            discover_calls["count"] += 1
            if discover_calls["count"] > 1:
                entrypoint.shutting_down = True
                return []
            return [("photos", "/data/photos", "/data/photos/.iceshelf/config")]

        monkeypatch.setattr(entrypoint, "discover_targets", fake_discover)
        monkeypatch.setattr(entrypoint, "merge_configs", lambda *_args, **_kwargs: ("/tmp/merged.conf", False))
        monkeypatch.setattr(entrypoint, "run_iceshelf", lambda *_args, **_kwargs: True)
        monotonic_values = deque([0.0, 7.0, 8.0, 9.0, 10.0, 11.0])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: monotonic_values.popleft())
        monkeypatch.setattr(entrypoint, "interruptible_sleep", lambda _seconds: None)

        entrypoint.main()

        assert self.health_states == [True, True, True]

    def test_later_long_successful_cycle_stays_healthy(self, monkeypatch):
        self._configure_env(monkeypatch, BACKUP_INTERVAL="5s")
        discover_calls = {"count": 0}

        def fake_discover(_data_dir):
            discover_calls["count"] += 1
            if discover_calls["count"] > 2:
                entrypoint.shutting_down = True
                return []
            return [("photos", "/data/photos", "/data/photos/.iceshelf/config")]

        monkeypatch.setattr(entrypoint, "discover_targets", fake_discover)
        monkeypatch.setattr(entrypoint, "merge_configs", lambda *_args, **_kwargs: ("/tmp/merged.conf", False))
        monkeypatch.setattr(entrypoint, "run_iceshelf", lambda *_args, **_kwargs: True)
        monotonic_values = deque([0.0, 7.0, 7.0, 8.0, 12.0, 20.0, 21.0, 22.0, 23.0, 24.0])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: monotonic_values.popleft())
        monkeypatch.setattr(entrypoint, "interruptible_sleep", lambda _seconds: None)

        entrypoint.main()

        assert self.health_states == [True, True, True, True]

    def test_target_failure_marks_unhealthy(self, monkeypatch):
        self._configure_env(monkeypatch)
        monkeypatch.setattr(
            entrypoint,
            "discover_targets",
            lambda _data_dir: [("photos", "/data/photos", "/data/photos/.iceshelf/config")],
        )
        monkeypatch.setattr(entrypoint, "merge_configs", lambda *_args, **_kwargs: ("/tmp/merged.conf", False))
        monkeypatch.setattr(entrypoint, "run_iceshelf", lambda *_args, **_kwargs: False)
        monotonic_values = deque([0.0, 1.0, 2.0])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: monotonic_values.popleft())

        def fake_sleep(_seconds):
            entrypoint.shutting_down = True

        monkeypatch.setattr(entrypoint, "interruptible_sleep", fake_sleep)

        entrypoint.main()

        assert self.health_states == [True, False]

    def test_config_error_marks_unhealthy(self, monkeypatch):
        self._configure_env(monkeypatch)
        monkeypatch.setattr(
            entrypoint,
            "discover_targets",
            lambda _data_dir: [("photos", "/data/photos", "/data/photos/.iceshelf/config")],
        )

        def raise_config_error(*_args, **_kwargs):
            raise ValueError("bad config")

        monkeypatch.setattr(entrypoint, "merge_configs", raise_config_error)
        monotonic_values = deque([0.0, 1.0, 2.0])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: monotonic_values.popleft())

        def fake_sleep(_seconds):
            entrypoint.shutting_down = True

        monkeypatch.setattr(entrypoint, "interruptible_sleep", fake_sleep)

        entrypoint.main()

        assert self.health_states == [True, False]

    def test_later_success_restores_health_after_failure(self, monkeypatch):
        self._configure_env(monkeypatch)
        runs = deque([
            [("photos", "/data/photos", "/data/photos/.iceshelf/config")],
            [("photos", "/data/photos", "/data/photos/.iceshelf/config")],
        ])
        outcomes = deque([False, True])
        monkeypatch.setattr(entrypoint, "discover_targets", lambda _data_dir: runs.popleft())
        monkeypatch.setattr(entrypoint, "merge_configs", lambda *_args, **_kwargs: ("/tmp/merged.conf", False))
        monkeypatch.setattr(entrypoint, "run_iceshelf", lambda *_args, **_kwargs: outcomes.popleft())
        monotonic_values = deque([0.0, 1.0, 2.0, 10.0, 11.0, 12.0])
        monkeypatch.setattr(entrypoint.time, "monotonic", lambda: monotonic_values.popleft())

        sleep_calls = []

        def fake_sleep(_seconds):
            sleep_calls.append(True)
            if len(sleep_calls) == 1:
                return
            entrypoint.shutting_down = True

        monkeypatch.setattr(entrypoint, "interruptible_sleep", fake_sleep)

        entrypoint.main()

        assert self.health_states == [True, False, True]
