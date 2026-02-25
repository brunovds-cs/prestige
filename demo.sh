#!/usr/bin/env bash
# demo.sh — Run the full insurance claim processing pipeline demo.
#
# Usage:
#   ./demo.sh              # headful (browser visible)
#   ./demo.sh --headless   # headless (CI mode)
#
# Prerequisites:
#   - .venv with dependencies installed
#   - ANTHROPIC_API_KEY set (via .env or environment)
#   - Playwright chromium installed: .venv/bin/playwright install chromium

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON=".venv/bin/python"
FORM_URL="http://localhost:8000/web_form/index.html"
SERVER_PID=""

# Load .env if present
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo ""
        echo "Stopping HTTP server (PID $SERVER_PID)..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# --- 1. Start local HTTP server ---
echo "Starting local HTTP server on port 8000..."
$PYTHON -m http.server 8000 --directory . >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1

# Verify server is running
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ERROR: Failed to start HTTP server. Is port 8000 in use?"
    exit 1
fi
echo "Server running (PID $SERVER_PID)"

# --- 2. Run the pipeline ---
echo ""
echo "=== Running Insurance Claim Pipeline ==="
echo ""

HEADFUL_FLAG="--headful"
if [ "${1:-}" = "--headless" ]; then
    HEADFUL_FLAG=""
fi

$PYTHON -m src.pipeline \
    --inbox ./inbound_claims \
    --form-url "$FORM_URL" \
    $HEADFUL_FLAG

# --- 3. Display audit logs ---
echo ""
echo "=== Audit Log (audit.db) ==="
echo ""
$PYTHON -c "
from src.logging_db import get_logs
logs = get_logs()
if not logs:
    print('  (no records)')
else:
    for row in logs:
        status = row['status']
        name = row.get('policyholder_name') or '—'
        policy = row.get('policy_number') or '—'
        amount = row.get('claim_amount')
        amount_str = f'\${amount:,.2f}' if amount else '—'
        err = row.get('error_message') or ''
        print(f'  [{status:>18}]  {row[\"source_file\"]:<30}  {name:<20}  {policy:<16}  {amount_str}')
        if err:
            print(f'                       Error: {err}')
print()
print(f'Total records: {len(logs)}')
"
