"""Bleach tactical adapter: persistent Kidō and one synchronized Zanpakutō."""
import copy,re
from bleach_data import CANON_HADO,CANON_BAKUDO
from naruto_tactics import key
from tactical_effects import compile_tactical_effect,named_applications

SHIELD_KIDO={'Seki','Enkosen','Danku','Tozansho'}
PASSIVE_KIDO={'Kakushitsuijaku','Tenteikura'}

def _special(state):return state.get('special') if isinstance(state.get('special'),dict) else {}
def _profile(state):
    row=_special(state).get('Zanpakuto Profile')
    return row if isinstance(row,dict) else {}

def _kido_geometry(branch,number,name):
    if branch=='Bakudo':
        if name in PASSIVE_KIDO:return None
        if name in SHIELD_KIDO:return {'shape':'self','origin':'self','effect':'shield'}
        radius=2 if number>=70 else 1
        return {'shape':'burst' if number>=60 else 'single','origin':'target','range':5,'radius':radius,'effect':'control'}
    if number>=88:return {'shape':'burst','origin':'target','range':6,'radius':2,'effect':'damage'}
    if number>=50:return {'shape':'line','origin':'self','length':6,'effect':'damage'}
    if number>=30:return {'shape':'burst','origin':'target','range':5,'radius':1,'effect':'damage'}
    return {'shape':'single','origin':'target','range':4,'effect':'damage'}

def compile_skill(name,detail):
    detail=copy.deepcopy(detail if isinstance(detail,dict) else {'description':str(detail or '')})
    if detail.get('locked') or detail.get('hidden') or detail.get('unlocked') is False or detail.get('passive'):
        return {**detail,'tactical_disabled':'This ability is passive, hidden or not unlocked.'}
    if isinstance(detail.get('tactical'),dict):return detail
    text=key(name+' '+str(detail.get('description',''))+' '+str(detail.get('effect','')))
    release=str(detail.get('release_stage') or detail.get('rank') or '')
    release_activation=(str(detail.get('category','')).lower()!='zanpakuto application' and
                        (detail.get('effect_type')=='transform' or text.startswith('shikai ') or text.startswith('bankai ')))
    if release_activation:
        stage='Bankai' if release=='Bankai' or text.startswith('bankai ') else 'Shikai'
        boosts=copy.deepcopy(detail.get('combat_boosts') or {})
        return {**detail,'effect_type':'transform','category':'zanpakuto release','release_stage':stage,
                'combat_boosts':boosts,'release_unlocks':copy.deepcopy(detail.get('release_unlocks') or []),
                'resource_cost':detail.get('resource_cost',20 if stage=='Bankai' else 10),
                'tactical':{'shape':'self','origin':'self','effect':'transform','handler':'form'},
                'visual_effect':{'asset':'chakra-guard','family':'release-transformation','delivery':'self'},
                'mechanics_source':'saved Zanpakuto release profile; no universal stat bonus'}
    data=detail.get('kido') if isinstance(detail.get('kido'),dict) else {}
    match=re.search(r'(had[ōo]|bakud[ōo])\s*#\s*(\d{1,2})(?:\s*:\s*(.+))?',name,re.I)
    if match:
        branch='Hado' if match.group(1).lower().startswith('ha') else 'Bakudo';number=int(match.group(2))
        catalog=CANON_HADO if branch=='Hado' else CANON_BAKUDO
        spell=(catalog.get(number) or (match.group(3) or 'Campaign Formula',''))[0]
    elif data.get('branch') and data.get('number'):
        branch='Hado' if str(data['branch']).lower().startswith('h') else 'Bakudo';number=int(data['number']);spell=name
    else:branch=number=spell=None
    if branch:
        tactical=_kido_geometry(branch,number,spell)
        if not tactical:return {**detail,'tactical_disabled':'This Kidō is informational rather than a direct battlefield action.'}
        effect=tactical['effect'];asset=('lightning-lance' if branch=='Hado' and number<30 else 'fireball' if branch=='Hado' else 'shadow-bind')
        if effect=='shield':asset='chakra-guard'
        return {**detail,'effect_type':effect,'category':'kido','resource_cost':max(4,round(number/4)),
                'duration_rounds':max(1,round(number/30)) if effect=='control' else detail.get('duration_rounds',1),
                'status_effect':'Restrained' if effect=='control' else detail.get('status_effect'),
                'tactical':tactical,'visual_effect':{
                    'asset':asset,
                    'family':'spirit-barrier' if effect=='shield' else 'binding-bands' if effect=='control' else 'horizon-ray',
                    'delivery':'area' if tactical['shape']=='burst' else 'target'}}
    if re.search(r'\bshunpo\b|flash step',text):
        return {**detail,'effect_type':'buff','combat_boosts':{'speed_pct':.25},'duration_rounds':2,'resource_cost':8,
                'tactical':{'shape':'self','origin':'self','effect':'buff','handler':'shunpo'},'visual_effect':{'asset':'wind-blade','family':'flash-step','delivery':'self'}}
    return compile_tactical_effect('Bleach',name,detail,default_cost=10)

def saved_skill_details(state):
    result={}
    for source in (state.get('skills'),(state.get('combat') or {}).get('ability_options')):
        if isinstance(source,dict):result.update({k:v for k,v in source.items() if k not in result})
    profile=_profile(state);special=_special(state)
    if profile.get('shikai_name') and str(special.get('Shikai','')).lower() not in {'','none','unknown','unachieved'}:
        name='Shikai — '+str(profile['shikai_name'])
        apps=named_applications(profile['shikai_name'],profile.get('shikai_applications') or profile.get('applications'),
                                category='zanpakuto application',release_stage='Shikai',requires_form=name)
        if not apps and profile.get('shikai_effect'):
            apps=named_applications(profile['shikai_name'],[{'name':profile['shikai_name']+' — Core Release','description':profile['shikai_effect']}],
                                    category='zanpakuto application',release_stage='Shikai',requires_form=name)
        result.setdefault(name,{'description':profile.get('shikai_effect','Established first release.'),'release_stage':'Shikai',
            'combat_usable':True,'combat_boosts':copy.deepcopy(profile.get('shikai_combat_boosts') or {}),'release_unlocks':list(apps)})
        for app_name,app in apps.items():result.setdefault(app_name,app)
    if profile.get('bankai_name') and str(special.get('Bankai','')).lower() not in {'','none','unknown','unachieved'}:
        apps=named_applications(profile['bankai_name'],profile.get('bankai_applications'),category='zanpakuto application',
                                release_stage='Bankai',requires_form=str(profile['bankai_name']))
        if not apps and profile.get('bankai_effect'):
            apps=named_applications(profile['bankai_name'],[{'name':profile['bankai_name']+' — Core Release','description':profile['bankai_effect']}],
                                    category='zanpakuto application',release_stage='Bankai',requires_form=str(profile['bankai_name']))
        result.setdefault(str(profile['bankai_name']),{'description':profile.get('bankai_effect','Established final release.'),'release_stage':'Bankai',
            'combat_usable':True,'combat_boosts':copy.deepcopy(profile.get('bankai_combat_boosts') or {}),'release_unlocks':list(apps)})
        for app_name,app in apps.items():result.setdefault(app_name,app)
    return result

def capabilities(state):
    result=set();special=_special(state);profile=_profile(state)
    if profile:result.add('zanpakuto')
    if str(special.get('Shikai','')).lower() not in {'','none','unknown','unachieved'}:result.add('shikai')
    if str(special.get('Bankai','')).lower() not in {'','none','unknown','unachieved'}:result.add('bankai')
    for name in saved_skill_details(state):
        if re.search(r'\bshunpo\b|flash step',name,re.I):result.add('shunpo')
    return sorted(result)

def blocks_narrative(state):
    combat=state.get('combat') or {}
    return state.get('world')=='Bleach' and combat.get('active') and combat.get('tactical_enabled')
