import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ai_client import MODEL_PRICING_PER_1M, estimate_cost_usd


class ModelChoiceTests(unittest.TestCase):
    def test_cloud_model_ladder_and_presets_are_exposed(self):
        js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        for model in (
            "gpt-5-nano", "gpt-4o-mini", "gpt-5.6-luna", "gpt-5.4-nano",
            "gpt-5-mini", "gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.4", "gpt-5.6-sol",
        ):
            self.assertIn(model, js)
        for preset in ("budget", "balanced", "quality", "premium"):
            self.assertIn(f"btn-preset-{preset}", html)
            self.assertIn(f"{preset}:", js)

    def test_current_sol_pricing_is_used_by_cost_estimator(self):
        self.assertEqual(MODEL_PRICING_PER_1M["gpt-5.6-sol"], (4.0, 20.0))
        self.assertAlmostEqual(estimate_cost_usd("gpt-5.6-sol", 1_000_000, 1_000_000), 24.0)


if __name__ == "__main__":
    unittest.main()
