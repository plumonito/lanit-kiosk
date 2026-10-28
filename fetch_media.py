#!/usr/bin/env python3
"""Download cover art + a short gameplay clip for every game in games.json.

Steam games: cover = capsule_616x353, clip = Steam's "microtrailer" (≈7s, silent,
480p) of the game's first trailer. Set "clip_start"/"clip_len" on a Steam entry
to cut a longer clip out of the full trailer instead, and "movie" to pick a
different trailer (index into the store's trailer list).

Local games: "media.clip" is a ready-made clip that is copied as is; otherwise
"media.source_video" is cut with ffmpeg. The cover is "media.cover" if given,
otherwise a frame grabbed from the clip. Relative paths are relative to this folder.

    ./fetch_media.py              # fetch whatever is missing
    ./fetch_media.py --force pico-park heave-ho
"""
import argparse, html, json, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
UA = {"User-Agent": "lanit-kiosk/1.0"}


def get(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except OSError:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def download(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(get(url))
    tmp.replace(dest)


def ffmpeg_clip(src, dest, start, length):
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-ss", str(start), "-i", str(src), "-t", str(length),
         "-an", "-vf", "scale=854:-2,fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)],
        check=True)


def ffmpeg_cover(src, dest):
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-ss", "2", "-i", str(src), "-frames:v", "1",
         "-vf", "scale=616:353:force_original_aspect_ratio=increase,crop=616:353", str(dest)],
        check=True)


def blurb_from_html(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def fetch_steam(game, out, force):
    # Demos have no store page; "store_page" points media at the full game instead.
    appid = game.get("store_page", game["steam"])
    meta_path = out / "meta.json"
    if not force and (out / "cover.jpg").exists() and (out / "clip.mp4").exists() and meta_path.exists():
        return "cached"

    data = json.loads(get(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=us&l=en"))
    entry = data.get(str(appid), {})
    if not entry.get("success"):
        raise RuntimeError("store has no data for this app (delisted or region-locked?)")
    d = entry["data"]

    header = d.get("header_image", "")
    capsule = re.sub(r"header\.jpg", "capsule_616x353.jpg", header)
    try:
        download(capsule, out / "cover.jpg")
    except Exception:
        download(header, out / "cover.jpg")

    movies = d.get("movies") or []
    clip = out / "clip.mp4"
    if movies:
        movie = movies[min(game.get("movie", 0), len(movies) - 1)]
        if "clip_start" in game:
            # Cut from the full trailer's HLS stream (480p variant).
            hls = movie.get("hls_h264") or ""
            src = re.sub(r"hls_264_master\.m3u8.*$", "hls_264_2_video.m3u8", hls) if hls else movie["mp4"]["480"]
            ffmpeg_clip(src, clip, game["clip_start"], game.get("clip_len", 12))
        else:
            hls = movie.get("hls_h264")
            if hls:
                micro = re.sub(r"hls_264_master\.m3u8.*$", "microtrailer.mp4", hls)
                download(micro, clip)
            else:  # older store format
                tmp = out / "micro.webm"
                download(f"https://cdn.akamai.steamstatic.com/steam/apps/{movie['id']}/microtrailer.webm", tmp)
                ffmpeg_clip(tmp, clip, 0, 30)
                tmp.unlink()
    elif clip.exists():
        clip.unlink()

    meta_path.write_text(json.dumps({
        "name": d.get("name"),
        "blurb": blurb_from_html(d.get("short_description")),
    }, indent=1))
    return "ok" + ("" if movies else " (no trailer, cover only)")


def local_path(p):
    """Media paths in games.json may be relative to the kiosk folder."""
    p = Path(p).expanduser()
    return p if p.is_absolute() else ROOT / p


def fetch_local(game, out, force):
    m = game.get("media") or {}
    src = local_path(m.get("source_video", ""))
    clip, cover = out / "clip.mp4", out / "cover.jpg"
    if not force and clip.exists() and cover.exists():
        return "cached"
    if m.get("clip") and local_path(m["clip"]).is_file():  # ready-made clip: just copy it
        shutil.copy(local_path(m["clip"]), clip)
    elif src.is_file():
        ffmpeg_clip(src, clip, m.get("clip_start", 0), m.get("clip_len", 10))
    elif m.get("source_video"):
        print(f"    ! source_video not found: {src}")
    if m.get("cover") and local_path(m["cover"]).is_file():
        shutil.copy(local_path(m["cover"]), cover)
    elif clip.exists():
        ffmpeg_cover(clip, cover)
    return "ok" if cover.exists() else "nothing to do (set media.source_video or media.cover)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="only these game ids")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args()

    games = json.loads((ROOT / "games.json").read_text())["games"]
    failed = 0
    for g in games:
        if args.ids and g["id"] not in args.ids:
            continue
        out = MEDIA / g["id"]
        out.mkdir(parents=True, exist_ok=True)
        try:
            status = fetch_steam(g, out, args.force) if "steam" in g else fetch_local(g, out, args.force)
            if status != "cached" and "steam" in g:
                time.sleep(1.5)  # stay well under the store API rate limit
        except Exception as e:
            status, failed = f"FAILED: {e}", failed + 1
        print(f"  {g['id']:<22} {status}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
