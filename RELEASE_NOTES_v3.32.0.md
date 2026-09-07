# Worldwalker RPG v3.32.0

## Strategic political atlas

- Replaced independently painted territory blobs with one non-overlapping
  strategy layer.
- Only real faction borders are drawn. Adjacent land under one controller
  reads as a single continuous territory.
- Authored political boundaries remain supported, while ordinary map anchors
  receive clean generated borders.
- Story changes to `location_details.controlling_faction` now synchronize the
  matching political region and immediately change its shading.
- Direct territory transfers update both the region and its anchor location.
- Recently changed borders receive a temporary gold highlight; contested land
  retains a subtle hatch.
- Political labels, landmark priority, legend styling, map framing, and mobile
  atlas sizing were cleaned up for much better readability.

## Mobile time control

- Added amount and unit controls directly to the mobile Advance dock.
- Added a dedicated clock button beside Advance for the full Time Control
  modal.
- The full modal now lists queued actions and keeps them intact.
- An unqueued Action Chat draft is added before a detailed time skip begins, so
  changing time settings no longer requires retyping the plan.
- Detailed selections sync back to the compact controls after closing.

## Verification

- Desktop Naruto atlas checked in a real browser at normal size.
- Mobile time controls checked at 390 x 844, including changing a Moment to a
  seven-day skip, queuing an action, and reopening detailed controls without
  losing the action.
- Narrative ownership synchronization, direct transfers, authored geometry,
  shared-controller merging, JavaScript syntax, and the full automated suite
  are covered by tests.
