(() => {
  'use strict';

  let activeId = '';
  let submitting = false;
  const OVERLAY_ID = 'team-membership-choice-overlay';

  const text = value => String(value ?? '').trim();
  const esc = value => text(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  const pending = state => (Array.isArray(state?.team_membership_offers) ? state.team_membership_offers : [])
    .filter(row => row && row.status === 'pending' && row.requires_player_choice !== false && text(row.id));

  function establishedGroups(state) {
    const names = new Map();
    const remember = value => {
      const name = text(value);
      if (name) names.set(name.toLocaleLowerCase(), name);
    };
    (Array.isArray(state?._organization_roster?.groups) ? state._organization_roster.groups : []).forEach(group => remember(group?.name));
    if (state?.organizations && typeof state.organizations === 'object') Object.values(state.organizations).forEach(group => remember(group?.name));
    if (state?.faction_rosters && typeof state.faction_rosters === 'object') Object.keys(state.faction_rosters).forEach(remember);
    return [...names.values()].sort((a, b) => b.length - a.length || a.localeCompare(b));
  }

  function directJoinTarget(action, state) {
    const raw = text(action);
    if (!raw) return '';
    const lower = raw.toLocaleLowerCase();
    if (/\b(?:refuse|decline|reject|do\s+not|don't|won't|will\s+not|never)\b.{0,35}\bjoin\b/i.test(raw)) return '';
    // Only preflight an explicit request for the *player* to join. Sentences
    // such as "I want Kakuzu to join the Akatsuki" are NPC recruitment
    // attempts and must wait for the GM/world to establish that NPC's
    // willingness before the separate recruitment offer is allowed.
    const playerJoin = /^(?:\s*)(?:join|apply\s+to\s+join|ask\s+to\s+join|request\s+to\s+join|become\s+(?:an?\s+)?member\s+of)\b/i.test(raw)
      || /\b(?:i|we)\s+(?:(?:really\s+)?(?:want|wish|plan|intend|hope|try|attempt|apply|ask|request|would\s+like)\s+to\s+)?(?:officially\s+)?join\b/i.test(raw)
      || /\b(?:i|we)\s+(?:want|wish|would\s+like|plan|intend|hope)\s+to\s+become\s+(?:an?\s+)?member\s+of\b/i.test(raw)
      || /\bi(?:'d| would)\s+like\s+to\s+(?:officially\s+)?join\b/i.test(raw)
      || /\b(?:can|may|could)\s+i\s+(?:officially\s+)?join\b/i.test(raw)
      || /\bi\s+apply\s+for\s+membership\s+in\b/i.test(raw)
      || /\b(?:let|allow)\s+me\s+(?:officially\s+)?join\b/i.test(raw);
    if (!playerJoin) return '';
    return establishedGroups(state).find(name => lower.includes(name.toLocaleLowerCase())) || '';
  }

  function ensureStyle() {
    if (document.getElementById('team-membership-choice-style')) return;
    const style = document.createElement('style');
    style.id = 'team-membership-choice-style';
    style.textContent = `
      .team-membership-choice{position:fixed;inset:0;z-index:10030;display:grid;place-items:center;padding:24px;background:rgba(3,7,14,.76);backdrop-filter:blur(8px)}
      .team-membership-card{width:min(620px,calc(100vw - 32px));max-height:min(780px,calc(100vh - 40px));overflow:auto;border:1px solid color-mix(in srgb,var(--accent,#d7a452) 48%,#31506a);border-radius:22px;background:linear-gradient(165deg,rgba(19,30,44,.98),rgba(8,15,25,.99));box-shadow:0 28px 90px rgba(0,0,0,.55);padding:26px}
      .team-membership-kicker{font-size:.73rem;letter-spacing:.16em;text-transform:uppercase;color:var(--accent,#e7ad54);font-weight:800}
      .team-membership-card h2{margin:7px 0 8px;font-size:1.55rem;color:#f5eee3}
      .team-membership-card p{color:#c9d5df;line-height:1.55;margin:.55rem 0}
      .team-membership-reason{padding:12px 14px;border-radius:14px;background:rgba(111,157,190,.09);border:1px solid rgba(111,157,190,.2)}
      .team-membership-roster{display:grid;gap:7px;margin:14px 0;padding:0;list-style:none}
      .team-membership-roster li{display:flex;justify-content:space-between;gap:16px;padding:9px 11px;border-radius:10px;background:rgba(255,255,255,.045);color:#e4ebf0}
      .team-membership-roster small{color:#9fb2c1}
      .team-membership-note{font-size:.82rem;color:#93a7b7!important}
      .team-membership-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:20px}
      .team-membership-actions button{min-height:48px;border-radius:12px;font-weight:800;letter-spacing:.025em;cursor:pointer}
      .team-membership-actions .accept{border:1px solid color-mix(in srgb,var(--accent,#d7a452) 70%,white);background:color-mix(in srgb,var(--accent,#d7a452) 72%,#1c2a35);color:#fff}
      .team-membership-actions .decline{border:1px solid #466174;background:#172533;color:#dce8ef}
      .team-membership-actions button:disabled{opacity:.5;cursor:wait}
      @media(max-width:520px){.team-membership-choice{padding:12px}.team-membership-card{padding:20px}.team-membership-actions{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function presentation(offer, state) {
    const kind = text(offer.kind);
    if (kind === 'recruit') return {
      kicker: 'Recruitment decision',
      title: `Recruit ${text(offer.person) || 'this character'}?`,
      lead: `${text(offer.person) || 'This character'} can now be made an official member of ${text(offer.group) || 'your group'}.`,
      yes: 'YES — RECRUIT', no: 'NO — DO NOT RECRUIT',
    };
    if (kind === 'naruto_squad') return {
      kicker: 'Ninja squad assignment',
      title: text(offer.title) || `Join ${text(offer.group)}?`,
      lead: text(offer.prompt) || `Konoha has assigned ${text(state?.name) || 'you'} to ${text(offer.group)}.`,
      yes: 'YES — JOIN THIS SQUAD', no: 'NO — DECLINE ASSIGNMENT',
    };
    return {
      kicker: 'Team membership decision',
      title: `Join ${text(offer.group) || 'this team'}?`,
      lead: `The campaign has reached a point where ${text(state?.name) || 'your character'} can officially join ${text(offer.group) || 'this team'}.`,
      yes: 'YES — JOIN', no: 'NO — DECLINE',
    };
  }

  async function decide(offer, accepted) {
    if (submitting) return;
    submitting = true;
    const overlay = document.getElementById(OVERLAY_ID);
    overlay?.querySelectorAll('button').forEach(button => { button.disabled = true; });
    try {
      const result = await apiPost('/api/campaign/correct', {
        type: 'organization_membership_choice',
        target: offer.id,
        value: accepted ? 'accept' : 'decline',
        explanation: accepted
          ? `Player confirmed the official membership decision for ${text(offer.person) || APP.state?.name || 'the player'} and ${text(offer.group)}.`
          : `Player declined the official membership decision for ${text(offer.person) || APP.state?.name || 'the player'} and ${text(offer.group)}.`,
      });
      overlay?.remove(); activeId = '';
      if (result?.state) renderState(result.state);
      if (Array.isArray(result?.story)) appendStoryEntries(result.story);
      showToast(accepted ? `Membership confirmed: ${text(offer.group)}.` : `Membership declined: ${text(offer.group)}.`, accepted ? 'notify' : 'system');
    } catch (error) {
      showToast(error?.message || 'The membership decision could not be saved.', 'danger');
      overlay?.querySelectorAll('button').forEach(button => { button.disabled = false; });
    } finally {
      submitting = false;
    }
  }

  function renderOffer(offer, state, decisionHandler = decide) {
    ensureStyle();
    document.getElementById(OVERLAY_ID)?.remove();
    const copy = presentation(offer, state);
    const roster = Array.isArray(offer.members) ? offer.members.filter(row => row && text(row.name)) : [];
    const rosterHtml = roster.length ? `<ul class="team-membership-roster">${roster.map(row =>
      `<li><span>${esc(row.name)}${text(row.name) === text(state?.name) ? ' <small>(You)</small>' : ''}</span><small>${esc(row.position || 'Member')}</small></li>`).join('')}</ul>` : '';
    const leader = text(offer.leader) && !roster.some(row => text(row.name) === text(offer.leader))
      ? `<p><b>Leader:</b> ${esc(offer.leader)}</p>` : '';
    const overlay = document.createElement('div');
    overlay.id = OVERLAY_ID;
    overlay.className = 'team-membership-choice';
    overlay.setAttribute('role', 'dialog'); overlay.setAttribute('aria-modal', 'true'); overlay.setAttribute('aria-labelledby', 'team-membership-title');
    overlay.innerHTML = `<section class="team-membership-card">
      <div class="team-membership-kicker">${esc(copy.kicker)}</div>
      <h2 id="team-membership-title">${esc(copy.title)}</h2>
      <p>${esc(copy.lead)}</p>${leader}${rosterHtml}
      <p class="team-membership-reason">${esc(offer.reason || 'The campaign reached an official membership decision.')}</p>
      <p class="team-membership-note">This is an engine-owned roster decision. The GM can create the opportunity, but cannot add or remove your official membership without this confirmation.</p>
      <div class="team-membership-actions"><button type="button" class="accept">${esc(copy.yes)}</button><button type="button" class="decline">${esc(copy.no)}</button></div>
    </section>`;
    overlay.querySelector('.accept').addEventListener('click', () => decisionHandler(offer, true));
    overlay.querySelector('.decline').addEventListener('click', () => decisionHandler(offer, false));
    document.body.appendChild(overlay);
    activeId = offer.id;
    requestAnimationFrame(() => overlay.querySelector('.accept')?.focus());
  }

  function preflightJoin(action, state) {
    const group = directJoinTarget(action, state);
    if (!group) return Promise.resolve({ handled: false, accepted: false });
    const outstanding = pending(state);
    if (outstanding.length) {
      handle(state);
      showToast('Resolve the current team membership decision before starting another one.', 'system');
      return Promise.resolve({ handled: true, accepted: false });
    }
    const offer = {
      id: `direct-local-${Date.now()}`, kind: 'join_team', group, person: text(state?.name), direct_action: true,
      reason: `You explicitly asked to join ${group}. Confirming Yes makes this the engine-owned official team membership immediately; the queued action will still let the GM narrate the scene.`,
      status: 'pending', requires_player_choice: true,
    };
    return new Promise(resolve => {
      renderOffer(offer, state, async (_offer, accepted) => {
        if (submitting) return;
        submitting = true;
        const overlay = document.getElementById(OVERLAY_ID);
        overlay?.querySelectorAll('button').forEach(button => { button.disabled = true; });
        try {
          const result = await apiPost('/api/campaign/correct', {
            type: 'organization_direct_join', target: group, value: accepted ? 'accept' : 'decline',
            explanation: accepted
              ? `Player explicitly confirmed joining ${group} from a typed action.`
              : `Player declined joining ${group} after the typed-action membership prompt.`,
          });
          overlay?.remove(); activeId = '';
          if (result?.state) renderState(result.state);
          if (Array.isArray(result?.story)) appendStoryEntries(result.story);
          showToast(accepted ? `Official team joined: ${group}.` : `You did not join ${group}.`, accepted ? 'notify' : 'system');
          resolve({ handled: true, accepted });
        } catch (error) {
          showToast(error?.message || 'The team membership decision could not be saved.', 'danger');
          overlay?.querySelectorAll('button').forEach(button => { button.disabled = false; });
        } finally {
          submitting = false;
        }
      });
    });
  }

  function handle(state) {
    const rows = pending(state);
    const current = rows[0];
    if (!current) {
      document.getElementById(OVERLAY_ID)?.remove(); activeId = ''; return;
    }
    if (activeId === current.id && document.getElementById(OVERLAY_ID)) return;
    renderOffer(current, state);
  }

  window.WorldwalkerTeamMembership = Object.freeze({ handle, preflightJoin, directJoinTarget });
})();
