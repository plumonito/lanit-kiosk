# LANIT Coop Corner kiosk

Full-screen, controller-driven game picker for the couch co-op corner. Tiles are
grouped by max player count, coloured by game type, and play a short gameplay
clip when focused. Launches Steam games via `steam://rungameid/…` and local
games via a command you configure.

Needs: Python 3, Google Chrome (or Chromium), ffmpeg (only for local-game clips), Steam.

## Run

```bash
./start.sh              # full-screen kiosk (Alt+F4 to quit)
./start.sh --windowed   # normal window, for testing
LANIT_DRY_RUN=1 ./start.sh --windowed   # log launches to launch.log instead of starting games
```

`start.sh` runs `fetch_media.py` on first start if `media/` is missing.

Not in git: `media/` (Steam art and clips, re-downloaded by `fetch_media.py`) and
`local-media/` (recordings and screenshots of local games, which show our faces).
On a fresh clone, put Blobby Knockout's `screenshot.png`, `cover.jpg` and `pan.mp4`
into `local-media/blobby-knockout/` and run `./fetch_media.py blobby-knockout`.

## Controls

| Controller | Keyboard | |
|---|---|---|
| D-pad / left stick | Arrows | Move |
| A / Start | Enter | Open game → A again to launch |
| B / Back | Esc | Back |
| LB / RB | PgUp / PgDn | Jump between player-count groups |

Mouse works too (hover + click).

## Idle showcase

After 45 s without input the kiosk tours random games every 14 s, each with a
(completely made-up) review quote from `quotes.json`. The first button press only
wakes it up. Edit or add quotes there, keyed by game id.

## Playtime counters

Each tile shows the total time played and, once someone plays, a yellow
"+x this LAN" badge. The server re-reads Steam every 2 minutes:

- **Steam client** (default, no setup): playtime from Steam's local `localconfig.vdf`.
  Steam writes that file on its own schedule, so new minutes may only appear
  after a game is closed.
- **Steam Web API** (more up to date): put an API key from
  <https://steamcommunity.com/dev/apikey> in `steam_api_key.txt` (or `STEAM_API_KEY`).
- **Local games**: the kiosk times each run from launch until the game exits.

"This LAN" counts from the first start; reset it when the party begins with
`./start.sh --new-lan`. The footer shows the source and the last update time.

## Editing the list: `games.json`

```json
{ "id": "heave-ho", "title": "Heave Ho", "steam": 905340, "players": 4, "type": "physics" }
```

- `players` is the local max; it decides which group the tile lands in.
- `type` is a key of `types` (label + colour). Add or recolour types there.
- `movie`: pick a different store trailer (index) for the clip.
- `clip_start` / `clip_len`: cut a longer clip from the full trailer instead of
  Steam's ~7 s microtrailer.
- `store_page`: take media from a different app id (used for the SpeedRunners 2 demo).

Local games (made at LANIT):

```json
{
  "id": "our-game", "title": "Our Game", "players": 4, "type": "local",
  "blurb": "One-line pitch shown on the detail screen.",
  "launch": { "cmd": ["/home/me/games/our-game/run.sh"], "cwd": "/home/me/games/our-game" },
  "media": { "source_video": "~/Videos/our-game-recording.mp4", "clip_start": 30, "clip_len": 10,
             "cover": "~/Pictures/our-game-cover.png" }
}
```

`cover` is optional (a frame from the clip is used otherwise). Then:

```bash
./fetch_media.py our-game           # or --force to redo one
```

Changes to `games.json` show up when the kiosk window regains focus or on reload (F5).

## Tips for the LAN

- Install everything beforehand: tiles show **Not installed** until Steam has
  the game; launching one of those opens Steam's install dialog.
- Turn off Steam's "Desktop Layout" for controllers if the d-pad feels doubled
  (the kiosk already drops the duplicate arrow-key presses).
- While a game runs, the kiosk ignores controller input; it picks up again when
  its window gets focus back.
