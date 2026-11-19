"""Draws the sample shop's product photos (renderer/static/sample_shop/): each garment laid flat from the front, on a
pale studio backdrop, as most shops photograph clothes. Made up, not any real product's photo. Each is drawn to its
size chart's middle size (the size a shop photographs, as the page assumes), so the photo's proportions agree with
the chart.

    python script/sample_shop/photos.py      # needs Pillow and NumPy

The shapes are in inches, x across from the garment's middle and y down from its top.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[2] / "renderer" / "static" / "sample_shop"
W, H = 1200, 1500
SS = 3  # drawn this many times larger, then shrunk: smooth edges
BACKDROP = (242, 240, 236)


def hexrgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


class Photo:
    """One photo: the garment's outline (a mask) and its details, darker or lighter than its cloth."""

    def __init__(self, width_in, top_in, bottom_in, fill=0.74):
        span = max(width_in / (W * fill), (bottom_in - top_in) / (H * 0.84))
        self.ppi = 1 / span
        self.top = top_in
        self.y0 = (H - (bottom_in - top_in) * self.ppi) / 2
        size = (W * SS, H * SS)
        self.mask = Image.new("L", size, 0)
        self.dark = Image.new("L", size, 0)
        self.light = Image.new("L", size, 0)
        self.ink = Image.new("L", size, 0)  # a print, in its own colour

    def px(self, x, y):
        return ((W / 2 + x * self.ppi) * SS, (self.y0 + (y - self.top) * self.ppi) * SS)

    def poly(self, layer, points, value=255, mirror=False):
        pts = [self.px(x, y) for x, y in points]
        if mirror:
            pts += [self.px(-x, y) for x, y in reversed(points)]
        ImageDraw.Draw(getattr(self, layer)).polygon(pts, fill=value)

    def line(self, layer, points, width_in, value=255):
        ImageDraw.Draw(getattr(self, layer)).line([self.px(x, y) for x, y in points], fill=value, width=max(1, round(width_in * self.ppi * SS)), joint="curve")

    def ellipse(self, layer, cx, cy, rx, ry, value=255, outline_in=None):
        a, b = self.px(cx - rx, cy - ry), self.px(cx + rx, cy + ry)
        draw = ImageDraw.Draw(getattr(self, layer))
        if outline_in:
            draw.ellipse([a, b], outline=value, width=max(1, round(outline_in * self.ppi * SS)))
        else:
            draw.ellipse([a, b], fill=value)

    def render(self, colour, path, texture="jersey", ink=(236, 230, 214), seed=1):
        rng = np.random.default_rng(seed)
        small = lambda image, blur=0: np.asarray((image.filter(ImageFilter.GaussianBlur(blur * SS)) if blur else image).resize((W, H), Image.LANCZOS), dtype=np.float32) / 255
        mask, dark, light, inked = small(self.mask), small(self.dark, 0.6), small(self.light, 0.6), small(self.ink)
        # The backdrop: a soft fall-off of light toward the corners, and the garment's faint shadow.
        yy, xx = np.mgrid[0:H, 0:W]
        fall = 1 - 0.012 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H * 0.45) / (H / 2)) ** 2)
        shadow = np.asarray(self.mask.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14)), dtype=np.float32) / 255
        shadow = np.roll(np.roll(shadow, 10, axis=0), 6, axis=1)
        back = np.array(BACKDROP, dtype=np.float32)[None, None, :] * (fall * (1 - 0.03 * shadow))[..., None]
        # The cloth: its colour, lit from above, its weave, its folds.
        grain = rng.normal(0, 1, (H, W)).astype(np.float32)
        if texture == "denim":
            twill = np.sin((xx + yy * 1.0) * 2 * math.pi / 5.0) * 0.5 + 0.5
            weave = 0.05 * (twill - 0.5) + 0.025 * grain
            fade = np.asarray(Image.fromarray((rng.random((H // 40, W // 40)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), dtype=np.float32) / 255
            weave += 0.06 * (fade - 0.5)
        elif texture == "rib":
            weave = 0.06 * (np.sin(xx * 2 * math.pi / 6.0) * 0.5) + 0.015 * grain
        elif texture == "nylon":
            weave = 0.008 * grain
        else:
            weave = 0.018 * grain
        folds = np.asarray(Image.fromarray((rng.random((H // 90, W // 90)) * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), dtype=np.float32) / 255
        lit = 1.04 - 0.08 * (yy / H) + 0.05 * (folds - 0.5) + weave
        shade = lit * (1 - 0.42 * dark) * (1 + 0.35 * light)
        cloth = np.array(hexrgb(colour), dtype=np.float32)[None, None, :] * shade[..., None]
        printed = np.array(ink, dtype=np.float32)[None, None, :] * (0.97 + 0.03 * grain[..., None])
        cloth = cloth * (1 - inked[..., None]) + printed * inked[..., None]
        out = back * (1 - mask[..., None]) + cloth * mask[..., None]
        OUT.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(OUT / path, quality=86, optimize=True, progressive=True)


def sleeve(shoulder, armpit, length, angle_deg, cuff):
    """A sleeve's outline (outer edge out from the shoulder point at an angle below level, its cuff, back in to the
    armpit), on the right of the garment."""
    a = math.radians(angle_deg)
    end = (shoulder[0] + length * math.cos(a), shoulder[1] + length * math.sin(a))
    inner = (end[0] - cuff * math.sin(a), end[1] + cuff * math.cos(a))
    return [shoulder, end, inner, armpit], end, inner


def tee():
    # M: chest 42 (21 flat), length 28, shoulders 18.25, sleeve 8.25.
    chest, length, shoulders, slv = 21, 28, 18.25, 8.25
    p = Photo(2 * (shoulders / 2 + slv * math.cos(math.radians(24))) + 1, -0.5, length + 0.5)
    neck = 3.6
    outline, end, inner = sleeve((shoulders / 2, 1.4), (chest / 2, 9.0), slv, 24, 6.6)
    right = [(neck, 0), *outline, (chest / 2, length - 0.2), (0, length + 0.15)]
    p.poly("mask", right, mirror=True)
    p.poly("mask", [(-neck, 0), (-neck * 0.5, 0.45), (0, 0.6), (neck * 0.5, 0.45), (neck, 0), (0, -0.05)])
    # The crew neck's rib (a round front neckline), the inside of the back showing above it.
    front = [(neck * math.cos(t), 0.1 + 2.9 * math.sin(t)) for t in np.linspace(0, math.pi, 25)]
    rib = [(1.18 * x, 0.1 + 1.25 * (y - 0.1)) for x, y in front]
    p.poly("dark", [(-neck, 0.05), (-neck * 0.55, 0.5), (0, 0.65), (neck * 0.55, 0.5), *front], 120)
    p.line("light", front, 0.2, 110)
    p.line("dark", rib, 0.06, 160)
    # A chest pocket, the sleeves' and the hem's stitching.
    p.line("dark", [(3.2, 6.2), (3.2, 11.0), (7.4, 11.0), (7.4, 6.2)], 0.06, 170)
    p.line("light", [(3.1, 6.2), (7.5, 6.2)], 0.12, 90)
    p.line("dark", [(-chest / 2 + 0.1, length - 0.9), (0, length - 0.55), (chest / 2 - 0.1, length - 0.9)], 0.05, 150)
    for sign in (1, -1):
        # The sleeve's hem stitching, a little in from its edge, and its seam.
        a, k = math.radians(24), 0.9
        p.line("dark", [(sign * (end[0] - k * math.cos(a)), end[1] - k * math.sin(a)), (sign * (inner[0] - k * math.cos(a)), inner[1] - k * math.sin(a))], 0.05, 150)
        p.line("dark", [(sign * shoulders / 2, 1.4), (sign * chest / 2, 9.0)], 0.05, 130)
    p.render("#9aa58a", "loopwheel-pocket-tee-sage-front.jpg", seed=11)


def hoodie(back=False):
    # M: chest 46 (23 flat), length 27.5, shoulders 20.25 (dropped), sleeve 24.5.
    chest, length, shoulders, slv = 23, 27.5, 20.25, 24.5
    angle = 66
    p = Photo(2 * (shoulders / 2 + slv * math.cos(math.radians(angle))) + 1.5, -8.2, length + 0.5)
    neck = 4.2
    outline, end, inner = sleeve((shoulders / 2, 1.8), (chest / 2, 10.5), slv, angle, 4.4)
    hem = chest / 2 * 0.92
    right = [(neck, 0), *outline, (chest / 2, length - 2.8), (hem, length - 2.6), (hem, length), (0, length)]
    p.poly("mask", right, mirror=True)
    hood = [(-6.6, 0.8), (-6.9, -3.5), (-5.8, -6.6), (-3.2, -8.0), (0, -8.2), (3.2, -8.0), (5.8, -6.6), (6.9, -3.5), (6.6, 0.8)]
    p.poly("mask", hood)
    # Ribbed cuffs and hem (a little darker), the sleeve's seam.
    p.poly("dark", [(-hem, length - 2.6), (hem, length - 2.6), (hem, length), (-hem, length)], 60)
    for sign in (1, -1):
        a = math.radians(angle)
        e, i = end, inner
        k = 2.8
        cuff = [(e[0] - k * math.cos(a), e[1] - k * math.sin(a)), e, i, (i[0] - k * math.cos(a), i[1] - k * math.sin(a))]
        p.poly("dark", [(sign * x, y) for x, y in cuff], 60)
        p.line("dark", [(sign * shoulders / 2, 1.8), (sign * chest / 2, 10.5)], 0.06, 140)
    if back:
        p.line("dark", [(0, -8.1), (0, 0.6)], 0.06, 120)
        p.line("dark", [(-6.5, 0.7), (0, 1.0), (6.5, 0.7)], 0.07, 120)
        p.render("#2f4a3a", "heavyweight-hoodie-forest-back.jpg", seed=23)
        return
    # The hood's opening (its lining in shadow), the drawcords, the kangaroo pocket.
    p.poly("dark", [(-4.6, 0.6), (-5.0, -3.2), (-3.6, -5.6), (0, -6.3), (3.6, -5.6), (5.0, -3.2), (4.6, 0.6), (2.4, 3.6), (0, 4.4), (-2.4, 3.6)], 150)
    p.line("light", [(-4.7, 0.6), (-2.4, 3.7), (0, 4.5), (2.4, 3.7), (4.7, 0.6)], 0.3, 80)
    p.line("light", [(-1.5, 3.9), (-1.7, 9.5)], 0.22, 120)
    p.line("light", [(1.5, 3.9), (1.6, 9.8)], 0.22, 120)
    pocket = [(-6.2, 16.0), (6.2, 16.0), (8.2, 21.0), (8.4, 24.7), (-8.4, 24.7), (-8.2, 21.0)]
    p.line("dark", pocket + [pocket[0]], 0.07, 160)
    p.line("dark", [(-6.2, 16.0), (-8.2, 21.0)], 0.35, 90)
    p.line("dark", [(6.2, 16.0), (8.2, 21.0)], 0.35, 90)
    # The ring graphic on the chest.
    p.ellipse("ink", 0, 10.4, 2.7, 2.7, outline_in=0.55)
    p.ellipse("ink", 0, 10.4, 0.7, 0.7)
    p.render("#2f4a3a", "heavyweight-hoodie-forest-front.jpg", seed=22)


def coach_jacket():
    # M: chest 46 (23 flat), length 28, shoulders 19.25, sleeve 25.5.
    chest, length, shoulders, slv = 23, 28, 19.25, 25.5
    angle = 68
    p = Photo(2 * (shoulders / 2 + slv * math.cos(math.radians(angle))) + 1.5, -1.6, length + 0.5)
    neck = 3.4
    outline, end, inner = sleeve((shoulders / 2, 1.5), (chest / 2, 10.0), slv, angle, 5.0)
    right = [(neck, 0), *outline, (chest / 2, length), (0, length)]
    p.poly("mask", right, mirror=True)
    # The collar: its stand behind the neck, its points over the front.
    p.poly("mask", [(-neck - 0.3, 0.2), (-neck, -1.4), (0, -1.6), (neck, -1.4), (neck + 0.3, 0.2)])
    for sign in (1, -1):
        p.poly("light", [(sign * (neck + 0.3), 0.1), (sign * 0.3, 1.2), (sign * 0.2, 3.6), (sign * 3.3, 4.0)], 70)
        p.line("dark", [(sign * (neck + 0.3), 0.1), (sign * 3.3, 4.0), (sign * 0.2, 3.6)], 0.07, 170)
        p.line("dark", [(sign * shoulders / 2, 1.5), (sign * chest / 2, 10.0)], 0.06, 140)
        a = math.radians(angle)
        k = 2.2
        p.line("dark", [(sign * (end[0] - k * math.cos(a)), end[1] - k * math.sin(a)), (sign * (inner[0] - k * math.cos(a)), inner[1] - k * math.sin(a))], 0.06, 160)
        # A slant pocket each side.
        p.line("dark", [(sign * 6.5, 15.5), (sign * 8.2, 21.5)], 0.25, 150)
    p.poly("dark", [(-neck, -1.4), (0, -1.6), (neck, -1.4), (neck - 0.3, -0.2), (0, 0.4), (-neck + 0.3, -0.2)], 90)
    # The snap placket down the front, and its snaps.
    p.line("dark", [(0, 1.3), (0, length)], 0.12, 210)
    p.line("dark", [(0.9, 3.8), (0.9, length - 0.1)], 0.05, 140)
    for y in (5.0, 9.5, 14.0, 18.5, 23.0):
        p.ellipse("light", 0.45, y, 0.32, 0.32)
        p.ellipse("dark", 0.45, y, 0.34, 0.34, outline_in=0.06)
    p.line("dark", [(-chest / 2 + 0.1, length - 1.0), (chest / 2 - 0.1, length - 1.0)], 0.05, 140)
    p.render("#a4532f", "nylon-coach-jacket-rust-front.jpg", texture="nylon", seed=33)


def jeans():
    # 31: waist 32.5 (16.25 flat), hip 21.5 flat, rise 11.75, thigh 12.75 flat, opening 8.25 flat, inseam 32.
    waist, hip, rise, opening, inseam = 16.25, 21.5, 11.75, 8.25, 32
    bottom = rise + inseam
    p = Photo(2 * (hip / 2 + 1.2) + 1, -0.4, bottom + 0.4, fill=0.6)
    out_hem = hip / 2 + 0.9
    in_hem = out_hem - opening
    right = [(0, 0), (waist / 2, 0), (hip / 2, 8.0), (hip / 2 + 0.4, rise + 2), (out_hem, bottom), (in_hem, bottom), (0.15, rise + 1.0), (0, rise)]
    p.poly("mask", right, mirror=True)
    # The waistband, belt loops, button fly, pockets, side seams' and hems' stitching (lighter thread on indigo).
    p.poly("dark", [(-waist / 2, 0), (waist / 2, 0), (waist / 2 + 0.2, 1.6), (-waist / 2 - 0.2, 1.6)], 50)
    p.line("light", [(-waist / 2 - 0.2, 1.6), (waist / 2 + 0.2, 1.6)], 0.05, 200)
    for x in (-6.4, -2.4, 6.4):
        p.poly("dark", [(x - 0.25, -0.1), (x + 0.25, -0.1), (x + 0.25, 1.9), (x - 0.25, 1.9)], 90)
    p.ellipse("light", 0, 0.8, 0.38, 0.38, 140)
    p.line("light", [(-1.6, 1.7), (-1.6, rise - 3.2), (-0.4, rise - 1.4)], 0.06, 200)
    for sign in (1, -1):
        p.line("light", [(sign * (waist / 2 - 3.6), 1.7), (sign * (waist / 2 - 2.6), 4.6), (sign * (waist / 2 + 0.45), 5.4)], 0.06, 200)
        p.line("dark", [(sign * (waist / 2 - 3.6), 1.7), (sign * (waist / 2 - 2.6), 4.6), (sign * (waist / 2 + 0.45), 5.4)], 0.18, 110)
        p.line("light", [(sign * (out_hem - 0.1), bottom - 1.0), (sign * (in_hem + 0.1), bottom - 1.0)], 0.05, 190)
        # Whiskers at the hips.
        for k in range(4):
            p.line("light", [(sign * (2.0 + 0.3 * k), 13.0 + 0.9 * k), (sign * (5.5 + 0.5 * k), 12.0 + 1.1 * k)], 0.12, 70)
        p.line("dark", [(sign * 0.2, rise + 1.0), (sign * in_hem, bottom)], 0.05, 120)
    p.render("#2c3e63", "relaxed-selvedge-jean-indigo-front.jpg", texture="denim", ink=(0, 0, 0), seed=44)


def dress():
    # M: bust 34 (17 flat), waist 28 (14 flat), hip 37 (18.5 flat), length 45 from the straps' top.
    bust, waist, hip, length = 17, 14, 18.5, 45
    top = 6.5
    p = Photo(2 * 11.8 + 1, -0.4, length + 0.4, fill=0.5)
    right = [(0, top), (bust / 2, top), (bust / 2, top + 2.5), (waist / 2, top + 9.5), (hip / 2, top + 17.5), (11.0, length - 1.0), (11.3, length), (0, length + 0.2)]
    p.poly("mask", right, mirror=True)
    for sign in (1, -1):
        p.poly("mask", [(sign * 4.0, -0.1), (sign * 4.55, -0.1), (sign * 5.35, top + 0.3), (sign * 4.8, top + 0.3)])
    # The square neckline's binding, a fold or two of the knit.
    p.line("light", [(-bust / 2, top + 0.25), (bust / 2, top + 0.25)], 0.12, 120)
    p.line("light", [(-2.0, top + 14), (-3.5, length - 2)], 0.6, 45)
    p.line("light", [(4.0, top + 18), (6.0, length - 3)], 0.5, 40)
    p.line("light", [(-11.0, length - 1.1), (11.0, length - 1.1)], 0.05, 110)
    p.render("#1d1e22", "rib-knit-midi-slip-dress-black-front.jpg", texture="rib", seed=55)


def skirt():
    # M: waist 28 (14 flat), hip 40 (20 flat, pleated), length 16.
    waist, length = 14, 16
    p = Photo(2 * 13.4 + 1, -0.4, length + 0.6, fill=0.66)
    band = 1.3
    hem = 13.0
    right = [(0, 0), (waist / 2, 0), (waist / 2 + 0.1, band), (hem, length - 0.2), (hem * 0.5, length + 0.25), (0, length + 0.3)]
    p.poly("mask", right, mirror=True)
    p.line("dark", [(-waist / 2, band), (waist / 2, band)], 0.06, 160)
    # Knife pleats: each a strip of shadow fanning out from the waistband to the hem.
    n = 18
    for k in range(n):
        f = (k + 0.5) / n
        x0 = -waist / 2 + waist * f
        x1 = -hem + 2 * hem * f
        p.line("dark", [(x0, band + 0.1), (x1, length)], 0.22, 140)
        p.line("light", [(x0 + 0.35, band + 0.1), (x1 + 0.6, length)], 0.15, 60)
    p.render("#5a2e48", "pleated-mini-skirt-plum-front.jpg", texture="twill", seed=66)


if __name__ == "__main__":
    tee()
    hoodie()
    hoodie(back=True)
    coach_jacket()
    jeans()
    dress()
    skirt()
    for path in sorted(OUT.glob("*.jpg")):
        print(path.name, path.stat().st_size)
