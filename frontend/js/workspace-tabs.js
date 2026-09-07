/* Full-height Map / Chronicle workspace. Presentation only; no API or save writes.
   Both panels stay in their original DOM parent and retain their dimensions.
   In particular, never reparent the live map iframe or rebuild the story feed. */
(() => {
  'use strict';
  const STORAGE_KEY = 'worldwalker.desktop-workspace.v1';
  // Match app.js:isMobileLayout, not the atlas's separate 800px toolbar rule.
  const DESKTOP_QUERY = '(min-width: 721px)';

  function init() {
    const center = document.querySelector('.col-center');
    const map = document.getElementById('living-map-main');
    const story = center?.querySelector('.story-card');
    const feed = document.getElementById('story-feed');
    if (!center || !map || !story || !feed || center.dataset.workspaceReady) return;
    if (map.parentElement !== center || story.parentElement !== center) return;

    // Keeping these scoped styles with their controller makes enhancement atomic:
    // a failed script request leaves the original, usable layout untouched.
    const style = document.createElement('style');
    style.id = 'workspace-tabs-style';
    style.textContent = `
      .workspace-tabs { display: none; }
      @media (min-width: 721px) {
        .col.col-center[data-workspace-ready] {
          display: grid !important;
          grid-template-columns: minmax(0, 1fr) !important;
          grid-template-rows: 52px minmax(0, 1fr) !important;
          gap: 8px; min-width: 0; min-height: 0 !important;
          height: 100%; overflow: hidden !important;
        }
        [data-workspace-ready] > .workspace-tabs {
          grid-area: 1 / 1; display: flex; align-items: center;
          min-width: 0; padding: 3px; gap: 10px;
          border: 1px solid var(--border, #3c5264); border-radius: 12px;
          background: var(--panel, #16202f);
          box-shadow: inset 0 1px 0 rgba(255,255,255,.06);
        }
        .workspace-tablist {
          position: relative; display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          width: min(100%, 340px); height: 44px; flex: 0 1 340px;
          border-radius: 8px; isolation: isolate;
        }
        .workspace-tab-indicator {
          position: absolute; inset: 0 auto 0 0; width: 50%; z-index: -1;
          border: 1px solid var(--accent, #c7a15c); border-radius: 8px;
          background: linear-gradient(120deg, rgba(var(--accent-rgb,199,161,92),.23), rgba(var(--accent-rgb,199,161,92),.06));
          box-shadow: inset 0 -2px 0 var(--accent, #c7a15c), 0 0 16px rgba(var(--accent-rgb,199,161,92),.10);
          transition: transform 280ms cubic-bezier(.2,.8,.2,1);
          pointer-events: none;
        }
        [data-workspace-view="map"] .workspace-tab-indicator { transform: translateX(100%); }
        .workspace-tablist > .workspace-tab {
          display: flex; align-items: center; justify-content: center; gap: 7px;
          min-width: 0; min-height: 44px; margin: 0; padding: 6px 9px;
          border: 0; border-radius: 8px; background: transparent;
          color: var(--sub, #a9b7c2); cursor: pointer;
          font: 700 12px/1.2 var(--font-body, system-ui); letter-spacing: .03em;
          transition: color 180ms ease;
        }
        .workspace-tablist > .workspace-tab[aria-selected="true"] { color: var(--text, #eef2f0); }
        .workspace-tablist > .workspace-tab:hover { color: var(--accent, #c7a15c); }
        .workspace-tablist > .workspace-tab:focus-visible { outline: 2px solid var(--accent, #c7a15c); outline-offset: -3px; }
        .workspace-tab svg { width: 17px; height: 17px; flex-shrink: 0; }
        .workspace-tab-badge {
          padding: 3px 4px; border-radius: 4px; background: var(--accent, #c7a15c);
          color: var(--bg, #0c0f1e); font: 800 8px/1 system-ui; letter-spacing: .04em;
        }
        .workspace-tab-badge[hidden] { display: none; }
        .workspace-tab-hint {
          display: none; margin-left: auto; padding-right: 9px;
          color: var(--sub, #a9b7c2); font: 11px/1.3 var(--font-body, system-ui);
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .col.col-center[data-workspace-ready] > .workspace-panel {
          grid-area: 2 / 1 !important; position: relative;
          width: 100%; height: 100% !important; min-width: 0;
          min-height: 0 !important; max-height: none !important;
          margin: 0 !important; flex: none !important; overflow: hidden;
          visibility: hidden; opacity: 0; pointer-events: none;
        }
        .col.col-center[data-workspace-ready] > .workspace-panel.is-workspace-active {
          visibility: visible; opacity: 1; pointer-events: auto;
        }
        [data-workspace-ready][data-workspace-animate] > .workspace-panel.is-workspace-active {
          animation: workspace-panel-reveal 300ms cubic-bezier(.2,.8,.2,1) both;
        }
        .col.col-center[data-workspace-ready] > .story-card.workspace-panel {
          display: flex !important; flex-direction: column;
        }
        .col.col-center[data-workspace-ready] > .living-map-main.workspace-panel {
          display: flex !important; flex-direction: column;
        }
        [data-workspace-ready] > .story-card > .story-head,
        [data-workspace-ready] > .story-card > .mobile-chronicle-tools { flex: 0 0 auto; }
        [data-workspace-ready] > .story-card > #story-feed {
          flex: 1 1 0 !important; height: auto !important; min-height: 0 !important;
          max-height: none !important; overflow-y: auto !important; overscroll-behavior: contain;
        }
        [data-workspace-ready] > .story-card > .suggestion-dock {
          flex: 0 0 auto; max-height: 25%; overflow-y: auto;
        }
        [data-workspace-ready] #living-map-main-body {
          height: 100%; min-height: 0 !important; max-height: none;
        }
        [data-workspace-ready] #living-map-main iframe { height: 100%; min-height: 0 !important; }
        [data-workspace-ready] #living-map-main .map-wrap { min-height: 0 !important; }
        .workspace-tab-status {
          position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
          overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
        }
      }
      @media (min-width: 1200px) { .workspace-tab-hint { display: block; } }
      @keyframes workspace-panel-reveal {
        from { opacity: .15; transform: translateX(var(--workspace-entry, 14px)) scale(.99); }
        to { opacity: 1; transform: translateX(0) scale(1); }
      }
      @media (prefers-reduced-motion: reduce) {
        .workspace-tab-indicator, .workspace-tablist > .workspace-tab { transition: none !important; }
        [data-workspace-ready][data-workspace-animate] > .workspace-panel.is-workspace-active { animation: none !important; }
      }
      body.mobile-low-data .workspace-tab-indicator, body.motion-off .workspace-tab-indicator { transition: none !important; }
      body.mobile-low-data [data-workspace-ready] > .workspace-panel, body.motion-off [data-workspace-ready] > .workspace-panel { animation: none !important; }
    `;
    document.head.append(style);

    if (!story.id) story.id = 'workspace-chronicle-panel';
    const panels = { chronicle: story, map };
    const keys = Object.keys(panels);
    const attributes = ['role', 'aria-labelledby', 'aria-hidden', 'tabindex', 'inert'];
    const originalAttributes = new Map(Object.values(panels).map(panel => [panel,
      Object.fromEntries(attributes.map(name => [name, panel.getAttribute(name)]))
    ]));
    const bar = document.createElement('nav');
    bar.className = 'workspace-tabs';
    bar.setAttribute('aria-label', 'Campaign workspace');
    bar.innerHTML = `
      <div class="workspace-tablist" role="tablist" aria-label="Chronicle or Map">
        <span class="workspace-tab-indicator" aria-hidden="true"></span>
        <button id="workspace-chronicle-tab" class="workspace-tab" type="button" role="tab" data-workspace-tab="chronicle">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="M3 4h5a4 4 0 0 1 4 4v13a4 4 0 0 0-4-3H3zM21 4h-5a4 4 0 0 0-4 4v13a4 4 0 0 1 4-3h5z"/></svg>
          <span>Chronicle</span><span class="workspace-tab-badge" hidden aria-hidden="true">NEW</span>
        </button>
        <button id="workspace-map-tab" class="workspace-tab" type="button" role="tab" data-workspace-tab="map">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2zM9 3v16M15 5v16"/></svg>
          <span>Living Map</span>
        </button>
      </div>
      <span class="workspace-tab-hint" aria-hidden="true">Your story, in focus</span>
      <span class="workspace-tab-status" role="status" aria-live="polite"></span>`;
    center.prepend(bar);
    const tabs = [...bar.querySelectorAll('[role="tab"]')];
    const badge = bar.querySelector('.workspace-tab-badge');
    const status = bar.querySelector('.workspace-tab-status');
    const hint = bar.querySelector('.workspace-tab-hint');
    const desktop = window.matchMedia(DESKTOP_QUERY);
    let view = 'chronicle';
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (keys.includes(saved)) view = saved;
    } catch (_) { /* Storage is optional in embedded/private browsers. */ }

    function markUnread(unread) {
      badge.hidden = !unread;
      tabs[0].setAttribute('aria-label', unread ? 'Chronicle — new updates' : 'Chronicle');
      status.textContent = unread ? 'New Chronicle updates are ready.' : '';
    }
    function apply() {
      center.dataset.workspaceView = view;
      center.style.setProperty('--workspace-entry', view === 'map' ? '14px' : '-14px');
      hint.textContent = view === 'map' ? 'Explore your living world' : 'Your story, in focus';
      for (const tab of tabs) {
        const key = tab.dataset.workspaceTab;
        const panel = panels[key];
        tab.setAttribute('aria-controls', panel.id);
        tab.setAttribute('aria-selected', String(key === view));
        tab.tabIndex = key === view ? 0 : -1;
        panel.classList.add('workspace-panel');
        panel.classList.toggle('is-workspace-active', key === view);
        if (desktop.matches) {
          panel.setAttribute('role', 'tabpanel');
          panel.setAttribute('aria-labelledby', tab.id);
          panel.setAttribute('aria-hidden', String(key !== view));
          panel.tabIndex = key === view ? 0 : -1;
          panel.toggleAttribute('inert', key !== view);
        } else {
          // The existing phone navigation exclusively owns mobile visibility.
          for (const [name, value] of Object.entries(originalAttributes.get(panel))) {
            if (value === null) panel.removeAttribute(name);
            else panel.setAttribute(name, value);
          }
        }
      }
      if (desktop.matches && view === 'chronicle') markUnread(false);
    }
    function select(next, focus = false) {
      if (!keys.includes(next) || !desktop.matches) return;
      const outgoing = panels[view];
      const moveFocus = focus || outgoing.contains(document.activeElement);
      if (next !== view) center.dataset.workspaceAnimate = 'true';
      view = next;
      // Transfer focus before hiding the outgoing panel from assistive tech.
      if (moveFocus) tabs.find(tab => tab.dataset.workspaceTab === view).focus({ preventScroll: true });
      apply();
      try { localStorage.setItem(STORAGE_KEY, view); } catch (_) { /* Optional. */ }
    }
    bar.addEventListener('click', event => {
      const tab = event.target.closest('[data-workspace-tab]');
      if (tab) select(tab.dataset.workspaceTab, true);
    });
    bar.addEventListener('keydown', event => {
      const index = tabs.indexOf(event.target);
      if (index < 0 || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 :
        (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      select(tabs[next].dataset.workspaceTab, true);
    });
    document.addEventListener('click', event => {
      if (!(event.target instanceof Element)) return;
      // Existing shortcuts still enter the map; do not swallow their handlers.
      if (event.target.closest('[data-journal="map"], #journal-tabs [data-tab="map"]')) select('map');
      if (event.target.closest('#btn-event-window-continue')) select('chronicle');
    }, true);

    // Preserve programmatic journal/advisor map navigation as well as clicks.
    const focusMap = window.focusApprovedLivingMap;
    if (typeof focusMap === 'function') {
      window.focusApprovedLivingMap = function (...args) {
        select('map');
        return focusMap.apply(this, args);
      };
    }

    // Compare content, not nodes: normal renders can rebuild identical entries.
    // A NEW flag is intentionally not a misleading count of DOM mutations.
    let signature = feed.textContent || '';
    let updateFrame = 0;
    new MutationObserver(() => {
      if (updateFrame) return;
      updateFrame = requestAnimationFrame(() => {
        updateFrame = 0;
        const next = feed.textContent || '';
        if (next && next !== signature && desktop.matches && view === 'map') markUnread(true);
        signature = next;
      });
    }).observe(feed, { childList: true, subtree: true, characterData: true });
    const onBreakpointChange = () => {
      delete center.dataset.workspaceAnimate;
      if (desktop.matches && keys.some(key => key !== view && panels[key].contains(document.activeElement))) {
        tabs.find(tab => tab.dataset.workspaceTab === view).focus({ preventScroll: true });
      }
      apply();
      if (!desktop.matches && bar.contains(document.activeElement)) {
        const mobileTab = document.querySelector('#mobile-bottom-nav [aria-selected="true"]');
        mobileTab?.focus({ preventScroll: true });
      }
    };
    if (desktop.addEventListener) desktop.addEventListener('change', onBreakpointChange);
    else desktop.addListener(onBreakpointChange);
    center.dataset.workspaceReady = 'true';
    apply();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
