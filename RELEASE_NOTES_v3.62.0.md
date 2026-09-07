# v3.62.0 — Living Relationships and Rivalries

- NPC follow-ups can use specific recorded shared experiences: help, promises, victories, disrespect and quiet time. They use the existing chat UI; no new menus.
- Removed the local goal-pasting message and the generic Chronicle instruction saying an NPC should initiate a conversation.
- The normal GM turn can compose one grounded follow-up. Local eligibility, delivery checks, a three-turn cooldown and saved experience fingerprints prevent repeated prompts. A contact dying or becoming unreachable during the turn cannot send it.
- Meaningful relationship reasons are remembered without requiring a numeric or attitude change. Repeated identical reasons no longer fill the memory chain.
- Offers remain offers: they do not automatically start training, spend time, grant rewards or recruit anyone. Quiet gratitude and companionship need not introduce a problem.
- Rival guidance uses existing nemesis flags and staged world plans. Motives, resources, knowledge and resolved outcomes govern rival activity; there is no new stat scaling or automatic sabotage.
- Shared keywords alone no longer make a contact learn private news. Dead or unavailable NPCs are excluded from the local/background contact paths.
- Existing saves use their existing shared-memory chains. No campaign restart or automatic rewrite of old conversations is required.

## Scope and cost

Local candidate selection and validation make no AI requests. In-character follow-up writing uses the existing main-turn request, with at most four bounded candidates. Existing optional background-message settings are unchanged. No new offline dialogue library is added.

These checks validate structured eligibility and repeat prevention, not arbitrary prose semantics. The GM still judges personality, offer feasibility and lore-appropriate delivery timing. Existing world plans remain responsible for persistent rival projects; this is not a replacement rival simulation.
