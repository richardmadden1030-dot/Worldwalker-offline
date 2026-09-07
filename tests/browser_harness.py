"""Deterministic narrator used only for manual multi-world browser QA."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app as app_module


class BrowserNarrator:
    model = "browser-qa"
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "uncached_input_tokens": 0,
             "output_tokens": 0, "calls": 0, "cost_usd": 0.0, "cost_unknown": False,
             "cost_is_conservative": False}

    def request(self, rules, payload, max_output_tokens=0):
        task = payload.get("task")
        state = payload.get("state") or payload.get("state_before") or {}
        world = state.get("world", "the world")
        name = state.get("name", "the traveler")
        archetype = str((state.get("special") or {}).get("Archetype") or "")
        if task == "advisor_question":
            return {
                "summary": f"Your strongest immediate option in {world} is to follow the established lead while preserving enough resources for the next canon pressure point.",
                "points": [
                    "Your current stats and recorded skills are the authoritative measure of your capabilities.",
                    "A prepared approach can improve the consequence even when another character refuses your request.",
                    "The next major event countdown should determine whether you train first or act immediately.",
                ],
                "follow_ups": ["What is my safest next move?", "How do I prepare for the next canon event?"],
                "chart": None,
            }
        if task == "opening":
            openings = {
                "Naruto": (
                    f"Morning mist hangs between Konohagakure's tiled roofs as {name} reaches the mission board. A breathless courier reports that a border scout missed two check-ins, while a veteran instructor offers focused chakra practice before the search party leaves.",
                    ["Question the courier about the missing scout", "Train with the veteran before the search party leaves", "Inspect the departure route for signs of an ambush"],
                ),
                "Bleach": (
                    f"A practice bell crosses Shin'o Academy as {name} completes a final Kido drill. Division representatives arrive with assignment records, while an instructor quietly offers one last chance to demonstrate control before recommendations are sealed.",
                    ["Ask about the division assignments", "Practice Hado #4 with the instructor", "Speak to a seated officer about squad life"],
                ),
                "Overgeared": (
                    (f"A contract sigil glows in Winston's adventurers' hall as {name} and Lumen Wisp face their first live formation test. A scout needs a summoned partner to trace a monster route without alarming the market district."
                     if archetype == "Summoner" else
                     f"A new notice appears in Winston's adventurers' hall as {name} finds an opportunity suited to the {archetype or 'adventurer'} class. The request rewards the class's actual contribution rather than forcing a production route."),
                    (["Train a moving formation with Lumen Wisp", "Ask the scout what spoor the summon must follow", "Accept the tracking contract"]
                     if archetype == "Summoner" else
                     ["Study the class-suited request", "Ask the client what went wrong before", "Prepare the class's strongest approach"]),
                ),
                "Solo Max-Level Newbie": (
                    f"The Tower's first-floor gate ignites above Seoul as {name} recognizes a hidden-condition marker no ordinary climber notices. A frightened beginner group gathers nearby while the public countdown continues.",
                    ["Inspect the hidden-condition marker", "Organize the beginner group", "Enter the first-floor trial"],
                ),
            }
            narrative, suggestions = openings.get(world, (
                f"Salt wind crosses the harbor as {name} watches a damaged courier boat drift toward the quay. Its lone deckhand carries a sealed route ledger, and a local navigator offers a safer path before patrols arrive.",
                ["Question the deckhand about the damaged boat", "Ask the navigator to chart the safer route", "Inspect the route ledger before patrols arrive"],
            ))
            return {"narrative": narrative, "state_patch": {"appearance_desc": state.get("appearance_desc") or "A capable young traveler in practical local clothing."},
                    "events": [], "timeline_event": "", "suggested_actions": suggestions}
        if task == "assess_time_skip":
            actions = payload.get("planned_actions", [])
            hard = any("guardian" in str(action).lower() or "elite" in str(action).lower() for action in actions)
            checks = []
            if hard:
                ability = {"Naruto": "Taijutsu", "Bleach": "Zanjutsu",
                           "Overgeared": "Strength", "Solo Max-Level Newbie": "Strength"}.get(world, "Strength")
                checks.append({"id": "elite-check", "reason": "Overcome the elite guardian", "ability": ability, "skill": None,
                               "difficulty_min": 84, "difficulty_max": 88, "relevant_average_stat": 35,
                               "situational_bonus": 0, "time_difficulty_modifier": 0, "major_event": False,
                               "major_reason": "", "lethal_risk": "moderate", "lethal_warning": "The guardian can inflict a serious wound."})
            return {"checks": checks, "fixed_facts": "The listed actions remain in order.",
                    "simulation_notes": "World actors continue independently.", "reachable_actions": actions, "deferred_actions": []}
        if task == "resolve_time_skip":
            actions = payload.get("planned_actions", [])
            event_mode = payload.get("next_major_event_mode", {}).get("enabled")
            route_name = {"Naruto": "eastern road", "Bleach": "academy courtyard",
                          "Overgeared": "Winston workshop lane", "Solo Max-Level Newbie": "first-floor gate"}.get(world, "outer harbor channel")
            updates = []
            for index, action in enumerate(actions or ["Continue the prior course"]):
                updates.append({"sequence": index + 1, "type": "action", "title": "Plan advances", "related_action": action,
                                "narrative": f"{name} works through: {action}. The result follows the time available and the supplied check rather than assuming instant completion.",
                                "why_it_matters": "The action changes what nearby people can reasonably observe and respond to.",
                                "player_knowledge": "The immediate result is directly witnessed; distant motives remain uncertain.",
                                "next_pressure": "A competing group is moving toward the same objective."})
            updates.append({"sequence": 20, "type": "faction_reaction", "title": "A rival group moves", "related_action": "",
                            "narrative": f"Several hours later, a reliable witness reports that another team left by the {route_name}. The witness saw their departure but does not know their orders.",
                            "why_it_matters": "The route may become contested.", "player_knowledge": "The departure is confirmed; its purpose is only an inference.",
                            "next_pressure": "Reaching the next landmark first now has value."})
            if world == "Naruto":
                quest = {"name": "The Missing Scout", "status": "Active", "category": "main",
                         "explanation": "A border scout missed two scheduled reports after investigating damaged signal posts.",
                         "giver": "Village courier", "first_step": "Inspect the eastern signal post",
                         "current_knowledge": ["The scout was last seen taking the eastern road", "Two signal posts stopped responding"],
                         "clear_conditions": ["Locate the scout", "Determine what disabled the signal posts"],
                         "objectives": [{"id": "find", "text": "Locate the missing scout", "status": "active", "optional": False, "progress": 20},
                                        {"id": "cause", "text": "Identify who damaged the signal posts", "status": "locked", "optional": False, "progress": 0}],
                         "branch_state": {"current": "search", "available": ["Follow the road", "Question nearby patrols"], "locked": ["Confront the saboteur"]},
                         "locations": [state.get("location", "Starting Region")], "risks": ["Unknown hostile presence"]}
                suggestions = ["Follow the eastern road before the rival team gains distance", "Ask the veteran to identify the signal damage", "Question the courier about the scout's usual contacts"]
            elif world == "Bleach":
                quest = {"name": "Choose a Gotei 13 Division", "status": "Active", "category": "main",
                         "explanation": "Graduation is near, and the player must earn recommendations before choosing a fitting division.",
                         "giver": "Shin'o Academy", "first_step": "Speak with the visiting division representatives",
                         "current_knowledge": ["Recommendations reflect demonstrated strengths", "Talented graduates may influence placement"],
                         "clear_conditions": ["Complete graduation evaluation", "Choose or accept a division assignment"],
                         "objectives": [], "branch_state": {"current": "evaluation", "available": ["Kido demonstration", "Officer interview"], "locked": []},
                         "locations": [state.get("location", "Shin'o Academy")], "risks": ["A poor demonstration narrows choices"]}
                suggestions = ["Demonstrate Kido control", "Interview a division representative", "Ask an instructor for a recommendation"]
            elif world == "Overgeared":
                if archetype == "Summoner":
                    quest = {"name": "The Market-Route Trace", "status": "Active", "category": "main",
                             "explanation": "A scout needs Lumen Wisp to trace a monster route without panicking Winston's crowded market.",
                             "giver": "Winston scout", "first_step": "Establish a controlled search formation with Lumen Wisp",
                             "current_knowledge": ["The spoor crosses a crowded route and requires a calm contracted creature"],
                             "clear_conditions": ["Trace the monster route", "Keep Lumen Wisp under safe field control"],
                             "objectives": [{"id": "trace", "text": "Trace the route with Lumen Wisp", "status": "active", "progress": 20}],
                             "branch_state": {"current": "contract", "available": ["Wide search", "Close formation"], "locked": []},
                             "locations": [state.get("location", "Winston")], "risks": ["Crowds can disrupt the contract link"]}
                    suggestions = ["Run a close formation with Lumen Wisp", "Ask the scout to mark the last confirmed spoor", "Use Contract Command to search without alarming civilians"]
                else:
                    quest = {"name": f"A {archetype or 'Class'} Opportunity", "status": "Active", "category": "main",
                             "explanation": f"A Winston client has posted work suited to a {archetype or 'new adventurer'} rather than a production specialist.",
                             "giver": "Winston adventurers' hall", "first_step": "Review the request and choose a class-suited approach",
                             "current_knowledge": ["The request recognizes non-production contributions"],
                             "clear_conditions": ["Complete the request through the chosen class role"],
                             "objectives": [{"id": "role", "text": "Contribute through the selected class", "status": "active", "progress": 20}],
                             "branch_state": {"current": "role", "available": ["Direct approach", "Prepared approach"], "locked": []},
                             "locations": [state.get("location", "Winston")], "risks": ["A rival party is interested"]}
                    suggestions = ["Use a class feature on the request", "Ask the client for the missing detail", "Coordinate with a suitable party member"]
            elif world == "Solo Max-Level Newbie":
                quest = {"name": "Clear the First-Floor Trial", "status": "Active", "category": "main",
                         "explanation": "The Tower countdown has begun, and the first trial contains a discoverable hidden condition.",
                         "giver": "Tower System", "first_step": "Inspect the gate before entering",
                         "current_knowledge": ["A hidden marker is visible near the gate"],
                         "clear_conditions": ["Clear the floor trial"],
                         "objectives": [{"id": "clear", "text": "Clear the first floor", "status": "active", "progress": 10}],
                         "branch_state": {"current": "entry", "available": ["Inspect marker", "Enter trial"], "locked": []},
                         "locations": [state.get("location", "Tower Entrance")], "risks": ["Floor countdown"]}
                suggestions = ["Inspect the hidden marker", "Enter with the beginner group", "Prepare for the floor guardian"]
            else:
                quest = {"name": "The Damaged Courier Boat", "status": "Active", "category": "main",
                         "explanation": "A courier boat limped into port with a stolen route page and signs of a deliberate attack.",
                         "giver": "Harbor watch", "first_step": "Inspect the hull and question the deckhand",
                         "current_knowledge": ["The damage happened outside the harbor", "One Marine route page is missing"],
                         "clear_conditions": ["Identify who attacked the courier", "Recover or account for the missing page"],
                         "objectives": [{"id": "attack", "text": "Identify the attackers", "status": "active", "optional": False, "progress": 20},
                                        {"id": "ledger", "text": "Account for the missing route page", "status": "locked", "optional": False, "progress": 0}],
                         "branch_state": {"current": "investigate", "available": ["Inspect the boat", "Question harbor witnesses"], "locked": ["Confront the attackers"]},
                         "locations": [state.get("location", "Starting Region")], "risks": ["Unknown vessel offshore"]}
                suggestions = ["Inspect the courier boat before the tide changes", "Ask the navigator to chart the attack route", "Question harbor witnesses about the rival vessel"]
            earned_events = []
            if world == "Overgeared":
                title = "Contract Formation Novice" if archetype == "Summoner" else f"Recognized {archetype or 'Adventurer'}"
                earned_events = [{"type": "title", "title": title, "message": f"Title acquired: {title}"}]
            elif world == "Solo Max-Level Newbie":
                earned_events = [{"type": "title", "title": "Hidden-Route Analyst", "message": "Title acquired: Hidden-Route Analyst"}]
            return {"narrative": "The ordered plan produces several distinct developments and ends at a clear decision point.",
                    "updates": updates, "state_patch": {"quests": [quest], "factions": {"Eastern Rivals": {"status": "active"}},
                                                       "npc_memories": {"Village Courier": {"goal": "Find the missing scout", "importance": "major", "attitude": "Concerned"}}},
                    "events": earned_events, "timeline_events": [], "elapsed": {"amount": 2 if event_mode else 4, "unit": "hours"},
                    "interrupted": False, "interruption_reason": "", "intervention_prompt": "",
                    "major_event_reached": bool(event_mode), "major_event_kind": "personal" if event_mode else "",
                    "major_event_title": "The Scout's Signal Returns" if event_mode else "",
                    "goal_status": {}, "new_contacts": [], "incoming_chats": [], "completed_actions": actions,
                    "deferred_actions": [],
                    "suggested_actions": suggestions}
        return {"narrative": "The situation remains stable.", "state_patch": {}, "events": [],
                "suggested_actions": ["Follow the strongest visible lead", "Prepare for the next obstacle", "Ask a local witness for details"]}


game = app_module.game
game.settings.update({"provider": "local", "model": "browser-qa", "secondary_model": ""})
game.ai = BrowserNarrator()
game.ai_bg = BrowserNarrator()
game.ai_major = BrowserNarrator()

if __name__ == "__main__":
    app_module.app.run(host="127.0.0.1", port=int(os.environ.get("WW_QA_PORT", "8765")), debug=False, use_reloader=False)
