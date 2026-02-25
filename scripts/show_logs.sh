#!/usr/bin/env bash
# show_logs.sh — Display audit log in a readable table
set -euo pipefail

DB="audit.db"

if [ ! -f "$DB" ]; then
    echo "No $DB found — run the pipeline first."
    exit 0
fi

TOTAL=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processing_log;")
SUCCESS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM processing_log WHERE status='success';")
FAILED=$((TOTAL - SUCCESS))

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════════════════╗"
echo "║                              AUDIT LOG — audit.db                                      ║"
echo "╠════╦══════════════════════╦══════════════════════╦══════════════════╦════════════╦═══════╣"
echo "║ ID ║ Source File          ║ Policyholder         ║ Policy Number    ║ Amount     ║Status ║"
echo "╠════╬══════════════════════╬══════════════════════╬══════════════════╬════════════╬═══════╣"

sqlite3 "$DB" -separator '|' \
    "SELECT id, source_file, COALESCE(policyholder_name,'-'), COALESCE(policy_number,'-'), COALESCE(printf('\$%,.2f',claim_amount),'-'), status FROM processing_log ORDER BY id;" \
| while IFS='|' read -r id file name policy amount status; do
    # Truncate long values to fit columns
    file=$(printf '%.20s' "$file")
    name=$(printf '%.20s' "$name")
    policy=$(printf '%.16s' "$policy")
    if [ "$status" = "success" ]; then
        mark="\033[32m  OK  \033[0m"
    else
        mark="\033[31m FAIL \033[0m"
    fi
    printf "║ %2s ║ %-20s ║ %-20s ║ %-16s ║ %10s ║${mark}║\n" "$id" "$file" "$name" "$policy" "$amount"
done

echo "╠════╩══════════════════════╩══════════════════════╩══════════════════╩════════════╩═══════╣"
printf "║  Total: %-4s  |  \033[32mSuccess: %-4s\033[0m  |  \033[31mFailed: %-4s\033[0m                                    ║\n" "$TOTAL" "$SUCCESS" "$FAILED"
echo "╚════════════════════════════════════════════════════════════════════════════════════════════╝"
echo ""
