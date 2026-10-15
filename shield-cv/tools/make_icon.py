#!/usr/bin/env python3
"""Generate the SHIELD-CV desktop icon v2 (assets/shield.ico + shield.png).

v2 — best-engineer pass:
  * deep-space navy tile with radar grid + vignette (defence ops feel)
  * glass shield: cyan→blue gradient face, bright edge highlight, inner glow
  * AI circuit nodes on the shield shoulders (intelligence layer hint)
  * bold green check with soft glow (assurance = pass)
  * micro tricolour bar at the base (Made for India, subtle)
  * high-contrast silhouette so 16px taskbar stays readable

Run:  .venv/Scripts/python.exe tools/make_icon.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_ICO = ROOT / "assets" / "shield.ico"
OUT_PNG = ROOT / "assets" / "shield.png"

SIZE = 1024


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _draw(size: int = SIZE):
    from PIL import Image, ImageDraw, ImageFilter

    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")

    # -- tile: vertical gradient navy -------------------------------------
    top, bot = (16, 48, 88), (5, 9, 16)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=_lerp(top, bot, y / max(1, S - 1)) + (255,))

    # -- radar grid (faint concentric + crosshair) -------------------------
    cx, cy = S / 2, S * 0.46
    grid_col = (56, 120, 180, 34)
    for r in (0.10, 0.18, 0.26, 0.34):
        rr = int(S * r)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=grid_col, width=max(2, S // 512))
    d.line([(cx - S * 0.36, cy), (cx + S * 0.36, cy)], fill=grid_col, width=max(2, S // 512))
    d.line([(cx, cy - S * 0.36), (cx, cy + S * 0.36)], fill=grid_col, width=max(2, S // 512))

    # -- vignette (darken edges) -------------------------------------------
    vig = Image.new("L", (S, S), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([-S * 0.25, -S * 0.25, S * 1.25, S * 1.25], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(S // 8))
    dark = Image.new("RGBA", (S, S), (0, 0, 0, 110))
    img = Image.composite(img, Image.new("RGBA", (S, S), (0, 0, 0, 255)), vig).convert("RGBA")
    img.alpha_composite(dark, (0, 0))
    d = ImageDraw.Draw(img, "RGBA")

    # rounded mask reused at the end
    r = int(S * 0.24)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=r, fill=255)

    # -- shield geometry ----------------------------------------------------
    w, h = S * 0.50, S * 0.58
    sy = S * 0.155
    pts = [(cx - w / 2, sy), (cx + w / 2, sy),
           (cx + w / 2, sy + h * 0.40), (cx, sy + h),
           (cx - w / 2, sy + h * 0.40)]

    # drop shadow
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh, "RGBA").polygon([(x, y + S * 0.022) for x, y in pts],
                                       fill=(0, 0, 0, 130))
    sh = sh.filter(ImageFilter.GaussianBlur(S // 64))
    img.alpha_composite(sh)
    d = ImageDraw.Draw(img, "RGBA")

    # shield face: cyan(top) -> blue(bottom), clipped to shield scanlines
    c_top, c_bot = (64, 224, 255), (24, 110, 235)
    ymin, ymax = int(sy), int(sy + h)
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(ymin, ymax, 2):
        t = (y - ymin) / max(1, ymax - ymin)
        col = _lerp(c_top, c_bot, t) + (255,)
        # scanline intersect of shield polygon (convex-ish: use full width slice)
        # approximate: interpolate left/right edges
        if y <= sy + h * 0.40:
            xl, xr = cx - w / 2, cx + w / 2
        else:
            k = (y - (sy + h * 0.40)) / (h * 0.60)
            xl = (cx - w / 2) + (w / 2) * k
            xr = (cx + w / 2) - (w / 2) * k
        d.line([(xl, y), (xr, y)], fill=col, width=2)

    # inner dark glass face
    inset = S * 0.038
    pts2 = [(cx - w / 2 + inset, sy + inset),
            (cx + w / 2 - inset, sy + inset),
            (cx + w / 2 - inset, sy + h * 0.40),
            (cx, sy + h - inset * 1.5),
            (cx - w / 2 + inset, sy + h * 0.40)]
    d.polygon(pts2, fill=(8, 20, 36, 245))
    # top gloss streak
    gloss = [(cx - w / 2 + inset * 1.6, sy + inset * 1.7),
             (cx + w / 2 - inset * 1.6, sy + inset * 1.7),
             (cx + w / 2 - inset * 2.2, sy + inset * 2.6),
             (cx - w / 2 + inset * 2.2, sy + inset * 2.6)]
    d.polygon(gloss, fill=(140, 230, 255, 60))

    # bright edge highlight (left/top lighter)
    d.polygon(pts, outline=(170, 245, 255, 255), width=max(4, S // 170))

    # -- AI circuit nodes on shoulders --------------------------------------
    node_c = (150, 235, 255, 255)
    trace_c = (90, 180, 230, 150)
    lw = max(3, S // 220)
    for sx in (-1, 1):
        x0 = cx + sx * w * 0.30
        y0 = sy + h * 0.16
        x1 = cx + sx * w * 0.22
        y1 = sy + h * 0.26
        d.line([(x0, y0), (x1, y1)], fill=trace_c, width=lw)
        for (nx, ny, nr) in ((x0, y0, S * 0.011), (x1, y1, S * 0.014)):
            d.ellipse([nx - nr, ny - nr, nx + nr, ny + nr], fill=node_c)

    # -- check mark with glow ------------------------------------------------
    cw, chh = S * 0.25, S * 0.155
    ox, oy = cx - cw * 0.44, sy + h * 0.40
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gg = ImageDraw.Draw(glow)
    gw = max(10, S // 40)
    gg.line([(ox, oy), (ox + cw * 0.38, oy + chh * 0.62)],
            fill=(48, 209, 88, 90), width=gw * 3, joint="curve")
    gg.line([(ox + cw * 0.38, oy + chh * 0.62), (ox + cw, oy - chh * 0.55)],
            fill=(48, 209, 88, 90), width=gw * 3, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(S // 90))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img, "RGBA")
    cw_w = max(12, S // 42)
    d.line([(ox, oy), (ox + cw * 0.38, oy + chh * 0.62)],
           fill=(52, 230, 100, 255), width=cw_w, joint="curve")
    d.line([(ox + cw * 0.38, oy + chh * 0.62), (ox + cw, oy - chh * 0.55)],
           fill=(52, 230, 100, 255), width=cw_w, joint="curve")

    # -- tricolour base bar (subtle India accent) -----------------------------
    bw, bh = S * 0.30, max(6, S // 128)
    bx, by = cx - bw / 2, sy + h + S * 0.045
    third = bw / 3
    d.rectangle([bx, by, bx + third, by + bh], fill=(255, 153, 51, 255))
    d.rectangle([bx + third, by, bx + 2 * third, by + bh], fill=(240, 240, 240, 255))
    d.rectangle([bx + 2 * third, by, bx + bw, by + bh], fill=(19, 136, 8, 255))

    # -- tile border + rounded corners ----------------------------------------
    d.rounded_rectangle([S * 0.008, S * 0.008, S * 0.992, S * 0.992],
                        radius=r, outline=(56, 200, 235, 255),
                        width=max(4, S // 200))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


def main() -> None:
    base = _draw(SIZE)
    base.save(OUT_PNG)
    base.resize((256, 256)).save(
        OUT_ICO, sizes=[(16, 16), (32, 32), (48, 48),
                        (64, 64), (128, 128), (256, 256)])
    print(f"wrote {OUT_ICO} + {OUT_PNG}")


if __name__ == "__main__":
    main()
