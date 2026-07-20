import os
import pytest

from importing import compute_destination

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
