# 14. GLAME — Cursor Execution Rules

## Base prompt

```text
You are implementing an approved GLAME App screen.

Do not redesign.
Do not reinterpret.
Do not invent missing visual elements.
Do not recreate the GLAME logo as text.
Do not recreate the GLAME G-sign as an icon.
Use only approved assets for logo, G-sign, patterns, and real store photos.
Preserve spacing, typography hierarchy, safe-area behavior, and component structure.
All sizes must follow provided responsive rules.
Top menu and bottom menu are live UI components, not part of the background image.
```

---

## Logo/sign

```text
Use approved logo asset only.
Use approved G-sign asset only.
Never approximate with Flutter Icon, text, or custom painter unless exact SVG path is provided.
Do not modify proportions.
Do not rotate.
Do not recolor outside approved color states.
```

---

## Real photos

```text
Use real store photos only.
Do not generate stores.
Do not redraw interiors.
Do not mix Yalta and Simferopol assets.
Do not alter architecture, signage, materials, furniture, objects, or proportions.
Allowed edits: crop, exposure, contrast, cool color correction, sharpness, gradient overlay.
```

---

## Safe area

```text
Respect MediaQuery safe areas.
Top bar = safeAreaTop + top offset + topBarHeight.
Bottom nav = visibleBottomBar + safeAreaBottom.
Hero content must stay above bottom nav + safeAreaBottom + 16-24 px.
```

---

## UI constraints

```text
Radius must be 0 px.
Borders must be 1 px.
No rounded marketplace cards.
No pill buttons.
No glassmorphism.
No warm UI accents.
No soft ecommerce shadows.
No decorative icons unless approved.
```

---

## Must ask before changing

Cursor/developer must ask before:
- changing text;
- changing CTA;
- replacing image;
- changing crop;
- changing icon;
- changing safe-area formulas;
- changing spacing;
- changing component behavior.

