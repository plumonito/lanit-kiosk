#!/usr/bin/env bash
# One-time setup on a new PC: builds and installs Blobby Knockout into ~/.local,
# then downloads the cover art and gameplay clips. Safe to re-run (also to update).
#
#   ./setup.sh                          # build + install + fetch media
#   ./setup.sh --players players.zip    # also install the player names + faces
set -euo pipefail
cd "$(dirname "$0")"

PREFIX="${BLOBBY_PREFIX:-$HOME/.local}"   # games.json launches ~/.local/bin/blobby
PLAYERS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --players) PLAYERS="${2:?--players needs a zip file}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

deps_help() {
  cat >&2 <<'EOF'

Install the build tools and libraries, then run ./setup.sh again:
  Debian / Ubuntu:  sudo apt install git python3 cmake g++ libsdl2-dev libboost-dev libphysfs-dev
  Fedora:           sudo dnf install git python3 cmake gcc-c++ SDL2-devel boost-devel physfs-devel
  Arch:             sudo pacman -S git python cmake gcc sdl2 boost physfs
EOF
  exit 1
}

missing=()
for tool in git python3 cmake; do command -v "$tool" >/dev/null || missing+=("$tool"); done
command -v c++ >/dev/null || command -v g++ >/dev/null || missing+=("a C++ compiler")
if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing: ${missing[*]}" >&2
  deps_help
fi

echo "==> Fetching Blobby Knockout source (git submodule)"
git submodule update --init --recursive

echo "==> Building Blobby Knockout"
mkdir -p build
cmake -S games/blobby-knockout -B build/blobby -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" >build/cmake.log 2>&1 \
  || { tail -20 build/cmake.log >&2; echo "CMake failed (full log: build/cmake.log)." >&2; deps_help; }
cmake --build build/blobby -j"$(nproc 2>/dev/null || echo 4)"

echo "==> Installing Blobby Knockout into $PREFIX"
cmake --install build/blobby >/dev/null
echo "    game: $PREFIX/bin/blobby   data: $PREFIX/share/blobby-knockout"

if [ -n "$PLAYERS" ]; then
  echo "==> Installing players from $PLAYERS"
  python3 - "$PLAYERS" "$PREFIX/share/blobby-knockout" <<'EOF'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    names = [n for n in z.namelist() if n.startswith("players/")]
    if not names:
        sys.exit("    the zip has no players/ folder")
    z.extractall(sys.argv[2], members=names)
    print(f"    {len(names)} files")
EOF
fi

echo "==> Downloading cover art and gameplay clips"
python3 fetch_media.py || echo "    Some downloads failed; re-run ./fetch_media.py later." >&2

echo "==> Checking the rest"
command -v steam >/dev/null || [ -d "$HOME/.var/app/com.valvesoftware.Steam" ] \
  || echo "    ! Steam not found: install it and log in, or only the local games will launch."
browser=""
for b in google-chrome-stable google-chrome chromium chromium-browser brave-browser microsoft-edge firefox; do
  command -v "$b" >/dev/null && { browser="$b"; break; }
done
[ -n "$browser" ] && echo "    browser: $browser" || echo "    ! No browser found: install Google Chrome or Chromium."

cat <<EOF

Done. Start the kiosk with:
  ./start.sh --new-lan     (first time at the party: resets the "this LAN" counters)
  ./start.sh               (any other time)
EOF
