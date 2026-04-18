"""Generate OCR test fixture images."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int = 24) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a TrueType font, fall back to default."""
    # Try common Windows fonts
    for font_path in [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_fixtures(output_dir: Path) -> None:
    """Generate all OCR test fixture images."""
    output_dir.mkdir(parents=True, exist_ok=True)
    font = _get_font(24)

    # hello_world.png — white background, black text "hello world"
    img = Image.new("RGB", (400, 100), "white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 30), "hello world", fill="black", font=font)
    img.save(output_dir / "hello_world.png")

    # chinese.png — white background, black text "你好世界"
    try:
        cn_font = _get_font(28)
        img2 = Image.new("RGB", (400, 100), "white")
        draw2 = ImageDraw.Draw(img2)
        draw2.text((50, 30), "你好世界", fill="black", font=cn_font)
        img2.save(output_dir / "chinese.png")
    except Exception:
        # Fallback: just save a blank image if Chinese font not available
        img2 = Image.new("RGB", (400, 100), "white")
        img2.save(output_dir / "chinese.png")

    # empty.png — pure white
    img3 = Image.new("RGB", (400, 100), "white")
    img3.save(output_dir / "empty.png")


if __name__ == "__main__":
    generate_fixtures(Path(__file__).parent)
