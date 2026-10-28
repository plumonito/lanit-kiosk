#!/usr/bin/env bash
# Start the launcher server and open the kiosk full screen in the browser.
# Run ./setup.sh once first on a new PC.
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

python3 - "$URL" <<'EOF'
import sys, time, urllib.request
for _ in range(50):
    try:
        urllib.request.urlopen(sys.argv[1], timeout=1); break
    except OSError:
        time.sleep(0.1)
EOF

# Any Chromium-based browser works best (it plays the H.264 clips); Firefox is the fallback.
for b in google-chrome-stable google-chrome chromium chromium-browser brave-browser microsoft-edge; do
  if command -v "$b" >/dev/null; then
    MODE=(--kiosk)
    [ "$WINDOWED" = 1 ] && MODE=(--window-size=1600,900)
    "$b" "${MODE[@]}" --app="$URL" \
      --user-data-dir="$PROFILE" \
      --no-first-run --no-default-browser-check --disable-translate \
      --autoplay-policy=no-user-gesture-required \
      --disable-features=Translate,MediaRouter \
      --password-store=basic
    exit
  fi
done

if command -v firefox >/dev/null; then
  FF_PROFILE="${XDG_DATA_HOME:-$HOME/.local/share}/lanit-kiosk/firefox-profile"
  mkdir -p "$FF_PROFILE"
  MODE=(--kiosk)
  [ "$WINDOWED" = 1 ] && MODE=()
  firefox "${MODE[@]}" --no-remote --profile "$FF_PROFILE" "$URL"
  exit
fi

echo "No browser found. Open $URL yourself; Ctrl-C here stops the kiosk."
wait $SERVER
