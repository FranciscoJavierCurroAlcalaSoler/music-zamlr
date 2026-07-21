import os
from dataclasses import dataclass
from enum import StrEnum

from models import Track


class ActionType(StrEnum):
    COPY = "copy"


@dataclass
class PlannedOperation:
    source: str
    destination: str
    action: ActionType


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


def plan_import(
    tracks: list[Track],
    source_root: str,
    destination_root: str,
    structure_mode: str,
) -> list[PlannedOperation]:
    planned_operations = []
    for track in tracks:
        normalized_root = os.path.normpath(destination_root)
        destination_path = compute_destination(track, source_root, destination_root, structure_mode)
        if os.path.commonpath([destination_path, normalized_root]) != normalized_root:
            raise ValueError(
                f"Destination {destination_path!r} escapes destination root {destination_root!r}"
            )
        planned_operations.append(PlannedOperation(
            source=track.file_path,
            destination=destination_path,
            action=ActionType.COPY
        ))
    return planned_operations