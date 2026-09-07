"""Two-player ownership and persistent ten-minute tactical activations."""
import copy
import time
from tactical_combat import (ensure_board, player_profile, paths, live_units, obj, seq,
    refresh_movement, _blocked, _outcome, _end_activation, _result, _tick_actor,
    submit_naruto_action, board_view)
from naruto_tactics import compile_skill as naruto_compile, saved_skill_details as naruto_details

def rules(game):
    if game.state.get('world')=='One Piece':
        from one_piece_tactics import compile_skill,saved_skill_details
        return compile_skill,saved_skill_details
    if game.state.get('world')=='Bleach':
        from bleach_tactics import compile_skill,saved_skill_details
        return compile_skill,saved_skill_details
    return naruto_compile,naruto_details


def initialize(game, participants, host_id, now=None):
    board=ensure_board(game.state)
    if board.get('owners'):return board
    if len(participants)!=2:raise ValueError('The tactical room requires exactly two players.')
    host=next(u for u in board['units'] if u.get('player'))
    host.update(human=True,owner_id=str(host_id))
    owners={str(host_id):host['id']}
    for person in participants:
        uid=str(person['user_id'])
        if uid==str(host_id):continue
        character=copy.deepcopy(person['character'])
        _,details=rules(game)
        guest=player_profile({**game.state,**character});guest.update(id='pc:'+uid,player=False,human=True,owner_id=uid,
            character=character,skills=details(character))
        free=sorted(paths(board,(host['x'],host['y']),None,host['id']).items(),key=lambda v:len(v[1]))
        free=[p for p,route in free if route]
        if not free:raise ValueError('No connected spawn tile for the second player.')
        guest.update(x=free[0][0],y=free[0][1],movement_left=host['movement_max'],movement_max=host['movement_max'],action_used=False)
        board['units'].append(guest);owners[uid]=guest['id']
    board.update(owners=owners,active_id=host['id'],human_done=[],deadline=(time.time() if now is None else now)+600)
    refresh_movement(game.state,board)
    return board


def snapshot(game,user_id):
    board=board_view(game.state);actor_id=board.get('owners',{}).get(str(user_id),'player')
    actor=next(u for u in board['units'] if u['id']==actor_id)
    compile_skill,saved_skill_details=rules(game)
    source=(saved_skill_details(game.state) if actor.get('player') else actor.get('skills',{}))
    board['skill_profiles']={name:compile_skill(name,detail) for name,detail in source.items()}
    board['reachable']=[list(p) for p,route in paths(board,(actor['x'],actor['y']),actor['movement_left'],actor_id).items() if route]
    for unit in board['units']:
        unit.pop('character',None)
        if unit['id']!=actor_id:unit.pop('skills',None);unit.pop('capabilities',None)
    return {'world':game.state.get('world'),'board':board,'viewer_id':actor_id,'is_turn':board.get('active_id')==actor_id,
            'combat':{k:copy.deepcopy(game.state['combat'].get(k)) for k in ('active','outcome','spare_enemy','non_lethal','log','cause')},
            'portrait_identity':game.state.get('portrait_identity',{}) if actor.get('player') else actor.get('portrait_identity',{})}


def finish(game,board,actor,now,forced=False):
    foes=[u for u in live_units(board) if u['side']=='enemy']
    if not forced and not actor.get('bonus_taken') and not _blocked(game,actor) and foes and actor['speed']-max(u['speed'] for u in foes)>=25:
        actor['bonus_taken']=True;actor['action_used']=False;actor['movement_left']=actor['movement_max'];board['deadline']=now+600
        return
    board['human_done'].append(actor['id'])
    if not actor.get('player'):
        from tactical_combat import _status_damage, number, _floor
        _status_damage(game,actor)
        _tick_actor(actor)
        for form in list(actor.get('buffs',[])):
            if not form.get('form'):continue
            if actor['resource']<number(form.get('upkeep')):actor['buffs'].remove(form)
            else:
                actor['resource']-=number(form.get('upkeep'))
                actor['hp']=max(_floor(game.state['combat'],actor),actor['hp']-number(form.get('recoil')))
        from portrait_generator import clear_active_portrait_form, set_active_portrait_form
        forms=[r['name'] for r in actor.get('buffs',[]) if r.get('form')]
        if forms:set_active_portrait_form(actor,' + '.join(forms),source='tactical')
        else:clear_active_portrait_form(actor)
    pending=[u for u in live_units(board) if u.get('human') and u['id'] not in board['human_done']]
    if pending:board['active_id']=pending[0]['id']
    else:
        board['bonus_activation']=True  # each human already received their own fresh bonus choice
        _end_activation(game,board,len(game.state['combat']['log']))
        humans=[u for u in live_units(board) if u.get('human')]
        for unit in humans:unit.update(action_used=False,bonus_taken=False,movement_left=unit['movement_max'])
        board['human_done']=[]
        board['active_id']=humans[0]['id'] if humans else None
    board['deadline']=now+600


def submit(game,user_id,payload,now=None,forced=False):
    from naruto_tactical_actions import cast
    now=time.time() if now is None else now
    board=ensure_board(game.state);uid=str(user_id)
    actor_id=board.get('owners',{}).get(uid)
    if not actor_id:raise ValueError('You do not own a combatant in this encounter.')
    # Duplicate retries remain harmless even after ownership moves to another player.
    token=uid+':'+str(payload.get('request_id') or '')
    ledger=board.setdefault('room_requests',{})
    import json,hashlib
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    if token in ledger:
        if ledger[token]!=digest:raise ValueError('This request ID was used for a different command.')
        return snapshot(game,uid)
    if board.get('active_id')!=actor_id:raise ValueError('Wait for your combat turn.')
    if not payload.get('request_id') or payload.get('revision')!=board['revision']:raise ValueError('Refresh the battlefield before submitting this command.')
    actor=next(u for u in board['units'] if u['id']==actor_id)
    before=copy.deepcopy(game.state);story_len=len(game.story_log)
    try:
        action=payload.get('action');start=len(game.state['combat']['log'])
        if action=='end':finish(game,board,actor,now,forced)
        elif actor.get('player'):
            submit_naruto_action(game,{**payload,'request_id':token})
        elif action=='move':
            if _blocked(game,actor):raise ValueError('You cannot move while incapacitated.')
            target=(int(payload.get('x',-1)),int(payload.get('y',-1)))
            route=paths(board,(actor['x'],actor['y']),actor['movement_left'],actor_id).get(target)
            if not route:raise ValueError('Choose a reachable empty tile.')
            actor['x'],actor['y']=target;actor['movement_left']-=len(route)
        elif action in {'attack','transform'}:
            name=payload.get('ability','');skills=actor.get('skills',{})
            if name and name not in skills:raise ValueError('That technique is not known by your character.')
            compile_skill,_=rules(game)
            detail=compile_skill(name,skills[name]) if name else {'resource_cost':0,'tactical':{'shape':'single','range':1,'effect':'damage'}}
            cast(game,board,payload,actor,detail)
        elif action=='defend':
            if actor.get('action_used') or _blocked(game,actor):raise ValueError('No available action.')
            actor.update(guarding=True,action_used=True)
        elif action=='revert':
            actor['buffs']=[r for r in actor['buffs'] if not obj(r).get('form')]
            from portrait_generator import clear_active_portrait_form
            clear_active_portrait_form(actor);refresh_movement(game.state,board)
        else:raise ValueError('Unsupported room command.')
        _outcome(game,board,start)
        board['revision']+=1;ledger[token]=digest
        if len(ledger)>128:ledger.pop(next(iter(ledger)))
        game.autosave()
        return snapshot(game,uid)
    except Exception:
        game.state=before;del game.story_log[story_len:];raise


def tick(game,participants,now=None):
    now=time.time() if now is None else now
    board=ensure_board(game.state)
    if not board.get('owners') or not game.state['combat'].get('active'):return False
    actor=next((u for u in board['units'] if u['id']==board.get('active_id')),None)
    if not actor:return False
    person=next((p for p in participants if str(p['user_id'])==actor['owner_id']),{})
    if person.get('connected',False) and now<board['deadline']:return False
    submit(game,actor['owner_id'],{'action':'end','revision':board['revision'],
        'request_id':'auto:'+str(board['revision'])},now,forced=True)
    return True


def characters(game,participants):
    from multiplayer import character_from_state
    result={}
    for person in participants:
        uid=str(person['user_id']);unit=next((u for u in game.state['combat']['tactical']['units'] if u.get('owner_id')==uid),None)
        if not unit:continue
        data=character_from_state(game.state) if unit.get('player') else copy.deepcopy(person['character'])
        data.update(hp=unit['hp'],resource=unit['resource'],alive=unit.get('alive',True))
        if not unit.get('player'):data['portrait_identity']=unit.get('portrait_identity',{})
        result[uid]=data
    return result


def persist_members(game,store,room_id,participants):
    """Publish the shared battle result once and restart the narrative turn clock."""
    store.save_characters(room_id,characters(game,participants))
    combat=game.state['combat'];board=combat['tactical']
    if not combat.get('active') and not board.get('room_completed'):
        text='The battle ended: '+str(combat.get('outcome','resolved'))+'.'
        result={'status':'ok','narrative':text,'story':[{'text':text,'tag':'combat'}]}
        store.complete(room_id,result,{str(p['user_id']):result for p in participants})
        board['room_completed']=True
        game.autosave()
