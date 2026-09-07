import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from worlds import APP_VERSION, BASE_STATE, power_profile_for


class BlueprintAI:
    model = "blueprint-test"

    def request(self, instructions, payload, max_output_tokens=700):
        if payload.get("kind") == "hidden_class":
            return {
                "name": "Mnemonic Crucible Sovereign",
                "kind": "Unique Hidden Production Class",
                "rank": "Unique",
                "description": "A memory-forging class that stores lived techniques in equipment patterns.",
                "effect": "Records one witnessed crafting motion, rebuilds it as a recipe clue, and imprints a narrow echo into bonded gear.",
                "limitation": "Only personally witnessed work can be recorded; failed reproductions damage the bonded item and consume rare materials.",
                "growth_path": "Complete the First Recollection, restore a forgotten masterwork, then survive the Crucible succession quest.",
                "signature_skill": "Crucible Recollection",
                "signature_effect": "Replays one recorded production motion during a compatible craft.",
                "canon_balance": "Starts near a rare production class feature and can approach top hidden-class versatility only through its succession quests.",
                "rarity_reason": "The route requires a crafter to remember a destroyed masterpiece perfectly.",
            }
        return {
            "name": "Ossuary Loom",
            "kind": "Kekkei Genkai",
            "rank": "Nascent",
            "origin": "An inherited chakra mutation changes living bone density and growth direction.",
            "effect": "Changes bone density for defense, grows short tools, and senses vibration through connected bone.",
            "limitation": "Rapid growth consumes calcium and chakra, causes pain, and can leave brittle recovery periods.",
            "growth_path": "Learn safe density shifts, shape articulated tools, then develop a full skeletal field technique.",
            "canon_balance": "Starts with breadth similar to an inexperienced bloodline user and can eventually rival versatile combat kekkei genkai through mastery.",
            "starting_skills": [
                {"name": "Marrow Bastion", "effect": "Densifies one struck limb to absorb impact.",
                 "limitation": "Slows the protected limb.", "growth_path": "Protect larger linked sections."},
                {"name": "Ivory Needle", "effect": "Grows a short bone spike as a tool or weapon.",
                 "limitation": "Costs calcium and chakra.", "growth_path": "Improve shape and controlled regrowth."},
            ],
        }


class WorldwalkerV372Tests(unittest.TestCase):
    def state(self, difficulty="Adventurer"):
        state = copy.deepcopy(BASE_STATE)
        state.update({
            "name": "Yahiko", "world": "Naruto", "difficulty": difficulty,
            "stats": {"Taijutsu": 40, "Ninjutsu": 48, "Genjutsu": 30,
                      "Chakra Control": 42, "Willpower": 45, "Intellect": 38},
            "special": {"Archetype": "Ninjutsu Student"},
        })
        return state

    def test_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_extreme_specialty_is_not_called_reality_bending_overall(self):
        stats = {"Taijutsu": 199, "Ninjutsu": 749, "Genjutsu": 35,
                 "Chakra Control": 188, "Willpower": 59, "Intellect": 53}
        profile = power_profile_for("Naruto", stats, "Ninjutsu Student")
        self.assertEqual(profile["overall"]["name"], "Exceptional")
        self.assertEqual(profile["combat"]["name"], "Powerhouse")
        self.assertNotEqual(profile["combat"]["name"], "Reality-Bending")
        self.assertEqual(profile["peak"]["stat"], "Ninjutsu")
        self.assertEqual(profile["axes"]["speed"], {"stat": "Taijutsu", "value": 199})
        self.assertEqual(profile["axes"]["defense"], {"stat": "Willpower", "value": 59})
        self.assertTrue(profile["lopsided"])

    def test_advisor_and_public_state_receive_same_mechanical_profile(self):
        game = GameSession()
        game.state = self.state()
        task_profile = game.task_state_for_ai("advisor")["mechanical_power_profile"]
        public_profile = game.public_state()["_power_profile"]
        self.assertEqual(task_profile, public_profile)
        self.assertIn("CURRENT stats", game.task_rules("moment"))

    def test_plain_training_develops_every_stat_and_targets_weak_foundation(self):
        game = GameSession()
        game.state = self.state()
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(data, [], 1, "months", ["I train"], "normal")
        stats = data["state_patch"]["stats"]
        self.assertEqual(set(stats), set(self.state()["stats"]))
        self.assertTrue(all(stats[name] > self.state()["stats"][name] for name in stats))
        entry = data["state_patch"]["progression_log"][-1]
        self.assertTrue(entry["balanced_training"])
        self.assertEqual(entry["ability"], "Genjutsu")
        self.assertEqual(entry["training_method_multiplier"], 1.0)

    def test_named_training_stat_is_used_and_world_method_can_accelerate_growth(self):
        game = GameSession()
        game.state = self.state()
        ordinary = {"state_patch": {}, "events": [], "updates": []}
        accelerated = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(
                ordinary, [], 1, "months", ["Train Ninjutsu every day"], "normal"
            )
            game.enforce_training_progress(
                accelerated, [], 1, "months",
                ["Train Ninjutsu through 1000 shadow clones every day until I reach Kage-level output"],
                "normal",
            )
        ordinary_gain = ordinary["state_patch"]["stats"]["Ninjutsu"] - 48
        accelerated_gain = accelerated["state_patch"]["stats"]["Ninjutsu"] - 48
        self.assertGreater(accelerated_gain, ordinary_gain * 3)
        entry = accelerated["state_patch"]["progression_log"][-1]
        self.assertEqual(entry["ability"], "Ninjutsu")
        self.assertGreaterEqual(entry["training_method_multiplier"], 4.5)
        self.assertIn("shadow-clone", entry["training_method"])
        self.assertGreater(entry["support_stat_gains"]["Chakra Control"], 0)

    def test_nightmare_specialized_training_keeps_single_stat_old_rate(self):
        game = GameSession()
        game.state = self.state("Nightmare")
        data = {"state_patch": {}, "events": [], "updates": []}
        with patch("engine_time.random.random", return_value=1.0):
            game.enforce_training_progress(
                data, [], 1, "months", ["Train Ninjutsu every day"], "normal"
            )
        self.assertEqual(data["state_patch"]["stats"], {"Ninjutsu": 68})

    def test_ai_authors_unique_hidden_class_instead_of_selecting_pool_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.ai_bg = BlueprintAI()
            game.ai_bg_ready = lambda: True
            hidden = game.generate_hidden_class(
                "Overgeared", "I have a hidden crafting class that stores memories in armor.",
                20, ["Strength", "Dexterity"], {"Strength": 40, "Dexterity": 38},
            )
        self.assertEqual(hidden["name"], "Mnemonic Crucible Sovereign")
        self.assertIn("succession", hidden["growth_path"].lower())
        self.assertIn("hidden-class", hidden["canon_balance"])
        self.assertEqual(hidden["signature_skill"], "Crucible Recollection")

    def test_claimed_kekkei_genkai_creates_matching_persisted_techniques(self):
        with tempfile.TemporaryDirectory() as folder:
            game = GameSession(save_dir=Path(folder), settings_path=Path(folder) / "settings.json")
            game.ai_bg = BlueprintAI()
            game.ai_bg_ready = lambda: True
            ability = game.generate_background_ability(
                "Naruto", "I inherited a kekkei genkai that manipulates my bone density.", 20
            )
        skills = {ability["name"]: copy.deepcopy(ability["details"])}
        game.install_background_ability_skills(skills, ability)
        self.assertEqual(ability["details"]["kind"], "Kekkei Genkai")
        self.assertIn("Marrow Bastion", skills)
        self.assertIn("Ivory Needle", skills)
        self.assertIn("densif", skills["Marrow Bastion"]["effect"].lower())

    def test_power_summary_is_above_journal_and_uses_shared_profile(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn("s._power_profile", js)
        self.assertIn("Balanced Combat", js)
        self.assertIn("(Number(value) || 0) / maxStat", js)
        self.assertIn("#modal-power-summary{ z-index:5100; }", css)


if __name__ == "__main__":
    unittest.main()
