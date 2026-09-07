# Full-height Chronicle / Living Map workspace

The desktop center column now has Chronicle and Living Map tabs instead of
stacking the map above a compressed story panel. Chronicle is selected on first
use; the last selected desktop tab is remembered on the device when storage is
available. The existing character and Action Chat rails are unchanged.

The selector slides between tabs and the incoming panel has a short directional
reveal. The OS reduced-motion preference disables these effects. New story
content received while the desktop map is open marks Chronicle as NEW without
interrupting map browsing. Existing Map shortcuts and the event acknowledgement
continue to reveal the appropriate panel.

Both panels remain in their original DOM parent, with full workspace dimensions
even when hidden. Switching does not reset the map iframe, camera, Chronicle
scroll position, or action draft. The inactive desktop panel is inert and hidden
from assistive technology. The tabs support Left/Right, Home/End and normal Tab
navigation. At 720px and below, the existing mobile bottom navigation retains
control and desktop-only ARIA/inert attributes are restored to their originals.

## Integration

- `frontend/js/workspace-tabs.js`: self-contained, idempotent presentation layer.
  Scoped CSS travels with the controller so a load failure does not hide panels.
- `frontend/js/world-atlas.js`: existing renderer is unchanged; a small optional
  loader at the end includes the workspace module in both desktop/browser shells.
- `frontend/sw.js`: new shell-cache revision and workspace script precache entry.
- No changes to backend logic, AI requests, save data, map geography or story art.

## Checks

`node --check frontend/js/workspace-tabs.js`

`node --check frontend/js/world-atlas.js`

Optional browser tests (pytest + Playwright + Chromium required):

`python -m pytest tools/check_workspace_tabs.py -q`

These isolated, offline browser regressions use the production controller and
atlas renderer, a reduced DOM and representative layout rules. They exercise
scrolling to the final entry, repeated switching, iframe identity/camera state,
unchanged drafts, unread notifications, keyboard focus, stored preferences,
blocked storage, duplicate initialization, reduced motion and 390/720/721/800/
801/1024/1920px breakpoint transitions. They do not boot the complete Flask app,
exercise the actual map prototype, check HTTP/service-worker loading, or run a
live AI campaign. A normal desktop/phone gameplay smoke test remains advisable.

## Receiving the update

Update the source checkout, restart the running game/server, then refresh the
browser. A packaged executable must be rebuilt to include the changed frontend;
changing the GitHub source does not modify an already-installed executable.
