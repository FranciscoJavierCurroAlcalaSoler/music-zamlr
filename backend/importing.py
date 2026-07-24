"""Import planning and execution.

Two halves, deliberately kept apart:

- ``plan_import`` computes what *would* happen and writes nothing, so the
  dry-run preview is simply the plan itself. There is no ``dry_run`` flag
  threaded through the executor for some future branch to forget.
- ``execute_plan`` runs a plan against the filesystem.

The plan is an *ordered* list, and the order is the safety mechanism rather
than a formatting detail: a destructive operation is positioned so it only
runs once its replacement is safely in place. See spec §5b for the full
rationale, including why the in-place upgrade inverts the usual order.
"""

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from itertools import count

from enums import ActionType, StructureMode, UpgradeAction
from matching import Match
from models import Track

SUPERSEDED_DIR_NAME = "_superseded"


@dataclass
class PlannedOperation:
    source: str
    destination: str | None
    action: ActionType
    group_id: int
    overwrites: bool = False


class OperationStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class OperationResult:
    operation: PlannedOperation
    status: OperationStatus
    error: str | None = None


def compute_destination(
    track: Track, source_root: str, destination_root: str, structure_mode: StructureMode
) -> str:
    """Compute where a single track would land under ``destination_root``.

    Pure path math: no disk access and no collision handling, since
    detecting a collision needs cross-track state that only the planner
    has. Mirror preserves the track's layout relative to its own collection
    root; flat drops it under the root by basename.

    An unknown mode raises rather than returning a silently wrong path, and
    a cross-drive ``relpath`` is left to raise on its own. A same-drive path
    outside ``source_root`` returns a ``..`` path without raising; catching
    that escape is the planner's containment guard, not this function's.
    """
    if structure_mode == StructureMode.MIRROR:
        relative_path = os.path.relpath(track.file_path, source_root)
    elif structure_mode == StructureMode.FLAT:
        relative_path = os.path.basename(track.file_path)
    else:
        raise ValueError(f"Unknown structure mode: {structure_mode!r}")

    return os.path.normpath(os.path.join(destination_root, relative_path))


def _disambiguate(
    destination: str,
    seen_destinations: set[str],
    path_exists: Callable[[str], bool],
    allow_path: str | None,
) -> str:
    """Return ``destination``, or the first free " (n)" variant of it.

    A path counts as taken if this plan already claimed it or a file is
    already sitting there. ``allow_path`` waives only the second check, for
    the one file an in-place upgrade deliberately replaces.
    """

    def path_used(candidate: str) -> bool:
        # Casefold for comparisons only: the target filesystem is
        # case-insensitive, so Song.mp3 and song.mp3 are the same file. But
        # path_exists talks to the real filesystem, so it gets the
        # original-case path; handing it a folded path breaks the check on
        # case-sensitive systems.
        folded = candidate.casefold()
        # Scoped to one exact path, and it waives the disk check only. If
        # the plan itself already claimed this path, we still disambiguate.
        if allow_path is not None and folded == allow_path.casefold():
            return folded in seen_destinations
        return folded in seen_destinations or path_exists(candidate)

    if not path_used(destination):
        return destination
    # splitext so the suffix lands before the extension (song (1).mp3),
    # not after it.
    base, ext = os.path.splitext(destination)
    n = 1
    # The loop condition needs the same compound check: a candidate bumped
    # to (1) may itself be claimed or already on disk.
    while path_used(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def _register(
    destination: str,
    seen_destinations: set[str],
    path_exists: Callable[[str], bool],
    allow_path: str | None = None,
) -> str:
    """Disambiguate a destination and record it as claimed."""
    destination = _disambiguate(destination, seen_destinations, path_exists, allow_path)
    # Store the resolved name, not the original: otherwise a third
    # colliding track would generate (1) again instead of (2).
    seen_destinations.add(destination.casefold())
    return destination


def plan_import(
    missing: list[Track],
    upgrades: list[Match],
    source_root: str,
    destination_root: str,
    structure_mode: StructureMode,
    upgrade_action: UpgradeAction,
    path_exists: Callable[[str], bool] = os.path.exists,
) -> list[PlannedOperation]:
    """Turn selected tracks into an ordered list of planned operations.

    Every track in ``missing`` is copied in. Every pair in ``upgrades``
    copies theirs in and then, per ``upgrade_action``, deletes or moves
    aside mine's replaced file.

    ``path_exists`` is injected so the planner stays fast and testable
    without a filesystem, and so tests don't inherit the host OS's
    case-sensitivity, which differs between Windows and Linux CI.

    Note this checks the disk at plan time, so a file appearing between
    preview and execution is not caught (see spec §12).
    """
    # Comparisons below use == / != rather than identity, so a raw string
    # ("delete") works as well as an UpgradeAction member. Don't switch to
    # 'is' without coercing upgrade_action to a member first.
    if upgrade_action not in UpgradeAction:
        raise ValueError(f"Unknown upgrade action: {upgrade_action!r}")

    normalized_root = os.path.normpath(destination_root)
    # One shared set for the whole plan: a missing track and an upgrade's
    # incoming copy can share a basename in flat mode, so they must
    # disambiguate against each other. Two sets would let them collide.
    seen_destinations: set[str] = set()
    operations: list[PlannedOperation] = []
    # One continuous counter across both buckets. Numbering each bucket
    # from zero would collide their ids, and the executor would then skip
    # an unrelated upgrade when a missing copy failed.
    group_ids = count()

    def plan_copy(
        track: Track, group_id: int, allow_path: str | None = None
    ) -> PlannedOperation:
        destination = compute_destination(
            track, source_root, destination_root, structure_mode
        )
        # Containment runs on the pre-disambiguation path: disambiguation
        # only changes the filename within the same directory, so contained
        # stays contained, and an escape fails fast with the path the user
        # would recognize. commonpath, not startswith, so a sibling like
        # /root-backup can't masquerade as being inside /root.
        if os.path.commonpath([destination, normalized_root]) != normalized_root:
            raise ValueError(
                f"Destination {destination!r} escapes destination root {normalized_root!r}"
            )
        destination = _register(destination, seen_destinations, path_exists, allow_path)
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
        # No allow_path here: _superseded accumulates across runs, so a
        # file an earlier import parked there must not be overwritten.
        destination = _register(destination, seen_destinations, path_exists)
        return PlannedOperation(
            source=track.file_path,
            destination=destination,
            action=ActionType.MOVE,
            group_id=group_id,
        )

    for track in missing:
        group_id = next(group_ids)
        # No allow_path: a missing track must never target an existing file.
        operations.append(plan_copy(track, group_id))

    for match in upgrades:
        group_id = next(group_ids)
        # mine's own file is the one existing path this copy may claim,
        # because replacing it is exactly what the user asked for.
        copy_operation = plan_copy(
            match.theirs, group_id, os.path.normpath(match.mine.file_path)
        )

        # An in-place upgrade overwrites mine's own file. Deleting that path
        # afterwards would remove the copy we just wrote. Both sides are
        # normalized here rather than trusting the scanner to have done it,
        # since this guard is what stands between the user and data loss.
        replaced_in_place = (
            copy_operation.destination.casefold()
            == os.path.normpath(match.mine.file_path).casefold()
        )
        if replaced_in_place:
            # The only case where the plan knowingly destroys existing
            # data, so the dry-run preview can say so.
            copy_operation.overwrites = True

        if upgrade_action == UpgradeAction.MOVE:
            move_operation = plan_move(match.mine, group_id)
            if replaced_in_place:
                # Move first: copying first would overwrite mine's file,
                # and the move would then relocate the freshly written
                # upgrade into the graveyard. A move is non-destructive, so
                # vacating the path first is safe.
                operations.extend([move_operation, copy_operation])
            else:
                operations.extend([copy_operation, move_operation])
            continue

        # Appended outside the action branches so a future action can't
        # silently drop the copy.
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


def _copy(source: str, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    # Temp file lives in the destination's own directory because os.replace
    # is atomic only within a volume; %TEMP% may be on another drive. A
    # copy2 that dies halfway leaves the mess here, never at the real path.
    temp_path = destination + ".tmp"
    try:
        # copy2, not copy: preserves mtime, which carries meaning in a
        # music library. os.replace, not os.rename: rename raises on
        # Windows when the target exists.
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    except OSError:
        try:
            os.remove(temp_path)
        except OSError:
            pass  # best effort; report the original failure, not the cleanup's
        raise


def _move(source: str, destination: str) -> None:
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    # shutil.move, not os.rename: _superseded sits under destination_root
    # but mine's file may be on another drive, and rename fails across
    # volumes. shutil.move falls back to copy-then-delete there, which
    # works but is not atomic.
    shutil.move(source, destination)


def _perform(operation: PlannedOperation) -> None:
    # DELETE first and return early: it's the one action with no
    # destination, so handling it here lets the check below narrow the type
    # for everything after it.
    if operation.action == ActionType.DELETE:
        os.remove(operation.source)
        return

    # ValueError, not OSError, and so deliberately not caught by
    # execute_plan: a missing destination is a planner bug, not a
    # filesystem problem, and recording it as a per-operation failure would
    # hide the real defect behind a plausible-looking result row.
    if operation.destination is None:
        raise ValueError(f"{operation.action} operation requires a destination")

    if operation.action == ActionType.COPY:
        _copy(operation.source, operation.destination)
    elif operation.action == ActionType.MOVE:
        _move(operation.source, operation.destination)
    else:
        raise ValueError(f"Invalid action value: {operation.action!r}")


def execute_plan(operations: list[PlannedOperation]) -> list[OperationResult]:
    """Run a plan in order, returning one result per operation.

    Failures are per-operation rather than fatal: an OSError (a file locked
    by a player, a missing source, the Windows path-length limit) marks
    that operation FAILED, marks the rest of its group SKIPPED, and lets
    the run continue with the next group.

    The group rule is what enforces "destroy the old file only if the new
    copy succeeded". Inferring that dependency from list position would
    break on the in-place move case, where the destructive operation
    deliberately comes first.
    """
    results: list[OperationResult] = []
    failed_groups: set[int] = set()

    for operation in operations:
        if operation.group_id in failed_groups:
            results.append(OperationResult(operation, OperationStatus.SKIPPED))
            continue
        try:
            _perform(operation)
        # OSError, never bare Exception: a bare except would swallow bugs
        # in this module and record them as filesystem failures.
        except OSError as error:
            failed_groups.add(operation.group_id)
            results.append(
                OperationResult(operation, OperationStatus.FAILED, str(error))
            )
        else:
            results.append(OperationResult(operation, OperationStatus.SUCCESS))

    return results
