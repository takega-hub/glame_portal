# GLAME: продуктовый фокус для ассортимента, остатков, продаж и маркетинга

Задача Kanban: t_dd8d52cd. Platform task: 82dcbc2c-386e-43dd-881c-7604a855b87b.
Статус платформы: pending_approval — это решение подготовлено для согласования, без автоматического запуска кампаний/закупок.

## Источники и проверка
- Проверено через GLAME API: /health = 200 OK.
- Использованы read-only endpoints: /api/inventory/dashboard, /api/inventory/marketing-link, /api/inventory/order, /api/inventory/clearance.
- Live snapshot: marketing_link=205 строк, order=403 строк, clearance=594 строк.
- В Kanban-паспорте был более ранний marketing_link total=216; live API на момент проверки вернул 205, поэтому решения ниже основаны на live API.

## Общая картина
- Выручка периода: 6 187 462 ₽; чеков: 585; товаров в чеках: 873; средний чек: 10 577 ₽.
- Остаток: 5708 шт. / 634 SKU; среднее покрытие: 2.06 мес.; критичных SKU: 392.
- Дозаказ: 401 SKU, 1004 шт., ориентир суммы 5 645 394 ₽.
- Расчистка: dead stock 563 SKU; slow/promo 20/20 SKU.

## Решение 1: ПРОДВИГАТЬ в маркетинге
Фокус: только товарные позиции, не упаковка/расходники; перед публикацией проверить наличие фото и карточки в каталоге.
- Браслет Bicolor широкий жесткий — sales_month=1.00; stock_qty=3.00; stock_cover=3.00; GROWTH_PRODUCTS; Instagram
- Кулон Bicolor галстук с регулируемой длиной — sales_month=1.00; stock_qty=3.00; stock_cover=3.00; GROWTH_PRODUCTS; Instagram
- Браслет Bicolor с мятыми кольцами — sales_month=0.67; stock_qty=2.00; stock_cover=3.00; GROWTH_PRODUCTS; Instagram
- Кулон Bicolor с мятым подвесным элементом в биколоре — sales_month=0.67; stock_qty=1.00; stock_cover=1.50; GROWTH_PRODUCTS; Instagram
- Серьги винтажные акцентные из крупных вытянутых звеньев Raganella Princess — sales_month=0.67; stock_qty=1.00; stock_cover=1.50; GROWTH_PRODUCTS; Instagram
- Каффа Geometry с подвесным элементом — sales_month=3.67; stock_qty=29.00; stock_cover=7.91; PROMO_PRODUCTS; Promotions
- Браслет "стиль внутри" серебро — sales_month=1.67; stock_qty=49.00; stock_cover=29.40; PROMO_PRODUCTS; Promotions
- Браслет "стиль внутри" золотой — sales_month=1.00; stock_qty=50.00; stock_cover=50.00; PROMO_PRODUCTS; Promotions
- Браслет Bicolor с биколорными пластинами — sales_month=0.67; stock_qty=7.00; stock_cover=10.50; PROMO_PRODUCTS; Promotions
- Кольцо Bicolor вогнутое — sales_month=0.67; stock_qty=5.00; stock_cover=7.50; PROMO_PRODUCTS; Promotions

Рекомендация по подаче: Instagram/Reels/сторис для украшений с понятным визуальным акцентом; Email/SMS использовать только для аккуратных подборок, не для дефицитных товаров.

## Решение 2: ДОЗАКАЗАТЬ / защитить от промо
Фокус: позиции с продажами и критическим/нулевым остатком; не запускать распродажи и широкие кампании до пополнения.
- Браслет Crystal с камнями по кругу — sales_month=4.67; stock_qty=0.00; optimal_stock=14.00; critical_stock; order_qty=14; order_amount=61 460 ₽
- Браслет Crystal жесткий с багетным камнем по кругу — sales_month=4.33; stock_qty=0.00; optimal_stock=13.00; critical_stock; order_qty=13; order_amount=60 970 ₽
- Серьги Magna конго базовые мятые — sales_month=3.67; stock_qty=0.00; optimal_stock=11.00; critical_stock; order_qty=11; order_amount=51 590 ₽
- Серьги Magna мятой фактуры вытянутые — sales_month=3.00; stock_qty=0.00; optimal_stock=9.00; critical_stock; order_qty=9; order_amount=51 210 ₽
- Чокер Crystal багетные камни сбоку — sales_month=2.67; stock_qty=0.00; optimal_stock=8.00; critical_stock; order_qty=8; order_amount=47 920 ₽
- Серьги Magna в форме звена — sales_month=2.67; stock_qty=0.00; optimal_stock=8.00; critical_stock; order_qty=8; order_amount=37 520 ₽
- Серьги Pearl в форме мятого овала с жемчужиной — sales_month=2.67; stock_qty=0.00; optimal_stock=8.00; critical_stock; order_qty=8; order_amount=34 320 ₽
- Кулон Magna лариат с мятыми элементами — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=52 430 ₽
- Чокер Crystal камни в багетной огранке сверху — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=48 230 ₽
- Кулон Geometry капля с бегунком — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=39 830 ₽
- Кулон Magna с мятым элементом на бегунке — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=39 830 ₽
- Кольцо Geometry овал — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=38 430 ₽
- Чокер Сrystal с камнямии сверху — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=37 030 ₽
- Серьги Geometry конго базовые — sales_month=2.33; stock_qty=0.00; optimal_stock=7.00; critical_stock; order_qty=7; order_amount=32 130 ₽
- Браслет Geometry кафф изогнутый — sales_month=2.00; stock_qty=0.00; optimal_stock=6.00; critical_stock; order_qty=6; order_amount=43 140 ₽

## Решение 3: РАСПРОДАТЬ / включить в мягкие промо и комплекты
Фокус: незащищенные позиции с высоким покрытием. Формат: комплект, подарок к покупке, персональная подборка, не агрессивная уценка премиальных героев.
- Браслет "стиль внутри" золотой — sales_month=1.00; stock_qty=50.00; stock_cover=50.00; PROMO
- Браслет "стиль внутри" серебро — sales_month=1.67; stock_qty=49.00; stock_cover=29.40; PROMO
- Кулон Bicolor галстук с шарами — sales_month=0.33; stock_qty=5.00; stock_cover=15.00; PROMO
- Кулон Bicolor длинная капля на якорной цепи — sales_month=0.33; stock_qty=5.00; stock_cover=15.00; PROMO
- Браслет Bicolor с биколорными пластинами — sales_month=0.67; stock_qty=7.00; stock_cover=10.50; PROMO
- Кольцо Antura с мятым кругом — sales_month=0.33; stock_qty=3.00; stock_cover=9.00; PROMO
- Чокер Bicolor с круглыми мятыми вставками — sales_month=0.33; stock_qty=3.00; stock_cover=9.00; PROMO
- Каффа Geometry с подвесным элементом — sales_month=3.67; stock_qty=29.00; stock_cover=7.91; PROMO
- Кольцо Bicolor вогнутое — sales_month=0.67; stock_qty=5.00; stock_cover=7.50; PROMO
- Браслет Crystal жесткий изогнутый с фианитами — sales_month=0.67; stock_qty=4.00; stock_cover=6.00; BUNDLE
- Кольцо Antura геометрической формы — sales_month=0.67; stock_qty=4.00; stock_cover=6.00; BUNDLE
- Кольцо Bicolor с тремя шарами — sales_month=0.67; stock_qty=4.00; stock_cover=6.00; BUNDLE
- Браслет винтажный акцентный из крупных вытянутых звеньев Raganella Princess — sales_month=0.33; stock_qty=2.00; stock_cover=6.00; BUNDLE

## Решение 4: ИСКЛЮЧИТЬ из кампаний до пополнения
Фокус: товар продается, но остаток ноль/дефицит — нельзя вести трафик на недоступные позиции.
- Браслет Crystal с камнями по кругу — sales_month=4.67; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Браслет Crystal жесткий с багетным камнем по кругу — sales_month=4.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Серьги Magna конго базовые мятые — sales_month=3.67; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Серьги Magna мятой фактуры вытянутые — sales_month=3.00; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Серьги Magna в форме звена — sales_month=2.67; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Серьги Pearl в форме мятого овала с жемчужиной — sales_month=2.67; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Чокер Crystal багетные камни сбоку — sales_month=2.67; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Кольцо Geometry овал — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Кулон Geometry капля с бегунком — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Кулон Magna лариат с мятыми элементами — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Кулон Magna с мятым элементом на бегунке — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Серьги Geometry конго базовые — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Чокер Crystal камни в багетной огранке сверху — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Чокер Сrystal с камнямии сверху — sales_month=2.33; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS
- Браслет Geometry кафф изогнутый — sales_month=2.00; stock_qty=0.00; stock_cover=0.00; PROTECT_PRODUCTS

Дополнительно защитить низкий остаток:
- Серьги Pearl в форме полусферы с окантовкой из металла — sales_month=2.00; stock_qty=2.00; stock_cover=1.00; PROTECT_PRODUCTS
- Браслет Bicolor базовый жесткий две линии — sales_month=1.00; stock_qty=1.00; stock_cover=1.00; PROTECT_PRODUCTS
- Браслет Bicolor с шариками — sales_month=1.33; stock_qty=2.00; stock_cover=1.50; PROTECT_PRODUCTS
- Серьги Bicolor с шарами — sales_month=1.33; stock_qty=2.00; stock_cover=1.50; PROTECT_PRODUCTS
- Серьги Antura квадратной геометрической формы — sales_month=1.00; stock_qty=2.00; stock_cover=2.00; PROTECT_PRODUCTS

## Операционные позиции, не клиентский маркетинг
Упаковка/пакеты/салфетки/коробки попали в алгоритмические группы из-за продаж и остатков, но их не нужно продвигать как клиентский продукт; учитывать отдельно для закупки и сервиса.
- Пакет UNOde50 мал. бежевый — sales_month=5.33; stock_qty=11.00; stock_cover=2.06; GROWTH_PRODUCTS; Instagram
- Салфетка GLAME — sales_month=80.33; stock_qty=767.00; stock_cover=9.55; PROMO_PRODUCTS; Promotions
- Мешочек GLAME средний 12*18 — sales_month=72.67; stock_qty=550.00; stock_cover=7.57; PROMO_PRODUCTS; Promotions
- Мешочек GLAME большой 14*20 — sales_month=19.33; stock_qty=292.00; stock_cover=15.10; PROMO_PRODUCTS; Promotions
- Малый мешочек из органзы — sales_month=8.33; stock_qty=696.00; stock_cover=83.52; PROMO_PRODUCTS; Promotions
- Мешочек большой из органзы — sales_month=3.00; stock_qty=416.00; stock_cover=138.67; PROMO_PRODUCTS; Promotions
- Мешочек большой Claudio Canzian — sales_month=2.00; stock_qty=15.00; stock_cover=7.50; PROMO_PRODUCTS; Promotions
- Упаковка средняя черного цвета GLAME — sales_month=1.33; stock_qty=35.00; stock_cover=26.25; PROMO_PRODUCTS; Promotions
- Упаковка большая черного цвета GLAME — sales_month=1.00; stock_qty=53.00; stock_cover=53.00; PROMO_PRODUCTS; Promotions
- Упаковка малая черного цвета GLAME — sales_month=0.33; stock_qty=67.00; stock_cover=201.00; PROMO_PRODUCTS; Promotions
- Коробка железная большая — sales_month=2.00; stock_qty=14.00; stock_cover=7.00; PROMO_PRODUCTS; Promotions
- Коробка железная малая — sales_month=1.33; stock_qty=41.00; stock_cover=30.75; PROMO_PRODUCTS; Promotions

## Предлагаемое решение для администратора
1. Согласовать продвижение первых 10–12 украшений из блока ПРОДВИГАТЬ после фото-чека карточек.
2. Отдельно передать закупке список ДОЗАКАЗАТЬ как приоритет: критические и нулевые остатки с продажами.
3. Для блока РАСПРОДАТЬ использовать не “дисконт на всё”, а комплекты/персональные предложения, чтобы не просадить премиальное восприятие GLAME.
4. Исключить из публичных кампаний все позиции с stock_qty=0 и низким покрытием, пока нет пополнения.
5. Доработать алгоритм product_focus: отделять упаковку/расходники от клиентских товарных кампаний и добавлять фото-доступность перед рекомендацией.

## Артефакты
- JSON с расчетными списками: /workspace/glame-platform/reports/product_focus_t_dd8d52cd_20260530_180313.json
- Markdown-отчет: /workspace/glame-platform/reports/product_focus_t_dd8d52cd_20260530_180313.md
