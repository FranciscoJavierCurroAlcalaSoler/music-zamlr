from sqlmodel import SQLModel, UniqueConstraint, Field, Relationship

class Collection (SQLModel, table=True):
  id: int | None = Field(default=None, primary_key=True)
  name: str = Field(unique=True, index=True)
  root_path: str
  last_scanned_at: str | None = None
  tracks: list["Track"] = Relationship(
    back_populates="collection",
    sa_relationship_kwargs={"cascade": "all, delete-orphan"}
  )

class Track (SQLModel, table=True):
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
  file_hash: str
  collection_id: int = Field(foreign_key="collection.id")
  collection: Collection = Relationship(back_populates="tracks")