# Worldwalker RPG v3.13.0

## Character creation and progression

- Background claims now change starting stats and resource pools in every built-in world. Exceptional descriptions such as immense spiritual pressure produce exceptional mechanics instead of cosmetic prose.
- Naruto now stores Kekkei Genkai and Dōjutsu as dedicated profiles with an identity, stage, abilities, limits, counters and growth path. Original, non-canon bloodlines are explicitly supported and must match the setting's established depth, versatility and power scale.
- The GM now generates new abilities at canon-relative quality across every world: distinctive mechanics, useful applications, real limitations and an appropriate growth ceiling.
- Broad competence is represented by stats rather than fake skills such as “Brawler Fundamentals.” Skill lists are reserved for actual named techniques, spells, jutsu, releases, forms, class features and recognized disciplines.
- Combat style is mechanically and narratively authoritative. A brawler defaults to fists, movement, grappling and body conditioning; learning a distant discipline such as swordsmanship needs instruction and substantially more practice.

## Reliability, lore and evaluation

- Fixed descriptive progression values such as an unmeasured Magicule Capacity causing a campaign crash.
- Added typed repair for malformed nested campaign fields and safer numeric normalization.
- Lore Sources can now refresh a public web page directly, with source metadata, size limits and private-network protections.
- Model evaluations now cover XP/title persistence, background-to-stat fidelity, original Dōjutsu quality, custom-world rules, combat-style continuity and turn causality.
- Test data is isolated from live settings, preventing local API configuration from leaking into automated tests.

## Dice presentation

- Important d100 checks now use physical percentile dice: one tens die and one ones die, with a dimensional tray, world-colored accents, rolling motion and the existing dice sound.
- The result remains easy to read as roll + bonus versus target on desktop and mobile.

## Added starts

- One Piece: Arlong Park, Whiskey Peak, Thriller Bark and Punk Hazard.
- Hunter x Hunter: Meteor City, NGL, Hunter Association HQ and Zevil Island.
- Naruto: Forest of Death, Land of Waves, Land of Rice Fields and Kannabi Bridge.
- Bleach: Kidō Honors, Field Practicum, Kidō Corps Candidate and Onmitsukidō Candidate variants for academy seniors or recent Soul Reaper graduates.
- Solo Max-Level Newbie: Floor 5 and Floor 10 starts with matching level and stat floors.
- Overgeared: Frontier, Saharan Empire and Northern Frontier.
- Reincarnated as a Slime: Falmuth, Thalion, Demon Lord's Domain and Dragon Peak.
- Custom World: Starting Region, Northern Reach, Western March, Eastern Reach and Southern Wilds.

No new map nodes or canon timeline dates were added in this release.

## Verification

- 471 automated tests pass.
- JavaScript syntax, Python bytecode compilation, desktop layout and mobile dice layout were verified.
