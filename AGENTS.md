# Worldwalker contributor instructions

## Publishing

Approved implementation updates go to `richardmadden1030-dot/worldwalker-rpg`,
branch `master`. Richard superseded the earlier dual-push instruction on
September 6, 2026: he will handle `Dexsidius/WorldWalkerRPG_Webapp` -> `web_prod`
himself. Do not retry, configure, or push to that repository without a new request.
Read the latest source tip before changes, preserve unrelated work, use non-force
writes, run relevant checks, and verify the actual resulting commit.
Never include credentials, API keys, player saves, or personal data in commits.

## Reliability and presentation

Preserve saves and freeform actions. Report gameplay changes from committed
state, not from prose guesses. A lost HTTP response does not prove a failed
turn: check its request receipt before replaying it. Keep IDs stable on retry.
Do not expose concealed skills, classes, NPC secrets, or request bookkeeping in
player-visible receipts or prompts. Suggested freeform actions remain editable proposals. Explicit location activity
buttons are the approved exception: show authoritative duration/cost, ask for
confirmation, then resolve exactly that time unless a declared interruption
pauses it. Never auto-run an activity on a preview or canceled confirmation. Keep the Chronicle and Map mounted when changing tabs.

## Windows distribution

When an executable is requested, build and verify a Windows package containing
that update, or provide a verified existing download with its limitations.
Do not present a source ZIP or older executable as the new build. Keep the
portable folder, including `_internal`, together. Publish previews separately
from stable releases unless promotion is explicitly requested.

## World dates and player reference

Use the fixed world-calendar profiles for displayed dates. Preserve canon event
IDs/offsets and explicit saved epochs. Never call a projected or conventional
date confirmed canon. The visible Canon timeline is a player reference and must
not alter NPC knowledge merely because it was viewed. Timed location actions
and objective bookkeeping are engine-owned, never narrator-authored patches.
