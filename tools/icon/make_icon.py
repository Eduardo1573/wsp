"""
Generate the home-screen icons: the word KBTU in Bricolage Grotesque ExtraBold,
amber on warm near-black — the same two tokens the app uses (--accent, --bg).

iOS ignores SVG for apple-touch-icon and applies its own rounded-corner mask, so
these are full-bleed PNGs with no baked-in radius.

    ./.venv/bin/python tools/icon/make_icon.py
"""
from PIL import Image, ImageDraw, ImageFont

BG = (0x12, 0x10, 0x0E)      # --bg  dark
FG = (0xFF, 0xB4, 0x54)      # --accent
WORD = "KBTU"
SUPER = 4                    # supersample factor for clean edges
TRACKING = -0.020            # matches the CSS -.022em display tracking
FONT = "tools/icon/Bricolage.ttf"


def load_font(px):
    f = ImageFont.truetype(FONT, px)
    # opsz 96 = display optical size, wght 800 = ExtraBold, wdth 100
    f.set_variation_by_axes([96, 800, 100])
    return f


def widths(font, word, track_px):
    """Per-glyph advances plus tracking, and the total inked width."""
    adv = [font.getlength(c) for c in word]
    total = sum(adv) + track_px * (len(word) - 1)
    return adv, total


def render(size, target_ratio=0.74):
    S = size * SUPER
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)

    # binary-search the point size so the word fills target_ratio of the width
    lo, hi = 10, S
    while hi - lo > 1:
        mid = (lo + hi) // 2
        f = load_font(mid)
        _, total = widths(f, WORD, TRACKING * mid)
        if total <= S * target_ratio:
            lo = mid
        else:
            hi = mid
    font = load_font(lo)
    track = TRACKING * lo
    adv, total = widths(font, WORD, track)

    # optical centring: use the ink bbox, not the advance box
    bbox = d.textbbox((0, 0), WORD, font=font)
    x = (S - total) / 2
    y = (S - (bbox[3] - bbox[1])) / 2 - bbox[1]

    for ch, a in zip(WORD, adv):
        d.text((x, y), ch, font=font, fill=FG)
        x += a + track

    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    # 180 = modern iPhone home screen; 152/167 = iPad; 192/512 = PWA manifest
    for size in (152, 167, 180, 192, 512):
        out = f"web/icon-{size}.png"
        render(size).save(out, optimize=True)
        print(f"  wrote {out}")
