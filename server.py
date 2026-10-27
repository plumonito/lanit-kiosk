#!/usr/bin/env python3
"""Tiny local server for the kiosk: serves the UI + media and launches games.

Only games listed in games.json can be launched; the browser sends an id, never
a command. Binds to localhost only.

    ./server.py [--port 8765]      LANIT_DRY_RUN=1 ./server.py  (log instead of launching)
"""
import argparse, json, mimetypes, os, posixpath, re, subprocess, threading, time, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import playtime

ROOT = Path(__file__).resolve().parent
STEAM = Path(os.environ.get("STEAM_ROOT", Path.home() / ".local/share/Steam"))
DRY_RUN = os.environ.get("LANIT_DRY_RUN") == "1"
LAUNCH_COOLDOWN = 8  # seconds; stops a mashed A button from starting a game twice
LOG = ROOT / "launch.log"

_last_launch = 0.0
_lock = threading.Lock()


def load_config():
    return json.loads((ROOT / "games.json").read_text())


def installed_appids():
    """App ids with an appmanifest in any Steam library folder."""
    libs = {STEAM}
    vdf = STEAM / "steamapps/libraryfolders.vdf"
    if vdf.exists():
        libs |= {Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace"))}
    ids = set()
    for lib in libs:
        for f in (lib / "steamapps").glob("appmanifest_*.acf"):
            ids.add(int(f.stem.split("_")[1]))
    return ids


def games_payload():
    cfg = load_config()
    installed = installed_appids()
    qf = ROOT / "quotes.json"
    quotes = json.loads(qf.read_text()) if qf.exists() else {}
    games = []
    for g in cfg["games"]:
        media = ROOT / "media" / g["id"]
        meta = {}
        if (media / "meta.json").exists():
            meta = json.loads((media / "meta.json").read_text())
        games.append({
            "id": g["id"],
            "title": g.get("title") or meta.get("name") or g["id"],
            "players": g.get("players", 1),
            "type": g.get("type", "local"),
            "blurb": g.get("blurb") or meta.get("blurb", ""),
            "cover": f"/media/{g['id']}/cover.jpg" if (media / "cover.jpg").exists() else None,
            "clip": f"/media/{g['id']}/clip.mp4" if (media / "clip.mp4").exists() else None,
            "installed": ("steam" not in g) or g["steam"] in installed,
            "local": "steam" not in g,
            "quotes": quotes.get(g["id"], []),
        })
    return {"title": cfg.get("title", "LAN KIOSK"), "types": cfg["types"], "games": games}


def launch(game_id):
    global _last_launch
    game = next((g for g in load_config()["games"] if g["id"] == game_id), None)
    if not game:
        return 404, {"error": "unknown game"}
    with _lock:
        if time.time() - _last_launch < LAUNCH_COOLDOWN:
            return 429, {"error": "already launching"}
        _last_launch = time.time()

    if "steam" in game:
        cmd, cwd = ["steam", f"steam://rungameid/{game['steam']}"], None
    else:
        cmd, cwd = game["launch"]["cmd"], game["launch"].get("cwd")

    with LOG.open("a") as log:
        log.write(f"{time.strftime('%F %T')} {'DRY ' if DRY_RUN else ''}{game_id}: {cmd}\n")
        if not DRY_RUN:
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                    start_new_session=True)
            if "steam" not in game:  # Steam tracks its own games; we time the local ones
                playtime.track_local_run(game_id, proc)
    return 200, {"ok": True, "dry_run": DRY_RUN}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = posixpath.normpath(urllib.parse.unquote(self.path.split("?")[0]))
        if path == "/api/games":
            return self.send_json(200, games_payload())
        if path == "/api/playtime":
            return self.send_json(200, playtime.snapshot())
        if path == "/":
            self.path = "/web/index.html"
        elif not (path.startswith("/web/") or path.startswith("/media/")):
            return self.send_error(404)
        if path.startswith("/media/") and self.headers.get("Range"):
            return self.send_range()
        return super().do_GET()

    def send_range(self):
        """Byte-range responses so <video> can seek/loop smoothly."""
        f = Path(self.translate_path(self.path))
        if not f.is_file():
            return self.send_error(404)
        size = f.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers["Range"])
        start = int(m.group(1)) if m and m.group(1) else 0
        end = min(int(m.group(2)) if m and m.group(2) else size - 1, size - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            return self.end_headers()
        self.send_response(206)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with f.open("rb") as fh:
            fh.seek(start)
            self.wfile.write(fh.read(end - start + 1))

    def do_POST(self):
        m = re.fullmatch(r"/api/launch/([\w.-]+)", self.path)
        if not m:
            return self.send_error(404)
        # Only the kiosk page itself may launch, not some other site open in a browser.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            return self.send_error(403)
        self.send_json(*launch(m.group(1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    playtime.start_poller(lambda: load_config()["games"], STEAM)
    print(f"kiosk server on http://127.0.0.1:{args.port}{'  (DRY RUN)' if DRY_RUN else ''}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
