const CACHE = "worldwalker-v3640-membership-truth-1";
const SHELL = [
  "/js/world-calendar.js?v=3.64.0-membership-truth-1", "/js/living-adventures.js?v=3.64.0-membership-truth-1",
  "/css/living-adventures.css?v=3.64.0-membership-truth-1",
  "/js/api-client.js?v=3.64.0-membership-truth-1", "/js/roster-sync.js?v=3.64.0-membership-truth-1", "/js/team-membership.js?v=3.64.0-membership-truth-1", "/js/action-deck.js?v=3.64.0-membership-truth-1",
  "/css/compact-workspace.css?v=3.64.0-membership-truth-1",
  "/js/turn-feedback.js?v=3.64.0-membership-truth-1", "/css/turn-feedback.css?v=3.64.0-membership-truth-1",
  "/", "/css/style.css?v=3.64.0-membership-truth-1", "/js/app.js?v=3.64.0-membership-truth-1", "/css/world-atlas.css?v=3.64.0-membership-truth-1&revision=2", "/js/world-atlas.js?v=3.64.0-membership-truth-1", "/js/workspace-tabs.js?v=3.64.0-membership-truth-1", "/manifest.webmanifest",
  "/assets/branding/worldwalker-emblem.png", "/cursors/naruto-kunai.svg", "/cursors/naruto-shuriken.svg",
  "/cursors/bleach-zanpakuto.svg", "/cursors/jjk-sukuna-finger.svg", "/cursors/one-piece-strawhat-jolly-roger.svg", "/fonts/nova-square.ttf"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith("/music/") || url.pathname.startsWith("/portrait-cache/")) return;
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(caches.open(CACHE).then(async (cache) => {
      const cached = await cache.match(event.request);
      const refresh = fetch(event.request).then((response) => {
        const assetCopy = response.ok ? response.clone() : null;
        if (assetCopy) cache.put(event.request, assetCopy);
        return response;
      }).catch(() => cached);
      return cached || refresh;
    }));
    return;
  }
  event.respondWith(fetch(event.request).then((response) => {
    // The clone MUST happen synchronously, in this same tick, before the
    // response is handed back below — once `caches.open()`'s promise settles
    // (a later tick), the page may already have started reading this same
    // response's body, which locks it and makes clone() throw "Response
    // body is already used". That race was silently falling back to
    // whatever stale copy sat in the old cache, which is why style/JS
    // updates could appear to not take effect after an update.
    const copy = response.ok ? response.clone() : null;
    if (copy) caches.open(CACHE).then((cache) => cache.put(event.request, copy));
    return response;
  }).catch(() => caches.match(event.request)));
});
