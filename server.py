"""Headless friend-server entry point for Worldwalker RPG on Linux/Docker.

The hosted build enables lightweight accounts and gives every signed-in friend
an independent GameSession and persistent save/settings folder. Gunicorn loads
this module as ``server:app``; direct ``python server.py`` remains useful for
simple development testing.

Configure with environment variables:
  HOST       - bind address (default 0.0.0.0, i.e. reachable from other machines)
  PORT       - bind port (default 8765)
  AUTH_USER  - if set (together with AUTH_PASS), requires an HTTP basic-auth
               login before any request is served
  AUTH_PASS  - password for AUTH_USER
Leaving AUTH_USER/AUTH_PASS unset disables auth entirely (the default).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# The headless build is the hosted/private-friends edition. Desktop and local
# phone mode import backend/app.py through launcher.py instead and remain the
# familiar single-player experience unless this is explicitly overridden.
os.environ.setdefault("WORLDWALKER_ACCOUNTS_ENABLED", "1")

from flask import request, Response

from app import app

AUTH_USER = os.environ.get("AUTH_USER")
AUTH_PASS = os.environ.get("AUTH_PASS")

if AUTH_USER and AUTH_PASS:
    @app.before_request
    def _require_basic_auth():
        auth = request.authorization
        if not auth or auth.username != AUTH_USER or auth.password != AUTH_PASS:
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Worldwalker RPG"'},
            )

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))
    auth_note = " (login required)" if AUTH_USER and AUTH_PASS else ""
    print(f"Worldwalker RPG server starting on http://{host}:{port}/{auth_note}")
    # debug=False is deliberate and load-bearing: Flask's debug mode exposes
    # an interactive in-browser debugger that allows arbitrary code execution
    # to anyone who can reach it — never enable it on a network-bound server.
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)
