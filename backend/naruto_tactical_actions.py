"""Naruto casts execute once on the server; presentation never resolves damage."""
import copy,re
from naruto_tactics import compile_skill as naruto_compile, validate_requirements, saved_skill_details as naruto_details
from tactical_combat import (obj, seq, number, cells, blocked_cells, live_units,
    ability_footprint, footprint_cells, _actor_effects, _blocked, _floor,
    _mark_defeated, refresh_movement, movement_budget, combat_profile)


def _release_channel(board, actor):
    for unit in board['units']:
        unit['statuses']=[s for s in seq(unit.get('statuses')) if not
                          (isinstance(s,dict) and s.get('channel_owner')==actor['id'])]


def cast(game, board, payload, actor=None, detail_override=None):
    state=game.state; combat=state['combat']; actor=actor or next(u for u in board['units'] if u.get('player'))
    pools=state if actor.get('player') else actor
    name=str(payload.get('ability') or '')
    if state.get('world')=='One Piece':
        from one_piece_tactics import compile_skill,saved_skill_details,blocked_by_sea
    elif state.get('world')=='Bleach':
        from bleach_tactics import compile_skill,saved_skill_details
    else:compile_skill,saved_skill_details=naruto_compile,naruto_details
    known=saved_skill_details(state) if actor.get('player') else {}
    if name and actor.get('player') and name not in known: raise ValueError('This character has not learned that ability.')
    detail=detail_override or (compile_skill(name,known.get(name)) if name else {
        'resource_cost':0,'tactical':{'shape':'single','range':1,'effect':'damage'}})
    if state.get('world')=='One Piece' and blocked_by_sea(actor):
        category=str(detail.get('category','')).lower()
        if detail.get('fruit_name') or category in {'devil fruit','haki','zoan form','transformation'}:
            raise ValueError('Seawater or Sea-Prism Stone is suppressing Devil Fruit and Haki use.')
    validate_requirements(detail,actor,board)
    raw=obj(detail.get('tactical')); mechanics=obj(raw.get('naruto')); handler=raw.get('handler')
    spec=ability_footprint(name,detail,board['width']); spec['effect']=raw.get('effect',spec['effect'])
    effect=spec['effect']; free=effect=='transform' and detail.get('voluntary',True) is not False
    disabling=_blocked(game,actor)
    if disabling and not (disabling.get('kind')=='genjutsu' and 'genjutsu' in mechanics.get('cleanse',[])):
        raise ValueError('This character cannot act while incapacitated.')
    if actor.get('action_used') and not free: raise ValueError('Your action is spent; move or end your turn.')
    required_form=str(detail.get('requires_form') or '').strip()
    if required_form:
        _,_,active_buffs=_actor_effects(state,actor)
        if not any(obj(row).get('form') and str(obj(row).get('name'))==required_form for row in active_buffs):
            raise ValueError('Activate '+required_form+' before using this application.')
    form_token=actor['id']+':'+name
    if free and form_token in board.get('forms_used',[]): raise ValueError('That form was already changed this activation.')
    cost=max(0,number(detail.get('resource_cost'),20 if name else 0))
    resource_name={'One Piece':'stamina','Bleach':'Reiryoku'}.get(state.get('world'),'chakra')
    if pools.get('resource',0)<cost: raise ValueError('Not enough '+resource_name+'.')
    status,_,_=_actor_effects(state,actor)
    if state.get('world')=='Naruto' and cost and any(obj(s).get('kind')=='chakra_blocked' for s in status): raise ValueError('Chakra points are blocked.')
    cooldowns=combat.setdefault('tactical_cooldowns',{}) if actor.get('player') else actor.setdefault('cooldowns',{})
    if number(cooldowns.get(name))>0: raise ValueError('That technique is still on cooldown.')
    target=(int(number(payload.get('x'),actor['x'])),int(number(payload.get('y'),actor['y'])))
    area=footprint_cells(board,actor,spec,target,payload.get('facing','east'))
    support=effect in {'heal','shield','buff','cleanse','transform','summon','movement'}
    targets=[u for u in live_units(board) if (u['x'],u['y']) in area and
             (u['side']==actor['side'] if support else u['side']!=actor['side'])]
    if handler=='room_shambles':targets=[u for u in live_units(board) if u['id']!=actor['id'] and (u['x'],u['y'])==target]
    if handler=='marked_teleport':
        marks=[m for m in board.get('teleport_marks',[]) if obj(m).get('owner_id')==actor['id']]
        if not any((m.get('x'),m.get('y'))==target for m in marks):
            raise ValueError('Flying Thunder God requires your established mark at the destination.')
        if target not in cells(board)-blocked_cells(board) or any((u['x'],u['y'])==target for u in live_units(board)):
            raise ValueError('That marked destination is occupied or blocked.')
    elif handler in {'shadow_clone','contract_summon'}:
        open_cells=cells(board)-blocked_cells(board)-{(u['x'],u['y']) for u in live_units(board)}
        if target not in open_cells:raise ValueError('Choose an empty, unblocked tile for the summon.')
        if abs(target[0]-actor['x'])+abs(target[1]-actor['y'])>2:
            raise ValueError('Choose a summon tile within two movement squares.')
        if len(live_units(board))>=24: raise ValueError('No room to summon a unit.')
        area=[target]
        if handler=='contract_summon':
            summon=obj(detail.get('summon_profile'))
            if not summon.get('contract_established') or not obj(summon.get('stats')):
                raise ValueError('A recorded summoning contract and summon attributes are required.')
    elif effect=='transform':
        if (not obj(detail.get('stat_boosts')) and not obj(detail.get('combat_boosts'))
                and not seq(detail.get('release_unlocks'))):
            raise ValueError('This form needs actual stat boosts or recorded release applications; a generic bonus will not be invented.')
    elif not targets:
        raise ValueError('No valid target in this footprint.')
    if effect not in {'damage','control','debuff','heal','shield','cleanse','buff','transform','summon','movement'}:
        raise ValueError('This technique needs a dedicated tactical handler.')
    if effect in {'summon','movement'} and handler not in {'shadow_clone','contract_summon','marked_teleport','room_shambles'}:
        raise ValueError('This movement or summoning technique has no supported tactical handler.')
    required_status=mechanics.get('requires',{}).get('targetStatus')
    required_source=mechanics.get('requires',{}).get('targetStatusSource')
    if required_source and not all(any(obj(s).get('technique_id')==required_source and obj(s).get('source_id')==actor['id']
                                     for s in _actor_effects(state,u)[0]) for u in targets):
        raise ValueError('This target is not held by your required setup technique.')
    if required_status and not all(any(obj(s).get('kind')==required_status and obj(s).get('source_id')==actor['id']
                                      for s in seq(u.get('statuses'))) for u in targets):
        raise ValueError('The target must first be restrained by your matching technique.')
    # Validation above is read-only. Costs, visuals and outcomes share one accepted cast.
    _release_channel(board,actor)
    pools['resource']-=cost; actor['resource']=pools['resource']
    event={'round':combat['round'],'actor':'player' if actor.get('player') else actor['side'],'unit_id':actor['id'],'ability':name or 'Plain Attack',
           'name':actor['name'],'origin':{'x':actor['x'],'y':actor['y']},'shape':spec['shape'],
           'action':effect,'cost':cost,'affected_tiles':[list(p) for p in area],
           'visual':copy.deepcopy(detail.get('visual_effect',{})), 'targets':[]}
    if handler=='room_shambles':
        other=targets[0];origin=(actor['x'],actor['y']);actor['x'],actor['y']=other['x'],other['y'];other['x'],other['y']=origin
        event['destination']=list(target);event['swapped_with']=other['name']
    elif handler=='marked_teleport':
        actor['x'],actor['y']=target;event['destination']=list(target)
    elif handler in {'shadow_clone','contract_summon'}:
        serial=board.get('summon_serial',0)+1;board['summon_serial']=serial
        if handler=='shadow_clone':
            from portrait_generator import portrait_view
            child=copy.deepcopy(actor);child.update(id=f'clone-{serial}',name=actor['name']+' — Shadow Clone',player=False,human=False,owner_id=None,
                clone=True,hp=1,hp_max=1,statuses=[],buffs=[],debuffs=[],cooldowns={},alive=True,defeated=False)
            child.pop('character',None)
            child['portrait_url']=portrait_view(state if actor.get('player') else {**obj(actor.get('character')),'world':'Naruto','portrait_identity':actor.get('portrait_identity',{})},{})['_portrait_image']
            # Real resource split, not free copies of the caster's entire pool.
            share=int(pools['resource']//2);pools['resource']-=share;actor['resource']=pools['resource']
            child['resource']=share;child['resource_max']=share
            child['abilities']=[{'name':'Clone strike','resource_cost':0,'effect_type':'damage',
                                'tactical':{'shape':'single','range':1,'effect':'damage'}}]
        else:
            child=combat_profile(state,detail['summon_profile'],'ally',f'summon-{serial}')
        child.update(summoner_id=actor['id'],x=target[0],y=target[1],action_used=False)
        if actor.get('player') or actor.get('player_controlled'):
            child['player_controlled']=True
            child['skills']={a['name']:copy.deepcopy(a) for a in child.get('abilities',[]) if isinstance(a,dict) and a.get('name')}
        child['movement_max']=movement_budget(child['speed'],board['width']);child['movement_left']=0
        board['units'].append(child);event['summoned']=child['name'];event['destination']=list(target)
        event['visual']={'asset':'clone-barrage','delivery':'target','scale':1}
    elif effect=='transform':
        from worlds import speed_stat_for, defense_stat_for
        from portrait_generator import set_active_portrait_form
        boosts=obj(detail.get('combat_boosts')); stats=obj(detail.get('stat_boosts'))
        speed_base=max(1,number(actor.get('base_speed'),30)); defense_base=max(1,number(actor.get('defense'),30))
        world=state.get('world','Naruto')
        power_stat={'Bleach':'Reiatsu Control','One Piece':'Strength'}.get(world,'Ninjutsu')
        row={'name':name,'form':True,'rounds_left':max(1,int(number(detail.get('duration_rounds'),999999))),
             'speed_pct':number(boosts.get('speed_pct'),number(stats.get(speed_stat_for(world)))/speed_base),
             'power_pct':number(boosts.get('power_pct'),number(stats.get(power_stat))/max(1,actor['power'])),
             'defense_pct':number(boosts.get('defense_pct'),number(stats.get(defense_stat_for(world)))/defense_base),
             'upkeep':max(0,number(detail.get('upkeep'))),'recoil':max(0,number(detail.get('recoil')))}
        # Mutually exclusive forms replace, rather than repeatedly stacking on clicks.
        row['form_slot']=str(detail.get('form_slot') or ('eyes' if any(k in name.lower() for k in ('sharingan','byakugan','rinnegan')) else 'body'))
        form_owner=combat if actor.get('player') else actor
        form_key='player_buffs' if actor.get('player') else 'buffs'
        form_owner[form_key]=[r for r in seq(form_owner.get(form_key)) if not
                               (obj(r).get('form') and obj(r).get('form_slot','body')==row['form_slot'])]+[row]
        names=[r['name'] for r in form_owner[form_key] if obj(r).get('form')]
        set_active_portrait_form(state if actor.get('player') else actor,' + '.join(names),details=detail.get('description',''),source='tactical')
        board.setdefault('forms_used',[]).append(form_token)
        event.update(form=name,boosts=row,cutin=True)
    else:
        for unit in targets:
            statuses,debuffs,buffs=_actor_effects(state,unit)
            result={'id':unit['id'],'name':unit['name']}
            if effect in {'damage','control','debuff'} and mechanics.get('element') in seq(unit.get('immunities')):
                result.update(immune=True,damage=0);event['targets'].append(result);continue
            if state.get('world')=='One Piece' and effect in {'damage','control','debuff'}:
                target_caps=set(unit.get('capabilities',[]));actor_caps=set(actor.get('capabilities',[]))
                logia='logia' in target_caps or 'logia-fruit' in target_caps
                counter=bool({'armament-haki','seastone','natural-counter'} & actor_caps)
                if logia and not counter:
                    result.update(immune=True,damage=0,reason='Logia body requires Armament Haki, Sea-Prism Stone, or an established natural counter.')
                    event['targets'].append(result);continue
            if effect in {'damage','control','debuff'}:
                _,ad,ab=_actor_effects(state,actor)
                _,td,tb=_actor_effects(state,unit)
                world=state.get('world','Naruto')
                attribute=detail.get('stat') or (('Zanjutsu' if re.search(r'\b(sword|slash|zanpakuto|zanjutsu)\b',name,re.I) else
                                                   'Hakuda' if re.search(r'\b(punch|kick|hakuda|strike)\b',name,re.I) else 'Kido') if world=='Bleach' else
                                                  ('Strength' if world=='One Piece' else
                                                   'Taijutsu' if mechanics.get('element')=='physical' or not name else
                                                   'Genjutsu' if obj(mechanics.get('status')).get('kind')=='genjutsu' else 'Ninjutsu'))
                power=number(obj(actor.get('stats')).get(attribute),actor['power'])*max(.1,1+sum(number(obj(r).get('power_pct')) for r in [*ab,*ad]))
                defense=unit['defense']*(1+sum(number(obj(r).get('defense_pct')) for r in [*tb,*td]))
                check=game._combat_check(round((power-defense)/4),30,60);result.update(check)
                if not check['success']: event['targets'].append(result);continue
                if effect=='damage':
                    base=game._damage(unit['hp_max'],check['margin'],0,check['breakthrough'],power-defense>=30)
                    multiplier=number(detail.get('damage_multiplier'),max(.3,number(mechanics.get('damage'),34)/34))
                    damage=0 if defense-power>=30 else max(0,round(base*multiplier))
                    if unit.get('guarding'): damage=round(damage*.5)
                    shield=max(0,number(combat.get('player_shield') if unit.get('player') else unit.get('shield')))
                    absorbed=min(shield,damage)
                    if unit.get('player'): combat['player_shield']=shield-absorbed
                    else: unit['shield']=shield-absorbed
                    previous=unit['hp'];unit['hp']=max(_floor(combat,unit),previous-damage+absorbed)
                    result.update(damage=previous-unit['hp'],absorbed=absorbed)
                    if result['damage']:
                        statuses[:]=[s for s in statuses if obj(s).get('kind')!='genjutsu']
                applied=obj(mechanics.get('status'))
                if effect=='control' and not applied:
                    applied={'kind':str(detail.get('status_effect') or 'restrained').lower(),
                             'remaining':max(1,int(number(detail.get('duration_rounds'),1)))}
                if applied:
                    row={'name':applied['kind'].replace('_',' ').title(),'kind':applied['kind'],
                         'rounds_left':int(number(applied.get('remaining'),1)), 'source_id':actor['id'],
                         'technique_id':detail.get('catalog_id'),
                         'blocks_action':applied['kind'] in {'genjutsu','restrained','paralyzed'}}
                    if mechanics.get('channel'): row['channel_owner']=actor['id']
                    game._add_or_refresh_effect(statuses,row)
                if effect=='debuff':
                    potency=max(0,min(.9,number(detail.get('status_potency'),20)/100))
                    game._add_or_refresh_effect(debuffs,{'name':str(detail.get('status_effect') or 'Weakened'),
                         'rounds_left':max(1,int(number(detail.get('duration_rounds'),2))),
                         'power_pct':-potency,'defense_pct':-potency,'speed_pct':-potency})
                if mechanics.get('chakraDrain'):
                    unit['resource']=max(0,unit['resource']-number(mechanics['chakraDrain']))
                    if unit.get('player'): state['resource']=unit['resource']
                push=int(number(mechanics.get('push')))
                if push and not unit.get('defeated'):
                    dx,dy={'north':(0,-1),'east':(1,0),'south':(0,1),'west':(-1,0)}.get(payload.get('facing'),(1,0))
                    for _ in range(push):
                        cell=(unit['x']+dx,unit['y']+dy)
                        if cell not in cells(board)-blocked_cells(board) or any((u['x'],u['y'])==cell for u in live_units(board)): break
                        unit['x'],unit['y']=cell
            elif effect=='heal':
                amount=min(unit['hp_max']-unit['hp'],number(mechanics.get('heal'),number(detail.get('heal'),20)))
                unit['hp']+=amount;result['healed']=amount
            elif effect=='shield':
                amount=number(mechanics.get('shield'),number(detail.get('shield'),20))
                if unit.get('player'): combat['player_shield']=amount
                else: unit['shield']=amount
                result['shield']=amount
            elif effect=='cleanse':
                kinds=mechanics.get('cleanse',detail.get('cleanse',[]))
                statuses[:]=[s for s in statuses if obj(s).get('kind') not in kinds]
            elif effect=='buff':
                game._add_or_refresh_effect(buffs,{'name':name,'rounds_left':max(1,int(number(detail.get('duration_rounds'),2))),
                                                 **obj(detail.get('combat_boosts'))})
            if unit.get('player'): state['hp']=unit['hp']
            _mark_defeated(state,unit);event['targets'].append(result)
    if not free: actor['action_used']=True
    recoil=number(mechanics.get('selfDamage'))
    if recoil:
        actor['hp']=max(_floor(combat,actor),actor['hp']-recoil)
        if actor.get('player'):state['hp']=actor['hp']
    cooldowns[name]=max(0,int(number(detail.get('cooldown'))))
    board['last_footprint']=[list(p) for p in area]
    if effect=='damage':
        event['action']='attack'
        event['damage']=sum(t.get('damage',0) for t in event['targets'])
        event['target']=', '.join(t['name'] for t in event['targets'])
        event['success']=any(t.get('success') for t in event['targets'])
    combat['log'].append(event);refresh_movement(state,board)
