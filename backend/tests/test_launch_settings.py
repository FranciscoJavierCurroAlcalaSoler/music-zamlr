import re

import pytest

from launch_settings import ALLOWED_ORIGINS_VARIABLE, read_launch_settings


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
