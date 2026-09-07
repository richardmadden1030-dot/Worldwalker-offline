import copy
import unittest

from character_paths import public_view as path_view, pin as pin_path, actions as path_actions
from canon_divergence import target as target_canon, public_view as intervention_view
from property_economy import public_view as economy_view
from reputation_system import public_view as reputation_view
from world_conflict import public_view as conflict_view


class V364SystemTests(unittest.TestCase):
    def base_state(self):
        return {
            'world': 'Naruto', 'name': 'Test Shinobi', 'campaign_id': 'v364-test',
            'turn': 10, 'canon_day': 0, 'canon_time_minutes': 480,
            'location': 'Konohagakure', 'location_details': {'Konohagakure': {'controlling_faction': 'Konohagakure'}},
            'skills': {'Wind Step': {'description': 'A movement technique', 'effect_type': 'movement', 'target_type': 'self'}},
            'npc_memories': {}, 'contacts': {}, 'companions': [], 'special': {},
            'currency': {'name': 'Ryo', 'amount': 1000}, 'reputation': {},
        }

    def test_read_views_do_not_create_system_ledgers(self):
        state = self.base_state(); before = copy.deepcopy(state)
        path_view(state); economy_view(state); reputation_view(state); conflict_view(state)
        self.assertEqual(state, before)

    def test_character_path_pin_uses_existing_skill(self):
        state = self.base_state()
        rows = path_view(state)['paths']; self.assertEqual(len(rows), 1)
        result = pin_path(state, rows[0]['id'])
        self.assertEqual(result['pinned'], rows[0]['id'])
        self.assertTrue(any(row['id'].startswith('path:') for row in path_actions(state)))

    def test_minor_canon_event_can_be_targeted(self):
        state = self.base_state()
        from worlds import timeline_for
        event = next((e for e in timeline_for('Naruto').get('events', [])
                      if isinstance(e, dict) and e.get('major') is False and int(e.get('day', 0)) > state['canon_day']), None)
        if event is None:
            self.skipTest('Installed Naruto timeline has no future minor event in this fixture.')
        event_id = event.get('id') or f"day:{event.get('day',0)}:{event.get('title','event')}"
        target_canon(state, event_id)
        self.assertEqual(intervention_view(state)['active'][0]['event_id'], event_id)


if __name__ == '__main__':
    unittest.main()
