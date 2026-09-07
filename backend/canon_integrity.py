"""Local canon identity locks and deterministic role-consistency repairs.

This deliberately covers identity, office, faction and crew/squad role facts
that models commonly swap.  It is not a plot-summary database.  Campaign
divergences and explicit player corrections still outrank stock canon.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from datetime import datetime


def _r(name, role, affiliation, aliases=(), **extra):
    return {"name": name, "role": role, "affiliation": affiliation,
            "aliases": list(aliases), **extra}


# Roles are the stock-canon truth at the world's normal opening unless a
# from_day/until_day range says otherwise.  These compact records are cheap
# enough to retrieve locally and important enough not to leave to model recall.
CANON_IDENTITIES = {
    "Naruto": [
        _r("Naruto Uzumaki", "Konoha genin and Team 7 member", "Konohagakure", ["Naruto"]),
        _r("Sasuke Uchiha", "Konoha genin and Team 7 member", "Konohagakure", ["Sasuke"]),
        _r("Sakura Haruno", "Konoha genin and Team 7 member", "Konohagakure", ["Sakura"]),
        _r("Kakashi Hatake", "jōnin leader of Team 7", "Konohagakure", ["Kakashi"]),
        _r("Hiruzen Sarutobi", "Third Hokage", "Konohagakure", ["Hiruzen", "Third Hokage"]),
        _r("Minato Namikaze", "Fourth Hokage and Naruto's father", "Konohagakure", ["Minato", "Fourth Hokage"]),
        _r("Yahiko", "co-founder and public leader of the original Akatsuki", "Original Akatsuki", ["Yahiko of the Akatsuki"]),
        _r("Nagato", "co-founder of the original Akatsuki; later the controlling identity behind Pain", "Original Akatsuki", ["Pain", "Nagato Uzumaki"]),
        _r("Konan", "co-founder of the original Akatsuki", "Original Akatsuki", ["Angel of Amegakure"]),
        _r("Hanzō", "leader of Amegakure", "Amegakure", ["Hanzo", "Hanzō of the Salamander"]),
    ],
    "One Piece": [
        _r("Monkey D. Luffy", "captain", "Straw Hat Pirates", ["Luffy", "Straw Hat Luffy"]),
        _r("Roronoa Zoro", "combatant and swordsman", "Straw Hat Pirates", ["Zoro"]),
        _r("Nami", "navigator", "Straw Hat Pirates", ["Cat Burglar Nami"]),
        _r("Usopp", "sniper", "Straw Hat Pirates", ["Sogeking"]),
        _r("Sanji", "cook", "Straw Hat Pirates", ["Black Leg Sanji"]),
        _r("Tony Tony Chopper", "doctor", "Straw Hat Pirates", ["Chopper"]),
        _r("Nico Robin", "archaeologist", "Straw Hat Pirates", ["Robin"]),
        _r("Smoker", "Marine captain stationed at Loguetown", "Marines", ["Captain Smoker"]),
        _r("Monkey D. Garp", "Marine vice admiral", "Marines", ["Garp", "Vice Admiral Garp"]),
        _r("Shanks", "captain", "Red Hair Pirates", ["Red-Haired Shanks"]),
    ],
    "Hunter x Hunter": [
        _r("Gon Freecss", "Hunter Exam applicant", "Independent", ["Gon"]),
        _r("Killua Zoldyck", "Hunter Exam applicant and Zoldyck assassin-family heir", "Independent", ["Killua"]),
        _r("Kurapika", "Hunter Exam applicant and sole known survivor of the Kurta Clan", "Independent", ["Kurta Kurapika"]),
        _r("Leorio Paradinight", "Hunter Exam applicant pursuing medical training", "Independent", ["Leorio"]),
        _r("Isaac Netero", "12th Chairman", "Hunter Association", ["Netero", "Chairman Netero"]),
        _r("Chrollo Lucilfer", "leader", "Phantom Troupe", ["Chrollo"]),
        _r("Hisoka Morow", "independent Hunter Exam applicant; not a loyal Phantom Troupe member", "Independent", ["Hisoka"]),
        _r("Illumi Zoldyck", "professional assassin", "Zoldyck Family", ["Illumi", "Gittarackur"]),
    ],
    "Solo Max-Level Newbie": [
        _r("Kang Jinhyuk", "the only player to clear the Tower of Trials game before it became reality", "Independent", ["Kang Jinhyeok", "Jinhyuk", "Jinhyeok"]),
        _r("Alice von Ataraxia", "vampire and former head of the Ataraxia family", "Ataraxia", ["Alice"]),
        _r("Teresa de Laurencia", "holy knight", "Laurencia", ["Teresa"]),
        _r("Cheon Yuseong", "swordsman and Jinhyuk's rival", "Independent", ["Chun Yoosung", "Yuseong", "Yoosung"]),
        _r("Lee Taemin", "player active after the Tower manifests", "Independent", ["Taemin"]),
        _r("Yoo Yeonhwa", "player active after the Tower manifests", "Independent", ["Yeonhwa"]),
    ],
    "Overgeared": [
        _r("Grid", "player who becomes Pagma's Successor", "Independent at the opening", ["Shin Youngwoo", "Youngwoo"]),
        _r("Pagma", "legendary blacksmith and great swordsman whose legacy creates Pagma's Successor", "Former Legend", ["Legendary Blacksmith Pagma"]),
        _r("Khan", "veteran blacksmith of Winston and Grid's mentor/friend", "Winston", ["Blacksmith Khan"]),
        _r("Piaro", "disgraced former captain of the Red Knights", "Former Red Knights", ["Farmer Piaro"]),
        _r("Irene", "daughter of Earl Steim and lady of Winston", "Steim family", ["Lady Irene"]),
        _r("Kraugel", "top-ranked player and swordsman", "Independent", ["Kraugel the Sky Above the Sky"]),
        _r("Yura", "top-ranked player initially associated with the Yatan Church", "Yatan Church", ["Yura"]),
        _r("Braham", "legendary great magician", "Former Legend", ["Braham Eshwald"]),
    ],
    "Reincarnated as a Slime": [
        _r("Rimuru Tempest", "reincarnated slime who becomes founder and ruler of Tempest", "Jura-Tempest Federation", ["Rimuru"]),
        _r("Veldora Tempest", "Storm Dragon", "Independent / allied with Rimuru", ["Veldora", "Storm Dragon Veldora"]),
        _r("Benimaru", "Kijin military commander serving Rimuru", "Jura-Tempest Federation", ["Benimaru"]),
        _r("Shuna", "Kijin priestess and chief domestic/diplomatic aide serving Rimuru", "Jura-Tempest Federation", ["Shuna"]),
        _r("Shion", "Kijin secretary and combatant serving Rimuru", "Jura-Tempest Federation", ["Shion"]),
        _r("Sōei", "Kijin intelligence and covert-operations leader serving Rimuru", "Jura-Tempest Federation", ["Soei", "Sōei"]),
        _r("Ranga", "Tempest Wolf and Rimuru's loyal shadow guardian", "Jura-Tempest Federation", ["Ranga"]),
        _r("Milim Nava", "Dragonoid and one of the oldest Demon Lords", "Demon Lords", ["Milim"]),
    ],
    "Bleach": [
        _r("Genryūsai Shigekuni Yamamoto", "Captain of the 1st Division and Captain-Commander", "Gotei 13", ["Yamamoto", "Genryusai Yamamoto"], division=1, duty_title="Captain"),
        _r("Chōjirō Sasakibe", "Lieutenant of the 1st Division", "Gotei 13", ["Chojiro Sasakibe", "Sasakibe"], division=1, duty_title="Lieutenant"),
        _r("Soi Fon", "Captain of the 2nd Division and commander-in-chief of the Onmitsukidō", "Gotei 13", ["Sui-Feng", "Soi Fong"], division=2, duty_title="Captain"),
        _r("Marechiyo Ōmaeda", "Lieutenant of the 2nd Division", "Gotei 13", ["Marechiyo Omaeda", "Omaeda"], division=2, duty_title="Lieutenant"),
        _r("Gin Ichimaru", "Captain of the 3rd Division", "Gotei 13", ["Gin"], division=3, duty_title="Captain", until_day=87),
        _r("Izuru Kira", "Lieutenant of the 3rd Division", "Gotei 13", ["Kira"], division=3, duty_title="Lieutenant"),
        _r("Retsu Unohana", "Captain of the 4th Division", "Gotei 13", ["Unohana"], division=4, duty_title="Captain"),
        _r("Isane Kotetsu", "Lieutenant of the 4th Division", "Gotei 13", ["Isane"], division=4, duty_title="Lieutenant"),
        _r("Sōsuke Aizen", "Captain of the 5th Division", "Gotei 13", ["Sosuke Aizen", "Aizen"], division=5, duty_title="Captain", until_day=87),
        _r("Momo Hinamori", "Lieutenant of the 5th Division", "Gotei 13", ["Hinamori", "Momo"], division=5, duty_title="Lieutenant"),
        _r("Byakuya Kuchiki", "Captain of the 6th Division", "Gotei 13", ["Byakuya"], division=6, duty_title="Captain"),
        _r("Renji Abarai", "Lieutenant of the 6th Division", "Gotei 13", ["Renji"], division=6, duty_title="Lieutenant"),
        _r("Sajin Komamura", "Captain of the 7th Division", "Gotei 13", ["Komamura"], division=7, duty_title="Captain"),
        _r("Tetsuzaemon Iba", "Lieutenant of the 7th Division", "Gotei 13", ["Iba"], division=7, duty_title="Lieutenant"),
        _r("Shunsui Kyōraku", "Captain of the 8th Division", "Gotei 13", ["Shunsui Kyoraku", "Kyoraku", "Shunsui"], division=8, duty_title="Captain", until_day=929),
        _r("Nanao Ise", "Lieutenant of the 8th Division", "Gotei 13", ["Nanao"], division=8, duty_title="Lieutenant"),
        _r("Kaname Tōsen", "Captain of the 9th Division", "Gotei 13", ["Kaname Tosen", "Tosen", "Tōsen"], division=9, duty_title="Captain", until_day=87),
        _r("Shūhei Hisagi", "Lieutenant of the 9th Division", "Gotei 13", ["Shuhei Hisagi", "Hisagi"], division=9, duty_title="Lieutenant"),
        _r("Tōshirō Hitsugaya", "Captain of the 10th Division", "Gotei 13", ["Toshiro Hitsugaya", "Hitsugaya"], division=10, duty_title="Captain"),
        _r("Rangiku Matsumoto", "Lieutenant of the 10th Division", "Gotei 13", ["Rangiku", "Matsumoto"], division=10, duty_title="Lieutenant"),
        _r("Kenpachi Zaraki", "Captain of the 11th Division", "Gotei 13", ["Zaraki", "Kenpachi"], division=11, duty_title="Captain"),
        _r("Yachiru Kusajishi", "Lieutenant of the 11th Division", "Gotei 13", ["Yachiru"], division=11, duty_title="Lieutenant"),
        _r("Mayuri Kurotsuchi", "Captain of the 12th Division and president of the Shinigami Research and Development Institute", "Gotei 13", ["Mayuri"], division=12, duty_title="Captain"),
        _r("Nemu Kurotsuchi", "Lieutenant of the 12th Division", "Gotei 13", ["Nemu"], division=12, duty_title="Lieutenant"),
        _r("Jūshirō Ukitake", "Captain of the 13th Division", "Gotei 13", ["Jushiro Ukitake", "Ukitake"], division=13, duty_title="Captain"),
        _r("Kaien Shiba", "former Lieutenant of the 13th Division; deceased before the main story", "Gotei 13", ["Kaien"], division=13, duty_title="Lieutenant"),
        _r("Ichigo Kurosaki", "Substitute Soul Reaper after receiving Rukia's power", "Independent / Substitute Soul Reaper", ["Ichigo"]),
        _r("Rukia Kuchiki", "unseated member of the 13th Division at the main-story opening", "Gotei 13", ["Rukia"], division=13, duty_title="Member"),
    ],
    "Jujutsu Kaisen": [
        _r("Satoru Gojo", "special-grade sorcerer and teacher at Tokyo Jujutsu High", "Tokyo Jujutsu High", ["Gojo"]),
        _r("Masamichi Yaga", "principal", "Tokyo Jujutsu High", ["Yaga", "Principal Yaga"]),
        _r("Yuji Itadori", "Tokyo first-year and vessel of Ryomen Sukuna", "Tokyo Jujutsu High", ["Yuji", "Itadori"]),
        _r("Megumi Fushiguro", "Tokyo first-year and Ten Shadows sorcerer", "Tokyo Jujutsu High", ["Megumi", "Fushiguro"]),
        _r("Nobara Kugisaki", "Tokyo first-year and Straw Doll Technique user", "Tokyo Jujutsu High", ["Nobara", "Kugisaki"]),
        _r("Maki Zenin", "Tokyo student and cursed-tool specialist with Heavenly Restriction", "Tokyo Jujutsu High", ["Maki"]),
        _r("Yuta Okkotsu", "special-grade sorcerer and Tokyo student", "Tokyo Jujutsu High", ["Yuta", "Okkotsu"]),
        _r("Suguru Geto", "special-grade curse user after defecting from Jujutsu High", "Geto's curse-user group", ["Geto"]),
        _r("Ryomen Sukuna", "incarnated King of Curses within Yuji Itadori at the main-story opening", "Independent", ["Sukuna"]),
    ],
}


_ORDINAL_WORDS = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th",
    8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th", 13: "13th",
}
_ORDINAL_VALUES = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13,
}


def _fold(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def _aliases(record):
    return [record["name"], *record.get("aliases", [])]


def _active(record, canon_day):
    return int(record.get("from_day", -10**9)) <= canon_day <= int(record.get("until_day", 10**9))


def _diverged(state, record):
    if _fold((state or {}).get("name")) in {_fold(x) for x in _aliases(record)}:
        return True  # player-controlled canon characters are allowed to diverge
    blob = " ".join(str(row) for row in (state or {}).get("canon_divergences", []) or [])
    folded = _fold(blob)
    return bool(folded and any(_fold(alias) in folded for alias in _aliases(record)))


def active_canon_identities(world, state=None):
    day = int((state or {}).get("canon_day", 0) or 0)
    return [copy.deepcopy(row) for row in CANON_IDENTITIES.get(world, []) if _active(row, day)]


def canon_identity_context(world, query="", state=None, limit=12):
    records = [row for row in active_canon_identities(world, state) if not _diverged(state, row)]
    if not records:
        return ""
    state = state or {}
    known = " ".join([
        str(query or ""), str(state.get("active_canon_event") or ""), str(state.get("active_major_event") or ""),
        " ".join((state.get("npc_memories") or {}).keys()), " ".join((state.get("contacts") or {}).keys()),
        # Companions intentionally support both the original compact string
        # form and newer structured records.  Never call ``.get`` on the
        # compact form: old and long-running campaigns commonly contain it.
        " ".join(
            str((row.get("name") or "") if isinstance(row, dict) else row)
            for row in state.get("companions", []) if isinstance(row, (dict, str))
        ),
    ])
    folded = _fold(known)
    ranked = []
    for index, row in enumerate(records):
        direct = any(_fold(alias) in folded for alias in _aliases(row) if len(_fold(alias)) > 2)
        if direct:
            ranked.append((100, -index, row))
    if not ranked and re.search(r"\b(canon|captain|lieutenant|leader|chairman|teacher|crew|squad|division|faction|role|rank)\b", str(query), re.I):
        ranked = [(1, -i, row) for i, row in enumerate(records)]
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    selected = [row for _, _, row in ranked[:max(1, int(limit))]]
    if not selected:
        return ""
    lines = ["CANON IDENTITY LOCKS (opening-era role records; the current canon date, recorded campaign divergences, and explicit player corrections override them):"]
    for row in selected:
        lines.append(f"- {row['name']}: {row['role']}; affiliation: {row['affiliation']}.")
    lines.append("Never swap these characters' offices, ranks, squads, factions, crew roles, or identities. If the campaign changed one, name the recorded divergence instead of silently using stock canon or inventing a different assignment.")
    return "\n".join(lines)


_ROLE_CLAIM = re.compile(
    r"(?:\b(?:captain|lieutenant)\s+of\s+(?:the\s+)?(?:[a-z]+|\d{1,2}(?:st|nd|rd|th)?)\s+(?:division|squad)\b|"
    r"\b(?:[a-z]+|\d{1,2}(?:st|nd|rd|th)?)\s+(?:division|squad)\s+(?:captain|lieutenant)\b|"
    r"\b(?:division|squad)\s+(?:[a-z]+|\d{1,2})\s+(?:captain|lieutenant)\b)", re.I,
)
_DIVISION_TOKEN = r"(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|\d{1,2}(?:st|nd|rd|th)?)"


def _division_value(value):
    folded = _fold(value)
    number_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", folded)
    if number_match:
        return int(number_match.group(1))
    return next((number for word, number in _ORDINAL_VALUES.items()
                 if re.search(rf"\b{word}\b", folded)), None)


def repair_canon_text(world, text, state=None):
    """Repair only unambiguous numbered-division role swaps.

    Broader political changes remain narrative and divergence-aware; this
    deterministic layer intentionally refuses to rewrite them blindly.
    """
    original = str(text or "")
    if world != "Bleach" or not original:
        return original, []
    records = [row for row in active_canon_identities(world, state)
               if row.get("division") and row.get("duty_title") and not _diverged(state or {}, row)]
    repairs = []
    pieces = re.split(r"(?<=[.!?\n])", original)
    for index, sentence in enumerate(pieces):
        mentioned = [row for row in records if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", sentence, re.I)
                                                   for alias in _aliases(row))]
        if len(mentioned) != 1:
            continue
        row = mentioned[0]
        expected = f"{row['duty_title']} of the {_ORDINAL_WORDS[row['division']]} Division"
        claims = list(_ROLE_CLAIM.finditer(sentence))
        if len(claims) == 1:
            claim = claims[0]
            claim_folded = _fold(claim.group(0))
            claimed_division = _division_value(claim_folded)
            claimed_title = "Lieutenant" if re.search(r"\blieutenant\b", claim_folded) else "Captain"
            if claimed_division == row["division"] and claimed_title == row["duty_title"]:
                continue
            sentence = sentence[:claim.start()] + expected + sentence[claim.end():]
            pieces[index] = sentence
            repairs.append(f"Restored {row['name']} as {expected}")
            continue

        # Models also emit appositive forms such as “the 5th Division and
        # Captain Kaname Tōsen.”  Bind these only when the title, one named
        # identity, and one numbered division are adjacent; do not infer an
        # association merely because both happen somewhere in a long sentence.
        aliases = "|".join(re.escape(alias) for alias in _aliases(row))
        forward = re.search(
            rf"(?P<div>\b{_DIVISION_TOKEN}\s+Division\b)(?:\*{{0,2}})?\s*(?:and|,|—|-)\s*"
            rf"(?:\*{{0,2}})?(?P<title>Captain|Lieutenant)\s+(?:{aliases})(?!\w)", sentence, re.I,
        )
        reverse = re.search(
            rf"(?P<title>Captain|Lieutenant)\s+(?:{aliases})(?!\w)(?:\*{{0,2}})?.{{0,24}}?"
            rf"(?:of|from|and|,)\s+(?:\*{{0,2}})?(?:the\s+)?(?P<div>\b{_DIVISION_TOKEN}\s+Division\b)", sentence, re.I,
        )
        pair = forward or reverse
        if not pair:
            continue
        claimed_division = _division_value(pair.group("div"))
        claimed_title = pair.group("title").title()
        if claimed_division == row["division"] and claimed_title == row["duty_title"]:
            continue
        correct_division = f"{_ORDINAL_WORDS[row['division']]} Division"
        start, end = pair.span("div")
        sentence = sentence[:start] + correct_division + sentence[end:]
        pieces[index] = sentence
        repairs.append(f"Restored {row['name']} as {expected}")
    return "".join(pieces), list(dict.fromkeys(repairs))


def repair_canon_payload(world, payload, state=None):
    """Repair unambiguous canon-role strings anywhere in one AI response."""
    repairs = []
    def walk(value):
        if isinstance(value, str):
            fixed, notes = repair_canon_text(world, value, state)
            repairs.extend(notes)
            return fixed
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value
    fixed = walk(payload)
    return fixed, list(dict.fromkeys(repairs))


def normalize_canon_integrity(state, scan_chronicle=False):
    """Repair stale structured NPC role text and flag bad prior Chronicle facts."""
    if not isinstance(state, dict):
        return []
    world = state.get("world", "Custom World")
    repairs = []
    for bucket_name in ("npc_memories", "contacts", "npc_clocks"):
        bucket = state.get(bucket_name)
        if not isinstance(bucket, dict):
            continue
        for name, detail in list(bucket.items()):
            if not isinstance(detail, dict):
                continue
            fixed, notes = repair_canon_payload(world, detail, state)
            if notes:
                bucket[name] = fixed
                repairs.extend(notes)
    # campaign_canon is the compact memory the GM actually reasons from.
    # Correct an unambiguous role swap here so a stale summary cannot keep
    # re-infecting future narration, while the original visible Chronicle is
    # preserved and receives a transparent correction note below.
    canon_rows = state.get("campaign_canon")
    if isinstance(canon_rows, list):
        for index, row in enumerate(canon_rows):
            fixed, notes = repair_canon_payload(world, row, state)
            if notes:
                canon_rows[index] = fixed
                repairs.extend(notes)
    if scan_chronicle:
        old_notes = set(state.setdefault("canon_integrity_repairs", []))
        found = [note for note in repairs if note not in old_notes]
        for entry in (state.get("story_log") or [])[-250:]:
            if not isinstance(entry, dict):
                continue
            _, notes = repair_canon_text(world, entry.get("text", ""), state)
            found.extend(note for note in notes if note not in old_notes)
        found = list(dict.fromkeys(found))
        if found:
            state.setdefault("_pending_chronicle_notes", []).append(
                "[CANON CORRECTION]\n" + "; ".join(found) + ". Future narration will use the corrected assignment."
            )
            old_notes.update(found)
            state["canon_integrity_repairs"] = sorted(old_notes)[-100:]
            repairs.extend(found)
    if repairs:
        state.setdefault("diagnostics", {}).setdefault("canon_integrity", {})["last_repairs"] = list(dict.fromkeys(repairs))
    return list(dict.fromkeys(repairs))


def registry_audit():
    """Return structural coverage problems for tests/Diagnostics."""
    required = {"Naruto", "One Piece", "Hunter x Hunter", "Solo Max-Level Newbie", "Overgeared",
                "Reincarnated as a Slime", "Bleach", "Jujutsu Kaisen"}
    problems = []
    for world in sorted(required):
        rows = CANON_IDENTITIES.get(world, [])
        if len(rows) < 5:
            problems.append(f"{world} has fewer than five canon identity locks")
        seen = set()
        for row in rows:
            if not row.get("name") or not row.get("role") or not row.get("affiliation"):
                problems.append(f"{world} has an incomplete identity record")
            key = _fold(row.get("name"))
            if key in seen:
                problems.append(f"{world} duplicates {row.get('name')}")
            seen.add(key)
    return problems
