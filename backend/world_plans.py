"""Durable causal plans. No random crises, AI calls, or automatic conquests."""
import copy
import math


def obj(value): return value if isinstance(value,dict) else {}
def seq(value): return value if isinstance(value,list) else []
def text(value,limit=500): return value.strip()[:limit] if isinstance(value,str) else ''
def number(value,default=0):
    try:
        n=float(value)
        return n if math.isfinite(n) else default
    except (TypeError,ValueError): return default


def actors(state):
    names={text(state.get('name'))}
    for field in ('npc_memories','contacts','factions','organizations'):
        names.update(obj(state.get(field)))
        names.update(text(row.get('name')) for row in obj(state.get(field)).values() if isinstance(row,dict))
    for row in seq(state.get('companions')):
        names.add(text(row.get('name')) if isinstance(row,dict) else text(row))
    return names


def visible(plan):
    delivery=obj(plan.get('delivery'))
    return plan.get('known_to_player') is True and bool(text(delivery.get('source'))) and delivery.get('channel') in {'witnessed','message','public','report'}


def normalize(state):
    store=state.setdefault('world_plans',{})
    if not isinstance(store,dict): store=state['world_plans']={}
    cleaned={}
    for key,raw in list(store.items())[-80:]:
        if not isinstance(raw,dict):continue
        plan=copy.deepcopy(raw)
        plan['stages']=[s for s in seq(plan.get('stages')) if isinstance(s,dict)][:8]
        if not plan['stages']:continue
        plan['stage']=min(len(plan['stages']),max(0,int(number(plan.get('stage')))))
        plan['elapsed_minutes']=max(0,number(plan.get('elapsed_minutes')))
        plan['history']=seq(plan.get('history'))[-12:]
        cleaned[str(key)[:100]]=plan
    state['world_plans']=cleaned
    return cleaned


def advance(state, elapsed_minutes=0, updates=None):
    plans=normalize(state); turn=int(number(state.get('turn')))
    # Updates are commands against app-owned state, never replacement ledgers.
    for update in seq(updates)[:20]:
        if not isinstance(update,dict):continue
        key=text(update.get('id'),100); op=update.get('op'); plan=plans.get(key)
        if not key:continue
        if op=='create' and not plan and len(plans)<80:
            if text(update.get('actor')) not in actors(state) or not text(update.get('evidence')):continue
            stages=[]
            for raw in seq(update.get('stages'))[:8]:
                if not isinstance(raw,dict) or not text(raw.get('summary')):continue
                stages.append({'summary':text(raw['summary'],240),
                               'minutes':max(60,min(5256000,number(raw.get('minutes'),10080))),
                               'routine':raw.get('routine') is True,
                               'requires':[text(x,100) for x in seq(raw.get('requires')) if text(x,100)][:8]})
            if not stages:continue
            plan=plans[key]={'id':key,'actor':text(update.get('actor')),'goal':text(update.get('goal'),240),
                            'evidence':text(update.get('evidence')),'location':text(update.get('location')),
                            'standing_intent_id':text(update.get('standing_intent_id'),100),
                            'stages':stages,'stage':0,'elapsed_minutes':0,'status':'active','created_turn':turn,
                            'known_to_player':update.get('known_to_player') is True,
                            'delivery':{k:text(obj(update.get('delivery')).get(k)) for k in ('source','channel')},
                            'history':[]}
        elif plan and op in {'block','cancel','resume'} and text(update.get('reason')):
            if plan.get('status') in {'completed','cancelled'}:continue
            plan['status']={'block':'blocked','cancel':'cancelled','resume':'active'}[op]
            plan['blocked_reason']=text(update['reason']) if op=='block' else ''
            plan['pending_report']=text(update.get('report'),240)
        elif plan and op=='reveal' and text(obj(update.get('delivery')).get('source')):
            plan['known_to_player']=True; plan['delivery']=copy.deepcopy(update['delivery'])
        elif plan and op=='resolve' and plan.get('status')=='awaiting_resolution' and text(update.get('evidence')):
            if update.get('success') is True:
                finish_stage(plan,text(update.get('report'),240) or plan['stages'][plan['stage']]['summary'],turn)
                plan['last_tick_turn']=turn
                # Improvements persist until an explicitly recorded disruption.
                benefit=obj(update.get('benefit'))
                if benefit.get('kind')=='narrative' and text(benefit.get('description')):
                    benefits=state.setdefault('world_benefits',{})
                    if isinstance(benefits,dict):benefits[key]={'kind':'narrative','description':text(benefit['description']),
                                                               'reason':text(update['evidence']),'active':True}
                elif benefit.get('kind')=='safer_route' and text(benefit.get('origin')) and text(benefit.get('destination')):
                    benefits=state.setdefault('world_benefits',{})
                    if isinstance(benefits,dict):
                        benefits[key]={'kind':'safer_route','origin':text(benefit['origin']),
                                       'destination':text(benefit['destination']),'factor':max(.5,min(1,number(benefit.get('factor'),1))),
                                       'reason':text(update['evidence']),'active':True}
            else:
                plan['status']='blocked'; plan['blocked_reason']=text(update['evidence'])
                plan['pending_report']=text(update.get('report'),240)
        elif op=='revoke_benefit' and text(update.get('reason')):
            benefit=obj(state.get('world_benefits')).get(key)
            if isinstance(benefit,dict): benefit.update(active=False,ended_reason=text(update['reason']))

    elapsed=max(0,number(elapsed_minutes))
    intents={str(r.get('id')):r for r in seq(state.get('standing_intents')) if isinstance(r,dict)}
    for key,plan in plans.items():
        # Retries/rendering may revisit the same turn. Never spend its time twice.
        if plan.get('last_tick_turn')==turn:continue
        plan['last_tick_turn']=turn
        if plan.get('status')!='active':continue
        linked=intents.get(plan.get('standing_intent_id'))
        if plan.get('standing_intent_id') and (not linked or linked.get('status') not in {'active'}):
            continue
        actor=obj(obj(state.get('npc_memories')).get(plan.get('actor')))
        if actor.get('status') in {'dead','deceased','missing','imprisoned','incapacitated'}:continue
        # A plan created at the end of this turn cannot consume all preceding time.
        if plan.get('created_turn')==turn:continue
        remaining=elapsed
        while plan.get('status')=='active' and remaining>0 and plan['stage']<len(plan['stages']):
            stage=plan['stages'][plan['stage']]
            if any(obj(plans.get(req)).get('status')!='completed' for req in seq(stage.get('requires'))):break
            duration=max(60,number(stage.get('minutes'),10080))
            used=min(remaining,max(0,duration-plan['elapsed_minutes']))
            plan['elapsed_minutes']+=used; remaining-=used
            if plan['elapsed_minutes']<duration:break
            if stage.get('routine') is not True:
                plan['status']='awaiting_resolution'; break
            finish_stage(plan,stage['summary'],turn)
    events=[]
    for key,plan in plans.items():
        if len(events)>=2:break
        report=text(plan.get('pending_report'),240)
        if not report or not visible(plan):continue
        token=f"{plan.get('stage')}:{plan.get('status')}:{report}"
        if token==plan.get('last_report'):continue
        events.append({'title':text(plan.get('goal'),100) or 'World development','narrative':report,
                       'type':'world','importance':55,'sequence':7550+len(events),
                       'why_it_matters':text(plan.get('evidence')),'world_plan_id':key})
        plan['last_report']=token; plan.pop('pending_report',None)
    return events


def finish_stage(plan,report,turn):
    plan['history'].append({'stage':plan['stage'],'turn':turn,'summary':report})
    plan['history']=plan['history'][-12:]
    plan['stage']+=1; plan['elapsed_minutes']=0
    plan['status']='completed' if plan['stage']>=len(plan['stages']) else 'active'
    plan['pending_report']=report


def context(state):
    rows=[]
    ordered=sorted(obj(state.get('world_plans')).items(),key=lambda pair:(obj(pair[1]).get('status')!='awaiting_resolution',obj(pair[1]).get('location')!=state.get('location')))
    for key,plan in ordered:
        if not isinstance(plan,dict) or plan.get('status') in {'completed','cancelled'}:continue
        rows.append({k:copy.deepcopy(plan.get(k)) for k in ('id','actor','goal','location','status','stage','elapsed_minutes','stages','blocked_reason','known_to_player','delivery','standing_intent_id')})
    return {'plans':rows[:12], 'benefits':[dict(obj(v),id=k) for k,v in list(obj(state.get('world_benefits')).items())[-12:]],
            'benefit_example':{'kind':'narrative','description':'An established positive change that persists until a causal disruption.'},
            'contract': 'Continue established plans and standing orders without routine refusal or invented setbacks. Use world_plan_updates, never state_patch world_plans. Create: {op:create,id,actor,goal,location,evidence,standing_intent_id(optional),known_to_player,delivery:{source,channel:witnessed|message|public|report},stages:[{summary:short completed milestone sentence,minutes,routine,requires:[plan IDs]}]}. Actor must be established; evidence must cite real motives, resources and opportunities. Use routine:true only for safe unopposed work with resources and consent already established. Never use it for conquest, negotiations, new powers, marriages or contested outcomes. Waiting stages require resolve with id,success,evidence,report; narrate and record actual territory/NPC location changes through normal state fields. Block/cancel/resume require id,reason and optional report; do not invent obstacles. Reveal requires id,delivery. Reports require player knowledge and a plausible delivery route, not omniscience. Do not seed a plan for every NPC. Useful opportunities and clean successes are valid outcomes. Resolve may include benefit:{kind:safer_route,origin,destination,factor:0.5..1} only for a causally established travel improvement; revoke_benefit requires id,reason. Never erase benefits merely to create drama.'}
