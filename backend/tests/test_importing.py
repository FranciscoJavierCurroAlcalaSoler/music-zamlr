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
        [make_track(file_path="/fake/path.mp3"),
         make_track(file_path="/fake/file/path.flac")],
        "/source_root",
        "/destination_root",
        "flat"
    )
    
    assert len(import_plan) == 2
    assert import_plan[0].source == "/fake/path.mp3"
    assert import_plan[1].source == "/fake/file/path.flac"
    assert import_plan[0].destination == os.path.normpath("/destination_root/path.mp3")
    assert import_plan[1].destination == os.path.normpath("/destination_root/path.flac")
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[1].action == ActionType.COPY