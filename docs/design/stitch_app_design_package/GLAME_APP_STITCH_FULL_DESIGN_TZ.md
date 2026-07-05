# GLAME App — полное ТЗ для Stitch на сборку дизайна клиентского приложения

Версия: 2026-06-16  
Цель: собрать в Stitch цельный mobile-first дизайн клиентского приложения GLAME с учетом всех утвержденных дизайн-наработок, текущей Flutter-реализации, витринных сценариев, образов, сборки образов, кабинета, избранного, AI-подбора и живого стилиста.

---

## 1. Роль Stitch

Stitch должен собрать не отдельный лендинг и не набор несвязанных экранов, а целостное клиентское приложение GLAME.

Результат должен показывать:

- полный пользовательский путь от первого входа до покупки;
- витрину украшений, брендов, пространств и образов;
- сценарии персонального подбора: AI-подбор по фото и живой стилист;
- разделы “Мой стиль”, избранное, сборку образов и look-feed;
- кабинет покупателя, корзину, checkout, заказы, бонусы;
- авторизацию и auth-gate для закрытых действий;
- единый визуальный язык GLAME на всех экранах.

Stitch не должен придумывать новую айдентику. Он должен привести уже согласованные решения к единой дизайн-системе и применить их ко всем страницам.

---

## 2. Главная идея продукта

GLAME — premium digital-пространство для выбора украшений. Это не маркетплейс и не обычный jewelry e-commerce.

Ключевой смысл:

> GLAME помогает выбрать украшение без случайности: через curated-витрину, образы, AI-подбор, живого стилиста и реальные пространства для примерки.

Приложение должно ощущаться как продолжение физических пространств GLAME: бетон, стекло, металл, холодный свет, архитектура, воздух, точная геометрия.

---

## 3. Айдентика и обязательные правила

### 3.1. Запрещено

- Перерисовывать логотип GLAME.
- Генерировать логотип или G-знак.
- Набирать GLAME похожим шрифтом.
- Делать warm beige/gold luxury UI.
- Делать rounded marketplace cards.
- Делать pill buttons.
- Использовать glow, bokeh, glassmorphism, мягкие ecommerce-тени.
- Дорисовывать реальные пространства, менять мебель, вывеску, интерьер.
- Смешивать фото Ялты и Симферополя.
- Зашивать top bar, bottom nav, кнопки, текст и slide indicators внутрь PNG.

### 3.2. Разрешено

- Использовать оригинальные assets логотипа и G-знака.
- Использовать реальные фото пространств с crop, cool color correction, exposure/contrast correction.
- Использовать утвержденный GLAME-pattern как архитектурную фактуру.
- Использовать тонкие overlay/gradient слои для читаемости поверх фото.

### 3.3. Цвета

```yaml
graphite: "#222426"
near_black: "#0E1012"
steel_gray: "#8E9397"
cold_light_gray: "#C7CBCF"
soft_gray: "#D8DADB"
white_glame: "#EFF1F2"
border_gray: "#5C6064"
surface_white: "#FFFFFF"
text_primary: "#222426"
text_secondary: "#6F7478"
```

### 3.4. Типографика

Основной шрифт: Clinica Pro Regular.  
Если Stitch не может подключить шрифт, использовать максимально нейтральный geometric sans только как временный fallback, но явно отметить замену.

Правила:

- Не использовать отрицательный letter-spacing.
- Не масштабировать шрифт от ширины viewport.
- Hero-заголовки крупные, но компактные панели и карточки не должны получать hero-scale typography.
- Все длинные брендовые названия показывать полностью, без троеточий.

### 3.5. Геометрия

```yaml
radius: 0px
border: 1px
button_height: 56-58px
mobile_page_padding: 28px
bottom_nav_visible_height: 96px
top_bar_height: 48-56px
```

---

## 4. Навигационная система

### 4.1. Нижнее меню

Mobile bottom nav всегда live UI:

1. G-знак / Главная
2. Украшения
3. Мой стиль
4. Подбор
5. Профиль

Правила:

- visible height: 96 px + safe area bottom;
- G-знак только оригинальным asset;
- labels короткие;
- активное состояние спокойное, без ярких marketplace colors;
- bottom nav не перекрывает CTA и slide indicators.

### 4.2. Верхнее меню

Для hero/home:

- transparent overlay;
- logo centered;
- справа menu/search/cart в зависимости от сценария;
- слева пусто или back на внутренних страницах;
- top safe area обязателен.

Для внутренних страниц:

- светлый или графитовый header по контексту;
- centered original logo;
- back слева;
- actions справа: избранное, корзина, меню, если нужно.

### 4.3. Drawer / меню справа

Раскрывающееся меню должно содержать:

- Главная
- Украшения
- Мой стиль
- Подбор
- Профиль
- Новинки
- Коллекции
- Бренды
- Пространства
- Сервис
- Сертификат
- Вход/Выход

---

## 5. Информационная архитектура приложения

### 5.1. Основные маршруты

```text
/onboarding
/home
/catalog
/product/:id
/brands
/brand/:id
/collections/:slug
/spaces
/spaces/:slug
/selection
/selection/gift
/selection/ai-photo
/photo-upload
/photo-review
/photo-analysis
/photo-selection-result
/stylist-chat
/looks-profile
/look/:id
/checkout
/login
/auth/register
/auth/otp
/auth/change-password
```

### 5.2. Основные пользовательские зоны

1. Вход и onboarding.
2. Главная как последовательный story-flow.
3. Каталог и карточка товара.
4. Бренды и страницы брендов.
5. Пространства GLAME.
6. Образы / look-feed / сборка образа.
7. Мой стиль / избранное.
8. AI-подбор по фото.
9. Живой стилист.
10. Корзина и checkout.
11. Кабинет покупателя.
12. Auth, SMS, регистрация, пароль.

---

## 6. Главные клиентские пути

### 6.1. Путь “Вдохновение → покупка”

```text
Home hero
→ Новое в GLAME
→ карточка товара
→ product detail
→ добавить в корзину
→ checkout
→ заказ оформлен
```

### 6.2. Путь “Не знаю, что выбрать”

```text
Home hero / Подбор
→ Selection screen
→ AI-подбор или живой стилист
→ рекомендации
→ товар / образ / стилист
→ корзина
```

### 6.3. Путь “Подбор по фото”

```text
Home block 3 или block 6
→ /selection/ai-photo
→ если гость: auth gate
→ загрузка/камера
→ review фото
→ анализ
→ результат
→ персональные товары + объяснение
→ сохранить / открыть товар / написать стилисту
```

### 6.4. Путь “Стилист”

```text
Hero slide 07 / block 6 / product / wishlist / bottom nav
→ stylist bottom sheet
→ quick tags + message
→ если гость: auth gate
→ /stylist-chat
→ сообщения, фото, товары, looks, stores
→ товар / каталог / пространство / checkout
```

### 6.5. Путь “Образ”

```text
Home / Мой стиль / Looks
→ look-feed
→ look detail
→ товары образа
→ сохранить образ
→ заменить товар через стилиста или AI
→ добавить товары в корзину
```

### 6.6. Путь “Бренд”

```text
Home block 4
→ /brands
→ brand detail
→ категории бренда
→ подборка GLAME по бренду
→ catalog filtered by brand
→ product
```

### 6.7. Путь “Пространство”

```text
Home block 5
→ /spaces
→ /spaces/yalta или /spaces/simferopol
→ построить маршрут / написать стилисту / смотреть наличие в городе
```

### 6.8. Путь “Личный кабинет”

```text
Профиль
→ если гость: login/register
→ данные покупателя
→ заказы
→ бонусы
→ покупки
→ предпочтения
→ выход
```

---

## 7. Главная страница

Главная должна быть mobile-first, полноэкранная по блокам, с живым top bar и bottom nav.

### 7.1. Block 1 — Hero carousel

Роль: вход в digital-пространство GLAME.

Слайды:

1. Стиль внутри
2. Собранный образ
3. Подарок
4. Акцентные украшения
5. На отдых
6. На свадьбу
7. Ваш стиль не из шаблона

Слайд 01:

```text
Стиль внутри
Украшения, которые собирают образ под ваш стиль, задачу и повод.
Онлайн — по всей России.
```

CTA:

- Собрать свой стиль → `/selection`
- Смотреть украшения → `/catalog`

Hero CTA на 430×932:

- primary: x 28, y 602, w 300, h 58;
- secondary: x 28, y 676, w 300, h 58;
- indicator: x 28, y 768.

Top/bottom nav не являются частью фото.

### 7.2. Block 2 — Новое в GLAME

Структура:

1. Заголовок `Новое в GLAME`
2. Ссылка `Все новинки`
3. Описание
4. Большая editorial drop card
5. Product mini cards horizontal carousel

Обновленное правило:

- в mini cards не показывать цены;
- heart icon только контурный, без белой подложки;
- если в образе/дропе 6 товаров, пользователь должен свайпом увидеть все 6.

Не превращать в marketplace grid.

### 7.3. Block 3 — Подбор по фото

Один сценарий: AI-подбор по фото.

CTA:

- Загрузить фото → `/selection/ai-photo`
- Какое фото подойдет? → instruction bottom sheet

Гость может читать, но не может загрузить фото. На upload action показывать auth gate.

### 7.4. Block 4 — Собрано GLAME

Роль: показать curated universe GLAME.

Текст:

```text
Собрано GLAME
Мы отбираем главное. Чтобы вы выбирали свое.
```

CTA: `Смотреть бренды` → `/brands`

Бренды:

- Geometry
- Magna
- Pearl
- Crystal
- Bicolor
- Prism Of Elegance
- UNOde50
- Raganella Princess
- Island Soul
- AGafi
- Antura
- Kalliope
- Wrinkles of Time
- Claudio Canzian

Названия брендов никогда не сокращать троеточием.

### 7.5. Block 5 — Пространства GLAME

Роль: trust layer, реальные физические пространства.

Карточки:

- Ялта: Набережная им. Ленина, 18, Приморский пляж.
- Симферополь: ул. Севастопольская, 62, 1 этаж.

CTA каждой карточки: `Смотреть пространство`.

Использовать только реальные фото соответствующего пространства.

### 7.6. Block 6 — Как выбрать и купить

Финальный сервисный блок, не FAQ и не отдельная сервисная страница.

Заголовок:

```text
Как выбрать
и купить
```

3 action-panels:

1. Самостоятельно — каталог, бренды и подборки → `/catalog`
2. С живым стилистом — онлайн или в пространстве → stylist sheet
3. Через AI-подбор — по фото, форме, масштабу и стилю → `/selection/ai-photo`

Сервисная зона 2×2, не кликабельна:

- Примерка перед покупкой
- Детали до заказа
- Гарантия и уход
- Поддержка и Клуб стильных

Важно: в текущей продуктовой версии можно использовать атмосферное фото магазина как фон, если оно нравится команде; поверх фото нужны холодный overlay, тонкие линии и читаемость.

---

## 8. Каталог / витрина украшений

### 8.1. Роль

Каталог — основная витрина. Он должен быть функциональным, но не выглядеть как generic marketplace.

### 8.2. Состав

- Header с логотипом.
- Название раздела: Каталог / Новинки / Коллекции / название подборки.
- Search.
- Фильтры и категории.
- Сетка товаров.
- Infinite scroll / load more.
- Состояния loading, empty, error.

### 8.3. Категории

- Все
- Кольца
- Серьги
- Колье
- Браслеты
- Каффы
- NEW
- SALE

### 8.4. Карточка товара в каталоге

Показывать:

- фото;
- бренд/линия;
- название;
- цена;
- наличие / доставка;
- heart/save;
- quick open product.

Правила:

- radius 0;
- border 1;
- фото не искажать;
- не использовать sale badges как marketplace;
- heart не должен выглядеть как add-to-cart;
- сохранить товар → “Мой стиль” / избранное.

---

## 9. Карточка товара

### 9.1. Состав страницы

- App bar: back, logo, favorite, cart.
- Image gallery / carousel.
- Бренд / линия.
- Название.
- Артикул.
- Цена или диапазон цен.
- Варианты изделия, если есть.
- Наличие и доставка.
- Описание.
- Характеристики.
- Loyalty points.
- CTA: добавить в корзину.
- CTA/secondary: написать стилисту.
- Looks с этим товаром.
- Рекомендации.
- Недавно просмотренные.

### 9.2. Сервисные действия

- Favorite → добавляет в “Мой стиль”.
- Add to cart → корзина.
- Stylist → bottom sheet с контекстом `product_id`.
- Share/copy article, если требуется.

### 9.3. Визуальные правила

- Product image hero чистый и крупный.
- Не перегружать карточку декоративными блоками.
- CTA фиксировать в нижней action-zone на mobile, если возможно.
- Детали и характеристики раскрывать аккуратными секциями.

---

## 10. Бренды

### 10.1. `/brands`

Роль: curated brand universe.

Состав:

- Hero / editorial header.
- Список всех брендов в единой системе.
- Для каждого: название, signature phrase.
- Без деления на “наши / не наши”.
- Клик → `/brand/:id`.

### 10.2. `/brand/:id`

Состав:

- Brand hero.
- Signature / DNA markers.
- Описание.
- Категории бренда.
- Выбор GLAME в бренде.
- Product grid.
- Use cases.
- CTA: смотреть все изделия бренда.
- CTA: написать стилисту по бренду.

Брендовые названия не сокращать.

---

## 11. Пространства GLAME

### 11.1. `/spaces`

Список пространств:

- Ялта
- Симферополь

Карточка: фото, город, адрес, краткое описание, CTA.

### 11.2. `/spaces/yalta`

Hero:

```text
GLAME Ялта
пространство у моря
Набережная им. Ленина, 18
Приморский пляж
```

CTA:

- Построить маршрут
- Написать стилисту
- Смотреть украшения в Ялте

### 11.3. `/spaces/simferopol`

Hero:

```text
GLAME Симферополь
пространство городского стиля и ритма
ул. Севастопольская, 62
```

CTA:

- Построить маршрут
- Написать стилисту
- Смотреть украшения в Симферополе

### 11.4. Правила фото

Использовать только реальные фото конкретного пространства. Не смешивать города.

---

## 12. Образы, look-feed и сборка образов

### 12.1. Роль

Раздел образов показывает, как украшения работают вместе: комплект, стиль, повод, настроение, масштаб.

Это не просто “галерея картинок”. Это сценарий “собрать образ”.

### 12.2. Основные экраны

- `/home?tab=5` или раздел `Мой стиль` / `Образы`
- `/look/:id`
- `/looks-profile`

### 12.3. Looks feed

Состав:

- Header `Образы` / `Мой стиль`.
- Переключатель представления: editorial / feed / grid.
- Фильтры:
  - Все
  - На каждый день
  - Вечер
  - Подарок
  - На отдых
  - Свадьба
  - Акцент
  - Сохраненные
- Карточки образов.

Карточка образа:

- большое фото/коллаж;
- название;
- описание;
- теги;
- количество изделий;
- примерная сумма;
- save/favorite;
- CTA: открыть образ;
- CTA: написать стилисту / заменить изделие.

### 12.4. Look detail

Состав:

- Hero образа.
- Название и сценарий.
- Описание стилизации.
- Товары образа.
- Возможность открыть каждый товар.
- CTA: сохранить образ.
- CTA: добавить доступные товары в корзину.
- CTA: подобрать замену со стилистом.
- Похожие образы.

### 12.5. Сборка образа

Stitch должен предусмотреть отдельный сценарий “Собрать образ”:

```text
Выбор цели
→ повод / стиль / фото / любимые товары
→ подборка изделий
→ образ как сет: основа + акцент + баланс
→ редактирование / замена
→ сохранить в Мой стиль
→ купить комплект или отдельные изделия
```

Состояния:

- пустой старт;
- выбранные товары;
- AI/stylist suggestions;
- замены;
- конфликт наличия;
- итоговый сохраненный образ.

Важно: сборка образа должна быть частью “Мой стиль”, а не отдельной игрушечной функции.

---

## 13. Мой стиль / избранное

### 13.1. Роль

“Мой стиль” — персональное пространство пользователя: сохраненные товары, образы, предпочтения и вход к стилисту.

### 13.2. Состояния

Гость:

- показать auth gate;
- объяснить, что после входа сохраняются избранное, образы, консультации и подборки;
- CTA `Войти`;
- CTA `Создать аккаунт`.

Авторизован:

- saved products;
- saved looks;
- favorite looks;
- недавно просмотренные;
- CTA: обсудить избранное со стилистом;
- CTA: собрать образ из избранного.

### 13.3. Wishlist

Если пусто:

- спокойный empty state;
- CTA: перейти в каталог;
- CTA: написать стилисту.

Если есть товары:

- сетка сохраненных товаров;
- массовое действие: обсудить избранное со стилистом;
- товарные карточки ведут в product detail.

---

## 14. AI-подбор по фото

### 14.1. Правило авторизации

Без авторизации фото не загружается. Гость может читать описание и инструкцию, но при попытке выбора фото видит auth gate.

### 14.2. Экран `/selection/ai-photo`

Состав:

- App bar.
- Editorial image / пример.
- Заголовок.
- Текст про подбор форм, линий, масштаба и стиля.
- CTA `Выбрать или сделать фото`.
- CTA/link `Какое фото подойдет?`.
- Helper text про сохранение результата в профиль.

### 14.3. Bottom sheet “Какое фото подойдет”

Содержит:

- пример фото;
- короткие правила: лицо/образ видно, свет ровный, без сильных фильтров, одно лицо, украшения не закрывают ключевые зоны;
- CTA вернуться к выбору фото.

Не писать медицинские/диагностические формулировки.

### 14.4. Review

Экран проверки фото:

- выбранное фото;
- CTA `Запустить подбор`;
- CTA `Выбрать другое`;
- предупреждение о качестве, если нужно.

### 14.5. Analysis

Состояние анализа:

- спокойный progress;
- фразы про форму, масштаб, линии, стиль;
- без магического “диагноза”.

### 14.6. Result

Состав:

- summary: что подходит;
- recommended shapes;
- recommended scale;
- product recommendations;
- раздел “на каждый день”;
- раздел “акцент”;
- CTA сохранить;
- CTA открыть товар;
- CTA обсудить со стилистом.

---

## 15. Живой стилист и AI-стилист

### 15.1. Entry points

- bottom nav `Подбор`;
- Home hero slide 07;
- Home block 6;
- Product detail;
- Wishlist / favorites;
- Look detail;
- Spaces;
- Brand page.

### 15.2. Stylist contact bottom sheet

Рабочее время: 10:00–20:00 по МСК.

Open state:

```text
Стилист GLAME
Опишите задачу — стилист поможет подобрать украшение онлайн или пригласит в пространство, если нужна примерка.
```

Closed state:

```text
Оставить заявку стилисту
Стилист GLAME ответит с 10:00 до 20:00 по МСК. Опишите задачу — мы подберем украшения под образ, повод или подарок.
```

Поля:

- textarea `Что хотите подобрать?`
- quick tags: Для себя, В подарок, Под образ, Нужен комплект, Хочу примерить
- CTA

Не дублировать AI-кнопку внутри sheet, если AI рядом на экране.

### 15.3. Auth

Если гость пытается открыть чат:

- не показывать пустой чат;
- не делать 401 API-запросы;
- показать auth gate `Войдите, чтобы написать стилисту`;
- после входа вернуть пользователя в тот же chat route с параметрами.

### 15.4. Chat

Состав:

- header: Стилист GLAME + статус графика;
- message list;
- composer;
- attachment photo;
- product cards inside chat;
- looks/cards inside chat;
- stores block inside chat;
- assistant typing state;
- empty state.

AI-стилист может предлагать:

- товары;
- замены;
- образы;
- магазины/примерку;
- вопросы для уточнения.

Тон: спокойный, премиальный, не chatbot-toy.

---

## 16. Корзина и checkout

### 16.1. Корзина

Состав:

- список товаров;
- фото, название, вариант, цена;
- изменение количества, удаление;
- сумма;
- CTA `Оформить заказ`;
- empty state.

Гость при переходе к checkout должен видеть auth или мягкий login prompt, если checkout требует профиль.

### 16.2. Checkout

Шаги:

1. Корзина
2. Адрес / доставка
3. Оплата
4. Подтверждение

Доставка:

- самовывоз;
- CDEK/PVZ;
- город;
- карта/список ПВЗ;
- расчет доставки.

Оплата:

- оплата при получении;
- онлайн-оплата, если доступна;
- бонусы/loyalty points.

После оформления:

- номер заказа;
- статус;
- дальнейшие действия.

---

## 17. Кабинет покупателя

### 17.1. Гость

Показать login required:

- заголовок `Профиль`;
- текст `Войдите, чтобы открыть личный кабинет`;
- CTA `Войти`;
- CTA `Создать аккаунт`.

### 17.2. Авторизованный пользователь

Состав:

- имя/телефон/email;
- бонусы;
- уровень/прогресс лояльности;
- заказы;
- история покупок;
- избранное;
- сохраненные образы;
- обращения к стилисту;
- настройки/выход.

### 17.3. Loyalty

Показывать:

- текущий баланс;
- сколько будет списано/начислено;
- прогресс до следующего уровня.

---

## 18. Авторизация

Экраны:

- `/login`
- `/auth/register`
- `/auth/otp`
- `/auth/change-password`

Требования:

- GLAME header logo;
- телефон/password;
- вход по SMS;
- регистрация;
- next route сохраняется;
- после login/register пользователь возвращается в исходный сценарий.

Auth gate должен быть переиспользуемым:

- AI upload;
- stylist chat;
- profile;
- checkout;
- wishlist save if needed.

---

## 19. Onboarding

Onboarding показывается первому пользователю.

Задача:

- коротко объяснить GLAME;
- показать ценность: украшения, образы, AI, стилист, пространства;
- не делать длинный tutorial;
- CTA: начать.

Визуально: холодный editorial, не app-store template.

---

## 20. Компоненты дизайн-системы

Stitch должен собрать component library:

- top bar transparent;
- top bar internal;
- bottom nav;
- drawer menu;
- hero slide;
- CTA primary/secondary;
- action panel;
- service tile;
- product card;
- product mini card;
- drop/editorial card;
- brand row/card;
- space card;
- look card;
- look product item;
- auth gate;
- bottom sheet;
- chat message bubble;
- chat product attachment;
- filter chips;
- segmented control;
- form field;
- checkout stepper;
- empty state;
- loading skeleton.

Все компоненты radius 0, кроме случаев, где текущий Flutter код уже использует небольшое скругление в looks; для нового единого дизайна предпочтительно привести looks к radius 0 или минимальному системному радиусу только если без него ломается UX.

---

## 21. States checklist

Для каждого ключевого раздела Stitch должен показать состояния:

- loading;
- empty;
- error;
- guest;
- authorized;
- with content;
- disabled CTA;
- no network/data unavailable.

Обязательные state screens:

- empty catalog;
- empty wishlist;
- guest profile;
- guest stylist chat auth gate;
- guest AI upload auth gate;
- empty cart;
- checkout success;
- photo analysis loading;
- stylist closed/off-hours.

---

## 22. Контент и мок-данные

Использовать реальные названия брендов из раздела Block 4.

Примеры коллекций:

- complete-look
- gift
- accent
- resort
- wedding

Примеры категорий:

- earrings
- ear_cuffs
- necklaces
- bracelets
- rings
- brooches

Примеры quick tags стилиста:

- Для себя
- В подарок
- Под образ
- Нужен комплект
- Хочу примерить

---

## 23. Что должно быть в результате Stitch

Минимальный полный набор экранов:

1. Onboarding
2. Home с 6 блоками
3. Drawer
4. Catalog
5. Catalog filtered: new / brand / collection / city availability
6. Product detail
7. Brands list
8. Brand detail
9. Spaces list
10. Space detail Yalta
11. Space detail Simferopol
12. Looks feed editorial
13. Looks feed grid
14. Look detail
15. Look builder / сборка образа
16. My Style / wishlist authorized
17. My Style guest auth gate
18. AI photo upload
19. AI photo guide bottom sheet
20. AI auth gate
21. Photo review
22. Photo analysis
23. Photo selection result
24. Selection method screen
25. Stylist bottom sheet open
26. Stylist bottom sheet closed
27. Stylist chat authorized
28. Stylist chat guest auth gate
29. Cart
30. Checkout steps 1-4
31. Checkout success
32. Profile guest
33. Profile authorized
34. Orders/history
35. Login
36. Register
37. OTP
38. Change password
39. Error/empty/loading templates

---

## 24. Ссылки на текущую Flutter-реализацию

Использовать как source of truth по текущей структуре:

- `mobile/glame_app/lib/src/app/app.dart`
- `mobile/glame_app/lib/src/features/home/home_screen.dart`
- `mobile/glame_app/lib/src/features/home/home_shell.dart`
- `mobile/glame_app/lib/src/features/catalog/catalog_screen.dart`
- `mobile/glame_app/lib/src/features/product/product_screen.dart`
- `mobile/glame_app/lib/src/features/brands/brands_screen.dart`
- `mobile/glame_app/lib/src/features/stores/stores_screen.dart`
- `mobile/glame_app/lib/src/features/looks/looks_screen.dart`
- `mobile/glame_app/lib/src/features/looks/look_detail_screen.dart`
- `mobile/glame_app/lib/src/features/home/photo_upload_screen.dart`
- `mobile/glame_app/lib/src/features/customer/stylist_entry.dart`
- `mobile/glame_app/lib/src/features/customer/stylist_chat_screen.dart`
- `mobile/glame_app/lib/src/features/wishlist/wishlist_screen.dart`
- `mobile/glame_app/lib/src/features/cart/cart_screen.dart`
- `mobile/glame_app/lib/src/features/checkout/checkout_screen.dart`
- `mobile/glame_app/lib/src/features/auth/login_screen.dart`
- `mobile/glame_app/lib/src/features/auth/register_screen.dart`

---

## 25. Референсы и assets в архиве

В архиве должны лежать:

- этот файл ТЗ;
- `ASSET_MANIFEST_FOR_STITCH.md`;
- оригинальные логотипы и G-знак;
- Clinica Pro font files;
- утвержденные изображения блоков 1, 3, 4, 5, 6;
- реальные фото пространств;
- дизайн-референсы block 2, block 3, block 4, block 5, block 6;
- ключевые исходные дизайн-доки.

---

## 26. Acceptance criteria для Stitch

- Приложение выглядит единым, а не набором разных макетов.
- Все основные разделы и клиентские пути представлены.
- Главная содержит 6 блоков и живую навигацию.
- Витрина не выглядит marketplace.
- Образы и сборка образов являются полноценной частью продукта.
- AI-подбор и стилист связаны с товарами, образами и избранным.
- Auth gates стоят на закрытых действиях.
- Кабинет, избранное, корзина и checkout не забыты.
- Логотип/G-знак не искажены.
- Реальные пространства не сгенерированы и не смешаны.
- Radius 0 / border 1 применены системно.
- Брендовые названия не сокращаются.
- Bottom nav не перекрывает контент.
- Все CTA имеют понятные routes/actions.
