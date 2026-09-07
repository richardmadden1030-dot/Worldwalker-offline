# Worldwalker RPG v3.18.1

## Proximity-aware multiplayer Chronicles

- Each player now receives a separate Chronicle based on what their character can actually witness or plausibly learn.
- Local and private scenes remain hidden from distant characters; co-located characters share nearby scenes.
- Messages, reports, rumors and broadcasts can carry information across distance without revealing unrelated private context.
- Major-event interruptions and prompts are delivered only to the involved player when the characters are separated.
- The GM now returns explicit event location, information scope, delivery channel and audience metadata for every multiplayer update.
- A deterministic proximity fallback protects local and older AI models that omit audience metadata.
- Each player's filtered Chronicle and most recent result are stored separately in SQLite and survive refreshes and server restarts.
- Chronicle cards are marked **Nearby**, **Reported**, or **Shared** so players know how their character received the information.

## Verification

- Added tests for separated local scenes, shared broadcasts, distant reports, co-located scenes, personalized round results and Chronicle persistence after a store restart.
- Passed the complete automated regression suite.
