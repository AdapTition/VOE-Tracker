"""Draws «Як запустити.png» — the one-step SmartScreen instruction shipped in the zip."""
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 520
BG, INK, MUTED, ACCENT, BLUE = "#f6f6f3", "#1d1d1b", "#6b6b66", "#ea580c", "#0067c0"


def font(size, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    try:
        return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
    except OSError:
        return ImageFont.load_default()


def main(out: str) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((56, 44), "Як запустити VOE Explorer", font=font(38, True), fill=INK)
    d.text((56, 100), "Якщо Windows показала синє вікно „Windows захистила ваш ПК“:", font=font(24), fill=MUTED)

    steps = [("1", "натисніть „Докладніше“", "(маленьке посилання під текстом)"),
             ("2", "потім „Усе одно запустити“", "(кнопка з'явиться внизу вікна)")]
    y = 170
    for num, text, hint in steps:
        d.ellipse((56, y, 112, y + 56), fill=ACCENT)
        d.text((84, y + 28), num, font=font(30, True), fill="white", anchor="mm")
        d.text((136, y + 2), text, font=font(32, True), fill=INK)
        d.text((136, y + 44), hint, font=font(20), fill=MUTED)
        y += 120

    d.rounded_rectangle((56, 420, W - 56, 480), radius=12, fill="white", outline="#e7e7e2")
    d.text((80, 450), "Це потрібно лише один раз. Програма безпечна — вона лише читає сайт voe.com.ua.",
           font=font(20), fill=BLUE, anchor="lm")
    img.save(out)


if __name__ == "__main__":
    main(sys.argv[1])
