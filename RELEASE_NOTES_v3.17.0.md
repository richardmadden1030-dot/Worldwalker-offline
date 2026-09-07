# Worldwalker RPG v3.17.0

## Private friend accounts

- The hosted build now opens on a Worldwalker login/create-account screen.
- Every friend receives a separate live game session, settings, campaigns,
  autosaves, and imported-save folder while using the same website.
- Passwords are hashed, login cookies persist for 30 days, and optional invite
  codes and account limits can be configured by the host.
- Signing out saves the active campaign before clearing its live session.

## Existing saves

- Older Worldwalker JSON exports can be imported through **Game → Import
  Campaign** after signing in.
- Imported campaigns pass through the existing schema migrator and belong only
  to the account that imported them.

## Hosted deployment

- Docker now runs Flask through Gunicorn with one worker and eight concurrent
  request threads, suitable for the private multi-account server model.
- Background-world queues are isolated per friend so simultaneous play cannot
  cross-deliver events.
- A single persistent `/data` volume stores the account database and every
  friend's private data.

Desktop EXE and local phone-host mode remain single-player and do not show the
friend-account login.
