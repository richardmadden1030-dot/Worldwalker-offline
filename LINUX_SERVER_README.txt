Worldwalker RPG — Private Friend Server
========================================

WHAT THIS BUILD DOES
--------------------
One hosted server now supports several friends at the same URL. Each person
creates a username and password and receives an isolated live game session,
settings file, campaign folder, rolling autosaves, and imported campaigns.
One friend cannot list, load, overwrite, or delete another friend's saves.

HOW TO RUN IT
-------------
1. Install Docker and Docker Compose.
2. Copy this folder to the server.
3. Run:
       docker compose up -d --build
4. Put Cloudflare in front of port 5001, or test directly at:
       http://<server-ip>:5001/

The container runs Flask through Gunicorn with one worker and eight threads.
One worker keeps the in-process GameSession registry coherent; the threads let
different friends use the game concurrently. Durable campaign data remains in
the mounted ./data folder across container rebuilds and restarts.

ACCOUNTS
--------
The sign-in screen lets a friend either log in or create an account. Usernames
are 3–24 letters, numbers, dashes, or underscores. Passwords are hashed in the
server database and never stored in campaign files.

Optional environment settings in docker-compose.yml:
  WORLDWALKER_MAX_ACCOUNTS=25       Maximum accounts allowed.
  WORLDWALKER_INVITE_CODE=...       Require this code at account creation.
  WORLDWALKER_SECRET_KEY=...        Optional fixed cookie-signing secret.
  WORLDWALKER_SECURE_COOKIES=1      Use 1 behind the HTTPS Cloudflare domain.

If testing directly over plain HTTP, temporarily change
WORLDWALKER_SECURE_COOKIES to 0. Put it back to 1 for the Cloudflare site.

OLD SAVES
---------
After signing into the correct account, use:
  GAME > IMPORT CAMPAIGN
Choose the old .worldwalker.json or JSON campaign export. The normal save
migrator upgrades the campaign and stores the imported copy only under the
signed-in account. Importing does not alter another friend's campaigns.

AI SETUP
--------
Existing server settings are copied when a friend account is first opened.
For a clean deployment, shared hosted AI can be configured with environment
variables instead of asking each friend to paste a key:
  OPENAI_API_KEY=...
  WORLDWALKER_AI_MODEL=gpt-5.4-mini
  WORLDWALKER_SECONDARY_MODEL=gpt-5.4-nano
  WORLDWALKER_MAJOR_MODEL=gpt-5.4-mini

Never commit the real API key to GitHub. Set it in the hosting dashboard or
the server's private compose environment.

BACKUPS
-------
Run ./backup.sh or back up the whole ./data folder. It contains:
  - the friend-account database;
  - each account's saves, autosaves, and settings;
  - generated portraits and other persistent runtime data.

Stop the container before restoring an older data backup.

TROUBLESHOOTING
---------------
Show server logs:
  docker compose logs -f worldwalker

Rebuild after an update:
  docker compose up -d --build

If account cookies work through Cloudflare but not by direct IP, that is
expected while WORLDWALKER_SECURE_COOKIES=1. HTTPS is required for that cookie.

FILES
-----
  backend/, frontend/, assets/, music/  Game source and bundled content
  server.py                             Hosted WSGI application entry point
  Dockerfile                            Gunicorn production image
  docker-compose.yml                    One multi-account friend server
  backup.sh                             Persistent-data backup helper
  requirements-server.txt               Flask and Gunicorn dependencies
