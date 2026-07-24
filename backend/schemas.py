from pydantic import BaseModel, ConfigDict, Field

from enums import ActionType, StructureMode, UpgradeAction


class TrackRead(BaseModel):
    id: int
    file_path: str
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


class MatchResultRead(BaseModel):
    missing: list[TrackRead] = []
    upgrade_available: list[MatchRead] = []
    already_have: list[MatchRead] = []
    needs_review: list[TrackRead] = []
    only_in_mine: list[TrackRead] = []

    model_config = ConfigDict(from_attributes=True)


class DiffRead(BaseModel):
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


class ImportPreviewRead(BaseModel):
    operations: list[PlannedOperationRead]
    operation_counts: dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class ImportRequest(BaseModel):
    track_ids: list[int] = Field(min_length=1)
    mine_collection_id: int
    theirs_collection_id: int
    destination_root: str
    structure_mode: StructureMode
    upgrade_action: UpgradeAction
