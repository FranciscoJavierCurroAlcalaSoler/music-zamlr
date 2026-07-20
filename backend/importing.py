import os

from models import Track


def compute_destination(
        track: Track,
        source_root: str,
        destination_root: str,
        structure_mode: str
) -> str:
    if structure_mode == "mirror":
        relative_path = os.path.relpath(track.file_path, source_root)
    elif structure_mode == "flat":
        relative_path = os.path.basename(track.file_path)
    else:
        raise ValueError(f"Unknown structure mode: {structure_mode!r}")

    return os.path.normpath(os.path.join(destination_root, relative_path))