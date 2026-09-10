from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint


class Collection(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    root_path: str
    last_scanned_at: str | None = None
    tracks: list["Track"] = Relationship(
        back_populates="collection",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Track(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("collection_id", "file_path"),)
    id: int | None = Field(default=None, primary_key=True)
    file_path: str = Field(index=True)
    file_name: str
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    track_number: int | None = None
    year: int | None = None
    format: str | None = None
    bit_depth: int | None = None
    bit_rate: int
    sample_rate: int
    duration: int
    file_size: int
    file_hash: str | None = None
    # Three columns that move together or not at all. The two producer
    # columns record which fpcalc settings made the bytes, and the matcher
    # trusts stored bytes only when both equal the settings in use now. Bytes
    # with no producer — every row written before these columns existed —
    # therefore read as stale and refill on the next diff, which is the
    # intended migration rather than an oversight.
    fingerprint: bytes | None = None
    fingerprint_algorithm: int | None = None
    fingerprint_length: int | None = None
    collection_id: int = Field(foreign_key="collection.id")
    collection: Collection = Relationship(back_populates="tracks")
