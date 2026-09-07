"""Evidence-based social opportunities; narration uses the existing GM request.

No automatic affection, obedience, powers, rewards, or rival stat scaling.
Existing NPC consequence chains remain the source of shared experiences.
"""
import hashlib
import re


def obj(value): return value if isinstance(value, dict) else {}
def seq(value): return value if isinstance(value, list) else []
def text(value): return value.strip() if isinstance(value, str) else ''
def integer(value, default=0):
    try: return int(value)
    except (ValueError, TypeError, OverflowError): return default


def lookup(state, field, name):
    return next((obj(v) for k, v in obj(state.get(field)).items()
                 if str(k).casefold() == name.casefold()), {})


def available(state, name):
    """All recorded sources can veto contact; a stale contact cannot revive an NPC."""
    records = [lookup(state, field, name) for field in ('npc_memories', 'contacts')]
    records += [row for row in seq(state.get('companions')) if isinstance(row, dict)
                and text(row.get('name')).casefold() == name.casefold()]
    for group in obj(state.get('organizations')).values():
        records += [obj(v) for k, v in obj(obj(group).get('members')).items()
                    if str(k).casefold() == name.casefold()]
    return bool(name) and name.casefold() != text(state.get('name')).casefold() and not any(
        row.get('alive') is False or row.get('deceased') is True or
        text(row.get('status')).casefold() in {'dead', 'deceased', 'missing', 'incapacitated', 'imprisoned'}
        for row in records)


def route(state, name):
    if not available(state, name): return ''
    scene = obj(state.get('scene_state'))
    present = [text(r.get('name')) if isinstance(r, dict) else text(r) for r in seq(scene.get('present'))]
    if scene.get('location', state.get('location')) == state.get('location') and name.casefold() in {n.casefold() for n in present}:
        return 'in_person'
    contact = lookup(state, 'contacts', name)
    if contact.get('can_contact') is True and contact.get('blocked') is not True:
        return 'message'
    return ''


def fingerprint(name, event):
    clean = re.sub(r'\W+', ' ', event.casefold()).strip()
    return hashlib.sha256((name.casefold() + '|' + clean).encode()).hexdigest()[:24]


def candidates(state, limit=4):
    """Read-only and old-save compatible. A private ambition alone is not a hook."""
    if obj(state.get('combat')).get('active') or state.get('alive') is False: return []
    store = obj(state.get('relationship_life'))
    turn = integer(state.get('turn'))
    if turn - integer(store.get('last_turn'), -99) < 3: return []
    result = []
    for name, raw in obj(state.get('npc_memories')).items():
        if not isinstance(name, str) or not isinstance(raw, dict): continue
        via = route(state, name)
        if not via: continue
        delivery = lookup(state, 'message_delivery_state', name)
        if turn - integer(delivery.get('last_incoming_turn'), -99) < 3: continue
        # These are explicitly shared relationship events, NOT arbitrary world news.
        for row in reversed(seq(raw.get('chain'))[-12:]):
            event = text(obj(row).get('event')) if isinstance(row, dict) else text(row)
            if not event or len(event) > 600: continue
            if isinstance(row, dict) and integer(row.get('turn'), -1) >= turn: continue
            token = fingerprint(name, event)
            if token in obj(store.get('handled')): continue
            result.append({'id': token, 'actor': name, 'experience': event, 'route': via,
                           'role': text(raw.get('role'))[:120], 'attitude': text(raw.get('attitude'))[:100],
                           'goal': text(raw.get('immediate_goal') or raw.get('goal'))[:200],
                           'nemesis': raw.get('nemesis') is True,
                           'last_followup': integer(obj(store.get('actor_turns')).get(name), -99)})
            break
    result.sort(key=lambda r: (r['last_followup'], r['actor'].casefold()))
    return result[:limit]


RULE = """LIVING RELATIONSHIPS: Record meaningful shared experiences in the existing npc_memories[name].chain_event, including kept/broken promises, help, respect, shared victories and quiet time; do not require an attitude change. Keep each entry one concrete sentence, not generic approval. Do not duplicate a recorded experience.
Optional relationship_candidates are remembered facts, NOT required events or proof of current availability/resources. At most one natural follow-up per turn: a specific thank-you, ordinary companionship, an offer of training/work/help, or an appropriate rival response. Use the person's canon temperament, current role, chat history and knowledge. State what they actually say, not a directive to the narrator or an event-card title. Quiet positive moments need no demand, penalty or new quest. Offers need player agreement before committing time, joining, training or rewards. Affection/trust never creates command authority; existing command fidelity still applies. Old shared history is not knowledge of new private actions. A remote message requires a lore-appropriate established route and enough delivery time; otherwise defer it. For relationship_followups return {id: candidate ID, actor, disposition: send|defer|close, message: complete short in-character dialogue, reason: concrete current cause, delivery:{channel: in_person|message, basis: actual route and timing}}. close means this specific opportunity was already settled/inappropriate, not that the relationship ended. Returning [] is valid. Defer changes nothing.
RIVALS: nemesis marks an important recurring opponent, not inevitable hostility, surveillance or a power multiplier. Use established motives, resources and known facts for their choices. Continue meaningful rival projects via existing world_plan_updates; preparation may progress locally, but victories and contested outcomes require resolution. Never match their stats to the player, resurrect defeated enemies, force sabotage, or negate a clean success to sustain rivalry. Allies can offer useful help in their actual specialty without twisting orders. Cooperation, rivalry, trust and authority are distinct."""


def prepare(state, packet):
    packet['relationship_guidance'] = RULE
    # Direct conversations use existing chain memory and the same writing rules,
    # but must not inject an unsolicited second conversation into the reply.
    if packet.get('thread') or 'chat' in text(packet.get('task')): return
    options = candidates(state)
    if options:
        packet['relationship_candidates'] = options
        if not isinstance(packet.get('schema'), dict): packet['schema'] = {}
        packet['schema']['relationship_followups'] = [
            {'id': 'candidate ID', 'actor': 'exact candidate actor', 'disposition': 'send|defer|close',
             'message': 'short complete dialogue', 'reason': 'current grounded reason',
             'delivery': {'channel': 'in_person|message', 'basis': 'established route and timing'}}]


def resolve(before, state, data):
    """Validate locally; no time, numeric relationship or resource changes."""
    eligible = {r['id']: r for r in candidates(before)}
    if not eligible: return []
    existing = {text(obj(r).get('sender')).casefold() for r in seq(data.get('incoming_chats'))}
    for raw in seq(data.get('relationship_followups'))[:4]:
        row = obj(raw); option = eligible.get(text(row.get('id')))
        if not option or text(row.get('actor')).casefold() != option['actor'].casefold(): continue
        name = option['actor']; disposition = row.get('disposition')
        if disposition not in {'send', 'close'} or not text(row.get('reason')): continue
        if not available(state, name): continue
        store = obj(state.get('relationship_life'))
        if option['id'] in obj(store.get('handled')): continue
        turn = integer(state.get('turn'))
        if turn - integer(store.get('last_turn'), -99) < 3: continue
        message = text(row.get('message')); delivery = obj(row.get('delivery'))
        if disposition == 'send':
            if name.casefold() in existing: continue
            if not message or len(message) > 900 or not text(delivery.get('basis')): continue
            if delivery.get('channel') != route(state, name): continue
        if not isinstance(state.get('relationship_life'), dict): state['relationship_life'] = {}
        store = state['relationship_life']
        handled = dict(obj(store.get('handled')))
        handled[option['id']] = {'actor': name, 'turn': turn, 'disposition': disposition}
        # Retain fingerprints only while their source memory still exists; never
        # replay an old opportunity simply because an arbitrary global cap rolls.
        retained = {fingerprint(str(n), text(obj(r).get('event')) if isinstance(r, dict) else text(r))
                    for n, m in obj(state.get('npc_memories')).items() for r in seq(obj(m).get('chain'))}
        store['handled'] = {k: v for k, v in handled.items() if k in retained or k == option['id']}
        store['last_turn'] = turn
        actor_turns = dict(obj(store.get('actor_turns'))); actor_turns[name] = turn
        store['actor_turns'] = {k: v for k, v in actor_turns.items() if k in obj(state.get('npc_memories'))}
        if disposition == 'close': return []
        return [{'thread': name, 'sender': name, 'message': message, 'channel': delivery['channel'],
                 'reason': text(row['reason']), 'metadata': {'relationship_followup': option['id']}}]
    return []
