# GLAME catalog quality audit — t_a7a4c3ce

Scope: read-only audit of `GET /api/products/paged` on `http://127.0.0.1:8000` using admin credentials through the GLAME API helper environment. No product cards were changed.

Dataset: 1445 products; 1445 are marked `is_active=true`.

## Release blockers / systemic problem classes

1. Photos are missing for most active catalog items: 965 / 1445 active products (66.8%). Local file checks found no broken referenced image files, so the primary issue is missing image references, not missing static files.

2. Descriptions are missing for most active catalog items: 928 / 1445 active products (64.2%) have neither `description` nor `full_description` usable by the app.

3. Every product is active, including zero-stock products: 965 active products have `stock <= 0`. This mirrors the missing-photo count and strongly suggests the app will publish many unavailable/empty cards unless stock filtering or `is_active` governance is added.

4. Categories are polluted by brands or merchandising buckets. Current category count is 17; examples include `AGafi` (211), `Antura` (56), `Madreperla` (3), `Eva Rites` (1), plus non-taxonomy buckets `SALE`, `Men`, and `Прочее`. The audit flags 214 brand-as-category records and 220 suspicious category records.

5. Brand fields disagree with `specifications.Бренд` in 20 records. Top groups: Prism of Elegance vs Crystal (12), Claudio Canzian vs visually similar Cyrillic/Latin spelling (5), plus isolated Wrinkles of Time/Geometry/Crystal conflicts.

6. Descriptions contain non-client markup/SEO artifacts: 171 records contain raw HTML headings/paragraph/strong tags, 137 contain `<meta>`/keywords artifacts, 152 contain Markdown syntax, and 173 match sales/SEO boilerplate patterns. The Flutter product screen strips HTML, but customer-facing copy still risks showing SEO-generated tone and duplicated meta content after stripping.

7. Stock and imported `specifications.quantity` disagree in 415 records. This matters because previous GLAME catalog guidance says both `stock` and `specifications.quantity` are used/inspected for availability decisions.

## Examples

### Active products without photos
- 40016 — Салфетка GLAME | brand=None | category=Сопутствующие материалы | stock=767.0
- 170026 — Кулон Wrinkles of Time с розовым кварцем длинный | brand=WRINKLES OG TIME | category=SALE | stock=0.0
- 160016 — Кольцо Wrinkles of Time с синей эмалью | brand=WRINKLES OG TIME | category=SALE | stock=4.0
- 71174 — Чокер Bicolor с биколорным подвесом | brand=BICOLOR | category=Колье | stock=3.0
- RP01759 — Серьги с монетами в биколоре Raganella Princess | brand=Raganella Princess | category=Серьги | stock=1.0
- AOT45030 — Серьги Antura с культивированным жемчугом и мятой пластиной | brand=None | category=Antura | stock=0.0
- AOT45028 — Серьги Antura с тремя мятыми пластинами | brand=None | category=Antura | stock=3.0
- 80155 — Серьги Pearl с жемчужинами на мятой основе | brand=PEARL | category=Серьги | stock=6.0

### Active products without descriptions
- 77151 — Кулон Bicolor трансформер с цепью ролло | brand=BICOLOR | category=Колье | stock=0.0
- 40016 — Салфетка GLAME | brand=None | category=Сопутствующие материалы | stock=767.0
- 73050 — Браслет Crystal жесткий с багетным камнем по кругу | brand=CRYSTAL | category=Браслеты | stock=10.0
- 71174 — Чокер Bicolor с биколорным подвесом | brand=BICOLOR | category=Колье | stock=3.0
- 71092 — Браслет Geometry с изгибом | brand=GEOMETRY | category=Браслеты | stock=0.0
- RP01759 — Серьги с монетами в биколоре Raganella Princess | brand=Raganella Princess | category=Серьги | stock=1.0
- 80046 — Браслет Magna мятый с замком на крючок | brand=MAGNA | category=Браслеты | stock=0.0
- 71140 — Браслет Magna мятый изогнутый кафф | brand=MAGNA | category=Браслеты | stock=0.0

### Brand-as-category / suspicious category examples
- 160011 — Серьги Wrinkles of Time в форме круассана | brand=WRINKLES OG TIME | category=AGafi | stock=5.0
- 170018 — Кольцо Wrinkles of Time с красным агатом объемное | brand=WRINKLES OG TIME | category=AGafi | stock=5.0
- 170011 — Кольцо Wrinkles of Time перекрученное с малахитом | brand=WRINKLES OG TIME | category=AGafi | stock=0.0
- 200091 — Серьги Momenti плоские в форме сердца | brand=None | category=AGafi | stock=1.0
- AG25159 — Сотуар на цепочке AGafi (раухтопаз в "авоське", раухтопаз бусины шар, черный агат) | brand=None | category=AGafi | stock=0.0
- AG25173 — Серьги AGafi(желтый кварцит, гематитовая галтовка) | brand=None | category=AGafi | stock=0.0
- AG25175 — Серьги AGafi (халцедон, галтовка из вулканической лавы) | brand=None | category=AGafi | stock=0.0
- AG25179 — Колье - бусы AGafi (янтарь, белый губчатый коралл, ангелит, желтый кварцит, сапфирин, горный хрустал | brand=None | category=AGafi | stock=0.0
- AG25191 — Серьги AGafi (ювелирная смола) | brand=None | category=AGafi | stock=0.0
- AG25196 — Серьги AGafi (натуральный речной жемчуг, сапфирин) | brand=None | category=AGafi | stock=1.0

### Brand/specification mismatches
- 73054 — Браслет Prism of Elegance с камнями в графитовом цвете | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Браслеты
- 73023 — Чокер Prism of Elegance с камнямии сверху | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Колье
- 73027 — Чокер Prism of Elegance  с камнями и подвесом крестом | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Колье
- 77161 — Кольцо  Wrinkles of Time с двумя шариками | brand=WRINKLES OG TIME | specifications.Бренд=Geometry | category=Кольца
- 73048 — Серьги Prism of Elegance конго с круглыми камнями в ободковом касте | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Серьги
- 73045 — Серьги Prism of Elegance гвоздики с круглыми крупными камнями графитового цвета | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Серьги
- 73014 — Кулон Prism of Elegance крест с камнями в изумдудной огранке | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Колье
- 73037 — Серьги Prism of Elegance длинные с крупными камнями в цвете графит | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Серьги
- 73022 — Чокер Prism of Elegance с графитовыми камными сбоку | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Колье
- 73020 — Кулон Prism of Elegance галстук с графитовыми камнями | brand=PRISM OF ELEGANCE | specifications.Бренд=Crystal | category=Колье

### Active zero-stock examples
- 77151 — Кулон Bicolor трансформер с цепью ролло | brand=BICOLOR | category=Колье | stock=0.0
- 71029 — Браслет Geometry разъемный плоский | brand=GEOMETRY | category=Браслеты | stock=0.0
- 71052 — Браслет Geometry кафф базовый дутый | brand=GEOMETRY | category=Браслеты | stock=0.0
- 71093 — Браслет Geometry с матовой вставкой | brand=GEOMETRY | category=Браслеты | stock=0.0
- 170026 — Кулон Wrinkles of Time с розовым кварцем длинный | brand=WRINKLES OG TIME | category=SALE | stock=0.0
- 170011 — Кольцо Wrinkles of Time перекрученное с малахитом | brand=WRINKLES OG TIME | category=AGafi | stock=0.0
- 71092 — Браслет Geometry с изгибом | brand=GEOMETRY | category=Браслеты | stock=0.0
- 71054 — Браслет Geometry слейв | brand=GEOMETRY | category=Браслеты | stock=0.0
- 73089 — Серьги Prism of Elegance гвоздик с крупным акцентным голубым фианитом | brand=PRISM OF ELEGANCE | category=Серьги | stock=0.0
- 80046 — Браслет Magna мятый с замком на крючок | brand=MAGNA | category=Браслеты | stock=0.0


## Recommended correction plan

Priority 0 — release gating (before public app release):
- Define publishable catalog rule: show only `is_active=true AND stock>0 AND images not empty`; decide whether accessories like салфетки/packaging are allowed in app catalog.
- Bulk set `is_active=false` or hide at API/app layer for zero-stock products until stock is replenished. Do not delete records; inventory sync should remain source of truth.
- Add catalog QA dashboard/query with counts for missing image, missing description, zero stock active, bad category, and HTML/meta copy.

Priority 1 — taxonomy cleanup:
- Split product type/category from brand and merchandising collection. Suggested canonical product categories: Серьги, Кольца, Колье, Подвески/Кулоны, Браслеты, Каффы, Чокеры, Броши, Сопутствующие материалы/Упаковка.
- Move brand-like categories (`AGafi`, `Antura`, `Madreperla`, `Eva Rites`) to `brand` or collection/tag fields.
- Move `SALE` and `Men` to tags/collections, not category.

Priority 2 — content enrichment:
- For publishable in-stock items, require at least one photo and one clean description. Start with active in-stock products missing either field.
- Normalize generated descriptions to plain customer copy: no `<meta>`, no `<h1>`, no keyword lists, no Markdown bullets unless app explicitly supports formatting.
- Keep GLAME brand-safe wording: describe alloys/steel/silver/plating accurately; avoid unsupported “gold jewelry/luxury gold” claims.

Priority 3 — data consistency:
- Normalize brand aliases (`WRINKLES OG TIME` -> `Wrinkles of Time`; fix Latin/Cyrillic `Claudio Canzian` spelling).
- Investigate Prism of Elegance items whose `specifications.Бренд` is Crystal before using brand filters in the app.
- Decide whether availability comes from `stock`, `specifications.quantity`, or a reconciled value; currently 415 products disagree.

## Artifacts

- Machine-readable audit: `/root/glame-platform/reports/catalog_quality_audit_t_a7a4c3ce.json`
- Audit script: `/root/glame-platform/scripts/catalog_quality_audit.py`
