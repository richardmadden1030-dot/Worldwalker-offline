"""Bounded, read-only evidence review. Suggestions are never applied on load."""
import re


def review_candidates(state):
    rows = state.get('campaign_canon', [])
    rows = rows if isinstance(rows,list) else []
    skills = state.get('skills', {})
    skills = skills if isinstance(skills,dict) else {}
    known = {str(k).casefold() for k in skills}
    results, seen, lost = [], set(), set()
    # The existing correction screen also exposes unresolved structured claims.
    # This is a proposal only, never an automatic repair of an old campaign.
    ledger = state.get('consequence_ledger', [])
    for claim in reversed(ledger[-240:] if isinstance(ledger, list) else []):
        if not isinstance(claim, dict) or claim.get('status') != 'needs_detail': continue
        target = str(claim.get('target') or '').strip()
        if not target or target.casefold() in seen: continue
        subject = str(claim.get('subject') or 'player')
        personal = subject.casefold() in {'player','you','the player',str(state.get('name')).casefold()}
        if personal and claim.get('kind') == 'skill' and target.casefold() in known: continue
        seen.add(target.casefold())
        results.append({'type':'skill' if personal and claim.get('kind') == 'skill' else 'fact',
                        'target':target,'value':str(claim.get('evidence') or ''),'text':str(claim.get('evidence') or ''),
                        'turn':claim.get('turn'),'note':f"Unresolved record for {subject}: {claim.get('reason', 'Review the details')}. Confirm the current outcome before applying."})
        if len(results)>=20:return results
    from worlds import WORLD_DATA
    places = [r[0] for r in WORLD_DATA.get(state.get('world'),{}).get('map',[]) if isinstance(r,(list,tuple)) and r]
    actor = re.escape(str(state.get('name') or 'Player'))
    # Do not interpret plans, conditional promises, or arbitrary NPC gains as
    # completed acquisitions. Even explicit statements still require review.
    pattern = re.compile(r'(?:^|[.!?]\s+)(?:You|' + actor + r')\s+(?:have\s+)?(?:learned|unlocked|awakened|mastered)\s+([A-Z][^.!?\n]{2,100})[.!?]', re.I)
    for row in reversed(rows[-500:]):
        if not isinstance(row,dict): continue
        text = str(row.get('outcome') or row.get('text') or '')[:4000].replace('**','')
        for loss in re.finditer(r'(?:^|[.!?]\s+)(?:You|' + actor + r')\s+(?:have\s+)?(?:lost|forgotten|forgot)\s+([^.!?\n]{2,100})[.!?]',text,re.I):
            lost.add(loss.group(1).strip(' "*').casefold())
        for place in places:
            match=re.search(r'(?:^|[.!?]\s+)(?:You|' + actor + r')\s+(?:have\s+)?(?:conquered|captured|taken control of)\s+'+re.escape(place)+r'[.!?]',text,re.I)
            key='territory:'+place.casefold()
            if match and key not in seen:
                seen.add(key)
                results.append({'type':'territory','target':place,'value':str(state.get('name') or 'Player'),
                                'text':text[:1600],'turn':row.get('turn'),
                                'note':'Historical control evidence, not proof of current ownership. Check later losses and enter the current faction before applying.'})
                if len(results)>=20:return results
        for match in pattern.finditer(text):
            name = match.group(1).strip(' "*')
            if re.search(r'\b(if|might|could|would|will|not|never|but|after|through|and)\b',name,re.I): continue
            key=name.casefold()
            if key in known or key in seen or key in lost: continue
            seen.add(key)
            results.append({'type':'skill','target':name,'value':match.group(0).lstrip('.!? '),
                            'text':text[:1600],'turn':row.get('turn'),
                            'note':'Possible missing ability. Confirm its name and details; no costs or stat boosts are invented.'})
            if len(results)>=20:return results
    return results
