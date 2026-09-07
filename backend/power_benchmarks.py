"""World-native power benchmarks shared by UI, Advisor, GM and combat."""
from __future__ import annotations

GENERIC_THRESHOLDS = (0, 20, 35, 50, 65, 90, 130, 200, 350, 600, 1000)

WORLD_BENCHMARKS = {
    "Naruto": ("Civilian", "Academy Student", "Genin", "Experienced Genin", "Chunin", "Special Jonin", "Jonin", "Elite Jonin", "Kage Candidate", "Kage Class", "Six Paths Scale"),
    "One Piece": ("Civilian", "East Blue Rookie", "Capable Rookie", "Grand Line Veteran", "Officer", "Supernova Threat", "New World Veteran", "Commander Class", "Admiral Candidate", "Emperor Class", "World-Shaking Anomaly"),
    "Hunter x Hunter": ("Civilian", "Conditioned Applicant", "Hunter Candidate", "Nen Initiate", "Competent Nen User", "Veteran Hunter", "Elite Hunter", "Master Nen User", "Royal Guard Threat", "Chairman-Class Monster", "Beyond Human Measure"),
    "Bleach": ("Ordinary Soul", "Academy Student", "Unseated Shinigami", "Seated Officer", "Lieutenant Candidate", "Lieutenant Class", "Captain Candidate", "Captain Class", "Senior Captain Class", "Transcendent", "Realm-Altering"),
    "Jujutsu Kaisen": ("Non-Sorcerer", "Grade 4", "Grade 3", "Grade 2 Candidate", "Grade 2", "Semi-Grade 1", "Grade 1", "Elite Grade 1", "Special Grade Candidate", "Special Grade", "Rule-Breaking Anomaly"),
    "Overgeared": ("Civilian NPC", "Beginner Player", "Established Player", "Skilled Ranker", "Regional Ranker", "National Ranker", "Top Ranker", "Legendary-Class Threat", "Transcendent", "Absolute", "Myth-Shaping"),
    "Solo Max-Level Newbie": ("Civilian", "Newly Awakened", "Low-Rank Player", "Proven Raider", "High-Rank Player", "Elite Ranker", "Named Power", "Floor-Dominating Threat", "Top-Rank Transcendent", "Administrator Threat", "Tower-Breaking Anomaly"),
    "Reincarnated as a Slime": ("Ordinary Being", "Lesser Monster", "Named Monster", "Regional Threat", "Majin", "Demon Lord Seed", "Awakened-Class", "True Demon Lord", "True Dragon Peer", "World-Class Existence", "Law-Altering Existence"),
    "Custom World": ("Mundane", "Trained", "Skilled", "Elite", "Exceptional", "Powerhouse", "Superhuman", "Legendary", "World-Class", "Cataclysmic", "Reality-Bending"),
}

CANON_ANCHORS = {
    "Naruto": ((2, "typical active Genin"), (4, "typical Chunin"), (6, "typical Jonin"), (9, "major Kage-era combatant")),
    "One Piece": ((2, "capable East Blue fighter"), (5, "notable Grand Line captain"), (7, "Yonko commander-level threat"), (9, "Emperor or Admiral-class combatant")),
    "Hunter x Hunter": ((3, "newly competent Nen user"), (6, "elite professional Hunter"), (8, "Royal Guard-scale threat")),
    "Bleach": ((2, "ordinary unseated Shinigami"), (5, "lieutenant-class combatant"), (7, "captain-class combatant"), (9, "transcendent combatant")),
    "Jujutsu Kaisen": ((2, "Grade 3 sorcerer"), (4, "Grade 2 sorcerer"), (6, "Grade 1 sorcerer"), (9, "Special Grade threat")),
    "Overgeared": ((2, "established player"), (4, "regional ranker"), (6, "top ranker"), (8, "transcendent")),
    "Solo Max-Level Newbie": ((2, "low-rank awakened player"), (4, "high-rank raider"), (6, "named ranker"), (8, "top transcendent")),
    "Reincarnated as a Slime": ((2, "named monster"), (5, "Demon Lord Seed"), (7, "True Demon Lord"), (8, "True Dragon peer")),
}

def benchmark_tier(world, score):
    names = WORLD_BENCHMARKS.get(world, WORLD_BENCHMARKS["Custom World"])
    numeric = max(0.0, float(score or 0))
    index = max(i for i, threshold in enumerate(GENERIC_THRESHOLDS) if numeric >= threshold)
    index = min(index, len(names) - 1)
    return {"index": index, "name": names[index], "score": round(numeric, 1),
            "threshold": GENERIC_THRESHOLDS[index],
            "next_threshold": GENERIC_THRESHOLDS[index + 1] if index + 1 < len(GENERIC_THRESHOLDS) else None,
            "world": world}

def benchmark_context(world):
    names = WORLD_BENCHMARKS.get(world, WORLD_BENCHMARKS["Custom World"])
    return {"world": world,
            "tiers": [{"index": i, "name": name, "threshold": GENERIC_THRESHOLDS[i]} for i, name in enumerate(names)],
            "canon_anchors": [{"tier": tier, "reference": label} for tier, label in CANON_ANCHORS.get(world, ())],
            "rule": "Use balanced combat score for overall comparisons; a peak specialty is not the whole fighter."}

def compare_profiles(left, right_score, right_name="Opponent"):
    left_score = float((left.get("combat") or {}).get("score", 0) or 0)
    right_score = max(1.0, float(right_score or 1)); ratio = left_score / right_score
    verdict = ("decisively stronger" if ratio >= 1.75 else "stronger" if ratio >= 1.2 else
               "roughly comparable" if ratio >= .84 else "weaker" if ratio >= .57 else "decisively weaker")
    return {"opponent": right_name, "player_score": round(left_score, 1), "opponent_score": round(right_score, 1), "ratio": round(ratio, 2), "verdict": verdict}
