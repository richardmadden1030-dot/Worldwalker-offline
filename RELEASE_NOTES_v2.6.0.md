# Worldwalker RPG 2.6.0

This release is intended for fresh campaigns and uses save schema 6.

## Major changes

- Added a pre-Advance difficult-action warning with the required d100 range,
  relevant bonuses, risk, and choices to roll normally, play Timing Clash,
  play Tactical Approach, or cancel and rewrite the plan.
- Added **Skip to next major event**. The simulation continues through routine
  developments and stops naturally at the first major personal or canon event.
- Added chapter memory, NPC/faction clocks, relationship summaries, campaign
  health diagnostics, progression tuning, lore-source management, quest
  objectives/branches, and an interactive route-planning world map.
- Expanded GM instructions for independent world motion, information fog,
  canon divergence, world-valid original abilities, concrete journey leads,
  and reproducible feats whose prerequisites are satisfied.
- Reworked Chronicle updates into readable narrative, significance, player
  knowledge, and next-pressure sections. Long entries scroll without clipping.
- Moment mode now resolves only the next meaningful beat and reliably retains
  every later queued action. New campaigns always reset to Moment mode.
- Default cloud pairing is GPT-5.6 Luna for the main GM and GPT-4o mini for
  background simulation. Existing user-selected models are preserved.
- Added a separate trusted-LAN Phone Host launcher and a responsive phone
  interface. The PC continues to own saves, music, and AI credentials.

## Verification

- 43 automated engine, API, progression, time, save, and UI regression tests.
- JavaScript syntax validation and Python bytecode compilation.
- Live browser playthroughs in Naruto and One Piece, including multiple queued
  actions, deferred Moment actions, both challenge minigames, next-event mode,
  quests, maps, lore/tuning/health panels, and Chronicle overflow checks.
