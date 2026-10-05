import pytest
from PyInstaller.compat import is_win

from stage_backend import BACKEND_NAME, BACKEND_PROGRAM, INTERNAL_DIR, stage_backend


@pytest.fixture
def layout(tmp_path):
    """A fresh build in dist/ and an older staged copy in binaries/."""
    dist_dir = tmp_path / "dist"
    (dist_dir / INTERNAL_DIR).mkdir(parents=True)
    (dist_dir / BACKEND_PROGRAM).write_text("new exe")
    (dist_dir / INTERNAL_DIR / "kept_module.pyd").write_text("new module")

    binaries_dir = tmp_path / "binaries"
    (binaries_dir / INTERNAL_DIR).mkdir(parents=True)
    (binaries_dir / BACKEND_PROGRAM).write_text("old exe")
    (binaries_dir / INTERNAL_DIR / "kept_module.pyd").write_text("old module")
    return dist_dir, binaries_dir


def test_staging_removes_what_the_new_build_lacks(layout):
    # A file only the old build had is the case a copy over the top misses:
    # everything else is replaced, so the staged folder looks current while
    # still carrying a module the backend no longer has.
    dist_dir, binaries_dir = layout
    (binaries_dir / INTERNAL_DIR / "old_module.pyd").write_text("gone")

    stage_backend(dist_dir, binaries_dir)

    assert not (binaries_dir / INTERNAL_DIR / "old_module.pyd").exists()
    assert (binaries_dir / INTERNAL_DIR / "kept_module.pyd").read_text() == (
        "new module"
    )
    assert (binaries_dir / BACKEND_PROGRAM).read_text() == "new exe"


def test_staging_leaves_fpcalc_alone(layout):
    # fpcalc.exe is staged once by hand and rebuilt by nothing, so a
    # staging step that cleared the whole folder would lose it for good.
    dist_dir, binaries_dir = layout
    (binaries_dir / "fpcalc.exe").write_text("fpcalc")

    stage_backend(dist_dir, binaries_dir)

    assert (binaries_dir / "fpcalc.exe").read_text() == "fpcalc"


def test_staging_without_a_build_says_how_to_make_one(tmp_path):
    with pytest.raises(FileNotFoundError, match="pyinstaller"):
        stage_backend(tmp_path / "missing", tmp_path / "binaries")


def test_the_staged_name_is_the_one_pyinstaller_writes():
    # Asks PyInstaller rather than os.name, which would only repeat the
    # expression under test. A wrong name is otherwise found when staging
    # fails in the release build, on the platform that has it wrong.
    assert BACKEND_PROGRAM == BACKEND_NAME + (".exe" if is_win else "")
