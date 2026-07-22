import os

import pytest

from enums import StructureMode, UpgradeAction
from importing import ActionType, compute_destination, plan_import
from matching import Match


def test_mirror_returns_mirrored_path(make_track):
    destination = compute_destination(
        make_track(file_path="/source_root/fake/path.mp3"),
        "/source_root",
        "/destination_root",
        StructureMode.MIRROR,
    )

    assert destination == os.path.normpath("/destination_root/fake/path.mp3")


def test_flat_returns_basename_under_root(make_track):
    destination = compute_destination(
        make_track(file_path="/source_root/fake/path.mp3"),
        "/source_root",
        "/destination_root",
        StructureMode.FLAT,
    )

    assert destination == os.path.normpath("/destination_root/path.mp3")


def test_unknown_raises_error(make_track):
    with pytest.raises(ValueError, match="Unknown structure mode"):
        compute_destination(
            make_track(file_path="/source_root/fake/path.mp3"),
            "/source_root",
            "/destination_root",
            "unknown_value",
        )


def test_plan_missing_tracks(make_track):
    import_plan = plan_import(
        missing=[
            make_track(file_path="/source_root/path.mp3"),
            make_track(file_path="/source_root/file/path.flac"),
        ],
        upgrades=[],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.FLAT,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert len(import_plan) == 2
    assert import_plan[0].source == "/source_root/path.mp3"
    assert import_plan[1].source == "/source_root/file/path.flac"
    assert import_plan[0].destination == os.path.normpath("/destination_root/path.mp3")
    assert import_plan[1].destination == os.path.normpath("/destination_root/path.flac")
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[1].action == ActionType.COPY


def test_escaped_destination_path_raises_error(make_track):
    with pytest.raises(ValueError, match="escapes destination root"):
        plan_import(
            missing=[make_track(file_path="/fake/path.mp3")],
            upgrades=[],
            source_root="/source_root",
            destination_root="/destination_root",
            structure_mode=StructureMode.MIRROR,
            upgrade_action=UpgradeAction.DELETE,
        )


def test_sibling_prefix_destination_raises_error(make_track):
    # /destination_root vs /destination_root-backup: a string prefix but a
    # different directory. commonpath must reject it; startswith would not.
    with pytest.raises(ValueError, match="escapes destination root"):
        plan_import(
            missing=[make_track(file_path="/destination_root-backup/evil.mp3")],
            upgrades=[],
            source_root="/destination_root",
            destination_root="/destination_root",
            structure_mode=StructureMode.MIRROR,
            upgrade_action=UpgradeAction.DELETE,
        )


def test_name_disambiguation(make_track):
    import_plan = plan_import(
        missing=[
            make_track(file_path="/source_root/one/path.mp3"),
            make_track(file_path="/source_root/two/path.mp3"),
            make_track(file_path="/source_root/three/path.mp3"),
        ],
        upgrades=[],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.FLAT,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert import_plan[0].destination == os.path.normpath("/destination_root/path.mp3")
    assert import_plan[1].destination == os.path.normpath(
        "/destination_root/path (1).mp3"
    )
    assert import_plan[2].destination == os.path.normpath(
        "/destination_root/path (2).mp3"
    )


def test_case_insensitive_names_disambiguate(make_track):
    # PATH.mp3 and path.mp3 are distinct strings but the same file on a
    # case-insensitive Windows drive, so the second must be disambiguated.
    import_plan = plan_import(
        missing=[
            make_track(file_path="/source_root/one/PATH.mp3"),
            make_track(file_path="/source_root/two/path.mp3"),
        ],
        upgrades=[],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.FLAT,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert import_plan[0].destination == os.path.normpath("/destination_root/PATH.mp3")
    assert import_plan[1].destination == os.path.normpath(
        "/destination_root/path (1).mp3"
    )


def test_upgrade_and_keep(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/mine.mp3"),
                theirs=make_track(file_path="/source_root/theirs.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.FLAT,
        upgrade_action=UpgradeAction.KEEP_BOTH,
    )

    assert len(import_plan) == 1
    assert import_plan[0].action == ActionType.COPY


def test_upgrade_and_delete(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/mine.mp3"),
                theirs=make_track(file_path="/source_root/theirs.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.FLAT,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert len(import_plan) == 2
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[1].action == ActionType.DELETE
    assert import_plan[1].source == "/destination_root/mine.mp3"
    assert import_plan[1].destination is None


def test_upgrade_and_delete_with_collision(make_track):
    import_plan = plan_import(
        missing=[make_track(file_path="/source_root/one/theirs.mp3")],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/mine.mp3"),
                theirs=make_track(file_path="/source_root/two/theirs.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.FLAT,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert len(import_plan) == 3
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[1].action == ActionType.COPY
    assert import_plan[2].action == ActionType.DELETE
    assert import_plan[0].destination == os.path.normpath(
        "/destination_root/theirs.mp3"
    )
    assert import_plan[1].destination == os.path.normpath(
        "/destination_root/theirs (1).mp3"
    )
    assert import_plan[2].source == "/destination_root/mine.mp3"


def test_upgrade_in_place_does_not_delete_the_new_file(make_track):
    # Same-format bitrate upgrade: theirs lands exactly where mine already is.
    # The plan must not copy over mine and then delete that same path.
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(
                    file_path=os.path.normpath("/destination_root/Radiohead/Creep.mp3")
                ),
                theirs=make_track(file_path="/source_root/Radiohead/Creep.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert len(import_plan) == 1
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[0].destination == os.path.normpath(
        "/destination_root/Radiohead/Creep.mp3"
    )


def test_unknown_upgrade_action_raises_error(make_track):
    with pytest.raises(ValueError, match="Unknown upgrade action"):
        plan_import(
            missing=[],
            upgrades=[],
            source_root="/source_root",
            destination_root="/destination_root",
            structure_mode=StructureMode.FLAT,
            upgrade_action="bogus",
        )


def test_basic_move(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/mine.mp3"),
                theirs=make_track(file_path="/source_root/theirs.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.MOVE,
    )

    assert len(import_plan) == 2
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[0].destination == os.path.normpath(
        "/destination_root/theirs.mp3"
    )
    assert import_plan[1].action == ActionType.MOVE
    assert import_plan[1].source == "/destination_root/mine.mp3"
    assert import_plan[1].destination == os.path.normpath(
        "/destination_root/_superseded/mine.mp3"
    )


def test_move_in_place(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/same_name.mp3"),
                theirs=make_track(file_path="/source_root/same_name.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.MOVE,
    )

    assert len(import_plan) == 2
    assert import_plan[0].action == ActionType.MOVE
    assert import_plan[1].action == ActionType.COPY
    assert import_plan[0].destination == os.path.normpath(
        "/destination_root/_superseded/same_name.mp3"
    )
    assert import_plan[1].destination == os.path.normpath(
        "/destination_root/same_name.mp3"
    )


def test_move_with_shared_mine_names(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/one/same_mine_name.mp3"),
                theirs=make_track(file_path="/source_root/theirs_one.mp3"),
            ),
            Match(
                mine=make_track(file_path="/destination_root/two/same_mine_name.mp3"),
                theirs=make_track(file_path="/source_root/theirs_two.mp3"),
            ),
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.MOVE,
    )

    assert len(import_plan) == 4
    assert import_plan[0].action == ActionType.COPY
    assert import_plan[1].action == ActionType.MOVE
    assert import_plan[2].action == ActionType.COPY
    assert import_plan[3].action == ActionType.MOVE
    assert import_plan[1].destination == os.path.normpath(
        "/destination_root/_superseded/same_mine_name.mp3"
    )
    assert import_plan[3].destination == os.path.normpath(
        "/destination_root/_superseded/same_mine_name (1).mp3"
    )


def test_group_in_upgrade_pair(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/mine.mp3"),
                theirs=make_track(file_path="/source_root/theirs.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.MOVE,
    )

    assert import_plan[0].group_id == import_plan[1].group_id


def test_different_group_in_missing_tracks(make_track):
    import_plan = plan_import(
        missing=[
            make_track(file_path="/source_root/one.mp3"),
            make_track(file_path="/source_root/two.mp3"),
        ],
        upgrades=[],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.MOVE,
    )

    assert import_plan[0].group_id != import_plan[1].group_id


def test_group_in_upgrade_move_in_place(make_track):
    import_plan = plan_import(
        missing=[],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/same_name.mp3"),
                theirs=make_track(file_path="/source_root/same_name.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.MOVE,
    )

    assert import_plan[0].group_id == import_plan[1].group_id


def test_missing_and_upgrade_have_different_groups(make_track):
    # The counter runs continuously across both buckets. Numbering each
    # bucket from zero would collide their ids and make the executor skip
    # an unrelated upgrade when a missing copy fails.
    import_plan = plan_import(
        missing=[make_track(file_path="/source_root/one.mp3")],
        upgrades=[
            Match(
                mine=make_track(file_path="/destination_root/mine.mp3"),
                theirs=make_track(file_path="/source_root/theirs.mp3"),
            )
        ],
        source_root="/source_root",
        destination_root="/destination_root",
        structure_mode=StructureMode.MIRROR,
        upgrade_action=UpgradeAction.DELETE,
    )

    assert import_plan[0].group_id != import_plan[1].group_id
