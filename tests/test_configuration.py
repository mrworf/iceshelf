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
skip broken links = yes
ignore unavailable files = yes
show delta = yes

[provider-cloud]
type = s3
bucket = backups
region = us-east-1
""", caplog=caplog)

        assert parsed is not None
        assert caplog.text == ""

    def test_warns_for_s3_prefix_option(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[provider-cloud]
type = s3
bucket = backups
prefix = archives
region = us-east-1
""", caplog=caplog)

        assert parsed is not None
        assert 'Unknown option "prefix" in [provider-cloud] for provider type "s3"' in caplog.text

    def test_does_not_warn_for_s3_storage_class_option(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[provider-cloud]
type = s3
bucket = backups
storage class = deep_archive
region = us-east-1
""", caplog=caplog)

        assert parsed is not None
        assert caplog.text == ""

    def test_does_not_warn_for_s3_create_option(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[provider-cloud]
type = s3
bucket = backups
create = yes
region = us-east-1
""", caplog=caplog)

        assert parsed is not None
        assert caplog.text == ""

    def test_does_not_warn_for_glacier_create_option(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[provider-cold]
type = glacier
vault = backups
create = no
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
    def test_missing_tar_binary_fails(self, valid_layout, caplog, monkeypatch):
        caplog.set_level(logging.ERROR)

        original_which = configuration.which

        def fake_which(program):
            if program == "tar":
                return None
            return original_which(program)

        monkeypatch.setattr(configuration, "which", fake_which)

        parsed = _parse(valid_layout, caplog=caplog)

        assert parsed is None
        assert "To create backups, you must have tar installed" in caplog.text

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

    def test_skip_broken_links_invalid_value_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        parsed = _parse(valid_layout, extra_sections="""
[options]
skip broken links = maybe
""", caplog=caplog)

        assert parsed is None
        assert "skip broken links has to be yes/no" in caplog.text

    def test_loop_slices_invalid_value_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        parsed = _parse(valid_layout, extra_sections="""
[options]
loop slices = maybe
""", caplog=caplog)

        assert parsed is None
        assert "loop slices has to be yes/no" in caplog.text

    def test_ignore_unavailable_files_invalid_value_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        parsed = _parse(valid_layout, extra_sections="""
[options]
ignore unavailable files = maybe
""", caplog=caplog)

        assert parsed is None
        assert "ignore unavailable files has to be yes/no" in caplog.text

    def test_tolerate_unreconcilable_files_invalid_value_fails(self, valid_layout, caplog):
        caplog.set_level(logging.ERROR)

        parsed = _parse(valid_layout, extra_sections="""
[options]
tolerate unreconcilable files = maybe
""", caplog=caplog)

        assert parsed is None
        assert "tolerate unreconcilable files has to be yes/no" in caplog.text


class TestParseOptions:
    def test_skip_broken_links_yes_parses_true(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
skip broken links = yes
""")

        assert parsed is not None
        assert parsed["skip-broken-links"] is True

    def test_skip_broken_links_no_parses_false(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
skip broken links = no
""")

        assert parsed is not None
        assert parsed["skip-broken-links"] is False

    def test_loop_slices_yes_parses_true(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
loop slices = yes
""")

        assert parsed is not None
        assert parsed["loop-slices"] is True

    def test_loop_slices_no_parses_false(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
loop slices = no
""")

        assert parsed is not None
        assert parsed["loop-slices"] is False

    def test_ignore_unavailable_files_yes_parses_true(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
ignore unavailable files = yes
""")

        assert parsed is not None
        assert parsed["ignore-unavailable-files"] is True

    def test_ignore_unavailable_files_no_parses_false(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
ignore unavailable files = no
""")

        assert parsed is not None
        assert parsed["ignore-unavailable-files"] is False

    def test_tolerate_unreconcilable_files_yes_parses_true(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
ignore unavailable files = yes
tolerate unreconcilable files = yes
""")

        assert parsed is not None
        assert parsed["tolerate-unreconcilable-files"] is True
        assert parsed["ignore-unavailable-files"] is True

    def test_tolerate_unreconcilable_files_no_parses_false(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
tolerate unreconcilable files = no
""")

        assert parsed is not None
        assert parsed["tolerate-unreconcilable-files"] is False

    def test_tolerate_without_ignore_warns_but_parses(self, valid_layout, caplog):
        caplog.set_level(logging.WARNING)

        parsed = _parse(valid_layout, extra_sections="""
[options]
ignore unavailable files = no
tolerate unreconcilable files = yes
""", caplog=caplog)

        assert parsed is not None
        assert parsed["tolerate-unreconcilable-files"] is True
        assert parsed["ignore-unavailable-files"] is False
        assert "tolerate unreconcilable files has no effect" in caplog.text

    def test_show_delta_yes_parses_true(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
show delta = yes
""")

        assert parsed is not None
        assert parsed["show-delta"] is True

    def test_show_delta_no_parses_false(self, valid_layout):
        parsed = _parse(valid_layout, extra_sections="""
[options]
show delta = no
""")

        assert parsed is not None
        assert parsed["show-delta"] is False


class TestExcludeRules:
    def test_parse_inlines_external_exclude_rules(self, valid_layout):
        exclude_rules = valid_layout["config"].parent / "exclude.rules"
        exclude_rules.write_text("# comment\n*.tmp\n^?/Mixed/Case/\n")

        parsed = _parse(valid_layout, extra_sections=f"""
[exclude]
exact file = {valid_layout["source"]}
external file = |{exclude_rules}
""")

        assert parsed is not None
        assert parsed["exclude"] == [
            str(valid_layout["source"]),
            "*.tmp",
            "^?/Mixed/Case/",
        ]

    def test_exact_rule_matches_full_path_only(self, valid_layout):
        configuration.setting["exclude"] = [str(valid_layout["source"])]

        assert configuration.isExcluded(str(valid_layout["source"])) is True
        assert configuration.isExcluded(str(valid_layout["source"]) + ".bak") is False

    def test_trailing_star_matches_prefix(self):
        configuration.setting["exclude"] = ["/tmp/report*"]

        assert configuration.isExcluded("/tmp/report-2026.txt") is True
        assert configuration.isExcluded("/tmp/other-report.txt") is False

    def test_leading_star_matches_suffix(self):
        configuration.setting["exclude"] = ["*.doc"]

        assert configuration.isExcluded("/tmp/readme.doc") is True
        assert configuration.isExcluded("/tmp/readme.doc.bak") is False

    def test_contains_match_supports_questionmark_and_star_forms(self):
        configuration.setting["exclude"] = ["?/.cache/", "*temp*"]

        assert configuration.isExcluded("/home/user/.cache/file.txt") is True
        assert configuration.isExcluded("/home/user/report-temp-file.txt") is True
        assert configuration.isExcluded("/home/user/report.txt") is False

    def test_case_insensitive_modifier_supports_flexible_prefix_order(self):
        configuration.setting["exclude"] = ["^?/MyFolder/", "*^.DOC"]

        assert configuration.isExcluded("/tmp/myfolder/file.txt") is True
        assert configuration.isExcluded("/tmp/report.doc") is True
        assert configuration.isExcluded("/tmp/report.DOCX") is False

    def test_invert_rule_still_uses_first_matching_rule(self):
        configuration.setting["exclude"] = ["!/tmp/keep-me.txt", "/tmp/*"]

        assert configuration.isExcluded("/tmp/keep-me.txt") is False
        assert configuration.isExcluded("/tmp/drop-me.txt") is True

    def test_literal_escaping_supports_special_characters(self):
        configuration.setting["exclude"] = [
            r"\*literal",
            r"prefix\*",
            r"\?question",
            r"\^caret",
            r"\!bang",
            r"slash\\name",
        ]

        assert configuration.isExcluded("*literal") is True
        assert configuration.isExcluded("prefix*") is True
        assert configuration.isExcluded("?question") is True
        assert configuration.isExcluded("^caret") is True
        assert configuration.isExcluded("!bang") is True
        assert configuration.isExcluded(r"slash\name") is True
        assert configuration.isExcluded("prefix-value") is False

    def test_escaped_leading_or_trailing_star_remains_literal(self):
        configuration.setting["exclude"] = [r"\*foo*", r"foo\*", r"\*foo\*"]

        assert configuration.isExcluded("*foobar") is True
        assert configuration.isExcluded("foo*") is True
        assert configuration.isExcluded("*foo*") is True
        assert configuration.isExcluded("foobar") is False

    def test_size_rules_continue_to_work(self, tmp_path):
        small = tmp_path / "small.txt"
        big = tmp_path / "big.txt"
        small.write_text("tiny")
        big.write_text("this is definitely longer")

        configuration.setting["exclude"] = [">10", "<5"]

        assert configuration.isExcluded(str(small)) is True
        assert configuration.isExcluded(str(big)) is True

    def test_invalid_size_rule_still_fails(self):
        configuration.setting["exclude"] = [">ten"]

        with pytest.raises(SystemExit):
            configuration.isExcluded("/tmp/example")
