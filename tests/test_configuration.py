"""Unit tests for modules/configuration.py."""

import copy
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from modules import configuration


BASE_SETTING = copy.deepcopy(configuration.setting)


@pytest.fixture(autouse=True)
def reset_configuration_state():
    configuration.setting = copy.deepcopy(BASE_SETTING)


def _write_conf(path, text):
    path.write_text(text)


@pytest.fixture()
def valid_layout(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("hello")

    prep = tmp_path / "prep"
    data = tmp_path / "data"
    done = tmp_path / "done"
    prep.mkdir()
    data.mkdir()
    done.mkdir()

    return {
        "source": source,
        "prep": prep,
        "data": data,
        "done": done,
        "config": tmp_path / "iceshelf.conf",
    }


def _base_config(layout):
    return f"""
[sources]
source = {layout["source"]}

[paths]
prep dir = {layout["prep"]}
data dir = {layout["data"]}
done dir = {layout["done"]}
""".strip() + "\n"


def _render_config(layout, sources_extra="", paths_extra="", extra_sections=""):
    config_text = f"""
[sources]
source = {layout["source"]}
{sources_extra}

[paths]
prep dir = {layout["prep"]}
data dir = {layout["data"]}
done dir = {layout["done"]}
{paths_extra}
""".strip() + "\n"
    if extra_sections:
        config_text += "\n" + extra_sections.strip() + "\n"
    return config_text


def _parse(layout, sources_extra="", paths_extra="", extra_sections="", caplog=None):
    config_text = _render_config(
        layout,
        sources_extra=sources_extra,
        paths_extra=paths_extra,
        extra_sections=extra_sections,
    )
    _write_conf(layout["config"], config_text)
    if caplog is not None:
        caplog.clear()
    return configuration.parse(str(layout["config"]))


class TestParseWarnings:
    def test_warns_unknown_option_in_paths(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, paths_extra="cretae paths = yes", caplog=caplog)

        assert parsed is not None
        assert 'Unknown option "cretae paths" in [paths]' in caplog.text

    def test_warns_unknown_option_in_options(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[options]
compres = yes
""", caplog=caplog)

        assert parsed is not None
        assert 'Unknown option "compres" in [options]' in caplog.text

    def test_warns_unknown_section(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[securty]
encrypt = nobody@example.com
""", caplog=caplog)

        assert parsed is not None
        assert 'Unknown section [securty]' in caplog.text

    def test_warns_unknown_provider_option(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[provider-cloud]
type = s3
bucket = backups
bukcet = typo
""", caplog=caplog)

        assert parsed is not None
        assert 'Unknown option "bukcet" in [provider-cloud] for provider type "s3"' in caplog.text

    def test_does_not_warn_for_valid_known_options(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[options]
compress = no

[provider-cloud]
type = s3
bucket = backups
prefix = archives
region = us-east-1
""", caplog=caplog)

        assert parsed is not None
        assert caplog.text == ""

    def test_does_not_warn_for_dynamic_sources_or_exclude_keys(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        exclude_rules = valid_layout["config"].parent / "exclude.rules"
        exclude_rules.write_text("# comment\n*.tmp\n")

        parsed = _parse(valid_layout, sources_extra=f"""
my source = {valid_layout["source"]}
""", extra_sections=f"""
[exclude]
named rule = *.log
external file = |{exclude_rules}
""", caplog=caplog)

        assert parsed is not None
        assert caplog.text == ""


class TestParseErrors:
    def test_missing_sources_still_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        _write_conf(valid_layout["config"], f"""
[paths]
prep dir = {valid_layout["prep"]}
data dir = {valid_layout["data"]}
done dir = {valid_layout["done"]}
""".strip() + "\n")

        parsed = configuration.parse(str(valid_layout["config"]))

        assert parsed is None
        assert "You don't have any sources defined" in caplog.text

    def test_deprecated_glacier_section_still_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        parsed = _parse(valid_layout, extra_sections="""
[glacier]
vault = old-style
""", caplog=caplog)

        assert parsed is None
        assert 'The [glacier] section is no longer supported.' in caplog.text

    def test_provider_missing_type_still_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        parsed = _parse(valid_layout, extra_sections="""
[provider-cloud]
bucket = backups
""", caplog=caplog)

        assert parsed is None
        assert 'Provider section provider-cloud must contain a type option' in caplog.text
