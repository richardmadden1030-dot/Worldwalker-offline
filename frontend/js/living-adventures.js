/* Timed, confirmed server actions. The composer remains a separate itinerary. */
const LivingAdventures = (() => {
  'use strict';
  let selection = 0, routeSelection = 0, previewSelection = 0, selectedPlace = '', mapCampaign = null, dialog = null, quote = null, resolving = false;
  const escape = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const duration = n => { n=Math.max(0,Math.trunc(Number(n)||0)); return n>=1440 ? `${Math.floor(n/1440)}d ${Math.floor(n%1440/60)}h ${n%60}m` : n>=60 ? `${Math.floor(n/60)}h ${n%60 ? n%60+'m' : ''}`.trim() : `${n} min`; };
  const detail = () => document.getElementById('map-detail');
  const button = (a) => `<button type="button" class="adventure-action" data-town-action="${escape(a.id)}"><span><b>${escape(a.label)}</b>${a.description?`<small>${escape(a.description)}</small>`:''}</span><strong>${escape(duration(a.minutes))}${a.cost?`<small>${escape(a.cost)} ${escape(a.currency||'')}</small>`:''}</strong></button>`;
  function cancelSelection() { selection++;routeSelection++;selectedPlace=''; }
  function valid(target,token,campaign) {return detail()===target && target.isConnected && token===selection && APP.state?.campaign_id===campaign;}
  function wireMap(host) {
    const campaign=APP.state?.campaign_id;
    if(mapCampaign && mapCampaign!==campaign)cancelSelection();
    mapCampaign=campaign;
    const heading=host.querySelector('.map-heading') || host.querySelector('.living-map-main-head') || host.querySelector('.panel-head') || host.querySelector('.atlas-toolbar');
    if (!heading || heading.querySelector('[data-location-home]')) return;
    const tools=document.createElement('span');tools.className='adventure-map-tools';
    tools.innerHTML='<button type="button" data-location-home>Local activities</button><button type="button" data-canon-reference>Canon timeline</button>';
    heading.append(tools);
    tools.querySelector('[data-location-home]').onclick=()=>showLocation(APP.state?.location);
    tools.querySelector('[data-canon-reference]').onclick=()=>openJournal('timeline');
    if(selectedPlace)showLocation(selectedPlace,false);
  }
  async function showLocation(name,focus=true) {
    const target=detail();if(!target||!name)return;
    const token=++selection,campaign=APP.state?.campaign_id;routeSelection++;selectedPlace=name;
    target.classList.add('open');target.innerHTML='<button class="atlas-close" data-atlas-close aria-label="Close location details">×</button><p role="status">Reading the location…</p>';
    try {
      const v=await apiGet('/api/adventures/location?place='+encodeURIComponent(name));
      if(!valid(target,token,campaign))return;
      const node=(APP.latestMapData?.map_data?.nodes||[]).find(n=>n.name===v.place)||{};
      const picture=/^\/assets\//.test(v.scene_image||'') ? `<img class="adventure-location-art" src="${escape(v.scene_image)}" alt="${escape(v.place)}">`:'';
      const groups=[['Rest and preparation',a=>/^(rest:|prepare|scout|activity:|journey:)/.test(a.id)],['Training',a=>a.id.startsWith('train:')],['Character mastery',a=>a.id.startsWith('path:')],['World conflict',a=>a.id.startsWith('conflict:')],['Expeditions',a=>a.id.startsWith('expedition:')],['Property & economy',a=>/^(property:|craft:)/.test(a.id)],['Public profile',a=>a.id.startsWith('reputation:')],['Known people',a=>a.id.startsWith('talk:')],['Trade',a=>a.id.startsWith('purchase:')]];
      target.innerHTML=`<button type="button" class="atlas-close" data-atlas-close aria-label="Close location details">×</button>${picture}<header class="adventure-place"><small>${escape(v.kind)} · ${v.current?'YOU ARE HERE':v.known?'KNOWN PLACE':'MAP REFERENCE'}</small><h2>${escape(v.place)}</h2></header><p>${escape(v.situation)}</p>${node.controller?`<p><b>Control:</b> ${escape(node.controller)}</p>`:''}<p class="adventure-meta">${v.services.map(escape).join(' · ')}</p>${v.warning?`<p class="adventure-warning">${escape(v.warning)}</p>`:''}
      ${v.conflict?.operations?.length||v.conflict?.contested_by?.length?`<section class="adventure-world-state"><h3>World conflict here</h3>${v.conflict?.contested_by?.length?`<p><b>Contested:</b> ${v.conflict.contested_by.map(escape).join(' · ')}</p>`:''}${(v.conflict.operations||[]).map(o=>`<p><b>${escape(o.faction)}</b> · ${escape(o.type)} · ${escape(o.progress)}%<br><small>${escape(o.objective||'Active operation')}</small></p>`).join('')}</section>`:''}${v.property_economy?.market?`<section class="adventure-world-state"><h3>Local economy</h3><p><b>${escape(v.property_economy.market.condition)}</b> · market index ×${escape(v.property_economy.market.price_multiplier)}</p>${(v.property_economy.properties||[]).filter(p=>p.location===v.place).map(p=>`<p><b>${escape(p.name)}</b> · treasury ${escape(p.treasury||0)}<br><small>${escape((p.facilities_readable||[]).join(' · ')||'No facility upgrades')}</small></p>`).join('')}</section>`:''}${v.reputation?.jurisdictions?.some(j=>j.heat>0)?`<section class="adventure-world-state"><h3>Public attention</h3>${v.reputation.jurisdictions.filter(j=>j.heat>0).slice(0,3).map(j=>`<p><b>${escape(j.faction)}</b> · ${escape(j.wanted)} · heat ${escape(j.heat)}</p>`).join('')}</section>`:''}${v.expedition?`<section class="adventure-world-state"><h3>${v.expedition.status==='active'?'Active expedition':'Expedition lead'}</h3><p><b>${escape(v.expedition.title)}</b>${v.expedition.stage?` · ${escape(v.expedition.stage.replaceAll('_',' '))}`:''}</p>${v.expedition.boss?`<small>Boss: ${escape(v.expedition.boss)}</small>`:''}${(v.expedition.intel||[]).length?`<ul>${v.expedition.intel.slice(-3).map(i=>`<li>${escape(i)}</li>`).join('')}</ul>`:''}<small>${escape(v.expedition.authorship||'')}</small></section>`:''}${v.current?`<p class="adventure-instruction">Every activity shows its time. Review and confirm before anything resolves.</p>${groups.map(([title,predicate])=>{const rows=v.actions.filter(predicate);return rows.length?`<details class="adventure-group" ${title==='Rest and preparation'?'open':''}><summary>${title} <small>${rows.length}</small></summary>${rows.map(button).join('')}</details>`:'';}).join('')}`:''}
      ${v.mission?`<section class="adventure-mission"><small>${escape(v.mission.authorship)}</small><h3>${escape(v.mission.title)}</h3><p>${escape(v.mission.description)}</p><p class="adventure-meta">${escape(v.mission.contact)} · ${escape(v.mission.status)}</p>${v.actions.filter(a=>a.id.startsWith('mission:')).map(button).join('')}</section>`:''}
      ${v.aftermath.length?`<section class="adventure-aftermath"><h3>What changed here</h3>${v.aftermath.slice().reverse().map(r=>`<article><b>${escape(r.title)}</b><small>${escape(formatCalendarDate(v.world,r.canon_day,APP.state.calendar_epoch,APP.state.calendar_anchor_day))} · ${escape(r.method)}</small><p>${escape(r.description)}</p>${r.changes.map(c=>`<p>${escape(c)}</p>`).join('')}<button type="button" data-aftermath-story="${escape(r.story_id)}">Read the Chronicle event</button></article>`).join('')}</section>`:''}
      ${!v.current?'<section class="adventure-journey"><h3>Plan your journey</h3><label>Travel pace and preparation<select data-travel-preparation><option value="normal">Normal pace</option><option value="cautious">Cautious · more time, less exposure</option><option value="swift">Swift · less time, more exposure</option><option value="booked_passage">Book passage · where available</option></select></label><label>Available companion<select data-travel-companion><option value="">Travel alone</option></select></label><div data-route-options role="status">Checking mapped routes…</div></section>':''}`;
      const image=target.querySelector('.adventure-location-art');
      if(image)image.addEventListener('error',()=>{image.hidden=true;},{once:true});
      target.querySelectorAll('[data-town-action]').forEach(b=>b.onclick=()=>preview({place:v.place,action:b.dataset.townAction}));
      target.querySelectorAll('[data-aftermath-story]').forEach(b=>b.onclick=()=>showAftermath(b.dataset.aftermathStory));
      if(!v.current){
        const prep=target.querySelector('[data-travel-preparation]'),comp=target.querySelector('[data-travel-companion]');
        const load=()=>loadRoutes(v.place,prep.value,comp.value,target,token,campaign);
        prep.onchange=comp.onchange=load;await load();
      }
      target.tabIndex=-1;if(focus)target.focus({preventScroll:true});
    }catch(error){if(valid(target,token,campaign))target.innerHTML=`<button class="atlas-close" data-atlas-close aria-label="Close details">×</button><p class="adventure-warning">${escape(error.message)}</p>`;}
  }
  async function loadRoutes(destination,preparation,companion,target,token,campaign) {
    const run=++routeSelection,box=target.querySelector('[data-route-options]');box.textContent='Comparing established routes…';
    try{
      const data=await apiGet('/api/adventures/routes?'+new URLSearchParams({destination,preparation,companion}));
      if(!valid(target,token,campaign)||run!==routeSelection)return;
      const select=target.querySelector('[data-travel-companion]');
      if(data.companions && select.options.length===1)for(const person of data.companions){const o=document.createElement('option');o.value=person.name;o.textContent=person.name;select.append(o);}
      box.innerHTML=data.routes.length?data.routes.map(r=>`<article class="adventure-route"><header><b>${escape(r.label)}</b><strong>${escape(duration(r.minutes))}</strong></header><p>${r.route.map(escape).join(' → ')}</p><small>Exposure ${escape(r.exposure)}/100 · ${escape(r.risk_basis)}</small>${r.cost?`<p>Passage: ${escape(r.cost)} ${escape(r.currency)}</p>`:''}${r.requirements.length?`<p>Access: ${r.requirements.map(escape).join('; ')}</p>`:''}${r.blocked_requirements.length?`<p class="adventure-warning">Required: ${r.blocked_requirements.map(escape).join('; ')}</p>`:''}<button type="button" data-route-id="${escape(r.id)}" ${r.available?'':'disabled'}>Review journey · ${escape(duration(r.minutes))}</button></article>`).join(''):`<p>${escape(data.reason)}</p>`;
      box.querySelectorAll('[data-route-id]').forEach(b=>b.onclick=()=>{const r=data.routes.find(r=>r.id===b.dataset.routeId);preview({action:'journey:start',place:r.origin,destination:r.destination,route_id:r.id,preparation:r.preparation,companion:r.companion});});
    }catch(e){if(valid(target,token,campaign)&&run===routeSelection)box.textContent=e.message;}
  }
  function ensureDialog() {
    if(dialog)return dialog;
    dialog=document.createElement('dialog');dialog.id='adventure-confirmation';dialog.className='adventure-dialog';dialog.setAttribute('aria-labelledby','adventure-confirm-title');
    dialog.innerHTML='<header><small>REVIEW ACTIVITY</small><h2 id="adventure-confirm-title"></h2></header><div data-confirm-body></div><p data-confirm-error role="alert"></p><footer><button type="button" data-confirm-cancel>Cancel</button><button type="button" class="primary" data-confirm-yes>Confirm and resolve</button></footer>';
    document.body.append(dialog);
    dialog.querySelector('[data-confirm-cancel]').onclick=()=>{if(!resolving){previewSelection++;quote=null;dialog.close();}};
    dialog.addEventListener('cancel',e=>{if(resolving)e.preventDefault();else {previewSelection++;quote=null;}});
    dialog.querySelector('[data-confirm-yes]').onclick=confirm;
    return dialog;
  }
  async function preview(payload) {
    if(resolving||APP.busy)return;
    const run=++previewSelection,campaign=APP.state?.campaign_id;const d=ensureDialog();quote=null;d.querySelector('[data-confirm-cancel]').textContent='Cancel';d.querySelector('[data-confirm-yes]').disabled=true;d.querySelector('[data-confirm-error]').textContent='';d.querySelector('#adventure-confirm-title').textContent='Preparing activity';d.querySelector('[data-confirm-body]').textContent='Checking time, availability and access…';
    if(!d.open)d.showModal();
    try {
      const q=await apiPost('/api/adventures/preview',payload);
      if(!d.open||run!==previewSelection||campaign!==APP.state?.campaign_id)return;
      quote=q;d.querySelector('#adventure-confirm-title').textContent=q.spec.label;
      d.querySelector('[data-confirm-body]').innerHTML=`<div class="adventure-time"><b>${escape(duration(q.minutes))} will pass</b><p>${escape(q.start)}</p><span>↓</span><p>${escape(q.end)}</p></div>${q.spec.description?`<p>${escape(q.spec.description)}</p>`:''}${q.spec.cost?`<p><b>Cost:</b> ${escape(q.spec.cost)} ${escape(q.spec.currency||'')}</p>`:''}${q.interruption?`<p class="adventure-warning">This activity will pause after ${escape(duration(q.interruption.after_minutes))} for ${escape(q.interruption.title)}. The remaining time is retained.</p>`:''}${q.warnings.map(w=>`<p class="adventure-warning">${escape(w)}</p>`).join('')}<p class="adventure-meta">${escape(q.calendar.calendar)} · ${escape(q.calendar.precision)}</p><details><summary>About this calendar</summary><p>${escape(q.calendar.note)}</p></details>`;
      d.querySelector('[data-confirm-yes]').textContent=`Confirm and resolve · ${duration(q.minutes)}`;d.querySelector('[data-confirm-yes]').disabled=false;
    }catch(e){if(run===previewSelection&&d.open)d.querySelector('[data-confirm-error]').textContent=e.message;}
  }
  function draftKey(){return 'worldwalker.activity-draft.v1:'+String(APP.account?.id||'local')+':'+String(APP.state?.campaign_id||'');}
  function keepDraft(){try{sessionStorage.setItem(draftKey(),JSON.stringify({action:document.getElementById('action-input')?.value||'',plan:document.getElementById('time-plan')?.value||''}));}catch{}}
  function onState(){
    const time=document.getElementById('stat-time');if(time&&APP.state?._world_calendar)time.title=APP.state._world_calendar.note;
    try{const saved=JSON.parse(sessionStorage.getItem(draftKey())||'null');if(saved){for(const [key,id]of [['action','action-input'],['plan','time-plan']]){const el=document.getElementById(id);if(el&&!el.value)el.value=saved[key]||'';}if(!APP.state?.combat?.active)sessionStorage.removeItem(draftKey());}}catch{}
  }
  async function confirm(){
    if(!quote||resolving)return;
    resolving=true;setBusy(true);const q=quote;quote=null;keepDraft();
    const yes=dialog.querySelector('[data-confirm-yes]'),cancel=dialog.querySelector('[data-confirm-cancel]');yes.disabled=cancel.disabled=true;yes.textContent='Resolving…';
    try{
      const result=await apiPost('/api/adventures/resolve',{token:q.token,confirmed:true,request_id:crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`,expected_campaign:q.expected_campaign,expected_guard:q.expected_guard});
      dialog.close();appendStoryEntries(result.story||[],{focusNew:true});renderState(result.state);onState();
      document.getElementById('workspace-chronicle-tab')?.click();
      showToast(result.interrupted?`Paused: ${result.interruption_reason}`:`Activity resolved · ${duration(result.elapsed?.amount ?? q.minutes)}`,'notify');
      if(!result.state.combat?.active && selectedPlace)await showLocation(result.state.location,false);
    }catch(e){dialog.querySelector('[data-confirm-error]').textContent=e.message+' Nothing will be submitted again automatically. Close this window and use Retry to recover an uncertain result.';}
    finally{resolving=false;setBusy(false);cancel.disabled=false;yes.textContent='Review the activity again';yes.disabled=true;}
  }
  async function showAftermath(id){
    try{
      const data=await apiGet('/api/adventures/aftermath?story_id='+encodeURIComponent(id));
      document.getElementById('workspace-chronicle-tab')?.click();
      if(typeof setMobileView==='function'&&isMobileLayout())setMobileView('chronicle');
      const d=ensureDialog();quote=null;d.querySelector('#adventure-confirm-title').textContent='Recorded aftermath';d.querySelector('[data-confirm-body]').innerHTML=`<p>${escape(data.entry.world_time||'')}</p><article class="adventure-source">${escape(data.entry.text)}</article>`;
      d.querySelector('[data-confirm-error]').textContent='';d.querySelector('[data-confirm-yes]').disabled=true;d.querySelector('[data-confirm-yes]').textContent='Historical record';d.querySelector('[data-confirm-cancel]').textContent='Close';if(!d.open)d.showModal();
    }catch(e){showToast(e.message,'danger');}
  }
  function timeline(panel,data){
    const world=data.world||'Custom World',current=Number(data.canon_day??0),cal=data.calendar_view||WorldCalendar.profile(world,data.calendar_epoch,data.calendar_anchor_day);
    const rows=(data.canon_dependencies?.events||data.canon_event_tracker||data.canon_events||[]).slice().sort((a,b)=>(a.effective_day??a.day)-(b.effective_day??b.day));
    const interventions=new Map((data.canon_interventions?.active||[]).map(r=>[r.event_id,r]));
    panel.innerHTML=`<header class="canon-reference-head"><small>PLAYER REFERENCE · SPOILERS VISIBLE</small><h2>Canon timeline</h2><b>Current: ${escape(formatCalendarDate(world,current,data.calendar_epoch,data.calendar_anchor_day))}</b><p>${escape(cal.note||'')}</p><small>Opening this reference does not give NPCs future knowledge. Projected dates follow this campaign’s installed chronology; your actions can change events.</small></header>${interventions.size?`<section class="canon-target-summary"><b>Targeted interventions</b><p>${[...interventions.values()].map(r=>`${escape(r.title||r.event_id)}${r.location?` · ${escape(r.location)}`:''}`).join('<br>')}</p><small>The GM is instructed to preserve a fair route toward these minor events without teleporting you or granting NPC foreknowledge.</small></section>`:''}<div class="canon-controls"><label>Search events<input type="search" data-canon-search placeholder="Event, person or place"></label><label>Show<select data-canon-filter><option value="all">All canon events</option><option value="upcoming">Upcoming</option><option value="past">Past / current</option><option value="changed">Changed / prevented</option></select></label></div><div data-canon-list></div>`;
    const render=()=>{
      const query=panel.querySelector('[data-canon-search]').value.toLocaleLowerCase(),filter=panel.querySelector('[data-canon-filter]').value;
      const matches=rows.filter(e=>{const day=Number(e.effective_day??e.day);return (!query||`${e.title} ${e.summary} ${e.location}`.toLocaleLowerCase().includes(query)) && (filter==='all'||filter==='upcoming'&&day>current||filter==='past'&&day<=current||filter==='changed'&&['impossible','replaced','delayed','prevented','diverged','altered'].includes(e.status));});
      panel.querySelector('[data-canon-list]').innerHTML=matches.map(e=>{const day=Number(e.effective_day??e.day),offset=day-current;return `<article class="timeline-row ${escape(e.status||'likely')}"><div class="timeline-day">${escape(formatCalendarDate(world,day,data.calendar_epoch,data.calendar_anchor_day))}<small>${offset>0?`In ${offset} days`:offset===0?'Today':`${-offset} days ago`}</small></div><div><header><b>${escape(e.title)}</b><span class="canon-status">${escape(e.status||(offset<0?'historical':'projected'))}</span></header><small>${escape(e.location||'Location not specified')} · campaign projection</small><p>${escape(e.summary||'')}</p>${e.requires?.length?`<small>Depends on: ${e.requires.map(escape).join(' → ')}</small>`:''}${e.reason?`<p>${escape(e.reason)}</p>`:''}${e.replacement?`<p>Possible replacement: ${escape(e.replacement)}</p>`:''}<button type="button" data-canon-plan="${escape(e.title)}" data-canon-place="${escape(e.location||'')}" data-canon-date="${escape(formatCalendarDate(world,day,data.calendar_epoch,data.calendar_anchor_day))}">Plan around this event</button>${offset>0&&e.major===false&&!['impossible','replaced'].includes(e.status)?`<button type="button" class="${interventions.has(e.id)?'active':''}" data-canon-intervene="${escape(e.id)}" data-canon-intervene-action="${interventions.has(e.id)?'cancel':'target'}">${interventions.has(e.id)?'Stop targeting this minor event':'Intervene in this minor event'}</button>`:''}</div></article>`;}).join('')||'<p>No matching canon events.</p>';
      panel.querySelectorAll('[data-canon-plan]').forEach(b=>b.onclick=()=>{const input=document.getElementById('action-input');const line=`Prepare to investigate ${b.dataset.canonPlan}${b.dataset.canonPlace?' at '+b.dataset.canonPlace:''} before ${b.dataset.canonDate}.`;input.value=input.value.trim()?input.value+'\n'+line:line;closeModal('modal-journal');input.focus();showToast('Preparation added to your draft. No time has passed.','notify');});
      panel.querySelectorAll('[data-canon-intervene]').forEach(b=>b.onclick=async()=>{try{await apiPost('/api/canon-interventions',{action:b.dataset.canonInterveneAction,event_id:b.dataset.canonIntervene});showToast(b.dataset.canonInterveneAction==='target'?'Minor canon event targeted. The GM will preserve a fair intervention opportunity.':'Canon intervention target cleared.','notify');openJournal('timeline');}catch(e){showToast(e.message,'danger');}});
    };
    panel.querySelector('[data-canon-search]').oninput=render;panel.querySelector('[data-canon-filter]').onchange=render;render();
  }
  return Object.freeze({showLocation,cancelSelection,wireMap,preview,onState,timeline,duration});
})();
