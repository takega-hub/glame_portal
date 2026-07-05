# GLAME APP — верхняя панель первого блока Главной

## Главное правило

В первом блоке Главной страницы верхняя панель должна быть прозрачной и накладываться поверх hero-визуала.

Белая верхняя плашка в первом блоке Главной страницы не используется.

Это правило относится к первому блоку / carousel hero на Главной странице.  
На остальных экранах верхняя панель может оставаться стандартной по UI-системе GLAME, если не утверждено иное.

---

## Состав верхней панели

| Зона | Элемент | Правило |
|---|---|---|
| Центр | Логотип GLAME | Всегда по центру |
| Справа | Поиск | Постоянный элемент |
| Справа рядом с поиском | Корзина / Ваш выбор | Только если в корзине есть товары |
| Слева | Пусто | Не ставить знак G и другие элементы |

---

## Safe Area iPhone

Логотип GLAME и иконка поиска должны быть опущены ниже с учетом верхней системной зоны iPhone:

- Dynamic Island;
- notch / «челка»;
- верхняя системная зона;
- черная вставка сверху.

### Правило размещения

Верхняя панель работает как overlay поверх hero-визуала.

Вертикальная позиция элементов:

```dart
final double topOffset = MediaQuery.of(context).padding.top + 12;
```

Допустимое значение дополнительного визуального отступа:

```dart
12–16 px after SafeArea top
```

Если на конкретных моделях iPhone логотип выглядит слишком высоко, использовать:

```dart
final double topOffset = MediaQuery.of(context).padding.top + 16;
```

---

## Рекомендуемые параметры

| Параметр | Значение |
|---|---:|
| Фон верхней панели | transparent |
| Позиция | overlay поверх hero image |
| SafeArea | обязательно учитывать |
| Дополнительный отступ после SafeArea | 12–16 px |
| Горизонтальные отступы | 24–28 px |
| Логотип | centered |
| Search icon | right |
| Left side | empty |
| Cart icon | only if cart has items |

---

## Flutter-пример

```dart
class GlameHeroTransparentTopBar extends StatelessWidget {
  final bool hasCartItems;
  final VoidCallback onSearchTap;
  final VoidCallback? onCartTap;

  const GlameHeroTransparentTopBar({
    super.key,
    required this.hasCartItems,
    required this.onSearchTap,
    this.onCartTap,
  });

  @override
  Widget build(BuildContext context) {
    final double topOffset = MediaQuery.of(context).padding.top + 12;

    return Positioned(
      top: topOffset,
      left: 24,
      right: 24,
      child: SizedBox(
        height: 44,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Center(
              child: Image.asset(
                'assets/images/logo_glame_white.png',
                height: 30,
                fit: BoxFit.contain,
              ),
            ),

            Positioned(
              right: hasCartItems ? 44 : 0,
              child: IconButton(
                icon: const Icon(
                  Icons.search,
                  size: 28,
                  color: Colors.white,
                ),
                onPressed: onSearchTap,
              ),
            ),

            if (hasCartItems)
              Positioned(
                right: 0,
                child: IconButton(
                  icon: const Icon(
                    Icons.shopping_bag_outlined,
                    size: 27,
                    color: Colors.white,
                  ),
                  onPressed: onCartTap,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
```

---

## Использование внутри первого слайда

```dart
Stack(
  children: [
    Positioned.fill(
      child: Image.asset(
        'assets/images/home_slide_01.jpg',
        fit: BoxFit.cover,
      ),
    ),

    const Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0x66000000),
              Color(0x00000000),
              Color(0x99000000),
            ],
          ),
        ),
      ),
    ),

    GlameHeroTransparentTopBar(
      hasCartItems: false,
      onSearchTap: () {
        // TODO: open search
      },
    ),

    // Text, CTA-zone, slide indicator, etc.
  ],
)
```

---

## Запреты

- Не использовать белый фон верхней панели в первом блоке Главной.
- Не ставить знак G сверху.
- Не ставить избранное сверху.
- Не показывать пустую корзину постоянно.
- Не размещать логотип в зоне Dynamic Island / notch.
- Не вшивать верхнее меню в фоновое изображение, если оно добавляется конструктором.
- Не менять структуру верхнего меню от слайда к слайду.
- Не использовать графический паттерн в верхней панели.

---

## Связь с фоновыми изображениями для конструктора

Если фоновые изображения слайдов загружаются в конструктор приложения отдельно:

- верхнее меню не должно быть вшито в изображение;
- логотип не должен быть частью картинки;
- иконка поиска не должна быть частью картинки;
- сверху изображения нужно сохранять визуальную зону, чтобы transparent top bar читался поверх hero-визуала;
- контраст в верхней части изображения должен позволять читать белый или графитовый логотип.
