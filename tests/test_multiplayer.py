import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from friend_accounts import FriendAccountStore, FriendGameRegistry
from multiplayer import MultiplayerStore, player_view, split_player_results
from worlds import BASE_STATE


def bundle(name="Imported Hero", version="3.6.4"):
    state = copy.deepcopy(BASE_STATE)
    state.update(name=name, world="Naruto", turn=12, campaign_created_version=version,
                 stats={"Taijutsu": 30, "Ninjutsu": 35, "Genjutsu": 12,
                        "Chakra Control": 25, "Willpower": 28, "Intellect": 20})
    return {"version": version, "schema_version": state.get("schema_version", 4),
            "state": state, "history": [], "checkpoints": [], "story_log": [], "system_log": []}


class MultiplayerStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings_patch = patch("friend_accounts.SETTINGS_PATH", self.root / "missing-settings.json")
        self.settings_patch.start()
        self.accounts = FriendAccountStore(self.root / "accounts")
        self.host = self.accounts.register("room_host", "password-one")
        self.friend = self.accounts.register("room_friend", "password-two")
        self.store = MultiplayerStore(self.accounts)

    def tearDown(self):
        self.settings_patch.stop()
        self.temp.cleanup()

    def create_and_join(self):
        status = self.store.create_room(self.host, bundle())
        joined = self.store.join_room(self.friend, status["join_code"], "Konan", "A founding Akatsuki member.")
        return status["room_id"], joined

    def test_old_save_is_copied_into_shared_room_without_overwriting_original(self):
        registry = FriendGameRegistry(self.accounts)
        personal = registry.get(self.host["id"])
        imported = personal.import_bundle(bundle())
        personal.load(imported["id"])
        original_path = personal.save_path_for_id(imported["id"])
        original_bytes = original_path.read_bytes()
        room = self.store.create_room(self.host, personal.save_bundle("multiplayer-copy"))
        shared_path = self.store.room_root(room["room_id"]) / "shared_campaign.json"
        self.assertTrue(shared_path.exists())
        self.assertEqual(original_path.read_bytes(), original_bytes)
        shared = json.loads(shared_path.read_text(encoding="utf-8"))
        self.assertEqual(shared["state"]["name"], "Imported Hero")
        self.assertEqual(shared["multiplayer_room_id"], room["room_id"])

    def test_each_member_has_independent_actions_and_character_view(self):
        room_id, _ = self.create_and_join()
        self.store.queue_action(room_id, self.host["id"], "Train ninjutsu")
        self.store.queue_action(room_id, self.friend["id"], "Scout the eastern road")
        self.store.set_ready(room_id, self.host["id"], True)
        host_status = self.store.status(room_id, self.host["id"])
        friend_status = self.store.status(room_id, self.friend["id"])
        self.assertEqual(host_status["your_actions"], ["Train ninjutsu"])
        self.assertEqual(friend_status["your_actions"], ["Scout the eastern road"])
        self.assertTrue(host_status["your_ready"])
        self.assertFalse(friend_status["your_ready"])
        friend_character = self.store.member(room_id, self.friend["id"])["character"]
        view = player_view(bundle()["state"], friend_character, friend_status["your_actions"])
        self.assertEqual(view["name"], "Konan")
        self.assertEqual(view["status"], ["Normal"])
        self.assertEqual(view["queued_actions"], ["Scout the eastern road"])

    def test_disconnected_player_passes_even_if_they_were_ready(self):
        room_id, _ = self.create_and_join()
        self.store.queue_action(room_id, self.host["id"], "Speak to Jiraiya")
        self.store.queue_action(room_id, self.friend["id"], "Attack the guards")
        self.store.set_ready(room_id, self.host["id"], True)
        self.store.set_ready(room_id, self.friend["id"], True)
        old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(timespec="seconds")
        with self.store._connect() as db:
            db.execute("UPDATE multiplayer_members SET last_seen_at=? WHERE room_id=? AND user_id=?",
                       (old, room_id, self.friend["id"]))
        plan = self.store.resolution_plan(room_id)
        host_plan = next(p for p in plan["participants"] if p["user_id"] == self.host["id"])
        friend_plan = next(p for p in plan["participants"] if p["user_id"] == self.friend["id"])
        self.assertFalse(host_plan["passes"])
        self.assertTrue(friend_plan["passes"])
        self.assertEqual(friend_plan["actions"], [])
        self.assertEqual(plan["orders"], ["Imported Hero: Speak to Jiraiya"])

    def test_no_ready_players_produces_one_pass_moment_and_round_resets(self):
        room_id, _ = self.create_and_join()
        plan = self.store.resolution_plan(room_id)
        self.assertEqual(plan["orders"], ["All player characters pass and take no deliberate action during this moment."])
        with self.store._connect() as db:
            db.execute("UPDATE multiplayer_rooms SET round_deadline=? WHERE id=?", ("2000-01-01T00:00:00+00:00", room_id))
        self.assertIn(room_id, self.store.due_rooms())
        self.assertTrue(self.store.claim(room_id))
        self.store.complete(room_id, {"status": "resolved", "story": [{"text": "The world moves.", "tag": "system"}]})
        status = self.store.status(room_id, self.host["id"], since_round=0)
        self.assertEqual(status["round"], 2)
        self.assertFalse(status["your_ready"])
        self.assertEqual(status["result"]["story"][0]["text"], "The world moves.")
        self.assertGreaterEqual(status["seconds_left"], 590)

    def test_each_player_receives_a_durable_proximity_aware_chronicle(self):
        room_id, _ = self.create_and_join()
        host_character = self.store.member(room_id, self.host["id"])["character"]
        friend_character = self.store.member(room_id, self.friend["id"])["character"]
        host_character.update(location="Konoha", sublocation="Eastern Gate")
        friend_character.update(location="Sunagakure", sublocation="Market Road")
        characters = {self.host["id"]: host_character, self.friend["id"]: friend_character}
        self.store.save_characters(room_id, characters)
        participants = self.store.resolution_plan(room_id)["participants"]
        result = {
            "status": "resolved",
            "story": [
                {"text": "[KONOHA WATCH] Yahiko questions the eastern gate guards.", "tag": "narrative"},
                {"text": "[DESERT CARAVAN] Konan finds a damaged caravan outside the market.", "tag": "narrative"},
                {"text": "[VILLAGE BROADCAST] Every great village receives the same emergency warning.", "tag": "canon_event"},
                {"text": "[SEALED REPORT] A messenger tells Konan what happened at the border.", "tag": "system"},
            ],
            "updates": [
                {"title": "Konoha Watch", "type": "action", "actor_user_id": self.host["id"],
                 "location": "Konoha", "sublocation": "Eastern Gate", "information_scope": "local",
                 "delivery_channel": "witness", "audience_user_ids": [self.host["id"]]},
                {"title": "Desert Caravan", "type": "action", "actor_user_id": self.friend["id"],
                 "location": "Sunagakure", "sublocation": "Market Road", "information_scope": "local",
                 "delivery_channel": "witness", "audience_user_ids": [self.friend["id"]]},
                {"title": "Village Broadcast", "type": "canon event", "information_scope": "global",
                 "delivery_channel": "broadcast", "audience_user_ids": [self.host["id"], self.friend["id"]]},
                {"title": "Sealed Report", "type": "world event", "information_scope": "reported",
                 "delivery_channel": "message", "audience_user_ids": [self.friend["id"]]},
            ],
        }
        personal = split_player_results(result, participants, characters, self.host["id"])
        host_text = " ".join(entry["text"] for entry in personal[self.host["id"]]["story"])
        friend_text = " ".join(entry["text"] for entry in personal[self.friend["id"]]["story"])
        self.assertIn("KONOHA WATCH", host_text)
        self.assertNotIn("DESERT CARAVAN", host_text)
        self.assertNotIn("SEALED REPORT", host_text)
        self.assertIn("DESERT CARAVAN", friend_text)
        self.assertNotIn("KONOHA WATCH", friend_text)
        self.assertIn("SEALED REPORT", friend_text)
        self.assertIn("VILLAGE BROADCAST", host_text)
        self.assertIn("VILLAGE BROADCAST", friend_text)
        self.assertEqual(personal[self.host["id"]]["story"][0]["multiplayer_scope"], "local")
        self.assertEqual(personal[self.host["id"]]["story"][-1]["multiplayer_scope"], "shared")
        self.assertEqual(personal[self.friend["id"]]["story"][-1]["multiplayer_scope"], "reported")

        self.store.complete(room_id, result, personal)
        host_status = self.store.status(room_id, self.host["id"], since_round=0)
        friend_status = self.store.status(room_id, self.friend["id"], since_round=0)
        self.assertNotEqual(host_status["result"]["story"], friend_status["result"]["story"])
        restarted_store = MultiplayerStore(self.accounts)
        host_history = restarted_store.chronicle(room_id, self.host["id"])
        friend_history = restarted_store.chronicle(room_id, self.friend["id"])
        self.assertEqual([entry["text"] for entry in host_history],
                         [entry["text"] for entry in personal[self.host["id"]]["story"]])
        self.assertEqual([entry["text"] for entry in friend_history],
                         [entry["text"] for entry in personal[self.friend["id"]]["story"]])

    def test_unspecified_local_scene_falls_back_to_character_proximity(self):
        room_id, _ = self.create_and_join()
        characters = {}
        for user_id in (self.host["id"], self.friend["id"]):
            character = self.store.member(room_id, user_id)["character"]
            character.update(location="Amegakure", sublocation="Old Tower")
            characters[user_id] = character
        self.store.save_characters(room_id, characters)
        participants = self.store.resolution_plan(room_id)["participants"]
        result = {
            "status": "resolved",
            "story": [{"text": "[TOWER MEETING] Yahiko lowers his voice and explains the plan.", "tag": "narrative"}],
            "updates": [{"title": "Tower Meeting", "type": "action", "actor_user_id": self.host["id"],
                         "information_scope": "local"}],
        }
        personal = split_player_results(result, participants, characters, self.host["id"])
        self.assertEqual(len(personal[self.host["id"]]["story"]), 1)
        self.assertEqual(len(personal[self.friend["id"]]["story"]), 1)


if __name__ == "__main__":
    unittest.main()
