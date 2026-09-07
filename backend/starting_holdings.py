"""Conservative local bridge for explicit starting land statements.

Only new-campaign creation calls this. Never re-interpret an old background
after its owner may have lost that territory. Ambiguous prose stays with GM.
"""
import re
from atlas_context import VILLAGE_COUNTRIES


def initialize_starting_holdings(state):
    from worlds import WORLD_DATA
    from world_atlas import preset
    from politics import normalize_political_state
    world = state.get('world', 'Custom World')
    # Multi-realm original holdings need an explicit realm/anchor from GM.
    if world in {'Bleach','Solo Max-Level Newbie'}:
        return []
    atlas = preset(world)
    locations = {str(n[0]).casefold():str(n[0]) for n in WORLD_DATA.get(world,{}).get('map',[])}
    countries = {s['name'].casefold():s['name'] for s in atlas['seeds']}
    countries.update({l['name'].casefold():l['name'] for l in atlas['land']})
    if world == 'Naruto':
        countries.update({v.casefold():v for v in VILLAGE_COUNTRIES.values()})
    aliases = {'konoha':'Konohagakure','suna':'Sunagakure','kiri':'Kirigakure'} if world=='Naruto' else {}
    known = {**locations, **countries, **aliases}
    changes = []
    for sentence in re.split(r'[.!?\n]+',str(state.get('background',''))):
        sentence=sentence.strip()
        sovereign=re.fullmatch(r"I am (?:the )?(king|queen|ruler|daimyo|governor|chief|Hokage|Kazekage|Mizukage|Raikage|Tsuchikage) of (.+)",sentence,re.I)
        estate=re.fullmatch(r"I own (?:a|an|my) (small )?(estate|farm|holding|fort|castle) (?:in|near) (.+)",sentence,re.I)
        if not sovereign and not estate:
            continue
        match=sovereign or estate
        target=known.get(match.group(2 if sovereign else 3).strip().casefold())
        if not target:
            continue
        if sovereign and sovereign.group(1).casefold().endswith('kage'):
            target=next((v for v,country in VILLAGE_COUNTRIES.items() if country==target),target)
        name=str(state.get('name') or 'Player')
        controller=target if sovereign else f"{name}'s {estate.group(2).lower()}"
        nationwide=bool(sovereign and target.casefold() in countries and target not in VILLAGE_COUNTRIES)
        claim={'id':'starting-'+re.sub(r'[^a-z0-9]+','-',controller.lower()).strip('-'),
               'name':controller,'controller':controller,'anchor':target,'world':world,
               'scale':'country' if nationwide else 'village' if sovereign else 'holding',
               'hex_count':0 if nationwide else 7 if sovereign else 1,
               'player_founded':not bool(sovereign)}
        # Countries absent from the destination list still have authored seeds.
        point=next((s for s in atlas['seeds']+atlas['land'] if s['name']==target),None)
        if point: claim.update(x=point['x'],y=point['y'])
        state.setdefault('political_regions',[]).append(claim)
        state.setdefault('polity_state',{})[controller]={'player_led':True,'leader':name}
        state.setdefault('affiliations',[]).append({'faction':controller,'rank':sovereign.group(1) if sovereign else 'Owner','status':'active'})
        changes.append(f"{name} starts with established control of {controller} at {target}.")
    if changes: normalize_political_state(state)
    return changes
