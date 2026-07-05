# 02. GLAME — Navigation & Safe Area System

## Роль

Фиксирует правила верхнего и нижнего меню GLAME App с учетом разных устройств.

Top menu и bottom menu нельзя зашивать в PNG.  
Они являются живыми Flutter-компонентами.

---

## Базовая структура

```text
safeAreaTop
topNavigation
contentArea
bottomNavigation
safeAreaBottom
```

Формула:

```dart
final safeTop = MediaQuery.of(context).padding.top;
final safeBottom = MediaQuery.of(context).padding.bottom;
final topReserve = safeTop + topBarHeight;
final bottomReserve = bottomBarHeight + safeBottom;
```

---

## Top bar hero-блока

Зафиксировано:
- transparent overlay;
- logo center;
- search right;
- left side empty;
- cart only if cart has items;
- no white top bar in first Home carousel block.

Формула:

```text
topBarTop = safeAreaTop + 12–16 px
topBarHeight = 48–56 px
```

В пропорциях:

```text
topBarHeight = 0.11W–0.13W
topOffsetAfterSafeArea = 0.03W–0.04W
```

---

## Bottom bar

Стандарт GLAME:

```text
visibleBottomBar = 96 px
safeAreaBottom = system
totalBottomReserve = 96 px + safeAreaBottom
```

В пропорциях:

```text
visibleBottomBar = 0.22W–0.24W
totalBottomReserve = bottomBarHeight + safeAreaBottom
```

Для iPhone 14/15 Pro Max ориентир:

```text
visible bottom bar ≈ 96 px
safe area bottom ≈ 34 px
total occupied zone ≈ 130 px
```

Контент hero-слайдов, карточек и кнопок не должен попадать в эту зону.  
Над bottom bar оставлять 16–24 px воздуха.

---

## Hero content safe zone

```text
contentTopLimit = safeAreaTop + topBarHeight + 12–16 px
contentBottomLimit = screenHeight - bottomBarHeight - safeAreaBottom - 16–24 px
```

Внутри этой зоны:
- заголовок;
- описание;
- CTA;
- slide indicator.

---

## Что не входит в background image

Background не содержит:
- top logo;
- search icon;
- bottom nav;
- CTA;
- text;
- slide indicator;
- system status bar;
- G icon in nav.

Все это live UI.

---

## QA

- [ ] Logo не попадает в Dynamic Island.
- [ ] Search icon не попадает в system area.
- [ ] Bottom nav не перекрывает CTA.
- [ ] Slide indicator above bottom nav.
- [ ] G sign in bottom nav is original asset.
- [ ] Hero background contains no UI.
- [ ] CTA не уезжают под нижнее меню.

