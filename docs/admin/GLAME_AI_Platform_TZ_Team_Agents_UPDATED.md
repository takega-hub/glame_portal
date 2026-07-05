GLAME AI MARKETING PLATFORM
Итоговое техническое описание системы, иерархии, агентов, потоков данных, задач, согласований и операционных циклов
Версия для разработки / Cursor · v1.0
1. Цель документа
Документ описывает, какую AI-платформу нужно собрать для GLAME. Разработчик не должен трактовать систему как обычный SMM-планировщик, CRM-рассыльщик или набор отдельных чатов. Это единая AI-управляемая marketing operating system для premium retail бренда GLAME.
Ключевой принцип: AI не придумывает контент в вакууме. AI получает бизнес-данные, формирует задачи, контролирует исполнение, фиксирует результат и возвращает выводы в стратегический контур.
2. Что система должна уметь
Собирать вводные из бизнеса: Елена, 1С, Omegacount, CRM/loyalty, соцсети, сайт/Метрика, приложение GLAME.
Переводить бизнес-задачи в маркетинговые задачи, контент, CRM, PR, traffic/growth и задачи магазинов.
Вести рабочие доски: Marketing Command Board, Content Board, Personal Media Board, CRM Board, Partnership Board, Traffic/Growth Board, Product Focus Board, Analytics Board.
Присылать ежедневный план на завтра вечером на согласование.
Проводить недельный operational review и месячный strategic review.
Контролировать статусы задач и фиксировать выполнение через статусы, ссылки, результаты и выводы.
После согласования выполнять низкорисковые действия: публикации утверждённого контента, stories по шаблону, CRM-коммуникации по утверждённым сценариям.
Разделять личный блог Елены и бренд-медиа GLAME как разные медиа-контуры.
3. Главная иерархия
4. Схема подчинения и взаимодействия
Елена
  ↓
AI Marketing Director
  ├── AI Personal Media
  ├── AI Brand Media
  │     ├── City logic inside AI Brand Media
  │     └── City logic inside AI Brand Media
  ├── AI CRM
  ├── AI PR & Partnerships
  ├── AI Traffic & Growth
  ├── AI Assortment
  └── AI Analytics

AI Marketing Director + media-агенты
  ↓ задачи / ТЗ
Контент-продюсер
  ├── оператор
  ├── монтажёр
  ├── организация моделей / стилистов / локаций
  └── передача материалов в AI Content/Brand/Personal

PR Manager → отчитывается в AI PR & Partnerships
Управляющие / стилисты → дают вводные в AI Marketing Director, AI Brand Media, AI Assortment

5. Источники данных
6. AI-агенты: задачи, входы, выходы, взаимодействия
AI Marketing Director
AI Personal Media
AI Brand Media
City logic inside AI Brand Media
City logic inside AI Brand Media
AI CRM
AI PR & Partnerships
AI Traffic & Growth
AI Assortment
AI Analytics
7. Человеческие роли
8. Доски и статусы задач
8.1 Обязательные Boards
8.2 Универсальные статусы задач
9. Согласования и права действий AI
10. Частота планёрок, отчётов и корректировок
11. Время оценки эффективности
12. Production-система
13. Медиаслои и объём контента
14. Customer flow, который должна поддерживать платформа
Personal Media → Attention → Brand Media GLAME → Desire → App/Saves/Site/CRM → Store Visit → Purchase → Return → Loyalty
Каждый агент должен понимать, где его действие находится в этой цепочке. Если действие не ведёт дальше по flow, оно не должно попадать в работу без отдельного обоснования.
15. Требования к разработке
Платформа должна иметь ролевую структуру агентов и не смешивать их задачи.
Каждый агент должен иметь собственную рабочую доску и общий доступ AI Marketing Director.
Каждая задача должна иметь статус, ответственного, дедлайн, источник вводных, ожидаемый результат, ссылку на материалы и поле “вывод”.
AI Marketing Director должен видеть статусы всех агентов и формировать ежедневный/недельный/месячный отчёт.
Должна быть approve-система: действия делятся на low-risk и high-risk.
Должна быть возможность прикреплять ссылки на материалы: Reels, stories, исходники, CRM-рассылки, отчёты, партнёров.
Интеграции должны быть заложены под 1С, Omegacount, соцсети, Яндекс.Метрику, CRM/loyalty и приложение GLAME.
AI должен не только планировать, но и фиксировать факт выполнения и анализировать результат.
Система должна присылать ежедневный вечерний план на завтра на согласование.
Система должна поддерживать корректировки в течение 24–72 часов по контенту и CRM.
16. Открытые вопросы для разработчика / уточнения
Какие API/выгрузки доступны из 1С и Omegacount: автоматический доступ или ручные CSV/Excel на первом этапе?
Какие соцсети будут подключены на старте и где будет происходить публикация: внутри платформы или через внешний scheduler?
Какая CRM/loyalty-система используется фактически: отдельная CRM или данные только в 1С?
Какие события приложения должны быть заложены в аналитику с первого релиза?
Кто утверждает low-risk и high-risk действия на первом этапе: только Елена или также контент-продюсер/управляющий?
Нужен ли Telegram/WhatsApp как канал отправки ежедневного плана и approve-уведомлений?


# Updated AI Brand Media Logic

AI Brand Media is a single unified brand media agent.

The agent must:
- maintain one unified GLAME identity
- adapt emotional mood depending on city
- use Simferopol logic for:
  - structure
  - architecture
  - city rhythm
  - classic/dramatic DNA
- use Yalta logic for:
  - light
  - resort
  - effortless luxury
  - romantic/naturalistic DNA

Cities are not separate media systems.
They are emotional environments inside one GLAME media ecosystem.
