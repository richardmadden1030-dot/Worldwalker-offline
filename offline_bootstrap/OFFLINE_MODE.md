# Worldwalker Offline Mode

This repository is **Worldwalker itself**, pinned to the 3.64 `web_prod` game and maintained separately from the online/AI version.

Offline Mode does not replace the Living Map, Chronicle, tactical combat, progression, powers/forms, relationships, organizations, property/economy, expeditions, or save schema. It replaces the free-text narrator loop with a structured activity browser over those same systems.

## Interaction model

The existing Action Deck becomes the Offline Activities menu. Choices are grouped like a life-sim menu rather than shown as one giant list:

- For You
- Activities
- People
- Training
- Travel
- Missions & Work
- Organization
- Property & Economy
- Combat
- World

Every resolving choice is revalidated by the server immediately before application. Living Adventures is the primary resolver, which means rest, training, travel, shops, local missions, expeditions, mastery paths, property actions, reputation pressure and world-conflict activities use Worldwalker's current local rules.

The free-text composer and AI Advance controls are hidden while Offline Mode is enabled. Tactical combat remains the same Worldwalker combat system rather than being auto-resolved.

## Save compatibility

`offline_mode` is a setting, not a different campaign schema. The campaign state remains Worldwalker's schema 21. The offline repo defaults the setting to `true`.
