#!/usr/bin/env python3
"""Render a faces-free cover + preview clip for Blobby Knockout from the game's own art.

Writes assets/blobby-knockout/cover.jpg and clip.mp4 (committed, so a fresh clone
has them). Needs Pillow and ffmpeg; only re-run if you want to change the look.

    python3 tools/make_blobby_media.py
"""
import math, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "games/blobby-knockout/data"
OUT = ROOT / "assets/blobby-knockout"
W, H, FPS, SECONDS = 854, 480, 30, 8
COLORS = [(40, 90, 255), (235, 50, 60), (60, 200, 90), (250, 200, 30), (170, 80, 220), (255, 130, 40)]


def keyed(path, scale):
    """Load a sprite with black as the transparent colour."""
    im = Image.open(path).convert("RGB")
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    mask = im.convert("L").point(lambda v: 255 if v > 12 else 0)
    im.putalpha(mask)
    return im


def tint(sprite, color):
    gray = sprite.convert("L")
    r, g, b = (gray.point(lambda v, c=c: v * c // 255) for c in color)
    out = Image.merge("RGB", (r, g, b))
    out.putalpha(sprite.getchannel("A"))
    return out


def font(size):
    return ImageFont.truetype(str(DATA / "fonts/Fredoka-SemiBold.ttf"), size)


def scene(t, title):
    bg = Image.open(DATA / "backgrounds/strand2.bmp").convert("RGB")
    bg = bg.crop((0, 90, 800, 540)).resize((W, H), Image.LANCZOS)
    frame = bg.convert("RGBA")
    blob = keyed(DATA / "gfx/blobbym1.bmp", 1.15)

    # Queue of waiting blobs at the back of the beach, bobbing.
    for i, color in enumerate(COLORS[2:]):
        b = tint(blob, color).resize((blob.width // 2, blob.height // 2))
        x = 60 + i * 52
        y = 205 - int(8 * abs(math.sin(t * 3 + i)))
        frame.alpha_composite(b, (x, y))

    # Ball flying back and forth over the net, the two active blobs jumping to hit it.
    period = 2.0
    phase = (t % period) / period
    left_to_right = int(t / period) % 2 == 0
    p = phase if left_to_right else 1 - phase
    bx = 170 + p * (W - 340)
    by = 330 - math.sin(phase * math.pi) * 220
    for side, color in ((0, COLORS[0]), (1, COLORS[1])):
        hitting = (side == 0 and (phase < 0.12 if left_to_right else phase > 0.88)) or \
                  (side == 1 and (phase > 0.88 if left_to_right else phase < 0.12))
        jump = 40 if hitting else 0
        x = 130 if side == 0 else W - 130 - blob.width
        frame.alpha_composite(tint(blob, color), (x, 440 - blob.height - jump))
    ball = keyed(DATA / f"gfx/ball{1 + int(t * 12) % 16:02d}.bmp", 0.75)
    frame.alpha_composite(ball, (int(bx - ball.width / 2), int(by - ball.height / 2)))

    if title:
        d = ImageDraw.Draw(frame)
        for text, size, y in (("BLOBBY KNOCKOUT", 64, 26), ("up to 8 players · miss and you're out", 26, 100)):
            f = font(size)
            w = d.textlength(text, font=f)
            shadow = Image.new("RGBA", frame.size)
            ImageDraw.Draw(shadow).text(((W - w) / 2, y + 3), text, font=f, fill=(0, 0, 0, 200))
            frame.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(3)))
            d.text(((W - w) / 2, y), text, font=f, fill=(255, 255, 255))
    return frame.convert("RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    scene(0.35, title=True).resize((616, 346)).save(OUT / "cover.jpg", quality=90)
    ff = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "24",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / "clip.mp4")],
        stdin=subprocess.PIPE)
    for i in range(FPS * SECONDS):
        ff.stdin.write(scene(i / FPS, title=False).tobytes())
    ff.stdin.close()
    ff.wait()
    print("wrote", OUT / "cover.jpg", OUT / "clip.mp4")


if __name__ == "__main__":
    main()
