# LANIT Coop Corner kiosk

Full-screen, controller-driven game picker for the couch co-op corner. Tiles are
grouped by max player count, coloured by game type, and play a short gameplay
clip when focused. When nobody touches it, it tours the games with (fake) review
quotes. Each tile shows how long the game has been played, read from Steam.

It launches Steam games through the Steam client and our own **Blobby Knockout**
(a party mode for [Blobby Volley 2](https://github.com/plumonito/blobbyvolley2/tree/feature/knockout-mode),
included as a git submodule and built from source).

Runs on Linux (tested on Ubuntu with GNOME, Wayland).

## Set up on a new PC

1. **Install the basics**: Steam (logged in), Google Chrome or Chromium, and the
   build tools for Blobby Knockout:

   ```bash
   # Debian / Ubuntu
   sudo apt install git python3 cmake g++ libsdl2-dev libboost-dev libphysfs-dev
   # Fedora:  sudo dnf install git python3 cmake gcc-c++ SDL2-devel boost-devel physfs-devel
   # Arch:    sudo pacman -S git python cmake gcc sdl2 boost physfs
   ```

2. **Clone with the submodule**:

   ```bash
   git clone --recurse-submodules https://github.com/plumonito/lanit-kiosk.git
   cd lanit-kiosk
   ```

3. **Run the setup once.** It builds Blobby Knockout, installs it into `~/.local`
   (no root needed) and downloads the cover art and gameplay clips from the Steam store:

   ```bash
   ./setup.sh
   ```

   To get our faces on the blobs, pass the players zip (kept out of git on purpose,
   bring it on a USB stick): `./setup.sh --players players.zip`. It needs a
   `players/` folder with `players.txt` and the face images, see the
   [Blobby Knockout README](https://github.com/plumonito/blobbyvolley2/tree/feature/knockout-mode#players-and-faces).

4. **Install the Steam games** you want on the tiles (they show **Not installed**
   until then; launching one opens Steam's install dialog).

5. **Start it**:

   ```bash
   ./start.sh --new-lan   # at the start of the party: resets the "+x this LAN" counters
   ./start.sh             # any other time
   ```

   Alt+F4 quits. `./start.sh --windowed` gives a normal window for testing, and
   `LANIT_DRY_RUN=1 ./start.sh --windowed` logs launches to `launch.log` instead of
   starting games.

To update later: `git pull --recurse-submodules && ./setup.sh`.

### What is (not) in git

- In git: the kiosk (`server.py`, `web/`), the game list, quotes, scripts, the
  Blobby Knockout source (submodule `games/blobby-knockout`) and its cover/clip in
  `assets/` (rendered from the game's art by `tools/make_blobby_media.py`).
- Not in git: `media/` (Steam's art and trailers, downloaded by `setup.sh` /
  `fetch_media.py`), player photos (`players.zip`), `local-media/` (your own
  recordings), `state/` (playtime counters) and `steam_api_key.txt`.

## Controls

| Controller | Keyboard | |
|---|---|---|
| D-pad / left stick | Arrows | Move |
| A / Start | Enter | Open game → A again to launch |
| B / Back | Esc | Back |
| LB / RB | PgUp / PgDn | Jump between player-count groups |

Mouse works too (hover + click). Blobby Knockout has its own controls: press jump
to join, Start to begin, X for drunk mode (see its README).

## Idle showcase

After 45 s without input the kiosk tours random games every 14 s, each with a
(completely made-up) review quote from `quotes.json`. The first button press only
wakes it up. Edit or add quotes there, keyed by game id.

## Playtime counters

Each tile shows the total time played and, once someone plays, a yellow
"+x this LAN" badge. The server re-reads Steam every 2 minutes:

- **Steam client** (default, no setup): playtime from Steam's local `localconfig.vdf`
  of the last logged-in user. Steam writes that file on its own schedule, so new
  minutes may only appear after a game is closed.
- **Steam Web API** (more up to date): put an API key from
  <https://steamcommunity.com/dev/apikey> in `steam_api_key.txt` (or `STEAM_API_KEY`).
- **Local games**: the kiosk times each run from launch until the game exits.

"This LAN" counts from the first start, or from `./start.sh --new-lan`. The footer
shows the source and the last update time. Steam is found in `~/.local/share/Steam`,
`~/.steam/steam` or the Flatpak folder; set `STEAM_ROOT` for anything else.

## Editing the list: `games.json`

```json
{ "id": "heave-ho", "title": "Heave Ho", "steam": 905340, "players": 4, "type": "physics" }
```

- `players` is the local max; it decides which group the tile lands in.
- `type` is a key of `types` (label + colour). Add or recolour types there.
- `movie`: pick a different store trailer (index) for the clip.
- `clip_start` / `clip_len`: cut a longer clip from the full trailer instead of
  Steam's ~7 s microtrailer (needs ffmpeg).
- `store_page`: take media from a different app id (used for the SpeedRunners 2 demo).

Then run `./fetch_media.py` (only downloads what is missing; `--force <id>` redoes one).

Local games (made at LANIT):

```json
{
  "id": "our-game", "title": "Our Game", "players": 4, "type": "local",
  "blurb": "One-line pitch shown on the detail screen.",
  "launch": { "cmd": ["~/games/our-game/run.sh"], "cwd": "~/games/our-game" },
  "media": { "source_video": "local-media/our-game/recording.mp4", "clip_start": 30, "clip_len": 10,
             "cover": "local-media/our-game/cover.png" }
}
```

`media.clip` uses a finished clip as is; `media.source_video` is cut with ffmpeg.
`cover` is optional (a frame from the clip is used otherwise). Paths may start
with `~` or be relative to this folder. Changes to `games.json` show up when the
kiosk window regains focus or on reload (F5).

## Tips for the LAN

- Turn off Steam's "Desktop Layout" for controllers if the d-pad feels doubled
  (the kiosk already drops the duplicate arrow-key presses).
- While a game runs, the kiosk ignores controller input and pauses its videos;
  it picks up again when its window gets focus back.
