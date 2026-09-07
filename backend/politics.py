"""Lightweight narrative polity and territorial-control support.

This deliberately is not a second strategy game.  The narrator decides what
happens in the fiction; this module keeps the resulting ownership visible on
the atlas, makes a player-founded realm a first-class faction, and schedules
occasional natural-language reports for rulers without exposing management
scores in the interface.
"""
import copy
import re


PEOPLE_REPORT_INTERVAL_DAYS = 90
CLAIM_SIZES = {
    "holding": 6.0,
    "district": 7.5,
    "village": 9.0,
    "town": 10.5,
    "city": 12.5,
    "island": 14.5,
    "province": 17.0,
    "country": 22.0,
    "nation": 22.0,
    "realm": 27.0,
    "continent": 34.0,
}

# Canon publications establish the relative placement of the five great
# countries and several smaller neighbors, but do not provide survey-grade
# borders. These polygons follow those published silhouettes on the game's
# label-free Naruto atlas. They are deliberately kept separate from the
# background art so a campaign can repaint or annex them narratively.
NARUTO_CANON_TERRITORY_POLYGONS = {
    "Konohagakure": [[39, 31], [55, 27], [68, 37], [68, 61], [59, 70], [42, 68], [33, 55], [34, 40]],
    "Sunagakure": [[0, 40], [23, 39], [34, 48], [42, 68], [35, 91], [0, 91]],
    "Kirigakure": [[73, 35], [100, 28], [100, 82], [73, 78], [68, 60]],
    "Kumogakure": [[59, 0], [91, 0], [92, 32], [77, 43], [68, 37], [55, 27]],
    "Iwagakure": [[0, 0], [39, 0], [42, 25], [34, 40], [23, 39], [0, 40]],
    "Amegakure": [[24, 35], [34, 32], [39, 40], [36, 58], [28, 58], [22, 48]],
    "Iron Country": [[38, 0], [59, 0], [55, 27], [42, 25]],
}
CANON_TERRITORY_POLYGONS = {
    "Naruto": NARUTO_CANON_TERRITORY_POLYGONS,
    # These are atlas silhouettes, not claims of survey-grade canon borders.
    # They prevent city-sized holdings from becoming overlapping circles and
    # remain repaintable when narrative ownership changes.
    "Bleach": {
        "Rukongai": [[7,8],[93,8],[97,50],[89,88],[11,88],[3,50]],
        "Seireitei": [[31,27],[69,27],[76,50],[68,72],[32,72],[24,50]],
        "Shin'o Academy": [[34,35],[48,35],[48,49],[34,49]],
        "Senzaikyu": [[40,53],[49,53],[49,65],[40,65]],
        "Central 46 Chambers": [[47,52],[56,52],[56,64],[47,64]],
    },
    "Reincarnated as a Slime": {
        "Great Jura Forest": [[33,28],[65,27],[74,43],[66,64],[39,65],[27,48]],
        "Tempest": [[45,42],[61,41],[64,54],[47,57]],
        "Kingdom of Falmuth": [[64,36],[87,36],[90,60],[67,64]],
        "Dwargon": [[42,8],[66,7],[68,28],[42,31]],
        "Holy Empire of Lubelius": [[13,17],[38,15],[39,38],[19,43]],
        "Eurazania": [[56,60],[79,58],[84,86],[54,87]],
        "Jistav": [[63,18],[83,17],[87,38],[66,39]],
        "El Dorado": [[1,61],[25,58],[31,91],[0,93]],
    },
    "Overgeared": {
        "Saharan Empire": [[35,15],[77,13],[88,46],[72,69],[39,65],[28,39]],
        "Reidan": [[14,43],[36,39],[39,66],[16,72]],
        "Reinhardt": [[39,54],[65,52],[67,77],[42,81]],
        "Valhalla": [[63,28],[90,28],[94,59],[71,65]],
    },
}
LEADER_WORDS = {
    "ruler", "leader", "founder", "sovereign", "king", "queen", "emperor",
    "empress", "president", "governor", "lord", "lady", "chief", "daimyo",
    "hokage", "kazekage", "mizukage", "raikage", "tsuchikage", "monarch",
}


def _number(value, default, low, high):
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _day(state):
    try:
        return float(state.get("canon_day", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "territory"


def _rank_is_leader(value):
    words = set(re.findall(r"[a-z]+", str(value).lower()))
    return bool(words & LEADER_WORDS)


def player_led_polities(state):
    """Return polities the campaign has established the player truly leads.

    An explicit hidden flag is preferred.  Rank inference is a fallback for
    older saves and ordinary affiliation updates, never a number shown to the
    player.
    """
    result = set()
    polity_state = state.get("polity_state") if isinstance(state.get("polity_state"), dict) else {}
    for name, polity in polity_state.items():
        if isinstance(polity, dict) and polity.get("player_led") is True:
            result.add(str(name))
    for affiliation in state.get("affiliations", []) or []:
        if not isinstance(affiliation, dict) or str(affiliation.get("status", "active")).lower() not in {"active", "honorary"}:
            continue
        name = str(affiliation.get("faction") or affiliation.get("name") or "").strip()
        if name and _rank_is_leader(affiliation.get("rank") or affiliation.get("role")):
            result.add(name)
    position = state.get("position")
    if isinstance(position, dict):
        faction = str(position.get("faction") or "").strip()
        if faction and _rank_is_leader(position.get("rank") or position.get("title")):
            result.add(faction)
    return result


def _clock(name):
    return {
        "name": name, "kind": "faction", "goal": f"Advance {name}'s current agenda",
        "progress": 0, "threshold": 100, "status": "active",
        "last_update": "Not yet advanced", "method": "organized effort",
        "target_location": "", "travel_remaining_days": 0, "dependencies": [],
        "resources": {"capacity": 50}, "resource_cost": {},
    }


def _ensure_first_class_faction(state, name):
    """Make every land-owning polity visible to the same GM systems as canon powers."""
    name = str(name or "").strip()
    if not name or name.lower() == "unknown":
        return
    factions = state.setdefault("factions", {})
    if isinstance(factions, dict):
        existing = factions.get(name)
        if not isinstance(existing, dict):
            factions[name] = {"name": name, "status": "active", "goal": f"Protect and advance {name}'s interests"}
        else:
            existing.setdefault("name", name)
            existing.setdefault("status", "active")
    clocks = state.setdefault("faction_clocks", {})
    if isinstance(clocks, dict):
        clocks.setdefault(name, _clock(name))


def _clean_region(raw, index):
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("territory") or raw.get("anchor") or "").strip()
    controller = str(raw.get("controller") or raw.get("controlling_faction") or "").strip()
    if not name or not controller:
        return None
    scale = str(raw.get("scale") or raw.get("scope") or "").strip().lower()
    default_size = CLAIM_SIZES.get(scale, 12.5)
    authored_hexes = int(_number(raw.get("hex_count"), 0, 0, 900))
    if raw.get("player_founded"):
        authored_hexes = max(1, authored_hexes)
    cleaned = {
        "id": str(raw.get("id") or f"{_slug(controller)}-{_slug(name)}-{index}")[:100],
        "name": name[:160],
        "controller": controller[:160],
        "status": str(raw.get("status") or "active").lower()[:40],
        "anchor": str(raw.get("anchor") or raw.get("source_location") or name)[:160],
        "scale": scale if scale in CLAIM_SIZES else "region",
        "size": _number(raw.get("size"), default_size, 4.0, 42.0),
        # An authored hex_count is exact. New player holdings begin at one
        # atlas hex and grow only when later narrative control expands them.
        "hex_count": authored_hexes,
        "player_founded": bool(raw.get("player_founded", False)),
        "upgrades": [_text[:300] for _text in raw.get("upgrades", []) if isinstance(_text, str) and _text.strip()][:30] if isinstance(raw.get("upgrades"), list) else [],
    }
    if raw.get("x") is not None:
        cleaned["x"] = _number(raw.get("x"), 50.0, 0.0, 100.0)
    if raw.get("y") is not None:
        cleaned["y"] = _number(raw.get("y"), 50.0, 0.0, 100.0)
    polygon = raw.get("polygon")
    if isinstance(polygon, list):
        points = []
        for point in polygon[:80]:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append([_number(point[0], 50, 0, 100), _number(point[1], 50, 0, 100)])
            elif isinstance(point, dict):
                points.append([_number(point.get("x"), 50, 0, 100), _number(point.get("y"), 50, 0, 100)])
        if len(points) >= 3:
            cleaned["polygon"] = points
    contested = raw.get("contested_by")
    if isinstance(contested, list):
        cleaned["contested_by"] = [str(value).strip()[:160] for value in contested if str(value).strip()][:8]
    if raw.get("parent_id"):
        cleaned["parent_id"] = str(raw.get("parent_id"))[:100]
    for key in ("world", "board", "realm"):
        if raw.get(key): cleaned[key] = str(raw[key])[:100]
    for key in ("established_day", "controller_changed_turn"):
        if isinstance(raw.get(key), (int, float)):
            cleaned[key] = raw[key]
    return cleaned


def normalize_political_state(state, before=None):
    """Repair narrator-authored polity state and connect it to existing systems."""
    changes = []
    day = _day(state)
    raw_polities = state.get("polity_state")
    if not isinstance(raw_polities, dict):
        raw_polities = {}
        state["polity_state"] = raw_polities
        changes.append("Repaired invalid polity state")
    old_polities = before.get("polity_state", {}) if isinstance(before, dict) and isinstance(before.get("polity_state"), dict) else {}
    cleaned_polities = {}
    for raw_name, raw in list(raw_polities.items())[:200]:
        name = str(raw_name or "").strip()[:160]
        if not name or not isinstance(raw, dict):
            continue
        old = old_polities.get(raw_name, {}) if isinstance(old_polities.get(raw_name), dict) else {}
        relationship = str(raw.get("people_relationship") or "cautiously accepting").strip()[:120]
        polity = {
            "people_relationship": relationship,
            "relationship_reason": str(raw.get("relationship_reason") or "Recent rule and local conditions shape public feeling.").strip()[:500],
            "player_led": bool(raw.get("player_led", False)),
            "last_people_report_day": _number(raw.get("last_people_report_day"), day, -1000000, 1000000),
            "reported_people_relationship": str(raw.get("reported_people_relationship") or relationship).strip()[:120],
            "pending_people_report": bool(raw.get("pending_people_report", False)),
        }
        if old and str(old.get("people_relationship") or "") != relationship:
            polity["pending_people_report"] = True
        elif isinstance(before, dict) and not old and polity["player_led"]:
            # Founding or taking over a polity is itself a rapid public change.
            polity["pending_people_report"] = True
        cleaned_polities[name] = polity
        _ensure_first_class_faction(state, name)
    state["polity_state"] = cleaned_polities

    regions = []
    seen = set()
    old_regions = {}
    if isinstance(before, dict) and isinstance(before.get("political_regions"), list):
        for row in before["political_regions"]:
            if isinstance(row, dict):
                old_regions[str(row.get("id") or row.get("name") or "").lower()] = row
    location_details = state.get("location_details") if isinstance(state.get("location_details"), dict) else {}
    detail_by_name = {str(name).strip().lower(): detail for name, detail in location_details.items() if isinstance(detail, dict)}
    for index, raw in enumerate(state.get("political_regions", []) if isinstance(state.get("political_regions"), list) else []):
        region = _clean_region(raw, index)
        if not region:
            continue
        # Synchronize newly changed location control, never stale details on
        # load. Substring matching can annex a distinct neighboring holding.
        anchor_key = str(region.get("anchor") or region.get("name") or "").strip().lower()
        detail = detail_by_name.get(anchor_key)
        old_details = before.get("location_details", {}) if isinstance(before, dict) else {}
        old_detail = next((v for k,v in old_details.items() if str(k).strip().lower()==anchor_key), None) if isinstance(old_details,dict) else None
        detail_turn=detail.get('controller_changed_turn') if isinstance(detail,dict) else None
        newer=isinstance(detail_turn,(int,float)) and detail_turn > region.get('controller_changed_turn',-1)
        if isinstance(detail, dict) and ("controlling_faction" in detail or detail.get("faction")) and ((isinstance(before,dict) and detail != old_detail) or newer):
            region["controller"] = str(detail.get("controlling_faction") or detail.get("faction") or "Unclaimed").strip()[:160]
            if isinstance(detail.get("controller_changed_turn"), (int, float)):
                region["controller_changed_turn"] = detail["controller_changed_turn"]
        key = region["id"].lower()
        if key in seen:
            continue
        prior = old_regions.get(key)
        if isinstance(before, dict) and (not prior or prior.get("controller") != region.get("controller")):
            region["controller_changed_turn"] = int(state.get("turn", 0) or 0)
        seen.add(key)
        regions.append(region)
        _ensure_first_class_faction(state, region["controller"])
    state["political_regions"] = regions[:300]

    # A controller written through the long-standing location_details route
    # is just as real as one created through a custom political region.
    for detail in (state.get("location_details") or {}).values():
        if isinstance(detail, dict):
            _ensure_first_class_faction(state, detail.get("controlling_faction") or detail.get("faction"))
    return changes


def political_regions_for_map(state, nodes):
    """Build public map geometry from canon holdings plus narrative claims."""
    node_by_name = {str(node.get("name", "")).lower(): node for node in nodes if isinstance(node, dict)}
    current = next((node for node in nodes if node.get("current")), None) or (nodes[0] if nodes else {"x": 50, "y": 50})
    regions = []
    explicit_anchors = set()
    for raw in state.get("political_regions", []) or []:
        if not isinstance(raw, dict):
            continue
        anchor_name = str(raw.get("anchor") or raw.get("name") or "").lower()
        matched_anchor = node_by_name.get(anchor_name) or next((node for key, node in node_by_name.items() if anchor_name and (anchor_name in key or key in anchor_name)), None)
        anchor = matched_anchor or current
        x = _number(raw.get("x"), _number(anchor.get("x"), 50, 0, 100), 0, 100)
        y = _number(raw.get("y"), _number(anchor.get("y"), 50, 0, 100), 0, 100)
        # normalize_political_state has already synchronized explicit
        # location_details changes. Keep this region's controller here so a
        # newly founded polity can claim land around a canon anchor without
        # the anchor's old default owner immediately overwriting that claim.
        controller = str(raw.get("controller") or "Unclaimed")
        polygon = raw.get("polygon") if isinstance(raw.get("polygon"), list) and len(raw.get("polygon")) >= 3 else None
        regions.append({
            "id": raw.get("id"), "name": raw.get("name"), "controller": controller,
            "x": x, "y": y, "size": _number(raw.get("size"), 12.5, 4, 42),
            "hex_count": max(0, int(raw.get("hex_count", 0) or 0)),
            "player_founded": bool(raw.get("player_founded", False)),
            "polygon": polygon, "geometry": "authored" if polygon else "strategic",
            "contested_by": list(raw.get("contested_by") or []),
            "recently_changed": bool(raw.get("controller_changed_turn") is not None and int(state.get("turn", 0) or 0) - int(raw.get("controller_changed_turn", 0)) <= 3),
        })
        explicit_anchors.add(anchor_name)
    kind_sizes = {"nation": 22, "region": 17, "island": 15, "village": 11, "city": 12, "floor": 12, "realm": 24}
    for node in nodes:
        controller = str(node.get("controller") or "").strip()
        if not controller or controller.lower() in {"unknown", "unclaimed"} or str(node.get("name", "")).lower() in explicit_anchors:
            continue
        kind = str(node.get("kind") or "").lower()
        tier = _number(node.get("tier"), 1, 1, 10)
        size = kind_sizes.get(kind, 8.5 + tier * 0.8)
        canon_polygon = CANON_TERRITORY_POLYGONS.get(str(state.get("world") or ""), {}).get(str(node.get("name") or ""))
        regions.append({
            "id": f"landmark-{_slug(node.get('name'))}", "name": node.get("name"),
            "controller": controller, "x": node.get("x", 50), "y": node.get("y", 50),
            "size": size, "polygon": canon_polygon, "geometry": "canon" if canon_polygon else "strategic",
            "contested_by": list(node.get("contested_by") or []), "recently_changed": bool(node.get("recently_changed")),
        })
    return regions


def transfer_territory(state, region_id, controller, contested_by=None):
    """Authoritative local annexation helper used by narrative state patches."""
    for region in state.get("political_regions", []) or []:
        if isinstance(region, dict) and str(region.get("id")) == str(region_id):
            previous = str(region.get("controller") or "Unclaimed")
            region["controller"] = str(controller)[:160]
            region["contested_by"] = [str(x)[:160] for x in (contested_by or []) if str(x).strip()][:8]
            region["controller_changed_turn"] = int(state.get("turn", 0) or 0)
            anchor = str(region.get("anchor") or region.get("name") or "").strip()
            if anchor:
                detail = state.setdefault("location_details", {}).setdefault(anchor, {})
                if isinstance(detail, dict):
                    detail["controlling_faction"] = str(controller)[:160]
                    detail["controller_changed_turn"] = int(state.get("turn", 0) or 0)
            _ensure_first_class_faction(state, controller)
            return {"region": region.get("name"), "from": previous, "to": controller}
    return None


def tick_polity_governance(state, elapsed_minutes=0, canon_controllers=None):
    """Return only the small Chronicle lines a land-owning ruler should see."""
    normalize_political_state(state)
    events = []
    day = _day(state)
    led = player_led_polities(state)
    holdings = {str(region.get("controller")) for region in state.get("political_regions", []) if isinstance(region, dict)}
    for detail in (state.get("location_details") or {}).values():
        if isinstance(detail, dict) and detail.get("controlling_faction"):
            holdings.add(str(detail["controlling_faction"]))
    # A canon holding may not have a location_details override yet.  Its
    # polity entry still counts as land-owning once leadership is established.
    holdings.update(str(name) for name in (canon_controllers or []) if name)
    holdings.update(name for name in led if name in state.get("polity_state", {}))
    for name in sorted(led & holdings):
        polity = state.setdefault("polity_state", {}).setdefault(name, {
            "people_relationship": "cautiously accepting", "relationship_reason": "The public is still judging the new rule.",
            "player_led": True, "last_people_report_day": day,
            "reported_people_relationship": "cautiously accepting", "pending_people_report": True,
        })
        last = _number(polity.get("last_people_report_day"), day, -1000000, 1000000)
        due = bool(polity.get("pending_people_report")) or day - last >= PEOPLE_REPORT_INTERVAL_DAYS
        if not due:
            continue
        feeling = str(polity.get("people_relationship") or "mixed").strip()
        reason = str(polity.get("relationship_reason") or "Recent decisions continue to shape daily life.").strip().rstrip(".!?")
        events.append({
            "type": "world", "governance": True,
            "message": f"Word from {name}: the people remain {feeling}; {reason[0].lower() + reason[1:] if reason else 'recent decisions continue to shape daily life'}."
        })
        polity["last_people_report_day"] = day
        polity["reported_people_relationship"] = feeling
        polity["pending_people_report"] = False
    return events
