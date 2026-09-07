import copy
import unittest
from unittest.mock import patch

import app as api
from test_naruto_tactical import fresh


class TacticalReplacesLegacyTests(unittest.TestCase):
    def test_supported_worlds_reject_legacy_combat_actions(self):
        for world in ("Naruto", "One Piece", "Bleach"):
            game = fresh()
            game.state["world"] = world
            with self.subTest(world=world), patch.object(api, "game", game), api.app.test_request_context(
                "/api/combat/action", method="POST", json={"action": "attack"}
            ):
                response, status = api.api_combat_action()
                self.assertEqual(status, 409)
                self.assertEqual(response.get_json()["tactical_url"], "/tactical-preview/designs/campaign.html")

    def test_unsupported_world_keeps_legacy_combat(self):
        game = fresh()
        game.state["world"] = "Hunter x Hunter"
        with patch.object(api, "game", game), patch.object(api, "atomic_game_call", return_value={"ok": True}), \
             api.app.test_request_context("/api/combat/action", method="POST", json={"action": "defend"}):
            self.assertEqual(api.api_combat_action().get_json(), {"ok": True})

    def test_supported_world_state_always_marks_tactical(self):
        for world in ("Naruto", "One Piece", "Bleach"):
            game = fresh()
            game.state["world"] = world
            game.public_state = lambda: copy.deepcopy(game.state)
            with self.subTest(world=world), patch.object(api, "game", game), \
                 patch.dict("os.environ", {"WORLDWALKER_TACTICAL": "0"}), api.app.test_request_context("/api/state"):
                state = api.request_public_state()
                self.assertTrue(state["combat"]["tactical_enabled"])
                self.assertEqual(state["_tactical_battle_url"], "/tactical-preview/designs/campaign.html")


if __name__ == "__main__":
    unittest.main()
