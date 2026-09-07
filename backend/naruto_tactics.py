"""Opt-in Naruto tactical authoring. Catalog lookup never grants an ability.

Numbers are grid adaptations. Campaign-authored mechanics take precedence.
Unsupported skills remain visible with an explanation, never a fake attack.
"""
import copy
import json
import re
import unicodedata
import math
from pathlib import Path


def key(value):
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()).strip()


MOVES = json.loads(Path(__file__).with_name('naruto_tactical_moves.json').read_text(encoding='utf-8'))['moves']
BY_NAME = {key(alias): row for row in MOVES for alias in [row['name'], *row['aliases']]}
PATTERNS = {
    'contact': {'shape':'single', 'range':1},
    'projectile': {'shape':'single', 'range':5},
    'burst': {'shape':'burst', 'range':5, 'radius':1},
    'beam': {'shape':'line', 'origin':'self', 'length':5},
    'cone': {'shape':'cone', 'origin':'self', 'length':3},
    'broadCone': {'shape':'cone', 'origin':'self', 'length':4},
    'wave': {'shape':'line', 'origin':'self', 'length':3, 'width':3},
    'pulse': {'shape':'burst', 'origin':'self', 'radius':2, 'exclude_origin':True},
    'sweep3': {'shape':'arc', 'origin':'self', 'width':3},
    'sweep': {'shape':'arc', 'origin':'self', 'width':3},
}


def compile_skill(name, detail):
    detail = copy.deepcopy(detail if isinstance(detail, dict) else {'description':str(detail or '')})
    if detail.get('locked') or detail.get('hidden') or detail.get('unlocked') is False or detail.get('passive'):
        return {**detail, 'tactical_disabled':'This ability is passive, hidden or not unlocked.'}
    authored = detail.get('tactical')
    row = BY_NAME.get(key(name))
    if isinstance(authored, dict) and authored.get('source')!='description':
        # Mechanics with an explicit supported handler are never replaced by a name lookup.
        if authored.get('shape','single') not in {'single','self','line','cone','arc','burst','ring','cross'}:
            return {**detail,'tactical_disabled':'Unsupported tactical shape; no substitute attack was invented.'}
        for field in ('range','length','width','radius'):
            value=authored.get(field)
            if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or
                                      not math.isfinite(value) or value<0 or int(value)!=value):
                return {**detail,'tactical_disabled':'Invalid tactical '+field+'.'}
        if authored.get('effect'):detail['effect_type']=authored['effect']
        return detail
    if row:
        c = copy.deepcopy(row['combat'])
        geometry = {'origin':'target', **PATTERNS.get(c.get('pattern'), {})}
        geometry.update({k:c[k] for k in ('shape','range','radius','length','width') if k in c})
        if geometry.get('shape')=='self':geometry['origin']='self'
        geometry['target'] = c.get('target', 'enemy')
        effect = ('heal' if c.get('heal') else 'shield' if c.get('shield') else
                  'cleanse' if c.get('cleanse') else 'control' if c.get('status') and not c.get('damage') else 'damage')
        geometry.update(effect=effect, naruto=c)
        return {**detail, 'tactical':geometry, 'effect_type':effect,
                'resource_cost':detail.get('resource_cost', c.get('cost',0)),
                'catalog_id':row['id'], 'visual_effect':c.get('effect',{}),
                'mechanics_source':'curated Naruto tactical adaptation'}
    text = key(name+' '+str(detail.get('description','')))
    if re.search(r'\b(shadow clone|kage bunshin)\b', text):
        return {**detail, 'tactical':{'shape':'single','origin':'target','range':2,'effect':'summon','handler':'shadow_clone'},
                'visual_effect':{'asset':'clone-barrage','delivery':'target','scale':1},
                'effect_type':'summon', 'resource_cost':detail.get('resource_cost',20)}
    if re.search(r'\b(flying thunder god|hiraishin)\b', text):
        return {**detail, 'tactical':{'shape':'single','range':32,'effect':'movement','handler':'marked_teleport'},
                'effect_type':'movement','resource_cost':detail.get('resource_cost',20)}
    if detail.get('effect_type') == 'transform':
        if not detail.get('stat_boosts') and not detail.get('combat_boosts'):
            return {**detail,'tactical_disabled':'This saved form has no recorded stat boosts. Its mechanics need confirmation before activation.'}
        return {**detail,'tactical':{'shape':'self','origin':'self','effect':'transform','handler':'form'}}
    if detail.get('effect_type') == 'summon':
        return {**detail,'tactical':{'shape':'single','origin':'target','range':2,'effect':'summon','handler':'contract_summon'},
                'visual_effect':{'asset':'clone-barrage','delivery':'target','scale':1}}
    if not re.search(r'\b(seal|dimension|intangib|teleport|illusion|summon|clone)\w*\b',text) and re.search(r'\b(sweep|sweeping|beam|projectile|bolt|punch|kick|slash|shockwave|cone)\b',text):
        from tactical_combat import ability_footprint
        geometry=ability_footprint(name,detail)
        element=next((e for e in ('fire','water','lightning','wind','earth','ice','sand','wood') if e in text.split()),'energy')
        assets={'fire':'fireball','water':'water-wave','lightning':'lightning-bolt','wind':'wind-blade','earth':'earth-spikes','physical':'taijutsu-hit'}
        delivery='area' if geometry['shape'] in {'arc','cone','burst','ring','cross'} else 'line' if geometry['shape']=='line' else 'target'
        return {**detail,'tactical':geometry,'visual_effect':{'asset':assets.get(element),'delivery':delivery} if element in assets else {},
                'mechanics_source':'description-derived supported geometry'}
    # Original abilities need supported shape/mechanics; keep their identity untouched.
    return {**detail, 'tactical_disabled':'This technique needs an explicit tactical profile before it can be used on the board.'}


def skill_options(game):
    return {name:compile_skill(name,detail) for name,detail in saved_skill_details(game.state).items()}


def saved_skill_details(state):
    """Adapt saved records without granting powers or rewriting player-owned data."""
    sources = {}
    for source in (state.get('skills'), state.get('combat',{}).get('ability_options')):
        if isinstance(source,dict):
            for name, detail in source.items():
                sources.setdefault(name,detail)
    special=state.get('special') if isinstance(state.get('special'),dict) else {}
    for label in ('Dōjutsu','Dojutsu','Dōjutsu Profile','Dojutsu Profile','Jinchūriki Profile'):
        profile=special.get(label)
        if not isinstance(profile,dict) or profile.get('pending') or profile.get('unlocked') is False:continue
        forms=profile.get('forms',[])
        if isinstance(forms,dict):forms=[{'name':name,**row} for name,row in forms.items() if isinstance(row,dict)]
        for row in forms if isinstance(forms,list) else []:
            if isinstance(row,dict) and row.get('name') and row.get('unlocked') is True:
                sources.setdefault(row['name'],{**copy.deepcopy(row),'effect_type':'transform'})
        if label.startswith(('Dōjutsu','Dojutsu')) and profile.get('name'):
            sources.setdefault(profile['name'],{**copy.deepcopy(profile),'effect_type':'transform'})
    return sources


def validate_requirements(detail, actor, board):
    if detail.get('tactical_disabled'):
        raise ValueError(detail['tactical_disabled'])
    spec = detail.get('tactical',{})
    req = spec.get('naruto',{}).get('requires',{})
    # Facts come from the saved encounter/campaign, never a click payload.
    available = set(actor.get('capabilities',[]))
    missing = set(req.get('capabilities',[])) - available
    conditions = set(board.get('conditions',[]))
    missing.update(set(req.get('environment',[])) - conditions)
    clone_count = sum(u.get('summoner_id')==actor['id'] and u.get('clone') and not u.get('defeated') for u in board['units'])
    if clone_count < req.get('alliedClones',0):
        missing.add('required living shadow clones')
    if missing:
        raise ValueError('Requirements not established: '+', '.join(sorted(missing)))


def blocks_narrative(state):
    combat = state.get('combat') or {}
    return state.get('world')=='Naruto' and combat.get('active') and bool(combat.get('tactical_enabled'))


def saved_capabilities(state):
    """Read explicit learned facts; a latent affinity or desired background goal is not mastery."""
    result=set(state.get('tactical_capabilities',[]) if isinstance(state.get('tactical_capabilities'),list) else [])
    special=state.get('special') if isinstance(state.get('special'),dict) else {}
    affinity=special.get('Chakra Affinity Profile',{})
    if isinstance(affinity,dict):
        for field in ('proficiencies','mastered_natures'):
            for nature in affinity.get(field,[]) if isinstance(affinity.get(field),list) else []:
                for element in ('fire','water','wind','earth','lightning'):
                    if element in key(nature).split(): result.add(element+'-nature')
    for name,detail in (state.get('skills') or {}).items():
        if not isinstance(detail,dict) or detail.get('locked') or detail.get('hidden') or detail.get('unlocked') is False:continue
        result.update(detail.get('capabilities',[]) if isinstance(detail.get('capabilities'),list) else [])
        if key(name)=='rasengan':result.add('rasengan')
    return sorted(result)


def require_narrative_available(state):
    blocked=blocks_narrative(state)
    if state.get('world')=='One Piece':
        from one_piece_tactics import blocks_narrative as one_piece_blocked
        blocked=one_piece_blocked(state)
    elif state.get('world')=='Bleach':
        from bleach_tactics import blocks_narrative as bleach_blocked
        blocked=bleach_blocked(state)
    if blocked:
        raise ValueError('Finish the tactical battle before typing actions or advancing time.')
