"""Conservative identity linking for known NPC record copies.

Only exact names, explicitly recorded aliases and shared IDs are evidence.
Ambiguous aliases or conflicting IDs are never resolved by fuzzy matching.
This links records when a settled consequence needs them, not on save load.
"""
import hashlib


def normalized(value):
    return str(value or '').strip().casefold()


def records(state):
    result = []
    for field in ('npc_memories', 'contacts'):
        collection = state.get(field)
        if isinstance(collection, dict):
            result.extend((str(name), row, False) for name, row in collection.items() if isinstance(row, dict))
    if isinstance(state.get('companions'), list):
        result.extend((str(row.get('name', '')), row, False) for row in state['companions'] if isinstance(row, dict))
    if isinstance(state.get('organizations'), dict):
        for group in state['organizations'].values():
            if isinstance(group, dict) and isinstance(group.get('members'), dict):
                result.extend((str(name), row, True) for name, row in group['members'].items() if isinstance(row, dict))
    return result


def identifiers(row):
    # Namespace identifiers so unrelated arbitrary IDs do not collide.
    result = set()
    for field, space in (('person_id', 'person'), ('npc_id', 'npc'), ('canon_character_id', 'canon'), ('canon_id', 'canon')):
        if row.get(field):
            result.add((space, normalized(row[field])))
    return result


def resolve_records(state, target):
    wanted = normalized(target)
    if not wanted:
        return []
    rows = records(state)
    def names(item):
        name, row, _ = item
        aliases = row.get('aliases', [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return {normalized(name), normalized(row.get('name'))} | ({normalized(v) for v in aliases if isinstance(v, str)} if isinstance(aliases, list) else set())
    candidates = [i for i, item in enumerate(rows) if wanted in names(item) or wanted in {v for _, v in identifiers(item[1])}]
    if not candidates:
        return []
    parent = list(range(len(rows)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def join(i, j):
        parent[root(j)] = root(i)
    # Explicitly shared IDs are the strongest cross-surface link.
    for i in range(len(rows)):
        for j in range(i):
            if identifiers(rows[i][1]) & identifiers(rows[j][1]):
                join(i, j)
    # Same-name legacy copies may link only when they do not join conflicting
    # already identified people. Alias overlap alone does not merge identities.
    by_name = {}
    for i, (name, row, _) in enumerate(rows):
        by_name.setdefault(normalized(name), []).append(i)
    for name, indices in by_name.items():
        if not name:
            continue
        identified_roots = {root(i) for i in indices if identifiers(rows[i][1])}
        if len(identified_roots) <= 1:
            for i in indices[1:]:
                join(indices[0], i)
    candidate_roots = {root(i) for i in candidates}
    if len(candidate_roots) != 1:
        return []
    selected = [item for i, item in enumerate(rows) if root(i) in candidate_roots]
    # IDs are assigned only after an unambiguous resolution succeeds.
    existing = {str(row['person_id']) for _, row, _ in selected if row.get('person_id')}
    if len(existing) > 1:
        return []
    seed = '|'.join((normalized(state.get('world')), min(normalized(name) for name, _, _ in selected)))
    person_id = next(iter(existing)) if existing else 'npc-' + hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]
    for _, row, _ in selected:
        row.setdefault('person_id', person_id)
    return selected
