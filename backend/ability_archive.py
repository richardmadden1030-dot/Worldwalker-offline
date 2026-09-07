"""Persistent archive and duplicate guard for original generated powers.

The archive intentionally stores only the authored package, not the player's
background prompt.  Each friend account therefore keeps a portable catalogue
of every original class, bloodline, release, technique, or special ability it
has ever seen without retaining unrelated character-creation text.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import uuid
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_IGNORED_FINGERPRINT_KEYS = {
    "name", "true_name", "public_name", "created_at", "id", "evidence",
    "development_evidence", "discovery", "revealed", "bonus", "rank",
    "stat_bonuses", "stat_modifiers", "mastery", "progress",
}


def _path_lock(path: Path):
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _normalized_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _semantic_value(value):
    if isinstance(value, dict):
        return {str(key): _semantic_value(item) for key, item in sorted(value.items())
                if key not in _IGNORED_FINGERPRINT_KEYS and item not in (None, "", [], {})}
    if isinstance(value, list):
        return [_semantic_value(item) for item in value if item not in (None, "", [], {})]
    if isinstance(value, str):
        return _normalized_text(value)
    return value


def ability_fingerprint(package):
    semantic = _semantic_value(package if isinstance(package, dict) else {"value": package})
    encoded = json.dumps(semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def _semantic_core_text(package):
    package = package if isinstance(package, dict) else {"value": package}
    # Compare the governing mechanic, not the shared scaffolding added by the
    # compiler (resource labels, mastery stages, generic counterplay, etc.).
    # Shared boilerplate used to dominate the token score, which both hid real
    # repeats and falsely rejected distinct powers from the same setting.
    core = []
    # Prefer the single authoritative rule.  Including the display name again
    # through an "effect" sentence can make two identical rules appear
    # different merely because their titles changed.
    for key in ("governing_rule", "shikai_effect", "enhancement"):
        value = package.get(key)
        if isinstance(value, str) and value.strip():
            core.append(value)
            break
    details = package.get("details")
    if not core and isinstance(details, dict):
        for key in ("effect", "description"):
            value = details.get(key)
            if isinstance(value, str) and value.strip():
                core.append(value)
                break
    abilities = package.get("abilities")
    if not core and isinstance(abilities, list):
        core.extend(str(value) for value in abilities[:3] if str(value).strip())
    if not core:
        for key in ("effect", "description"):
            value = package.get(key)
            if isinstance(value, str) and value.strip():
                core.append(value)
                break
    if not core:
        core = [json.dumps(_semantic_value(package), sort_keys=True, ensure_ascii=False)]
    return " ".join(core)

def _semantic_tokens(package):
    text = _semantic_core_text(package)
    stop = {"the", "and", "that", "with", "from", "into", "this", "when", "user", "ability", "effect", "their"}
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2 and token not in stop}


_CONCEPT_FAMILIES = {
    "time": {"time", "temporal", "seconds", "future", "past", "rewind", "delay", "accelerate"},
    "space": {"space", "spatial", "distance", "portal", "teleport", "dimension", "coordinate"},
    "momentum": {"momentum", "motion", "kinetic", "velocity", "inertia", "impact", "stored", "accumulate"},
    "shadow": {"shadow", "darkness", "shade", "silhouette", "umbra"},
    "memory": {"memory", "remember", "forgotten", "recall", "knowledge", "thought"},
    "contract": {"contract", "vow", "promise", "condition", "restriction", "exchange"},
    "copy": {"copy", "replicate", "imitate", "steal", "borrow", "reproduce"},
    "gravity": {"gravity", "weight", "mass", "attract", "repel", "density"},
    "soul": {"soul", "spirit", "essence", "reiatsu", "aura"},
    "creation": {"create", "construct", "forge", "manifest", "generate", "shape"},
}


def mechanic_signature(package):
    tokens = _semantic_tokens(package)
    concepts = sorted(name for name, family in _CONCEPT_FAMILIES.items() if tokens & family)
    ordered = re.findall(r"[a-z0-9]+", _normalized_text(_semantic_core_text(package)))
    pairs = sorted({f"{ordered[i]}:{ordered[i + 1]}" for i in range(max(0, len(ordered) - 1))
                    if ordered[i] not in {"the", "and", "with", "into", "from"}})
    return {"concepts": concepts, "pairs": pairs[:80]}

def semantic_similarity(left, right):
    left_tokens, right_tokens = _semantic_tokens(left), _semantic_tokens(right)
    jaccard = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))

    def symmetric_ratio(a, b):
        # SequenceMatcher is order-sensitive. The archive checks new/old while
        # callers can compare old/new; use the more conservative result in
        # either direction so a reroll cannot slip through merely by ordering.
        return max(SequenceMatcher(None, a, b).ratio(), SequenceMatcher(None, b, a).ratio())

    sequence = symmetric_ratio(" ".join(sorted(left_tokens)), " ".join(sorted(right_tokens)))
    phrase_sequence = symmetric_ratio(_normalized_text(_semantic_core_text(left)),
                                      _normalized_text(_semantic_core_text(right)))
    return round(max(jaccard, sequence * .9, phrase_sequence * .95), 4)


class GeneratedAbilityArchive:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = _path_lock(self.path)

    def _read(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw.get("entries", []) if isinstance(raw, dict) else raw
            return entries if isinstance(entries, list) else []
        except Exception:
            return []

    def _write(self, entries):
        payload = {"schema_version": 2, "entries": entries}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def entries(self, world="", category=""):
        with self.lock:
            rows = copy.deepcopy(self._read())
        if world:
            rows = [row for row in rows if str(row.get("world")) == str(world)]
        if category:
            rows = [row for row in rows if str(row.get("category")) == str(category)]
        return rows

    def is_duplicate(self, world, category, package):
        name = _normalized_text((package or {}).get("name") or (package or {}).get("true_name"))
        fingerprint = ability_fingerprint(package)
        for row in self.entries(world, category):
            if name and name == _normalized_text(row.get("name")):
                return True
            if fingerprint and fingerprint == row.get("fingerprint"):
                return True
            similarity = semantic_similarity(package, row.get("package") or {})
            left, right = mechanic_signature(package), mechanic_signature(row.get("package") or {})
            shared_concepts = set(left["concepts"]) & set(right["concepts"])
            pair_overlap = len(set(left["pairs"]) & set(right["pairs"])) / max(1, min(len(left["pairs"]), len(right["pairs"])))
            if similarity >= 0.72 or (shared_concepts and similarity >= 0.62):
                return True
        return False

    def closest_match(self, world, category, package):
        best = None
        for row in self.entries(world, category):
            score = semantic_similarity(package, row.get("package") or {})
            if best is None or score > best["similarity"]:
                left, right = mechanic_signature(package), mechanic_signature(row.get("package") or {})
                best = {"similarity": score, "name": row.get("name", ""), "id": row.get("id", ""),
                        "shared_concepts": sorted(set(left["concepts"]) & set(right["concepts"]))}
        return best or {"similarity": 0.0, "name": "", "id": "", "shared_concepts": []}

    def exclusions(self, world, category, limit=40):
        rows = self.entries(world, category)[-max(1, int(limit)):]
        result = []
        for row in rows:
            package = row.get("package") if isinstance(row.get("package"), dict) else {}
            effect = _semantic_core_text(package)
            result.append({"name": row.get("name", ""), "mechanic": str(effect)[:180]})
        return result

    def record(self, world, category, package, source="generation"):
        package = copy.deepcopy(package) if isinstance(package, dict) else {"value": copy.deepcopy(package)}
        name = str(package.get("name") or package.get("true_name") or "Unnamed original ability").strip()
        with self.lock:
            entries = self._read()
            fingerprint = ability_fingerprint(package)
            normalized_name = _normalized_text(name)
            for index, row in enumerate(entries):
                if (row.get("world") == world and row.get("category") == category and
                        (row.get("fingerprint") == fingerprint or
                         (normalized_name and _normalized_text(row.get("name")) == normalized_name))):
                    if normalized_name and _normalized_text(row.get("name")) == normalized_name and row.get("package") != package:
                        row["fingerprint"] = fingerprint
                        row["package"] = package
                        row["source"] = str(source)
                        entries[index] = row
                        self._write(entries)
                    return copy.deepcopy(row)
            entry = {
                "id": uuid.uuid4().hex,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "world": str(world), "category": str(category), "name": name,
                "fingerprint": fingerprint, "source": str(source), "canon": False,
                "mechanic_signature": mechanic_signature(package), "package": package,
            }
            entries.append(entry)
            self._write(entries)
            return copy.deepcopy(entry)
