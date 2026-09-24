"""Learner-safe slide and quiz flow for the fixed GLAME trainee programme."""

from __future__ import annotations

from typing import Any


_QUIZZES: dict[str, list[dict[str, Any]]] = {
    "Миссия и ценности GLAME": [
        {"id": "mission_focus", "question": "Что является целью консультации в GLAME?", "options": ["Помочь подобрать украшение под образ и потребность", "Продать самое дорогое изделие", "Сразу назвать все акции"], "answer": "Помочь подобрать украшение под образ и потребность"},
        {"id": "mission_tone", "question": "Какой тон общения верный?", "options": ["Внимательный и без давления", "Настойчивый, чтобы клиент решил быстрее", "Только профессиональные термины"], "answer": "Внимательный и без давления"},
        {"id": "mission_uncertain", "question": "Что делать, если вы не уверены в характеристике изделия?", "options": ["Проверить карточку товара или уточнить у управляющего", "Назвать вероятный ответ", "Не отвечать покупателю"], "answer": "Проверить карточку товара или уточнить у управляющего"},
    ],
    "Первый контакт 30–60 секунд": [
        {"id": "contact_start", "question": "С чего начинается корректный первый контакт?", "options": ["Приветствие и мягкое предложение помощи", "С вопроса «Что будете брать?»", "Сразу с демонстрации дорогого комплекта"], "answer": "Приветствие и мягкое предложение помощи"},
        {"id": "contact_needs", "question": "Что полезно уточнить после приветствия?", "options": ["Повод, адресата и предпочтения", "Только сумму на карте", "Ничего — покупатель сам скажет"], "answer": "Повод, адресата и предпочтения"},
        {"id": "contact_pressure", "question": "Какой следующий шаг соответствует стандарту?", "options": ["Предложить посмотреть подходящие варианты без спешки", "Попросить немедленно определиться", "Оставить покупателя без контакта"], "answer": "Предложить посмотреть подходящие варианты без спешки"},
    ],
    "Материалы и уход за украшениями": [
        {"id": "product_source", "question": "Где проверить точную характеристику изделия?", "options": ["В карточке товара", "По памяти коллеги", "В описании другой коллекции"], "answer": "В карточке товара"},
        {"id": "product_presentation", "question": "Как лучше рассказывать о свойстве изделия?", "options": ["Связать свойство с пользой и образом покупателя", "Перечислить термины без пояснений", "Обещать любые свойства"], "answer": "Связать свойство с пользой и образом покупателя"},
        {"id": "product_care", "question": "Какое правило ухода корректно?", "options": ["Избегать агрессивной бытовой химии", "Хранить все украшения в одной куче", "Не соблюдать инструкцию материала"], "answer": "Избегать агрессивной бытовой химии"},
    ],
    "Касса, сертификаты и возвраты": [
        {"id": "ops_regulation", "question": "На что опираться при возврате или нестандартной оплате?", "options": ["На актуальный регламент магазина", "На собственное предположение", "На обещание покупателю"], "answer": "На актуальный регламент магазина"},
        {"id": "ops_escalation", "question": "Когда нужно пригласить управляющего?", "options": ["Если ситуация не описана в регламенте", "Никогда", "Только после закрытия смены"], "answer": "Если ситуация не описана в регламенте"},
        {"id": "ops_discipline", "question": "Какое действие относится к кассовой дисциплине?", "options": ["Корректно оформить выбранный способ оплаты", "Принять оплату без оформления", "Отложить оформление на конец дня"], "answer": "Корректно оформить выбранный способ оплаты"},
    ],
}


def trainee_lesson_flow(step_title: str, lesson_text: str | None, answer_template: str | None, practice_text: str | None) -> dict[str, Any] | None:
    quiz = _QUIZZES.get(step_title)
    if not quiz:
        return None
    slides = [
        {"id": "idea", "eyebrow": "01 · Суть", "title": "Главная идея", "body": (lesson_text or "Изучите ключевой принцип этого урока.").split("\n\n")[0]},
        {"id": "focus", "eyebrow": "02 · Фокус", "title": "Что запомнить", "body": answer_template or "Выберите конкретный пример и действуйте без давления."},
        {"id": "practice", "eyebrow": "03 · Применение", "title": "Как применить", "body": practice_text or "Примените принцип в следующем разговоре с покупателем."},
    ]
    return {
        "slides": slides,
        "quiz": [{key: item[key] for key in ("id", "question", "options")} for item in quiz],
        "passing_score": 2,
    }


def evaluate_trainee_lesson_quiz(step_title: str, answers: dict[str, Any]) -> dict[str, Any] | None:
    quiz = _QUIZZES.get(step_title)
    if not quiz:
        return None
    results = [{"question_id": item["id"], "correct": str(answers.get(item["id"]) or "") == item["answer"]} for item in quiz]
    correct = sum(1 for item in results if item["correct"])
    return {
        "score": round(correct / len(quiz) * 100), "correct_answers": correct, "total_questions": len(quiz),
        "passed": correct >= 2, "question_results": results,
    }
