# Official team membership truth

Worldwalker 3.64 uses `state.organizations` as the single authoritative ledger for official group membership. The Team/Party UI, GM context, Advisor membership answers, organization commands, and mirrored faction rosters all consume this same ledger.

Old saves are repaired conservatively. Places, factions, organizations, relationship targets, and other non-character entities are removed from member lists. A missing legacy member is recovered only from character-backed affirmative membership evidence. Later negative evidence (refusal, departure, independent partner status, or an unaccepted offer) wins over older recruitment language unless the application already recorded the membership through the confirmation engine.

New membership is application-owned. When play establishes that a named character can join, Worldwalker queues a Yes/No recruitment decision. When the player explicitly tries to join an established organization, Worldwalker presents a local Yes/No join decision before the action is queued for narration. Naruto Academy graduates receive a deterministic squad-assignment opportunity four in-game days after graduation, using a known canon squad when applicable or a deterministic original squad otherwise.

The browser never infers membership from contacts, relationships, locations, or prose. `roster-sync.js` is presentation-only.
