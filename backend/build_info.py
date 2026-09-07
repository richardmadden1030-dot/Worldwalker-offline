"""Membership-truth hotfix build ID; save schema and base app version remain stable."""
BUILD_ID = "3.64.0-membership-truth-1"
PATCH_NOTES = {
    "title": "One official team roster everywhere",
    "summary": "The Team screen, GM, and Advisor now read the same engine-owned membership ledger; old-save entity pollution is repaired without treating relationships or locations as people.",
    "highlights": [
        {"title": "One membership source of truth", "example": "Official members come from the organization ledger for the Team screen, GM context, Advisor context, commands, and faction-roster mirror."},
        {"title": "Old-save roster repair", "example": "Places and organizations such as Amegakure or Akatsuki are removed when they were accidentally stored as member names; legitimate character-backed members are recovered once."},
        {"title": "Candidates are not members", "example": "Invitations, recruitment attempts, affiliates, and refused offers do not appear as official party members until the engine-owned Yes/No decision establishes membership."},
        {"title": "Relationships do not imply membership", "example": "High affinity, a contact record, being in the same location, or appearing in old prose can no longer put an entity on a team."},
        {"title": "Recruitment prompts remain authoritative", "example": "Future named recruits and player join requests still use the explicit local confirmation system from the previous hotfix."},
    ],
}
