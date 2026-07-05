# 03. GLAME — Home Hero Slides Logic

## Роль

Первый блок Главной — вход в digital-пространство GLAME.  
Это не рекламные баннеры и не товарная витрина.

Hero должен создавать ощущение:
- пространства;
- доверия;
- стиля;
- персонализации;
- отсутствия случайности.

---

## Story flow

```text
Бренд →
Образ →
Повод →
Эмоция →
Сценарий →
Персонализация
```

---

## Слайды 01–07

### 01. Стиль внутри

Роль: brand + space + trust.  
Смысл: GLAME — реальное пространство + онлайн-подбор, не безликий магазин.

Текст:

```text
Стиль внутри

Украшения, которые собирают
образ под ваш стиль, задачу и повод.
Онлайн — по всей России.
```

CTA:
- `Собрать свой стиль` → `/selection`
- `Смотреть украшения` → `/catalog`

Использовать только реальное фото пространства Ялта.  
Фото не искажать.  
Логотип, top menu, bottom nav, CTA и текст — live UI, не часть фото.

---

### 02. Собранный образ

Роль: quiet luxury / complete look.

CTA:
- `Смотреть подборку` → `/collections/complete-look`
- `Подобрать под меня` → `/selection`

---

### 03. Подарок

Роль: gift scenario.

CTA:
- `Смотреть подарки` → `/collections/gift`
- `Подобрать подарок` → `/selection/gift`

Постоянная версия — фирменная упаковка без сезонных цветов.  
Цветы/8 марта не использовать для evergreen hero.

---

### 04. Акцентные украшения

Роль: statement / выразительность.

CTA:
- `Смотреть акценты` → `/collections/accent`
- `Подобрать под меня` → `/selection`

---

### 05. На отдых

Роль: resort / vacation.

CTA:
- `Смотреть подборку` → `/collections/resort`
- `Подобрать под меня` → `/selection`

Цветокоррекция: охладить, не уходить в оранжевый закат.

---

### 06. На свадьбу

Роль: wedding / occasion.

CTA:
- `Смотреть подборку` → `/collections/wedding`
- `Подобрать под меня` → `/selection`

---

### 07. Ваш стиль не из шаблона

Роль: entry to AI/stylist personalization.

CTA:
- `Начать подбор` → `/selection`
- `Написать стилисту` → `openStylistContact(source: 'hero_slide_07')`

---

## CTA system

Принцип:

```text
Primary CTA = действие по теме слайда
Secondary CTA = персональный подбор / стилист / каталог
```

Кнопки не должны прыгать между слайдами.

Стандарт:
- content area starts 28 px from left/right на 390–430 px;
- primary CTA width ≈ 300 px;
- height 56–58 px;
- secondary CTA below with 16 px gap;
- radius 0 px;
- border 1 px;
- after secondary CTA leave 34 px before slide indicator;
- slide indicator above bottom nav.

---

## Top bar

Для всех hero-слайдов:
- transparent overlay;
- no white header;
- logo centered;
- search right;
- cart only if items exist;
- safeAreaTop respected.

---

## Background image rules

Hero background передается отдельно:
- without text;
- without buttons;
- without top bar;
- without bottom nav;
- without slide indicator;
- without generated logo/sign.

