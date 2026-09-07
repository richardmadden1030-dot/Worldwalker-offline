"""Concise player-facing recaps, separate from the full continuity record."""
import copy
import re
from gm_refinements import obj, seq, words


def sentences(value):
    text = re.sub(r"\*\*|\[/?[A-Z _-]+\]", "", str(value or ""))
    return [re.sub(r"\s+", " ", s).strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def compact_recap(beats, player="", max_words=110):
    candidates = []
    seen = set()
    for index, beat in enumerate(beats):
        if not isinstance(beat, dict): continue
        action_terms = words(beat.get("action", ""))
        for sentence_index, sentence in enumerate(sentences(beat.get("summary", ""))):
            key = " ".join(sorted(words(sentence)))
            if key in seen or len(sentence.split()) < 4: continue
            if re.search(r"\b(?:state_patch|recorded because|practical progress within|the world moved forward|next meaningful decision|the situation remains stable)\b", sentence, re.I): continue
            if len(sentence.split()) > 65: continue  # never cut a sentence into nonsense
            seen.add(key)
            score = len(action_terms & words(sentence))
            if player and player.casefold() in sentence.casefold(): score += 4
            if re.search(r"\b(?:you|your)\b", sentence, re.I): score += 3
            if beat.get("changes"): score += 2
            candidates.append((score, index, sentence_index, sentence))
    # Select salient completed developments, then restore narrative chronology.
    chosen, count = [], 0
    for score, index, sentence_index, sentence in sorted(candidates, key=lambda row: (-row[0], -row[1])):
        size = len(sentence.split())
        if count + size <= max_words and len(chosen) < 5:
            chosen.append((index, sentence_index, sentence)); count += size
    chosen.sort(key=lambda row: (row[0], row[1]))
    return " ".join(sentence for _, _, sentence in chosen)


def prepare_chapter_request(state, packet):
    if packet.get("task") not in {"resolve_time_skip", "narrator_and_resolution", "event_turn", "time_skip", "major_event"}: return
    buffer = [r for r in seq(state.get("chapter_buffer")) if isinstance(r, dict)]
    duration = obj(packet.get("duration"))
    factor = {"minutes": 1/1440, "hours": 1/24, "days": 1, "weeks": 7, "months": 30}.get(duration.get("unit"), 0)
    try: projected = float(duration.get("amount", 0)) * factor
    except (ValueError, TypeError): projected = 0
    first_day = buffer[0].get("canon_day", state.get("canon_day", 0)) if buffer else state.get("canon_day", 0)
    if len(buffer) < 23 and float(state.get("canon_day", 0) or 0) - float(first_day or 0) + projected < 90: return
    packet["chapter_recap_context"] = {
        "player": state.get("name"),
        "confirmed_beats": [{"id": i, "action": str(r.get("action", ""))[:160], "summary": compact_recap([r], max_words=65)}
                            for i, r in enumerate(buffer)],
        "rule": "Return chapter_recap: a vivid, restrained 70–110 word retrospective in 3–5 sentences about what THIS PLAYER actually did and accomplished in these beats plus this turn's resolved events. Past tense, coherent narrative, no bullet lists, statistics, system labels, repeated turn openings, invented motives, dialogue or future threats. Quiet positive endings are valid. title is 2–7 evocative words. source_ids lists the confirmed beat IDs used; current-turn events are also allowed. This is a recap, never new world state.",
    }
    packet.setdefault("schema", {})["chapter_recap"] = {"title": "short narrative chapter title", "summary": "70–110 words", "source_ids": []}


def finish_recap(chapter, beats, player, draft=None):
    fallback = compact_recap(beats, player)
    draft = obj(draft)
    summary = str(draft.get("summary") or "").strip()
    source = " ".join(str(r.get("summary", "")) for r in beats if isinstance(r, dict))
    sources = seq(draft.get("source_ids"))
    valid = (40 <= len(summary.split()) <= 120 and 2 <= len(sentences(summary)) <= 5
             and all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(beats) for i in sources)
             and not re.search(r"state_patch|current direction:|key decisions:|^-|^\*", summary, re.M | re.I))
    # Each sentence must be anchored, not a wholly unrelated closing hook.
    valid = valid and all(len(words(s) & words(source)) / max(1, len(words(s))) >= .45 for s in sentences(summary))
    chapter["narrative_summary"] = summary if valid else fallback or "No detailed account of this chapter was recorded."
    chapter["recap_style_version"] = 1
    title = str(draft.get("title") or "").strip()
    if valid and 2 <= len(title.split()) <= 7 and len(title) <= 90:
        chapter["title"] = f"Chapter {chapter.get('number', '')}: {title}"
    chapter["recap_source"] = "narrator" if valid else "recorded_events"
    return chapter


def chapter_view(chapter, player=""):
    result = copy.deepcopy(obj(chapter))
    if not result.get("narrative_summary"):
        # Old saves keep their unabridged memory; only the display is compacted.
        finish_recap(result, [{"summary": result.get("summary", ""), "action": " ".join(str(x) for x in seq(result.get("key_decisions")))}], player)
    return result
