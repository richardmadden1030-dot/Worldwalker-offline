# Worldwalker RPG 3.6.0

## More directed, less bloated simulation

- A deterministic Campaign Director keeps the current goal, next obstacle,
  unresolved characters, nearby opportunities, and approaching canon pressure
  visible and coherent without another AI request.
- Recurring NPCs retain goals, loyalties, fears, private secrets, opinion of
  the player, and last-known location. Their private secrets are not exposed
  in the player-facing relationship view.
- Optional relationship scenes surface periodically when a relevant character
  is nearby; they never interrupt or force the player's choice.
- Active quests receive meaningful route choices and consequences, with later
  routes able to unlock from progress.
- Failed checks now leave a setback, clue, partial insight, or concrete new
  approach instead of simply stopping the story.

## Clearer planning and consequences

- Queued actions can be edited and moved up or down before Advance.
- Multi-day plans show approximate day ranges and a simple risk label.
- The queue warns when an upcoming canon event could interrupt the requested
  time period.
- Important state changes show a concise “Why things changed” explanation tied
  to the relevant action and d100 result.
- Sustained training produces a readable proportional report of time invested,
  gains, breakthroughs, and unresolved weaknesses.

## AI quality and cost control

- An optional Major Event model can handle only canon turning points and other
  major scenes while the normal model continues routine turns.
- A per-request estimated-cost ceiling blocks an oversized cloud request before
  it is sent.
- A session spending warning is shown in the existing cost indicator.
- Model Evaluations can compare two to five models on identical isolated
  scenarios and ranks quality, speed, call count, and estimated cost without
  changing the campaign.

## Verification

- 339 automated regression and feature tests pass.
- Python compilation and JavaScript syntax checks pass.
- Browser checks covered fresh launch, the campaign library, a loaded One Piece
  campaign, multi-action day planning, risk/date labels, canon interruption
  notices, and the six-scenario model-comparison interface.
- Live gpt-4o-mini playtests completed three turns each in Naruto and One Piece
  with separate readable updates, coherent suggested actions, and no errors.
