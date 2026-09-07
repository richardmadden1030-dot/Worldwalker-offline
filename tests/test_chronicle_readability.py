import sys
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from chronicle_prose import beat_body, WRITING_RULE


class ChronicleReadabilityTests(unittest.TestCase):
    def test_distinct_facts_are_not_glued_together(self):
        self.assertEqual(beat_body(dict(narrative='The repairs are finished.', why_it_matters='The road is safer.',
                                       player_knowledge='You inspected the bridge.', next_pressure='Rain may delay departure.')),
                         'The repairs are finished.\n\nThe road is safer.\n\nYou inspected the bridge.\n\nRain may delay departure.')

    def test_exact_repeats_and_placeholders(self):
        self.assertEqual(beat_body(dict(narrative='**Paulie** paid you 8,000 berries.',
                                       why_it_matters='Paulie paid you 8,000 berries.', player_knowledge='None', next_pressure=None)),
                         '**Paulie** paid you 8,000 berries.')

    def test_no_truncation_or_approximate_dedup(self):
        prose = '“Do not leave yet,” said Dr. Kureha.\n\n' + ('The villagers repair their homes. ' * 500)
        result = beat_body(dict(narrative=prose, why_it_matters='You earned 8,000 berries.', player_knowledge='You spent 8,000 berries.'))
        self.assertTrue(result.startswith(prose.strip()))
        self.assertIn('You earned 8,000 berries.\n\nYou spent 8,000 berries.', result)

    def test_writing_rule_is_in_request_not_extra_ai_call(self):
        from gm_consistency import prepare_request
        result = prepare_request({'name':'Test','world':'One Piece'}, {'task':'moment','action':'Rest.'})
        self.assertEqual(result['chronicle_writing'], WRITING_RULE)

    def test_special_stone_classifier_ignores_incidental_words(self):
        js = (ROOT/'frontend/js/app.js').read_text(encoding='utf-8')
        fn = js[js.index('function poneglyphTone('):js.index('function storyBeatLabel(')]
        cases = [({'tag':'canon_event'}, 'special'), ({'tag':'system','text':'[REWARD]\n8,000 berries'}, 'special'),
                 ({'tag':'narrative','text':'You ask about the reward, but earn nothing.'}, 'standard'),
                 ({'tag':'growth','text':'Routine training continues.'}, 'standard'),
                 ({'tag':'system','detail':{'chronicle_tone':'special'}}, 'special'),
                 ({'tag':'system','text':'[NOTICE]\nWelcome back.'}, 'standard')]
        script = fn + '\nconst cases=' + json.dumps(cases) + '; for(const [entry,want] of cases){if(poneglyphTone(entry)!==want)throw Error(JSON.stringify(entry));}'
        subprocess.run(['node', '-e', script], check=True, capture_output=True)

    def test_font_bundled_and_old_texture_not_used(self):
        self.assertGreater((ROOT/'frontend/fonts/nova-square.ttf').stat().st_size, 1000)
        self.assertTrue((ROOT/'frontend/fonts/Nova-Square-OFL.txt').exists())
        css = (ROOT/'frontend/css/style.css').read_text(encoding='utf-8')
        self.assertNotIn('url("/art/one-piece/poneglyph-chronicle.png")', css)
