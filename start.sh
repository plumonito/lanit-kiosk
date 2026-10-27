#!/usr/bin/env bash
# Start the launcher server and open the kiosk full screen in Chrome.
# Exit the kiosk with Alt+F4.
#   --windowed   normal window, for testing
#   --new-lan    reset the "+x this LAN" playtime counters (run once when the party starts)
set -euo pipefail
cd "$(dirname "$0")"

WINDOWED=0
for arg in "$@"; do
  case "$arg" in
    --windowed) WINDOWED=1 ;;
    --new-lan) rm -f state/playtime_baseline.json && echo "Playtime counters for this LAN reset." ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

PORT="${PORT:-8765}"
URL="http://127.0.0.1:$PORT/"
PROFILE="${XDG_DATA_HOME:-$HOME/.local/share}/lanit-kiosk/chrome-profile"

if [ ! -d media ]; then
  echo "No media yet, fetching covers and clips…"
  ./fetch_media.py || echo "Some media failed to download; continuing anyway."
fi

python3 server.py --port "$PORT" &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT

for _ in $(seq 50); do curl -fs "$URL" >/dev/null && break; sleep 0.1; done

BROWSER="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
MODE=(--kiosk)
[ "$WINDOWED" = 1 ] && MODE=(--window-size=1600,900)

"$BROWSER" "${MODE[@]}" --app="$URL" \
  --user-data-dir="$PROFILE" \
  --no-first-run --no-default-browser-check --disable-translate \
  --autoplay-policy=no-user-gesture-required \
  --disable-features=Translate,MediaRouter \
  --password-store=basic
