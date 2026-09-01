import os
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from enums import (
    ActionType,
    Bucket,
    ImportPhase,
    OperationStatus,
    StructureMode,
    UpgradeAction,
)


class TrackRead(BaseModel):
    id: int
    file_path: str
    # Exposed because the UI needs to tell two candidates apart, and tracks
    # that land in the same review group matched each other on artist and
    # title — so the file name is the only field that distinguishes them.
    file_name: str
    artist: str | None = None
    album: str | None = None
    title: str | None = None
    track_number: int | None = None
    year: int | None = None
    format: str | None = None
    bit_rate: int | None = None
    sample_rate: int | None = None
    duration: int | None = None
    collection_id: int

    model_config = ConfigDict(from_attributes=True)


class CollectionRead(BaseModel):
    id: int
    name: str
    root_path: str
    last_scanned_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MatchRead(BaseModel):
    mine: TrackRead
    theirs: TrackRead

    model_config = ConfigDict(from_attributes=True)


class ReviewCandidateRead(BaseModel):
    mine: TrackRead
    would_be: Bucket

    model_config = ConfigDict(from_attributes=True)


class AmbiguousMatchRead(BaseModel):
    theirs: TrackRead
    candidates: list[ReviewCandidateRead]

    model_config = ConfigDict(from_attributes=True)


class MatchResultRead(BaseModel):
    missing: list[TrackRead] = []
    upgrade_available: list[MatchRead] = []
    already_have: list[MatchRead] = []
    needs_review: list[AmbiguousMatchRead] = []
    only_in_mine: list[TrackRead] = []

    model_config = ConfigDict(from_attributes=True)


class DiffResultRead(BaseModel):
    match_results: MatchResultRead
    match_counts: dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class PlannedOperationRead(BaseModel):
    source: str
    destination: str | None
    action: ActionType
    group_id: int
    overwrites: bool

    model_config = ConfigDict(from_attributes=True)


class OperationResultRead(BaseModel):
    operation: PlannedOperationRead
    status: OperationStatus
    error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ImportPreviewRead(BaseModel):
    operations: list[PlannedOperationRead]
    upgrades: list[MatchRead] = []
    operation_counts: dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class TrackResolution(BaseModel):
    theirs_id: int
    mine_id: int | None

    model_config = ConfigDict(from_attributes=True)


class ImportRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1)
    mine_collection_id: int
    theirs_collection_id: int
    destination_root: str
    structure_mode: StructureMode
    upgrade_action: UpgradeAction
    resolutions: list[TrackResolution] = []

    @field_validator("destination_root")
    @classmethod
    def normalize_destination_root(cls, value: str) -> str:
        # Normalizing here rather than in the endpoint because two functions
        # read this field, and normalizing in one would leave the other with
        # the raw string. normpath is pure string manipulation, so the schema
        # still needs no filesystem to be tested.
        #
        # The empty check must come first: normpath("") is ".", which is a
        # real writable directory, so an empty root would pass the endpoint's
        # isdir and access checks and import into the server's working
        # directory instead of failing.
        #
        # strip() before normpath, because normpath does not remove
        # surrounding whitespace. A trailing space is the dangerous one:
        # Win32 strips it per component, so isdir and access both pass and
        # the padding rides along into every computed destination, the
        # preview, and the log path. Linux keeps it, so the same request
        # 400s there instead.
        stripped = value.strip()
        if not stripped:
            raise ValueError("destination_root must not be empty")
        return os.path.normpath(stripped)


class ImportResultRead(BaseModel):
    operations: list[OperationResultRead]
    status_counts: dict[str, int]
    log_path: str | None = None
    log_error: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ScanRequest(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    root_path: str

    @field_validator("root_path")
    @classmethod
    def normalize_root_path(cls, value: str) -> str:
        # Normalizing here rather than in the endpoint because two functions
        # read this field, and normalizing in one would leave the other with
        # the raw string. normpath is pure string manipulation, so the schema
        # still needs no filesystem to be tested.
        #
        # The empty check must come first: normpath("") is ".", which is a
        # real writable directory, so an empty root would pass the endpoint's
        # isdir and access checks and import into the server's working
        # directory instead of failing.
        #
        # strip() before normpath, because normpath does not remove
        # surrounding whitespace. A trailing space is the dangerous one:
        # Win32 strips it per component, so isdir and access both pass and
        # the padding rides along into every computed destination, the
        # preview, and the log path. Linux keeps it, so the same request
        # 400s there instead.
        stripped = value.strip()
        if not stripped:
            raise ValueError("root_path must not be empty")
        return os.path.normpath(stripped)


class ScanProgressRead(BaseModel):
    # The running counts only. The accumulated lists stay on ScanResultRead:
    # progress is a state the stream overwrites, and a log would then travel
    # twice. current_path is the file being read at that moment, so it is the
    # one field with no counterpart in the result.
    scanned: int
    added: int
    updated: int
    deleted: int
    skipped_non_audio: int
    matched: int
    current_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DiffProgressRead(BaseModel):
    theirs_processed_count: int
    theirs_count: int
    hashed_count: int
    current_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ImportProgressRead(BaseModel):
    phase: ImportPhase
    processed_count: int
    total_count: int
    current_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ScanResultRead(BaseModel):
    scanned: int
    added: int
    updated: int
    deleted: int
    skipped_non_audio: int
    matched: int
    # unreadable_directories is not just a count of problems: rows beneath
    # these paths were deliberately not deleted, so a client that reports
    # deleted=0 without also reporting these is describing a partial scan as
    # a clean one.
    unreadable_files: list[str] = []
    unreadable_directories: list[str] = []
    collection: CollectionRead

    model_config = ConfigDict(from_attributes=True)
