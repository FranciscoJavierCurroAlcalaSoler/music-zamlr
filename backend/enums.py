from enum import StrEnum


class StructureMode(StrEnum):
    MIRROR = "mirror"
    FLAT = "flat"


class UpgradeAction(StrEnum):
    DELETE = "delete"
    KEEP_BOTH = "keep_both"
    MOVE = "move"


# UpgradeAction and ActionType deliberately share the strings "delete" and
# "move" but are not interchangeable: one is what the user asked for, the
# other is what an operation does. Because StrEnum members compare equal to
# their value, ActionType.DELETE == UpgradeAction.DELETE is True and passes
# plan_import's membership guard, so a mix-up fails silently rather than
# loudly. Pass the right one.
class ActionType(StrEnum):
    COPY = "copy"
    DELETE = "delete"
    MOVE = "move"


class OperationStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
