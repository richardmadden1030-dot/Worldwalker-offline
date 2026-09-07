"""Local tactical geometry and encounter profiles. Terrain only blocks occupancy.

The GM owns identities, established powers and why a fight exists. Python owns
the board, paths, footprints, resource accounting and activation order.
"""
from __future__ import annotations

import copy
import hashlib
import math
import random
import re
from collections import deque

from power_benchmarks import benchmark_tier
from skill_system import infer_skill_metadata
from worlds import defense_stat_for, power_profile_for, speed_stat_for

CARDINAL = ((0, -1), (1, 0), (0, 1), (-1, 0))
VERSION = 1
MAX_UNITS = 24


def obj(value):
    return value if isinstance(value, dict) else {}


def seq(value):
    return value if isinstance(value, list) else []


def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) and not isinstance(value, bool) else default
    except (TypeError, ValueError):
        return default


def words(row):
    return ' '.join(str(row.get(k) or '') for k in
                    ('name', 'description', 'effect', 'role', 'rank', 'type', 'weapon', 'power_reason')).lower()


def movement_budget(speed=30, board_size=12):
    """Distance derives from effective speed, never XP level or overall power.

    Examples: speed 30 -> 3 squares, 120 -> 6, 480 -> 12. The square-root
    curve preserves a meaningful gap without making ordinary improvements
    teleport a fighter across the board. Only the battlefield bounds cap it.
    """
    amount = round(3 * math.sqrt(max(1, number(speed, 30)) / 30))
    return min(board_size * 2 - 2, max(1, amount))


def refresh_movement(state, board):
    """Buffs/debuffs alter remaining distance without refunding spent steps."""
    combat = obj(state.get('combat'))
    for unit in live_units(board):
        rows = [*seq(unit.get('buffs')), *seq(unit.get('debuffs'))]
        if unit.get('player'):
            rows = [*seq(combat.get('player_buffs')), *seq(combat.get('player_debuffs'))]
        pct = sum(number(row.get('speed_pct')) for row in rows if isinstance(row, dict)
                  and number(row.get('rounds_left'), 1) > 0)
        pct = max(-.9, pct)
        unit['speed'] = max(1, round(number(unit.get('base_speed'), unit.get('speed', 30)) * (1+pct), 1))
        used = max(0, int(number(unit.get('movement_max'))-number(unit.get('movement_left'))))
        unit['movement_max'] = movement_budget(unit['speed'], board['width'])
        unit['movement_left'] = max(0, unit['movement_max']-used)


def environment_for(state):
    combat = obj(state.get('combat'))
    text = ' '.join(str(x or '') for x in (combat.get('environment'), combat.get('location'),
                       state.get('location'), obj(state.get('scene_state')).get('setting'))).lower()
    for kind, pattern, obstacles, density in (
        ('forest', r'forest|woodland|grove|jungle|trees|training ground', ('tree', 'rock'), .15),
        ('ship', r'ship|deck|vessel|boat', ('crate', 'mast'), .11),
        ('interior', r'room|hall|inside|interior|academy|temple|dungeon', ('pillar', 'crate'), .13),
        ('urban', r'street|city|town|village|seireitei|konoha|alley', ('building', 'crate'), .15),
        ('cave', r'cave|cavern|tunnel|mine', ('rock',), .17),
        ('open', r'desert|beach|plain|wasteland|clearing|arena|sea|ocean', ('rock',), .06),
    ):
        if re.search(pattern, text):
            return {'kind': kind, 'obstacles': obstacles, 'density': density}
    return {'kind': 'open', 'obstacles': ('rock',), 'density': .08}


def cells(board):
    return {(x, y) for y in range(board['height']) for x in range(board['width'])}


def blocked_cells(board):
    return {(int(r['x']), int(r['y'])) for r in seq(board.get('obstacles')) if isinstance(r, dict)}


def live_units(board):
    return [u for u in seq(board.get('units')) if isinstance(u, dict) and u.get('alive', True)
            and number(u.get('hp'), 1) > 0 and not u.get('defeated') and not u.get('escaped')]


def paths(board, start, budget=None, ignore_id=None, allow_target=None):
    """Four-neighbour BFS; every step costs one movement and never an action."""
    start = tuple(start)
    mover=next((u for u in live_units(board) if u.get('id')==ignore_id),{})
    mobile=bool({'flight','geppo','air-walk'} & set(seq(mover.get('capabilities'))))
    blocked = set() if mobile else blocked_cells(board)
    blocked.update((u['x'], u['y']) for u in live_units(board)
                   if u.get('id') != ignore_id and (u['x'], u['y']) != allow_target)
    queue = deque([start]); found = {start: []}
    while queue:
        x, y = queue.popleft()
        path = found[(x, y)]
        if budget is not None and len(path) >= budget:
            continue
        for dx, dy in CARDINAL:
            p = (x + dx, y + dy)
            if p in found or p in blocked or not (0 <= p[0] < board['width'] and 0 <= p[1] < board['height']):
                continue
            found[p] = path + [p]; queue.append(p)
    if mobile:
        for p in blocked_cells(board):found.pop(p,None)
    return found


def connected(board):
    """Every walkable tile is connected, and each actor can approach all others."""
    available = cells(board) - blocked_cells(board)
    if not available:
        return False
    bare = {**board, 'units': []}
    if len(paths(bare, next(iter(available)))) != len(available):
        return False
    actors = live_units(board)
    for actor in actors:
        accessible = paths(board, (actor['x'], actor['y']), ignore_id=actor['id'])
        for other in actors:
            if other is actor:
                continue
            if not any((other['x'] + dx, other['y'] + dy) in accessible for dx, dy in CARDINAL):
                return False
    return True


def make_board(state, units):
    count = len(units)
    size = 8 if count <= 4 else 10 if count <= 8 else 12 if count <= 16 else 16
    combat = obj(state.get('combat'))
    identity = '|'.join(str(state.get(k) or '') for k in ('campaign_id', 'turn', 'canon_time_minutes', 'location'))
    identity += '|' + str(combat.get('cause', '')) + '|' + '|'.join(u['name'] for u in units)
    seed = int(hashlib.sha256(identity.encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    board = {'version': VERSION, 'width': size, 'height': size, 'seed': str(seed),
             'environment': environment_for(state)['kind'], 'units': units, 'obstacles': [],
             'activation': 1, 'active_id': 'player', 'revision': 0, 'last_footprint': [], 'last_path': []}
    allies = [u for u in units if u['side'] == 'ally']
    enemies = [u for u in units if u['side'] == 'enemy']
    # Spread spawns; no unit starts inside an object or in a one-square pocket.
    left = [(x, y) for x in range(1, max(2, size // 3)) for y in range(1, size - 1)]
    right = [(x, y) for x in range(size - 3, size - 1) for y in range(1, size - 1)]
    rng.shuffle(left); rng.shuffle(right)
    for actors, places in ((allies, left), (enemies, right)):
        for i, actor in enumerate(actors):
            actor['x'], actor['y'] = places[i]
            actor['next_at'] = 0 if actor['id'] == 'player' else .25 + i * .08
            actor['movement_max'] = movement_budget(actor['speed'], size)
            actor['movement_left'] = actor['movement_max']
            actor['action_used'] = False
    env = environment_for(state)
    occupied = {(u['x'], u['y']) for u in units}
    safe = occupied | {(x+dx, y+dy) for x, y in occupied for dx, dy in CARDINAL}
    candidates = list(cells(board) - safe)
    rng.shuffle(candidates)
    wanted = int(size * size * env['density'])
    for x, y in candidates:
        board['obstacles'].append({'x': x, 'y': y, 'kind': rng.choice(env['obstacles'])})
        if not connected(board):
            board['obstacles'].pop()
        if len(board['obstacles']) >= wanted:
            break
    return board


def ability_footprint(name='', detail=None, board_size=12):
    """Compile compact explicit geometry or infer it from established wording.

    The same compiler drives the UI preview and authoritative hit selection.
    Obstacles have no line-of-sight, armour or special damage properties.
    """
    detail = obj(detail)
    meta = infer_skill_metadata(name or 'Attack', detail)
    raw = obj(detail.get('tactical') or obj(detail.get('mechanics')).get('tactical'))
    text = (name + ' ' + words(detail)).lower()
    effect = raw.get('effect', meta.get('effect_type', 'damage'))
    shape, reach, radius, length, width, origin = 'single', 1, 0, 1, 1, 'target'
    if effect in {'heal', 'buff', 'shield', 'cleanse', 'transform', 'detect', 'stealth', 'summon', 'utility', 'movement'}:
        shape, reach, origin = 'self', 0, 'self'
    if re.search(r'\b(beam|ray|piercing line|straight line|linear wave)\b', text):
        shape, reach, length, origin = 'line', 5, 5, 'self'
    elif re.search(r'\b(cone|breath|fan.shaped|flamethrower|fireball jutsu)\b', text):
        shape, reach, length, origin = 'cone', 3, 3, 'self'
    elif re.search(r'\b(sweep\w*|wide slash|cleave|crescent|arc)\b', text):
        shape, reach, width, origin = 'arc', 1, 3, 'self'
    elif re.search(r'\b(all around|surrounding|shockwave|radial|domain expansion|almighty push)\b', text):
        shape, reach, radius, origin = 'burst', 0, 2, 'self'
    elif re.search(r'\b(explosion|explosive|detonat\w*|blast radius|area of effect)\b', text):
        shape, reach, radius, origin = 'burst', 5, 1, 'target'
    elif re.search(r'\b(projectile|ranged|throw|kunai|shuriken|arrow|bullet|shoot|fireball|bolt)\b', text):
        reach = 5
    shape = raw.get('shape', shape)
    if shape not in {'single', 'self', 'line', 'cone', 'arc', 'burst', 'ring', 'cross'}:
        shape = 'single'
    origin = raw.get('origin', origin)
    if origin not in {'self', 'target'}:
        origin = 'target'
    limit = max(8, board_size * 2)
    return {'shape': shape, 'origin': origin,
            'range': int(max(0, min(limit, number(raw.get('range'), reach) + number(detail.get('mastery_range_bonus'), 0)))),
            'radius': int(max(0, min(board_size, number(raw.get('radius'), radius)))),
            'length': int(max(1, min(limit, number(raw.get('length'), length)))),
            'width': int(max(1, min(board_size, number(raw.get('width'), width)))),
            'effect': effect, 'friendly_fire': raw.get('friendly_fire') is True,
            'exclude_origin':raw.get('exclude_origin') is True,
            'source': 'authored' if raw else 'description',
            'free_action': effect == 'transform' and detail.get('voluntary', True) is not False}


def footprint_cells(board, actor, spec, target=None, facing='east'):
    directions = {'north': (0, -1), 'east': (1, 0), 'south': (0, 1), 'west': (-1, 0)}
    dx, dy = directions.get(facing, (1, 0)); px, py = -dy, dx
    ax, ay = int(actor['x']), int(actor['y'])
    tx, ty = (target if target is not None else (ax+dx, ay+dy))
    if spec['origin'] == 'target' and abs(tx-ax)+abs(ty-ay) > spec['range']:
        return []
    shape = spec['shape']; output = set()
    if shape == 'self':
        output.add((ax, ay))
    elif shape == 'single':
        output.add((tx, ty))
    elif shape in {'burst', 'ring', 'cross'}:
        cx, cy = (ax, ay) if spec['origin'] == 'self' else (tx, ty)
        r = spec['radius']
        for x in range(cx-r, cx+r+1):
            for y in range(cy-r, cy+r+1):
                d = abs(x-cx)+abs(y-cy)
                if d <= r and (shape != 'ring' or d == r) and (shape != 'cross' or x == cx or y == cy):
                    output.add((x, y))
    else:
        for distance in range(1, (1 if shape == 'arc' else spec['length'])+1):
            half = distance-1 if shape == 'cone' else spec['width']//2
            for offset in range(-half, half+1):
                output.add((ax+dx*distance+px*offset, ay+dy*distance+py*offset))
    if spec.get('exclude_origin'): output.discard((ax,ay))
    return sorted(output & cells(board))


ENEMY_TEMPLATES = {
    'strike': {'shape': 'single', 'range': 1, 'origin': 'target'},
    'projectile': {'shape': 'single', 'range': 5, 'origin': 'target'},
    'sweep': {'shape': 'arc', 'range': 1, 'width': 3, 'origin': 'self'},
    'beam': {'shape': 'line', 'length': 5, 'origin': 'self'},
    'breath': {'shape': 'cone', 'length': 3, 'origin': 'self'},
    'blast': {'shape': 'burst', 'range': 4, 'radius': 1, 'origin': 'target'},
    'pulse': {'shape': 'burst', 'radius': 2, 'origin': 'self'},
}


def enemy_abilities(raw, power):
    """Reuse mechanical templates, not randomly granted bloodlines/unique moves."""
    from enemy_attack_catalog import attack_for
    raw = obj(raw); text = words(raw)
    tier = min(5, sum(power >= t for t in (35, 90, 200, 600, 1000)))
    result = []
    authored = raw.get('abilities') or raw.get('skills')
    if isinstance(authored, dict):
        authored = [{'name': name, **obj(detail)} for name, detail in authored.items()]
    for row in seq(authored)[:12]:
        row = {'name': row} if isinstance(row, str) else obj(row)
        name = str(row.get('name') or '')[:120]
        if name:
            result.append({**row, 'name': name, 'tactical': ability_footprint(name, row),
                           'effectiveness': tier, 'source': 'established ability'})
    if not result:
        result.append(attack_for('strike', power))
        patterns = (
            ('projectile', r'archer|bow|rifle|pistol|sniper|kunai|shuriken|throw|ranged|projectile', 'Projectile attack'),
            ('sweep', r'wide slash|sweep|cleave', 'Sweeping attack'),
            ('beam', r'beam|ray|cero', 'Beam attack'),
            ('breath', r'breath|flamethrower|cone', 'Breath attack'),
            ('blast', r'explosive|explosion|detonat', 'Explosive attack'),
            ('pulse', r'shockwave|radial', 'Radial attack'),
            ('binding', r'\b(binding|paralysis|restraint technique|bakudo)\b', 'Binding attack'),
            ('weakening', r'\b(poison|weakening|debilitat)\b', 'Weakening attack'),
            ('shield', r'\b(barrier technique|shield spell)\b', 'Barrier'),
            ('heal', r'\b(healing technique|healer|medical ninjutsu|regeneration)\b', 'Recovery'),
        )
        for kind, pattern, label in patterns:
            if re.search(pattern, text):
                result.append(attack_for(kind, power))
    return result


def combat_profile(state, raw, side='enemy', unit_id='enemy-1'):
    """Current campaign facts outrank canon; unsupported player-level inflation doesn't."""
    from combat import _fallback_enemy_power
    from organizations import power_for
    raw = copy.deepcopy(obj(raw)); name = str(raw.get('name') or 'Opponent')[:160]
    world = state.get('world', 'Custom World')
    memory = next((obj(v) for k, v in obj(state.get('npc_memories')).items() if k.casefold() == name.casefold()), {})
    for companion in seq(state.get('companions')):
        if isinstance(companion, dict) and str(companion.get('name', '')).casefold() == name.casefold():
            memory = {**memory, **companion}
    established = {**memory, **raw}
    stats = obj(memory.get('stats')) or obj(raw.get('stats'))
    anchor = power_for(state, name, people={name: memory})
    authored = number(raw.get('power'), 0)
    own_role = _fallback_enemy_power(world, established)
    anchored = number(anchor.get('score'), 0)
    # A named transformation, injury or training result is a legitimate
    # encounter-specific departure. A huge naked number is not evidence.
    reason = str(raw.get('power_reason') or raw.get('strength_basis') or '').strip()
    if stats:
        p = power_profile_for(world, stats, established.get('archetype', ''))
        power = number(obj(p.get('world_combat') or p.get('combat')).get('score'), own_role)
        source = 'recorded combat attributes'
    elif anchored > 0 and not reason:
        power = anchored; source = anchor.get('source', 'campaign/canon benchmark')
    elif authored > 0:
        ordinary = bool(re.search(r'\b(civilian|bandit|thug|farmer|common guard|ordinary soldier)\b', words(established)))
        if ordinary and not reason and authored > own_role * 2:
            power = own_role; source = 'role correction: unsupported inflation removed'
        else:
            power = authored; source = 'narrative encounter estimate' if reason else 'narrator estimate'
    else:
        power = own_role; source = 'world role estimate'
    power = max(1, min(1000000, power))
    corrected = authored > 0 and abs(power-authored) > 1 and 'recorded' not in str(source)
    # Correct the whole unsupported profile, not just the displayed power label.
    speed = max(1, number(stats.get(speed_stat_for(world)), power if corrected else number(raw.get('speed'), power)))
    defense = max(1, number(stats.get(defense_stat_for(world)), power if corrected else number(raw.get('defense'), power)))
    old_max = max(1, number(raw.get('hp_max'), number(raw.get('hp'), power*2)))
    hp_max = max(20, round(power*2)) if corrected else max(1, round(old_max))
    hp = round(hp_max * min(1, max(0, number(raw.get('hp'), old_max) / old_max)))
    capabilities=set(seq(established.get('capabilities')))
    if world=='One Piece':
        text=words(established)
        if 'logia' in text:capabilities.add('logia')
        if re.search(r'armament.*haki|busoshoku',text):capabilities.add('armament-haki')
        if re.search(r'observation.*haki|kenbunshoku',text):capabilities.add('observation-haki')
        if re.search(r'geppo|moonwalk|flight|flying',text):capabilities.add('flight')
    elif world=='Bleach':
        text=words(established)
        if re.search(r'\b(shunpo|flash step)\b',text):capabilities.add('shunpo')
        if re.search(r'\bshikai\b',text):capabilities.add('shikai')
        if re.search(r'\bbankai\b',text):capabilities.update({'shikai','bankai'})
        if re.search(r'\b(flying|flight|winged)\b',text):capabilities.add('flight')
    return {**raw, 'id': unit_id, 'name': name, 'side': side,
            'power': round(power, 1), 'power_source': source,
            'power_tier': benchmark_tier(world, power)['name'], 'strength_basis': reason,
            'speed': round(speed, 1), 'base_speed': round(speed, 1), 'defense': round(defense, 1),
            'level': raw.get('level', memory.get('level')),
            'hp': hp, 'hp_max': hp_max, 'alive': raw.get('alive', hp > 0),
            'resource': max(0, number(raw.get('resource'), 100)), 'resource_max': max(1, number(raw.get('resource_max'), 100)),
            'statuses': copy.deepcopy(seq(raw.get('statuses') or raw.get('multiplayer_statuses'))),
            'debuffs': [], 'buffs': [], 'cooldowns': {},
            'capabilities': sorted(capabilities),
            'abilities': enemy_abilities(established, power)}


def player_profile(state):
    if state.get('world')=='One Piece':
        from one_piece_tactics import capabilities as saved_capabilities
    elif state.get('world')=='Bleach':
        from bleach_tactics import capabilities as saved_capabilities
    else:
        from naruto_tactics import saved_capabilities
    stats = obj(state.get('stats')); world = state.get('world', 'Custom World')
    profile = power_profile_for(world, stats, obj(state.get('special')).get('Archetype', ''))
    power = number(obj(profile.get('world_combat') or profile.get('combat')).get('score'), 30)
    combat=obj(state.get('combat'))
    return {'id': 'player', 'name': str(state.get('name') or 'You'), 'side': 'ally', 'player': True,
            'hp': number(state.get('hp'), 100), 'hp_max': number(state.get('hp_max'), 100),
            'resource': number(state.get('resource'), 100), 'resource_max': number(state.get('resource_max'), 100),
            'level': state.get('level'), 'power': power, 'power_tier': benchmark_tier(world, power)['name'],
            'speed': max(1, number(stats.get(speed_stat_for(world)), power)),
            'base_speed': max(1, number(stats.get(speed_stat_for(world)), power)),
            'defense': max(1, number(stats.get(defense_stat_for(world)), power)), 'alive': True,
            'capabilities': saved_capabilities(state), 'stats':copy.deepcopy(stats),
            'statuses': copy.deepcopy(seq(combat.get('player_statuses'))),
            'debuffs': copy.deepcopy(seq(combat.get('player_debuffs'))),
            'buffs': copy.deepcopy(seq(combat.get('player_buffs'))), 'cooldowns': {}}


def ensure_board(state):
    combat = obj(state.get('combat'))
    if not combat.get('active'):
        return obj(combat.get('tactical'))
    existing = obj(combat.get('tactical'))
    if existing.get('version') == VERSION and seq(existing.get('units')):
        # Preserve positions and spent allowances through refreshes / old saves.
        player = next((u for u in existing['units'] if isinstance(u, dict) and u.get('id') == 'player'), None)
        if player:
            player.update({k: v for k, v in player_profile(state).items()
                           if k not in {'statuses', 'debuffs', 'buffs', 'cooldowns', 'alive'}})
        # Migrate already-running single-player boards: friendly companions are
        # choices for the player, never hidden AI actors.
        if not existing.get('owners') and state.get('world') in {'Naruto','One Piece','Bleach'}:
            if state.get('world')=='One Piece':from one_piece_tactics import compile_skill
            elif state.get('world')=='Bleach':from bleach_tactics import compile_skill
            else:from naruto_tactics import compile_skill
            for unit in existing['units']:
                if unit.get('side')!='ally' or unit.get('player') or unit.get('human'):continue
                unit['player_controlled']=True
                if not obj(unit.get('skills')):
                    compiled=[compile_skill(a.get('name',''),a) for a in seq(unit.get('abilities')) if isinstance(a,dict)]
                    unit['abilities']=compiled;unit['skills']={a['name']:copy.deepcopy(a) for a in compiled if a.get('name')}
        refresh_movement(state, existing)
        return existing
    raw_enemies = seq(combat.get('opponents')) or seq(combat.get('enemies'))
    if not raw_enemies:
        aggregate = copy.deepcopy(obj(combat.get('enemy')))
        count = max(1, min(12, int(number(aggregate.get('group_size'), 1)))) if aggregate.get('is_group') else 1
        for i in range(count):
            row = copy.deepcopy(aggregate)
            if count > 1:
                row['name'] = f"{aggregate.get('name', 'Opponent')} · {i+1}"
                row['hp_max'] = max(1, round(number(aggregate.get('hp_max'), 100) / count))
                row['hp'] = max(0, round(number(aggregate.get('hp'), 100) / count))
                row['power'] = max(1, number(aggregate.get('power'), 30) - min(40, (count-1)*5))
                row['is_group'] = False; row.pop('group_size', None)
            raw_enemies.append(row)
    units = [player_profile(state)]
    for i, raw in enumerate(raw_enemies[:MAX_UNITS-1]):
        raw = {'name': raw} if isinstance(raw, str) else raw
        units.append(combat_profile(state, raw, unit_id=f'enemy-{i+1}'))
    # Only physically present, combat-support-enabled companions join the board.
    from simulation_core import companion_support_for_combat
    for row in companion_support_for_combat(state)[:min(6, MAX_UNITS-len(units))]:
        if row.get('name') == state.get('name'):
            continue
        ally=combat_profile(state, row, 'ally', f'ally-{len(units)}')
        ally.update(player_controlled=state.get('world') in {'Naruto','One Piece','Bleach'},character=copy.deepcopy(row))
        units.append(ally)
    board = make_board(state, units)
    board['world_rules'] = state.get('world') if combat.get('tactical_enabled') else ''
    board['naruto_rules'] = board['world_rules']=='Naruto'
    board['one_piece_rules'] = board['world_rules']=='One Piece'
    board['bleach_rules'] = board['world_rules']=='Bleach'
    board['conditions'] = copy.deepcopy(seq(combat.get('conditions')))
    board['teleport_marks'] = copy.deepcopy(seq(combat.get('teleport_marks')))
    if state.get('world') in {'Naruto','One Piece','Bleach'}:
        if state.get('world')=='One Piece':from one_piece_tactics import compile_skill
        elif state.get('world')=='Bleach':from bleach_tactics import compile_skill
        else:from naruto_tactics import compile_skill
        for unit in units:
            if not unit.get('player'):
                unit['abilities'] = [compile_skill(a['name'],a) for a in unit['abilities']]
                if unit.get('player_controlled'):
                    unit['skills']={a.get('name',f"Ability {i+1}"):copy.deepcopy(a)
                                    for i,a in enumerate(unit['abilities']) if a.get('name')}
    combat['tactical'] = board
    from encounter_objectives import initialize as initialize_objective
    initialize_objective(state, board)
    refresh_movement(state, board)
    # Existing conditions survive converting an in-progress fight.
    if len([u for u in units if u['side']=='enemy']) == 1:
        enemy = next(u for u in units if u['side']=='enemy')
        enemy['statuses'] = copy.deepcopy(seq(combat.get('enemy_statuses')))
        enemy['debuffs'] = copy.deepcopy(seq(combat.get('enemy_debuffs')))
    return board


def board_view(state):
    board = ensure_board(state)
    if not board:
        return {}
    actor = next((u for u in live_units(board) if u['id']==board.get('active_id')), None)
    board['reachable'] = ([list(p) for p, path in paths(board, (actor['x'], actor['y']),
                          actor.get('movement_left', 0), actor['id']).items() if path] if actor else [])
    actors = live_units(board)
    player = next((u for u in actors if u.get('player')), None)
    opponents = [u for u in actors if u['side']=='enemy']
    order = [player] if player else []
    if player and opponents and not board.get('bonus_activation') and player['speed']-max(u['speed'] for u in opponents)>=25:
        order.append(player)
    order.extend(sorted([u for u in actors if not u.get('player')], key=lambda u: -u['speed']))
    preview = [{'id': u['id'], 'name': u['name'], 'side': u['side'], 'speed': u['speed'],
                'bonus': i==1 and u.get('player', False)} for i,u in enumerate(order)]
    board['turn_order'] = preview
    combat = obj(state.get('combat'))
    if state.get('world')=='One Piece':from one_piece_tactics import saved_skill_details
    elif state.get('world')=='Bleach':from bleach_tactics import saved_skill_details
    elif state.get('world')=='Naruto':from naruto_tactics import saved_skill_details
    else:from reliability import visible_skills as saved_skill_details
    options = (saved_skill_details(state) if not actor or actor.get('player') else
               copy.deepcopy(obj(actor.get('skills'))))
    board['ability_shapes'] = {'': ability_footprint('', {}, board['width'])}
    for name, detail in options.items():
        board['ability_shapes'][name] = ability_footprint(name, detail, board['width'])
    if state.get('world') in {'Naruto','One Piece','Bleach'} and combat.get('tactical_enabled'):
        if state.get('world')=='One Piece':from one_piece_tactics import compile_skill
        elif state.get('world')=='Bleach':from bleach_tactics import compile_skill
        else:from naruto_tactics import compile_skill
        board['skill_profiles'] = {name:compile_skill(name,detail) for name,detail in options.items()}
        board['ability_shapes'] = {'':ability_footprint('',{},board['width']), **{
            name:ability_footprint(name,detail,board['width']) for name,detail in board['skill_profiles'].items()
            if not detail.get('tactical_disabled')}}
    if state.get('world') not in {'Naruto','One Piece','Bleach'}:
        board['skill_profiles']=copy.deepcopy(options)
    view=copy.deepcopy(board)
    from encounter_objectives import public_view as objective_view
    view['objective'] = objective_view(state, board)
    if not view['objective']:
        try:
            from expeditions import objective_public as expedition_objective
            view['objective'] = expedition_objective(state, board)
        except Exception:
            pass
    if state.get('world') in {'Naruto','One Piece','Bleach'}:
        from portrait_generator import portrait_view
        for unit in view['units']:
            source=state if unit.get('player') else obj(unit.get('character'))
            if source:
                source={**source,'world':state.get('world'),'portrait_identity':state.get('portrait_identity',{}) if unit.get('player') else unit.get('portrait_identity',source.get('portrait_identity',{}))}
                unit['portrait_url']=portrait_view(source,{})['_portrait_image']
                unit['portrait_identity']=copy.deepcopy(source.get('portrait_identity',{}))
    return view


def _actor_effects(state, actor):
    if actor.get('player'):
        combat = obj(state.get('combat'))
        return seq(combat.get('player_statuses')), seq(combat.get('player_debuffs')), seq(combat.get('player_buffs'))
    return seq(actor.get('statuses')), seq(actor.get('debuffs')), seq(actor.get('buffs'))


def _blocked(game, actor):
    return game._active_disabling_status(_actor_effects(game.state, actor)[0])


def _floor(combat, actor):
    return 1 if combat.get('non_lethal') or (actor['side']=='enemy' and (combat.get('spare_enemy') or
                actor.get('death_prevented') or actor.get('immortal') or actor.get('cannot_die'))) else 0


def _sync_player(state, board):
    player = next((u for u in board['units'] if u.get('player')), None)
    if player:
        player['hp'] = state.get('hp', player['hp']); player['resource'] = state.get('resource', player['resource'])


def _sync_aggregate(state, board):
    enemies = [u for u in board['units'] if u['side']=='enemy']
    aggregate = obj(state['combat'].get('enemy'))
    aggregate.update(hp=sum(max(0, u['hp']) for u in enemies), hp_max=sum(u['hp_max'] for u in enemies),
                     alive=any(not u.get('defeated') and u.get('alive', True) for u in enemies))
    state['combat']['enemy'] = aggregate
    state['combat']['opponents'] = [{k:copy.deepcopy(v) for k,v in u.items()
                                   if k not in {'next_at','action_used','movement_left','movement_max'}} for u in enemies]


def _mark_defeated(state, actor):
    combat = state['combat']
    if actor['hp'] > _floor(combat, actor):
        return
    actor['defeated'] = True
    actor['alive'] = _floor(combat, actor) > 0
    if not actor.get('player') and not actor.get('clone'):
        memory = state.setdefault('npc_memories',{}).setdefault(actor['name'],{})
        if isinstance(memory, dict):
            memory.update(alive=actor['alive'], status='deceased' if actor['hp']<=0 else 'subdued')
        for companion in seq(state.get('companions')):
            if isinstance(companion, dict) and companion.get('name')==actor['name']:
                companion.update(alive=actor['alive'], status='deceased' if actor['hp']<=0 else 'subdued')


def _outcome(game, board, log_start):
    combat = game.state['combat']; _sync_player(game.state, board)
    if not combat.get('active'):return None
    for actor in board['units']:
        _mark_defeated(game.state, actor)
    _sync_aggregate(game.state, board)
    player = next(u for u in board['units'] if u.get('player'))
    lost = (not any(u.get('human') for u in live_units(board)) if board.get('owners') else
            not any(u['side']=='ally' and (u.get('player') or u.get('player_controlled')) for u in live_units(board)))
    outcome = 'defeat' if lost else 'victory' if not any(u['side']=='enemy' for u in live_units(board)) else None
    from encounter_objectives import outcome as objective_outcome
    outcome = objective_outcome(game.state, board, outcome)
    if outcome:
        if outcome=='defeat' and combat.get('non_lethal'):
            outcome = 'yielded'
        combat['casualties'] = [{'name':u['name'], 'side':u['side'], 'outcome':'killed' if u['hp']<=0 else 'subdued'}
                                for u in board['units'] if u.get('defeated') and not u.get('clone')]
        result = game.end_combat(outcome, log_start)
        combat['enemy_died'] = any(u['side']=='enemy' and u['hp']<=0 for u in board['units'])
        combat['death_prevented'] = any(u['side']=='enemy' and u.get('defeated') and u['hp']>0
                                      and (u.get('death_prevented') or u.get('immortal') or u.get('cannot_die')) for u in board['units'])
        _sync_aggregate(game.state, board)
        board['revision'] += 1
        record_outcome(game, board, outcome)
        game.autosave()
        return result
    return None


def _result(game, board, log_start):
    _sync_player(game.state, board); _sync_aggregate(game.state, board)
    board['revision'] += 1
    board_view(game.state)
    game.autosave()
    return {'combat': game.state['combat'], 'hp': game.state.get('hp'), 'hp_max': game.state.get('hp_max'),
            'resource': game.state.get('resource'), 'resource_max': game.state.get('resource_max'),
            'log_tail': game.state['combat']['log'][log_start:], 'player_died': game.state.get('hp', 1)<=0,
            'awaiting_bonus_action': bool(board.get('bonus_activation'))}


def _targets(board, actor, spec, target=None, facing='east'):
    area = footprint_cells(board, actor, spec, target, facing)
    is_support = spec.get('effect') in {'heal','buff','shield','cleanse','transform','detect','stealth','summon','utility','movement'}
    if is_support:
        found = [u for u in live_units(board) if u['side']==actor['side'] and (u['x'],u['y']) in area]
    else:
        found = [u for u in live_units(board) if u['id']!=actor['id'] and (u['x'],u['y']) in area
                 and (u['side']!=actor['side'] or spec.get('friendly_fire'))]
    return area, found


def _player_attack(game, board, payload, actor=None):
    actor=actor or next(u for u in board['units'] if u.get('player'))
    if game.state.get('world') in {'Naruto','One Piece','Bleach'} and game.state['combat'].get('tactical_enabled'):
        from naruto_tactical_actions import cast
        detail=None
        if not actor.get('player'):
            name=str(payload.get('ability') or '')
            if name:
                if name not in obj(actor.get('skills')):raise ValueError('That ally has not learned this ability.')
                detail=copy.deepcopy(actor['skills'][name])
        return cast(game,board,payload,actor,detail)
    from worlds import abilities_for, primary_stats_for
    state=game.state; combat=state['combat']; player=next(u for u in board['units'] if u.get('player'))
    name=str(payload.get('ability') or '')
    if name and not game._combat_skill_known(name):
        raise ValueError('That ability is not available to this character.')
    detail=game._combat_skill_detail(name) or {}
    spec=ability_footprint(name, detail, board['width'])
    if player.get('action_used') and not spec['free_action']:
        raise ValueError('Your combat action is spent. You can still move or end this turn.')
    if spec['free_action'] and name in seq(board.get('forms_used')):
        raise ValueError('That transformation was already used in this activation.')
    if _blocked(game,player):
        raise ValueError('You cannot act while incapacitated. End this turn to continue.')
    target=(int(number(payload.get('x'),player['x'])), int(number(payload.get('y'),player['y'])))
    area, targets=_targets(board,player,spec,target,str(payload.get('facing') or 'east'))
    if not area or not targets:
        raise ValueError('No valid target is inside the selected ability footprint. Move, change facing, or choose another attack.')
    primary=primary_stats_for(state.get('world'),obj(state.get('special')).get('Archetype','')) or abilities_for(state.get('world'))
    stat=primary[0]
    offense=number(obj(state.get('stats')).get(stat),30)*(1+game._player_effect_bonuses(combat)['power_pct'])
    original_enemy_status=combat['enemy_statuses']; original_enemy_debuff=combat['enemy_debuffs']
    support_effect=spec['effect'] not in {'damage','control','debuff'}
    if support_effect:
        targets=targets[:1]  # existing self/support mechanics execute exactly once
    for i,target_actor in enumerate(targets):
        proxy=copy.deepcopy(target_actor)
        proxy.setdefault('difficulty_min', max(1,min(90,int(proxy['defense'])-10)))
        proxy.setdefault('difficulty_max', max(1,min(100,int(proxy['defense'])+10)))
        proxy.setdefault('attack_min',25); proxy.setdefault('attack_max',55)
        combat['enemy_statuses']=target_actor['statuses']; combat['enemy_debuffs']=target_actor['debuffs']
        prior=proxy['hp']
        event=game._resolve_swing(combat,proxy,stat,name or None,
              game._ability_resource_type(name) if i==0 and name else 'free',0,offense,proxy['power'],False)
        if not support_effect:
            target_actor['hp']=max(_floor(combat,target_actor),proxy['hp'])
            target_actor['statuses']=combat['enemy_statuses']; target_actor['debuffs']=combat['enemy_debuffs']
            if event.get('action')=='attack': event['damage']=max(0,prior-target_actor['hp'])
            _mark_defeated(state,target_actor)
        event.update(round=combat['round'],unit_id=player['id'],target_id=target_actor['id'],target=target_actor['name'])
        combat['log'].append(event)
    combat['enemy_statuses']=original_enemy_status;combat['enemy_debuffs']=original_enemy_debuff
    if spec['free_action']:
        board.setdefault('forms_used',[]).append(name)
    else:
        player['action_used']=True
    board['last_footprint']=[list(p) for p in area]
    refresh_movement(state,board)


def _best_npc_attack(board, actor, candidates=None):
    """Visible positions and known attacks only; never create a new power."""
    available=[]
    for attack in actor.get('abilities',[]):
        if attack.get('tactical_disabled'): continue
        if board.get('naruto_rules'):
            from naruto_tactics import validate_requirements
            try: validate_requirements(attack,actor,board)
            except ValueError: continue
        if number(attack.get('resource_cost'))>actor.get('resource',0): continue
        if number(actor.get('cooldowns',{}).get(attack.get('id',attack['name'])))>0: continue
        spec=ability_footprint(attack['name'],{**attack,'tactical':attack['tactical']},board['width'])
        for target in (candidates or live_units(board)):
            for facing in ('north','east','south','west'):
                area, targets=_targets(board,actor,spec,(target['x'],target['y']),facing)
                if not targets: continue
                required_source=obj(obj(obj(attack.get('tactical')).get('naruto')).get('requires')).get('targetStatusSource')
                if required_source and not all(any(obj(s).get('source_id')==actor['id'] and obj(s).get('technique_id')==required_source
                                                   for s in seq(u.get('statuses'))) for u in targets):continue
                support=spec['effect'] in {'heal','shield','buff','cleanse'}
                if support and spec['effect']=='heal' and actor['hp']>=actor['hp_max']*.65: continue
                if support and spec['effect']!='heal' and actor.get('shield',0)>0: continue
                authored_damage=number(obj(obj(attack.get('tactical')).get('naruto')).get('damage'),34)
                score=len(targets)*(65+authored_damage)-number(attack.get('resource_cost'))
                if spec['effect']=='control':
                    if all(any(obj(s).get('blocks_action') for s in seq(u.get('statuses'))) for u in targets):continue
                    score=100*len(targets)-number(attack.get('resource_cost'))
                if support: score=180 if spec['effect']=='heal' and actor['hp']<actor['hp_max']*.4 else 5
                available.append((score,attack,area,targets,(target['x'],target['y']),facing))
    return max(available,key=lambda a:a[0]) if available else None


def _npc_effect(game, board, actor, attack, target):
    combat=game.state['combat']; meta=infer_skill_metadata(attack['name'],attack)
    effect=attack.get('effect_type') or meta.get('effect_type','damage')
    potency=number(attack.get('status_potency'),20)/100
    duration=max(1,int(number(attack.get('duration_rounds'),2)))
    status,debuff,buff=_actor_effects(game.state,target)
    _,ad,ab=_actor_effects(game.state,actor)
    _,td,tb=_actor_effects(game.state,target)
    penalty=sum(number(obj(r).get('power_pct')) for r in [*ad,*ab])
    attack_power=actor['power']*max(.1,1+penalty)
    defense=target['defense']*max(.1,1+sum(number(obj(r).get('defense_pct')) for r in [*td,*tb]))
    check=game._combat_check(round((attack_power-defense)/4),30,60)
    event={'actor':'enemy' if actor['side']=='enemy' else 'ally','name':actor['name'],'unit_id':actor['id'],
           'target':target['name'],'target_id':target['id'],'ability':attack['name'],'round':combat['round'],**check}
    if game.state.get('world')=='One Piece' and ('logia' in set(seq(target.get('capabilities'))) or 'logia-fruit' in set(seq(target.get('capabilities')))):
        counters={'armament-haki','seastone','natural-counter'} & set(seq(actor.get('capabilities')))
        if not counters:
            event.update(action='attack',success=False,damage=0,immune=True,
                         reason='Logia body requires Armament Haki, Sea-Prism Stone, or an established natural counter.')
            combat['log'].append(event);return
    if effect in {'heal','shield','buff','cleanse'}:
        check['success']=True;event['success']=True
    event['action']=effect if effect!='damage' else 'attack'
    if check['success']:
        if effect=='control':
            row={'name':attack.get('status_effect') or 'Restrained','rounds_left':duration,'blocks_action':True}
            game._add_or_refresh_effect(status,row);event['status']=row['name'];event['applied']=True
        elif effect=='debuff':
            row={'name':attack.get('status_effect') or 'Weakened','rounds_left':duration,
                 'power_pct':-potency,'defense_pct':-potency,'speed_pct':-potency,'accuracy_pct':-potency}
            game._add_or_refresh_effect(debuff,row);event['status']=row['name'];event['applied']=True
        elif effect=='heal':
            amount=min(target['hp_max']-target['hp'],round(target['hp_max']*potency))
            target['hp']+=amount;event['healed']=amount
        elif effect=='shield':
            amount=round(target['hp_max']*potency)
            if target.get('player'): combat['player_shield']=amount
            else: target['shield']=amount
            event['shield']=amount
        elif effect=='cleanse':
            status.clear();debuff.clear();event['applied']=True
        elif effect=='buff':
            game._add_or_refresh_effect(buff,{'name':attack['name'],'rounds_left':duration,'power_pct':potency,'speed_pct':potency})
            event['applied']=True
        else:
            shrugged=defense-attack_power>=30
            amount=0 if shrugged else game._damage(target['hp_max'],check['margin'],0,check['breakthrough'],attack_power-defense>=30)
            amount=round(amount*number(attack.get('damage_multiplier'),1))
            if target.get('guarding'): amount=round(amount*.5)
            shield=int(number(combat.get('player_shield'))) if target.get('player') else int(number(target.get('shield')))
            absorbed=min(shield,amount);amount-=absorbed
            if target.get('player'): combat['player_shield']=shield-absorbed
            else: target['shield']=shield-absorbed
            prior=target['hp'];target['hp']=max(_floor(combat,target),target['hp']-amount)
            event.update(damage=prior-target['hp'],absorbed=absorbed,shrugged=shrugged)
        if target.get('player'):
            game.state['hp']=target['hp']
        _mark_defeated(game.state,target)
    else:
        event['damage']=0
    combat['log'].append(event)


def _npc_activation(game,board,actor):
    from encounter_objectives import npc_action
    if npc_action(game,board,actor):return
    combat=game.state['combat']
    if _blocked(game,actor):
        combat['log'].append({'round':combat['round'],'actor':'enemy' if actor['side']=='enemy' else 'ally',
                              'name':actor['name'],'action':'controlled','status':_blocked(game,actor)['name']})
        return
    actor['movement_left']=actor['movement_max']
    actor['action_used']=False
    best=_best_npc_attack(board,actor)
    if best is None or best[0]<50:
        possible=paths(board,(actor['x'],actor['y']),actor['movement_left'],actor['id'])
        opponents=[u for u in live_units(board) if u['side']!=actor['side']]
        origin=(actor['x'],actor['y'])
        choices=[]
        for p,path in possible.items():
            actor['x'],actor['y']=p
            attack=_best_npc_attack(board,actor)
            distance=min((abs(p[0]-u['x'])+abs(p[1]-u['y']) for u in opponents),default=0)
            choices.append(((attack[0] if attack else -distance)-len(path)*.1,p,path,attack))
        actor['x'],actor['y']=origin
        if choices:
            _,destination,path,best=max(choices,key=lambda c:c[0])
            actor['x'],actor['y']=destination;actor['movement_left']-=len(path)
            if path:
                combat['log'].append({'round':combat['round'],'actor':'enemy' if actor['side']=='enemy' else 'ally',
                                     'name':actor['name'],'action':'move','distance':len(path),'path':[list(p) for p in path]})
    if best:
        _,attack,area,targets,aim,facing=best
        if (board.get('naruto_rules') or board.get('one_piece_rules') or board.get('bleach_rules')) and (attack.get('catalog_id') or obj(attack.get('tactical')).get('handler')):
            from naruto_tactical_actions import cast
            try:
                cast(game,board,{'ability':attack['name'],'x':aim[0],'y':aim[1],'facing':facing},actor,attack)
            except ValueError as exc:
                combat['log'].append({'actor':actor['side'],'unit_id':actor['id'],'action':'defend','reason':str(exc)})
        else:
            for target in targets:
                _npc_effect(game,board,actor,attack,target)
            actor['resource']=max(0,actor.get('resource',100)-number(attack.get('resource_cost')))
        cooldown=int(number(attack.get('cooldown')))
        if cooldown: actor['cooldowns'][attack.get('id',attack['name'])]=cooldown+1
    else:
        actor['guarding']=True
        combat['log'].append({'round':combat['round'],'actor':'enemy' if actor['side']=='enemy' else 'ally',
                             'name':actor['name'],'action':'defend','result':'waiting for an opening'})


def _status_damage(game, actor):
    for row in _actor_effects(game.state,actor)[0]:
        dot=number(obj(row).get('damage_over_time_pct'))
        if dot<=0: continue
        damage=max(1,round(actor['hp_max']*dot));prior=actor['hp']
        actor['hp']=max(_floor(game.state['combat'],actor),prior-damage)
        if actor.get('player'): game.state['hp']=actor['hp']
        game.state['combat']['log'].append({'actor':'status','target_id':actor['id'],'action':'status damage',
                                            'damage':prior-actor['hp'],'status':row.get('name','Lingering effect')})
        _mark_defeated(game.state,actor)


def _tick_actor(actor):
    for key in ('statuses','buffs','debuffs'):
        rows=[r for r in seq(actor.get(key)) if isinstance(r,dict)]
        for row in rows: row['rounds_left']=int(number(row.get('rounds_left'),1))-1
        actor[key]=[row for row in rows if row['rounds_left']>0]
    actor['cooldowns']={k:max(0,int(number(v))-1) for k,v in actor.get('cooldowns',{}).items()}


def _end_activation(game,board,log_start):
    combat=game.state['combat'];player=next(u for u in board['units'] if u.get('player'))
    foes=[u for u in live_units(board) if u['side']=='enemy']
    refresh_movement(game.state,board)
    if not board.get('owners'):
        actor=next((u for u in live_units(board) if u['id']==board.get('active_id')),player)
        controlled=[u for u in live_units(board) if u['side']=='ally' and (u.get('player') or u.get('player_controlled'))]
        # The established speed rule grants this piece another chosen activation.
        if foes and not actor.get('bonus_taken') and not _blocked(game,actor) and actor['speed']-max(u['speed'] for u in foes)>=25:
            actor['bonus_taken']=True;actor['movement_left']=actor['movement_max'];actor['action_used']=False
            board['bonus_activation']=True;board['activation']+=1;board['forms_used']=[]
            combat['bonus_turn_pending']=True
            combat['bonus_turn_reason']=f"Speed advantage: {actor['speed']:g} vs {max(u['speed'] for u in foes):g}"
            combat['log'].append({'round':combat['round'],'actor':'system','action':'bonus_turn',
                                  'unit_id':actor['id'],'name':actor['name'],'reason':combat['bonus_turn_reason']})
            return None
        _status_damage(game,actor)
        outcome=_outcome(game,board,log_start)
        if outcome:return outcome
        if actor.get('player'):
            for key in ('player_statuses','player_debuffs','player_buffs'):
                combat[key]=[{**r,'rounds_left':int(number(r.get('rounds_left'),1))-1}
                             for r in seq(combat.get(key)) if isinstance(r,dict) and number(r.get('rounds_left'),1)>1]
            combat['tactical_cooldowns']={k:max(0,int(number(v))-1) for k,v in obj(combat.get('tactical_cooldowns')).items()}
        else:_tick_actor(actor)
        form_rows=combat.get('player_buffs',[]) if actor.get('player') else actor.get('buffs',[])
        pool=game.state if actor.get('player') else actor
        for form in list(form_rows):
            if not obj(form).get('form'):continue
            if number(pool.get('resource'))<number(form.get('upkeep')):form_rows.remove(form)
            else:
                pool['resource']=max(0,number(pool.get('resource'))-number(form.get('upkeep')))
                pool['hp']=max(_floor(combat,actor),number(pool.get('hp'))-number(form.get('recoil')))
                actor['resource']=pool['resource'];actor['hp']=pool['hp']
        from portrait_generator import clear_active_portrait_form,set_active_portrait_form
        portrait_owner=game.state if actor.get('player') else actor
        forms=[r['name'] for r in form_rows if obj(r).get('form')]
        if forms:set_active_portrait_form(portrait_owner,' + '.join(forms),source='tactical')
        elif obj(obj(portrait_owner.get('portrait_identity')).get('active_form')).get('source')=='tactical':clear_active_portrait_form(portrait_owner)
        actor.update(guarding=False,bonus_taken=False)
        # Every surviving allied piece receives its own player-controlled turn.
        try:index=controlled.index(actor)
        except ValueError:index=-1
        pending=controlled[index+1:] if index>=0 else controlled
        if pending:
            next_actor=pending[0];board['active_id']=next_actor['id'];board['bonus_activation']=False;board['forms_used']=[]
            next_actor.update(movement_left=next_actor['movement_max'],action_used=False,guarding=False)
            combat.pop('bonus_turn_pending',None);combat.pop('bonus_turn_reason',None)
            return None
        # Enemy AI acts only after every player-controlled ally has finished.
        for enemy in sorted([u for u in live_units(board) if u['side']=='enemy' or (u['side']=='ally' and not u.get('player') and not u.get('player_controlled'))],key=lambda u:-u['speed']):
            _status_damage(game,enemy)
            outcome=_outcome(game,board,log_start)
            if outcome:return outcome
            if enemy.get('defeated'):continue
            opponents=[u for u in live_units(board) if u['side']!=enemy['side']]
            if not opponents:break
            enemy['guarding']=False
            count=2 if enemy['speed']-max(u['speed'] for u in opponents)>=25 and not _blocked(game,enemy) else 1
            for _ in range(count):
                _npc_activation(game,board,enemy)
                outcome=_outcome(game,board,log_start)
                if outcome:return outcome
            _tick_actor(enemy)
        combat.pop('bonus_turn_pending',None);combat.pop('bonus_turn_reason',None);combat.pop('bonus_turn_first_action',None)
        combat['round']+=1;board['activation']+=1;board['bonus_activation']=False;board['forms_used']=[]
        try:
            from expeditions import tactical_tick
            tactical_tick(game.state, board)
        except Exception:
            pass
        controlled=[u for u in live_units(board) if u['side']=='ally' and (u.get('player') or u.get('player_controlled'))]
        if controlled:
            board['active_id']=controlled[0]['id']
            for unit in controlled:unit.update(movement_left=unit['movement_max'],action_used=False,guarding=False,bonus_taken=False)
        refresh_movement(game.state,board)
        return None
    # Preserve the shipped +25 speed-gap rule: exactly one fresh chosen bonus
    # activation, not a continuous initiative scheduler or an automatic repeat.
    if foes and not board.get('bonus_activation') and not _blocked(game,player) and player['speed']-max(u['speed'] for u in foes)>=25:
        board['bonus_activation']=True;board['activation']+=1;board['forms_used']=[]
        player['movement_left']=player['movement_max'];player['action_used']=False
        combat['bonus_turn_pending']=True;combat['bonus_turn_reason']=f"Speed advantage: {player['speed']:g} vs {max(u['speed'] for u in foes):g}"
        combat['log'].append({'round':combat['round'],'actor':'system','action':'bonus_turn','reason':combat['bonus_turn_reason']})
        return None
    _status_damage(game,player)
    outcome=_outcome(game,board,log_start)
    if outcome: return outcome
    # Consume the player's completed activation BEFORE NPCs inflict fresh control.
    # Otherwise a one-turn paralysis applied by an NPC expires before the player acts.
    for key in ('player_statuses','player_debuffs'):
        combat[key]=[{**r,'rounds_left':int(number(r.get('rounds_left'),1))-1}
                     for r in seq(combat.get(key)) if isinstance(r,dict) and number(r.get('rounds_left'),1)>1]
    for actor in sorted([u for u in live_units(board) if not u.get('player') and not u.get('human')],key=lambda u:-u['speed']):
        _status_damage(game,actor)
        outcome=_outcome(game,board,log_start)
        if outcome: return outcome
        if actor.get('defeated'): continue
        opponents=[u for u in live_units(board) if u['side']!=actor['side']]
        if not opponents: break
        actor['guarding']=False
        count=2 if actor['speed']-max(u['speed'] for u in opponents)>=25 and not _blocked(game,actor) else 1
        for _ in range(count):
            _npc_activation(game,board,actor)
            outcome=_outcome(game,board,log_start)
            if outcome: return outcome
        _tick_actor(actor)
    # NPC conditions were ticked above; do not tick the single-enemy aliases twice.
    for key in ('player_buffs',):
        combat[key]=[{**r,'rounds_left':int(number(r.get('rounds_left'),1))-1}
                     for r in seq(combat.get(key)) if isinstance(r,dict) and number(r.get('rounds_left'),1)>1]
    combat['tactical_cooldowns']={k:max(0,int(number(v))-1) for k,v in obj(combat.get('tactical_cooldowns')).items()}
    for form in list(combat['player_buffs']):
        if not form.get('form'): continue
        if game.state['resource']<number(form.get('upkeep')):
            combat['player_buffs'].remove(form)
        else:
            game.state['resource']-=number(form.get('upkeep'))
            game.state['hp']=max(_floor(combat,player),game.state['hp']-number(form.get('recoil')))
    if obj(obj(game.state.get('portrait_identity')).get('active_form')).get('source')=='tactical':
        from portrait_generator import clear_active_portrait_form, set_active_portrait_form
        forms=[r['name'] for r in combat['player_buffs'] if r.get('form')]
        if forms: set_active_portrait_form(game.state,' + '.join(forms),source='tactical')
        else: clear_active_portrait_form(game.state)
    combat.pop('bonus_turn_pending',None);combat.pop('bonus_turn_reason',None);combat.pop('bonus_turn_first_action',None)
    combat['round']+=1;board['activation']+=1;board['bonus_activation']=False;board['forms_used']=[]
    try:
        from expeditions import tactical_tick
        tactical_tick(game.state, board)
    except Exception:
        pass
    refresh_movement(game.state,board)
    player['movement_left']=player['movement_max'];player['action_used']=False;player['guarding']=False
    return None


def resolve_tactical_action(game,payload):
    game.ensure_combat_numbers()
    state=game.state;combat=state['combat'];board=ensure_board(state)
    if not combat.get('active'): raise ValueError('This battle has already ended.')
    if payload.get('revision') is not None and number(payload['revision'],-1)!=board['revision']:
        raise ValueError('The battlefield changed. Refresh it before submitting that move.')
    player=next(u for u in board['units'] if u.get('player'))
    actor=next((u for u in live_units(board) if u['id']==board.get('active_id')),player)
    if actor['side']!='ally' or not (actor.get('player') or actor.get('player_controlled')):
        raise ValueError('Wait for a player-controlled allied turn.')
    log_start=len(combat['log']);action=str(payload.get('action') or 'attack')
    if action=='move':
        if _blocked(game,actor): raise ValueError('This ally cannot move while incapacitated. End this turn to continue.')
        destination=(int(number(payload.get('x'),-1)),int(number(payload.get('y'),-1)))
        route=paths(board,(actor['x'],actor['y']),actor['movement_left'],actor['id']).get(destination)
        if not route: raise ValueError('That square is occupied, blocked, or beyond your remaining movement.')
        from naruto_tactical_actions import _release_channel
        _release_channel(board,actor)
        actor['x'],actor['y']=destination;actor['movement_left']-=len(route)
        board['last_path']=[list(p) for p in route];board['last_footprint']=[]
        combat['log'].append({'round':combat['round'],'actor':'player','action':'move','unit_id':actor['id'],'name':actor['name'],
                             'distance':len(route),'movement_left':actor['movement_left'],'path':board['last_path']})
    elif action in {'attack','transform'}:
        _player_attack(game,board,payload,actor)
    elif action=='revert':
        if _blocked(game,actor): raise ValueError('This ally cannot voluntarily change form while incapacitated.')
        from portrait_generator import clear_active_portrait_form
        if actor.get('player'):
            combat['player_buffs']=[r for r in seq(combat.get('player_buffs')) if not obj(r).get('form')]
            clear_active_portrait_form(state)
        else:
            actor['buffs']=[r for r in seq(actor.get('buffs')) if not obj(r).get('form')]
            clear_active_portrait_form(actor)
        refresh_movement(state,board);combat['log'].append({'actor':'player','unit_id':actor['id'],'name':actor['name'],'action':'revert','round':combat['round']})
    elif action=='objective':
        from encounter_objectives import interact
        interact(game,board,actor)
    elif action=='defend':
        if actor['action_used']: raise ValueError('This ally’s action is already spent.')
        if _blocked(game,actor): raise ValueError('This ally cannot act while incapacitated. End this turn to continue.')
        actor['guarding']=True;actor['action_used']=True
        combat['log'].append({'round':combat['round'],'actor':'player','unit_id':actor['id'],'name':actor['name'],'action':'defend','result':'braced'})
    elif action=='flee':
        if not actor.get('player'):raise ValueError('Only the player character can order a retreat for the whole team.')
        if actor['action_used'] or _blocked(game,actor): raise ValueError('The active ally cannot flee without an available action.')
        check=game._combat_check(round((actor['speed']-30)/4),35,65);actor['action_used']=True
        combat['log'].append({'round':combat['round'],'actor':'player','unit_id':actor['id'],'name':actor['name'],'action':'flee',**check,'result':'escaped' if check['success'] else 'failed to escape'})
        if check['success']:
            result=game.end_combat('fled',log_start)
            board['revision']+=1
            record_outcome(game,board,'fled');game.autosave()
            return result
    elif action=='end':
        outcome=_end_activation(game,board,log_start)
        if outcome: return outcome
    else:
        raise ValueError('Unknown tactical action.')
    outcome=_outcome(game,board,log_start)
    return outcome or _result(game,board,log_start)


def record_outcome(game, board, outcome):
    """One durable receipt per encounter; no invented loot/XP in a Naruto fight."""
    combat=game.state['combat']
    import uuid
    receipt_id=combat.setdefault('tactical_receipt_id', str(uuid.uuid4()))
    receipts=game.state.setdefault('tactical_battle_results',[])
    if any(r.get('id')==receipt_id for r in receipts if isinstance(r,dict)): return
    receipts.append({'id':receipt_id,'outcome':outcome,'turn':game.state.get('turn'),
                     'casualties':copy.deepcopy(combat.get('casualties',[])),
                     'combatants':[{'name':u['name'],'hp':u['hp'],'alive':u.get('alive',True),
                                   'side':u['side']} for u in board['units'] if not u.get('clone')],
                     'rewards_status':('recorded_in_adventure_aftermath' if combat.get('adventure_objective',{}).get('mission_id') and outcome=='objective_complete' else 'none_awarded_locally')})
    del receipts[:-30]
    combat['result_receipt']=copy.deepcopy(receipts[-1])
    from narrative_state import record_npc_death
    actual_people = {u['name'] for u in board['units'] if not u.get('clone') and not u.get('summon')}
    for casualty in receipts[-1]['casualties']:
        if casualty.get('outcome') == 'killed' and casualty.get('name') in actual_people:
            record_npc_death(game.state, casualty['name'], f"Confirmed killed in battle {receipt_id}.")
    if game.state.get('world')=='One Piece':
        evidence=game.state.setdefault('one_piece_combat_evidence',[])
        evidence.append({'id':receipt_id,'turn':game.state.get('turn'),'outcome':outcome,
                         'defeated':[r['name'] for r in receipts[-1]['casualties'] if r.get('side')=='enemy'],
                         'public':bool(combat.get('witnesses') or combat.get('public_battle')),
                         'bounty_change':'pending narrative assessment','newspaper':'pending only if information spreads'})
        del evidence[:-50]
    elif game.state.get('world')=='Bleach':
        evidence=game.state.setdefault('bleach_combat_evidence',[])
        evidence.append({'id':receipt_id,'turn':game.state.get('turn'),'outcome':outcome,
                         'defeated':[r['name'] for r in receipts[-1]['casualties'] if r.get('side')=='enemy'],
                         'witnessed_by':copy.deepcopy(seq(combat.get('witnesses'))),
                         'division_report':'pending narrative assessment'})
        del evidence[:-50]
    lines=[f"{r['name']}: {r['outcome']}" for r in receipts[-1]['casualties']]
    game.append('[BATTLE RESULT]\n'+outcome.title()+('. '+ '; '.join(lines) if lines else ''), 'narrative')


def submit_tactical_action(game, payload):
    """Persist retry IDs with the board so reconnect/restart cannot replay a cast."""
    import json
    if (game.state.get('world') not in {'Naruto','One Piece','Bleach'} and not obj(game.state.get('combat')).get('adventure_objective')) or not obj(game.state.get('combat')).get('tactical_enabled'):
        raise ValueError('Tactical combat is not enabled for this encounter.')
    request_id=str(payload.get('request_id') or '')[:100]
    if not request_id or 'revision' not in payload:
        raise ValueError('A request ID and battlefield revision are required.')
    before=copy.deepcopy(game.state)
    story_length=len(game.story_log)
    board=ensure_board(game.state)
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    ledger=board.get('requests',{})
    if request_id in ledger:
        if ledger[request_id]!=digest: raise ValueError('Request ID already used for another command.')
        return {'combat':copy.deepcopy(game.state['combat']),'replayed_request':True}
    try:
        result=resolve_tactical_action(game,payload)
        board.setdefault('requests',{})[request_id]=digest
        if len(board['requests'])>128: board['requests'].pop(next(iter(board['requests'])))
        game.autosave()
        result['combat']=copy.deepcopy(game.state['combat'])
        return result
    except Exception:
        game.state=before
        del game.story_log[story_length:]
        raise

submit_naruto_action=submit_tactical_action
