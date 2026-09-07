# Worldwalker RPG v3.46.0

## What players will notice

- **Short story-like chapters.** New recaps target 70–110 words about what you actually did, with a brief title. For example: restoring a clinic, securing medicine and developing Water Release through winter. The popup no longer repeats long decision/stat lists; the Journal retains an expandable detailed record. Old chapters get a concise local display without erasing their full memory.
- **Faithful group orders.** “Tell my guards to protect the children” covers known subordinate guards. “Have them continue” can refer to that recent group; ambiguous references do not pick a random NPC. Friendly NPCs do not automatically become subordinates.
- **Connected memory.** Asking about an orphanage can retrieve its caretaker, funding promise and completed construction together, without injecting the whole campaign history.
- **Relevant evidence.** A reaction or refusal must cite a related fact, not merely an existing fact. Suspicions cannot justify a claim marked as confirmed.
- **Lasting accomplishments.** Completed quests, projects and promises are remembered as settled. Reopening the same problem requires a new relevant cause; ordinary beneficial callbacks need no new crisis or repeated reward.
- **Fewer unnecessary repairs.** Mentioning Bankai, discussing future mastery or describing another character's awakening is distinguished from an actual player acquisition.
- **Safer turn recovery.** Failed turn checkpoints retain dice and response stages. Retry reuses matching work and validates repaired output before committing. Request IDs prevent the same successful request from applying twice within the running server session. Campaign changes invalidate stale work.
- **Inline corrections with previews.** Narrative Chronicle entries offer “Correct this.” Review the proposed fact and mechanical before/after changes before applying; a stale preview must be refreshed. Skill corrections keep the existing skill's metadata.
- **Long-running regression scenarios.** Multi-year local calendar/save/reload checks cover all nine worlds, including retired/deceased NPCs, learned skills, completed work and chapter length. Small live-GM samples separately check group commands and narrative recap quality.

## Compatibility and cost

Validation: 870 automated tests and 73 subtests passed. Phone-sized browser checks verified interrupted-turn retry, the chapter popup, legacy Journal recaps, and correction preview/apply; desktop layout had no horizontal overflow. Both packaged EXEs passed their self-tests, including Phone-Host LAN mode. These checks used isolated fixtures, not player saves.

Existing saves work; no new campaign is required. Original Chronicle text and full chapter continuity records remain intact. Retrieval, evidence filtering, closure checks and extractive recaps run locally. When a chapter is due, its optional prose summary is requested with the existing turn response—not a separate normal-gameplay AI call. Bounded additional context and output may modestly increase those chapter turns' tokens. Invalid outputs may still need one repair.

Two recorded live sample calls used 2,377 input and 519 output tokens; the app estimated $0.00110. These are narrow tests, not a forecast of a complete campaign's cost or a claim of exhaustive live playtesting.

Windows and Phone-Host ZIPs include the same game update and all 11 currently bundled Bleach/Naruto music tracks. The separate offline prototype is unchanged. Hosted sites must redeploy/restart the updated code before these changes appear there.
