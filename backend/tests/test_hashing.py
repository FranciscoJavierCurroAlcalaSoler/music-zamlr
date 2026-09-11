from hashing import compute_file_hash


def test_a_missing_file_has_no_hash(tmp_path):
    result = compute_file_hash(str(tmp_path / "missing.mp3"))

    assert result is None


def test_a_directory_has_no_hash(tmp_path):
    result = compute_file_hash(str(tmp_path))

    assert result is None
