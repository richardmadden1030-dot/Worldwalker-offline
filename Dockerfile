FROM python:3.12-slim

WORKDIR /app

# Only Flask is needed for headless server mode — pywebview (the desktop
# window wrapper) is intentionally excluded, since it needs a GUI toolkit
# that has no place in a container.
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY assets/ assets/
COPY music/ music/
COPY server.py .

# Worldwalker's own data directory (saves, settings, generated portraits)
# resolves to $HOME/WorldwalkerRPG. Pointing HOME at a mounted volume is what
# makes save games and AI/API settings survive a container restart or
# rebuild — see docker-compose.yml.
ENV HOME=/data
VOLUME /data

EXPOSE 8765
ENV HOST=0.0.0.0
ENV PORT=8765
ENV WORLDWALKER_ACCOUNTS_ENABLED=1

# A bind-mounted host folder (./data/playerN on the NAS) can end up owned by
# a different UID than the one this container runs as — some NAS Docker
# setups remap "root" inside the container to an unprivileged host user.
# When that happens, the app crashes immediately on its very first write to
# $HOME (before Flask even starts listening), and the restart policy just
# keeps relaunching it every few seconds forever, which looks like the
# server "opening and closing." chmod the mount permissive on every start so
# this can't happen regardless of exactly how the NAS maps ownership — fine
# for a private, friends-only game server, not something to do on anything
# handling real secrets.
CMD ["sh", "-c", "chmod -R 777 /data 2>/dev/null || true; exec gunicorn --bind ${HOST:-0.0.0.0}:${PORT:-8765} --workers 1 --threads ${GUNICORN_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-600} --access-logfile - --error-logfile - server:app"]
