#!/usr/bin/env python3
"""Turn the avatar cutout into the ASCII-art variants used by the landing page.

Usage:
    python tools/gen_ascii.py [cutout.png] [--preview DIR]

Input is a background-removed RGBA portrait (see README for how to make one).
Output is assets/ascii.js, which defines window.ASCII_VARIANTS.
Requires: pillow, numpy.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FONT = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"

# Terminal cell = 0.6em wide x 1.32em tall (JetBrains Mono advance / ascent+descent).
CELL_W, CELL_H = 0.6, 1.32
ROWS = 30
COLS = round(ROWS * CELL_H / CELL_W)  # square crop -> 66 columns

# Crop (x0, y0, x1, y1) on the 460x460 avatar: head and shoulders.
CROP = (100, 140, 360, 400)

EVERFOREST = {
    "bg0": "#2d353b", "bg1": "#343f44", "bg2": "#3d484d", "bg3": "#475258",
    "bg4": "#4f585e", "bg5": "#56635f", "grey0": "#7a8478", "grey1": "#859289",
    "grey2": "#9da9a0", "fg": "#d3c6aa", "red": "#e67e80", "orange": "#e69875",
    "yellow": "#dbbc7f", "green": "#a7c080", "aqua": "#83c092", "blue": "#7fbbb3",
    "purple": "#d699b6",
    "bg_red": "#514045", "bg_yellow": "#4d4c43", "bg_green": "#425047", "bg_visual": "#543a48",
}


def hex2rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def rgb2hex(c):
    return "".join(f"{int(v):02x}" for v in np.clip(c, 0, 255))


def to_lab(rgb):
    c = np.clip(np.asarray(rgb, dtype=np.float32) / 255, 0, 1)
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


# ----------------------------------------------------------------- image prep

def load(path):
    im = Image.open(path).convert("RGBA").crop(CROP)
    rgb = im.convert("RGB")
    alpha = im.split()[3]
    # local contrast + a bit of sharpening so features survive the downscale
    lum = ImageOps.grayscale(rgb)
    lum = ImageOps.equalize(lum, mask=alpha.point(lambda a: 255 if a > 128 else 0))
    lum = lum.filter(ImageFilter.UnsharpMask(radius=3, percent=120, threshold=2))
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))
    return rgb, lum, alpha


def grid(img, w, h, resample=Image.Resampling.BOX):
    return np.asarray(img.resize((w, h), resample), dtype=np.float32)


# ----------------------------------------------------------------- char ramp

RAMP = " .:-=+*#%@"
RAMP_LONG = " .'`,:;-~=+*?ozx#%8@"

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 - 0.5


def bayer(h, w):
    return BAYER4[np.arange(h)[:, None] % 4, np.arange(w)[None, :] % 4]


def pick_chars(levels, ramp=RAMP, dither=0.8):
    """levels in [0,1] -> glyph from a light-to-dense ramp.
    A little fixed-seed noise breaks up flat areas so they don't turn into rows of one glyph."""
    n = len(ramp) - 1
    noise = np.random.default_rng(7).uniform(-0.5, 0.5, levels.shape)
    idx = np.clip(np.round(levels * n + dither * noise), 0, n).astype(int)
    return np.array(list(ramp))[idx]


def contour_chars(lum, alpha, out, keep=0.22, coherence=0.45):
    """Overlay strong, well-oriented edges (hairline, jaw, eyes, silhouette) with - | / \\.

    Uses a per-cell structure tensor on a square-pixel version of the image, so each
    cell gets one dominant edge direction. `keep` is the share of subject cells drawn as edges.
    """
    sw, sh = 4, 9  # 0.6 : 1.32 cell ~ 4 : 9 square pixels
    W, H = COLS * sw, ROWS * sh
    l = np.asarray(lum.resize((W, H), Image.Resampling.LANCZOS), dtype=np.float32) / 255
    a = np.asarray(alpha.resize((W, H), Image.Resampling.BOX), dtype=np.float32) / 255
    img = Image.fromarray(((l * a) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.4))
    g = np.asarray(img, dtype=np.float32) / 255
    gy, gx = np.gradient(g)

    def cell(m):
        return m.reshape(ROWS, sh, COLS, sw).mean((1, 3))

    jxx, jyy, jxy = cell(gx * gx), cell(gy * gy), cell(gx * gy)
    mag = np.sqrt(jxx + jyy)
    coh = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2) / (jxx + jyy + 1e-9)
    theta = 0.5 * np.arctan2(2 * jxy, jxx - jyy)          # gradient direction
    edge = (np.degrees(theta) + 90) % 180                  # edge direction, y axis down

    subject = cell(a) > 0.15
    thr = np.quantile(mag[subject], 1 - keep)
    strong = subject & (mag >= thr) & (coh >= coherence)
    glyph = np.full(out.shape, "-", dtype=object)
    glyph[(edge >= 22.5) & (edge < 67.5)] = "\\"
    glyph[(edge >= 67.5) & (edge < 112.5)] = "|"
    glyph[(edge >= 112.5) & (edge < 157.5)] = "/"
    out = out.astype(object)
    out[strong] = glyph[strong]
    return out.astype(str)


# ----------------------------------------------------------------- variants

def tone(lum, mask, gamma=0.9, floor=0.12):
    """Normalise luminance on the subject; background -> 0, subject >= floor."""
    l = (lum / 255.0) ** gamma
    l = floor + (1 - floor) * l
    return np.where(mask > 0.5, l, 0.0)


def face_tone(lum, mask, head=0.55, lo=3, hi=97, contrast=6.0):
    """Stretch luminance using the head region only (the bright shirt would eat
    the range otherwise), then an S-curve so hair/beard vs skin read clearly."""
    h = lum.shape[0]
    region = lum[: int(h * head)][mask[: int(h * head)] > 0.5]
    a, b = np.percentile(region, [lo, hi])
    l = np.clip((lum - a) / max(b - a, 1), 0, 1)
    l = 1 / (1 + np.exp(-contrast * (l - 0.5)))
    l = (l - l.min()) / (l.max() - l.min())
    return np.where(mask > 0.5, l, 0.0)


def fade(h, strength=0.5, start=0.62):
    """Per-row brightness multiplier: 1 above `start`, easing down to 1-strength at the bottom."""
    y = np.linspace(0, 1, h)
    f = np.clip((y - start) / (1 - start), 0, 1) ** 1.2
    return (1 - strength * f)[:, None]


def mono_chars(rgb, lum, alpha):
    L = grid(lum, COLS, ROWS)
    A = grid(alpha, COLS, ROWS) / 255
    t = face_tone(L, A) * fade(ROWS, 0.4)
    out = pick_chars(0.2 + 0.8 * t, RAMP_LONG)
    out[A <= 0.5] = " "
    out = contour_chars(lum, alpha, out)
    return {"type": "text", "lines": ["".join(r) for r in out]}


def mono_shades(rgb, lum, alpha):
    L = grid(lum, COLS, ROWS)
    A = grid(alpha, COLS, ROWS) / 255
    t = tone(L, A, gamma=1.0, floor=0.2) * fade(ROWS)
    ramp = np.array([" ", "░", "▒", "▓", "█"])
    q = np.clip(np.round(t * 4), 0, 4).astype(int)
    q[(A > 0.5) & (q == 0)] = 1
    out = ramp[q]
    out[A <= 0.5] = " "
    return {"type": "text", "lines": ["".join(r) for r in out]}


def color_chars(rgb, lum, alpha):
    L = grid(lum, COLS, ROWS)
    A = grid(alpha, COLS, ROWS) / 255
    C = grid(rgb, COLS, ROWS)
    t = face_tone(L, A, contrast=4.0) * fade(ROWS, 0.3)
    out = pick_chars(0.25 + 0.75 * t, RAMP_LONG)
    out[A <= 0.5] = " "
    out = contour_chars(lum, alpha, out, keep=0.15)
    # glyphs only cover part of the cell, so lift the colour to keep it readable
    hsv = np.asarray(Image.fromarray(C.astype(np.uint8)).convert("HSV"), dtype=np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.25, 0, 255)
    hsv[..., 2] = np.clip(70 + hsv[..., 2] * 0.85, 0, 255)
    C = np.asarray(Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB"), dtype=np.float32)
    cols = "".join(rgb2hex(C[y, x]) for y in range(ROWS) for x in range(COLS))
    return {"type": "text", "lines": ["".join(r) for r in out], "colors": cols}


def braille(rgb, lum, alpha):
    W, H = COLS * 2, ROWS * 4
    L = grid(lum, W, H, Image.Resampling.LANCZOS) / 255
    A = grid(alpha, W, H) / 255
    L = np.where(A > 0.5, 0.08 + 0.92 * L, 0) * fade(H)
    # Floyd-Steinberg to 1 bit
    err = L.copy()
    bits = np.zeros_like(err, dtype=bool)
    for y in range(H):
        for x in range(W):
            old = err[y, x]
            new = 1.0 if old > 0.5 else 0.0
            bits[y, x] = new > 0
            e = old - new
            if A[y, x] <= 0.5:
                continue
            if x + 1 < W: err[y, x + 1] += e * 7 / 16
            if y + 1 < H:
                if x > 0: err[y + 1, x - 1] += e * 3 / 16
                err[y + 1, x] += e * 5 / 16
                if x + 1 < W: err[y + 1, x + 1] += e * 1 / 16
    dot = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08),
           (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80)]
    lines = []
    for r in range(ROWS):
        s = ""
        for c in range(COLS):
            v = 0
            for dx, dy, b in dot:
                if bits[r * 4 + dy, c * 2 + dx]:
                    v |= b
            s += chr(0x2800 + v) if v else " "
        lines.append(s)
    return {"type": "text", "lines": lines}


def half_pixels(rgb, lum, alpha, mode):
    W, H = COLS, ROWS * 2
    A = grid(alpha, W, H) / 255
    if mode == "color":
        C = grid(rgb, W, H, Image.Resampling.LANCZOS)
    elif mode == "duotone":
        L = tone(grid(lum, W, H, Image.Resampling.LANCZOS), A, gamma=0.85, floor=0.0) * fade(H, 0.45)
        stops = [hex2rgb(EVERFOREST["bg1"]), hex2rgb("#5a6b4a"), hex2rgb(EVERFOREST["green"]), hex2rgb("#e3ecc8")]
        pos = np.clip(L, 0, 1) * (len(stops) - 1)
        i = np.clip(pos.astype(int), 0, len(stops) - 2)
        f = (pos - i)[..., None]
        S = np.stack(stops)
        C = S[i] * (1 - f) + S[i + 1] * f
    elif mode == "palette":
        C = grid(rgb, W, H, Image.Resampling.LANCZOS)
        keys = ("bg2", "bg3", "bg4", "bg5", "bg_red", "bg_yellow", "bg_visual", "grey0", "grey1",
                "grey2", "fg", "orange", "yellow")
        pal = np.stack([hex2rgb(EVERFOREST[k]) for k in keys])
        # ordered (Bayer) dither so the picture keeps texture with few colours
        C = C * fade(H, 0.35)[..., None] + 18 * bayer(H, W)[..., None]
        lab, plab = to_lab(C), to_lab(pal)
        w = np.array([2.0, 0.75, 0.75])  # lightness matters most for a portrait
        d = (((lab[..., None, :] - plab[None, None]) * w) ** 2).sum(-1)
        C = pal[d.argmin(-1)]
    px = "".join(rgb2hex(C[y, x]) if A[y, x] > 0.5 else "------" for y in range(H) for x in range(W))
    return {"type": "pixels", "w": W, "h": H, "px": px}


VARIANTS = [
    ("mono-chars",   "mono · ascii",       "single colour, classic ASCII glyphs", mono_chars),
    ("mono-shades",  "mono · shade blocks", "single colour, ░▒▓█ blocks",          mono_shades),
    ("mono-braille", "mono · braille",     "single colour, braille dots ⣿",        braille),
    ("mono-half",    "mono · half blocks", "Everforest green tones, ▀▄ blocks",    lambda *a: half_pixels(*a, "duotone")),
    ("color-chars",  "color · ascii",      "photo colours, classic ASCII glyphs",  color_chars),
    ("color-half",   "color · half blocks", "photo colours, ▀▄ blocks",            lambda *a: half_pixels(*a, "color")),
    ("theme-half",   "theme · half blocks", "Everforest palette only, ▀▄ blocks", lambda *a: half_pixels(*a, "palette")),
]


def preview(v, path, scale=14):
    """Rough PNG preview (text drawn with the real font)."""
    cw, ch = round(scale * CELL_W), round(scale * CELL_H)
    img = Image.new("RGB", (COLS * cw, ROWS * ch), EVERFOREST["bg0"])
    d = ImageDraw.Draw(img)
    if v["type"] == "text":
        font = ImageFont.truetype(FONT, scale)
        cols = v.get("colors")
        for y, line in enumerate(v["lines"]):
            for x, c in enumerate(line):
                if c == " ":
                    continue
                fill = "#" + cols[(y * COLS + x) * 6:(y * COLS + x) * 6 + 6] if cols else EVERFOREST["green"]
                d.text((x * cw, y * ch), c, fill=fill, font=font)
    else:
        px = v["px"]
        for y in range(v["h"]):
            for x in range(v["w"]):
                h = px[(y * v["w"] + x) * 6:(y * v["w"] + x) * 6 + 6]
                if h != "------":
                    d.rectangle([x * cw, y * ch / 2, x * cw + cw - 1, (y + 1) * ch / 2 - 1], fill="#" + h)
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cutout", nargs="?", default=str(ROOT / "tools" / "avatar-cutout.png"))
    ap.add_argument("--preview", help="directory for PNG previews")
    args = ap.parse_args()

    rgb, lum, alpha = load(args.cutout)
    out = []
    for vid, label, desc, fn in VARIANTS:
        v = {"id": vid, "label": label, "desc": desc, "rows": ROWS, "cols": COLS, **fn(rgb, lum, alpha)}
        out.append(v)
        if args.preview:
            Path(args.preview).mkdir(parents=True, exist_ok=True)
            preview(v, Path(args.preview) / f"{vid}.png")
    js = "// generated by tools/gen_ascii.py, do not edit by hand\nwindow.ASCII_VARIANTS = " + json.dumps(out, ensure_ascii=False) + ";\n"
    (ROOT / "assets" / "ascii.js").write_text(js, encoding="utf-8")
    print(f"wrote {len(out)} variants, {len(js) // 1024} KiB")


if __name__ == "__main__":
    main()
