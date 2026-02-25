#!/usr/bin/env bash
# clean_db.sh — Reset the audit database
set -euo pipefail

DB="audit.db"

if [ ! -f "$DB" ]; then
    echo "No $DB found — nothing to clean."
    exit 0
fi

COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processing_log;")
rm "$DB"
echo "Deleted $DB ($COUNT records removed)"
