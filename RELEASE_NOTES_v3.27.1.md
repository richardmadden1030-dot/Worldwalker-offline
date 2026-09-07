# Worldwalker RPG v3.27.1

## Mobile sign-in reliability

- Successful sign-ins now receive a signed 30-day fallback token in addition to the normal secure session cookie.
- Phones, installed PWAs, and privacy-heavy browsers can keep the correct private account even when they discard the cookie between the login response and the first game request.
- Bearer sessions preserve the same account isolation and CSRF checks as cookie sessions.

## Original Ability Archive

- Every non-canon starting ability, hidden class, Zanpakuto, and JJK birth-slot design is saved per account in `generated_abilities.json`.
- The Codex now includes an expandable Original Ability Archive for later reference.
- Rerolls exclude every design already seen by that account. Exact name and mechanical duplicates are rejected locally, while the generator also receives a concise list of prior designs to avoid cosmetic reskins.
- Canon abilities are deliberately reusable and are not added to the exclusion archive.
