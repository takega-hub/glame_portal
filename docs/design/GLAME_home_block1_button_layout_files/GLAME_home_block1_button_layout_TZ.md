# GLAME — Home Block 1 / Hero carousel layout

## Canvas

- Base logical size: **430 × 932 px**
- Export scale: **1290 × 2796 px** for 3x preview/mockup
- Top bar: transparent overlay over hero photo
- Bottom reserve: **130 px total** = visible bottom bar **96 px** + Safe Area bottom **34 px**

## Top bar

- Background: transparent
- Logo: centered
- Search icon: right side, same horizontal line as logo
- Left side: empty
- Safe Area top: **59 px**
- Additional visual offset after Safe Area: **12–16 px**

## CTA fixed zone

All buttons on slides of the first Home carousel must stay in the same fixed location.

| Element | x | y | width | height | radius | border |
|---|---:|---:|---:|---:|---:|---:|
| Primary CTA | 28 | 602 | 300 | 58 | 0 | 0 |
| Secondary CTA | 28 | 676 | 300 | 58 | 0 | 1 |
| Slide indicator | 28 | 768 | — | — | — | — |

## Spacing

- Content left/right margin: **28 px**
- Primary → Secondary gap: **16 px**
- Secondary CTA bottom → slide indicator: **34 px**
- CTA font: **Clinica Pro Regular, 20 px**
- Body text: **17–19 px**, line-height **1.35–1.45**
- Bottom content must not enter the nav reserve zone.

## Bottom navigation

Visible bottom bar: **96 px**, from y=802 to y=898.  
Safe Area bottom: **34 px**, from y=898 to y=932.

Items:
1. G sign — **no label**
2. Украшения
3. Мой стиль
4. Подбор
5. Профиль

## Constructor rule

Hero photo/background is exported separately from live UI when possible.  
Top menu, bottom menu, CTA buttons, text, and slide indicator should be app/UI components, not baked into the photo.
