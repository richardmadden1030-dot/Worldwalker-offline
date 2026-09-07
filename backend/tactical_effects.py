"""World-neutral tactical effect contracts.

This module maps already-authored abilities onto the board.  It never grants
ownership and never invents an unrelated attack when the saved rule is vague.
"""
from __future__ import annotations
import copy,math,re
from naruto_tactics import key

EFFECTS={'damage','heal','shield','control','debuff','buff','cleanse','transform','summon','movement','field'}
SHAPES={'single','self','line','cone','arc','burst','ring','cross'}
AREA_SHAPES={'line','cone','arc','burst','ring','cross'}
ELEMENT_ASSETS={
    'fire':'fireball','flame':'fireball','water':'water-wave','ice':'water-wave',
    'lightning':'lightning-bolt','electric':'lightning-bolt','wind':'wind-blade',
    'earth':'earth-spikes','stone':'earth-spikes','sand':'sand-wave','poison':'insect-swarm',
    'shadow':'shadow-bind','darkness':'shadow-bind','light':'lightning-lance',
    'energy':'lightning-lance','spirit':'lightning-lance','reishi':'lightning-lance',
}
ELEMENT_FAMILIES={
    'fire':'living-flame','flame':'living-flame','water':'tidal-surge','ice':'frost-bloom',
    'lightning':'storm-vein','electric':'storm-vein','wind':'wind-shear','earth':'stone-crystal',
    'stone':'stone-crystal','sand':'stone-crystal','poison':'poison-mist','shadow':'shadow-ink',
    'darkness':'shadow-ink','light':'horizon-ray','energy':'spirit-bolt','spirit':'spirit-bolt',
    'reishi':'spirit-bolt','blood':'soul-siphon','metal':'blade-trail',
}


def _disabled(detail,message):
    return {**detail,'tactical_disabled':message,'mechanics_source':'strict shared tactical-effect compiler'}


def _validate_authored(detail):
    tactical=copy.deepcopy(detail.get('tactical'))
    if not isinstance(tactical,dict):return None
    shape=tactical.get('shape','single');effect=tactical.get('effect') or detail.get('effect_type','damage')
    if shape not in SHAPES:return _disabled(detail,'Unsupported tactical shape; no replacement effect was invented.')
    if effect not in EFFECTS:return _disabled(detail,'Unsupported tactical effect; no replacement effect was invented.')
    for field in ('range','length','width','radius'):
        value=tactical.get(field)
        if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or int(value)!=value):
            return _disabled(detail,'Invalid tactical '+field+'.')
    return {**detail,'effect_type':effect,'tactical':tactical,'mechanics_source':detail.get('mechanics_source','authored tactical profile')}


def _effect(text,detail):
    explicit=str(detail.get('effect_type') or '').lower()
    if explicit in EFFECTS:return explicit
    tests=(
        ('heal',r'\b(heal(?:s|ed|ing)?|restore[sd]?|restoration|regenerate[sd]?|mend(?:s|ed|ing)?|repairs?|recovery)\b'),
        ('cleanse',r'\b(cleanse|purif(?:y|ies)|remove poison|dispel|cure status)\b'),
        ('shield',r'\b(shield|barrier|wall|ward|protect(?:ion|ive)?|block attacks?|repel)\b'),
        ('control',r'\b(bind(?:s|ing)?|restrain(?:s|ed|ing)?|controls?|immobili[sz](?:e|es|ed|ing)|paraly[sz](?:e|es|ed|ing)|trap(?:s|ped|ping)?|imprison(?:s|ed|ing)?|seal movement|pin(?:s|ned|ning)?|illusion|misdirect(?:s|ed|ing)?|confuse[sd]?|hypnoti[sz](?:e|es|ed|ing))\b'),
        ('debuff',r'\b(weaken|drain|slow|blind|poison|corrode|reduce|suppress|exhaust)\b'),
        ('movement',r'\b(teleport|swap positions?|dash|blink|transport|relocate|pulls? the user|propel)\b'),
        ('summon',r'\b(summon|create an? (?:ally|creature|construct)|manifest an? (?:ally|creature|construct))\b'),
        ('buff',r'\b(enhance|empower|increase|strengthen|hasten|accelerate|reinforce)\b'),
        ('field',r'\b(field|domain|zone|terrain|battlefield-wide|across the battlefield)\b'),
        ('damage',r'\b(attacks?|strikes?|slashes?|cuts?|pierces?|burns?|blasts?|bolts?|beams?|explosions?|crush(?:es)?|damages?|shatters?|projectiles?|shots?|bullets?|waves?)\b'),
    )
    matches=[effect for effect,pattern in tests if re.search(pattern,text)]
    return matches[0] if matches else None


def _shape(text,effect,detail):
    target=str(detail.get('target_type') or '').lower()
    if effect in {'transform','buff','cleanse'} and target not in {'ally','allies','enemy','enemies','area'}:return 'self'
    if effect=='shield' and not re.search(r'\b(area|allies|wall|field|zone)\b',text):return 'self'
    if re.search(r'\b(ring|surrounding ring)\b',text):return 'ring'
    if re.search(r'\b(cross|four directions)\b',text):return 'cross'
    if re.search(r'\b(cone|breath|fan|spray)\b',text):return 'cone'
    if re.search(r'\b(sweep|arc|crescent|three adjacent)\b',text):return 'arc'
    if re.search(r'\b(line|beam|lance|ray|column|straight path)\b',text):return 'line'
    if re.search(r'\b(area|burst|explosion|field|domain|zone|radius|multiple targets|around the target)\b',text):return 'burst'
    return 'single'


def _geometry(shape,effect,detail):
    tactical={'shape':shape,'effect':effect,'origin':'self' if shape in {'self','line','cone','arc','ring','cross'} else 'target'}
    reach=max(1,min(12,int(detail.get('range_tiles') or 5)))
    size=max(1,min(5,int(detail.get('radius_tiles') or detail.get('area_size') or 1)))
    if shape=='single':
        close=bool(re.search(r'\b(punch|kick|slash|sword|blade|strike|touch|contact|hakuda|zanjutsu)\b',key(str(detail))))
        tactical['range']=1 if close else reach
    elif shape in {'line','cone'}:tactical['length']=max(1,min(12,int(detail.get('length_tiles') or reach)))
    elif shape=='arc':tactical['width']=max(1,min(7,int(detail.get('width_tiles') or 3)))
    elif shape in {'burst','ring'}:tactical.update(range=reach,radius=size)
    elif shape=='cross':tactical['length']=max(1,min(6,int(detail.get('length_tiles') or 3)))
    return tactical


def _visual(text,shape,effect):
    family=None
    if effect=='heal':asset='healing';family='restoration-pulse'
    elif effect=='shield':asset='chakra-guard';family='spirit-barrier'
    elif effect=='control':asset='shadow-bind';family='binding-bands'
    elif effect=='movement':asset='wind-blade';family='flash-step'
    elif effect=='summon':asset='clone-barrage';family='spirit-construct'
    elif effect=='debuff':asset='genjutsu';family='illusion-glass'
    elif effect=='cleanse':asset='healing';family='restoration-pulse'
    elif effect=='buff':asset='chakra-guard';family='reiatsu-pressure'
    else:
        tokens=set(key(text).split());asset=next((value for token,value in ELEMENT_ASSETS.items() if token in tokens),None)
        family=next((value for token,value in ELEMENT_FAMILIES.items() if token in tokens),None)
        if not asset:return {}
    delivery='self' if shape=='self' else 'area' if shape in AREA_SHAPES else 'target'
    return {'asset':asset,'family':family,'delivery':delivery}


def compile_tactical_effect(world,name,detail,default_cost=10):
    """Compile explicit or unambiguous saved mechanics into one board action."""
    detail=copy.deepcopy(detail if isinstance(detail,dict) else {'description':str(detail or '')})
    if detail.get('locked') or detail.get('hidden') or detail.get('unlocked') is False or detail.get('passive'):
        return _disabled(detail,'This ability is passive, hidden or not unlocked.')
    authored=_validate_authored(detail)
    if authored is not None:return authored
    text=key(' '.join(str(v) for v in (name,detail.get('description',''),detail.get('effect',''),detail.get('governing_rule','')) if v))
    effect=_effect(text,detail)
    if effect=='field':
        # A field must state what it does. Merely saying "field" is presentation,
        # not enough information to resolve outcomes.
        secondary=_effect(re.sub(r'\b(field|domain|zone|terrain|battlefield wide|across the battlefield)\b','',text),{})
        if not secondary:return _disabled(detail,'This field needs a recorded battlefield effect before it can be used.')
        effect=secondary
    if not effect:return _disabled(detail,f'This {world} ability needs an explicit tactical effect; no generic attack was substituted.')
    if effect in {'transform','summon','movement'}:
        return _disabled(detail,f'This {effect} requires an explicit supported handler.')
    shape=_shape(text,effect,detail);tactical=_geometry(shape,effect,detail)
    result={**detail,'effect_type':effect,'tactical':tactical,
            'resource_cost':detail.get('resource_cost',default_cost),
            'mechanics_source':'strict shared tactical-effect compiler'}
    visual=_visual(text,shape,effect)
    if visual:result['visual_effect']=visual
    return result


def named_applications(parent,applications,**defaults):
    """Normalize saved named applications without creating new capabilities."""
    result={}
    if isinstance(applications,dict):
        applications=[{'name':name,**(row if isinstance(row,dict) else {'description':row})} for name,row in applications.items()]
    if not isinstance(applications,list):return result
    for index,row in enumerate(applications,1):
        if isinstance(row,dict):
            detail={**copy.deepcopy(defaults),**copy.deepcopy(row)};name=str(detail.pop('name', '') or '').strip()
        else:
            raw=str(row);parts=re.split(r'\s+[—–-]\s+|:\s+',raw,maxsplit=1)
            name=parts[0].strip() if len(parts)>1 else ''
            detail={**copy.deepcopy(defaults),'description':parts[-1].strip()}
        if not name:name=f'{parent} · Application {index}'
        result[name]=detail
    return result
