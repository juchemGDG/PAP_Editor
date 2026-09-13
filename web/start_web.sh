#!/usr/bin/env bash
# Startet den PAP-Editor als Web-App im Browser.
# Auf dem Mac: bash web/start_web.sh
# Vom iPad: http://<IP-des-Macs>:5000
#
# Der Menuepunkt "Desktop-Version" holt die Pakete vom neuesten GitHub-Release.
# Bei einem privaten Repository vorher ein Lese-Token setzen:
#   export PAP_GITHUB_TOKEN=github_pat_...

PORT="${1:-5000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  PAP Editor – Web-Version                   │"
echo "  │                                             │"
echo "  │  Lokal:   http://localhost:${PORT}             │"
echo "  │  iPad:    http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}         │"
echo "  │                                             │"
echo "  │  Beenden: Strg+C                            │"
echo "  └─────────────────────────────────────────────┘"
echo ""

cd "$SCRIPT_DIR"
python3 app.py "$PORT"
