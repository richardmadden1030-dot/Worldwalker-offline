# Worldwalker RPG v3.16.0

## World content quality gate

- Added one deterministic audit across all eight bundled worlds.
- The gate checks starts, atlas links, archetype equipment, named abilities,
  factions, progression rules, canon-character state, eras, timelines and
  opening guidance.
- Fixed the three default starts that lacked useful opening context.
- Renamed two unrelated Naruto returns that previously shared the same generic
  timeline title, making event dependencies and Chronicle references clear.
- All bundled worlds now pass the same ten-part release gate.

## Environment art identity

- Scene selection now tracks world, exact location, sublocation, setting,
  indoors/outdoors, time, weather, current activity and live combat state.
- Specific rooms and businesses outrank broad landmark art.
- Outdoor weather cannot replace known indoor scenes.
- Old combat logs and distant events cannot force battlefield art; only active
  combat does so.
- Scene context and selection reasoning are available in diagnostics.

## Automatic lore coverage

- Added opt-in periodic refresh for approved sources.
- Includes a verified starter source for every supported canon world.
- Fandom pages use the lighter MediaWiki API instead of ad-heavy page HTML.
- Uses ETag/Last-Modified caching and content hashes to avoid needless writes.
- Optional related-page discovery is same-site and strictly capped.
- Extraction, indexing, claim detection and authority ranking run locally.
- Routine refreshes make zero AI calls. Relevant conflicts are carried into an
  already-needed GM prompt instead of creating a separate summarization bill.

## Timeline, special-detail and portrait fixes

- Bleach dates now state their actual distance before or after the day Ichigo
  receives Soul Reaper powers instead of resetting every era to a vague Year 1.
- The one-year Bleach start is regression-tested to keep that event 365 days
  away, and opening narration is explicitly forbidden from pulling it forward.
- Skills, hidden classes, world-specific powers, Shikai and Bankai cards can be
  expanded to read their complete descriptions, limits and progression notes.
- Portrait effect or transformation changes keep the previous valid portrait
  visible until the replacement has loaded.
- Removed the portrait status and role banners from the top of the artwork;
  both now sit cleanly in the lower identity caption without covering art.
