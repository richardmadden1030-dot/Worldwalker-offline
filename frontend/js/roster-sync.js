(() => {
  'use strict';

  function text(value) { return String(value ?? '').trim(); }
  function clone(value) {
    try { return structuredClone(value); }
    catch (_) { return JSON.parse(JSON.stringify(value ?? {})); }
  }

  /**
   * Membership is resolved by backend/organizations.py.
   *
   * Older builds tried to "help" here by re-inferencing membership from
   * contacts, relationships, faction_rosters and Chronicle prose. That made
   * the browser a second game-state interpreter and could turn places or
   * factions (for example Amegakure/Akatsuki) into people. The browser now
   * performs presentation-only normalization and never adds/removes members.
   */
  function reconcile(roster, state) {
    const out = clone(roster && typeof roster === 'object' ? roster : { groups: [] });
    out.groups = Array.isArray(out.groups) ? out.groups : [];
    for (const group of out.groups) {
      group.members = Array.isArray(group.members) ? group.members.filter(row => row && typeof row === 'object' && text(row.name)) : [];
      group.candidates = Array.isArray(group.candidates) ? group.candidates.filter(row => row && typeof row === 'object' && text(row.name)) : [];
    }
    const official = text(state?.official_party_group_id || out.official_group_id);
    if (official) out.groups.sort((a, b) => Number(text(a?.id) !== official) - Number(text(b?.id) !== official) || text(a?.name).localeCompare(text(b?.name)));
    out.official_group_id = official || out.official_group_id || '';
    if (out.groups.length === 1) out.label = out.groups[0].type || out.label || 'Group';
    else if (official && out.groups[0]?.id === official) out.label = out.groups[0].type || out.label || 'Group';
    out.source = out.source || 'canonical_organization_ledger_v2';
    return out;
  }

  window.WorldwalkerRosterSync = Object.freeze({ reconcile });
})();
