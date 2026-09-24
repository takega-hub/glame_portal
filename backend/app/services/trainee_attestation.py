"""Final trainee check based on the 2025 GLAME trainee blank.

The question text is kept in code so the assessment is reproducible and a
manager can always see exactly what the trainee was asked.  The reference
terms are deliberately server-only: they are used by the fallback evaluator
and are never returned to a learner.
"""

from __future__ import annotations

from typing import Any


TRAINEE_BLANK_SOURCE = "Бланк стажера 2025"

# A compact, balanced final check.  It covers every operational block from the
# supplied blank while keeping the final interview realistic for a new seller.
TRAINEE_FINAL_QUESTIONS: list[dict[str, Any]] = [
    {"id": "brand_products", "section": "Бренд и продукт", "question": "С какой продукцией, странами и брендами работает GLAME?", "keywords": ["glame", "украш", "бренд", "стра"], "criteria": "Называет ассортимент и объясняет позиционирование бренда."},
    {"id": "brand_concept", "section": "Бренд и продукт", "question": "В чём концепция бренда GLAME и как вы объясните её покупателю?", "keywords": ["образ", "украш", "клиент", "стиль"], "criteria": "Связывает украшение с образом и потребностью клиента."},
    {"id": "seller_role", "section": "Роль консультанта", "question": "Что обязан знать и за что отвечает продавец-консультант?", "keywords": ["ассортимент", "клиент", "касс", "стандарт"], "criteria": "Описывает знания, обязанности и ответственность консультанта."},
    {"id": "dress_code", "section": "Роль консультанта", "question": "Перечислите основные требования дресс-кода и примеры нарушений.", "keywords": ["чист", "аккурат", "форма", "внешн"], "criteria": "Называет конкретные требования к внешнему виду."},
    {"id": "ring_size", "section": "Ювелирная база", "question": "Назовите элементы кольца и как корректно определить размер покупателя.", "keywords": ["шинка", "размер", "палец", "пример"], "criteria": "Знает базовые части изделия и безопасный способ определения размера."},
    {"id": "earring_locks", "section": "Ювелирная база", "question": "Какие замки в серьгах вы знаете? Назовите их особенности и преимущества.", "keywords": ["замок", "серьг", "штифт", "англий"], "criteria": "Сравнивает несколько типов замков через удобство и надёжность."},
    {"id": "chain_locks", "section": "Ювелирная база", "question": "Какие замки и плетения цепей или браслетов есть в магазине? В чём их преимущества?", "keywords": ["цеп", "браслет", "замок", "плетен"], "criteria": "Описывает варианты из ассортимента и пользу для клиента."},
    {"id": "coatings", "section": "Ювелирная база", "question": "Какие защитно-декоративные покрытия вы знаете и почему о них важно говорить покупателю?", "keywords": ["покрыт", "защит", "цвет", "уход"], "criteria": "Связывает покрытие с внешним видом и правилами носки."},
    {"id": "greeting", "section": "Сервис", "question": "Как вы приветствуете покупателя и устанавливаете контакт?", "keywords": ["привет", "контакт", "помочь", "вопрос"], "criteria": "Даёт спокойный сценарий без давления."},
    {"id": "needs", "section": "Сервис", "question": "Какие обязательные вопросы вы задаёте при выявлении потребностей?", "keywords": ["для кого", "повод", "бюджет", "предпоч"], "criteria": "Выявляет повод, адресата, стиль и ограничения."},
    {"id": "presentation", "section": "Сервис", "question": "Опишите алгоритм презентации изделия и приведите пример перевода свойства в выгоду.", "keywords": ["свойств", "выгод", "образ", "пример"], "criteria": "Показывает последовательность и ориентируется на выгоду клиента."},
    {"id": "objections", "section": "Сервис", "question": "Как вы работаете с фразами «Я просто смотрю» и «Мне надо подумать»?", "keywords": ["вопрос", "спокой", "помочь", "давлен"], "criteria": "Не давит, уточняет причину и оставляет следующий шаг."},
    {"id": "closing", "section": "Сервис", "question": "Из каких действий состоит этап завершения продажи?", "keywords": ["итог", "оплата", "упаков", "поблагодар"], "criteria": "Собирает продажу корректно и завершает контакт."},
    {"id": "client_types", "section": "Сервис", "question": "Какие типы клиентов вы знаете и как адаптируете коммуникацию?", "keywords": ["клиент", "особен", "коммуникац", "вопрос"], "criteria": "Описывает различия и подход без ярлыков."},
    {"id": "collections", "section": "Ассортимент", "question": "Выберите две коллекции GLAME и расскажите об их вставках, особенностях и кому вы их предложите.", "keywords": ["коллекц", "вставк", "образ", "клиент"], "criteria": "Уверенно презентует ассортимент через стиль и повод."},
    {"id": "steel", "section": "Ассортимент", "question": "Что такое ювелирная сталь и какие её особенности важны покупателю?", "keywords": ["сталь", "прочн", "уход", "гипо"], "criteria": "Корректно объясняет свойства без неподтверждённых обещаний."},
    {"id": "stones", "section": "Камни и уход", "question": "Назовите виды огранки и закрепок камней. Как объясните синтетические камни?", "keywords": ["огранк", "закрепк", "камень", "синтет"], "criteria": "Различает термины и понятно объясняет покупателю."},
    {"id": "zircon", "section": "Камни и уход", "question": "Чем отличаются циркон, фианит, цирконий и кубический цирконий?", "keywords": ["циркон", "фианит", "циркони", "кам"], "criteria": "Не смешивает разные понятия и честно обозначает материал."},
    {"id": "care_display", "section": "Камни и уход", "question": "Расскажите правила ухода за украшениями GLAME и основные правила выкладки.", "keywords": ["уход", "украш", "выклад", "чист"], "criteria": "Указывает практические правила сохранности и визуального стандарта."},
    {"id": "cash_register", "section": "Операционная работа", "question": "Как открыть/закрыть смену и оформить продажу наличными, картой и QR?", "keywords": ["смен", "касс", "оплат", "qr"], "criteria": "Понимает порядок работы и типы оплаты."},
    {"id": "returns", "section": "Операционная работа", "question": "Как оформляется обмен или возврат и где проверить актуальную памятку?", "keywords": ["возврат", "обмен", "памятк", "оплат"], "criteria": "Описывает безопасный порядок и обращение к регламенту."},
    {"id": "loyalty_bot", "section": "Операционная работа", "question": "Как работает программа лояльности и GLAME-бот: какие задачи они помогают решить?", "keywords": ["лояль", "бот", "клиент", "остатк"], "criteria": "Знает практическое применение инструментов."},
    {"id": "store_kpi", "section": "Магазин и показатели", "question": "Что такое длина чека и что делать, если для выполнения плана не хватает трафика?", "keywords": ["чек", "трафик", "план", "продаж"], "criteria": "Связывает показатель с действиями команды, а не с давлением на клиента."},
    {"id": "opening_closing", "section": "Магазин и показатели", "question": "Какие ключевые правила открытия, закрытия магазина и передачи смены?", "keywords": ["открыт", "закрыт", "смен", "провер"], "criteria": "Описывает последовательность и ответственность при передаче смены."},
]


TRAINEE_FINAL_TIME_LIMIT_MINUTES = 45

# The final blank is not a second, unexpected curriculum. Each of its topics
# must be introduced and checked in a concrete lesson first. The map is used
# by the programme editor as an auditable curriculum contract; it contains IDs
# from ``TRAINEE_FINAL_QUESTIONS``, never answer keys.
TRAINEE_BLANK_LESSON_COVERAGE: dict[str, list[str]] = {
    "Миссия и ценности GLAME": ["brand_products", "brand_concept", "seller_role", "dress_code"],
    "Первый контакт 30–60 секунд": ["greeting", "needs", "client_types"],
    "Ювелирная база: кольца, серьги и замки": ["ring_size", "earring_locks", "chain_locks"],
    "Материалы, покрытия, сталь и уход": ["coatings", "steel", "care_display"],
    "Коллекции GLAME и подбор по образу": ["collections"],
    "Камни, огранки и закрепки": ["stones", "zircon"],
    "Презентация: свойство → выгода": ["presentation"],
    "Сомнения и завершение продажи": ["objections", "closing"],
    "Касса, сертификаты, возвраты и лояльность": ["cash_register", "returns", "loyalty_bot"],
    "Открытие, закрытие, выкладка и KPI": ["store_kpi", "opening_closing"],
}


def trainee_blank_coverage_for_lesson(lesson_title: str | None) -> list[dict[str, str]]:
    """Learner-safe final-blank topics that this lesson must introduce first."""
    question_by_id = {item["id"]: item for item in TRAINEE_FINAL_QUESTIONS}
    return [
        {key: question_by_id[question_id][key] for key in ("id", "section", "question")}
        for question_id in TRAINEE_BLANK_LESSON_COVERAGE.get((lesson_title or "").strip(), [])
        if question_id in question_by_id
    ]


def trainee_blank_coverage_summary(lesson_titles: list[str]) -> dict[str, Any]:
    """Return transparent coverage and gaps for a trainee programme revision."""
    seen: set[str] = set()
    lessons = []
    for title in lesson_titles:
        questions = trainee_blank_coverage_for_lesson(title)
        seen.update(question["id"] for question in questions)
        lessons.append({"lesson_title": title, "questions": questions})
    all_ids = {item["id"] for item in TRAINEE_FINAL_QUESTIONS}
    return {
        "source": TRAINEE_BLANK_SOURCE,
        "total_questions": len(all_ids),
        "covered_question_ids": sorted(seen),
        "missing_question_ids": sorted(all_ids - seen),
        "is_complete": seen == all_ids,
        "lessons": lessons,
    }


def trainee_attestation_task(*, time_limit_minutes: int = TRAINEE_FINAL_TIME_LIMIT_MINUTES) -> dict[str, Any]:
    """Return learner-safe questions, without evaluation reference terms."""
    return {
        "title": "Итоговая проверка стажёра",
        "source": TRAINEE_BLANK_SOURCE,
        "instructions": "Ответьте своими словами. Важно не заученное определение, а понимание и применение в работе с покупателем.",
        "time_limit_minutes": time_limit_minutes,
        "time_limit_message": f"На итоговую проверку отводится {time_limit_minutes} минут. Время фиксируется сервером с момента открытия.",
        "questions": [{key: item[key] for key in ("id", "section", "question")} for item in TRAINEE_FINAL_QUESTIONS],
        "manager_review_required": True,
    }


def trainee_evaluation_fallback(answer_payload: dict[str, Any]) -> dict[str, Any]:
    """Transparent fallback used only when the AI runtime is unavailable."""
    results: list[dict[str, Any]] = []
    for item in TRAINEE_FINAL_QUESTIONS:
        answer = str(answer_payload.get(item["id"]) or "").strip()
        normalized = answer.lower()
        matches = sum(1 for keyword in item["keywords"] if keyword in normalized)
        if len(answer) < 20:
            score, comment = 0, "Ответа недостаточно для оценки."
        elif len(answer) < 70:
            score, comment = 2, "Есть направление ответа; добавьте конкретный пример из работы."
        else:
            score = min(5, 3 + matches)
            comment = "Ответ раскрыт." if matches >= 2 else "Добавьте профессиональные термины и пример для покупателя."
        results.append({"question_id": item["id"], "score": score, "max_score": 5, "status": "passed" if score >= 3 else "revision", "comment": comment})
    total = sum(item["score"] for item in results)
    maximum = len(results) * 5
    return {
        "score": round(total / maximum * 100) if maximum else 0,
        "max_score": 100,
        "question_results": results,
        "overall_summary": "Предварительная оценка сформирована по полноте и покрытию тем. Управляющий подтверждает итог.",
        "gaps": [item["question_id"] for item in results if item["status"] == "revision"],
        "manager_recommendation": "Проверьте ответы с пометкой «доработать» и проведите короткий устный разбор перед допуском к самостоятельной смене.",
        "assessment_mode": "deterministic_fallback",
        "requires_manager_review": True,
    }
