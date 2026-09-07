"""Persistent property, local market, passive proceeds, and workshop orders."""
from __future__ import annotations
import copy,hashlib,math,re
from worlds import expansion_for
from systems import currency_balance,record_currency_transaction

def _obj(v):return v if isinstance(v,dict) else {}
def _seq(v):return v if isinstance(v,list) else []
def _text(v):return str(v or '').strip()
def _num(v,d=0):
    try:
        n=float(v);return n if math.isfinite(n) else d
    except (TypeError,ValueError):return d
def _id(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()[:18]
def _minute(s):return int(s.get('canon_time_minutes',int(s.get('canon_day',0) or 0)*1440+480))
def _baseline(s):return max(1,_num(expansion_for(s.get('world','Custom World')).get('currency_baseline'),250))
def _currency(s):return _text(_obj(s.get('currency')).get('name')) or 'Currency'
def _store(s):
    r=s.setdefault('property_economy',{})
    if not isinstance(r,dict):r=s['property_economy']={}
    r.setdefault('version',1);r.setdefault('properties',[]);r.setdefault('work_orders',[]);r.setdefault('history',[]);r.setdefault('last_tick_minute',_minute(s));return r
PROPERTY_TYPES={'home':1.2,'workshop':2.0,'shop':2.5,'warehouse':1.7}
FACILITIES={'training_hall':1.0,'infirmary':1.0,'storage':.7,'defenses':1.2,'workshop':1.1,'shopfront':.9,'quarters':.8,'intelligence_office':1.2}
def property_name(kind,place):return f"{place} {kind.replace('_',' ').title()}"
def acquisition_cost(s,kind):return round(_baseline(s)*PROPERTY_TYPES.get(kind,2),2)
def facility_cost(s,facility,level=1):return round(_baseline(s)*FACILITIES.get(facility,1)*(1+max(0,int(level)-1)*.55),2)
def bootstrap_established_holdings(state):
    root=_store(state)
    existing={p.get('id') for p in root['properties'] if isinstance(p,dict)}
    regions=state.get('political_regions') or []
    for row in regions if isinstance(regions,list) else []:
        if not isinstance(row,dict) or not row.get('player_led'):continue
        place=_text(row.get('anchor') or row.get('name'));pid='established-'+_id(state.get('campaign_id'),place)
        if pid in existing:continue
        root['properties'].append({'id':pid,'name':property_name('holding',place),'type':'holding','location':place,'level':1,'condition':100,'facilities':{},'treasury':0.0,'income_remainder':0.0,'established':True,'organization':''});existing.add(pid)
    return root

def _market_factors(s,place):
    danger=0;supply=1.0
    try:
        from world_conflict import location_status
        conflict=location_status(s,place);danger=min(.45,.08*len(conflict.get('operations',[]))+.12*len(conflict.get('contested_by',[])))
    except Exception:pass
    benefits=s.get('world_benefits') if isinstance(s.get('world_benefits'),dict) else {}
    if any(isinstance(v,dict) and v.get('active') and v.get('kind')=='safer_route' and place in {v.get('origin'),v.get('destination')} for v in benefits.values()):supply-=.08
    try:
        from reputation_system import price_multiplier
        rep=price_multiplier(s,place)
    except Exception:rep=1
    return {'danger':round(danger,3),'supply':round(max(.7,min(1.4,supply)),3),'price_multiplier':round(max(.65,min(1.8,(1+danger)*supply*rep)),3)}
def market_view(s,place):
    f=_market_factors(s,place);m=f['price_multiplier'];return {'location':place,**f,'condition':'strained' if m>=1.15 else 'favorable' if m<=.9 else 'stable'}
def adjusted_price(s,base_price,place):return round(max(0,_num(base_price))*market_view(s,place)['price_multiplier'],2)
def market_shops_view(s):
    shops=copy.deepcopy(_seq(s.get('shops')));here=_text(s.get('location'))
    for shop in shops:
        if not isinstance(shop,dict):continue
        place=_text(shop.get('location') or here)
        for item in _seq(shop.get('inventory')) or _seq(shop.get('items')):
            if not isinstance(item,dict):continue
            for key in ('price','cost','value'):
                if isinstance(item.get(key),(int,float)):
                    item[key]=adjusted_price(s,item[key],place);item['market_adjusted']=True;break
    return shops
def purchase_price(s,shop,item,base):
    place=next((_text(r.get('location')) for r in _seq(s.get('shops')) if isinstance(r,dict) and _text(r.get('name')).casefold()==_text(shop).casefold()),_text(s.get('location')))
    return adjusted_price(s,base,place)
def properties_at(s,place):return [p for p in _seq(_obj(s.get('property_economy')).get('properties')) if isinstance(p,dict) and _text(p.get('location')).casefold()==_text(place).casefold()]
def known_recipes(s):
    vals=[];special=_obj(s.get('special'));profile=_obj(special.get('Satisfy Profile'))
    for src in (s.get('known_recipes'),profile.get('known_recipes')):
        for r in _seq(src):
            name=_text(r.get('name') if isinstance(r,dict) else r)
            if name and name not in vals:vals.append(name)
    return vals[:30]
def actions(s,place):
    if _obj(s.get('currency')).get('tracked') is False:return []
    root=_obj(s.get('property_economy'));out=[];currency=_currency(s);owned=properties_at(s,place)
    existing_types={p.get('type') for p in owned}
    for kind in PROPERTY_TYPES:
        if kind not in existing_types:
            cost=adjusted_price(s,acquisition_cost(s,kind),place);out.append({'id':f'property:buy:{kind}','label':f'Acquire {kind.replace("_"," ")} in {place}','minutes':60,'cost':cost,'currency':currency,'description':'Purchase a permanent local property. The price is rechecked when the transaction completes.'})
    for p in owned:
        if _num(p.get('treasury'))>0:out.append({'id':f"property:collect:{p['id']}",'label':f"Collect accounts from {p['name']}",'minutes':30,'description':f"Collect up to {_num(p.get('treasury')):.2f} {currency} accrued locally."})
        facilities=_obj(p.get('facilities'))
        for facility in ('training_hall','infirmary','storage','defenses','workshop','shopfront'):
            lvl=int(facilities.get(facility,0) or 0)
            if lvl<3:
                cost=facility_cost(s,facility,lvl+1);out.append({'id':f"property:upgrade:{p['id']}:{facility}",'label':f"Upgrade {facility.replace('_',' ')} at {p['name']} (Lv {lvl+1})",'minutes':480,'cost':cost,'currency':currency,'description':'A permanent facility upgrade; completion can be interrupted by major events.'})
        if int(facilities.get('workshop',0) or 0)>0 or p.get('type')=='workshop':
            active={o.get('recipe') for o in _seq(root.get('work_orders')) if isinstance(o,dict) and o.get('property_id')==p.get('id') and o.get('status') in {'active','complete'}}
            for recipe in known_recipes(s):
                if recipe not in active:
                    cost=round(_baseline(s)*.15,2);out.append({'id':f"craft:start:{p['id']}:{_id(recipe)}",'label':f'Start production: {recipe}','minutes':60,'cost':cost,'currency':currency,'recipe':recipe,'property_id':p['id'],'description':'Start a workshop order. Production continues for 6 hours of campaign time.'})
    for o in _seq(root.get('work_orders')):
        if isinstance(o,dict) and o.get('status')=='complete' and not o.get('claimed'):
            prop=next((p for p in owned if p.get('id')==o.get('property_id')),None)
            if prop:out.append({'id':f"craft:claim:{o['id']}",'label':f"Claim finished {o.get('recipe')}",'minutes':15,'description':'Move the completed reusable product into your inventory.'})
    return out[:80]
def refresh_spec(s,spec):
    ident=spec.get('id');place=spec.get('place') or s.get('location');row=next((a for a in actions(s,place) if a.get('id')==ident),None)
    if not row:raise ValueError('That property or production action is no longer available. Cancel the unfinished activity.')
    return {**row,'place':place}
def _spend(s,cost,reason,kind):
    if currency_balance(copy.deepcopy(s),_currency(s))<_num(cost):raise ValueError('There is not enough currency to complete this action.')
    record_currency_transaction(s,-_num(cost),reason,kind,source='property_economy')
def resolve(s,spec):
    root=_store(s);ident=_text(spec.get('id'));place=_text(spec.get('place') or s.get('location'));msg=''
    if ident.startswith('property:buy:'):
        kind=ident.split(':',2)[2];cost=_num(spec.get('cost'));_spend(s,cost,f'Acquired {kind} in {place}','property_purchase')
        if any(p.get('type')==kind and p.get('location')==place for p in root['properties']):raise ValueError('You already own that type of property here.')
        pid='property-'+_id(s.get('campaign_id'),place,kind,len(root['properties']));p={'id':pid,'name':property_name(kind,place),'type':kind,'location':place,'level':1,'condition':100,'facilities':{},'treasury':0.0,'income_remainder':0.0,'organization':''};root['properties'].append(p);msg=f"Acquired {p['name']} for {cost:g} {_currency(s)}."
    elif ident.startswith('property:collect:'):
        pid=ident.split(':',2)[2];p=next((x for x in root['properties'] if x.get('id')==pid and x.get('location')==place),None)
        if not p:raise ValueError('That property is not available here.')
        amount=_num(p.get('treasury'));p['treasury']=0.0;record_currency_transaction(s,amount,f"Collected proceeds from {p['name']}",'property_income',source='property_economy');msg=f"Collected {amount:g} {_currency(s)} from {p['name']}."
    elif ident.startswith('property:upgrade:'):
        _,_,pid,facility=ident.split(':',3);p=next((x for x in root['properties'] if x.get('id')==pid and x.get('location')==place),None)
        if not p:raise ValueError('That facility upgrade is no longer available here.')
        lvl=int(_obj(p.get('facilities')).get(facility,0) or 0)+1;cost=facility_cost(s,facility,lvl);_spend(s,cost,f'Upgraded {facility} at {p["name"]}','property_upgrade');p.setdefault('facilities',{})[facility]=min(3,lvl);msg=f"{facility.replace('_',' ').title()} at {p['name']} reached level {min(3,lvl)}."
    elif ident.startswith('craft:start:'):
        pid=spec.get('property_id');recipe=spec.get('recipe');p=next((x for x in root['properties'] if x.get('id')==pid and x.get('location')==place),None)
        if not p or recipe not in known_recipes(s):raise ValueError('That workshop order is no longer valid.')
        _spend(s,_num(spec.get('cost')),f'Production inputs for {recipe}','crafting_input');oid='work-'+_id(s.get('campaign_id'),pid,recipe,_minute(s));root['work_orders'].append({'id':oid,'property_id':pid,'recipe':recipe,'status':'active','started_minute':_minute(s),'due_minute':_minute(s)+360,'claimed':False});msg=f"Production of {recipe} begins at {p['name']}; expected completion in 6 hours."
    elif ident.startswith('craft:claim:'):
        oid=ident.split(':',2)[2];o=next((x for x in root['work_orders'] if x.get('id')==oid),None)
        if not o or o.get('status')!='complete' or o.get('claimed'):raise ValueError('That work order is not ready to claim.')
        p=next((x for x in root['properties'] if x.get('id')==o.get('property_id') and x.get('location')==place),None)
        if not p:raise ValueError('Return to the workshop to claim this order.')
        mastery=_num(_obj(_obj(s.get('special')).get('Satisfy Profile')).get('crafting_mastery'),_num(_obj(s.get('special')).get('Crafting Mastery')));rating='Rare' if mastery>=30 else 'Uncommon' if mastery>=15 else 'Standard'
        s.setdefault('inventory',[]).append({'name':o['recipe'],'category':'Crafted product','rating':rating,'creator':s.get('name'),'source':p['name'],'effects':['A reusable product made from an established known recipe.']});o['claimed']=True;msg=f"Claimed {o['recipe']} ({rating}) from {p['name']}."
    else:raise ValueError('Unknown property/economy action.')
    root['history'].append({'turn':s.get('turn'),'canon_day':s.get('canon_day'),'action':ident,'message':msg});root['history']=root['history'][-120:];return {'message':msg,'property_economy':public_view(s)}
def advance(s,elapsed_minutes):
    root=_store(s);now=_minute(s);last=int(root.get('last_tick_minute',now) or now);minutes=max(0,now-last if elapsed_minutes is None else int(elapsed_minutes or 0));hours=minutes/60
    if hours:
        for p in root['properties']:
            if not isinstance(p,dict) or p.get('type')=='home':continue
            fac=_obj(p.get('facilities'));base=_baseline(s)*.08/24;mult=1+int(fac.get('shopfront',0) or 0)*.05+int(fac.get('workshop',0) or 0)*.03
            try:danger=_market_factors(s,p.get('location'))['danger']
            except Exception:danger=0
            income=max(0,base*hours*mult*(1-danger*.55));p['treasury']=round(_num(p.get('treasury'))+income,2)
    for o in root['work_orders']:
        if isinstance(o,dict) and o.get('status')=='active' and now>=int(o.get('due_minute',10**18)):o['status']='complete'
    root['last_tick_minute']=now
    return public_view(s)
def facility_level(s,place,facility):return max([int(_obj(p.get('facilities')).get(facility,0) or 0) for p in properties_at(s,place)] or [0])
def training_bonus(s,place):return facility_level(s,place,'training_hall')*.08
def recovery_multiplier(s,place):return 1+facility_level(s,place,'infirmary')*.12
def organization_base(s,group_id):return next((p for p in _seq(_obj(s.get('property_economy')).get('properties')) if isinstance(p,dict) and p.get('organization')==group_id),None)
def attach_organization_base(s,property_id,group_id):
    p=next((x for x in _store(s)['properties'] if x.get('id')==property_id),None)
    if not p:raise ValueError('That property does not exist.')
    p['organization']=group_id;return p
def public_view(s):
    """Pure read view. Established holdings are materialized on simulation ticks."""
    root=copy.deepcopy(_obj(s.get('property_economy')));root.setdefault('properties',[]);root.setdefault('work_orders',[]);root.setdefault('history',[])
    props=copy.deepcopy(_seq(root.get('properties')))
    for p in props:p['facilities_readable']=[f"{k.replace('_',' ').title()} Lv {v}" for k,v in _obj(p.get('facilities')).items() if int(v or 0)>0]
    return {'properties':props,'work_orders':copy.deepcopy(_seq(root.get('work_orders'))),'market':market_view(s,s.get('location')),'known_recipes':known_recipes(s),'history':copy.deepcopy(_seq(root.get('history'))[-20:])}
