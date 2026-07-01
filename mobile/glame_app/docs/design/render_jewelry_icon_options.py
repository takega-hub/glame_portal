from pathlib import Path

from PIL import Image, ImageDraw

import render_bottom_nav_icons as base
from render_bottom_nav_icons_with_brand import prepare_brand_icon


OUT = Path(__file__).resolve().parent / "bottom_nav_png"
OUT.mkdir(parents=True, exist_ok=True)


def icon_jewelry_ring_clean(draw, scale, stroke, fill):
    base.ellipse(draw, (150, 170, 362, 382), scale, stroke, 24)
    base.line(draw, [(214, 170), (236, 104), (276, 104), (298, 170)], scale, stroke, 22)
    base.line(draw, [(236, 104), (256, 74), (276, 104)], scale, stroke, 20)


def icon_jewelry_earring(draw, scale, stroke, fill):
    base.ellipse(draw, (184, 76, 328, 220), scale, stroke, 22)
    base.line(draw, [(256, 220), (256, 298)], scale, stroke, 22)
    base.ellipse(draw, (202, 298, 310, 406), scale, stroke, 22)
    base.line(draw, [(224, 352), (288, 352)], scale, stroke, 16)


def icon_jewelry_pendant(draw, scale, stroke, fill):
    base.line(draw, [(166, 110), (256, 196), (346, 110)], scale, stroke, 22)
    base.line(draw, [(256, 196), (256, 252)], scale, stroke, 20)
    base.polygon(draw, [(256, 250), (332, 326), (256, 416), (180, 326)], scale, stroke, 22)
    base.line(draw, [(220, 326), (292, 326)], scale, stroke, 16)


def icon_jewelry_chain(draw, scale, stroke, fill):
    base.arc(draw, (132, 86, 380, 334), 18, 162, scale, stroke, 22)
    base.ellipse(draw, (176, 270, 262, 356), scale, stroke, 18)
    base.ellipse(draw, (250, 270, 336, 356), scale, stroke, 18)
    base.line(draw, [(232, 314), (280, 314)], scale, stroke, 16)


def icon_jewelry_stud_pair(draw, scale, stroke, fill):
    base.ellipse(draw, (132, 132, 248, 248), scale, stroke, 22)
    base.ellipse(draw, (264, 132, 380, 248), scale, stroke, 22)
    base.line(draw, [(190, 248), (190, 354)], scale, stroke, 20)
    base.line(draw, [(322, 248), (322, 354)], scale, stroke, 20)
    base.ellipse(draw, (158, 344, 222, 408), scale, stroke, 18)
    base.ellipse(draw, (290, 344, 354, 408), scale, stroke, 18)


def draw_option(sheet, x, y, title, drawer):
    white = (246, 246, 242, 255)
    muted = (170, 170, 164, 255)
    icon = base.render_icon(f"jewelry_option_{title.lower().replace(' ', '_')}", drawer, stroke=white)
    sheet.alpha_composite(icon.resize((190, 190), Image.Resampling.LANCZOS), (x, y))
    draw = ImageDraw.Draw(sheet)
    draw.text((x + 95, y + 214), title, fill=white, font=base.font(25, True), anchor="mt")
    draw.text((x + 95, y + 248), "512 PNG", fill=muted, font=base.font(20), anchor="mt")


def draw_nav(sheet, y, brand_icon, jewelry_drawer, title):
    draw = ImageDraw.Draw(sheet)
    x = 120
    white = (246, 246, 242, 255)
    inactive = (122, 122, 116, 255)
    draw.text((x, y - 50), title, fill=white, font=base.font(30, True))
    draw.rounded_rectangle((x, y, x + 820, y + 150), radius=44, fill=(248, 248, 246, 255), outline=(225, 225, 220, 255), width=2)
    positions = [x + 72, x + 238, x + 404, x + 570, x + 736]
    sheet.alpha_composite(brand_icon.resize((68, 68), Image.Resampling.LANCZOS), (positions[0] - 34, y + 40))
    icons = [
        ("jewelry_nav", jewelry_drawer),
        ("style_look", base.icon_style_look),
        ("selection_scan", base.icon_selection_scan),
        ("profile", base.icon_profile),
    ]
    for index, (name, drawer) in enumerate(icons, start=1):
        icon = base.render_icon(f"tmp_jewelry_nav_{name}_{title}", drawer, stroke=inactive)
        sheet.alpha_composite(icon.resize((68, 68), Image.Resampling.LANCZOS), (positions[index] - 34, y + 40))


def main():
    brand_icon = prepare_brand_icon()
    white = (246, 246, 242, 255)
    muted = (170, 170, 164, 255)
    black = (17, 17, 17, 255)

    options = [
        ("Ring", icon_jewelry_ring_clean),
        ("Earring", icon_jewelry_earring),
        ("Pendant", icon_jewelry_pendant),
        ("Chain", icon_jewelry_chain),
        ("Pair", icon_jewelry_stud_pair),
    ]

    for name, drawer in options:
        base.render_icon(f"jewelry_{name.lower()}_black_512", drawer, stroke=black)
        base.render_icon(f"jewelry_{name.lower()}_white_512", drawer, stroke=white)
        base.render_icon(f"jewelry_{name.lower()}_gray_512", drawer, stroke=(122, 122, 116, 255))

    sheet = Image.new("RGBA", (2400, 1550), (17, 17, 17, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((120, 92), "GLAME / варианты иконки 'Украшения'", fill=white, font=base.font(56, True))
    draw.text(
        (120, 152),
        "Вторая иконка должна считываться как украшение, а не как витрина или магазин.",
        fill=muted,
        font=base.font(30),
    )

    for index, (name, drawer) in enumerate(options):
        draw_option(sheet, 120 + index * 285, 260, name, drawer)

    draw_nav(sheet, 650, brand_icon, icon_jewelry_ring_clean, "В меню: Ring")
    draw_nav(sheet, 890, brand_icon, icon_jewelry_earring, "В меню: Earring")
    draw_nav(sheet, 1130, brand_icon, icon_jewelry_pendant, "В меню: Pendant")

    sheet.save(OUT / "jewelry_icon_options_preview_2400.png")

    for file in OUT.glob("tmp_jewelry_nav_*.png"):
        file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
