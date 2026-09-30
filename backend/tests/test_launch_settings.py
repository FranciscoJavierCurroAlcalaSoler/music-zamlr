import os
import re

import pytest

from launch_settings import (
    ALLOWED_ORIGINS_VARIABLE,
    DATABASE_PATH_VARIABLE,
    FPCALC_PATH_VARIABLE,
    TOKEN_VARIABLE,
    read_launch_settings,
)


def test_origins_default_to_the_vite_dev_server():
    assert read_launch_settings({}).allowed_origins == ("http://localhost:5173",)


def test_origins_are_split_on_commas_and_stripped():
    assert read_launch_settings(
        {ALLOWED_ORIGINS_VARIABLE: "http://localhost:5173, https://example.com"}
    ).allowed_origins == ("http://localhost:5173", "https://example.com")


@pytest.mark.parametrize(
    "value, rule",
    [
        ("", "contains an empty origin entry"),
        (",,", "contains an empty origin entry"),
        ("*", re.escape("must not contain '*'")),
        ("http://localhost:5173/", "origin must not end with '/'"),
    ],
    ids=["empty", "empty-entry", "wildcard", "trailing-slash"],
)
def test_a_bad_origin_list_is_refused(value, rule):
    with pytest.raises(ValueError, match=rule):
        read_launch_settings({ALLOWED_ORIGINS_VARIABLE: value})


def test_a_refusal_names_the_variable():
    with pytest.raises(ValueError, match=ALLOWED_ORIGINS_VARIABLE):
        read_launch_settings({ALLOWED_ORIGINS_VARIABLE: "*"})


def test_the_token_is_absent_by_default():
    assert read_launch_settings({}).token is None


def test_the_token_is_read_from_the_environment():
    assert (
        read_launch_settings({TOKEN_VARIABLE: "secret-token"}).token == "secret-token"
    )


@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "blank"])
def test_an_empty_token_is_refused(value):
    with pytest.raises(ValueError, match=re.escape(TOKEN_VARIABLE)):
        read_launch_settings({TOKEN_VARIABLE: value})


def test_the_database_path_is_absent_by_default():
    assert read_launch_settings({}).database_path is None


def test_the_database_path_is_read_and_normalized(tmp_path):
    # From tmp_path, because it is absolute on every operating system. A
    # literal like "c:\\db\\music.db" is absolute on Windows and relative
    # everywhere else, so this test would refuse its own input in CI.
    path = os.path.join(str(tmp_path), "music", "..", "music.db")
    expected = os.path.normpath(path)
    assert (
        read_launch_settings({DATABASE_PATH_VARIABLE: path}).database_path == expected
    )


def test_a_relative_database_path_is_refused():
    # Matched on the rule, not on the variable name, which every message in
    # this module carries. An empty path is refused by a different rule, and
    # a test that matched the name alone would pass whichever one fired.
    with pytest.raises(ValueError, match="must be an absolute path"):
        read_launch_settings({DATABASE_PATH_VARIABLE: os.path.join("db", "music.db")})


@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "blank"])
def test_an_empty_database_path_is_refused(value):
    # "contains an empty path", not the variable name: an empty string is not
    # absolute either, so the rule below would refuse it and this test would
    # pass with its own rule deleted.
    with pytest.raises(ValueError, match="contains an empty path"):
        read_launch_settings({DATABASE_PATH_VARIABLE: value})


def test_the_fpcalc_path_is_absent_by_default():
    assert read_launch_settings({}).fpcalc_path is None


def test_the_fpcalc_path_is_read_and_normalized(tmp_path):
    path = os.path.join(str(tmp_path), "fpcalc", "..", "fpcalc")
    expected = os.path.normpath(path)
    assert read_launch_settings({FPCALC_PATH_VARIABLE: path}).fpcalc_path == expected


def test_a_relative_fpcalc_path_is_refused():
    with pytest.raises(ValueError, match="must be an absolute path"):
        read_launch_settings({FPCALC_PATH_VARIABLE: os.path.join("bin", "fpcalc")})


@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "blank"])
def test_an_empty_fpcalc_path_is_refused(value):
    with pytest.raises(ValueError, match="contains an empty path"):
        read_launch_settings({FPCALC_PATH_VARIABLE: value})
