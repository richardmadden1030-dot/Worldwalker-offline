# Worldwalker Offline — Full Offline Build 0.5

Worldwalker Offline is a separate, model-free RPG built around the worlds and progression identities of Worldwalker. It requires **no OpenAI key, no local language model, no server, and no internet connection during play**.

This build is intentionally separate from the current online Worldwalker project.

## Start playing

- **Windows:** double-click `START_HERE.bat`
- **macOS/Linux:** open `index.html` directly, or use `START_HERE.command`
- Your campaign autosaves in browser local storage.
- Game Menu → **Export Save** creates a portable JSON save.

## The offline gameplay loop

**Choose a world and power path → explore locations → pursue contextual opportunities → train world-native disciplines → build relationships/companions → accept procedural quests → fight local encounters → discover hidden conditions → run expeditions → choose milestone rewards → watch factions and world pressure change → continue roleplaying.**

There is no free-text command box. The game surfaces actions that are actually legal and meaningful in the current state.

## World-native progression

Rank/standing and raw power are intentionally separate.

- **Naruto:** Shinobi Rank + Ninjutsu, Taijutsu, Genjutsu, Chakra Control, Willpower; bloodlines, Dōjutsu and Jinchūriki paths remain separate power systems.
- **One Piece:** World Reputation + Fighting Style, Observation/Armament/Conqueror's Haki, Devil Fruit Mastery and Crew Influence.
- **Hunter x Hunter:** Hunter Standing + Ten, Zetsu, Ren, Hatsu Mastery, Fieldcraft and conditioning.
- **Bleach:** Division Standing + Zanjutsu, Hakuda, Hohō, Kidō, Reiatsu Control and Zanpakutō Bond; Shikai/Bankai remain earned releases.
- **Jujutsu Kaisen:** Official Grade + Cursed Energy Control, Technique Mastery, Combat Skill, Barrier Arts and Jujutsu Standing; Innate Technique and Heavenly Restriction remain exclusive paths.
- **Overgeared:** literal Level/XP + Class, Combat, Production, Reputation/NPC Affinity and Guild development.
- **Solo Max-Level Newbie:** literal Level/XP + Combat, Skill, Copy, System and Tower development.
- **Reincarnated as a Slime:** Species Stage + Magicules, Skill Mastery, Control, Nation and Resistances; species/skill evolution remain separate milestones.
- **Custom World:** Standing + Power, Combat, Insight, Craft and Leadership.

## Major systems included

- Contextual action system with no required typing
- State-driven Storylet/Event Director
- Seven procedural quest archetypes in every world
- World-native progression and deterministic personalized power identities
- Persistent abilities, applications, transformations, releases and evolutions
- Local combat with range, resources, guards, movement, abilities, forms, companions and boss phases
- Relationships, relationship-gated help and active companions
- Exploration depth, materials, secrets and hidden conditions
- Shops, equippable gear and crafting with mechanical bonuses
- Persistent expeditions with scouting, hazards, elite encounters, camps and bosses
- Three-choice milestone rewards
- Faction standing/activity and local world-pressure simulation
- Interactive Atlas, Character, Journal and World surfaces
- Chronicle generated strictly from committed game facts
- Local autosave plus save export/import

## Offline guarantee

The static audit checks that the runtime contains no `fetch`, XHR, WebSocket, remote API endpoint, remote script/stylesheet, API key, or AI client. All runtime content is bundled locally.

## Testing

Run:

```bash
python tests/run_all.py
```

The final review suite covers all nine worlds, all 63 world×quest-archetype completion paths, every creation power path, every staged form/evolution reaching its conditions, combat, shops/equipment/crafting, exploration/secrets, rewards, expeditions, save migration, 9,000 randomized world actions, and real Chromium interaction at desktop/tablet/phone widths.

See `REVIEW_AND_TESTING.md` for the critical review and the known remaining limitations.
