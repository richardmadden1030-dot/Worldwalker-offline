"""Offline Mode: structured, model-free play over Worldwalker's existing systems.

Living Adventures remains the primary resolver so offline actions advance the
same calendar, training, world clocks, economy, missions, travel, Chronicle and
tactical combat used by normal Worldwalker. This layer catalogs those actions,
adds bounded social play, and closes AI-only live canon-event scenes through
explicit conservative player choices rather than invented prose.
"""
from __future__ import annotations
import copy

from living_adventures import (action_list, action_spec, available_people,
                               location_node, location_view, resolve, route_options,
                               _local_turn)
from simulation_integrity import build_travel_graph

CATEGORY_META = {
    "recommended": ("For You", "Best next choices from your current situation."),
    "activities": ("Activities", "Useful things to do where you are."),
    "people": ("People", "Spend time with people who are actually available here."),
    "training": ("Training", "Develop your existing world-native attributes and powers."),
    "travel": ("Travel", "Move through established routes on the Living Atlas."),
    "missions": ("Missions & Work", "Accept or advance grounded local work."),
    "organization": ("Organization", "Review your team, guild, crew, division or faction responsibilities."),
    "property": ("Property & Economy", "Use established holdings, production and local commerce."),
    "combat": ("Combat", "Return to a current fight or seek nonlethal practice."),
    "world": ("World", "Explore, prepare and respond to wider-world pressure."),
}

def _obj(v): return v if isinstance(v, dict) else {}
def _text(v): return str(v or "").strip()

def enabled(game): return bool(game.settings.get("offline_mode", True))

def _category_for(action_id):
    if action_id.startswith(("train:", "path:")): return "training"
    if action_id.startswith("talk:"): return "people"
    if action_id.startswith("mission:"): return "missions"
    if action_id.startswith(("purchase:", "property:", "craft:")): return "property"
    if action_id.startswith("journey:"): return "travel"
    if action_id.startswith("rest:") or action_id in {"scout", "prepare", "activity:resume", "activity:cancel"}: return "activities"
    if action_id.startswith("expedition:"): return "missions"
    if action_id.startswith(("conflict:", "reputation:", "offline:event:")): return "world"
    if action_id.startswith(("organization:", "command:")): return "organization"
    return "activities"

def _decorate(row,category=None,source="living_adventures"):
    r=copy.deepcopy(row);r["category"]=category or _category_for(_text(r.get("id")));r["source"]=source
    r.setdefault("description","Available from the current campaign state.");r.setdefault("minutes",0);r.setdefault("risk","")
    return r

def _relationship_score(state,name):
    row=_obj(_obj(state.get("relationships")).get(name))
    try:return int(row.get("score",row.get("affinity",0)) or 0)
    except Exception:return 0

def _person_actions(state,person):
    name=person["name"];score=_relationship_score(state,name)
    actions=[
        {"id":f"offline:social:spend:{name}","label":f"Spend time with {name}","description":"Share an ordinary hour together. Repeated same-day social farming has diminishing value.","minutes":60},
        {"id":f"offline:social:goals:{name}","label":f"Ask what {name} is focused on","description":"Review this person's established public goal or current concern without inventing private knowledge.","minutes":15},
        {"id":f"offline:social:train:{name}","label":f"Train with {name}","description":"Practice together. The existing training system owns actual character growth.","minutes":120},
    ]
    if score>=20:actions.append({"id":f"offline:social:help:{name}","label":f"Offer meaningful help to {name}","description":"Help with an established goal when one exists. This strengthens the relationship only when there is something concrete to help with.","minutes":60})
    return [_decorate(a,"people","offline_social") for a in actions]

def _navigation_actions(state):
    rows=[];org=state.get("_organization_roster") or {}
    if org.get("members") or state.get("organizations"):
        rows.append(_decorate({"id":"offline:navigate:organization","label":f"Review {org.get('label') or 'organization'}","description":"Open the existing Team/organization systems. Official membership remains engine-owned.","minutes":0},"organization","navigation"))
    if state.get("properties") or state.get("property_economy") or state.get("shops"):
        rows.append(_decorate({"id":"offline:navigate:property","label":"Review property & economy","description":"Open your established holdings, production and local economy information.","minutes":0},"property","navigation"))
    if _obj(state.get("combat")).get("active"):
        rows.append(_decorate({"id":"offline:navigate:combat","label":"Return to active combat","description":"Open the existing combat/tactical controls. Offline Mode never auto-resolves a tactical fight.","minutes":0},"combat","navigation"))
    return rows

def _travel_actions(state):
    if _obj(state.get("combat")).get("active"):return []
    origin=location_node(state)["name"];graph=build_travel_graph(state);edges=graph.get("edges",{}).get(origin,[]);rows=[]
    for edge in edges[:12]:
        dest=edge.get("to")
        if not dest:continue
        routes=route_options(state,dest,"normal","").get("routes",[]);route=next((r for r in routes if r.get("available")),None)
        if route:rows.append(_decorate({"id":f"offline:travel:{route['id']}","label":f"Travel to {dest}","description":f"{route.get('label','Mapped route')} · {route.get('minutes',0)} min · exposure {route.get('exposure',0)}.","minutes":route.get("minutes",0),"destination":dest,"route_id":route["id"],"preparation":"normal"},"travel","offline_travel"))
    return rows

def _event_actions(state):
    title=_text(state.get("active_canon_event"));prompt=_text(state.get("active_event_prompt"));context=_text(state.get("active_event_context"))
    if not title:return []
    detail=prompt or context or "A major canon event has reached your current position."
    return [
        _decorate({"id":"offline:event:engage","label":f"Take part in {title}","description":detail+" Record active involvement without inventing an unearned canon outcome.","minutes":0},"world","offline_event"),
        _decorate({"id":"offline:event:support","label":"Act cautiously within your role","description":"Stay involved, prioritize immediate responsibilities and safety, and let established world state determine the wider event.","minutes":0},"world","offline_event"),
        _decorate({"id":"offline:event:withdraw","label":"Disengage from the event","description":"Leave, refuse involvement, or remain out of the scene. The wider canon event continues without direct player participation.","minutes":0},"world","offline_event"),
    ]

def _event_catalog(game,place):
    rows=_event_actions(game.state);first=copy.deepcopy(rows[0]);first["original_category"]="world";first["category"]="recommended"
    actions=[first,*rows];counts={key:sum(1 for r in actions if r.get("category")==key) for key in CATEGORY_META}
    cats=[{"id":key,"label":label,"description":desc,"count":counts[key]} for key,(label,desc) in CATEGORY_META.items() if counts[key]]
    return {"offline_mode":True,"location":place,"world":game.state.get("world"),"categories":cats,"actions":actions,"location_view":location_view(game.state,place),"active_canon_event":game.state.get("active_canon_event")}

def catalog(game):
    state=game.state
    if not game.campaign_active:return {"offline_mode":enabled(game),"categories":[],"actions":[],"location":""}
    place=location_node(state)["name"];public=game.public_state()
    if _obj(state.get("combat")).get("active"):
        actions=_navigation_actions(public);counts={key:sum(1 for r in actions if r.get("category")==key) for key in CATEGORY_META};cats=[{"id":key,"label":label,"description":desc,"count":counts[key]} for key,(label,desc) in CATEGORY_META.items() if counts[key]]
        return {"offline_mode":enabled(game),"location":place,"world":state.get("world"),"categories":cats,"actions":actions,"location_view":location_view(state,place)}
    if _text(state.get("active_canon_event")):return _event_catalog(game,place)
    base=[_decorate(row) for row in action_list(state,place)];people=[]
    for person in available_people(state,place)[:20]:people.extend(_person_actions(state,person))
    actions=base+people+_travel_actions(state)+_navigation_actions(public);seen=set();dedup=[]
    for row in actions:
        key=(row.get("id"),row.get("label"))
        if key in seen:continue
        seen.add(key);dedup.append(row)
    priority=[]
    for prefixes in (("activity:resume","journey:resume"),("mission:","expedition:"),("rest:",),("train:","path:"),("offline:social:",),("offline:travel:",)):
        match=next((r for r in dedup if any(_text(r.get("id")).startswith(p) for p in prefixes)),None)
        if match and match not in priority:
            copy_row=copy.deepcopy(match);copy_row["original_category"]=match.get("category");copy_row["category"]="recommended";priority.append(copy_row)
        if len(priority)>=5:break
    all_actions=priority+dedup;counts={key:sum(1 for r in all_actions if r.get("category")==key) for key in CATEGORY_META}
    cats=[{"id":key,"label":label,"description":desc,"count":counts[key]} for key,(label,desc) in CATEGORY_META.items() if counts[key] or key in {"recommended","activities"}]
    return {"offline_mode":enabled(game),"location":place,"world":state.get("world"),"categories":cats,"actions":all_actions,"location_view":location_view(state,place)}

def _resolve_event(game,action_id):
    state=game.state;title=_text(state.get("active_canon_event"));context=_text(state.get("active_event_context"))
    if not title:raise ValueError("No canon event is currently waiting for a decision.")
    choice=action_id.rsplit(":",1)[-1]
    if choice=="engage":summary=f"You choose to take an active role in {title}. Your participation is recorded, but Offline Mode does not invent a specific canon-changing victory or failure that the local rules did not establish."
    elif choice=="support":summary=f"You remain involved in {title} while acting cautiously within your established role and capabilities. The wider event continues from the world's existing facts rather than a generated rewrite."
    elif choice=="withdraw":summary=f"You disengage from {title}. You are no longer personally inside the live scene; later consequences can reach you through normal world-state systems."
    else:raise ValueError("Choose one of the available canon-event responses.")
    history=state.setdefault("canon_event_participation",[]);history.append({"title":title,"choice":choice,"canon_day":state.get("canon_day"),"location":state.get("location"),"context":context[:600]});state["canon_event_participation"]=history[-120:]
    game.append(f"[CANON EVENT — {title}]\n{summary}","narrative",canon_day=state.get("canon_day"))
    state["active_canon_event"]="";state["active_event_context"]="";state["active_event_prompt"]="";state["canon_event_engagement_count"]=0;game.autosave()
    return {"narrative":summary,"event_concluded":True,"generated_locally":True,"state":game.public_state(),"story":game._flush_story()}

def _social_resolve(game,action_id):
    _,_,kind,name=action_id.split(":",3);state=game.state;place=location_node(state)["name"]
    if _obj(state.get("combat")).get("active"):raise ValueError("Finish the active encounter before spending time socially.")
    available={p["name"]:p for p in available_people(state,place)}
    if name not in available:raise ValueError("That person is not currently available here.")
    today=int(state.get("canon_day",0) or 0);ledger=state.setdefault("offline_social_activity",{});key=f"{name}:{today}";count=int(ledger.get(key,0) or 0);relation=state.setdefault("relationships",{}).setdefault(name,{"score":0})
    if not isinstance(relation,dict):relation=state["relationships"][name]={"score":0}
    goal=_text(available[name].get("goal"))
    if kind=="goals":return _local_turn(game,f"You ask {name} what is occupying their attention. "+(f"Their established concern is: {goal}." if goal else "They have no concrete public request recorded right now."),15)
    if kind=="train":
        stats=list(_obj(state.get("stats")))
        if not stats:raise ValueError("This character has no trainable attributes recorded.")
        stat=max(stats,key=lambda x:float(_obj(state.get("stats")).get(x,0) or 0));spec=action_spec(state,{"place":place,"action":"train:"+stat});result=resolve(game,{"place":place,"action":"train:"+stat},spec)
        if count<2:relation["score"]=min(100,int(relation.get("score",0) or 0)+1)
        ledger[key]=count+1;result["state"]=game.public_state();return result
    if kind=="help" and not goal:raise ValueError(f"{name} has no established public goal to help with right now.")
    gain=0 if count>=2 else (2 if kind=="help" else 1);label=(f"You spend an unhurried hour with {name}." if kind=="spend" else f"You help {name} make practical progress toward: {goal}.");result=_local_turn(game,label,60);relation["score"]=min(100,int(relation.get("score",0) or 0)+gain);ledger[key]=count+1
    if gain:game.append(f"Your relationship with {name} strengthens through time actually spent together.","system",canon_day=state.get("canon_day"))
    result["story"]=list(result.get("story",[]))+game._flush_story();result["state"]=game.public_state();return result

def resolve_action(game,payload):
    if not enabled(game):raise ValueError("Offline Mode is not enabled.")
    if not game.campaign_active:raise ValueError("Start or load a campaign first.")
    action_id=_text(payload.get("id"));place=location_node(game.state)["name"]
    if not action_id:raise ValueError("Choose an offline activity.")
    if action_id.startswith("offline:navigate:"):return {"status":"navigation","target":action_id.rsplit(":",1)[-1],"state":game.public_state(),"story":[]}
    if _obj(game.state.get("combat")).get("active"):raise ValueError("Finish the active tactical encounter before taking another world action.")
    if action_id.startswith("offline:event:"):return _resolve_event(game,action_id)
    if _text(game.state.get("active_canon_event")):raise ValueError("Resolve the active canon event before taking another world action.")
    if action_id.startswith("offline:social:"):return _social_resolve(game,action_id)
    if action_id.startswith("offline:travel:"):
        destination=_text(payload.get("destination"));route_id=_text(payload.get("route_id"));request={"place":place,"action":"journey:start","destination":destination,"route_id":route_id,"preparation":payload.get("preparation","normal"),"companion":payload.get("companion","")};spec=action_spec(game.state,request);return resolve(game,request,spec)
    spec=action_spec(game.state,{"place":place,"action":action_id});return resolve(game,{"place":place,"action":action_id},spec)

def opening(game):
    s=game.state;name=_text(s.get("name")) or "Traveler";place=_text(s.get("location"))
    if not _text(s.get("age")):
        defaults={"Naruto":"16","Jujutsu Kaisen":"16","Hunter x Hunter":"18","One Piece":"18","Bleach":"18","Overgeared":"20","Solo Max-Level Newbie":"20","Reincarnated as a Slime":"20"};s["age"]=defaults.get(s.get("world"),"18")
    if not _text(s.get("appearance_desc")):s["appearance_desc"]="A capable traveler whose appearance reflects the background and equipment chosen at creation."
    if not _text(s.get("background")):s["background"]="A local newcomer with enough preparation to begin pursuing opportunities in this world."
    s["opening_complete"]=True;s["offline_mode"]=True;local=location_view(s,place);services=", ".join(local.get("services",[])[:3]);lead=next((r for r in local.get("actions",[]) if r.get("id","").startswith(("mission:","expedition:","conflict:"))),None)
    narrative=f"{name} begins at {place}. {services or 'The surrounding area'} gives you practical ways to recover, train, investigate and meet people without waiting for a narrator."
    if lead:narrative+=f" One immediate opportunity stands out: {lead.get('label')}."
    narrative+=" Choose Activities to decide what happens next; the Chronicle records only outcomes the game actually resolves.";game.append(narrative,"narrative",canon_day=s.get("canon_day"));game.autosave()
    return {"narrative":narrative,"state":game.public_state(),"story":game._flush_story(),"generated_locally":True,"offline_catalog":catalog(game)}
