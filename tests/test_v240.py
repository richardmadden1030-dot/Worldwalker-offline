import copy
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["APPDATA"] = str(ROOT / "tests" / ".runtime")
sys.path.insert(0, str(ROOT / "backend"))

from game import GameSession
from state_guard import apply_guarded_patch
from worlds import BASE_STATE, WORLD_DATA, abilities_for, playable_characters_for
from util import scene_image_url
import app as app_module


class FakeAI:
    def request(self, instructions, payload, max_output_tokens=700):
        task = payload.get("task")
        if task == "assess_time_skip":
            return {
                "checks": [], "fixed_facts": "Ordered plan.", "simulation_notes": "No uncertain check.",
                "reachable_actions": payload["time_budget"]["reachable_actions"],
                "deferred_actions": payload["time_budget"]["deferred_actions"],
            }
        if task == "resolve_time_skip":
            actions = payload.get("planned_actions", [])
            deferred = payload.get("assessment", {}).get("deferred_actions", [])
            completed = [x for x in actions if x not in deferred]
            return {
                "narrative": "The plan resolves in order.",
                "updates": [
                    {"sequence": i + 1, "type": "action", "title": f"Action {i + 1}",
                     "related_action": action, "narrative": f"The player attempts {action}. The world reacts according to the available time."}
                    for i, action in enumerate(completed)
                ],
                "state_patch": {}, "events": [], "timeline_events": [],
                "elapsed": payload["duration"], "interrupted": False, "interruption_reason": "",
                "new_contacts": [], "incoming_chats": [],
                "completed_actions": completed, "deferred_actions": deferred,
            }
        raise AssertionError(f"Unexpected fake-AI task: {task}")


def session(world="Naruto"):
    game = GameSession()
    game.settings["autosave"] = False
    game.ai = FakeAI()
    abilities = {key: 10 for key in abilities_for(world)}
    game.new_campaign("Tester", world, "Adventurer", "", "", "", "", "", abilities)
    game._flush_story()
    return game


class WorldwalkerV240Tests(unittest.TestCase):
    def test_every_world_has_map_and_playable_character_registry(self):
        for name, world in WORLD_DATA.items():
            self.assertIsInstance(world.get("map"), list, name)
            self.assertGreater(len(world["map"]), 0, name)
            self.assertIsInstance(playable_characters_for(name), list)

    def test_canon_character_start_has_full_player_identity(self):
        game = session()
        game.new_campaign("Ignored", "Naruto", "Adventurer", "", "", "", "", "", {}, canon_character_id="yahiko_akatsuki")
        self.assertEqual(game.state["name"], "Yahiko")
        self.assertEqual(game.state["location"], "Amegakure")
        self.assertEqual(game.state["player_identity"]["mode"], "canon")
        self.assertEqual(game.state["canon_day"], -5221)

    def test_queue_does_not_move_time_or_create_story(self):
        game = session()
        before_time = game.state["world_clock_minutes"]
        before_turn = game.state["turn"]
        game.queue_action("Inspect the gate")
        game.queue_action("Ask the guard a question")
        self.assertEqual(game.state["world_clock_minutes"], before_time)
        self.assertEqual(game.state["turn"], before_turn)
        self.assertEqual(game._flush_story(), [])

    def test_advance_resolves_updates_separately_and_defers_for_time(self):
        game = session()
        game.queue_action("Inspect the market")
        game.queue_action("Train chakra control")
        assessed = game.assess_time_skip(10, "minutes", "", "normal")
        result = game.run_time_skip(assessed["amount"], assessed["unit"], assessed["orders"], assessed["intensity"], assessed["assessment"])
        update_entries = [x for x in result["story"] if x.get("text", "").startswith("[ACTION")]
        self.assertEqual(len(update_entries), 1)
        self.assertIn("Train chakra control", result["deferred_actions"])
        self.assertEqual(result["state"]["turn"], 1)
        self.assertEqual(result["state"]["world_clock_minutes"], 490)

    def test_state_guard_rejects_ai_clock_and_unknown_field(self):
        state = copy.deepcopy(BASE_STATE)
        before = state["world_clock_minutes"]
        report = apply_guarded_patch(state, {"world_clock_minutes": 9999, "map": [], "hp": 80})
        self.assertEqual(state["world_clock_minutes"], before)
        self.assertEqual(state["hp"], 80)
        rejected = {x["field"] for x in report["rejected"]}
        self.assertEqual(rejected, {"world_clock_minutes", "map"})

    def test_start_timestamp_canon_event_fires_on_first_advance(self):
        game = session()
        game.new_campaign("Ignored", "Naruto", "Adventurer", "", "", "", "", "", {}, canon_character_id="yahiko_akatsuki")
        game._flush_story()
        before = copy.deepcopy(game.state)
        game.advance_clock(before, 1, "days")
        self.assertTrue(any("original Akatsuki is founded" in x for x in game.state["world_events"]))
        self.assertEqual(len(game.state["canon_events_fired"]), 1)

    def test_current_landmark_beats_old_battle_language(self):
        url, category = scene_image_url({"world": "Naruto", "location": "Amegakure", "combat": {},
                                         "timeline": ["The war continues elsewhere."], "world_events": [], "weather": "rain"})
        self.assertTrue(url.endswith("naruto_amegakure.webp"))
        self.assertEqual(category, "rain_city")

    def test_new_campaign_api_returns_complete_state(self):
        api_game = session()
        app_module.game = api_game
        client = app_module.app.test_client()
        response = client.post("/api/campaign/new", json={
            "name": "Fresh", "world": "Naruto", "difficulty": "Adventurer",
            "background": "", "appearance": "", "origin": "Academy Student",
            "archetype": "Ninjutsu Student", "stats": {},
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data["state"]["name"], "Fresh")
        self.assertIsInstance(WORLD_DATA[data["state"]["world"]]["map"], list)

    def test_queue_api_is_silent_until_advance(self):
        api_game = session()
        app_module.game = api_game
        client = app_module.app.test_client()
        before = client.get("/api/state").get_json()["state"]
        queued = client.post("/api/actions/queue", json={"action": "Watch the street"})
        after = client.get("/api/state").get_json()["state"]
        self.assertEqual(queued.status_code, 200)
        self.assertEqual(after["turn"], before["turn"])
        self.assertEqual(after["world_clock_minutes"], before["world_clock_minutes"])
        self.assertEqual(api_game._flush_story(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
