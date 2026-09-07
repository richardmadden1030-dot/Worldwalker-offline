#!/bin/sh
# Backs up all players' save/settings data to a timestamped tarball.
# Run manually, or point the NAS's scheduled-task feature at this script
# (e.g. daily at 3am) to back up automatically.
#
# Keeps the last 14 daily backups and prunes older ones.
set -e
cd "$(dirname "$0")"

STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p backups
tar -czf "backups/worldwalker_data_${STAMP}.tar.gz" data
find backups -name 'worldwalker_data_*.tar.gz' -mtime +14 -delete

echo "Backed up data/ to backups/worldwalker_data_${STAMP}.tar.gz"
