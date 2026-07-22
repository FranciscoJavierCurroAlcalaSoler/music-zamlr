from enum import StrEnum


class StructureMode(StrEnum):
    MIRROR = "mirror"
    FLAT = "flat"


class UpgradeAction(StrEnum):
    DELETE = "delete"
    KEEP_BOTH = "keep_both"
    MOVE = "move"
