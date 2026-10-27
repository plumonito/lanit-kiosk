"""Playtime counters for the kiosk.

Steam games: minutes from the Steam Web API (GetOwnedGames) when an API key is
configured, otherwise from the local Steam client's localconfig.vdf. Local games:
the server times each run itself and keeps the total in state/local_playtime.json.

"This LAN" = minutes played since state/playtime_baseline.json was written (on the
first successful read). Delete that file to start counting from zero again.
"""
import json, os, re, threading, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state"
STEAMID64_BASE = 76561197960265728
REFRESH = 120  # seconds between Steam queries

_lock = threading.Lock()
_cache = {"source": None, "updated": None, "error": None, "games": {}}


def parse_vdf(text):
    """Minimal text-VDF parser: nested dicts of strings."""
    stack, key = [{}], None
    for s, brace in re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        if brace == "{":
            node = {}
            stack[-1][key] = node
            stack.append(node)
            key = None
        elif brace == "}":
            stack.pop()
        elif key is None:
            key = s
        else:
            stack[-1][key] = s
            key = None
    return stack[0]


def _read_json(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    STATE.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def steam_user(steam_root):
    """(steamid64, account dir) of the most recently logged-in Steam user."""
    users = parse_vdf((steam_root / "config/loginusers.vdf").read_text(errors="replace")).get("users", {})
    steamid = next((sid for sid, u in users.items() if u.get("MostRecent") == "1"), None) or next(iter(users))
    return steamid, steam_root / "userdata" / str(int(steamid) - STEAMID64_BASE)


def api_key():
    key = os.environ.get("STEAM_API_KEY")
    f = ROOT / "steam_api_key.txt"
    if not key and f.exists():
        key = f.read_text().strip()
    return key or None


def minutes_from_api(key, steamid):
    url = ("https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
           f"?key={key}&steamid={steamid}&include_played_free_games=1&skip_unvetted_apps=0&format=json")
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.load(r)
    return {g["appid"]: g.get("playtime_forever", 0) for g in data.get("response", {}).get("games", [])}


def minutes_from_client(userdir):
    cfg = parse_vdf((userdir / "config/localconfig.vdf").read_text(encoding="utf-8", errors="replace"))
    steam = cfg.get("UserLocalConfigStore", {}).get("Software", {}).get("Valve", {}).get("Steam", {})
    apps = steam.get("apps") or steam.get("Apps") or {}
    return {int(a): int(v.get("Playtime", 0)) for a, v in apps.items() if a.isdigit() and isinstance(v, dict)}


def refresh(games, steam_root):
    """Re-read all counters into the cache. `games` is the list from games.json."""
    try:
        steamid, userdir = steam_user(steam_root)
        key = api_key()
        if key:
            try:
                steam_min, source = minutes_from_api(key, steamid), "Steam Web API"
            except Exception as e:  # API down or bad key: still show something
                steam_min, source = minutes_from_client(userdir), f"Steam client (API failed: {e})"
        else:
            steam_min, source = minutes_from_client(userdir), "Steam client"
        error = None
    except Exception as e:
        steam_min, source, error = {}, None, str(e)

    local_min = _read_json(STATE / "local_playtime.json", {})
    totals = {}
    for g in games:
        if "steam" in g:
            if source:  # never-played games have no entry: count them as 0 so they can grow
                totals[g["id"]] = steam_min.get(g["steam"], 0)
        else:
            totals[g["id"]] = round(local_min.get(g["id"], 0))

    baseline_path = STATE / "playtime_baseline.json"
    baseline = _read_json(baseline_path, None)
    if baseline is None and totals:
        baseline = {"since": time.strftime("%Y-%m-%d %H:%M"), "minutes": totals}
        _write_json(baseline_path, baseline)
    elif baseline is not None:
        new = {k: v for k, v in totals.items() if k not in baseline["minutes"]}
        if new:  # a game added to games.json later starts counting from now
            baseline["minutes"].update(new)
            _write_json(baseline_path, baseline)
    base = (baseline or {}).get("minutes", {})

    with _lock:
        _cache.update(
            source=source, error=error, updated=time.strftime("%H:%M:%S"),
            since=(baseline or {}).get("since"),
            games={gid: {"minutes": m, "lan_minutes": max(0, m - base.get(gid, m))} for gid, m in totals.items()},
        )


def snapshot():
    with _lock:
        return json.loads(json.dumps(_cache))


def start_poller(load_games, steam_root):
    def loop():
        while True:
            refresh(load_games(), steam_root)
            time.sleep(REFRESH)
    threading.Thread(target=loop, daemon=True, name="playtime").start()


def track_local_run(game_id, proc):
    """Wait for a locally launched game to exit and add its run time to the counter."""
    def wait():
        start = time.time()
        proc.wait()
        with _lock:
            totals = _read_json(STATE / "local_playtime.json", {})
            totals[game_id] = totals.get(game_id, 0) + (time.time() - start) / 60
            _write_json(STATE / "local_playtime.json", totals)
    threading.Thread(target=wait, daemon=True, name=f"track-{game_id}").start()
