# Worldwalker RPG 3.6.4

## Friendlier action resolution

- D100 checks are now reserved for extremely difficult or seemingly
  impossible attempts, lethal undertakings, and genuine power-tier leaps.
- Routine politics, strategy, social actions, investigation, travel, crafting,
  ordinary combat, and focused training resolve without dice.
- Automatic success remains grounded: the intended feasible action succeeds,
  while NPC agency, reactions, costs, and downstream consequences still apply.
- Major power leaps use a visible manual d100. Success grants the leap with a
  concrete setting-valid narrative cause; failure retains substantial training
  foundation and explains what remains.

## Faster, visible training

- Training rates are substantially higher across every intensity.
- Specific daily or goal-focused practice receives an additional focus bonus.
- A month of ordinary focused training now creates a clearly visible change
  instead of a tiny incremental tick.
- System/XP worlds award twice the previous daily training XP before world and
  difficulty tuning.
- Lucky breakthroughs remain possible and multiply the already proportional
  training return.

## Event and combat flow

- Major/canon-event popups are now informational notices only. They no longer
  contain a separate chat, choices, or relocated combat controls.
- Closing an event notice returns to the normal Chronicle and Action Chat.
  The Chronicle already contains the complete event context and a next
  decision grounded in the character's distance, involvement, status, access,
  and the event's scale.
- Explicit player attacks and unavoidable incoming attacks begin structured
  combat immediately. A local fallback creates a valid combat state if a
  narrator model omits it.
- Major-event importance no longer forces a difficult roll by itself. Rolls
  remain reserved for genuinely extreme or seemingly impossible actions.
- Significant personal turning points and major world/canon events still stop
  the simulation naturally.

## Challenge continuation

- Timing Clash and Tactical Approach now offer **Play & Stop** or **Play &
  Continue Sim**.
- Play & Stop resolves the challenged result, pauses immediately afterward,
  and keeps later planned actions queued.
- Play & Continue Sim applies the same minigame result and continues toward
  the originally selected time boundary unless another legitimate major stop
  occurs.

## Mobile conversations

- Chats now use a phone-height layout with horizontally scrollable contacts
  and a full remaining-height conversation thread.
- The Advisor window is larger on desktop and nearly full-screen on phones.
- Advisor starters and follow-up suggestions scroll horizontally on mobile
  instead of shrinking the readable message history.

## One warning per dangerous scenario

- A dangerous confrontation now records that its initial warning was
  accepted. Later difficult actions in that same scene continue without
  reopening the blocking warning — their d100 checks and consequences still
  resolve normally; only the repeated confirmation was removed.
- A new action with a credible chance of death always receives a fresh
  lethal warning.
- Accepting a difficult warning that already states the danger may be fatal
  also counts as lethal confirmation, preventing two consecutive
  confirmation popups for the same action.
- The acknowledgement clears when combat ends, the player leaves, the
  confrontation concludes, or the scene becomes stale.

## Immediate combat

- Deliberately attacking starts structured combat immediately.
- A committed incoming attack starts combat immediately without another
  negotiation or intervention prompt.
- Detection now covers additional physical and ability-based phrasing
  including lunges, weapon swings, gunfire, projectiles, spells, blasts,
  tackles, grapples, and targeted techniques.
- Negotiation, retreat, or de-escalation remains available while violence
  has not actually begun.

## Verification

- 363 automated regression and feature tests pass, including new coverage
  for warning persistence, lethal escalation, combat entry, negotiation,
  combat cleanup, and frontend popup suppression.
- A normal month-long focused Naruto training test raises Ninjutsu from 30
  to 50 without a breakthrough.
- Routine training, negotiation, strategy, and an ordinary fight generate no
  checks; elite opposition and a new Haki awakening still generate d100
  checks.
