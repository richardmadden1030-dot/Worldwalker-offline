import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import lore
import portrait_generator
from content_audit import audit_all_worlds
from game import GameSession
from util import scene_art_signature, scene_category, scene_context
from worlds import APP_VERSION, BASE_STATE, abilities_for, format_calendar_date


class WorldwalkerV3160Tests(unittest.TestCase):
    def fresh(self, world="Naruto"):
        state = copy.deepcopy(BASE_STATE)
        state.update(world=world, location="Konohagakure", weather="clear", current_activity="")
        return state

    def test_release_version(self):
        self.assertEqual(APP_VERSION, "3.64.0")

    def test_every_bundled_world_passes_the_shared_depth_gate(self):
        report = audit_all_worlds()
        self.assertEqual(report["summary"]["worlds"], 9)
        self.assertEqual(report["summary"]["critical"], 0, report["issues"])
        self.assertEqual(report["summary"]["release_ready"], 9, report["issues"])

    def test_sublocation_beats_broad_landmark_and_old_combat_language(self):
        state = self.fresh()
        state["location_details"] = {"Konohagakure": {"sublocation": "Old merchant stall", "indoors": True}}
        state["standing_orders"] = ["Return from the battlefield and buy medicine"]
        state["combat"] = {"active": False, "enemy": {"name": "Monster horde"}}
        self.assertEqual(scene_category(state), "merchant_shop")
        context = scene_context(state)
        self.assertEqual(context["sublocation"], "Old merchant stall")
        self.assertTrue(context["indoors"])

    def test_indoor_scene_ignores_outdoor_weather(self):
        state = self.fresh()
        state["weather"] = "heavy blizzard"
        state["location_details"] = {"Konohagakure": {"sublocation": "Academy classroom", "indoors": True}}
        self.assertEqual(scene_category(state), "academy_classroom")

    def test_active_combat_is_the_only_combat_art_override(self):
        state = self.fresh()
        state["location_details"] = {"Konohagakure": {"sublocation": "Market stall", "indoors": True}}
        state["combat"] = {"active": True, "enemy": {"name": "Rogue shinobi", "is_group": False}}
        self.assertEqual(scene_category(state), "duel")

    def test_scene_signature_tracks_real_sublocation_changes(self):
        state = self.fresh()
        state["location_details"] = {"Konohagakure": {"sublocation": "Market stall", "indoors": True}}
        first = scene_art_signature(state)
        state["location_details"]["Konohagakure"]["sublocation"] = "Academy classroom"
        self.assertNotEqual(first, scene_art_signature(state))

    def test_auto_lore_refresh_is_local_bounded_and_zero_ai(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(lore, "LORE_AUTOMATION_PATH", root / "automation.json"), \
                 patch.object(lore, "USER_LORE_DIR", root / "lore"), \
                 patch.object(lore, "_validate_public_url", side_effect=lambda url: url):
                (root / "lore").mkdir()
                lore.register_lore_source("https://example.com/wiki/start", "Naruto", "wiki", discover=True)
                lore.configure_lore_automation({"enabled": True, "discover_related_pages": True,
                                                "max_pages_per_refresh": 2, "interval_days": 30})
                download = {"url": "https://example.com/wiki/start", "raw": b"unused", "content_type": "text/plain",
                            "etag": "v1", "last_modified": "today", "not_modified": False}
                entry = {"title": "Chakra", "keys": "chakra", "text": "A sufficiently long local lore note about chakra control and training rules.",
                         "source": "example.com", "source_type": "wiki", "citation": download["url"], "claims": {},
                         "updated_at": "2026-08-26T00:00:00+00:00"}
                links = ["https://example.com/wiki/one", "https://example.com/wiki/two", "https://other.test/wiki/no"]
                with patch.object(lore, "_fetch_lore_url", return_value=download), \
                     patch.object(lore, "_entry_from_download", return_value=(entry, links)):
                    result = lore.refresh_lore_sources(force=True, world="Naruto")
                self.assertEqual(result["updated"], 1)
                self.assertEqual(result["discovered"], 2)
                self.assertEqual(result["ai_calls"], 0)
                status = lore.lore_automation_status("Naruto")
                self.assertEqual(len(status["sources"]), 3)
                self.assertEqual(status["cost_policy"]["routine_refresh_ai_calls"], 0)

    def test_fandom_sources_use_lightweight_mediawiki_api(self):
        url = lore._mediawiki_api_url("https://naruto.fandom.com/wiki/Narutopedia")
        self.assertIn("/api.php?", url)
        self.assertIn("prop=wikitext%7Clinks", url)
        self.assertIn("page=Narutopedia", url)
        self.assertEqual(lore._mediawiki_api_url("https://example.com/wiki/Page"), "https://example.com/wiki/Page")

    def test_bleach_year_before_start_keeps_ichigo_event_365_days_away(self):
        game = GameSession()
        game.new_campaign(
            "Test Soul Reaper", "Bleach", "Adventurer", "", "", "",
            "Recent Shin'o Academy Graduate", "Kido Caster",
            {name: 30 for name in abilities_for("Bleach")},
            start_location="Seireitei", starting_era_id="year_before_arrival",
        )
        self.assertEqual(game.state["canon_day"], -365)
        self.assertEqual(game.state["canon_time_minutes"], -365 * 1440 + 480)
        countdown = game.canon_countdown()
        self.assertEqual(countdown["minutes_until"], 365 * 1440)
        self.assertIsNone(game.next_canon_stop(364, "days"))
        self.assertEqual(game.next_canon_stop(365, "days")["canon_day"], 0)

    def test_bleach_dates_name_the_story_anchor_instead_of_fake_year_one(self):
        self.assertEqual(format_calendar_date("Bleach", -365, None, -365),
                         "May 18, 2000")
        self.assertEqual(format_calendar_date("Bleach", 0, None, -365),
                         "May 18, 2001")

    def test_special_ability_cards_are_expandable(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
        self.assertIn('class="release-card shikai-card expandable-special-card', js)
        self.assertIn('class="skill-journal-card expandable-special-card', js)
        self.assertIn("Read details +", css)

    def test_portrait_effect_change_keeps_previous_picture_visible(self):
        state = self.fresh("Bleach")
        state.update(campaign_id="portrait-regression", appearance_desc="A Soul Reaper with black hair")
        settings = {"portrait_generation_enabled": True, "portrait_auto_generate": True,
                    "provider": "local", "local_image_model": "test-model"}
        with tempfile.TemporaryDirectory() as tmp, patch.object(portrait_generator, "PORTRAIT_CACHE_DIR", Path(tmp)):
            old_signature = portrait_generator.portrait_signature(state)
            old_file = Path(tmp) / f"portrait-regression-{old_signature}.png"
            old_file.write_bytes(b"valid prior portrait placeholder")
            state["portrait_identity"] = {"temporary_traits": ["Bankai aura"], "reference_file": ""}
            view = portrait_generator.portrait_view(state, settings)
        self.assertTrue(view["_portrait_previous"])
        self.assertTrue(view["_portrait_image"].endswith(old_file.name))
        self.assertFalse(view["_portrait_generated"])


if __name__ == "__main__":
    unittest.main()
