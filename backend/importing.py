import os
from dataclasses import dataclass
from enum import StrEnum
from itertools import count

from enums import StructureMode, UpgradeAction
from matching import Match
from models import Track

SUPERSEDED_DIR_NAME = "_superseded"


class ActionType(StrEnum):
    COPY = "copy"
    DELETE = "delete"
    MOVE = "move"


@dataclass
class PlannedOperation:
    source: str
    destination: str | None
    action: ActionType
    group_id: int


def compute_destination(
    track: Track, source_root: str, destination_root: str, structure_mode: StructureMode
) -> str:
    if structure_mode == StructureMode.MIRROR:
        relative_path = os.path.relpath(track.file_path, source_root)
    elif structure_mode == StructureMode.FLAT:
        relative_path = os.path.basename(track.file_path)
    else:
        raise ValueError(f"Unknown structure mode: {structure_mode!r}")

    return os.path.normpath(os.path.join(destination_root, relative_path))


def _disambiguate(destination: str, seen_destinations: set[str]) -> str:
    if destination.casefold() not in seen_destinations:
        return destination
    base, ext = os.path.splitext(destination)
    n = 1
    while f"{base} ({n}){ext}".casefold() in seen_destinations:
        n += 1
    return f"{base} ({n}){ext}"


def _register(destination: str, seen_destinations: set[str]) -> str:
    destination = _disambiguate(destination, seen_destinations)
    seen_destinations.add(destination.casefold())
    return destination


def plan_import(
    missing: list[Track],
    upgrades: list[Match],
    source_root: str,
    destination_root: str,
    structure_mode: StructureMode,
    upgrade_action: UpgradeAction,
) -> list[PlannedOperation]:
    # Comparisons below use == / != rather than identity, so a raw string
    # ("delete") works as well as an UpgradeAction member. Don't switch to
    # 'is' without coercing upgrade_action to a member first.
    if upgrade_action not in UpgradeAction:
        raise ValueError(f"Unknown upgrade action: {upgrade_action!r}")

    normalized_root = os.path.normpath(destination_root)
    seen_destinations: set[str] = set()
    operations: list[PlannedOperation] = []
    group_ids = count()

    def plan_copy(track: Track, group_id: int) -> PlannedOperation:
        destination = compute_destination(
            track, source_root, destination_root, structure_mode
        )
        if os.path.commonpath([destination, normalized_root]) != normalized_root:
            raise ValueError(
                f"Destination {destination!r} escapes destination root {normalized_root!r}"
            )
        destination = _register(destination, seen_destinations)
        return PlannedOperation(
            source=track.file_path,
            destination=destination,
            action=ActionType.COPY,
            group_id=group_id,
        )

    def plan_move(track: Track, group_id: int) -> PlannedOperation:
        destination = os.path.normpath(
            os.path.join(
                destination_root, SUPERSEDED_DIR_NAME, os.path.basename(track.file_path)
            )
        )
        destination = _register(destination, seen_destinations)
        return PlannedOperation(
            source=track.file_path,
            destination=destination,
            action=ActionType.MOVE,
            group_id=group_id,
        )

    for track in missing:
        group_id = next(group_ids)
        operations.append(plan_copy(track, group_id))

    for match in upgrades:
        group_id = next(group_ids)
        copy_operation = plan_copy(match.theirs, group_id)

        # An in-place upgrade overwrites mine's own file. Deleting that path
        # afterwards would remove the copy we just wrote.
        replaced_in_place = (
            copy_operation.destination.casefold()
            == os.path.normpath(match.mine.file_path).casefold()
        )

        if upgrade_action == UpgradeAction.MOVE:
            move_operation = plan_move(match.mine, group_id)
            if replaced_in_place:
                operations.extend([move_operation, copy_operation])
            else:
                operations.extend([copy_operation, move_operation])
            continue

        operations.append(copy_operation)

        if upgrade_action == UpgradeAction.DELETE and not replaced_in_place:
            operations.append(
                PlannedOperation(
                    source=match.mine.file_path,
                    destination=None,
                    action=ActionType.DELETE,
                    group_id=group_id,
                )
            )

    return operations
