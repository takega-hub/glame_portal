from pathlib import Path
from collections import deque

from PIL import Image, ImageDraw

import render_bottom_nav_icons as base


BRAND_SIGN = Path(
    "C:/Users/takeg/YandexDisk/GLAME/GLAME BRANDBOOK/Restiling/Brand Assets/logos/png/glame_sign.png"
)
OUT = Path(__file__).resolve().parent / "bottom_nav_png"
OUT.mkdir(parents=True, exist_ok=True)


def remove_border_white(image):
    image = image.convert("RGBA")
    pixels = image.load()
    width, height = image.size
    visited = set()
    queue = deque()

    def is_background(x, y):
        r, g, b, a = pixels[x, y]
        return a > 0 and r > 246 and g > 246 and b > 246

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in visited or x < 0 or y < 0 or x >= width or y >= height:
            continue
        visited.add((x, y))
        if not is_background(x, y):
            continue
        pixels[x, y] = (255, 255, 255, 0)
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    return image


def crop_to_alpha(image, padding=72):
    alpha = image.getchannel("A")
    box = alpha.getbbox()
    if box is None:
        return image
    left, top, right, bottom = box
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)
    cropped = image.crop((left, top, right, bottom))
    side = max(cropped.width, cropped.height)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.alpha_composite(cropped, ((side - cropped.width) // 2, (side - cropped.height) // 2))
    return square


def prepare_brand_icon():
    source = Image.open(BRAND_SIGN)
    transparent = remove_border_white(source)
    cropped = crop_to_alpha(transparent)
    icon = cropped.resize((512, 512), Image.Resampling.LANCZOS)
    icon.save(OUT / "brand_glame_sign_transparent_512.png")
    return icon


def draw_nav(sheet, x, y, title, brand_icon, icon_drawers, dark=False):
    draw = ImageDraw.Draw(sheet)
    white = (246, 246, 242, 255)
    inactive = (122, 122, 116, 255)
    bar = (248, 248, 246, 255) if not dark else (16, 16, 16, 255)
    border = (225, 225, 220, 255) if not dark else (62, 62, 62, 255)

    draw.text((x, y - 56), title, fill=white, font=base.font(28, True))
    draw.rounded_rectangle((x, y, x + 820, y + 150), radius=44, fill=bar, outline=border, width=2)

    positions = [x + 72, x + 238, x + 404, x + 570, x + 736]
    sheet.alpha_composite(brand_icon.resize((68, 68), Image.Resampling.LANCZOS), (positions[0] - 34, y + 40))

    for index, (name, drawer) in enumerate(icon_drawers, start=1):
        icon = base.render_icon(
            f"tmp_brand_nav_{name}_{'dark' if dark else 'light'}",
            drawer,
            stroke=inactive,
        )
        sheet.alpha_composite(icon.resize((68, 68), Image.Resampling.LANCZOS), (positions[index] - 34, y + 40))


def main():
    brand_icon = prepare_brand_icon()
    white = (246, 246, 242, 255)
    muted = (170, 170, 164, 255)

    sheet = Image.new("RGBA", (2400, 1500), (17, 17, 17, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((120, 92), "GLAME / нижнее меню с фирменным знаком", fill=white, font=base.font(56, True))
    draw.text(
        (120, 152),
        "Первая иконка взята из брендбука. Белый фон удален, сам объемный знак сохранен.",
        fill=muted,
        font=base.font(30),
    )

    draw.text((120, 260), "Фирменный знак в PNG 512x512", fill=white, font=base.font(34, True))
    sheet.alpha_composite(brand_icon.resize((260, 260), Image.Resampling.LANCZOS), (120, 320))
    draw.text((420, 366), "Файл: brand_glame_sign_transparent_512.png", fill=(220, 220, 214, 255), font=base.font(28))
    draw.text((420, 410), "В навигации лучше тестировать в размере 24-28 dp: объемные грани могут стать очень тонкими.", fill=muted, font=base.font(24))

    variant_a = [
        ("jewelry_showcase", base.icon_jewelry_showcase),
        ("style_look", base.icon_style_look),
        ("selection_scan", base.icon_selection_scan),
        ("profile", base.icon_profile),
    ]
    variant_b = [
        ("jewelry_ring", base.icon_jewelry_ring),
        ("style_book", base.icon_style_book),
        ("selection_guides", base.icon_selection_guides),
        ("profile", base.icon_profile),
    ]

    draw_nav(sheet, 120, 700, "A: брендовый G + витрина / образ / скан", brand_icon, variant_a, dark=False)
    draw_nav(sheet, 120, 920, "A на черной панели", brand_icon, variant_a, dark=True)
    draw_nav(sheet, 120, 1160, "B: брендовый G + кольцо / лукбук / направляющие", brand_icon, variant_b, dark=False)

    sheet.save(OUT / "bottom_nav_icons_with_brand_preview_2400.png")

    for file in OUT.glob("tmp_brand_nav_*.png"):
        file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
