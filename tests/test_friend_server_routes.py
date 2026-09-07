import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FriendServerRouteTests(unittest.TestCase):
    def test_two_browser_sessions_cannot_see_each_others_campaigns(self):
        script = textwrap.dedent(r"""
            import copy, io, json, sys
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd() / "backend"))
            from app import app
            from worlds import BASE_STATE

            anonymous = app.test_client()
            blocked = anonymous.get("/api/state")
            assert blocked.status_code == 401, blocked.data

            first = app.test_client()
            second = app.test_client()
            first_auth = first.get("/api/auth/session").get_json()
            second_auth = second.get("/api/auth/session").get_json()
            assert first_auth["accounts_enabled"] and not first_auth["authenticated"]

            registered_one = first.post("/api/auth/register", json={"username":"friend_one","password":"password-one"})
            registered_two = second.post("/api/auth/register", json={"username":"friend_two","password":"password-two"})
            assert registered_one.status_code == 201, registered_one.data
            assert registered_two.status_code == 201, registered_two.data
            csrf_one = registered_one.get_json()["csrf_token"]
            csrf_two = registered_two.get_json()["csrf_token"]
            mobile_token = registered_one.get_json()["auth_token"]

            # Privacy-heavy mobile browsers and installed PWAs may discard the
            # Flask cookie after login. The signed fallback must preserve the
            # exact same private account and CSRF boundary without cookies.
            mobile = app.test_client(use_cookies=False)
            bearer = {"Authorization":f"Bearer {mobile_token}", "X-Worldwalker-CSRF":csrf_one}
            mobile_session = mobile.get("/api/auth/session", headers=bearer).get_json()
            assert mobile_session["authenticated"] and mobile_session["user"]["username"] == "friend_one"
            mobile_settings = mobile.post("/api/settings", json={"narration":"Cinematic"}, headers=bearer)
            assert mobile_settings.status_code == 200, mobile_settings.data
            assert mobile.get("/api/settings", headers=bearer).get_json()["narration"] == "Cinematic"

            created_one = first.post("/api/campaign/new", json={
                "name":"Friend One Hero", "world":"Naruto", "difficulty":"Adventurer", "background":"A traveling shinobi."
            }, headers={"X-Worldwalker-CSRF":csrf_one})
            created_two = second.post("/api/campaign/new", json={
                "name":"Friend Two Hero", "world":"Bleach", "difficulty":"Adventurer", "background":"A recent academy graduate."
            }, headers={"X-Worldwalker-CSRF":csrf_two})
            assert created_one.status_code == 200 and created_two.status_code == 200
            first.post("/api/actions/queue", json={"action":"Train chakra control"}, headers={"X-Worldwalker-CSRF":csrf_one})
            second.post("/api/actions/queue", json={"action":"Practice Hado"}, headers={"X-Worldwalker-CSRF":csrf_two})
            first_state = first.get("/api/state").get_json()["state"]
            second_state = second.get("/api/state").get_json()["state"]
            assert first_state["name"] == "Friend One Hero" and first_state["world"] == "Naruto"
            assert second_state["name"] == "Friend Two Hero" and second_state["world"] == "Bleach"
            assert first_state["queued_actions"] == ["Train chakra control"]
            assert second_state["queued_actions"] == ["Practice Hado"]

            old_state = copy.deepcopy(BASE_STATE)
            old_state.update(name="Old Save Hero", world="Naruto", turn=33, campaign_created_version="3.6.4")
            bundle = {"version":"3.6.4", "schema_version":7, "state":old_state, "history":[], "story_log":[], "system_log":[]}
            imported = first.post("/api/save/import", data={
                "file": (io.BytesIO(json.dumps(bundle).encode()), "friend-old-save.worldwalker.json")
            }, headers={"X-Worldwalker-CSRF": csrf_one}, content_type="multipart/form-data")
            assert imported.status_code == 200, imported.data
            save_id = imported.get_json()["id"]
            first_saves = first.get("/api/saves").get_json()["saves"]
            second_saves = second.get("/api/saves").get_json()["saves"]
            assert save_id in {item["id"] for item in first_saves}
            assert save_id not in {item["id"] for item in second_saves}
            assert all("Friend Two Hero" not in item.get("label", "") for item in first_saves)
            assert all("Friend One Hero" not in item.get("label", "") for item in second_saves)

            cross_load = second.post("/api/load", json={"name":save_id}, headers={"X-Worldwalker-CSRF":csrf_two})
            assert cross_load.status_code != 200

            changed = first.post("/api/settings", json={"narration":"Detailed", "provider":"cloud", "api_key":"first-account-only", "model":"gpt-5.6-luna"}, headers={"X-Worldwalker-CSRF":csrf_one})
            assert changed.status_code == 200
            first_settings = first.get("/api/settings").get_json()
            second_settings = second.get("/api/settings").get_json()
            assert first_settings["narration"] == "Detailed" and first_settings["has_api_key"] is True
            assert "api_key" not in first_settings
            assert second_settings["narration"] != "Detailed" and second_settings["has_api_key"] is False

            logout = first.post("/api/auth/logout", json={}, headers={"X-Worldwalker-CSRF":csrf_one})
            assert logout.status_code == 200
            assert first.get("/api/saves").status_code == 401
            login = first.post("/api/auth/login", json={"username":"friend_one","password":"password-one"})
            assert login.status_code == 200
            assert len(first.get("/api/saves").get_json()["saves"]) >= 1
        """)
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "WORLDWALKER_DATA_DIR": str(Path(td) / "data"),
                "WORLDWALKER_ACCOUNTS_ENABLED": "1",
                "WORLDWALKER_SECURE_COOKIES": "0",
                "WORLDWALKER_MAX_ACCOUNTS": "10",
            })
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=90,
            )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)

    def test_two_accounts_join_one_room_with_separate_characters_and_plans(self):
        script = textwrap.dedent(r"""
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd() / "backend"))
            from app import app

            host = app.test_client()
            friend = app.test_client()
            host_auth = host.post("/api/auth/register", json={"username":"mp_host","password":"password-one"}).get_json()
            friend_auth = friend.post("/api/auth/register", json={"username":"mp_friend","password":"password-two"}).get_json()
            h = {"X-Worldwalker-CSRF":host_auth["csrf_token"]}
            f = {"X-Worldwalker-CSRF":friend_auth["csrf_token"]}
            made = host.post("/api/campaign/new", json={
                "name":"Yahiko", "world":"Naruto", "difficulty":"Adventurer",
                "background":"Founder of the original Akatsuki."
            }, headers=h)
            assert made.status_code == 200, made.data
            room = host.post("/api/multiplayer/create", json={}, headers=h)
            assert room.status_code == 201, room.data
            code = room.get_json()["join_code"]
            joined = friend.post("/api/multiplayer/join", json={
                "join_code":code, "character_name":"Konan", "background":"Paper-user and Akatsuki founder."
            }, headers=f)
            assert joined.status_code == 200, joined.data
            assert len(joined.get_json()["members"]) == 2

            host_q = host.post("/api/actions/queue", json={"action":"Address the gathered rebels"}, headers=h)
            friend_q = friend.post("/api/actions/queue", json={"action":"Scout Hanzo's patrols"}, headers=f)
            assert host_q.get_json()["queued_actions"] == ["Address the gathered rebels"]
            assert friend_q.get_json()["queued_actions"] == ["Scout Hanzo's patrols"]
            host_state = host.get("/api/state").get_json()["state"]
            friend_state = friend.get("/api/state").get_json()["state"]
            assert host_state["name"] == "Yahiko", host_state["name"]
            assert friend_state["name"] == "Konan", friend_state["name"]
            assert host_state["queued_actions"] == ["Address the gathered rebels"]
            assert friend_state["queued_actions"] == ["Scout Hanzo's patrols"]
            assert host_state["_multiplayer_chronicle"] == []
            assert friend_state["_multiplayer_chronicle"] == []

            denied = friend.post("/api/multiplayer/time", json={"amount":7,"unit":"days"}, headers=f)
            assert denied.status_code == 400
            chosen = host.post("/api/multiplayer/time", json={"amount":7,"unit":"days","intensity":"intense"}, headers=h)
            assert chosen.status_code == 200
            ready = host.post("/api/multiplayer/ready", json={"ready":True}, headers=h)
            assert ready.status_code == 200 and ready.get_json()["your_ready"]
            friend_status = friend.get("/api/multiplayer/status").get_json()
            assert not friend_status["your_ready"]
            assert friend_status["time_amount"] == 7 and friend_status["time_unit"] == "days"
            assert 0 < friend_status["seconds_left"] <= 600
        """)
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env.update({
                "WORLDWALKER_DATA_DIR": str(Path(td) / "data"),
                "WORLDWALKER_ACCOUNTS_ENABLED": "1",
                "WORLDWALKER_SECURE_COOKIES": "0",
                "WORLDWALKER_MAX_ACCOUNTS": "10",
            })
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=ROOT, env=env,
                capture_output=True, text=True, timeout=90,
            )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)


if __name__ == "__main__":
    unittest.main()
