import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from politics import political_regions_for_map
from systems import BLEACH_REALM_NODES, WORLD_TERRITORIES, map_snapshot
from util import world_slug
from worlds import WORLD_DATA


def _state(world, location):
    return {"world": world, "location": location, "turn": 1, "discovered_locations": [location],
            "location_details": {}, "custom_locations": [], "political_regions": [], "quests": []}


def test_every_world_atlas_is_4k_and_label_free_asset_exists():
    from PIL import Image
    for world in WORLD_DATA:
        path = ROOT / "assets" / "generated_maps" / f"{world_slug(world)}.webp"
        assert path.exists(), path
        assert Image.open(path).size[0] >= 3840


def test_bleach_realm_boards_follow_current_location_and_keep_other_boards_switchable():
    world_map = WORLD_DATA["Bleach"]["map"]
    payload = map_snapshot(_state("Bleach", "Karakura Town"), world_map, "Bleach")
    assert payload["active_board"] == "World of the Living"
    assert {board["name"] for board in payload["boards"]} == set(BLEACH_REALM_NODES)
    assert {node["name"] for node in payload["nodes"]} == set(BLEACH_REALM_NODES["World of the Living"])
    assert any(node["current"] for node in payload["nodes"])
    old_save_payload = map_snapshot(_state("Bleach", "11th Division barracks"), world_map, "Bleach")
    assert old_save_payload["active_board"] == "Soul Society"
    assert next(node["name"] for node in old_save_payload["nodes"] if node["current"]) == "Gotei 13 Barracks"


def test_bleach_realm_assets_are_4k():
    from PIL import Image
    for realm in BLEACH_REALM_NODES:
        path = ROOT / "assets" / "generated_maps" / f"Bleach_{realm.replace(' ', '_')}.webp"
        assert path.exists(), path
        assert Image.open(path).size == (4096, 2304)


def test_solo_overview_does_not_pretend_floors_are_land_territories():
    assert WORLD_TERRITORIES["Solo Max-Level Newbie"] == {}
    nodes = map_snapshot(_state("Solo Max-Level Newbie", "Earth — Tower Entrance"), WORLD_DATA["Solo Max-Level Newbie"]["map"], "Solo Max-Level Newbie")["nodes"]
    regions = political_regions_for_map(_state("Solo Max-Level Newbie", "Earth — Tower Entrance"), nodes)
    # Later atlas releases shade the actual Earth entrance under local civil
    # control; that must not expose tower floors as neighboring countries.
    assert all(region['name'] == 'Earth — Tower Entrance' for region in regions)


def test_removed_generic_locations_are_not_reintroduced():
    assert "Demon Lord's Domain" not in {row[0] for row in WORLD_DATA["Reincarnated as a Slime"]["map"]}
    assert "Colonies" not in {row[0] for row in WORLD_DATA["Jujutsu Kaisen"]["map"]}
