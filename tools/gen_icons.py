"""Generates icons/icon-{192,512}[-maskable].png.

Dev-only tool — needs Pillow (`pip install pillow` into .venv; deliberately not
added to requirements.txt, which is the engine/tests' dependency list, not the
web app's). Not part of the shipping app; run by hand when the source logo changes.

Two modes:
  - icons/source-logo.png exists  -> use it (owner's real logo).
  - it doesn't                    -> generate a plain placeholder so the PWA is
    installable today. Swapping in the real file later means re-running this
    script; nothing else in the app changes.

Run: ./.venv/Scripts/python.exe tools/gen_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "icons"
ICONS.mkdir(exist_ok=True)
SOURCE = ICONS / "source-logo.png"

BG = (0, 0, 0, 255)              # the source logo's own background is already black
ACCENT = (192, 38, 211, 255)     # #c026d3 — placeholder only; real logo is already colored

SIZES = [192, 512]
# Maskable icons get cropped to a centered circle by Android launchers — content
# needs to live inside roughly the middle 80% (safe zone), or it gets clipped.
MASKABLE_SAFE_RATIO = 0.8


def make_placeholder(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)
    # A simple bold "L" mark — obviously a placeholder, not trying to be a real logo.
    try:
        font = ImageFont.truetype("arialbd.ttf", int(size * 0.6))
    except OSError:
        font = ImageFont.load_default()
    text = "L"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, font=font, fill=ACCENT)
    return img


def make_maskable(base: Image.Image, size: int) -> Image.Image:
    """Pad `base` (already `size`x`size`) into a safe-zone-centered version on a
    solid background, so Android's circular mask doesn't clip the content."""
    canvas = Image.new("RGBA", (size, size), BG)
    inner = int(size * MASKABLE_SAFE_RATIO)
    scaled = base.resize((inner, inner), Image.LANCZOS)
    offset = (size - inner) // 2
    canvas.paste(scaled, (offset, offset), scaled if scaled.mode == "RGBA" else None)
    return canvas


def main():
    if SOURCE.exists():
        print(f"using real logo: {SOURCE}")
        src = Image.open(SOURCE).convert("RGBA")
    else:
        print("no icons/source-logo.png yet — generating a placeholder (swap in the real file and re-run)")
        src = None

    for size in SIZES:
        base = src.resize((size, size), Image.LANCZOS) if src else make_placeholder(size)
        base.save(ICONS / f"icon-{size}.png")

        maskable = make_maskable(base, size)
        maskable.save(ICONS / f"icon-{size}-maskable.png")

        print(f"  wrote icon-{size}.png, icon-{size}-maskable.png")


if __name__ == "__main__":
    main()
