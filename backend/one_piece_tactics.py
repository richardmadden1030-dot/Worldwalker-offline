"""One Piece tactical adapter: saved powers in, no invented ownership out."""
import copy,re
from naruto_tactics import key
from tactical_effects import compile_tactical_effect
from one_piece_power_catalog import CANON_TECHNIQUES,TACTICAL_PRESETS,DEVIL_FRUITS,HAKI_APPLICATIONS,TRANSFORMATIONS,fruit_by_name

ELEMENT_ASSET={'fire':'fireball','flame':'fireball','ice':'water-wave','water':'water-wave','lightning':'lightning-bolt','electric':'lightning-bolt','wind':'wind-blade','sand':'sand-wave','poison':'insect-swarm','string':'shadow-bind','gravity':'earth-spikes','light':'lightning-lance'}
CATALOG={}
def _moves(names,shape,reach,effect='damage',asset='taijutsu-hit',cost=10,**extra):
    for name in names.split('|'):
        CATALOG[key(name)]={'tactical':{'shape':shape,'origin':'self' if shape in {'line','cone','arc','self'} else 'target','effect':effect,**({'range':reach} if shape in {'single','burst'} else {'length':reach}),**extra},'effect_type':effect,'resource_cost':cost,'visual_effect':{'asset':asset,'delivery':'area' if shape in {'burst','cone','arc'} else 'line' if shape=='line' else 'self' if shape=='self' else 'target'}}
_moves('Gum-Gum Pistol|Gum-Gum Red Hawk|Shigan|Fish-Man Karate Punch|Thunder Bagua','single',4,asset='taijutsu-hit')
_moves('Gum-Gum Gatling|Three Sword Style: Onigiri|Demon Aura Nine-Sword Style: Asura|Tempest Kick','arc',1,asset='slash',width=3)
_moves('Gum-Gum Bazooka|Divine Departure|King Kong Gun|Galaxy Impact|Shock Wille','line',4,asset='taijutsu-hit')
_moves('Gum-Gum Elephant Gatling|Gum-Gum Bajrang Gun|Ursus Shock|Conqueror Haki Burst','burst',3,asset='lightning-storm',radius=2,cost=20)
_moves('Fire Fist|Flame Emperor|Prometheus Heavenly Fire','cone',4,asset='fire-breath',cost=16)
_moves('Ice Age|Ice Block: Pheasant Beak','line',5,asset='water-wave',cost=16)
_moves('Yasakani Sacred Jewel|Laser Beam|Radical Beam','line',6,asset='lightning-lance',cost=16)
_moves('Room: Shambles','single',6,'movement','lightning-storm',14,handler='room_shambles')
_moves('Parasite String|Black Knight|Birdcage String Bind','single',5,'control','shadow-bind',15)
_moves('Venom Demon|Poison Hydra','cone',4,'debuff','insect-swarm',16)
_moves('Barrier Crash|Bartolomeo Barrier','self',0,'shield','chakra-guard',12)
_moves('Soru|Geppo','self',0,'buff','wind-blade',8)

def _profile(state):
    special=state.get('special') if isinstance(state.get('special'),dict) else {}
    return special.get('Devil Fruit Profile') if isinstance(special.get('Devil Fruit Profile'),dict) else {}

def _haki(state):
    special=state.get('special') if isinstance(state.get('special'),dict) else {}
    profile=special.get('Haki Profile')
    if isinstance(profile,dict):return profile
    # Saves made before Haki Profile used one broad Haki object. Preserve them.
    legacy=special.get('Haki')
    if not isinstance(legacy,dict):return {}
    result={}
    for branch,value in legacy.items():
        if isinstance(value,dict):result[branch]=value
        elif value not in (None,False,0,'','Locked','Unawakened'):
            result[branch]={'mastery':value,'applications':[]}
    return result

def _visual(text,shape):
    low=key(text);asset=next((v for k,v in ELEMENT_ASSET.items() if k in low.split()),None)
    if not asset:return {}
    return {'asset':asset,'delivery':'area' if shape in {'burst','cone','arc','ring','cross'} else 'line' if shape=='line' else 'target'}

def compile_skill(name,detail):
    detail=copy.deepcopy(detail if isinstance(detail,dict) else {'description':str(detail or '')})
    if detail.get('locked') or detail.get('hidden') or detail.get('unlocked') is False or detail.get('passive'):
        return {**detail,'tactical_disabled':'This ability is passive, hidden or not unlocked.'}
    authored=detail.get('tactical')
    if isinstance(authored,dict):return detail
    text=key(name+' '+str(detail.get('description',''))+' '+str(detail.get('effect','')))
    category=key(detail.get('category',''))
    canonical=CATALOG.get(key(name))
    if canonical:return {**detail,**copy.deepcopy(canonical),'mechanics_source':'curated One Piece tactical adaptation'}
    if detail.get('effect_type')=='transform' or category in {'zoan form','transformation'}:
        if not detail.get('combat_boosts') and not detail.get('stat_boosts'):
            return {**detail,'tactical_disabled':'This saved form needs recorded combat boosts before it can be activated.'}
        return {**detail,'effect_type':'transform','tactical':{'shape':'self','origin':'self','effect':'transform','handler':'form'},
                'visual_effect':detail.get('visual_effect',{'family':'release-transformation','delivery':'self'})}
    canon=next((row for title,row in CANON_TECHNIQUES.items() if key(title)==key(name)),None)
    if canon:
        canon_name=next(title for title in CANON_TECHNIQUES if key(title)==key(name))
        detail.setdefault('category',canon.get('category'))
        detail.setdefault('canon_source',canon.get('source'))
        detail.setdefault('description',f"Canon application of {canon.get('source')}.")
        preset=copy.deepcopy(TACTICAL_PRESETS[canon_name])
        if preset.get('effect_type')=='transform':
            known=next((v for title,v in TRANSFORMATIONS.items() if key(title)==key(name)),None)
            boosts=detail.get('combat_boosts') or detail.get('stat_boosts') or (known or {}).get('boosts')
            if not boosts:return {**detail,'tactical_disabled':'This canon form needs its recorded transformation profile before activation.'}
            preset['combat_boosts']=copy.deepcopy(boosts)
        return {**detail,**preset,'canon_owner':canon.get('owner'),'mechanics_source':'preset canon One Piece catalog'}
    if 'observation' in text and 'haki' in text:
        return {**detail,'effect_type':'buff','combat_boosts':{'speed_pct':.15},'duration_rounds':2,'resource_cost':8,
                'tactical':{'shape':'self','origin':'self','effect':'buff','handler':'observation'},'visual_effect':{'asset':'genjutsu','delivery':'self'}}
    if 'armament' in text and 'haki' in text:
        return {**detail,'effect_type':'buff','combat_boosts':{'power_pct':.18,'defense_pct':.18},'duration_rounds':2,'resource_cost':10,
                'tactical':{'shape':'self','origin':'self','effect':'buff','handler':'armament'},'visual_effect':{'asset':'chakra-guard','delivery':'self'}}
    if 'conqueror' in text and 'haki' in text:
        return {**detail,'effect_type':'control','duration_rounds':1,'resource_cost':18,
                'tactical':{'shape':'burst','origin':'self','radius':3,'effect':'control','handler':'conqueror'},'visual_effect':{'asset':'lightning-storm','delivery':'area'}}
    if detail.get('effect_type')=='transform' or category in {'zoan form','transformation'}:
        if not detail.get('combat_boosts') and not detail.get('stat_boosts'):
            return {**detail,'tactical_disabled':'This saved form needs recorded combat boosts before it can be activated.'}
        return {**detail,'effect_type':'transform','tactical':{'shape':'self','origin':'self','effect':'transform','handler':'form'}}
    return compile_tactical_effect('One Piece',name,detail,default_cost=10)

def saved_skill_details(state):
    sources={}
    for source in (state.get('skills'),(state.get('combat') or {}).get('ability_options')):
        if isinstance(source,dict):sources.update({k:v for k,v in source.items() if k not in sources})
    fruit=_profile(state)
    if fruit and fruit.get('name'):
        canon_fruit=fruit_by_name(fruit.get('name'))
        if canon_fruit:
            fruit.setdefault('canon_owner',canon_fruit['canon_owner']);fruit.setdefault('governing_rule',canon_fruit['governing_rule'])
            fruit.setdefault('canon_reference',canon_fruit['name'])
        for i,row in enumerate(fruit.get('abilities',[]) if isinstance(fruit.get('abilities'),list) else []):
            text=str(row);name=(text.split('—',1)[0].strip() if '—' in text else f"{fruit['name']} · Application {i+1}")
            sources.setdefault(name,{'description':text,'category':'devil fruit','fruit_name':fruit['name'],'fruit_type':fruit.get('type'),'resource_cost':12+i*4})
        if 'Zoan' in str(fruit.get('type')):
            boosts={'power_pct':.20,'defense_pct':.20,'speed_pct':.10}
            for form,scale in [('Hybrid Form',1),('Full Beast Form',1.2)]:
                sources.setdefault(form,{'description':form+' of '+fruit['name'],'category':'zoan form','effect_type':'transform','combat_boosts':{k:round(v*scale,3) for k,v in boosts.items()},'resource_cost':10})
        if str(fruit.get('awakening_status','')).lower() in {'awakened','mastered'}:
            sources.setdefault(fruit['name']+' Awakening',{'description':'Established awakened application','category':'transformation','effect_type':'transform','combat_boosts':{'power_pct':.3,'defense_pct':.2,'speed_pct':.15},'resource_cost':20})
    for branch,row in _haki(state).items():
        if not isinstance(row,dict) or not (row.get('mastery',0) or row.get('applications')):continue
        title=str(branch)
        if 'haki' not in title.lower():title+=' Haki'
        sources.setdefault(title,{'description':f"Established {title} proficiency.",'category':'haki','mastery':row.get('mastery',0),'resource_cost':10})
        profile=next((p for p in HAKI_APPLICATIONS.values() if key(p['branch'])==key(branch)),None)
        known={key(v) for v in row.get('applications',[]) if isinstance(v,str)}
        if profile:
            for application,mechanics in profile['applications'].items():
                if key(application) in known:
                    sources.setdefault(application,{'description':f"Established {profile['branch']} Haki application.",'category':'haki',
                                      'haki_branch':profile['branch'],'mastery':row.get('mastery',0),**mechanics})
    return sources

def skill_options(state):return {n:compile_skill(n,d) for n,d in saved_skill_details(state).items()}

def capabilities(state):
    result=set();fruit=_profile(state);haki=_haki(state)
    if fruit:
        result.add('devil-fruit');result.add(key(fruit.get('type','devil fruit')).replace(' ','-'))
    for branch,row in haki.items():
        if isinstance(row,dict) and (row.get('mastery',0) or row.get('applications')):result.add(key(branch)+'-haki')
    for name,detail in saved_skill_details(state).items():
        text=key(name+' '+str((detail or {}).get('description','') if isinstance(detail,dict) else detail))
        for branch in ('armament','observation','conqueror'):
            if branch in text and 'haki' in text:result.add(branch+'-haki')
    return sorted(result)

def blocked_by_sea(actor):
    return any(str(s.get('kind','')).lower() in {'seastone','submerged','deep_water'} for s in actor.get('statuses',[]) if isinstance(s,dict))

def blocks_narrative(state):
    c=state.get('combat') or {};return state.get('world')=='One Piece' and c.get('active') and c.get('tactical_enabled')
