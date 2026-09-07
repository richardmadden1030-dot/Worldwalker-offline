# World content audit — v3.16.0

All eight bundled worlds pass the shared ten-part release gate. A pass means
the content is internally connected and mechanically usable; it does not mean
every world has the same amount of canon material.

| World | Starts | Loadouts | Canon starts | Eras | Timeline events | Result |
|---|---:|---:|---:|---:|---:|---|
| One Piece | 35 | 8 | 2 | 5 | 40 | Pass |
| Hunter x Hunter | 10 | 9 | 2 | 4 | 31 | Pass |
| Naruto | 11 | 11 | 4 | 6 | 52 | Pass |
| Solo Max-Level Newbie | 4 | 8 | 1 | 3 | 12 | Pass |
| Overgeared | 10 | 8 | 1 | 3 | 14 | Pass |
| Reincarnated as a Slime | 10 | 8 | 1 | 4 | 25 | Pass |
| Bleach | 6 | 8 | 1 | 3 | 27 | Pass |
| Custom World | 5 | 6 | 0 | player-authored | 1 seed | Pass |

## Findings

- One Piece has the broadest location choice. Naruto has the densest timeline
  and the most canon-character coverage.
- Hunter x Hunter and Reincarnated as a Slime are structurally complete and
  sit in the middle for authored breadth.
- Bleach is narrower by design but unusually deep in its specialized systems,
  equipment, Kido, release progression and timeline coverage.
- Solo Max-Level Newbie and Overgeared have the smallest authored timelines,
  but their persistent progression subsystems carry more of their simulation.
- Custom World correctly relies on player-authored chronology and has no canon
  character requirement.

## Recommended next content work

1. Add more playable canon starts to the four worlds that currently have only
   one, when a specific player-requested scenario justifies the work.
2. Add landmark artwork for high-use starts that currently fall back to a
   biome image; prioritize by real campaign telemetry rather than asset count.
3. Grow approved lore-source catalogs gradually and keep discovery capped.
   Whole-site crawling would add noise, spoiler risk and maintenance burden.
4. Add source-specific spoiler-era metadata as imported lore coverage grows so
   later facts cannot leak into early campaigns.
