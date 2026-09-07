from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tactical_effects import compile_tactical_effect


LIBRARY = ROOT / "frontend" / "tactical" / "effect-family-library.js"


def test_phase_one_has_exactly_thirty_unique_effect_families():
    source = LIBRARY.read_text(encoding="utf-8")
    identifiers = re.findall(r"^\+? \['([a-z0-9-]+)'", source, flags=re.MULTILINE)
    assert len(identifiers) == 30
    assert len(set(identifiers)) == 30


def test_shared_compiler_assigns_reusable_visual_families():
    examples = {
        "fire beam that burns enemies": "living-flame",
        "water wave that damages enemies": "tidal-surge",
        "ice lance that damages enemies": "frost-bloom",
        "lightning bolt that damages enemies": "storm-vein",
        "spirit blast that damages enemies": "spirit-bolt",
    }
    for description, expected in examples.items():
        compiled = compile_tactical_effect("Bleach", "Release Application", {"description": description})
        assert compiled["visual_effect"]["family"] == expected
