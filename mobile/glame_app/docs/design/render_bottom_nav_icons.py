from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent / "bottom_nav_png"
OUT.mkdir(parents=True, exist_ok=True)

FONT_REGULAR = Path("C:/Windows/Fonts/arial.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/arialbd.ttf")


def font(size, bold=False):
    path = FONT_BOLD if bold and FONT_BOLD.exists() else FONT_REGULAR
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_icon(name, drawer, stroke=(17, 17, 17, 255), fill=None, size=512):
    scale = 4
    image = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    drawer(draw, scale, stroke, fill)
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    image.save(OUT / f"{name}.png")
    return image


def line(draw, pts, scale, color, width=22):
    draw.line([(x * scale, y * scale) for x, y in pts], fill=color, width=width * scale, joint="curve")


def arc(draw, box, start, end, scale, color, width=22):
    draw.arc(tuple(v * scale for v in box), start=start, end=end, fill=color, width=width * scale)


def ellipse(draw, box, scale, outline, width=22, fill=None):
    draw.ellipse(tuple(v * scale for v in box), outline=outline, width=width * scale, fill=fill)


def rect(draw, box, scale, outline, width=22, radius=0, fill=None):
    box = tuple(v * scale for v in box)
    if radius:
        draw.rounded_rectangle(box, radius=radius * scale, outline=outline, width=width * scale, fill=fill)
    else:
        draw.rectangle(box, outline=outline, width=width * scale, fill=fill)


def polygon(draw, pts, scale, outline, width=22, fill=None):
    points = [(x * scale, y * scale) for x, y in pts]
    if fill:
        draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=outline, width=width * scale, joint="curve")


def icon_glame_g(draw, scale, stroke, fill):
    arc(draw, (116, 112, 396, 392), 35, 330, scale, stroke, 28)
    line(draw, [(260, 256), (404, 256), (404, 374)], scale, stroke, 28)
    line(draw, [(404, 374), (344, 374)], scale, stroke, 28)


def icon_jewelry_showcase(draw, scale, stroke, fill):
    rect(draw, (98, 150, 414, 380), scale, stroke, 20, radius=8)
    arc(draw, (166, 62, 346, 242), 196, 344, scale, stroke, 22)
    line(draw, [(158, 252), (354, 252)], scale, stroke, 20)
    line(draw, [(178, 316), (334, 316)], scale, stroke, 16)


def icon_jewelry_ring(draw, scale, stroke, fill):
    ellipse(draw, (142, 158, 370, 386), scale, stroke, 24)
    polygon(draw, [(196, 162), (236, 76), (276, 76), (316, 162)], scale, stroke, 22)
    line(draw, [(216, 160), (296, 160)], scale, stroke, 18)


def icon_style_look(draw, scale, stroke, fill):
    line(draw, [(256, 92), (178, 142), (178, 390)], scale, stroke, 22)
    line(draw, [(256, 92), (334, 142), (334, 390)], scale, stroke, 22)
    line(draw, [(132, 390), (380, 390)], scale, stroke, 22)
    line(draw, [(196, 230), (316, 230)], scale, stroke, 18)
    line(draw, [(218, 142), (218, 390)], scale, stroke, 14)
    line(draw, [(294, 142), (294, 390)], scale, stroke, 14)


def icon_style_book(draw, scale, stroke, fill):
    rect(draw, (118, 108, 256, 406), scale, stroke, 20, radius=8)
    rect(draw, (256, 108, 394, 406), scale, stroke, 20, radius=8)
    line(draw, [(256, 120), (256, 394)], scale, stroke, 16)
    line(draw, [(148, 190), (224, 190)], scale, stroke, 14)
    line(draw, [(288, 190), (364, 190)], scale, stroke, 14)


def icon_selection_scan(draw, scale, stroke, fill):
    line(draw, [(120, 174), (120, 104), (190, 104)], scale, stroke, 22)
    line(draw, [(322, 104), (392, 104), (392, 174)], scale, stroke, 22)
    line(draw, [(392, 338), (392, 408), (322, 408)], scale, stroke, 22)
    line(draw, [(190, 408), (120, 408), (120, 338)], scale, stroke, 22)
    ellipse(draw, (156, 156, 356, 356), scale, stroke, 18)
    line(draw, [(196, 256), (316, 256)], scale, stroke, 18)
    line(draw, [(256, 196), (256, 316)], scale, stroke, 18)


def icon_selection_guides(draw, scale, stroke, fill):
    line(draw, [(132, 172), (220, 172)], scale, stroke, 22)
    line(draw, [(292, 172), (380, 172)], scale, stroke, 22)
    line(draw, [(132, 340), (220, 340)], scale, stroke, 22)
    line(draw, [(292, 340), (380, 340)], scale, stroke, 22)
    ellipse(draw, (226, 226, 286, 286), scale, stroke, 18)
    line(draw, [(256, 130), (256, 382)], scale, stroke, 16)


def icon_profile(draw, scale, stroke, fill):
    ellipse(draw, (178, 104, 334, 260), scale, stroke, 22)
    arc(draw, (116, 254, 396, 488), 200, 340, scale, stroke, 22)
    line(draw, [(128, 408), (384, 408)], scale, stroke, 22)


def paste_icon(sheet, icon, x, y, label, title_font, label_font, color=(245, 245, 242, 255)):
    sheet.alpha_composite(icon.resize((96, 96), Image.Resampling.LANCZOS), (x, y))
    draw = ImageDraw.Draw(sheet)
    draw.text((x + 48, y + 112), label, fill=color, font=label_font, anchor="mt")


def nav_bar(sheet, x, y, variant_name, icons, dark=False):
    draw = ImageDraw.Draw(sheet)
    bar_color = (248, 248, 246, 255) if not dark else (16, 16, 16, 255)
    border = (225, 225, 220, 255) if not dark else (62, 62, 62, 255)
    text_color = (238, 238, 234, 255)
    icon_color = (22, 22, 22, 255) if not dark else (246, 246, 242, 255)
    inactive = (122, 122, 116, 255)
    draw.text((x, y - 56), variant_name, fill=text_color, font=font(28, True))
    draw.rounded_rectangle((x, y, x + 820, y + 150), radius=44, fill=bar_color, outline=border, width=2)
    positions = [x + 72, x + 238, x + 404, x + 570, x + 736]
    labels = ["G", "Украшения", "Мой стиль", "Подбор", "Профиль"]
    for index, (icon_name, drawer) in enumerate(icons):
        color = icon_color if index == 0 else inactive
        icon = render_icon(f"tmp_{icon_name}_{'dark' if dark else 'light'}", drawer, stroke=color)
        sheet.alpha_composite(icon.resize((72, 72), Image.Resampling.LANCZOS), (positions[index] - 36, y + 38))
        if index == 0:
            dot_color = icon_color
            draw.ellipse((positions[index] - 4, y + 18, positions[index] + 4, y + 26), fill=dot_color)
        draw.text((positions[index], y + 122), labels[index], fill=(150, 150, 145, 255), font=font(14), anchor="mm")


def main():
    black = (20, 20, 20, 255)
    white = (246, 246, 242, 255)
    gray = (118, 118, 112, 255)

    selected = [
        ("glame_g", icon_glame_g),
        ("jewelry_showcase", icon_jewelry_showcase),
        ("style_look", icon_style_look),
        ("selection_scan", icon_selection_scan),
        ("profile", icon_profile),
    ]
    alternatives = [
        ("glame_g", icon_glame_g),
        ("jewelry_ring", icon_jewelry_ring),
        ("style_book", icon_style_book),
        ("selection_guides", icon_selection_guides),
        ("profile", icon_profile),
    ]

    for name, drawer in selected:
        render_icon(f"a_{name}_black_512", drawer, stroke=black)
        render_icon(f"a_{name}_white_512", drawer, stroke=white)
        render_icon(f"a_{name}_gray_512", drawer, stroke=gray)
    for name, drawer in alternatives[1:4]:
        render_icon(f"b_{name}_black_512", drawer, stroke=black)

    sheet = Image.new("RGBA", (2400, 1600), (17, 17, 17, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((120, 92), "GLAME / PNG иконки нижнего меню", fill=white, font=font(56, True))
    draw.text(
        (120, 152),
        "Первый знак оставлен без изменения. Остальные показаны крупно и в реальном контексте нижнего меню.",
        fill=(170, 170, 164, 255),
        font=font(30),
    )

    draw.text((120, 260), "Вариант A: витрина / образ / скан", fill=white, font=font(34, True))
    labels = ["Главная", "Украшения", "Мой стиль", "Подбор", "Профиль"]
    for i, (name, drawer) in enumerate(selected):
        icon = render_icon(f"preview_a_{name}", drawer, stroke=white)
        paste_icon(sheet, icon, 140 + i * 205, 330, labels[i], font(24, True), font(23))

    nav_bar(sheet, 120, 560, "A на белой панели", selected, dark=False)
    nav_bar(sheet, 120, 780, "A на черной панели", selected, dark=True)

    draw.text((120, 1060), "Вариант B: кольцо / лукбук / направляющие", fill=white, font=font(34, True))
    for i, (name, drawer) in enumerate(alternatives):
        icon = render_icon(f"preview_b_{name}", drawer, stroke=white)
        paste_icon(sheet, icon, 140 + i * 205, 1130, labels[i], font(24, True), font(23))

    draw.text((1260, 260), "Прозрачные PNG", fill=white, font=font(34, True))
    draw.text((1260, 306), "Сохранены отдельно в 512x512:", fill=(170, 170, 164, 255), font=font(27))
    file_list = [
        "a_glame_g_black_512.png",
        "a_jewelry_showcase_black_512.png",
        "a_style_look_black_512.png",
        "a_selection_scan_black_512.png",
        "a_profile_black_512.png",
        "и белые/серые версии для A",
    ]
    for i, text in enumerate(file_list):
        draw.text((1260, 360 + i * 44), text, fill=(220, 220, 214, 255), font=font(25))

    sheet.save(OUT / "bottom_nav_icons_preview_2400.png")

    for file in OUT.glob("tmp_*.png"):
        file.unlink(missing_ok=True)
    for file in OUT.glob("preview_*.png"):
        file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
