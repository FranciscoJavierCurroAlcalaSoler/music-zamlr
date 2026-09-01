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


class Bucket(StrEnum):
    """Internal routing key and API contract: which list a classified track belongs in.

    only_in_mine has no member here because nothing classifies *into* it;
    it's whatever is left over once every track of theirs is placed.

    Use == instead of "is" for comparisons. A raw string from a request body compares
    equal to a StrEnum member, so == keeps working when the value arrives as JSON rather
    than as an enum.
    """

    MISSING = "missing"
    UPGRADE_AVAILABLE = "upgrade_available"
    ALREADY_HAVE = "already_have"
    NEEDS_REVIEW = "needs_review"


class ImportPhase(StrEnum):
    COMPARING = "comparing"
    COPYING = "copying"
