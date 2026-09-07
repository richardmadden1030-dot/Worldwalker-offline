import sys
import tempfile
import unittest
import copy
import json
import os
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from friend_accounts import FriendAccountStore, FriendGameRegistry
from worlds import BASE_STATE


class FriendAccountTests(unittest.TestCase):
    def test_friend_accounts_hash_passwords_and_authenticate(self):
        with tempfile.TemporaryDirectory() as td:
            store = FriendAccountStore(Path(td) / "accounts")
            user = store.register("KonohaFriend", "hidden-leaf")
            self.assertEqual(user["username"], "KonohaFriend")
            self.assertNotIn("password", user)
            with store._connect() as db:
                stored = db.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()[0]
            self.assertNotEqual(stored, "hidden-leaf")
            self.assertEqual(store.authenticate("konohafriend", "hidden-leaf")["id"], user["id"])
            with self.assertRaises(ValueError):
                store.authenticate("KonohaFriend", "wrong-password")

    def test_friend_game_registry_isolates_settings_and_saves(self):
        with tempfile.TemporaryDirectory() as td, patch("friend_accounts.SETTINGS_PATH", Path(td) / "missing-shared-settings.json"):
            store = FriendAccountStore(Path(td) / "accounts")
            first = store.register("first_friend", "password-one")
            second = store.register("second_friend", "password-two")
            registry = FriendGameRegistry(store)
            game_one = registry.get(first["id"])
            game_two = registry.get(second["id"])
            self.assertIsNot(game_one, game_two)
            self.assertNotEqual(game_one.save_dir, game_two.save_dir)
            self.assertNotEqual(game_one.settings_path, game_two.settings_path)
            game_one.update_settings({"provider": "cloud", "api_key": "account-one-secret", "model": "gpt-5.6-luna"})
            game_two.update_settings({"provider": "cloud", "api_key": "account-two-secret", "model": "gpt-5.6-luna"})
            self.assertEqual(json.loads(game_one.settings_path.read_text(encoding="utf-8"))["api_key"], "account-one-secret")
            self.assertEqual(json.loads(game_two.settings_path.read_text(encoding="utf-8"))["api_key"], "account-two-secret")
            self.assertNotEqual(game_one.settings["api_key"], game_two.settings["api_key"])
            game_one.state["name"] = "Only First Friend"
            game_one.state["world"] = "Naruto"
            game_one.campaign_active = True
            game_one.save()
            self.assertEqual(len(game_one.list_saves()), 1)
            self.assertEqual(game_two.list_saves(), [])
            self.assertFalse(any(game_two.save_dir.rglob("*.json")))

    def test_new_account_never_inherits_global_or_environment_api_secret(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shared = root / "shared-settings.json"
            shared.write_text(json.dumps({"provider": "cloud", "model": "gpt-5.6-luna", "api_key": "host-secret", "local_token": "host-token"}), encoding="utf-8")
            with patch("friend_accounts.SETTINGS_PATH", shared), patch.dict(os.environ, {"OPENAI_API_KEY": "environment-secret"}):
                store = FriendAccountStore(root / "accounts")
                account = store.register("isolated", "password123")
                game = FriendGameRegistry(store).get(account["id"])
                saved = json.loads(game.settings_path.read_text(encoding="utf-8"))
                self.assertEqual(saved.get("model"), "gpt-5.6-luna")
                self.assertNotIn("api_key", saved)
                self.assertNotIn("local_token", saved)
                self.assertEqual(game.settings.get("api_key"), "")

    def test_registration_limit_and_invite_code(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(
            "os.environ", {"WORLDWALKER_INVITE_CODE": "ramen-night", "WORLDWALKER_MAX_ACCOUNTS": "1"}, clear=False
        ):
            store = FriendAccountStore(Path(td) / "accounts")
            with self.assertRaisesRegex(ValueError, "invite"):
                store.register("first_friend", "password-one", "wrong")
            store.register("first_friend", "password-one", "ramen-night")
            with self.assertRaisesRegex(ValueError, "limit"):
                store.register("second_friend", "password-two", "ramen-night")

    def test_old_campaign_import_stays_with_importing_friend(self):
        with tempfile.TemporaryDirectory() as td, patch("friend_accounts.SETTINGS_PATH", Path(td) / "missing-shared-settings.json"):
            store = FriendAccountStore(Path(td) / "accounts")
            owner = store.register("save_owner", "password-one")
            other = store.register("other_friend", "password-two")
            registry = FriendGameRegistry(store)
            old_state = copy.deepcopy(BASE_STATE)
            old_state.update(name="Imported Hero", world="Naruto", turn=47, campaign_created_version="3.6.4")
            result = registry.get(owner["id"]).import_bundle({
                "version": "3.6.4", "schema_version": 7, "state": old_state,
                "history": [], "story_log": [{"text": "An older journey.", "tag": "story"}], "system_log": [],
            })
            self.assertTrue(result["id"])
            self.assertEqual(len(registry.get(owner["id"]).list_saves()), 1)
            self.assertEqual(registry.get(other["id"]).list_saves(), [])


if __name__ == "__main__":
    unittest.main()
