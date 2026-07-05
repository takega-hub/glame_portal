# 15. GLAME — QA & Acceptance Checklist

## Identity

- [ ] Логотип GLAME — оригинальный asset.
- [ ] Логотип не набран текстом.
- [ ] G-знак — оригинальный asset.
- [ ] G-знак не упрощен.
- [ ] Пропорции G-знака сохранены.
- [ ] Паттерн не повернут.
- [ ] Паттерн не искажен.

---

## Photos

- [ ] Использовано реальное фото GLAME.
- [ ] Ялта не смешана с Симферополем.
- [ ] Не изменена архитектура.
- [ ] Не изменена вывеска.
- [ ] Не изменены материалы, мебель, витрины.
- [ ] Обработка только техническая.

---

## Navigation

- [ ] Top bar — live UI, not background.
- [ ] Bottom nav — live UI, not background.
- [ ] Top bar respects safeAreaTop.
- [ ] Bottom nav respects safeAreaBottom.
- [ ] Visible bottom bar = 96 px на 390–430W.
- [ ] Total bottom reserve = 96 px + safeAreaBottom.
- [ ] Над bottom nav есть 16–24 px воздуха.

---

## Hero

- [ ] CTA не заходят в нижнюю навигацию.
- [ ] Slide indicator above bottom nav.
- [ ] CTA positions unified across slides.
- [ ] First slide does not use `Смотреть новинки`.
- [ ] Hero background contains no UI.
- [ ] Top bar transparent overlay.

---

## UI

- [ ] Radius 0 px.
- [ ] Border 1 px.
- [ ] No rounded marketplace cards.
- [ ] No warm UI accents.
- [ ] No heavy shadows.
- [ ] Typography matches Clinica Pro.
- [ ] Spacing follows docs.

---

## Responsive

Check:
- [ ] iPhone Pro Max / 430W.
- [ ] iPhone standard / 390W.
- [ ] iPhone SE / smaller height.
- [ ] Android gesture navigation.

On all:
- [ ] text not clipped;
- [ ] CTA not overlapped;
- [ ] bottom nav not covering content;
- [ ] top bar not in system area;
- [ ] background crop preserves meaning.

---

## Logic

- [ ] CTA routes match docs.
- [ ] Whole panel clickable where action-panel.
- [ ] Service tiles not clickable if fixed.
- [ ] AI not duplicated inside stylist bottom sheet.
- [ ] Auth gates work.
- [ ] Stylist status works by Moscow time.

