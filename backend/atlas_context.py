"""Canon context for the atlas, without treating a scheduled event as an outcome.

Dates below refer to EXISTING game scenario/event anchors, not manga dates.
Explicit campaign control always overlays these defaults in world_atlas.
"""
import re

VILLAGE_COUNTRIES = {
    'Konohagakure': 'Land of Fire', 'Sunagakure': 'Land of Wind',
    'Iwagakure': 'Land of Earth', 'Kumogakure': 'Land of Lightning',
    'Kirigakure': 'Land of Water', 'Amegakure': 'Land of Rain',
    'Kusagakure': 'Land of Grass', 'Takigakure': 'Land of Waterfalls',
    'Otogakure': 'Land of Rice Fields', 'Yugakure': 'Land of Hot Water',
}

SOURCES = {
    'Naruto': ('Country/village distinction; major relative geography', 'https://naruto-official.com/en/news/01_1401'),
    'One Piece': ('Island sovereignty, occupation and pirate protection', 'https://onepiece.fandom.com/wiki/World'),
    'Hunter x Hunter': ('Known-world regions; undisclosed positions remain approximate', 'https://hunterxhunter.fandom.com/wiki/World_of_Hunter_%C3%97_Hunter'),
    'Overgeared': ('Saharan dominance; other borders are inferred', 'https://overgeared.fandom.com/wiki/Saharan_Empire'),
    'Reincarnated as a Slime': ('Tempest grows from a settlement, not a pre-existing country', 'https://tensura.fandom.com/wiki/Jura-Tempest_Federation'),
    'Bleach': ('Seireitei surrounded by four Rukongai sectors', 'https://bleach.fandom.com/wiki/Soul_Society'),
    'Jujutsu Kaisen': ('Japan is civil territory; colonies are barriers', 'https://jujutsu-kaisen.fandom.com/wiki/Culling_Game/Colonies'),
}


def _int(value):
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return None


def baseline_day(state, world):
    """Freeze history at campaign creation. Never use elapsed time to annex land."""
    from worlds import timeline_for
    for key in ('atlas_start_day', 'calendar_anchor_day'):
        value = _int(state.get(key))
        if value is not None:
            return value, 'campaign start'
    if _int(state.get('turn')) == 0 and _int(state.get('canon_day')) is not None:
        return _int(state['canon_day']), 'campaign start'
    return int(timeline_for(world).get('start_day', -7)), 'default era; original start unavailable'


def contextualize(atlas, state, world, board):
    """Change political meaning, not stable tile IDs or campaign claims."""
    day, basis = baseline_day(state, world)
    notes = []
    metadata = {}
    rename = {}
    if world == 'Naruto':
        rename.update(VILLAGE_COUNTRIES)
        metadata = {v: {'sovereignty': country, 'local_authority': v}
                    for v, country in VILLAGE_COUNTRIES.items()}
        # These early starts explicitly precede Orochimaru's Sound network.
        if day <= -4380:
            metadata['Otogakure']['local_authority'] = 'Not established in this starting era'
            metadata['Otogakure']['era_unavailable'] = True
        notes.append('Countries are shaded; hidden-village command is separate from national sovereignty. Minor borders are gameplay approximations.')
    elif world == 'Reincarnated as a Slime':
        if day < 100:  # Existing "Tempest emerges" event, not a new date.
            rename['Jura Tempest Federation'] = 'Jura Forest communities'
            metadata['Tempest'] = {'era_unavailable': True, 'local_authority': 'No established Tempest nation at campaign start'}
        notes.append('The starting scenario determines whether Tempest exists. Later founding or conquest requires recorded campaign control, not merely elapsed days.')
    elif world == 'Overgeared':
        # All currently selectable Satisfy eras predate the later named realm.
        # No invented foundation date is added to the game calendar.
        rename['Valhalla'] = 'Belto Kingdom'
        metadata['Valhalla'] = {'display_name': 'Belto Kingdom', 'local_authority': 'Belto Kingdom'}
        notes.append('Belto precedes Ares’s Valhalla in the available starting eras. West/East Continent placement is established; exact kingdom borders and hinterlands use contextual extrapolation. A legendary class does not grant a kingdom.')
    elif world == 'Hunter x Hunter':
        notes.append('This is a known-world regional chart, not the complete planet. An estate, Association office or criminal presence does not own its surrounding country.')
    elif world == 'Bleach':
        notes.append('Each board is a separate realm diagram, not an island on a shared ocean. Seireitei and Rukongai are parts of Soul Society, not separate nations.')
    elif world == 'Jujutsu Kaisen':
        notes.append('Schools, clans and Culling Game barriers are not sovereign countries. Local control does not transfer all of Japan.')
    elif world == 'Solo Max-Level Newbie':
        notes.append('Current-floor diagram only. Terrain is not yet a canon-authored floor map; Tower administration is a neutral gameplay placeholder.')
    elif world == 'One Piece':
        metadata.update({
            'Dressrosa': {'sovereignty': 'Dressrosa Kingdom', 'local_authority': 'Donquixote regime'},
            'Wano Country': {'sovereignty': 'Wano Country', 'local_authority': 'Kurozumi shogunate / Beasts Pirates'},
            'Amazon Lily': {'sovereignty': 'Amazon Lily', 'local_authority': 'Kuja'},
            'Fishman Island': {'sovereignty': 'Ryugu Kingdom', 'protection': 'Whitebeard Pirates'},
        })
        rename['Dressrosa Kingdom'] = 'Donquixote Pirates'
        if day < -6450:  # Before existing Oden execution anchor (Roger-era start).
            rename.update({'Arlong Pirates':'Conomi Island communities', 'Dressrosa Kingdom':'Riku dynasty', "Kaido's Beasts Pirates":'Wano shogunate'})
            metadata['Dressrosa']['local_authority'] = 'Riku dynasty'
            metadata['Wano Country']['local_authority'] = 'Wano shogunate'
            metadata['Fishman Island']['protection'] = 'Not established for this era'
        if day > 14:  # Existing Arlong Park revolt anchor.
            rename['Arlong Pirates'] = 'Conomi Island communities'
        if day > 736:  # Existing Dressrosa liberation anchor.
            rename['Dressrosa Kingdom'] = 'Riku dynasty'
            metadata['Dressrosa']['local_authority'] = 'Riku dynasty'
        if day > 774:  # Existing Onigashima outcome anchor.
            rename["Kaido's Beasts Pirates"] = 'Kozuki shogunate'
            metadata['Wano Country']['local_authority'] = 'Kozuki shogunate'
        if day > 68:
            metadata['Fishman Island']['protection'] = 'Big Mom Pirates' if day >= 732 else 'Unsettled after the Summit War'
        notes.append('Island spacing and sizes are schematic. Occupation, kingdom sovereignty and protection are distinct; later campaign changes override starting history.')
    else:
        notes.append('Original-world geography and regional governments are authored gameplay content.')
    for cell in atlas['cells']:
        cell['owner'] = rename.get(cell['owner'], cell['owner'])
        cell['sovereignty'] = cell['owner']
        if world == 'One Piece' and cell['district'] in metadata:
            cell['sovereignty'] = metadata[cell['district']].get('sovereignty',cell['owner'])
        if world == 'Hunter x Hunter':
            site = next((s for s in atlas['seeds'] if s['name']==cell['district']), None)
            if site and site['name'] in {'Zoldyck estate','Hunter Association HQ','Meteor City','Yorknew district'}:
                if (site['x']-cell['x'])**2+(site['y']-cell['y'])**2 > 9:
                    region = atlas['land'][cell['land']]
                    cell.update(owner=region['owner'], sovereignty=region['owner'], district=region['name'])
    atlas['context'] = {'start_day': day, 'basis': basis, 'notes': notes,
                        'sources': [{'title': SOURCES[world][0], 'url': SOURCES[world][1]}] if world in SOURCES else [],
                        'extent': 'realm diagram' if world == 'Bleach' else 'floor diagram' if world == 'Solo Max-Level Newbie' else 'regional atlas'}
    return metadata


def explicitly_established(state, name):
    """A current location, discovery or authored claim can supersede an era gate."""
    key = name.casefold()
    if key in str(state.get('location', '')).casefold():
        return True
    if any(str(n).casefold() == key for n in (state.get('discovered_locations') or []) if isinstance(n, str)):
        return True
    details = state.get('location_details')
    if isinstance(details, dict) and any(str(n).casefold() == key for n in details):
        return True
    claims = state.get('political_regions')
    return isinstance(claims, list) and any(isinstance(c, dict) and key in
        {str(c.get('name', '')).casefold(), str(c.get('anchor', '')).casefold()}
        for c in claims)


def gm_map_context(state):
    """Small era facts only; no polygons, tile grid or reference URLs in prompts."""
    world=state.get('world','Custom World')
    atlas={'cells':[]}
    local=contextualize(atlas,state,world,'')
    facts=list(atlas['context']['notes'])
    for name,detail in local.items():
        if explicitly_established(state,name):
            continue
        if detail.get('era_unavailable'):
            facts.append(f'{name}: not established in this starting era; founding must occur through play.')
        elif detail.get('display_name'):
            facts.append(f"{name} site: currently {detail['display_name']}, not its later canon identity.")
    return {'basis':atlas['context']['basis'],'facts':facts,
            'precedence':'Explicit campaign control and divergences override starting history.'}
