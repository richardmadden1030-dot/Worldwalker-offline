"""Campaign-scoped, bounded idempotency records. Never a gameplay prompt input."""
import copy
from gm_refinements import fingerprint
from turn_recovery import guard

KEY = '_request_receipts'
LIMIT = 8


def campaign(state):
    return state.get('campaign_id') or f"{state.get('world', '')}:{state.get('name', '')}"


def completed(game, request_id, route=None, payload=None):
    records = game.state.get(KEY)
    record = records.get(request_id) if isinstance(records, dict) else None
    if not isinstance(record, dict):
        return None
    if record.get('campaign') != campaign(game.state):
        raise ValueError('This request belongs to another campaign.')
    if route is not None and record.get('route') != route:
        raise ValueError('This request ID belongs to a different operation.')
    if payload is not None and record.get('input') != fingerprint(payload):
        raise ValueError('This request ID was already used for a different action.')
    result = copy.deepcopy(record.get('result'))
    if not isinstance(result, dict):
        raise ValueError('The stored request result is unreadable. Inspect the Chronicle before continuing.')
    if 'state' in result or record.get('has_state'):
        result['state'] = game.public_state()
    result['_recovery_guard'] = guard(game.state)
    result['replayed_request'] = True
    return result


def remember(game, request_id, route, payload, result):
    if not request_id or not isinstance(result, dict):
        return
    records = game.state.get(KEY)
    records = dict(records) if isinstance(records, dict) else {}
    records[request_id] = {'campaign': campaign(game.state), 'route': route, 'input': fingerprint(payload),
                           'has_state': 'state' in result,
                           'result': {k: copy.deepcopy(v) for k, v in result.items() if k != 'state'}}
    game.state[KEY] = dict(list(records.items())[-LIMIT:])


def status(game, request_id, route):
    inflight = getattr(game, '_inflight_request', None)
    if inflight or getattr(game, 'busy', False):
        return {'status': 'in_progress'}
    result = completed(game, request_id, route)
    if result is not None:
        return {'status': 'completed', 'result': result}
    failed = game.state.get('last_failed_turn')
    if isinstance(failed, dict) and failed.get('route') == route and isinstance(failed.get('payload'), dict) and failed['payload'].get('request_id') == request_id:
        return {'status': 'failed', 'campaign': campaign(game.state), 'guard': guard(game.state)}
    return {'status': 'unknown', 'campaign': campaign(game.state), 'guard': guard(game.state)}
