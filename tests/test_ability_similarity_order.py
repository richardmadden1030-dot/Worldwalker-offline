"""Regression for an order-dependent reroll comparison found in CI."""
import random
from pathlib import Path
from ability_archive import GeneratedAbilityArchive, semantic_similarity
from game import GameSession

LEFT = {"name": "Silver Image Calibration", "governing_rule": "Measures reflections that contain a complete image of a target when the user maintains an unbroken hand sign for one breath and declares that amount as a temporary cursed standard for later comparisons."}
RIGHT = {"name": "Graven Measure", "governing_rule": "Measures effective weight borne by marked targets when the user maintains an unbroken hand sign for one breath and declares that amount as a temporary cursed standard for later comparisons."}


def test_duplicate_comparison_is_symmetric(tmp_path):
    assert semantic_similarity(LEFT, RIGHT) == semantic_similarity(RIGHT, LEFT)
    assert semantic_similarity(LEFT, RIGHT) >= .82
    for index, (first, second) in enumerate(((LEFT, RIGHT), (RIGHT, LEFT))):
        archive = GeneratedAbilityArchive(tmp_path / f"archive-{index}.json")
        archive.record("Jujutsu Kaisen", "birth_slot", first)
        assert archive.is_duplicate("Jujutsu Kaisen", "birth_slot", second)


def test_previously_failing_reroll_seed_stays_distinct(tmp_path):
    saved_random = random.getstate()
    try:
        random.seed(23)
        game = GameSession(save_dir=tmp_path / "saves", settings_path=tmp_path / "settings.json")
        game.generated_ability_archive = GeneratedAbilityArchive(tmp_path / "generated.json")
        slots = [game.generate_jjk_birth_slot("A sorcerer with an innate technique.", seed="reroll") for _ in range(18)]
        assert len({row["name"] for row in slots}) == len(slots)
        for index, left in enumerate(slots):
            for right in slots[index + 1:]:
                assert semantic_similarity(left, right) < .82
    finally:
        random.setstate(saved_random)
