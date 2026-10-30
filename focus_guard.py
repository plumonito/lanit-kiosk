"""Keep the kiosk in front when no game is running, without ever stealing focus from a game.

The Steam client likes to bring its own window forward (when a game starts, when it exits, for
notifications), and at the LAN nobody has a mouse to click back to the kiosk. Every few seconds:

- a game is running (a Steam `reaper SteamLaunch AppId=...` process, or a local game we started):
  only Steam's own windows are minimized, never the game's (Steam games have their own window
  class, `steam_app_<id>`), and the kiosk is not brought forward;
- a game was launched in the last LAUNCH_GRACE seconds and hasn't shown up yet: leave everything
  alone, so Steam's install, shader and "launching" dialogs can do their thing;
- otherwise: minimize Steam's windows and bring the kiosk window (found by its title) to the front.

Windows are moved through a KWin script (KDE Plasma, e.g. SteamOS desktop mode) over D-Bus with
`busctl`. Anywhere else the guard switches itself off.
"""
import json, os, shutil, subprocess, tempfile, threading, time
from pathlib import Path

INTERVAL = 3        # seconds between checks
LAUNCH_GRACE = 90   # seconds a launch may take before the kiosk takes the screen back

_launched_at = 0.0
_local_procs = []   # Popen objects of local games we started
_lock = threading.Lock()

SCRIPT = """
(function () {
    const kioskTitle = %(title)s.toLowerCase();
    const activate = %(activate)s;
    let kiosk = null;
    for (const w of workspace.windowList()) {
        const cls = String(w.resourceClass);
        if (cls === "steam" && w.minimizable && !w.minimized)
            w.minimized = true;
        else if (!kiosk && cls !== "steam" && String(w.caption).toLowerCase().indexOf(kioskTitle) !== -1)
            kiosk = w;
    }
    if (activate && kiosk) {
        kiosk.minimized = false;
        if (workspace.activeWindow !== kiosk)
            workspace.activeWindow = kiosk;
    }
})();
"""


def note_launch(proc=None):
    """Called by the launcher; `proc` is the process of a local game (None for Steam games)."""
    global _launched_at
    with _lock:
        _launched_at = time.time()
        if proc is not None:
            _local_procs.append(proc)


def steam_game_running():
    """Steam starts every game under `reaper SteamLaunch AppId=<id> -- ...`."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if b"SteamLaunch" in args and any(a.startswith(b"AppId=") for a in args):
            return True
    return False


def local_game_running():
    with _lock:
        _local_procs[:] = [p for p in _local_procs if p.poll() is None]
        return bool(_local_procs)


class KWin:
    """Runs a one-off KWin script through org.kde.KWin /Scripting."""

    def __init__(self):
        self.busctl = shutil.which("busctl")
        self.dir = Path(tempfile.mkdtemp(prefix="lanit-kwin-"))
        self.n = 0

    def call(self, path, iface, method, sig="", *args):
        out = subprocess.run([self.busctl, "--user", "call", "org.kde.KWin", path, iface, method,
                              *([sig, *map(str, args)] if sig else [])],
                             capture_output=True, text=True, timeout=5)
        if out.returncode != 0:
            raise OSError(out.stderr.strip() or f"busctl {method} failed")
        return out.stdout.split()

    def available(self):
        if not self.busctl:
            return False
        try:
            self.call("/Scripting", "org.kde.kwin.Scripting", "isScriptLoaded", "s", "lanit-probe")
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    def run(self, source):
        self.n += 1
        name = f"lanit-kiosk-{os.getpid()}-{self.n}"
        f = self.dir / "guard.js"
        f.write_text(source)
        try:
            reply = self.call("/Scripting", "org.kde.kwin.Scripting", "loadScript", "ss", f, name)
            script_id = reply[-1]  # "i 7"
            self.call(f"/Scripting/Script{script_id}", "org.kde.kwin.Script", "run")
        finally:
            try:
                self.call("/Scripting", "org.kde.kwin.Scripting", "unloadScript", "s", name)
            except (OSError, subprocess.TimeoutExpired):
                pass


def tidy(kwin, kiosk_title, activate):
    kwin.run(SCRIPT % {"title": json.dumps(kiosk_title), "activate": "true" if activate else "false"})


def start(load_title, log):
    """Start the guard thread. `load_title()` returns the kiosk's page title (from games.json)."""
    if os.environ.get("LANIT_FOCUS_GUARD") == "0":
        log("focus guard: off (LANIT_FOCUS_GUARD=0)")
        return
    kwin = KWin()
    if not kwin.available():
        log("focus guard: off (no KWin scripting on the session bus)")
        return
    log("focus guard: on")

    def loop():
        global _launched_at
        failures = 0
        while True:
            time.sleep(INTERVAL)
            try:
                playing = steam_game_running() or local_game_running()
                if playing:
                    _launched_at = 0.0  # the game showed up: once it exits, come straight back
                launching = time.time() - _launched_at < LAUNCH_GRACE
                if launching and not playing:
                    continue  # let Steam's dialogs and the starting game have the screen
                tidy(kwin, load_title(), activate=not playing)
                failures = 0
            except Exception as e:  # never take the server down over window juggling
                failures += 1
                if failures in (1, 10, 100):
                    log(f"focus guard: {e}")

    threading.Thread(target=loop, daemon=True, name="focus-guard").start()
