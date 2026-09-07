"""Tactical objective rules. Reads never advance a round or award a result."""
from __future__ import annotations
import copy


def objective(state):
    combat=state.get('combat') or {}
    row=combat.get('adventure_objective')
    return row if isinstance(row,dict) else {}


def initialize(state,board):
    goal=objective(state)
    if not goal or goal.get('target'):return
    from tactical_combat import paths
    player=next(u for u in board['units'] if u.get('player'))
    reachable=paths(board,(player['x'],player['y']),board['width']*board['height'],'player')
    if not reachable:raise ValueError('The objective needs a reachable battlefield.')
    far=max(reachable,key=lambda p:(len(reachable[p]),p[0],p[1]))
    near=min((p for p in reachable if len(reachable[p])>=2),key=lambda p:len(reachable[p]),default=(player['x'],player['y']))
    goal['target']=list(near if goal['kind']=='protection' else far)
    goal['exit']=None if goal['kind']=='protection' else list((player['x'],player['y']) if goal['kind']=='retrieval' else far)
    goal['started_round']=int(state['combat'].get('round',1))


def public_view(state,board):
    initialize(state,board)
    g=copy.deepcopy(objective(state))
    if not g:return {}
    g['rounds_survived']=max(0,int(state['combat'].get('round',1))-g.get('started_round',1))
    actor=next((u for u in board['units'] if u['id']==board.get('active_id')),None)
    g['can_interact']=bool(actor and not actor.get('defeated') and not actor.get('action_used') and
        ((g['kind']=='retrieval' and not g.get('carried_by') and abs(actor['x']-g['target'][0])+abs(actor['y']-g['target'][1])<=1) or
         (g['kind']=='protection' and abs(actor['x']-g['target'][0])+abs(actor['y']-g['target'][1])<=1)))
    g['title']={'retrieval':'Recover the dispatch and reach the exit','protection':'Protect the relief beacon','escape':'Reach the far exit'}[g['kind']]
    g['interaction_label']='Take dispatch · 1 action' if g['kind']=='retrieval' else 'Shield beacon · 1 action'
    g['instructions']={'retrieval':'Move next to the gold dispatch marker and take it, then return its carrier to the teal exit. A fallen carrier drops the dispatch.',
       'protection':'Keep the beacon above 0 HP for four full rounds. Nearby allies can shield it; defeating all attackers also secures it.',
       'escape':'Move your character onto the teal exit. Defeating all opponents does not replace reaching the exit.'}[g['kind']]
    g['enemy_intents']=[{'id':u['id'],'name':u['name'],'intent':'Advance toward and attack the beacon' if g['kind']=='protection' else 'Intercept the nearest exposed opponent'} for u in board['units'] if u['side']=='enemy' and not u.get('defeated')]
    return g


def interact(game,board,actor):
    g=objective(game.state)
    if not g:raise ValueError('There is no interactive objective in this encounter.')
    from tactical_combat import _blocked
    if actor.get('action_used') or _blocked(game,actor):raise ValueError('An available, unblocked action is required.')
    if abs(actor['x']-g['target'][0])+abs(actor['y']-g['target'][1])>1:raise ValueError('Move next to the objective first.')
    if g['kind']=='retrieval':
        if g.get('carried_by'):raise ValueError('The dispatch is already being carried.')
        g['carried_by']=actor['id'];label='takes the dispatch'
    elif g['kind']=='protection':
        actor['guarding']=True;g['shield_round']=int(game.state['combat'].get('round',1));label='shields the beacon for this round'
    else:raise ValueError('Reach the marked exit to complete this objective.')
    actor['action_used']=True
    game.state['combat']['log'].append({'actor':actor['side'],'name':actor['name'],'unit_id':actor['id'],'action':label,'round':game.state['combat']['round']})


def outcome(state,board,ordinary):
    g=objective(state)
    if not g:return ordinary
    initialize(state,board)
    if ordinary=='defeat':return ordinary
    live=[u for u in board['units'] if not u.get('defeated') and u.get('hp',0)>0]
    carrier=next((u for u in board['units'] if u['id']==g.get('carried_by')),None)
    if carrier and carrier not in live:
        g['target']=[carrier['x'],carrier['y']];g['carried_by']=None;carrier=None
    if g['kind']=='protection':
        if g.get('target_hp',0)<=0:return 'objective_failed'
        survived=max(0,int(state['combat'].get('round',1))-g.get('started_round',1))
        if survived>=g.get('rounds_required',4) or not any(u['side']=='enemy' for u in live):return 'objective_complete'
    elif g['kind']=='retrieval':
        if carrier and [carrier['x'],carrier['y']]==g['exit']:return 'objective_complete'
    elif any(u.get('player') and [u['x'],u['y']]==g['exit'] for u in live):return 'objective_complete'
    return None  # Kill-all alone cannot resolve retrieval or escape.


def npc_action(game,board,actor):
    g=objective(game.state)
    if not g or g['kind']!='protection' or actor['side']!='enemy':return False
    from tactical_combat import paths,_blocked
    if _blocked(game,actor):return False
    target=g['target'];origin=(actor['x'],actor['y'])
    routes=paths(board,origin,actor['movement_max'],actor['id'])
    if not routes:return False
    destination=min(routes,key=lambda p:(abs(p[0]-target[0])+abs(p[1]-target[1]),len(routes[p])))
    distance=abs(destination[0]-target[0])+abs(destination[1]-target[1])
    # A defending body can genuinely block access. The normal AI then tries
    # to deal with that blocker rather than damaging a remote objective.
    if distance>1 and destination==origin:return False
    path=routes[destination];actor['x'],actor['y']=destination
    actor['movement_left']=max(0,actor['movement_max']-len(path));actor['action_used']=True
    log=game.state['combat']['log'];rnd=game.state['combat'].get('round',1)
    if path:log.append({'name':actor['name'],'actor':'enemy','action':'moves toward beacon','round':rnd,'path':[list(p) for p in path]})
    if distance<=1:
        protected=g.get('shield_round')==rnd or any(u['side']=='ally' and not u.get('defeated') and u.get('guarding') and abs(u['x']-target[0])+abs(u['y']-target[1])<=1 for u in board['units'])
        damage=max(3,min(20,round(actor['power']*.3)))
        if protected:damage=max(1,damage//3)
        prior=g['target_hp'];g['target_hp']=max(0,prior-damage)
        log.append({'name':actor['name'],'actor':'enemy','action':'attacks relief beacon','target':'Relief beacon','damage':prior-g['target_hp'],'round':rnd,'shielded':protected})
    return True
