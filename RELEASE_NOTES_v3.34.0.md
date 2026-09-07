# Worldwalker RPG v3.34.0

## Player-visible changes

- Reworked the political atlas with a curated faction palette, calmer territory washes, merged internal ownership borders, and clearer contested boundaries.
- Added an informational canon/major-event sheet that shows the event, the player's actual position, ordinary travel estimate, involvement, and why the simulation stopped. Decisions continue in the normal Chronicle.
- Replaced generic percentile styling with world-specific dice presentations for Naruto, One Piece, Bleach, Jujutsu Kaisen, Hunter x Hunter, Overgeared, Solo Max-Level Newbie, and Reincarnated as a Slime.
- Rebuilt possible-next-move suggestions as readable two-column cards on phone and desktop, including a persistent custom-approach card.
- Added an expandable Active Form panel beneath the portrait. It surfaces known bonuses, granted effects, risks, and a return-to-base control while preserving the base portrait.

## Reliability

- Major-event location and travel context is calculated locally from the campaign map, avoiding an extra AI call and preventing accidental teleportation in the notice.
- Returning to base form clears the active transformation portrait state and matching combat transformation buff without removing unrelated buffs.
- Existing territory changes and player-founded factions continue to feed the same native map ownership layer.
