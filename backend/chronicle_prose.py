"""Lossless presentation of authored beats; never rewrites player text or dialogue."""
import re

WRITING_RULE = (
    "Chronicle prose: use concrete subjects and short complete sentences, usually one action or result per sentence. "
    "Separate changes of subject into short paragraphs. Name who acted, what happened and the actual result; "
    "do not splice unrelated clauses into a run-on sentence or repeat the title as an explanation. "
    "Routine notices may be one sentence; longer scenes may use several short paragraphs. "
    "Avoid internal bookkeeping phrases, empty placeholders and invented stakes. Leave supplementary fields "
    "empty when the narrative already conveys them. Preserve exact names, amounts, uncertainty and causal limits."
)


def _key(value):
    return re.sub(r"\s+", " ", value.replace("**", "")).strip().rstrip(".!?").casefold()


def beat_body(update):
    """Keep distinct supplemental facts in separate paragraphs, not a glued-on tail.

    Only exact redundant prose (ignoring bold/whitespace/terminal punctuation)
    is omitted. No length caps, fuzzy similarity, or inferred sentence rewrites.
    """
    narrative = update.get("narrative")
    narrative = narrative.strip() if isinstance(narrative, str) else ""
    sections = [narrative] if narrative else []
    seen = {_key(narrative)}
    seen.update(_key(line) for line in re.split(r"\n+|(?<=[.!?])\s+", narrative) if line.strip())
    for field in ("why_it_matters", "player_knowledge", "next_pressure"):
        value = update.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if _key(value) in {"none", "null", "n/a", "not applicable"} or _key(value) in seen:
            continue
        sections.append(value)
        seen.add(_key(value))
    return "\n\n".join(sections)
