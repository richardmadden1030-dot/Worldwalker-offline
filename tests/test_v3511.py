from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_build_includes_the_naruto_move_library_beside_the_module():
    spec = (ROOT / "WorldwalkerRPG.spec").read_text(encoding="utf-8")
    assert "('backend/naruto_tactical_moves.json', '.')" in spec
    assert (ROOT / "backend" / "naruto_tactical_moves.json").is_file()


def test_release_version_is_3511():
    from worlds import APP_VERSION
    assert APP_VERSION == "3.64.0"
