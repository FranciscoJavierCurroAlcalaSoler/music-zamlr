import os
import pytest

from importing import compute_destination, plan_import, ActionType

def test_mirror_returns_mirrored_path(make_track):
    destination = compute_destination(
        make_track(file_path="/source_root/fake/path.mp3"),
        "/source_root",
        "/destination_root",
        "mirror"
    )
    
    assert destination == os.path.normpath("/destination_root/fake/path.mp3")


def test_flat_returns_basename_under_root(make_track):
    destination = compute_destination(
        make_track(file_path="/source_root/fake/path.mp3"),
        "/source_root",
        "/destination_root",
        "flat"
    )
    
    assert destination == os.path.normpath("/destination_root/path.mp3")


def test_unknown_raises_error(make_track):
    with pytest.raises(ValueError, match="Unknown structure mode"):
        compute_destination(
            make_track(file_path="/source_root/fake/path.mp3"),
            "/source_root",
            "/destination_root",
            "unknown_value"
        )


def test_plan_missing_tracks(make_track):
    import_plan = plan_import(
        [make_track(file_path="/source_root/path.mp3"),
         make_track(file_path="/source_root/file/path.flac")],
        "/source_root",
        "/destination_root",
        "flat"
    )
    
    assert len(import_plan) == 2
    assert import_plan[0].source == "/source_root/path.mp3"
    assert import_plan[1].source == "/source_root/file/path.flac"
    assert import_plan[0].destination == os.path.normpath("/destination_root/path.mp3")
    assert import_plan[1].destination == os.path.normpath("/destination_root/path.flac")
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[1].action == ActionType.COPY


def test_escaped_destination_path_raises_error(make_track):
    with pytest.raises(ValueError, match="escapes destination root"):
        plan_import(
            [make_track(file_path="/fake/path.mp3")],
            "/source_root",
            "/destination_root",
            "mirror"
        )


def test_sibling_prefix_destination_raises_error(make_track):
    # /destination_root vs /destination_root-backup: a string prefix but a
    # different directory. commonpath must reject it; startswith would not.
    with pytest.raises(ValueError, match="escapes destination root"):
        plan_import(
            [make_track(file_path="/destination_root-backup/evil.mp3")],
            "/destination_root",
            "/destination_root",
            "mirror",
        )


def test_name_disambiguation(make_track):
    import_plan = plan_import(
        [make_track(file_path="/source_root/one/path.mp3"),
         make_track(file_path="/source_root/two/path.mp3"),
         make_track(file_path="/source_root/three/path.mp3")],
        "/source_root",
        "/destination_root",
        "flat",
    )

    assert import_plan[0].destination == os.path.normpath("/destination_root/path.mp3")
    assert import_plan[1].destination == os.path.normpath("/destination_root/path (1).mp3")
    assert import_plan[2].destination == os.path.normpath("/destination_root/path (2).mp3")


def test_case_insensitive_names_disambiguate(make_track):
    # PATH.mp3 and path.mp3 are distinct strings but the same file on a
    # case-insensitive Windows drive, so the second must be disambiguated.
    import_plan = plan_import(
        [make_track(file_path="/source_root/one/PATH.mp3"),
         make_track(file_path="/source_root/two/path.mp3")],
        "/source_root",
        "/destination_root",
        "flat",
    )

    assert import_plan[0].destination == os.path.normpath("/destination_root/PATH.mp3")
    assert import_plan[1].destination == os.path.normpath("/destination_root/path (1).mp3")