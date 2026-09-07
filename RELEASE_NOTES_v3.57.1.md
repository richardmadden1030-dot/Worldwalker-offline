# Worldwalker RPG v3.57.1 — The Living Map Arrives

This corrective release integrates the approved Living Map renderer. The new
high-resolution atlases from v3.57.0 remain, but the old Journal map and its
blob-like procedural territory shading are no longer the player-facing map.

## Player-visible changes

- Desktop uses the approved character/map/inspector composition and expands the
  map to fill all unused space between its panels.
- Political control uses soft influence washes that preserve the illustrated map.
- Political, Danger, Relationships, and Events modes each show a focused layer.
- Player, travel, event, and eligible relationship markers animate on the map.
- Individuals are positioned only for meaningful ties, party/team/org membership,
  or established companion, mentor, or nemesis status.
- Mobile opens Map as a dedicated bottom-navigation view with touch pan and zoom.
- Bleach retains separate Soul Society, World of the Living, Hueco Mundo, Royal
  Realm, and Hell maps with current-realm identification.
- The service-worker cache version changed so phones cannot silently retain the
  old renderer after updating.
