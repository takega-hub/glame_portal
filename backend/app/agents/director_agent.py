"""
Director Agent - главный оркестратор AI-агентов GLAME.

Роль:
- Центральный узел для общения с пользователем через чат
- Принимает задачи, разбивает на подзадачи, распределяет между агентами
- Управляет кратковременной, среднесрочной и долгой памятью
- Взаимодействует с базой знаний (добавление, поиск, векторизация)
- Формирует отчёты для пользователя
- Имеет доступ к живым данным о продажах, покупателях и товарах
"""
from typing import Dict, Any, Optional, List, Tuple
from uuid import UUID, uuid4
from datetime import datetime
import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_, or_, func, text

from app.agents.base_agent import BaseAgent
from app.services.llm_service import llm_service
from app.services.vector_service import vector_service
from app.database.connection import AsyncSessionLocal
from app.models.director_memory import (
    DirectorChatMessage,
    DirectorTask,
    DirectorMemory,
    DirectorKnowledge,
    DirectorConversationContext,
)
from app.models.agent_interaction import AgentInteractionLog, AgentInteractionTask, InteractionStatus
from app.agents.director_data_service import DirectorDataService
from app.agents.agent_registry import get_marketing_agent_registry
from app.services.hermes_web_ui_mirror import mirror_director_turn_to_hermes_web_ui

logger = logging.getLogger(__name__)

DIRECTOR_SYSTEM_PROMPT = """Ты — AI-директор GLAME, главный оркестратор агентской системы.

Твоя роль:
- Ты — центральный узел, через который пользователь (владелец бизнеса) управляет всей платформой.
- Ты общаешься с пользователем через чат: принимаешь задачи, уточняешь детали, отчитываешься о результатах.
- Ты распределяешь работу между специализированными AI-агентами, контролируешь выполнение и сводишь результаты в единый отчёт.
- Ты управляешь базой знаний: можешь добавлять новые документы, искать информацию, структурировать её.

Принципы работы:
1. Память:
   - Кратковременная — текущий диалог (контекст сессии).
   - Среднесрочная — ключевые факты, решения, договорённости из завершённых диалогов.
   - Долгая — векторизованные знания, стратегические документы, правила в базе знаний.
2. При получении задачи ты должен:
   a. Уточнить, если задача неоднозначна.
   b. Разбить задачу на подзадачи и определить, какие агенты нужны.
   c. Раздать задания агентам с чёткими инструкциями и дедлайнами.
   d. Дождаться результатов, проверить их полноту.
   e. Подготовить и предоставить пользователю структурированный отчёт.
3. Если задача требует согласования — запроси подтверждение у пользователя перед выполнением.
4. Если какой-то агент не справился — переформулируй задачу и отправь повторно, либо предложи альтернативу.
5. Для ответа используй контекст из базы знаний (Knowledge Base), если это релевантно задаче.
6. Важные моменты диалогов автоматически векторизуются в базу знаний для долгой памяти.
7. Если для работы не хватает внешнего документа, фотографии, PDF, таблицы или другого
   файла, прямо запроси его у пользователя. Объясни, что файл можно прикрепить в чат
   и при необходимости добавить в базу знаний директора для дальнейшей работы.
8. Чат — основной интерфейс управления процессом. Задачи, согласования, запросы
   доработок и отчёты должны возвращаться пользователю в чат как понятные рабочие
   карточки с текущим статусом, ответственным агентом, краткой аналитикой и
   следующими действиями.
9. Для кампаний, CRM-рассылок, Product Focus, контент-планов и аналитических
   отчетов не выдавай длинный финальный документ сразу. Сначала покажи короткое
   резюме, какие агенты нужны, какие данные нужно запросить, и предложи действия
   для постановки задач агентам. Если пользователь запускает работу, общайся с
   каждым профильным агентом через его постоянный чат/задачу и только после
   получения результата собирай итог для пользователя.
10. Не создавай задачи с названием “рабочий чат”: рабочий чат агента уже является
    сервисным каналом. Создавай только конкретные рабочие задачи: сегментация,
    Product Focus, контент-пакет, KPI/аналитика, трафик, PR и т.п.
11. Если для плана нужна CRM-сегментация, товарный фокус, контент или аналитика,
    явно укажи профильного агента, ожидаемый результат и критерий готовности.
    Не утверждай, что сегмент, SKU-пул или KPI уже подготовлены, пока это не
    пришло из данных/задачи агента.
12. Не допускай текстовой фантазии. Все числа, сегменты, списки клиентов, товары,
    SKU, остатки, продажи, магазины и рекомендации должны быть взяты из БД/API
    платформы или из фактического результата агента. Если данных нет или они не
    получены, прямо напиши, каких данных нет и какую синхронизацию/проверку нужно
    запустить. Нельзя заменять отсутствующие данные гипотезами.

Формат ответа:
- Всегда структурируй ответ: что сделано, какие агенты задействованы, результаты, следующие шаги.
- Если нужны действия от пользователя — явно укажи их.
- Длинные материалы разбивай на короткие фрагменты: вывод, запросы агентам,
  решения пользователя, затем подробности. В конце давай варианты действий,
  чтобы интерфейс мог показать их кнопками.
- Поддерживай профессиональный, деловой тон.

Доступ к данным: Ты имеешь ПОЛНЫЙ ДОСТУП к живым данным о продажах, покупателях,
товарах, магазинах и кампаниях. Ниже приведён DATA_TOOLS_BLOCK с только что
полученными данными — используй их для ответа пользователю.

Запрещено говорить, что у тебя нет постоянного подключения к CRM, продажам,
остаткам, чекам, посещениям или истории заказов. Эти данные уже синхронизируются
в БД GLAME из 1С, CRM/loyalty, счетчиков посещений и аналитических сервисов.
Если каких-то конкретных цифр нет в DATA_TOOLS_BLOCK, скажи, что проверишь
доступный срез данных, и запроси недостающий период или фильтр.
Если DATA_TOOLS_BLOCK содержит посещения магазинов с разбивкой by_store,
используй только эти точные значения. Не оценивай посещения по магазинам и
не распределяй общий трафик пропорциями; если точной разбивки нет — прямо
напиши, что точных данных по магазинам за период нет.
Все отчеты и выводы должны собираться только из данных, которые уже есть в
БД/agent_work_results/DATA_TOOLS_BLOCK и точно получены. Если данных нет,
не подставляй примерные числа: запроси обновление/синхронизацию нужного
источника или прямо напиши, каких данных нет и почему их нельзя показать.
Продажи и чеки бери из sales_records/sales_metrics, а не из store_visits:
store_visits — это источник посещаемости счетчиков. Нулевой sales_count в
store_visits не означает отсутствие продаж. Для связи посещений и продаж
показывай выручку на посетителя, если есть visitors и revenue.

Канонический состав AI-агентов GLAME строго по GLAME_AI_Agent_System_Prompts_v1_2:
- director-agent — AI Marketing Director
- personal-media-agent — AI Personal Media
- brand-media-agent — AI Brand Media
- crm-agent — AI CRM
- pr-partnerships-agent — AI PR & Partnerships
- traffic-growth-agent — AI Traffic & Growth
- analytics-agent — AI Analytics
- assortment-agent — AI Assortment
Старые content-agent, communication-agent и marketing-inventory-agent являются
только техническими алиасами для совместимости. В ответах пользователю используй
канонические названия и роли из ТЗ v1_2.

Задачи:
- Актуальные задачи существуют только в БД GLAME: director_tasks и agent_interaction_tasks.
- Если пользователь спрашивает “какие задачи”, “что в работе”, “статусы задач”,
  используй только DATA_TOOLS_BLOCK секцию [Актуальные задачи из БД].
- Не придумывай коды задач вроде BM-2025-04-01, CRM-2025-04-01, AS-2025-04-01.
  Такие коды можно упоминать только если они дословно пришли из БД в title/id.
- База знаний и память могут содержать старые планы; они не являются источником
  текущего статуса задач.
"""


class DirectorAgent(BaseAgent):
    """AI Director Agent - главный оркестратор"""

    AGENT_TYPE = "director-agent"

    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Основной метод обработки — диспетчеризация по action"""
        action = input_data.get("action", "chat")
        user_id = input_data.get("user_id")

        if action == "execute_task":
            return await self.execute_task(
                user_id=user_id,
                task_title=input_data.get("task_title", ""),
                task_description=input_data.get("task_description"),
                task_type=input_data.get("task_type", "assignment"),
                priority=input_data.get("priority", "P2"),
                source_message_id=input_data.get("source_message_id"),
            )

        if action == "add_knowledge":
            result = await self.add_to_knowledge(
                user_id=user_id,
                title=input_data.get("title", ""),
                content=input_data.get("content", ""),
                category=input_data.get("category", "fact"),
                source=input_data.get("source"),
                source_message_id=input_data.get("source_message_id"),
            )
            return result

        if action == "get_data":
            data_service = DirectorDataService(self.db)
            data_type = input_data.get("data_type", "general")
            return await self._resolve_data_query(data_service, data_type, input_data.get("params", {}))

        # По умолчанию — обработка сообщения чата
        return await self.process_chat_message(
            user_id=user_id,
            message=input_data.get("message", ""),
            session_id=input_data.get("session_id"),
            category=input_data.get("category"),
        )

    async def get_greeting(self, user_id: UUID, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Сгенерировать проактивное приветствие с текущей сводкой данных"""
        data_service = DirectorDataService(self.db)

        # 1. Собираем данные
        try:
            general_stats = await data_service.get_general_stats()
        except Exception as e:
            logger.warning(f"get_general_stats failed in greeting: {e}")
            general_stats = {}

        try:
            top_products = await data_service.get_top_selling_products(5)
        except Exception as e:
            logger.warning(f"get_top_products failed in greeting: {e}")
            top_products = []

        try:
            campaigns = await data_service.get_active_campaigns()
        except Exception as e:
            logger.warning(f"get_active_campaigns failed in greeting: {e}")
            campaigns = []

        # 2. Получаем незавершённые задачи
        tasks_result = await self.db.execute(
            select(DirectorTask)
            .where(
                and_(
                    DirectorTask.user_id == user_id,
                    DirectorTask.status.in_(["in_progress", "pending"]),
                )
            )
            .order_by(desc(DirectorTask.priority), desc(DirectorTask.created_at))
            .limit(5)
        )
        active_tasks = tasks_result.scalars().all()

        # 3. Формируем блок данных для промпта
        data_block_parts = []
        today = general_stats.get("today", {})
        if today:
            data_block_parts.append(
                f"Продажи сегодня: {today.get('orders_count', 0)} заказов, "
                f"{today.get('total_revenue_rub', 0)} ₽ выручка."
            )
        week = general_stats.get("last_7_days", {})
        if week:
            data_block_parts.append(
                f"За 7 дней: {week.get('orders_count', 0)} заказов, "
                f"{week.get('total_revenue_rub', 0)} ₽ выручка, "
                f"средний чек {week.get('average_check_rub', 0)} ₽."
            )
        customers = general_stats.get("customers", {})
        if customers:
            data_block_parts.append(
                f"Покупатели: всего {customers.get('total_customers', 0)}, "
                f"новых за 30 дней: {customers.get('new_last_30_days', 0)}."
            )
        products = general_stats.get("products", {})
        if products:
            data_block_parts.append(
                f"Товары: {products.get('total_active_products', 0)} активных, "
                f"core assortment: {products.get('core_assortment', 0)}."
            )

        if top_products:
            top_lines = ", ".join(
                [p.get("product_name") or p.get("name", "") for p in top_products[:3]]
            )
            data_block_parts.append(f"Топ товаров: {top_lines}.")

        if campaigns:
            data_block_parts.append(
                f"Активные кампании: {len(campaigns)}."
            )

        if active_tasks:
            data_block_parts.append(
                f"Активных задач: {len(active_tasks)}."
            )

        data_context = "\n".join(data_block_parts)

        # 4. Генерируем приветствие через LLM
        prompt = (
            f"Ты — AI-директор GLAME. Сгенерируй краткое проактивное приветствие "
            f"для владельца бизнеса на основе следующих данных:\n\n{data_context}\n\n"
            f"Требования:\n"
            f"- Обращение на «Вы»\n"
            f"- Тон: деловой, энергичный, профессиональный\n"
            f"- Укажи статус: как прошёл день / неделя по продажам\n"
            f"- Если есть активные задачи — кратко упомяни их\n"
            f"- Если есть активные кампании — упомяни\n"
            f"- Озвучь рекомендацию / фокус на сегодня\n"
            f"- Заверши вопросом «Чем могу помочь?» или «С чего начнём?»\n"
            f"- Приветствие должно быть 3-5 предложений, без списков, без маркдауна, одним абзацем"
        )

        system_prompt = await self.get_active_system_prompt(
            self.db, self.AGENT_TYPE, DIRECTOR_SYSTEM_PROMPT
        )

        try:
            greeting_text = await self.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=500,
            )
        except Exception as e:
            logger.warning(f"Greeting generation failed: {e}")
            greeting_text = (
                f"Добрый день! Сегодня {today.get('orders_count', 0)} заказов, "
                f"выручка {today.get('total_revenue_rub', 0)} ₽. "
                f"Чем могу помочь?"
            )

        # 5. Сохраняем приветствие как сообщение директора
        greeting_msg = DirectorChatMessage(
            user_id=user_id,
            message=greeting_text,
            message_type="greeting",
            message_direction="director",
            category="greeting",
            session_id=session_id,
            extra_data={"greeting": True, "data_snapshot": data_context},
        )
        self.db.add(greeting_msg)
        await self.db.commit()

        return {
            "response": greeting_text,
            "director_message_id": str(greeting_msg.id),
            "data_context": data_context,
            "active_tasks_count": len(active_tasks),
        }

    async def _resolve_data_query(
        self, data_service: DirectorDataService, data_type: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Разрешение запроса данных по типу"""
        if data_type == "today_sales":
            return await data_service.get_today_sales()
        elif data_type == "sales_week":
            days = params.get("days", 7)
            return await data_service.get_sales_for_period(days)
        elif data_type == "sales_trend":
            days = params.get("days", 30)
            return {"trend": await data_service.get_daily_sales_trend(days)}
        elif data_type == "customer_summary":
            return await data_service.get_customer_summary()
        elif data_type == "product_summary":
            return await data_service.get_product_summary()
        elif data_type == "top_products":
            limit = params.get("limit", 10)
            return {"products": await data_service.get_top_selling_products(limit)}
        elif data_type == "stores":
            return {"stores": await data_service.get_stores_summary(params.get("days"))}
        elif data_type == "inventory":
            return await data_service.get_inventory_summary()
        elif data_type == "store_visits":
            days = params.get("days", 7)
            return await data_service.get_store_visits_summary(days)
        elif data_type == "sales_metrics":
            days = params.get("days", 7)
            return await data_service.get_sales_metrics_summary(days)
        elif data_type == "sales_sources":
            days = params.get("days", 7)
            return await data_service.get_sales_sources_status(days)
        elif data_type == "campaigns":
            return {"campaigns": await data_service.get_active_campaigns()}
        elif data_type == "recent_orders":
            limit = params.get("limit", 10)
            return {"orders": await data_service.get_recent_orders(limit)}
        elif data_type == "search_customer":
            query = params.get("query", "")
            search_by = params.get("search_by", "auto")
            return {"customers": await data_service.find_customer(query, search_by)}
        elif data_type == "search_products":
            query = params.get("query", "")
            return {"products": await data_service.search_products(query)}
        elif data_type == "customer_history":
            customer_id = params.get("customer_id")
            if customer_id:
                return await data_service.get_customer_purchase_history(UUID(customer_id))
            return {"error": "customer_id is required"}
        else:
            return await data_service.get_general_stats()

    async def process_chat_message(
        self,
        user_id: UUID,
        message: str,
        session_id: Optional[str] = None,
        category: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Обработка сообщения от пользователя в чате"""
        # 1. Получаем контекст сессии и среднесрочную память
        context = await self._get_or_create_context(user_id, session_id)
        medium_term = await self._get_medium_term_memory(user_id, limit=5)

        # 2. Строим рабочий цикл запроса и получаем живые данные из БД.
        request_workflow = self._build_request_workflow(message)
        data_context = await self._fetch_data_context(message, request_workflow)
        cron_management_result = await self._auto_manage_cron_jobs(message, request_workflow)
        if cron_management_result:
            data_context = dict(data_context or {})
            data_context["admin_cron_result"] = cron_management_result
            data_context["admin_cron"] = await self._get_admin_cron_context()
        agent_work_result = await self._auto_execute_required_agent_work(user_id, message, request_workflow)
        if agent_work_result:
            data_context = dict(data_context or {})
            data_context["agent_work_results"] = agent_work_result

        # 3. Ищем релевантные знания. Для операционного планирования и задач
        # не подмешиваем старые "инсайты" с выдуманными task-кодами.
        knowledge_context = await self._search_knowledge(message, user_id)
        knowledge_context = [
            item for item in knowledge_context
            if not self._is_stale_task_artifact(f"{item.get('title', '')}\n{item.get('content', '')}")
        ]
        medium_term = [
            item for item in medium_term
            if not self._is_stale_task_artifact(str(item.get("content", "")))
        ]

        visible_data_context = self._filter_data_context_for_user_request(
            message, data_context, request_workflow
        )

        # 4. Формируем промпт с контекстом и данными, которые пользователь реально запросил
        prompt = self._build_chat_prompt(
            message, context, medium_term, knowledge_context, visible_data_context, request_workflow
        )

        # 5. Генерируем ответ или отдаём строгий срез задач из БД
        if agent_work_result and (agent_work_result or {}).get("segment"):
            response = self._format_agent_work_result_response(agent_work_result)
        elif cron_management_result:
            response = self._format_cron_management_response(
                cron_management_result,
                (visible_data_context or {}).get("admin_cron") if visible_data_context else None,
            )
        elif self._is_current_tasks_question(message) and visible_data_context and visible_data_context.get("current_tasks"):
            response = self._format_current_tasks_response(visible_data_context["current_tasks"])
        else:
            system_prompt = await self.get_active_system_prompt(
                self.db, self.AGENT_TYPE, DIRECTOR_SYSTEM_PROMPT
            )
            response = await self.generate_response(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model if isinstance(model, str) and "/" in model else None,
                temperature=0.5,
                max_tokens=4000,
            )

        # 6. Сохраняем сообщение пользователя
        user_msg = DirectorChatMessage(
            user_id=user_id,
            message=message,
            message_type=self._detect_message_type(message),
            message_direction="user",
            category=category,
            session_id=session_id,
            extra_data={"session_id": session_id} if session_id else {},
        )
        self.db.add(user_msg)
        await self.db.flush()

        # 7. Сохраняем ответ директора
        director_extra = {"session_id": session_id} if session_id else {}
        director_extra["request_workflow"] = request_workflow
        if data_context:
            director_extra["data_used"] = list(data_context.keys())
            director_extra["visible_data_used"] = list((visible_data_context or {}).keys())
            rich_blocks = self._build_rich_response_blocks(visible_data_context or {}, request_workflow, message)
            if rich_blocks:
                director_extra["rich_blocks"] = rich_blocks
        director_msg = DirectorChatMessage(
            user_id=user_id,
            message=response,
            message_type="response",
            message_direction="director",
            category=category,
            parent_message_id=user_msg.id,
            session_id=session_id,
            extra_data=director_extra,
        )
        self.db.add(director_msg)

        mirror_director_turn_to_hermes_web_ui(
            user_id=str(user_id),
            session_id=session_id,
            user_message=message,
            director_response=response,
            model=model if isinstance(model, str) else None,
        )

        # 8. Обновляем контекст сессии
        if context:
            context.last_activity_at = func.now()

        # 9. Анализируем, нужно ли сохранить в среднесрочную память
        await self._analyze_and_store_memory(user_id, message, response, user_msg.id)

        # 10. Анализируем, нужно ли векторизовать в базу знаний
        await self._analyze_and_vectorize_knowledge(user_id, message, response, user_msg.id)

        await self.db.commit()

        return {
            "user_message_id": str(user_msg.id),
            "director_message_id": str(director_msg.id),
            "response": response,
            "session_id": session_id,
            "message_type": "response",
            "category": category,
            "priority": director_msg.priority or "P2",
            "message_id": str(user_msg.id),
            "response_id": str(director_msg.id),
            "action": "respond",
            "extracted_task": None,
            "suggested_knowledge": None,
            "extra_data": director_extra,
            "context_used": {
                "medium_term_count": len(medium_term),
                "knowledge_count": len(knowledge_context),
                "data_fetched": bool(data_context),
                "workflow_intent": request_workflow.get("intent"),
            },
        }

    def _build_request_workflow(self, message: str) -> Dict[str, Any]:
        """Планирует рабочий цикл директора: какие данные, агенты и инструменты нужны до ответа."""
        msg_lower = (message or "").lower()

        def has(*keywords: str) -> bool:
            return any(keyword in msg_lower for keyword in keywords)

        intent = "general"
        if has("рассыл", "crm", "сегмент", "клиент", "покупател"):
            intent = "crm_campaign"
        if has("uno", "product focus", "ассортимент", "sku", "остат", "товар"):
            intent = "product_campaign" if intent in {"general", "crm_campaign"} else intent
        if has("отчет", "отчёт", "аналит", "график", "динамик", "конверс", "выручк", "продаж"):
            intent = "analytics_report"
        if has("кампани", "запуск", "план", "first look", "прогрев", "увеличить продажи", "рост продаж"):
            intent = "campaign_orchestration"
        if has("крон", "cron", "регламент", "регламенты", "периодическ", "автозадач", "авто-задач"):
            intent = "cron_management"

        data_requests: List[Dict[str, str]] = []
        agent_requests: List[Dict[str, str]] = []

        def add_data(key: str, label: str, reason: str) -> None:
            if not any(item["key"] == key for item in data_requests):
                data_requests.append({"key": key, "label": label, "reason": reason})

        def add_agent(agent: str, label: str, request: str, expected: str) -> None:
            if not any(item["agent"] == agent for item in agent_requests):
                agent_requests.append({"agent": agent, "label": label, "request": request, "expected": expected})

        if intent in {"campaign_orchestration", "crm_campaign", "product_campaign"}:
            add_data("current_tasks", "Актуальные задачи", "Понять, нет ли уже активной работы по теме.")
            add_data("customer_summary", "Покупатели и loyalty", "Оценить базу, VIP/активных/спящих клиентов и доступные атрибуты.")
            add_data("sales_metrics", "Продажи и чеки", "Понять текущую динамику, чек и выручку для цели кампании.")
            add_data("stores", "Магазины", "Проверить точки, посещаемость и продажи по магазинам.")
            add_agent("crm-agent", "AI CRM", "Собрать сегменты, каналы, ограничения и сценарий коммуникации.", "Сегменты, размер базы, тексты, условия согласования.")

        if intent in {"campaign_orchestration", "product_campaign"} or has("uno", "sku", "остат", "ассортимент", "product focus"):
            add_data("product_summary", "Каталог и товары", "Понять бренды, категории и товарный контекст.")
            add_data("inventory", "Остатки", "Проверить наличие и магазины для товарного фокуса.")
            add_data("top_products", "Топ товаров", "Увидеть, что уже продаётся и что можно усилить.")
            add_agent("assortment-agent", "AI Assortment", "Собрать Product Focus, остатки, SKU и товарные гипотезы.", "Список SKU/групп, приоритеты, риски остатков.")

        if intent in {"campaign_orchestration", "analytics_report"} or has("отчет", "отчёт", "аналит", "график", "конверс"):
            add_data("store_visits", "Офлайн-посещения", "Связать посещаемость магазинов с продажами.")
            add_data("website_traffic", "Сайт", "Проверить онлайн-трафик и страницы.")
            add_data("app_usage", "Приложение", "Проверить поведение пользователей во Flutter-приложении.")
            add_data("instagram_analytics", "Instagram", "Оценить соцсети и Reels/охваты, если источник доступен.")
            add_agent("analytics-agent", "AI Analytics", "Собрать KPI, базовые метрики, динамику и контрольные точки.", "Короткий аналитический вывод, KPI и что измерять.")

        if intent == "campaign_orchestration" or has("контент", "сторис", "reels", "фото", "видео"):
            add_agent("brand-media-agent", "AI Brand Media", "Подготовить контент-пакет, сторис, визуальные акценты и тексты.", "Контент-структура, hero-материалы, тексты и формат подачи.")

        if intent == "campaign_orchestration" or has("трафик", "реклама", "digital", "канал"):
            add_agent("traffic-growth-agent", "AI Traffic & Growth", "Проверить каналы трафика и поддержку кампании.", "План digital support, гипотезы роста и ограничения запуска.")

        if intent == "cron_management":
            add_data("admin_cron", "CRON регламенты", "Проверить расписания, ответственных агентов, последние запуски и задачи, созданные регламентами.")

        steps = [
            "Принять и классифицировать запрос пользователя.",
            "Определить необходимые данные, инструменты и профильных агентов.",
            "Получить доступные срезы из БД и сервисов платформы.",
            "Сверить результат с актуальными задачами и ограничениями.",
            "Сформировать интерактивный ответ: вывод, данные, решения и кнопки запуска задач.",
        ]

        return {
            "intent": intent,
            "steps": steps,
            "data_requests": data_requests,
            "agent_requests": agent_requests,
            "requires_agent_work": bool(agent_requests),
        }

    async def _auto_execute_required_agent_work(
        self,
        user_id: UUID,
        message: str,
        request_workflow: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Автономно выполняет маленькие подзадачи, без ожидания ручного запуска агентам."""
        msg_lower = (message or "").lower()
        if self._is_existing_crm_segment_question(message):
            return await self._get_latest_crm_agent_work_result()
        intent = (request_workflow or {}).get("intent")
        is_crm_campaign = intent in {"crm_campaign", "campaign_orchestration", "product_campaign"} and any(
            keyword in msg_lower for keyword in ["рассыл", "crm", "сегмент", "клиент", "покупател"]
        )
        if not is_crm_campaign:
            return None

        try:
            from app.api.agent_interactions import (
                _calc_count,
                _dedupe_segment_name,
                _enrich_rules_with_stores,
                _extract_segment_business_meta,
                _extract_segment_rules_from_plan,
                _make_ai_segment_description,
            )
            from app.models.customer_segment import CustomerSegment

            title = self._build_crm_task_title(message)
            directive = self._build_crm_agent_directive(message)
            source_text = f"{title}\n{message}\n{directive}"
            segment_meta = _extract_segment_business_meta(source_text)
            segment_rules = _extract_segment_rules_from_plan(source_text, title)
            segment_rules = await _enrich_rules_with_stores(self.db, segment_rules, source_text)
            initial_customer_count = await _calc_count(self.db, segment_rules)
            refinement = await self._refine_crm_segment_to_target(
                segment_rules,
                source_text,
                target_min=100,
                target_max=120,
            )
            segment_rules = refinement["rules"]
            customer_count = int(refinement["count"])

            expected_result = (
                "Редактируемый сегмент покупателей, критерии отбора, риски, "
                "каналы коммуникации и статус согласования для директора."
            )
            existing_task = await self._find_active_crm_task_for_update(message, title)
            if existing_task:
                task = existing_task
                task.task_context = {
                    **(task.task_context or {}),
                    "title": title,
                    "board": "crm",
                    "created_by_director": True,
                    "original_user_request": message,
                    "workflow_intent": intent,
                    "passport_updated_at": datetime.utcnow().isoformat(),
                }
                task.input_data = {
                    **(task.input_data or {}),
                    "title": title,
                    "description": directive,
                    "expected_result": expected_result,
                }
                task.requirements = {
                    **(task.requirements or {}),
                    "must_create_editable_segment": True,
                    "must_log_dialog": True,
                    "must_not_ask_what_data_exists": True,
                    "segment_approval_required": True,
                }
                task.constraints = {
                    **(task.constraints or {}),
                    "source_of_truth": "GLAME DB customer_segments + user_segments/customer filters",
                    "no_mass_send_without_admin_approval": True,
                }
                task.priority = 1
                task.status = InteractionStatus.PROCESSING.value
                task.updated_at = datetime.utcnow()
                self.db.add(task)
                await self.db.flush()
                self.db.add(
                    AgentInteractionLog(
                        task_id=task.id,
                        agent_name="system",
                        event_type="chat_reset",
                        event_data={"reason": "director_updated_existing_crm_task", "source": "director_agent"},
                        message="Директор обновил паспорт: начат новый чат внутри существующей CRM-задачи",
                    )
                )
            else:
                task = AgentInteractionTask(
                    source_agent="director-agent",
                    target_agent="crm-agent",
                    task_type="crm_segmentation_and_messaging",
                    task_context={
                        "title": title,
                        "board": "crm",
                        "created_by_director": True,
                        "original_user_request": message,
                        "workflow_intent": intent,
                    },
                    input_data={
                        "title": title,
                        "description": directive,
                        "expected_result": expected_result,
                    },
                    requirements={
                        "must_create_editable_segment": True,
                        "must_log_dialog": True,
                        "must_not_ask_what_data_exists": True,
                        "segment_approval_required": True,
                    },
                    constraints={
                        "source_of_truth": "GLAME DB customer_segments + user_segments/customer filters",
                        "no_mass_send_without_admin_approval": True,
                    },
                    priority=1,
                    status=InteractionStatus.PROCESSING.value,
                )
                self.db.add(task)
                await self.db.flush()

            segment_name = segment_meta.get("name") or f"AI CRM | сегмент на согласование | {datetime.utcnow():%d.%m %H:%M}"
            segment = None
            try:
                existing_segment_id = (task.task_context or {}).get("segment_id")
                if existing_segment_id:
                    row = await self.db.execute(select(CustomerSegment).where(CustomerSegment.id == UUID(str(existing_segment_id))))
                    existing_segment = row.scalar_one_or_none()
                    if existing_segment and bool(getattr(existing_segment, "is_auto_generated", True)):
                        segment = existing_segment
            except Exception:
                segment = None
            if segment:
                segment.name = _dedupe_segment_name(segment_name, str(segment.id))
                segment.description = _make_ai_segment_description(segment_meta, source_text)
                segment.rules = segment_rules
                segment.customer_count = customer_count
                segment.updated_at = datetime.utcnow()
            else:
                segment = CustomerSegment(
                    id=uuid4(),
                    name=_dedupe_segment_name(segment_name, str(task.id)),
                    description=_make_ai_segment_description(segment_meta, source_text),
                    rules=segment_rules,
                    customer_count=customer_count,
                    is_auto_generated=True,
                    is_active=True,
                )
                self.db.add(segment)
            await self.db.flush()
            try:
                from app.api.customer_segmentation import materialize_segment_members

                customer_count = await materialize_segment_members(
                    self.db,
                    segment.id,
                    segment_rules,
                    assigned_by="ai",
                    confidence_score=0.92,
                )
                segment.customer_count = customer_count
            except Exception:
                logger.warning("Failed to materialize AI CRM segment members", exc_info=True)

            task_ctx = dict(task.task_context or {})
            task_ctx.update(
                {
                    "segment_id": str(segment.id),
                    "segment_name": segment.name,
                    "segment_rules": segment_rules,
                    "segment_meta": segment_meta,
                    "segment_customer_count": customer_count,
                    "segment_edit_path": segment_meta.get("edit_path") or "/admin/customers/segments",
                    "segment_initial_customer_count": initial_customer_count,
                    "segment_refinement": refinement,
                }
            )
            task.task_context = task_ctx
            task.output_data = {
                "segment_id": str(segment.id),
                "segment_name": segment.name,
                "segment_customer_count": customer_count,
                "segment_rules": segment_rules,
                "agent_reply": self._build_crm_agent_result_text(segment, segment_rules, customer_count, refinement, initial_customer_count, str(task.id)),
                "needs_user_attention": True,
            }
            task.output_metadata = {
                "closed_by": "director-autonomous-orchestration",
                "closure_status": InteractionStatus.PENDING_APPROVAL.value,
                "evaluated_at": datetime.utcnow().isoformat(),
            }
            task.status = InteractionStatus.PENDING_APPROVAL.value

            self.db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="director-agent",
                    event_type="dialog_message",
                    event_data={
                        "role": "user",
                        "from_director": True,
                        "step_type": "segmentation",
                        "user_id": str(user_id),
                    },
                    message=directive,
                )
            )
            crm_reply = task.output_data["agent_reply"]
            self.db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="crm-agent",
                    event_type="dialog_message",
                    event_data={
                        "kind": "assistant_reply",
                        "role": "assistant",
                        "from_agent": "crm-agent",
                        "segment_id": str(segment.id),
                        "segment_name": segment.name,
                    },
                    message=crm_reply,
                )
            )
            if initial_customer_count < 100 and customer_count >= 100:
                refined_reply = (
                    "Сегмент расширен до рабочего диапазона. Я сохранил обновленные правила: "
                    f"{customer_count} покупателей. Строгий фильтр дал {initial_customer_count}. "
                    f"segment_id: {segment.id}. task_id: {task.id}. "
                    "Результат можно передавать директору на согласование администратором."
                )
                self.db.add(
                    AgentInteractionLog(
                        task_id=task.id,
                        agent_name="director-agent",
                        event_type="dialog_message",
                        event_data={
                            "role": "user",
                            "from_director": True,
                            "step_type": "segmentation_refinement",
                            "target_min": 100,
                            "target_max": 120,
                        },
                        message=(
                            "AI CRM, текущий сегмент слишком маленький для кампании "
                            f"({initial_customer_count}). Расширь критерии до рабочего диапазона "
                            "100-120 релевантных покупателей: оставь Симферополь/Центрум и высокую вероятность покупки, "
                            "но добавь смежные признаки интереса к серебру, крупным формам, регулярности и высокому чеку. "
                            "Обнови сохраненный сегмент и верни итог для согласования."
                        ),
                    )
                )
                self.db.add(
                    AgentInteractionLog(
                        task_id=task.id,
                        agent_name="crm-agent",
                        event_type="dialog_message",
                        event_data={
                            "kind": "assistant_reply",
                            "role": "assistant",
                            "from_agent": "crm-agent",
                            "segment_id": str(segment.id),
                            "segment_name": segment.name,
                            "refined": True,
                        },
                        message=refined_reply,
                    )
                )
                crm_reply = refined_reply
            self.db.add(
                AgentInteractionLog(
                    task_id=task.id,
                    agent_name="crm-agent",
                    event_type="segmentation_completed",
                    event_data={
                        "segment_id": str(segment.id),
                        "segment_name": segment.name,
                        "customer_count": customer_count,
                        "rules": segment_rules,
                        "meta": segment_meta,
                        "edit_path": task_ctx["segment_edit_path"],
                    },
                    message=f"AI CRM сохранил редактируемый сегмент: {segment.name} ({customer_count})",
                )
            )

            await self.db.commit()

            return {
                "status": "completed_needs_approval",
                "summary": "AI CRM отработал подзадачу: сегмент создан и ожидает согласования администратора.",
                "task": {
                    "id": str(task.id),
                    "title": title,
                    "target_agent": "crm-agent",
                    "status": task.status,
                    "href": f"/ai-marketer/tasks/{task.id}",
                },
                "segment": {
                    "id": str(segment.id),
                    "name": segment.name,
                    "customer_count": customer_count,
                    "edit_path": task_ctx["segment_edit_path"],
                    "rules": segment_rules,
                },
                "agent_dialog": {
                    "director_request": directive,
                    "crm_reply": crm_reply,
                },
                "next_admin_actions": [
                    "Проверить критерии сегмента и количество покупателей.",
                    "При необходимости отредактировать фильтры в «Покупатели → Сегменты покупателей».",
                    "Согласовать сегмент перед генерацией и отправкой сообщений.",
                ],
            }
        except Exception as exc:
            logger.warning("Director autonomous CRM orchestration failed", exc_info=True)
            try:
                await self.db.rollback()
            except Exception:
                pass
            return {
                "status": "failed",
                "summary": "Не удалось автоматически подготовить CRM-сегмент.",
                "error": str(exc),
            }

    @staticmethod
    def _is_cron_message(message: str, request_workflow: Optional[Dict[str, Any]] = None) -> bool:
        src = (message or "").lower()
        return (request_workflow or {}).get("intent") == "cron_management" or any(
            marker in src for marker in ["крон", "cron", "регламент", "регламенты", "периодическ", "автозадач", "авто-задач"]
        )

    async def _get_admin_cron_context(self) -> Dict[str, Any]:
        from app.services.cron_registry import list_cron_jobs, list_cron_runs

        jobs = await list_cron_jobs(self.db)
        runs = await list_cron_runs(self.db, limit=20)
        return {
            "jobs": jobs,
            "runs": runs,
            "total": len(jobs),
            "enabled_count": sum(1 for job in jobs if job.get("enabled")),
            "source_of_truth": ["admin_cron_jobs", "admin_cron_runs", "agent_interaction_tasks"],
        }

    @staticmethod
    def _agent_from_text(text_value: str) -> Optional[str]:
        src = (text_value or "").lower()
        if "crm" in src or "клиент" in src or "рассыл" in src:
            return "crm-agent"
        if "ассортимент" in src or "поступлен" in src or "остат" in src or "товар" in src:
            return "assortment-agent"
        if "аналит" in src or "отчет" in src or "отчёт" in src or "метрик" in src:
            return "analytics-agent"
        if "контент" in src or "сторис" in src or "reels" in src:
            return "brand-media-agent"
        if "трафик" in src or "реклам" in src:
            return "traffic-growth-agent"
        if "директор" in src or "план" in src:
            return "director-agent"
        return None

    @staticmethod
    def _category_from_agent(agent: Optional[str]) -> str:
        return {
            "crm-agent": "crm",
            "assortment-agent": "assortment",
            "analytics-agent": "analytics",
            "brand-media-agent": "director",
            "traffic-growth-agent": "director",
            "director-agent": "director",
        }.get(agent or "", "system")

    @staticmethod
    def _task_type_from_text(text_value: str, agent: Optional[str]) -> str:
        src = (text_value or "").lower()
        if "др" in src or "день рожд" in src:
            return "crm_birthday_check"
        if "лояльност" in src or "возврат" in src or "спящ" in src:
            return "crm_loyalty_reactivation_check"
        if "поступлен" in src or "новин" in src:
            return "new_arrivals_marketing_check"
        if "остат" in src or "slow" in src:
            return "inventory_control_review"
        if "отчет" in src or "отчёт" in src or "аналит" in src:
            return "daily_marketing_analysis"
        if agent == "crm-agent":
            return "crm_scheduled_check"
        if agent == "assortment-agent":
            return "assortment_scheduled_check"
        if agent == "analytics-agent":
            return "analytics_scheduled_check"
        return "scheduled_admin_task"

    def _find_cron_job_for_message(self, message: str, jobs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        src = (message or "").lower()
        for job in jobs:
            if str(job.get("id") or "").lower() in src:
                return job
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for job in jobs:
            title_words = [w for w in re.split(r"\W+", str(job.get("title") or "").lower()) if len(w) >= 4]
            score = sum(1 for word in title_words if word in src)
            if score:
                scored.append((score, job))
        if scored:
            scored.sort(key=lambda item: item[0], reverse=True)
            return scored[0][1]
        agent = self._agent_from_text(src)
        if agent:
            for job in jobs:
                if job.get("target_agent") == agent:
                    return job
        return None

    @staticmethod
    def _extract_cron_patch(message: str, current_job: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        src = (message or "").lower()
        patch: Dict[str, Any] = {}
        time_match = re.search(r"\b([01]?\d|2[0-3])[:.](\d{2})\b", message or "")
        if time_match:
            patch["time_of_day"] = f"{int(time_match.group(1)):02d}:{int(time_match.group(2)):02d}"
            if not patch.get("schedule_type"):
                patch["schedule_type"] = (current_job or {}).get("schedule_type") if (current_job or {}).get("schedule_type") != "hourly" else "daily"
        interval_match = re.search(r"(?:каждые|раз в)\s+(\d{1,4})\s*(?:мин|минут)", src)
        if interval_match:
            patch["schedule_type"] = "hourly"
            params = dict((current_job or {}).get("parameters") or {})
            params["interval_minutes"] = max(5, min(int(interval_match.group(1)), 1440))
            patch["parameters"] = params
        if "ежеднев" in src or "каждый день" in src:
            patch["schedule_type"] = "daily"
        if "еженед" in src or "раз в неделю" in src:
            patch["schedule_type"] = "weekly"
        if "ежемесяч" in src or "раз в месяц" in src:
            patch["schedule_type"] = "monthly"
        weekday_map = {
            "понедель": 0,
            "вторник": 1,
            "сред": 2,
            "четвер": 3,
            "пятниц": 4,
            "суббот": 5,
            "воскрес": 6,
        }
        for marker, value in weekday_map.items():
            if marker in src:
                patch["weekday"] = value
                patch["schedule_type"] = "weekly"
                break
        day_match = re.search(r"(\d{1,2})\s*(?:числа|день месяца)", src)
        if day_match:
            patch["day_of_month"] = max(1, min(int(day_match.group(1)), 28))
            patch["schedule_type"] = "monthly"
        agent = DirectorAgent._agent_from_text(src)
        if agent:
            patch["target_agent"] = agent
            patch["category"] = DirectorAgent._category_from_agent(agent)
        if "включ" in src:
            patch["enabled"] = True
        if "выключ" in src or "отключ" in src:
            patch["enabled"] = False
        return patch

    async def _auto_manage_cron_jobs(
        self,
        message: str,
        request_workflow: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not self._is_cron_message(message, request_workflow):
            return None

        src = (message or "").lower()
        mutation_markers = [
            "создай", "добавь", "включ", "выключ", "отключ", "запусти", "запуск",
            "сохрани", "перенеси", "поставь", "назначь", "измени", "обнови",
        ]
        if not any(marker in src for marker in mutation_markers):
            return None

        from app.services.cron_registry import create_cron_job, list_cron_jobs, run_cron_job, update_cron_job

        jobs = await list_cron_jobs(self.db)
        create_requested = any(marker in src for marker in ["создай", "добавь", "новый регламент", "новую автозадач"])
        run_requested = "запусти" in src or "запуск сейчас" in src or "запустить сейчас" in src

        try:
            if create_requested:
                quoted = re.search(r"[«\"]([^»\"]{3,120})[»\"]", message or "")
                tail = re.split(r"создай|добавь", message or "", flags=re.IGNORECASE)
                title = quoted.group(1).strip() if quoted else (tail[-1].strip(" .:")[:120] if len(tail) > 1 else "Новый CRON регламент")
                title = re.sub(r"^(регламент|крон|cron)\s+", "", title, flags=re.IGNORECASE).strip() or "Новый CRON регламент"
                agent = self._agent_from_text(message) or "director-agent"
                patch = self._extract_cron_patch(message)
                payload = {
                    "title": title[:200],
                    "description": message.strip(),
                    "category": patch.get("category") or self._category_from_agent(agent),
                    "target_agent": patch.get("target_agent") or agent,
                    "task_type": self._task_type_from_text(message, patch.get("target_agent") or agent),
                    "schedule_type": patch.get("schedule_type") or "daily",
                    "time_of_day": patch.get("time_of_day") or "09:00",
                    "weekday": patch.get("weekday"),
                    "day_of_month": patch.get("day_of_month"),
                    "enabled": bool(patch.get("enabled", False)),
                    "parameters": patch.get("parameters") or {"approval_required": True, "managed_by_director": True},
                }
                job = await create_cron_job(self.db, payload)
                return {
                    "status": "applied",
                    "action": "create",
                    "message": f"Создал CRON-регламент «{job.get('title')}».",
                    "job": job,
                }

            job = self._find_cron_job_for_message(message, jobs)
            if not job:
                return {
                    "status": "needs_clarification",
                    "action": "select_job",
                    "message": "Не понял, какой CRON-регламент нужно изменить. Назовите регламент или его id.",
                    "available_jobs": [{"id": j.get("id"), "title": j.get("title")} for j in jobs[:12]],
                }

            if run_requested:
                run = await run_cron_job(self.db, str(job["id"]), manual=True)
                return {
                    "status": "applied",
                    "action": "run_now",
                    "message": f"Запустил регламент «{job.get('title')}» и создал задачу агенту.",
                    "job": job,
                    "run": run,
                }

            patch = self._extract_cron_patch(message, job)
            if not patch:
                return {
                    "status": "needs_clarification",
                    "action": "edit",
                    "message": f"Регламент «{job.get('title')}» найден, но я не увидел конкретную правку.",
                    "job": job,
                }
            updated = await update_cron_job(self.db, str(job["id"]), patch)
            return {
                "status": "applied",
                "action": "update",
                "message": f"Обновил CRON-регламент «{updated.get('title')}».",
                "job": updated,
                "patch": patch,
            }
        except Exception as exc:
            logger.warning("Director CRON management failed", exc_info=True)
            try:
                await self.db.rollback()
            except Exception:
                pass
            return {
                "status": "failed",
                "action": "cron_management",
                "message": "Не удалось применить изменение CRON-регламента.",
                "error": str(exc),
            }

    @staticmethod
    def _format_cron_management_response(result: Dict[str, Any], cron_context: Optional[Dict[str, Any]] = None) -> str:
        status = result.get("status")
        if status == "needs_clarification":
            jobs = result.get("available_jobs") or []
            lines = [result.get("message") or "Нужно уточнить регламент."]
            if jobs:
                lines.append("\nДоступные регламенты:")
                for job in jobs:
                    lines.append(f"- `{job.get('id')}` — {job.get('title')}")
            return "\n".join(lines)
        if status == "failed":
            return f"Не смог применить изменение CRON: {result.get('error') or result.get('message')}"

        job = result.get("job") or {}
        lines = [
            result.get("message") or "CRON-регламент обновлен.",
            "",
            f"- Регламент: {job.get('title')}",
            f"- ID: `{job.get('id')}`",
            f"- Статус: {'включен' if job.get('enabled') else 'выключен'}",
            f"- Агент: {job.get('target_agent')}",
            f"- Тип задачи: `{job.get('task_type')}`",
            f"- Расписание: {job.get('schedule_type')} {job.get('time_of_day') or ''}".rstrip(),
            f"- Следующий запуск: {job.get('next_run_at') or 'не запланирован'}",
        ]
        run = result.get("run") or {}
        if run.get("task_id"):
            lines.extend([
                "",
                f"Создана задача агенту: `/ai-marketer/tasks/{run.get('task_id')}`",
                "Я буду учитывать этот запуск при следующих проверках CRON и статусов задач.",
            ])
        if cron_context:
            lines.extend([
                "",
                f"Сейчас включено регламентов: {cron_context.get('enabled_count', 0)} из {cron_context.get('total', 0)}.",
            ])
        return "\n".join(lines)

    @staticmethod
    def _is_existing_crm_segment_question(message: str) -> bool:
        src = (message or "").lower()
        question_markers = ["сколько", "какой размер", "размер сегмента", "сколько человек", "сколько покупателей"]
        object_markers = ["рассыл", "сегмент", "аудитор", "получател", "покупател", "человек"]
        action_markers = ["создай", "подбери", "сформируй", "расширь", "обнови", "измени", "пересобери"]
        return (
            any(marker in src for marker in question_markers)
            and any(marker in src for marker in object_markers)
            and not any(marker in src for marker in action_markers)
        )

    async def _get_latest_crm_agent_work_result(self) -> Optional[Dict[str, Any]]:
        from app.models.customer_segment import CustomerSegment

        active_statuses = [
            InteractionStatus.PENDING.value,
            InteractionStatus.VALIDATING.value,
            InteractionStatus.VALIDATED.value,
            InteractionStatus.PENDING_APPROVAL.value,
            InteractionStatus.APPROVED.value,
            InteractionStatus.QUEUED.value,
            InteractionStatus.PROCESSING.value,
        ]
        result = await self.db.execute(
            select(AgentInteractionTask)
            .where(
                AgentInteractionTask.target_agent == "crm-agent",
                AgentInteractionTask.task_type == "crm_segmentation_and_messaging",
                AgentInteractionTask.status.in_(active_statuses),
            )
            .order_by(desc(AgentInteractionTask.updated_at).nullslast(), desc(AgentInteractionTask.created_at))
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if not task:
            return None
        ctx = task.task_context or {}
        out = task.output_data or {}
        segment_id = ctx.get("segment_id") or out.get("segment_id")
        if not segment_id:
            return None
        segment = None
        try:
            row = await self.db.execute(select(CustomerSegment).where(CustomerSegment.id == UUID(str(segment_id))))
            segment = row.scalar_one_or_none()
        except Exception:
            segment = None
        if not segment:
            return None
        return {
            "status": "completed_needs_approval",
            "summary": "Найден последний сохраненный результат AI CRM по сегменту.",
            "task": {
                "id": str(task.id),
                "title": (task.input_data or {}).get("title") or (task.task_context or {}).get("title") or task.task_type,
                "target_agent": "crm-agent",
                "status": task.status,
                "href": f"/ai-marketer/tasks/{task.id}",
            },
            "segment": {
                "id": str(segment.id),
                "name": segment.name,
                "customer_count": int(segment.customer_count or 0),
                "edit_path": "/admin/customers/segments",
                "rules": segment.rules or {},
            },
            "agent_dialog": {
                "crm_reply": str(out.get("agent_reply") or ""),
            },
            "next_admin_actions": [
                "Проверить карточку сегмента и список покупателей.",
                "При необходимости отредактировать фильтры.",
                "После согласования продолжить эту же задачу как подготовку рассылки и текстов.",
            ],
        }

    @staticmethod
    def _build_crm_task_title(message: str) -> str:
        src = (message or "").lower()
        brand = "UNOde50" if "uno" in src else "бренд"
        store = "ТРК Центрум" if ("центрум" in src or "centrum" in src) else "магазин"
        return f"Сегмент для рассылки {brand} | {store}"

    async def _find_active_crm_task_for_update(
        self,
        message: str,
        title: str,
    ) -> Optional[AgentInteractionTask]:
        """Reuse the current CRM work item when the director refines the same assignment."""
        src = f"{message or ''}\n{title or ''}".lower()
        brand_key = "unode50" if "uno" in src else None
        store_keys = []
        if "центрум" in src or "centrum" in src or "симферопол" in src:
            store_keys.extend(["центрум", "centrum", "симферопол"])

        active_statuses = [
            InteractionStatus.PENDING.value,
            InteractionStatus.VALIDATING.value,
            InteractionStatus.VALIDATED.value,
            InteractionStatus.PENDING_APPROVAL.value,
            InteractionStatus.APPROVED.value,
            InteractionStatus.QUEUED.value,
            InteractionStatus.PROCESSING.value,
        ]
        result = await self.db.execute(
            select(AgentInteractionTask)
            .where(
                AgentInteractionTask.target_agent == "crm-agent",
                AgentInteractionTask.task_type == "crm_segmentation_and_messaging",
                AgentInteractionTask.status.in_(active_statuses),
            )
            .order_by(desc(AgentInteractionTask.updated_at).nullslast(), desc(AgentInteractionTask.created_at))
            .limit(20)
        )
        candidates = result.scalars().all()
        if not candidates:
            return None

        def haystack(task: AgentInteractionTask) -> str:
            return json.dumps(
                {
                    "task_context": task.task_context or {},
                    "input_data": task.input_data or {},
                    "task_type": task.task_type,
                },
                ensure_ascii=False,
                default=str,
            ).lower()

        for task in candidates:
            text_value = haystack(task)
            if brand_key and brand_key not in text_value.replace(" ", ""):
                continue
            if store_keys and not any(key in text_value for key in store_keys):
                continue
            return task

        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _build_crm_agent_directive(message: str) -> str:
        return (
            "AI Marketing Director передает конкретную CRM-подзадачу.\n\n"
            f"Исходный запрос администратора: {message}\n\n"
            "Суть задачи: подготовить редактируемый сегмент аудитории для рассылки по новому поступлению. "
            "Не спрашивай, какие данные есть: используй доступные CRM-поля, историю покупок, loyalty, "
            "магазин/город, бренд и товарные признаки.\n\n"
            "Критерии, которые нужно применить как стартовую логику: покупатели с высокой вероятностью покупки; "
            "VIP, активные и регулярные клиенты; интерес к UNOde50, серебру или крупным/statement-формам; "
            "привязка к Симферополю и/или ТРК Центрум; исключить нерелевантную массовую базу. "
            "Результат должен быть сохранен как сегмент в БД, доступный для ручного редактирования.\n\n"
            "Ответь как AI CRM: 1) какие данные использованы; 2) какие правила сегмента применены; "
            "3) размер сегмента; 4) риски; 5) что администратор должен согласовать перед передачей в рассылку."
        )

    @staticmethod
    def _build_crm_agent_result_text(
        segment: Any,
        rules: Dict[str, Any],
        customer_count: int,
        refinement: Optional[Dict[str, Any]] = None,
        initial_customer_count: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> str:
        refinement = refinement or {}
        initial_line = ""
        if initial_customer_count is not None and initial_customer_count != customer_count:
            initial_line = (
                f"- Первый строгий фильтр дал {initial_customer_count}; директор запросил расширение, "
                f"обновленный сегмент: {customer_count}.\n"
            )
        target_line = ""
        if refinement.get("target_applied"):
            target_line = "- Диапазон директора 100-120 применен: сегмент ограничен самым релевантным top-N.\n"
        return (
            "## AI CRM: сегмент аудитории подготовлен\n\n"
            f"- Сегмент: {segment.name}\n"
            f"- segment_id: {segment.id}\n"
            f"- task_id: {task_id or '—'}\n"
            f"- Покупателей по текущим правилам: {customer_count}\n"
            f"{initial_line}"
            f"{target_line}"
            "- Статус: готов к проверке и согласованию администратором, массовая отправка не запускалась.\n"
            "- Где редактировать: «Покупатели → Сегменты покупателей».\n\n"
            "### Использованные данные\n"
            "- CRM-профиль покупателя: город, предпочитаемый магазин, сегмент клиента.\n"
            "- История покупок: бренд, название товара, последняя/предпочтительная точка покупки.\n"
            "- Loyalty и покупательская активность: количество покупок и признаки регулярности.\n\n"
            "### Логика сегмента\n"
            "- База не массовая: только реальные покупатели.\n"
            "- Фокус на релевантность к UNOde50/серебру/крупным формам и магазину Центрум/Симферополь.\n"
            "- Сегмент сохранен как фильтруемый объект, чтобы администратор мог сузить или расширить правила.\n\n"
            "### Риски\n"
            "- Если размер сегмента слишком мал, нужно расширить критерии по брендам/категориям или периоду покупок.\n"
            "- Если сегмент слишком широк, нужно усилить фильтры по истории покупок UNOde50/серебра и активности.\n"
            "- Перед отправкой нужно проверить согласия на канал коммуникации.\n\n"
            "### Нужно согласовать\n"
            "- Подтвердить размер сегмента и правила отбора.\n"
            "- Подтвердить канал рассылки и исключения.\n"
            "- После согласования можно передавать директору на подготовку текста и запуск следующей подзадачи."
        )

    async def _refine_crm_segment_to_target(
        self,
        strict_rules: Dict[str, Any],
        source_text: str,
        target_min: int = 100,
        target_max: int = 120,
    ) -> Dict[str, Any]:
        """Подбирает рабочую CRM-выборку: сначала строгая, затем релевантное расширение и top-N."""
        from sqlalchemy import select
        from app.api.customer_segmentation import _build_select_for_rules
        from app.api.agent_interactions import _calc_count, _enrich_rules_with_stores
        from app.models.user import User as UserModel

        candidates: List[Tuple[str, Dict[str, Any]]] = [("strict", strict_rules)]
        src = (source_text or "").lower()
        base_city_store = {
            "logic": "AND",
            "filters": [
                {"field": "is_customer", "operator": "equals", "value": True},
                {
                    "logic": "OR",
                    "filters": [
                        {"field": "city", "operator": "ilike", "value": "Симферополь"},
                        {"field": "preferred_store_name", "operator": "ilike", "value": "Центрум"},
                        {"field": "last_store_name", "operator": "ilike", "value": "Центрум"},
                    ],
                },
                {"field": "total_purchases", "operator": ">=", "value": 1},
            ],
        }
        if "центрум" in src or "centrum" in src or "симферопол" in src:
            candidates.append(("simferopol_loyal_base", await _enrich_rules_with_stores(self.db, dict(base_city_store), source_text)))

        intent_or = {
            "logic": "OR",
            "filters": [
                {"field": "brand", "operator": "ilike", "value": "UNOde50"},
                {"field": "product_name", "operator": "ilike", "value": "UNOde50"},
                {"field": "category", "operator": "ilike", "value": "сереб"},
                {"field": "product_name", "operator": "ilike", "value": "сереб"},
                {"field": "category", "operator": "ilike", "value": "коль"},
                {"field": "category", "operator": "ilike", "value": "серь"},
                {"field": "category", "operator": "ilike", "value": "брасл"},
                {"field": "average_check", "operator": ">=", "value": 12000},
                {"field": "total_spent", "operator": ">=", "value": 30000},
            ],
        }
        expanded = {
            "logic": "AND",
            "filters": [*base_city_store["filters"], intent_or],
        }
        candidates.append(("expanded_interest", await _enrich_rules_with_stores(self.db, expanded, source_text)))

        broad_relevant = {
            "logic": "AND",
            "filters": [
                {"field": "is_customer", "operator": "equals", "value": True},
                {
                    "logic": "OR",
                    "filters": [
                        {"field": "city", "operator": "ilike", "value": "Симферополь"},
                        {"field": "preferred_store_name", "operator": "ilike", "value": "Центрум"},
                        {"field": "last_store_name", "operator": "ilike", "value": "Центрум"},
                    ],
                },
                {
                    "logic": "OR",
                    "filters": [
                        {"field": "customer_segment", "operator": "contains", "value": "VIP"},
                        {"field": "customer_segment", "operator": "contains", "value": "Active"},
                        {"field": "customer_segment", "operator": "contains", "value": "Regular"},
                        {"field": "total_purchases", "operator": ">=", "value": 2},
                        {"field": "average_check", "operator": ">=", "value": 10000},
                        {"field": "total_spent", "operator": ">=", "value": 25000},
                    ],
                },
            ],
        }
        candidates.append(("broad_relevant", await _enrich_rules_with_stores(self.db, broad_relevant, source_text)))

        best = {"label": "strict", "rules": strict_rules, "count": 0}
        for label, rules in candidates:
            try:
                count = await _calc_count(self.db, rules)
            except Exception:
                continue
            if target_min <= count <= target_max:
                return {"label": label, "rules": rules, "count": count, "target_applied": False}
            if count > best["count"]:
                best = {"label": label, "rules": rules, "count": count}

        if int(best["count"]) > target_max:
            base_stmt, _ = _build_select_for_rules(best["rules"])
            subq = base_stmt.subquery()
            top_stmt = (
                select(UserModel.id)
                .where(UserModel.id.in_(select(subq.c.id)))
                .order_by(
                    UserModel.customer_segment.desc().nullslast(),
                    UserModel.last_purchase_date.desc().nullslast(),
                    UserModel.total_purchases.desc().nullslast(),
                    UserModel.total_spent.desc().nullslast(),
                )
                .limit(target_max)
            )
            result = await self.db.execute(top_stmt)
            top_ids = [str(value) for value in result.scalars().all()]
            if top_ids:
                return {
                    "label": f"{best['label']}_top_{target_max}",
                    "rules": {"logic": "AND", "filters": [{"field": "id", "operator": "in", "value": top_ids}]},
                    "count": len(top_ids),
                    "target_applied": True,
                }

        return {**best, "target_applied": False}

    async def _fetch_data_context(self, message: str, request_workflow: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Определяет, нужны ли живые данные по сообщению, и возвращает их"""
        data_service = DirectorDataService(self.db)
        msg_lower = message.lower()
        requested_data = {
            item.get("key")
            for item in ((request_workflow or {}).get("data_requests") or [])
            if isinstance(item, dict) and item.get("key")
        }

        data_keywords = [
            "продаж", "выручк", "заказ", "покупк", "товар", "клиент",
            "покупател", "категори", "бренд", "магазин", "кампани",
            "статистик", "отчёт", "отчет", "сколько", "покажи",
            "данные", "метрик", "цифр", "итог", "суммар",
            "тенденци", "тренд", "динамик", "график", "актуаль",
            "сегодня", "вчера", "на этой недел", "в этом месяце",
            "лояльност", "бонус", "балл", "остат", "склад", "налич",
            "чек", "посещ", "визит", "трафик", "конверс", "агент",
            "страниц", "страницы", "клик", "клики", "действия", "счетчик",
            "счётчик", "приложени", "app", "ui",
            "агентов", "навык", "инструмент", "взаимодейств",
            "задач", "задани", "работе", "в работе", "канбан", "статус",
            "блокер", "согласован", "приоритет",
            "план", "планирован", "поднимать продажи", "рост продаж",
            "увеличить продажи", "что делать", "с чего начать", "начать",
        ]
        if not requested_data and not any(kw in msg_lower for kw in data_keywords):
            return None

        data = {}
        if any(kw in msg_lower for kw in ["агент", "агентов", "навык", "инструмент", "взаимодейств"]) or (request_workflow or {}).get("requires_agent_work"):
            data["agent_registry"] = get_marketing_agent_registry()

        if "current_tasks" in requested_data or any(kw in msg_lower for kw in [
            "задач", "задани", "работе", "в работе", "канбан", "статус",
            "блокер", "согласован", "приоритет", "план", "планирован",
            "поднимать продажи", "рост продаж", "увеличить продажи",
            "что делать", "с чего начать", "начать",
        ]):
            try:
                data["current_tasks"] = await self._get_current_tasks_context(limit=50)
            except Exception as e:
                logger.warning(f"_get_current_tasks_context failed: {e}")

        if "admin_cron" in requested_data or any(kw in msg_lower for kw in ["крон", "cron", "регламент", "регламенты", "периодическ", "автозадач", "авто-задач"]):
            try:
                data["admin_cron"] = await self._get_admin_cron_context()
            except Exception as e:
                logger.warning(f"_get_admin_cron_context failed: {e}")

        period_days = None
        days_match = re.search(r"(\d{1,3})\s*(?:дн(?:ей|я|ь)?|сут(?:ок|ки)?)", msg_lower)
        if days_match:
            period_days = max(1, min(int(days_match.group(1)), 365))
        if any(kw in msg_lower for kw in ["недел", "7 дней", "7 дн"]):
            period_days = 7
        elif any(kw in msg_lower for kw in ["месяц", "30 дней", "30 дн"]):
            period_days = 30
        elif any(kw in msg_lower for kw in ["актуаль", "текущ", "свеж"]):
            period_days = 7

        if any(kw in msg_lower for kw in ["сегодня", "сегодняшн"]):
            try:
                data["sales_today"] = await data_service.get_today_sales()
            except Exception as e:
                logger.warning(f"get_today_sales failed: {e}")

        if any(kw in msg_lower for kw in ["недел", "7 дней", "7 дн"]):
            try:
                data["sales_week"] = await data_service.get_sales_for_period(7)
            except Exception as e:
                logger.warning(f"get_sales_for_period(7) failed: {e}")

        if any(kw in msg_lower for kw in ["месяц", "30 дней", "30 дн"]):
            try:
                data["sales_month"] = await data_service.get_sales_for_period(30)
            except Exception as e:
                logger.warning(f"get_sales_for_period(30) failed: {e}")

        if any(kw in msg_lower for kw in ["график", "динамик", "тренд", "по дням", "chart"]):
            try:
                data["sales_trend"] = await data_service.get_daily_sales_trend(period_days or 14)
            except Exception as e:
                logger.warning(f"get_daily_sales_trend failed: {e}")

        if "customer_summary" in requested_data or any(kw in msg_lower for kw in ["покупател", "клиент", "лояльност"]):
            try:
                data["customer_summary"] = await data_service.get_customer_summary()
            except Exception as e:
                logger.warning(f"get_customer_summary failed: {e}")
            try:
                data["customer_data_capabilities"] = data_service.get_customer_data_capabilities()
            except Exception as e:
                logger.warning(f"get_customer_data_capabilities failed: {e}")
            try:
                customer_lookup = self._extract_customer_lookup(message)
                if customer_lookup:
                    data["customer_full_profile"] = await data_service.get_customer_full_profile(customer_lookup)
            except Exception as e:
                logger.warning(f"get_customer_full_profile failed: {e}")

        if "product_summary" in requested_data or any(kw in msg_lower for kw in ["товар", "ассортимент", "категори", "бренд"]):
            try:
                data["product_summary"] = await data_service.get_product_summary()
            except Exception as e:
                logger.warning(f"get_product_summary failed: {e}")

        if "top_products" in requested_data or any(kw in msg_lower for kw in ["топ", "лидер", "бестселлер", "популярн"]):
            try:
                data["top_products"] = await data_service.get_top_selling_products(10)
            except Exception as e:
                logger.warning(f"get_top_products failed: {e}")

        if "stores" in requested_data or any(kw in msg_lower for kw in ["магазин", "бутик", "точк"]):
            try:
                data["stores"] = await data_service.get_stores_summary(period_days)
            except Exception as e:
                logger.warning(f"get_stores_summary failed: {e}")

        if "inventory" in requested_data or any(kw in msg_lower for kw in ["остат", "склад", "налич", "товар"]):
            try:
                data["inventory"] = await data_service.get_inventory_summary()
            except Exception as e:
                logger.warning(f"get_inventory_summary failed: {e}")

        if "store_visits" in requested_data or any(kw in msg_lower for kw in ["посещ", "визит", "трафик", "конверс", "магазин"]):
            try:
                data["store_visits"] = await data_service.get_store_visits_summary(period_days or 7)
            except Exception as e:
                logger.warning(f"get_store_visits_summary failed: {e}")

        if "website_traffic" in requested_data or any(kw in msg_lower for kw in ["сайт", "метрик", "яндекс", "website", "web", "страниц", "страницы"]):
            try:
                data["website_traffic"] = await data_service.get_website_traffic_summary(period_days or 7)
            except Exception as e:
                logger.warning(f"get_website_traffic_summary failed: {e}")

        if "app_usage" in requested_data or any(kw in msg_lower for kw in ["страниц", "страницы", "клик", "клики", "действия", "счетчик", "счётчик", "приложени", "app", "ui", "flutter", "поведен"]):
            try:
                data["app_usage"] = await data_service.get_app_usage_summary(period_days or 7)
            except Exception as e:
                logger.warning(f"get_app_usage_summary failed: {e}")

        if "instagram_analytics" in requested_data or any(kw in msg_lower for kw in ["instagram", "инстаграм", "инста", "соцсет", "охват", "лайк", "reels"]):
            try:
                data["instagram_analytics"] = await data_service.get_instagram_analytics_summary(period_days or 7)
            except Exception as e:
                logger.warning(f"get_instagram_analytics_summary failed: {e}")

        if "analytics_agent_context" in requested_data or any(kw in msg_lower for kw in ["ai analytics", "аналитик", "аналитика", "отчет", "отчёт"]):
            try:
                data["analytics_agent_context"] = await data_service.get_analytics_agent_data_context(period_days or 7)
            except Exception as e:
                logger.warning(f"get_analytics_agent_data_context failed: {e}")

        if "sales_metrics" in requested_data or any(kw in msg_lower for kw in ["чек", "средний чек", "1с", "продаж", "выручк"]):
            try:
                data["sales_metrics"] = await data_service.get_sales_metrics_summary(period_days or 7)
            except Exception as e:
                logger.warning(f"get_sales_metrics_summary failed: {e}")

        if any(kw in msg_lower for kw in ["кампани", "маркетин"]) or (request_workflow or {}).get("intent") in {"campaign_orchestration", "crm_campaign", "product_campaign"}:
            try:
                data["campaigns"] = await data_service.get_active_campaigns()
            except Exception as e:
                logger.warning(f"get_active_campaigns failed: {e}")

        if any(kw in msg_lower for kw in ["последн", "свеж", "новые заказ"]):
            try:
                data["recent_orders"] = await data_service.get_recent_orders(10)
            except Exception as e:
                logger.warning(f"get_recent_orders failed: {e}")

        if not data:
            try:
                data["general_stats"] = await data_service.get_general_stats()
            except Exception as e:
                logger.warning(f"get_general_stats failed: {e}")

        return data if data else None

    @staticmethod
    def _extract_customer_lookup(message: str) -> Optional[str]:
        """Вытащить из сообщения явный идентификатор покупателя: телефон, email, UUID или карту."""
        text_value = message or ""
        email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}", text_value)
        if email_match:
            return email_match.group(0)

        uuid_match = re.search(
            r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
            text_value,
        )
        if uuid_match:
            return uuid_match.group(0)

        phone_match = re.search(r"(?:\+?7|8)?[\s(.-]*\d{3}[\s).-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}", text_value)
        if phone_match:
            return phone_match.group(0)

        card_match = re.search(r"(?:карта|карт[аы]|дисконт|номер)\D{0,12}([A-Za-zА-Яа-я0-9-]{5,})", text_value, re.IGNORECASE)
        if card_match:
            return card_match.group(1)

        return None

    @staticmethod
    def _requested_output_scopes(message: str, request_workflow: Optional[Dict[str, Any]] = None) -> set[str]:
        """Что пользователь просит именно показать в ответе, а не просто использовать как фон."""
        msg = (message or "").lower()
        scopes: set[str] = set()

        def has(*keywords: str) -> bool:
            return any(keyword in msg for keyword in keywords)

        def has_any_pattern(*patterns: str) -> bool:
            return any(re.search(pattern, msg) for pattern in patterns)

        asks_broad_report = has(
            "собери отчет", "собери отчёт", "управленческий отчет", "управленческий отчёт",
            "полный отчет", "полный отчёт", "сводк", "дашборд", "покажи все", "все данные",
        )
        asks_analytics = has("аналитик", "аналитика", "проанализируй", "анализ", "график", "динамик")

        if asks_broad_report:
            scopes.update({
                "workflow", "sales", "stores", "store_visits", "website_traffic",
                "app_usage", "instagram_analytics", "products", "inventory",
                "customers", "campaigns", "tasks",
            })
            return scopes

        if has("продаж", "выручк", "чек", "средний чек", "заказ", "1с"):
            scopes.add("sales")
        asks_store_analytics = (
            has("сравн", "рейтинг магаз", "эффективность магаз", "магазины: выручка")
            or has_any_pattern(
                r"покажи\s+(?:.*\s)?магазин",
                r"отч[её]т\s+(?:.*\s)?по\s+магазин",
                r"аналитик[а-я\s]+магазин",
                r"выручк[а-я\s]+по\s+магазин",
                r"продаж[а-я\s]+по\s+магазин",
                r"чек[а-я\s]+по\s+магазин",
            )
        )
        if asks_store_analytics:
            scopes.add("stores")
        if has("посещ", "визит", "трафик", "конверс") and not has("рассыл", "кампани"):
            scopes.add("store_visits")
        if has("сайт", "страниц", "website", "web", "метрик", "яндекс"):
            scopes.add("website_traffic")
        if has("приложени", "app", "flutter", "клик", "действия", "поведен"):
            scopes.add("app_usage")
        if has("instagram", "инстаграм", "инста", "reels", "охват", "соцсет"):
            scopes.add("instagram_analytics")
        if has("товар", "sku", "ассортимент", "бренд", "product focus", "топ", "бестселлер"):
            scopes.add("products")
        if has("остат", "склад", "налич"):
            scopes.add("inventory")
        if has("клиент", "покупател", "crm", "сегмент", "лояльност", "балл"):
            scopes.add("customers")
        if has("кампани", "маркетин", "рассыл"):
            scopes.add("campaigns")
        if has("задач", "задани", "в работе", "канбан", "статус", "блокер"):
            scopes.add("tasks")
        if has("крон", "cron", "регламент", "регламенты", "периодическ", "автозадач", "авто-задач"):
            scopes.add("cron")
        if has("агент", "агентов", "инструмент", "взаимодейств"):
            scopes.add("agents")

        if asks_analytics:
            scopes.add("workflow")
        return scopes

    def _filter_data_context_for_user_request(
        self,
        message: str,
        data_context: Optional[Dict[str, Any]],
        request_workflow: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Не отдаёт в промпт и rich UI блоки данные, которые пользователь не просил выводить."""
        if not data_context:
            return None
        scopes = self._requested_output_scopes(message, request_workflow)
        key_scopes = {
            "sales_today": "sales",
            "sales_week": "sales",
            "sales_month": "sales",
            "sales_metrics": "sales",
            "sales_trend": "sales",
            "stores": "stores",
            "store_visits": "store_visits",
            "website_traffic": "website_traffic",
            "app_usage": "app_usage",
            "instagram_analytics": "instagram_analytics",
            "product_summary": "products",
            "top_products": "products",
            "inventory": "inventory",
            "customer_summary": "customers",
            "customer_data_capabilities": "customers",
            "customer_full_profile": "customers",
            "campaigns": "campaigns",
            "current_tasks": "tasks",
            "recent_orders": "sales",
            "agent_registry": "agents",
            "agent_work_results": "campaigns",
            "admin_cron": "cron",
            "admin_cron_result": "cron",
            "analytics_agent_context": "workflow",
            "general_stats": "workflow",
        }
        visible: Dict[str, Any] = {}
        for key, value in data_context.items():
            if key in {"agent_work_results", "admin_cron_result"}:
                visible[key] = value
                continue
            scope = key_scopes.get(key)
            if scope and scope in scopes:
                visible[key] = value
        return visible or None

    def _build_rich_response_blocks(
        self,
        data_context: Dict[str, Any],
        request_workflow: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Готовит визуальные блоки для чата директора: KPI, графики, таблицы и карточки."""
        blocks: List[Dict[str, Any]] = []
        output_scopes = self._requested_output_scopes(message or "", request_workflow)

        agent_work = data_context.get("agent_work_results")
        if isinstance(agent_work, dict) and isinstance(agent_work.get("segment"), dict):
            segment = agent_work.get("segment") or {}
            task = agent_work.get("task") or {}
            rules = segment.get("rules") if isinstance(segment.get("rules"), dict) else {}
            blocks.append({
                "type": "segment_card",
                "title": "Сегмент для согласования",
                "segment": {
                    "id": segment.get("id"),
                    "name": segment.get("name"),
                    "customer_count": segment.get("customer_count"),
                    "edit_path": segment.get("edit_path") or "/admin/customers/segments",
                    "rules": rules,
                },
                "task": {
                    "id": task.get("id"),
                    "title": task.get("title"),
                    "href": task.get("href"),
                    "status": task.get("status"),
                },
                "actions": agent_work.get("next_admin_actions") or [],
            })

        if request_workflow and output_scopes.intersection({"workflow", "agents", "tasks"}):
            data_requests = request_workflow.get("data_requests") or []
            agent_requests = request_workflow.get("agent_requests") or []
            blocks.append({
                "type": "workflow",
                "title": "Как директор собрал ответ",
                "intent": request_workflow.get("intent"),
                "steps": request_workflow.get("steps") or [],
                "data_requests": data_requests,
                "agent_requests": agent_requests,
                "meta": {
                    "source": "director-workflow",
                    "data_count": len(data_requests),
                    "agent_count": len(agent_requests),
                },
            })

        def money(value: Any) -> str:
            try:
                return f"{float(value or 0):,.0f} ₽".replace(",", " ")
            except Exception:
                return "0 ₽"

        def number(value: Any) -> str:
            try:
                return f"{float(value or 0):,.0f}".replace(",", " ")
            except Exception:
                return "0"

        sales = (
            data_context.get("sales_metrics")
            or data_context.get("sales_week")
            or data_context.get("sales_month")
            or data_context.get("sales_today")
        )
        if isinstance(sales, dict):
            blocks.append({
                "type": "kpi_grid",
                "title": "Продажи",
                "items": [
                    {"label": "Выручка", "value": money(sales.get("revenue_rub") or sales.get("total_revenue_rub")), "tone": "success"},
                    {"label": "Чеки", "value": number(sales.get("checks_count") or sales.get("orders_count")), "tone": "info"},
                    {"label": "Средний чек", "value": money(sales.get("average_check_rub") or sales.get("average_check")), "tone": "neutral"},
                    {"label": "Товаров", "value": number(sales.get("items_sold")), "tone": "neutral"},
                ],
                "meta": {
                    "period": sales.get("period"),
                    "source": sales.get("source"),
                    "last_date": sales.get("last_metric_date") or sales.get("last_sale_at"),
                },
            })

        trend = data_context.get("sales_trend")
        if isinstance(trend, list) and trend:
            blocks.append({
                "type": "line_chart",
                "title": "Динамика продаж по дням",
                "x_key": "date",
                "series": [
                    {"key": "revenue_rub", "label": "Выручка", "color": "#4f46e5"},
                    {"key": "orders_count", "label": "Заказы", "color": "#059669"},
                ],
                "data": trend[-30:],
            })

        stores = data_context.get("stores")
        if isinstance(stores, list) and stores:
            rows = stores[:8]
            blocks.append({
                "type": "bar_chart",
                "title": "Магазины: выручка и посещения",
                "x_key": "name",
                "series": [
                    {"key": "total_revenue_rub", "label": "Выручка", "color": "#4f46e5"},
                    {"key": "visitors", "label": "Посетители", "color": "#f59e0b"},
                ],
                "data": rows,
            })
            blocks.append({
                "type": "comparison_table",
                "title": "Сравнение магазинов",
                "columns": [
                    {"key": "name", "label": "Магазин"},
                    {"key": "total_revenue_rub", "label": "Выручка", "format": "money"},
                    {"key": "checks_count", "label": "Чеки", "format": "number"},
                    {"key": "visitors", "label": "Посетители", "format": "number"},
                    {"key": "revenue_per_visitor_rub", "label": "₽/пос.", "format": "money"},
                    {"key": "visit_conversion_rate", "label": "Конв.", "format": "percent"},
                ],
                "rows": rows,
            })

        visits = data_context.get("store_visits")
        if isinstance(visits, dict) and isinstance(visits.get("by_store"), list) and visits.get("by_store"):
            blocks.append({
                "type": "bar_chart",
                "title": "Посещаемость по магазинам",
                "x_key": "store_name",
                "series": [
                    {"key": "visitors", "label": "Посетители", "color": "#2563eb"},
                    {"key": "sales", "label": "Продажи", "color": "#16a34a"},
                ],
                "data": visits["by_store"][:10],
            })

        top_products = data_context.get("top_products")
        if isinstance(top_products, list) and top_products:
            blocks.append({
                "type": "product_cards",
                "title": "Топ товаров",
                "items": [
                    {
                        "id": item.get("id"),
                        "name": item.get("product_name") or item.get("name"),
                        "brand": item.get("brand"),
                        "category": item.get("category"),
                        "article": item.get("article"),
                        "metric": f"{number(item.get('total_sold'))} шт.",
                        "revenue": money(item.get("total_revenue_rub")),
                        "image_url": item.get("image_url"),
                    }
                    for item in top_products[:6]
                ],
            })

        app_usage = data_context.get("app_usage")
        if isinstance(app_usage, dict):
            top_pages = app_usage.get("top_pages")
            if isinstance(top_pages, list) and top_pages:
                blocks.append({
                    "type": "comparison_table",
                    "title": "Страницы приложения",
                    "columns": [
                        {"key": "page_url", "label": "Страница"},
                        {"key": "views", "label": "Просмотры", "format": "number"},
                    ],
                    "rows": top_pages[:10],
                })
            top_clicks = app_usage.get("top_clicks")
            if isinstance(top_clicks, list) and top_clicks:
                blocks.append({
                    "type": "comparison_table",
                    "title": "Действия пользователей",
                    "columns": [
                        {"key": "label", "label": "Действие"},
                        {"key": "clicks", "label": "Клики", "format": "number"},
                    ],
                    "rows": top_clicks[:10],
                })

        return blocks[:7]

    async def _get_current_tasks_context(self, limit: int = 50) -> Dict[str, Any]:
        """Возвращает актуальные задачи из БД для ответов директора."""
        active_agent_statuses = [
            InteractionStatus.PENDING.value,
            InteractionStatus.VALIDATING.value,
            InteractionStatus.VALIDATED.value,
            InteractionStatus.PENDING_APPROVAL.value,
            InteractionStatus.APPROVED.value,
            InteractionStatus.QUEUED.value,
            InteractionStatus.PROCESSING.value,
        ]
        final_agent_statuses = [
            InteractionStatus.COMPLETED.value,
            InteractionStatus.FAILED.value,
            InteractionStatus.CANCELLED.value,
            InteractionStatus.REJECTED.value,
            InteractionStatus.DELETED.value,
        ]
        director_active_statuses = ["pending", "in_progress", "blocked", "pending_approval", "approved", "queued", "processing"]
        director_final_statuses = ["completed", "cancelled", "rejected", "failed", "deleted"]

        director_result = await self.db.execute(
            select(DirectorTask)
            .where(DirectorTask.status.notin_(director_final_statuses))
            .order_by(desc(DirectorTask.created_at))
            .limit(limit)
        )
        director_tasks = director_result.scalars().all()

        agent_result = await self.db.execute(
            select(AgentInteractionTask)
            .where(
                and_(
                    AgentInteractionTask.status.notin_(final_agent_statuses),
                    AgentInteractionTask.task_type != "agent_control_chat",
                )
            )
            .order_by(AgentInteractionTask.priority.asc(), desc(AgentInteractionTask.created_at))
            .limit(limit)
        )
        agent_tasks = agent_result.scalars().all()

        def priority_label(value: Any) -> str:
            try:
                return f"P{max(0, int(value or 3) - 1)}"
            except Exception:
                return "P2"

        def title_from_agent_task(task: AgentInteractionTask) -> str:
            input_data = task.input_data or {}
            context = task.task_context or {}
            return input_data.get("title") or context.get("title") or task.task_type.replace("_", " ")

        def board_from_agent_task(task: AgentInteractionTask) -> Optional[str]:
            input_data = task.input_data or {}
            context = task.task_context or {}
            return context.get("board") or input_data.get("source_board")

        agent_items = [
            {
                "id": str(task.id),
                "source": "agent_interaction_tasks",
                "title": title_from_agent_task(task),
                "description": (task.input_data or {}).get("description") or (task.input_data or {}).get("expected_result") or task.error_message,
                "status": task.status,
                "priority": priority_label(task.priority),
                "source_agent": task.source_agent,
                "target_agent": task.target_agent,
                "board": board_from_agent_task(task),
                "task_type": task.task_type,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
                "href": f"/ai-marketer/tasks/{task.id}",
            }
            for task in agent_tasks
        ]

        director_items = [
            {
                "id": str(task.id),
                "source": "director_tasks",
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "source_agent": "user",
                "target_agent": task.target_agent or task.assigned_to or "director-agent",
                "board": (task.extra_data or {}).get("board"),
                "task_type": task.task_type,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
                "href": None,
            }
            for task in director_tasks
        ]

        all_items = sorted(
            director_items + agent_items,
            key=lambda item: (item.get("priority") or "P9", item.get("created_at") or ""),
        )[:limit]
        by_status: Dict[str, int] = {}
        by_agent: Dict[str, int] = {}
        for item in all_items:
            by_status[item["status"]] = by_status.get(item["status"], 0) + 1
            agent = item.get("target_agent") or "unknown"
            by_agent[agent] = by_agent.get(agent, 0) + 1

        return {
            "source_of_truth": ["director_tasks", "agent_interaction_tasks"],
            "generated_at_note": "Живой список из БД на момент ответа. Не использовать задачи из базы знаний как актуальные.",
            "total": len(all_items),
            "by_status": by_status,
            "by_agent": by_agent,
            "tasks": all_items,
        }

    def _is_current_tasks_question(self, message: str) -> bool:
        msg = message.lower()
        task_terms = ["задач", "задани", "канбан", "статус", "в работе", "блокер", "согласован"]
        question_terms = ["какие", "что", "покажи", "список", "сколько", "текущ", "актуаль", "работе", "статус"]
        create_terms = ["создай", "поставь", "сделай", "добавь задачу", "запусти", "сформируй задачу"]
        return (
            any(term in msg for term in task_terms)
            and any(term in msg for term in question_terms)
            and not any(term in msg for term in create_terms)
        )

    def _is_stale_task_artifact(self, text_value: str) -> bool:
        """Исторические/сфантазированные task-коды не должны попадать в оперативный контекст."""
        text_value = text_value or ""
        stale_patterns = [
            r"\bBM-20\d{2}-\d{2}-\d{2}",
            r"\bCRM-20\d{2}-\d{2}-\d{2}",
            r"\bAS-20\d{2}-\d{2}-\d{2}",
            r"\bTG-20\d{2}-\d{2}-\d{2}",
            r"\bA-20\d{2}-\d{2}-\d{2}",
        ]
        return any(re.search(pattern, text_value, re.IGNORECASE) for pattern in stale_patterns)

    def _format_current_tasks_response(self, tasks_context: Dict[str, Any]) -> str:
        tasks = tasks_context.get("tasks") or []
        by_status = tasks_context.get("by_status") or {}
        by_agent = tasks_context.get("by_agent") or {}

        lines = [
            "**Актуальные задачи в работе**",
            "",
            "Источник: `director_tasks` и `agent_interaction_tasks` в БД GLAME. Старые коды из документов или памяти не использую.",
            "",
            f"Всего незавершённых задач: **{len(tasks)}**",
        ]
        if by_status:
            lines.append(f"По статусам: {', '.join(f'{status}: {count}' for status, count in by_status.items())}")
        if by_agent:
            lines.append(f"По агентам: {', '.join(f'{agent}: {count}' for agent, count in by_agent.items())}")
        lines.append("")

        if not tasks:
            lines.append("Сейчас активных задач в БД нет.")
            return "\n".join(lines)

        lines.extend([
            "| Задача | Агент | Доска | Приоритет | Статус | Создана |",
            "|---|---|---|---|---|---|",
        ])
        for task in tasks[:30]:
            created_at = task.get("created_at") or "—"
            if created_at and created_at != "—":
                created_at = created_at[:16].replace("T", " ")
            title = str(task.get("title") or "Без названия").replace("|", "/")
            agent = str(task.get("target_agent") or "—").replace("|", "/")
            board = str(task.get("board") or "—").replace("|", "/")
            lines.append(
                f"| {title} | {agent} | {board} | {task.get('priority') or '—'} | {task.get('status') or '—'} | {created_at} |"
            )

        lines.extend([
            "",
            "**Следующий шаг:** откройте нужную карточку на доске агента или во вкладке задач директора для согласования/доработки.",
        ])
        return "\n".join(lines)

    def _format_agent_work_result_response(self, result: Dict[str, Any]) -> str:
        """Форматирует отчет директора строго по результату профильного агента из БД."""
        task = result.get("task") or {}
        segment = result.get("segment") or {}
        dialog = result.get("agent_dialog") or {}
        actions = result.get("next_admin_actions") or []
        task_id = str(task.get("id") or "").strip()
        segment_id = str(segment.get("id") or "").strip()
        segment_name = str(segment.get("name") or "Сегмент AI CRM").strip()
        count = int(segment.get("customer_count") or 0)
        edit_path = str(segment.get("edit_path") or "/admin/customers/segments")
        task_href = str(task.get("href") or (f"/ai-marketer/tasks/{task_id}" if task_id else "")).strip()
        crm_reply = str(dialog.get("crm_reply") or "").strip()

        lines = [
            "**AI CRM подготовил сегмент и сохранил результат в БД.**",
            "",
            f"- Задача: `{task_id}`" if task_id else "- Задача: ID не получен",
            f"- Сегмент: `{segment_id}`" if segment_id else "- Сегмент: ID не получен",
            f"- Название сегмента: {segment_name}",
            f"- Размер сегмента: **{count} покупателей**",
            f"- Карточка задачи: `{task_href}`" if task_href else "- Карточка задачи: ссылка не получена",
            f"- Редактирование сегмента: `{edit_path}`",
            "",
            "Показываю именно сохраненную сегментацию для согласования. Дальше эта же задача развивается в рассылку: согласование фильтра, затем текстов и запуска.",
        ]
        if crm_reply:
            lines.extend(["", "**Короткий отчет AI CRM:**", crm_reply])
        if actions:
            lines.extend(["", "**Что согласовать:**"])
            lines.extend([f"- {item}" for item in actions])
        return "\n".join(lines)

    async def execute_task(
        self,
        user_id: UUID,
        task_title: str,
        task_description: Optional[str] = None,
        task_type: str = "assignment",
        priority: str = "P2",
        source_message_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Создание и выполнение задачи"""
        # 1. Создаём задачу
        task = DirectorTask(
            user_id=user_id,
            title=task_title,
            description=task_description,
            task_type=task_type,
            priority=priority,
            status="in_progress",
            related_message_id=source_message_id,
        )
        self.db.add(task)
        await self.db.flush()

        # 2. Планируем выполнение — разбиваем на подзадачи через LLM
        plan = await self._plan_task(task_title, task_description)

        # 3. Сохраняем план в extra_data
        task.extra_data = {"plan": plan}
        task.execution_notes = json.dumps(plan, ensure_ascii=False)

        # 4. Отмечаем задачу как выполненную (симуляция оркестрации)
        task.status = "completed"
        task.result_summary = f"Задача '{task_title}' запланирована. Определено {len(plan)} подзадач."

        # 5. Сохраняем в среднесрочную память
        memory = DirectorMemory(
            user_id=user_id,
            memory_type="medium_term",
            content=f"Задача: {task_title}\nПлан: {json.dumps(plan, ensure_ascii=False)}",
            content_type="task_plan",
            source_task_id=task.id,
            source_message_id=source_message_id,
            importance=3,
        )
        self.db.add(memory)
        await self.db.commit()

        return {
            "task_id": str(task.id),
            "title": task_title,
            "status": "completed",
            "plan": plan,
            "memory_id": str(memory.id),
        }

    async def search_chat(
        self,
        user_id: UUID,
        query: str,
        limit: int = 20,
        message_type: Optional[str] = None,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Поиск по истории чата"""
        conditions = [
            DirectorChatMessage.user_id == user_id,
            DirectorChatMessage.status.in_(("pending", "processing", "completed")),
        ]

        if message_type:
            conditions.append(DirectorChatMessage.message_type == message_type)
        if category:
            conditions.append(DirectorChatMessage.category == category)

        stmt = select(DirectorChatMessage).where(and_(*conditions))

        # Текстовый поиск
        if query:
            search_pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    DirectorChatMessage.message.ilike(search_pattern),
                    DirectorChatMessage.category.ilike(search_pattern),
                )
            )

        stmt = stmt.order_by(desc(DirectorChatMessage.created_at))

        # Пагинация
        offset = (page - 1) * limit
        stmt = stmt.offset(offset).limit(limit)

        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        # Считаем общее количество
        count_stmt = select(func.count(DirectorChatMessage.id)).where(and_(*conditions))
        if query:
            search_pattern = f"%{query}%"
            count_stmt = count_stmt.where(
                or_(
                    DirectorChatMessage.message.ilike(search_pattern),
                    DirectorChatMessage.category.ilike(search_pattern),
                )
            )
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        return {
            "messages": [m.to_dict() for m in messages],
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit),
        }

    async def add_to_knowledge(
        self,
        user_id: UUID,
        title: str,
        content: str,
        category: str = "fact",
        source: Optional[str] = None,
        source_message_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Добавление знания в базу знаний (долгая память)"""
        # 1. Сохраняем в PostgreSQL
        knowledge = DirectorKnowledge(
            user_id=user_id,
            title=title,
            content=content,
            category=category,
            content_type="text",
            source=source or "chat",
            source_message_id=source_message_id,
            importance=3,
        )
        self.db.add(knowledge)
        await self.db.flush()

        # 2. Векторизуем в Qdrant
        try:
            vector_id = vector_service.add_knowledge(
                collection_name="director_knowledge",
                text=f"{title}\n\n{content}",
                category=category,
                source=source or "chat",
                metadata={
                    "knowledge_id": str(knowledge.id),
                    "user_id": str(user_id),
                    "title": title,
                    "category": category,
                },
            )
            knowledge.vector_id = vector_id
        except Exception as e:
            logger.warning(f"Failed to vectorize knowledge: {e}")

        await self.db.commit()

        return {"knowledge_id": str(knowledge.id), "vector_id": knowledge.vector_id}

    async def search_knowledge(
        self,
        query: str,
        user_id: Optional[UUID] = None,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Поиск по базе знаний (векторный + текстовый)"""
        results = []

        # 1. Векторный поиск в Qdrant
        try:
            collection_name = "director_knowledge"
            vector_service.ensure_collection(collection_name)
            vector_results = vector_service.get_context(
                collection_name, query, limit=limit * 2, score_threshold=0.3
            )
            for vr in vector_results:
                payload = vr.get("payload", {})
                results.append({
                    "id": payload.get("knowledge_id"),
                    "title": payload.get("title"),
                    "content": payload.get("text", ""),
                    "category": payload.get("category"),
                    "source": payload.get("source"),
                    "score": vr.get("score", 0),
                    "search_type": "vector",
                })
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")

        # 2. Текстовый поиск в PostgreSQL (дополнение)
        conditions = [DirectorKnowledge.status == "active"]
        if category:
            conditions.append(DirectorKnowledge.category == category)

        search_pattern = f"%{query}%"
        db_results = await self.db.execute(
            select(DirectorKnowledge)
            .where(
                and_(
                    *conditions,
                    or_(
                        DirectorKnowledge.title.ilike(search_pattern),
                        DirectorKnowledge.content.ilike(search_pattern),
                    ),
                )
            )
            .order_by(desc(DirectorKnowledge.importance), desc(DirectorKnowledge.updated_at))
            .limit(limit)
        )
        for doc in db_results.scalars().all():
            results.append({
                "id": str(doc.id),
                "title": doc.title,
                "content": doc.content,
                "category": doc.category,
                "source": doc.source,
                "score": 0.5,
                "search_type": "text",
            })

        # Дедупликация и сортировка по score
        seen = set()
        unique_results = []
        for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
            rid = r.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                unique_results.append(r)

        return unique_results[:limit]

    async def get_memory_context(
        self,
        user_id: UUID,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Получение контекста памяти директора"""
        result = {
            "short_term": [],
            "medium_term": [],
            "long_term": [],
        }

        if not memory_type or memory_type == "short_term":
            short = await self._get_recent_chat_messages(user_id, limit=limit)
            result["short_term"] = short

        if not memory_type or memory_type == "medium_term":
            medium = await self._get_medium_term_memory(user_id, limit=limit)
            result["medium_term"] = medium

        if not memory_type or memory_type == "long_term":
            long = await self._get_long_term_memory(user_id, limit=limit)
            result["long_term"] = long

        return result

    async def _get_or_create_context(
        self, user_id: UUID, session_id: Optional[str] = None
    ) -> Optional[DirectorConversationContext]:
        """Получение или создание контекста сессии"""
        if session_id:
            result = await self.db.execute(
                select(DirectorConversationContext).where(
                    and_(
                        DirectorConversationContext.user_id == user_id,
                        DirectorConversationContext.session_id == session_id,
                        DirectorConversationContext.status == "active",
                    )
                )
            )
            context = result.scalar_one_or_none()
            if context:
                return context

        context = DirectorConversationContext(
            user_id=user_id,
            session_id=session_id or str(uuid4()),
            status="active",
        )
        self.db.add(context)
        await self.db.flush()
        return context

    async def _get_recent_chat_messages(
        self, user_id: UUID, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Получение последних сообщений чата (кратковременная память)"""
        result = await self.db.execute(
            select(DirectorChatMessage)
            .where(
                and_(
                    DirectorChatMessage.user_id == user_id,
                    DirectorChatMessage.status.in_(("pending", "processing", "completed")),
                )
            )
            .order_by(desc(DirectorChatMessage.created_at))
            .limit(limit)
        )
        return [m.to_dict() for m in result.scalars().all()]

    async def _get_medium_term_memory(
        self, user_id: UUID, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Получение среднесрочной памяти (ключевые факты из диалогов)"""
        result = await self.db.execute(
            select(DirectorMemory)
            .where(
                and_(
                    DirectorMemory.user_id == user_id,
                    DirectorMemory.memory_type == "medium_term",
                    DirectorMemory.status == "active",
                )
            )
            .order_by(desc(DirectorMemory.importance), desc(DirectorMemory.created_at))
            .limit(limit)
        )
        return [m.to_dict() for m in result.scalars().all()]

    async def _get_long_term_memory(
        self, user_id: UUID, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Получение долгой памяти (база знаний)"""
        result = await self.db.execute(
            select(DirectorKnowledge)
            .where(
                and_(
                    DirectorKnowledge.user_id == user_id,
                    DirectorKnowledge.status == "active",
                )
            )
            .order_by(desc(DirectorKnowledge.importance), desc(DirectorKnowledge.updated_at))
            .limit(limit)
        )
        return [k.to_dict() for k in result.scalars().all()]

    async def _search_knowledge(
        self, query: str, user_id: UUID
    ) -> List[Dict[str, Any]]:
        """Поиск релевантных знаний для контекста ответа"""
        return await self.search_knowledge(query, user_id, limit=3)

    async def _analyze_and_store_memory(
        self,
        user_id: UUID,
        user_message: str,
        director_response: str,
        source_message_id: UUID,
    ):
        """Анализ диалога и сохранение важных моментов в среднесрочную память"""
        # Определяем важность на основе сообщения
        importance = self._calculate_importance(user_message, director_response)

        if importance >= 3:
            # Извлекаем ключевой факт через LLM
            fact_prompt = (
                f"Из диалога ниже извлеки ключевой факт или договорённость, "
                f"которые стоит запомнить (1-2 предложения):\n\n"
                f"Пользователь: {user_message}\n"
                f"Директор: {director_response}"
            )
            try:
                fact = await self.generate_response(
                    prompt=fact_prompt,
                    system_prompt="Ты — ассистент, извлекающий ключевые факты для памяти AI-директора.",
                    temperature=0.3,
                    max_tokens=200,
                )
                if not fact or not fact.strip():
                    return
                memory = DirectorMemory(
                    user_id=user_id,
                    memory_type="medium_term",
                    content=fact.strip(),
                    content_type="fact",
                    source_message_id=source_message_id,
                    importance=importance,
                )
                self.db.add(memory)
            except Exception as e:
                logger.warning(f"Failed to extract memory fact: {e}")

    async def _analyze_and_vectorize_knowledge(
        self,
        user_id: UUID,
        user_message: str,
        director_response: str,
        source_message_id: UUID,
    ):
        """Анализ и векторизация важных моментов в базу знаний (долгая память)"""
        importance = self._calculate_importance(user_message, director_response)

        if importance >= 4:
            # Формируем знание для сохранения
            knowledge_text = f"Диалог:\nПользователь: {user_message}\nДиректор: {director_response}"
            title = user_message[:100] if len(user_message) > 100 else user_message

            try:
                await self.add_to_knowledge(
                    user_id=user_id,
                    title=title,
                    content=knowledge_text,
                    category="insight",
                    source="chat",
                    source_message_id=source_message_id,
                )
            except Exception as e:
                logger.warning(f"Failed to vectorize knowledge: {e}")

    async def _plan_task(
        self, title: str, description: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Планирование задачи — разбивка на подзадачи через LLM"""
        prompt = (
            f"Разбери следующую задачу на подзадачи:\n\n"
            f"Заголовок: {title}\n"
            f"Описание: {description or 'не указано'}\n\n"
            f"Для каждой подзадачи определи:\n"
            f"1. Какой агент нужен из канонического списка: personal-media-agent, "
            f"brand-media-agent, crm-agent, pr-partnerships-agent, traffic-growth-agent, "
            f"analytics-agent, assortment-agent. Старые content-agent, communication-agent "
            f"и marketing-inventory-agent использовать только как технические алиасы.\n"
            f"2. Чёткое описание задачи для агента\n"
            f"3. Приоритет (high/medium/low)\n\n"
            f"Верни JSON массив: [{{\"agent\": \"...\", \"task\": \"...\", \"priority\": \"...\"}}]"
        )
        try:
            result = await self.generate_structured(
                prompt=prompt,
                system_prompt="Ты — планировщик задач для AI-директора.",
                temperature=0.3,
                max_tokens=2000,
            )
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "plan" in result:
                return result["plan"]
            if isinstance(result, dict):
                possible_keys = ["tasks", "subtasks", "items", "steps"]
                for key in possible_keys:
                    if key in result and isinstance(result[key], list):
                        return result[key]
                for v in result.values():
                    if isinstance(v, list):
                        return v
            return [{"agent": "unknown", "task": title, "priority": "medium"}]
        except Exception as e:
            logger.warning(f"Task planning failed: {e}")
            return [{"agent": "unknown", "task": title, "priority": "medium"}]

    def _build_chat_prompt(
        self,
        message: str,
        context: Optional[DirectorConversationContext],
        medium_term: List[Dict[str, Any]],
        knowledge_context: List[Dict[str, Any]],
        data_context: Optional[Dict[str, Any]] = None,
        request_workflow: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Формирование промпта для чата с контекстом и данными"""
        parts = [f"Сообщение пользователя: {message}\n"]
        parts.append(
            "Операционный контекст платформы: директор подключен к данным GLAME в БД: "
            "CRM/покупатели/loyalty, заказы и чеки, продажи из 1С, остатки по складам, "
            "товары, посещения магазинов, маркетинговые кампании и задачи агентов. "
            "Не отвечай, что у тебя нет доступа к этим данным; при необходимости используй DATA_TOOLS_BLOCK ниже.\n"
        )
        parts.append(
            "Жёсткое правило релевантности ответа: отвечай только на то, что спросил пользователь. "
            "Не добавляй в конец ответа продажи, выручку, магазины, сравнение магазинов, графики, "
            "посещения или другую аналитику, если пользователь прямо не попросил эти данные. "
            "Если пользователь упоминает магазин как место запуска кампании или рассылки, это параметр задачи, "
            "а не запрос на отчёт по магазинам. Если данные используются как внутренний контекст для планирования, "
            "не выводи их отдельным блоком.\n"
        )

        if request_workflow:
            parts.append("\n[Рабочий цикл обработки запроса директором]")
            parts.append(f"Интент: {request_workflow.get('intent')}")
            steps = request_workflow.get("steps") or []
            if steps:
                parts.append("Шаги:")
                for index, step in enumerate(steps, start=1):
                    parts.append(f"{index}. {step}")
            data_requests = request_workflow.get("data_requests") or []
            if data_requests:
                parts.append("Запрошенные источники данных:")
                for item in data_requests:
                    parts.append(f"- {item.get('label')} ({item.get('key')}): {item.get('reason')}")
            agent_requests = request_workflow.get("agent_requests") or []
            if agent_requests:
                parts.append("Профильные агенты, которых нужно подключить через задачи/чат:")
                for item in agent_requests:
                    parts.append(
                        f"- {item.get('label')} ({item.get('agent')}): запрос — {item.get('request')}; "
                        f"ожидаемый результат — {item.get('expected')}"
                    )
            parts.append(
                "Правило ответа: сначала опирайся на уже полученные DATA_TOOLS_BLOCK данные. "
                "Если в DATA_TOOLS_BLOCK есть agent_work_results, профильный агент уже отработал подзадачу: "
                "покажи готовый результат, ссылку/ID задачи, segment_id и точный размер сегмента из БД. "
                "Не пересчитывай и не заменяй эти цифры предположениями. В этом случае не проси пользователя "
                "вручную запускать агента. Если результата профильного агента ещё нет, не изображай его "
                "выполненным; предложи интерактивное действие/кнопку для постановки конкретной задачи агенту."
            )
            parts.append("")

        if context and context.current_topic:
            parts.append(f"Текущая тема: {context.current_topic}\n")
            parts.append(f"Фаза: {context.current_phase or 'диалог'}\n")

        if medium_term:
            parts.append("\nКлючевые факты из прошлых диалогов (среднесрочная память):")
            for m in medium_term:
                parts.append(f"- {m.get('content', '')} (важность: {m.get('importance', 1)})")
            parts.append("")

        if knowledge_context:
            parts.append("\nРелевантные знания из базы знаний:")
            parts.append(
                "Важно: база знаний может содержать старые примеры, планы и исторические документы. "
                "Не выдавай задачи из базы знаний как актуальные. Актуальные задачи бери только из блока [Актуальные задачи из БД], если он есть."
            )
            for k in knowledge_context:
                parts.append(f"- [{k.get('category', 'общее')}] {k.get('title', '')}: {k.get('content', '')[:200]}")
            parts.append("")

        if data_context:
            parts.append("\n*** DATA_TOOLS_BLOCK: ЖИВЫЕ ДАННЫЕ ИЗ БД ***")
            for key, value in data_context.items():
                if key == "agent_registry":
                    lines = [
                        "[Канонический состав AI-агентов GLAME по ТЗ v1_2]",
                        "Используй этот список как единственный актуальный список агентов для пользователя. Старые agent_type можно упоминать только как технические aliases.",
                    ]
                    for agent in value:
                        lines.append(
                            f"  - {agent.get('name')} ({agent.get('id')}): {agent.get('role')} "
                            f"Доска: {agent.get('board')}. "
                            f"Получает: {', '.join(agent.get('receives', [])[:4])}. "
                            f"Отдает: {', '.join(agent.get('outputs', [])[:5])}. "
                            f"Инструменты: {', '.join(agent.get('tools', [])[:5])}. "
                            f"Алиасы: {', '.join(agent.get('aliases', []))}."
                        )
                    parts.append("\n".join(lines))
                elif key == "current_tasks":
                    tasks = value.get("tasks", []) if isinstance(value, dict) else []
                    lines = [
                        "[Актуальные задачи из БД]",
                        f"Источник истины: {', '.join(value.get('source_of_truth', [])) if isinstance(value, dict) else 'director_tasks, agent_interaction_tasks'}",
                        f"Всего активных/незавершенных задач: {value.get('total', len(tasks)) if isinstance(value, dict) else len(tasks)}",
                        f"По статусам: {value.get('by_status', {}) if isinstance(value, dict) else {}}",
                        f"По агентам: {value.get('by_agent', {}) if isinstance(value, dict) else {}}",
                        "Правило: отвечая на вопрос о текущих задачах, используй только строки ниже. "
                        "Не придумывай task code вроде BM-2025/CRM-2025, если такого id/title нет в БД.",
                    ]
                    if tasks:
                        for task in tasks[:50]:
                            lines.append(
                                f"  - ID {task.get('id')}: {task.get('title')} | "
                                f"агент {task.get('target_agent') or 'не указан'} | "
                                f"доска {task.get('board') or 'не указана'} | "
                                f"статус {task.get('status')} | "
                                f"приоритет {task.get('priority')} | "
                                f"тип {task.get('task_type')} | "
                                f"создана {task.get('created_at') or 'нет даты'} | "
                                f"дедлайн {task.get('deadline_at') or 'нет дедлайна'} | "
                                f"ссылка {task.get('href') or 'нет'}"
                            )
                            if task.get("description"):
                                lines.append(f"    описание: {str(task.get('description'))[:240]}")
                    else:
                        lines.append("  - Активных задач в БД сейчас нет.")
                    parts.append("\n".join(lines))
                elif key == "agent_work_results":
                    segment = value.get("segment", {}) if isinstance(value, dict) else {}
                    task = value.get("task", {}) if isinstance(value, dict) else {}
                    lines = [
                        "[Результат профильного агента из БД]",
                        f"Статус: {value.get('status') if isinstance(value, dict) else 'unknown'}",
                        f"Задача ID: {task.get('id') or 'нет'}",
                        f"Задача ссылка: {task.get('href') or 'нет'}",
                        f"Сегмент ID: {segment.get('id') or 'нет'}",
                        f"Сегмент название: {segment.get('name') or 'нет'}",
                        f"Сегмент размер: {segment.get('customer_count') if segment.get('customer_count') is not None else 'нет'}",
                        f"Редактирование сегмента: {segment.get('edit_path') or '/admin/customers/segments'}",
                        "Правило: в отчете директора используй именно эти ID и этот размер сегмента. Не заменяй их другими цифрами.",
                    ]
                    parts.append("\n".join(lines))
                elif key == "admin_cron_result":
                    if isinstance(value, dict):
                        parts.append(
                            "[Действие директора с CRON]\n"
                            f"Статус: {value.get('status')}\n"
                            f"Действие: {value.get('action')}\n"
                            f"Сообщение: {value.get('message')}\n"
                            f"Регламент: {(value.get('job') or {}).get('title') or value.get('job_id') or 'не указан'}\n"
                            f"Созданная задача: {(value.get('run') or {}).get('task_id') or 'нет'}"
                        )
                elif key == "admin_cron":
                    jobs = value.get("jobs", []) if isinstance(value, dict) else []
                    runs = value.get("runs", []) if isinstance(value, dict) else []
                    lines = [
                        "[CRON регламенты]",
                        f"Всего: {value.get('total', len(jobs)) if isinstance(value, dict) else len(jobs)}",
                        f"Включено: {value.get('enabled_count', 0) if isinstance(value, dict) else 0}",
                        "Правило: директор может советовать, создавать и редактировать регламенты. Запуск CRON создает задачу агенту, но не отправляет рассылки без согласования администратора.",
                    ]
                    for job in jobs[:30]:
                        lines.append(
                            f"  - {job.get('id')}: {job.get('title')} | статус {'включен' if job.get('enabled') else 'выключен'} | "
                            f"агент {job.get('target_agent')} | тип {job.get('task_type')} | расписание {job.get('schedule_type')} {job.get('time_of_day') or ''} | "
                            f"следующий {job.get('next_run_at') or 'нет'} | последний {job.get('last_run_at') or 'нет'}"
                        )
                        if job.get("description"):
                            lines.append(f"    описание: {str(job.get('description'))[:220]}")
                    if runs:
                        lines.append("[Последние CRON запуски]")
                        for run in runs[:10]:
                            lines.append(
                                f"  - {run.get('job_title') or run.get('job_id')} | {run.get('status')} | "
                                f"{'ручной' if run.get('manual') else 'авто'} | задача {run.get('task_id') or 'нет'} | {run.get('started_at')}"
                            )
                    parts.append("\n".join(lines))
                elif key == "sales_today":
                    parts.append(
                        f"[Продажи сегодня] Чеков: {value.get('checks_count', value.get('orders_count', 0))}, "
                        f"Выручка: {value.get('total_revenue_rub', 0)} ₽, "
                        f"Товаров продано: {value.get('items_sold', 0)}, "
                        f"последняя продажа: {value.get('last_sale_at') or 'нет данных'}, "
                        f"источник: {value.get('source') or 'unknown'}"
                    )
                elif key == "sales_week":
                    parts.append(
                        f"[Продажи за 7 дней] Чеков: {value.get('checks_count', value.get('orders_count', 0))}, "
                        f"Выручка: {value.get('total_revenue_rub', 0)} ₽, "
                        f"Средний чек: {value.get('average_check_rub', 0)} ₽, "
                        f"Уникальных покупателей: {value.get('unique_customers', 0)}, "
                        f"последняя продажа: {value.get('last_sale_at') or 'нет данных'}, "
                        f"источник: {value.get('source') or 'unknown'}"
                    )
                elif key == "sales_month":
                    parts.append(
                        f"[Продажи за 30 дней] Чеков: {value.get('checks_count', value.get('orders_count', 0))}, "
                        f"Выручка: {value.get('total_revenue_rub', 0)} ₽, "
                        f"Средний чек: {value.get('average_check_rub', 0)} ₽, "
                        f"последняя продажа: {value.get('last_sale_at') or 'нет данных'}, "
                        f"источник: {value.get('source') or 'unknown'}"
                    )
                elif key == "customer_summary":
                    parts.append(
                        f"[Покупатели] Всего: {value.get('total_customers', 0)}, "
                        f"По сегментам: {value.get('by_segment', {})}, "
                        f"Новых за 30 дней: {value.get('new_last_30_days', 0)}, "
                        f"Баллов лояльности: {value.get('total_loyalty_points', 0)}"
                    )
                elif key == "product_summary":
                    parts.append(
                        f"[Товары] Активных: {value.get('total_active_products', 0)}, "
                        f"Core assortment: {value.get('core_assortment', 0)}, "
                        f"Категории: {value.get('by_category', {})}, "
                        f"Бренды: {value.get('by_brand', {})}"
                    )
                elif key == "inventory":
                    parts.append(
                        f"[Остатки 1С] Записей остатков: {value.get('stock_records', 0)}, "
                        f"Доступно единиц: {value.get('available_quantity', 0)}, "
                        f"Критических SKU: {value.get('critical_count', 0)}, "
                        f"Low stock SKU: {value.get('low_count', 0)}, "
                        f"Последняя синхронизация: {value.get('last_synced_at') or 'нет данных'}"
                    )
                    critical_products = value.get("critical_products") or []
                    if critical_products:
                        lines = ["[Критические остатки]"]
                        for p in critical_products[:5]:
                            lines.append(
                                f"  - {p.get('name')} ({p.get('article') or 'без артикула'}), "
                                f"{p.get('store_name')}: {p.get('available_quantity', 0)}"
                            )
                        parts.append("\n".join(lines))
                elif key == "store_visits":
                    parts.append(
                        f"[Посещения магазинов] Период: {value.get('period')}, "
                        f"посетителей: {value.get('visitors', 0)}, "
                        f"последняя дата посещений: {value.get('last_visit_date') or 'нет данных'}. "
                        "Важно: это отдельный источник посещаемости; поле sales_count в store_visits "
                        "не является источником продаж и не должно использоваться как вывод о продажах."
                    )
                    by_store = value.get("by_store") or []
                    if by_store:
                        lines = [
                            "[Точные посещения по магазинам] Используй эти значения, не оценивай и не распределяй общий трафик. Продажи бери из блока [Магазины] или [Чеки / sales_metrics]:"
                        ]
                        for row in by_store[:20]:
                            lines.append(
                                f"  - {row.get('store_name') or row.get('store_id')}: "
                                f"посетителей {row.get('visitors', 0)}"
                            )
                        parts.append("\n".join(lines))
                    else:
                        parts.append(
                            "[Посещения по магазинам] Точной разбивки by_store за этот период нет. "
                            "Не делай оценок по магазинам; сообщи пользователю, что нужны данные счетчиков в разрезе магазинов."
                        )
                elif key == "sales_metrics":
                    parts.append(
                        f"[Чеки / sales_metrics] Период: {value.get('period')}, "
                        f"чеков: {value.get('checks_count', 0)}, "
                        f"выручка: {value.get('revenue_rub', 0)} ₽, "
                        f"средний чек: {value.get('average_check_rub', 0)} ₽, "
                        f"товаров: {value.get('items_sold', 0)}, "
                        f"последняя дата: {value.get('last_metric_date') or 'нет данных'}, "
                        f"источник: {value.get('source') or 'unknown'}"
                    )
                    source_status = value.get("source_status") or {}
                    if source_status:
                        parts.append(
                            "[Статус источников продаж] "
                            f"primary={source_status.get('primary_sales_source')}; "
                            f"sales_records={source_status.get('sales_records')}; "
                            f"sales_metrics={source_status.get('sales_metrics')}; "
                            f"orders={source_status.get('orders')}; "
                            f"store_visits={source_status.get('store_visits')}"
                        )
                elif key == "top_products":
                    top = value.get("products", value) if isinstance(value, dict) else value
                    if isinstance(top, list) and top:
                        lines = ["[Топ товаров]"]
                        for i, p in enumerate(top[:5], 1):
                            name = p.get("product_name") or p.get("name", "")
                            sold = p.get("total_sold", p.get("total_quantity", 0))
                            rev = p.get("total_revenue_rub", 0)
                            lines.append(f"  {i}. {name} — продано {sold}, выручка {rev} ₽")
                        parts.append("\n".join(lines))
                elif key == "stores":
                    stores = value if isinstance(value, list) else value.get("stores", [])
                    if stores:
                        lines = ["[Магазины]"]
                        for s in stores:
                            lines.append(
                                f"  - {s.get('name')} ({s.get('city') or 'город не указан'}): "
                                f"выручка {s.get('total_revenue_rub', 0)} ₽, "
                                f"чеков {s.get('checks_count', s.get('total_orders', 0))}, "
                                f"средний чек {s.get('average_check_rub', 0)} ₽, "
                                f"посетителей {s.get('visitors', 0)}, "
                                f"выручка на посетителя {s.get('revenue_per_visitor_rub', 0)} ₽, "
                                f"последняя дата посещений {s.get('last_visit_date') or 'нет данных'}, "
                                f"последняя продажа {s.get('last_sale_at') or 'нет данных'}, "
                                f"источник {s.get('source') or 'unknown'}"
                            )
                        parts.append("\n".join(lines))
                elif key == "campaigns":
                    campaigns = value if isinstance(value, list) else value.get("campaigns", [])
                    if campaigns:
                        lines = ["[Активные кампании]"]
                        for c in campaigns:
                            lines.append(f"  - {c.get('name')} ({c.get('type')}): бюджет {c.get('budget_rub', 0)} ₽")
                        parts.append("\n".join(lines))
                elif key == "recent_orders":
                    orders = value if isinstance(value, list) else value.get("orders", [])
                    if orders:
                        lines = ["[Последние заказы]"]
                        for o in orders:
                            lines.append(
                                f"  - {o.get('order_id', '')[:8]}: {o.get('status')}, "
                                f"{o.get('total_amount_rub', 0)} ₽, {o.get('customer_name') or o.get('customer_email', '')}"
                            )
                        parts.append("\n".join(lines))
                elif key == "general_stats":
                    parts.append(f"[Общая сводка] Данные загружены: см. секции выше")
                    if isinstance(value, dict):
                        parts.append(json.dumps(value, ensure_ascii=False, indent=2)[:2000])
            parts.append("*** КОНЕЦ DATA_TOOLS_BLOCK ***\n")

        return "\n".join(parts)

    def _detect_message_type(self, message: str) -> str:
        """Определение типа сообщения"""
        msg_lower = message.lower()

        # Задача/поручение
        task_keywords = [
            "сделай", "выполни", "задача", "поручение", "нужно сделать",
            "подготовь", "создай", "напиши", "проанализируй",
        ]
        if any(kw in msg_lower for kw in task_keywords):
            return "task"

        # Запрос отчёта
        report_keywords = [
            "отчёт", "отчет", "результат", "статистика", "покажи",
            "сколько", "какие", "что сделано",
        ]
        if any(kw in msg_lower for kw in report_keywords):
            return "report"

        # Согласование
        approval_keywords = [
            "согласуй", "утверди", "подтверди", "одобри",
            "согласование", "утверждение", "как думаешь",
        ]
        if any(kw in msg_lower for kw in approval_keywords):
            return "approval"

        # Работа с базой знаний
        knowledge_keywords = [
            "запомни", "сохрани в базу", "добавь знание",
            "база знаний", "knowledge",
        ]
        if any(kw in msg_lower for kw in knowledge_keywords):
            return "knowledge"

        return "text"

    def _calculate_importance(self, user_message: str, director_response: str) -> int:
        """Расчёт важности диалога (1-5)"""
        score = 1
        msg_lower = (user_message + " " + director_response).lower()

        high_importance = [
            "стратегия", "стратегический", "бюджет", "план", "решение",
            "важно", "критично", "срочно", "приоритет",
        ]
        medium_importance = [
            "задача", "отчёт", "отчет", "анализ", "рекомендация",
            "клиент", "кампания", "продажи", "ассортимент",
        ]

        for kw in high_importance:
            if kw in msg_lower:
                score = max(score, 4)

        for kw in medium_importance:
            if kw in msg_lower:
                score = max(score, 3)

        # Диалоги с планами
        if "план" in msg_lower and any(w in msg_lower for w in ["сделать", "нужно", "будем"]):
            score = max(score, 4)

        return score

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Any:
        """Генерация структурированного ответа (JSON)"""
        try:
            response = await self.llm.generate_structured(
                prompt=prompt,
                response_format={"type": "json_object"},
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response
        except Exception as e:
            logger.warning(f"Structured generation failed, trying plain: {e}")
            text = await self.generate_response(
                prompt=prompt + "\n\nОтветь ТОЛЬКО JSON.",
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"error": str(e), "raw": text[:500]}

    async def create_task_from_message(
        self,
        user_id: UUID,
        message_id: UUID,
        title: str,
        description: Optional[str] = None,
        priority: str = "P2",
    ) -> Dict[str, Any]:
        """Создание задачи из сообщения чата"""
        return await self.execute_task(
            user_id=user_id,
            task_title=title,
            task_description=description,
            task_type="assignment",
            priority=priority,
            source_message_id=message_id,
        )
