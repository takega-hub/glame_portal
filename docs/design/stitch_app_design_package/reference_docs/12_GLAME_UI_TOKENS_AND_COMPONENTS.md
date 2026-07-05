# 12. GLAME — UI Tokens & Components

## Colors

```yaml
colors:
  graphite: "#222426"
  near_black: "#0E1012"
  steel_gray: "#8E9397"
  cold_light_gray: "#C7CBCF"
  white: "#EFF1F2"
  border_gray: "#5C6064"
  soft_gray: "#D8DADB"
```

---

## Typography

Main font:

```text
Clinica Pro Regular
```

Use as font asset.  
Do not replace with similar font without approval.

---

## Geometry

```yaml
radius: 0px
border: 1px
button_height: 56-58px
primary_button_width: 300px on 390-430W
```

---

## Spacing

На ширине 390–430 px:

```yaml
page_horizontal_padding: 28px
button_gap: 16px
gap_after_secondary_cta_to_indicator: 34px
content_air_above_bottom_nav: 16-24px
```

В пропорциях:

```yaml
page_horizontal_padding: 0.065W-0.07W
primary_button_width: 0.70W-0.77W
button_height: 0.13W-0.14W
bottom_air: 0.04W-0.055W
```

---

## Hero CTA

Primary:
- height 56–58 px;
- width ≈ 300 px;
- radius 0;
- fill white on dark background;
- text graphite.

Secondary:
- height 56–58 px;
- width ≈ 300 px;
- radius 0;
- transparent fill;
- border 1 px;
- text white on dark background.

---

## Bottom nav

```yaml
visible_height: 96px
safe_area_bottom: system
active_icon: original_G_asset
inactive_icons: approved line icons
```

G-sign only original asset.

---

## Top bar

```yaml
position: fixed_overlay
background: transparent
logo: centered_original_asset
search: right
left: empty
cart: only_if_items_exist
top_offset: safeAreaTop + 12-16px
height: 48-56px
```

---

## Action panel

```yaml
radius: 0
border: 1px
number_column: left
title: main
description: secondary
arrow: right
whole_panel_clickable: true
```

---

## Service tile

```yaml
layout: 2x2
clickable: false
radius: 0
border: 1px
number: top
title: middle
description: bottom
```

