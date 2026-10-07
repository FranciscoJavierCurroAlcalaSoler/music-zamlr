import importlib.metadata

import check_compiled_packages
from check_compiled_packages import (
    AUDITED_COMPILED,
    canonical_name,
    main,
    unaudited,
)

# Copied from installed WHEEL files (greenlet 3.5.3 and alembic 1.20.0 on
# Windows), not written from memory of the format.
COMPILED_WHEEL = (
    "Wheel-Version: 1.0\nGenerator: setuptools (82.0.1)\n"
    "Root-Is-Purelib: false\nTag: cp314-cp314-win_amd64\n\n"
)
PURE_WHEEL = (
    "Wheel-Version: 1.0\nGenerator: setuptools (84.0.0)\n"
    "Root-Is-Purelib: true\nTag: py3-none-any\n\n"
)


def _wheels(texts):
    return lambda name: texts[name]


def test_a_pure_package_needs_no_review():
    findings = unaudited(
        {"alembic": "1.20.0"}, _wheels({"alembic": PURE_WHEEL}), audited={}
    )

    assert findings == []


def test_a_compiled_package_off_the_list_is_reported():
    findings = unaudited(
        {"greenlet": "3.5.3"}, _wheels({"greenlet": COMPILED_WHEEL}), audited={}
    )

    assert len(findings) == 1
    assert "greenlet 3.5.3" in findings[0]


def test_a_compiled_package_at_another_version_is_reported():
    findings = unaudited(
        {"greenlet": "3.5.4"},
        _wheels({"greenlet": COMPILED_WHEEL}),
        audited={"greenlet": "3.5.3"},
    )

    assert len(findings) == 1
    assert "greenlet 3.5.4" in findings[0]
    assert "3.5.3" in findings[0]


def test_a_compiled_package_at_the_reviewed_version_passes():
    findings = unaudited(
        {"greenlet": "3.5.3"},
        _wheels({"greenlet": COMPILED_WHEEL}),
        audited={"greenlet": "3.5.3"},
    )

    assert findings == []


def test_a_package_with_no_wheel_file_counts_as_compiled():
    findings = unaudited({"oddity": "1.0"}, _wheels({"oddity": None}), audited={})

    assert len(findings) == 1
    assert "oddity 1.0" in findings[0]


def test_the_spelling_of_a_name_does_not_matter():
    # The list is written in normal form; the metadata may not be.
    findings = unaudited(
        {"MarkupSafe": "3.0.3", "pydantic_core": "2.46.4"},
        _wheels({"MarkupSafe": COMPILED_WHEEL, "pydantic_core": COMPILED_WHEEL}),
        audited={"markupsafe": "3.0.3", "pydantic-core": "2.46.4"},
    )

    assert findings == []


def test_main_fails_the_step_on_a_finding(monkeypatch, tmp_path):
    # The exit status is what stops the workflow. Printed findings with an
    # exit status of 0 would leave the run green.
    monkeypatch.setattr(
        check_compiled_packages,
        "bundled_distributions",
        lambda build_dir: {"newcomer": "1.0"},
    )

    assert main(tmp_path, _wheels({"newcomer": COMPILED_WHEEL})) == 1


def test_main_passes_the_step_with_no_finding(monkeypatch, tmp_path):
    monkeypatch.setattr(
        check_compiled_packages,
        "bundled_distributions",
        lambda build_dir: {"alembic": "1.20.0"},
    )

    assert main(tmp_path, _wheels({"alembic": PURE_WHEEL})) == 0


def test_the_audited_versions_are_the_installed_ones():
    """A requirements.txt bump of an audited package fails here, at push time.

    The build workflows run the real check, but only when a release is
    built. This environment is installed from requirements.txt, so a version
    that moved there without a review fails in CI on the same push.
    """
    installed = {
        canonical_name(name): importlib.metadata.version(name)
        for name in AUDITED_COMPILED
    }

    assert installed == AUDITED_COMPILED
