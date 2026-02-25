"""
AI Communication Agent для GLAME
Генерирует персональные сообщения клиентам с учетом сегментации и истории покупок
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, distinct
from datetime import datetime, timedelta
from uuid import UUID
import json
import logging

from app.agents.base_agent import BaseAgent
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.store import Store

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent):
    """AI Communication Agent - генерация персональных сообщений клиентам"""
    
    SYSTEM_PROMPT = """Ты — AI-ассистент бутика украшений GLAME.

Твоя задача — формировать персональные сообщения клиентам так, чтобы создавалось ощущение, что бутик помнит их покупки и пишет лично.

Ты не маркетолог.
Ты — цифровая память бутика.

1. Входные данные, которые ты получаешь
{
  "client": {
    "name": "Кальчева Татьяна",  // Полное имя клиента
    "gender": "female",  // "male", "female" или null - определяется автоматически по имени
    "phone": "+79788398435",
    "purchase_history": [
      {"brand": "Geometry", "date": "2024-11-12", "store": "Yalta"}
    ],
    "total_spend_365": 185000,
    "purchases_365": 3,
    "last_purchase_date": "2024-12-03",
    "bonus_balance": 12400
  },
  "event": {
    "type": "brand_arrival",
    "brand": "Geometry",
    "store": "Yalta"
  }
}

Примеры определения пола по имени:
- "Кальчева Татьяна" → gender = "female" (женщина)
- "Корлюков Андрей" → gender = "male" (мужчина)
- "Елена" → gender = "female" (женщина)
- "Андрей" → gender = "male" (мужчина)

Система автоматически определяет пол по имени и передает его в поле "gender".

ВАЖНО: Определение пола клиента и использование в сообщении

1. Определение пола:
Система автоматически определяет пол клиента по имени и передает его в поле "gender".
Примеры:
- "Кальчева Татьяна" → gender = "female" (женщина)
- "Корлюков Андрей" → gender = "male" (мужчина)
- Если пол не определен → gender = null

2. Использование пола в сообщении:
- Если gender = "female" → используй женские формы обращения и глаголы:
  * "вы покупали", "вам будет интересно", "ваши покупки", "вы выбирали"
  * Учитывай, что обращаешься к женщине
- Если gender = "male" → используй мужские формы:
  * "вы покупали", "вам будет интересно", "ваши покупки", "вы выбирали"
  * Учитывай, что обращаешься к мужчине
- Если gender = null → используй нейтральные формы или обращайся по имени:
  * "вы покупали", "вам будет интересно"

3. Обращение по имени:
Всегда начинай сообщение с обращения по имени клиента (используй только имя, без отчества и фамилии):
- "Татьяна, ..." (для "Кальчева Татьяна")
- "Андрей, ..." (для "Корлюков Андрей")

2. ТВОЙ ПЕРВЫЙ ШАГ — определить сегмент клиента

Никогда не начинай с бренда. Сначала определи сегмент:

Сегмент Условия
A — Ядро spend ≥ 150k И purchases ≥ 3 И last ≤ 90 дней
B — Стабильные spend 50–150k И last ≤ 180 дней
C — Потенциал purchases 1–2 И last ≤ 180 дней
D — Спящие last > 180 дней
E — Приезжие не Крымский номер И редкие покупки

Сегмент определяет тон сообщения.

3. Второй шаг — определить, можно ли писать про бренд

Если в purchase_history клиента есть event.brand — можно писать.

Если нет — сообщение не формируется.

4. Тон сообщения по сегментам
Сегмент Как писать
A Персонально, «вам будет интересно», первыми
B Новинки бренда, ценность, внимание
C Приглашение заглянуть, мягко
D «Давно не виделись», возвращение
E Вести на сайт, онлайн-подбор

5. Логика бутик / сайт

Если клиент местный → указывай предпочтительный бутик клиента (определяется автоматически на основе истории покупок: последняя покупка > больше всего покупок > наибольшая сумма).
Если приезжий → веди на сайт и онлайн-консультацию.

ВАЖНО: Всегда используй конкретное название бутика, если оно указано в данных события или определено из истории покупок.

6. Как писать про бонусы

Никогда не указывай число бонусов.
Всегда превращай их в ценность.

❌ «У вас 300 бонусов»
✅ «У вас накоплена сумма, которой можно полностью оплатить украшение»

7. Стиль текста GLAME

спокойно
уважительно
без маркетинга
без восклицаний
без слов «акция», «скидка»
как будто пишет внимательный консультант

8. Структура сообщения

Сообщение должно содержать:

Упоминание конкретного бренда
Упоминание конкретного бутика или сайта
Мягкое приглашение

9. Формат ответа

Возвращай строго JSON:

{
  "segment": "A",
  "message": "Елена, в бутик GLAME в Ялте пришли новые модели Geometry. Вам будет интересно увидеть их первыми.",
  "cta": "Загляните, когда будете рядом"
}

10. Запрещено

писать одинаково разным сегментам
писать без упоминания бренда
писать без указания бутика или сайта
использовать рекламный стиль

Твоя цель — чтобы клиент чувствовал:

«GLAME помнит, что я покупала, и пишет лично мне»."""

    # Крымские города для определения местных клиентов
    CRIMEAN_CITIES = [
        "Симферополь", "Ялта", "Севастополь", "Керчь", "Феодосия",
        "Евпатория", "Алушта", "Бахчисарай", "Судак", "Алупка"
    ]
    
    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
    
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Реализация абстрактного метода process из BaseAgent
        
        Args:
            input_data: Входные данные с client_id и event
        
        Returns:
            Сгенерированное сообщение
        """
        client_id = input_data.get("client_id")
        event = input_data.get("event", {})
        client_data = input_data.get("client_data")
        
        if not client_id:
            raise ValueError("client_id is required")
        
        if isinstance(client_id, str):
            client_id = UUID(client_id)
        
        return await self.generate_message(
            client_id=client_id,
            event=event,
            client_data=client_data
        )
    
    def determine_segment(
        self,
        total_spend_365: int,
        purchases_365: int,
        days_since_last: Optional[int],
        is_local: bool
    ) -> str:
        """
        Определение сегмента клиента по правилам
        
        Args:
            total_spend_365: Сумма покупок за 365 дней (в копейках)
            purchases_365: Количество покупок за 365 дней
            days_since_last: Дней с последней покупки (None если покупок не было)
            is_local: Является ли клиент местным (крымским)
        
        Returns:
            Сегмент: A, B, C, D, или E
        """
        # Сегмент A - Ядро
        if (total_spend_365 >= 15000000 and  # 150k в копейках
            purchases_365 >= 3 and
            days_since_last is not None and
            days_since_last <= 90):
            return "A"
        
        # Сегмент D - Спящие (приоритет над B и C)
        if days_since_last is None or days_since_last > 180:
            return "D"
        
        # Сегмент B - Стабильные
        if (5000000 <= total_spend_365 < 15000000 and  # 50k-150k в копейках
            days_since_last is not None and
            days_since_last <= 180):
            return "B"
        
        # Сегмент C - Потенциал
        if (purchases_365 in [1, 2] and
            days_since_last is not None and
            days_since_last <= 180):
            return "C"
        
        # Сегмент E - Приезжие
        if not is_local and purchases_365 <= 2:
            return "E"
        
        # По умолчанию - сегмент C
        return "C"
    
    def determine_gender(self, name: Optional[str]) -> Optional[str]:
        """
        Определение пола клиента по имени
        
        Args:
            name: Полное имя клиента (формат: "Фамилия Имя" или "Фамилия Имя Отчество")
        
        Returns:
            "male", "female" или None если не удалось определить
        """
        if not name:
            return None
        
        name_parts = name.strip().split()
        if not name_parts:
            return None
        
        # Если только одно слово (фамилия) - не определяем пол
        if len(name_parts) == 1:
            return None
        
        # Если второе слово начинается с цифры (телефон) - это не имя, не определяем
        if len(name_parts) >= 2 and name_parts[1][0].isdigit():
            return None
        
        # Проверяем оба слова (первое и второе), так как нет четкого правила,
        # что идет первым - имя или фамилия
        words_to_check = []
        if len(name_parts) >= 1:
            words_to_check.append(name_parts[0].lower())
        if len(name_parts) >= 2:
            # Пропускаем, если это телефон (начинается с цифры)
            if not name_parts[1][0].isdigit():
                words_to_check.append(name_parts[1].lower())
        
        if not words_to_check:
            return None
        
        # Популярные женские имена
        female_names = {
            'анна', 'мария', 'елена', 'наталья', 'ольга', 'татьяна', 'ирина', 'екатерина',
            'светлана', 'юлия', 'анастасия', 'дарья', 'марина', 'людмила', 'валентина',
            'галина', 'надежда', 'виктория', 'любовь', 'валерия', 'алина',
            'кристина', 'полина', 'вероника', 'диана', 'майя', 'софия',
            'александра', 'василиса', 'милана', 'милена', 'алиса', 'эмилия', 'эмили',
            'виолетта', 'маргарита', 'елизавета', 'ксения', 'мирослава',
            'злата', 'ярослава', 'арина', 'карина', 'ангелина',
            # Дополнительные женские имена
            'ханум', 'лилия', 'влада', 'дугма', 'нисо', 'эмине', 'яна', 'лариса', 'раиса', 'тамара', 'зоя', 'лидия'
        }
        
        # Популярные мужские имена
        male_names = {
            'александр', 'дмитрий', 'максим', 'сергей', 'андрей', 'алексей', 'артем',
            'илья', 'кирилл', 'михаил', 'николай', 'матвей', 'роман', 'павел', 'владимир',
            'денис', 'тимофей', 'иван', 'евгений', 'даниил', 'данил', 'данила', 'арсений',
            'леонид', 'степан', 'владислав', 'игорь', 'семен', 'антон',
            'василий', 'виктор', 'юрий', 'олег', 'валерий'
        }
        
        # Определение по окончанию
        female_endings = ['а', 'я', 'ия', 'ья', 'ея', 'уя', 'ая', 'яя']
        male_endings = ['й', 'ь', 'н', 'р', 'л', 'с', 'т', 'в', 'м', 'к', 'г', 'д', 'б', 'п', 'з', 'ж', 'ш', 'ч', 'ц', 'ф', 'х']
        
        # Собираем результаты для каждого слова
        results_by_list = []  # Результаты по списку имен (надежнее)
        results_by_ending = []  # Результаты по окончанию
        
        for word in words_to_check:
            # Проверка по списку имен (приоритет 1)
            if word in female_names:
                results_by_list.append("female")
            elif word in male_names:
                results_by_list.append("male")
            
            # Проверка по окончанию (приоритет 2)
            if len(word) > 1:
                last_char = word[-1]
                if last_char in female_endings:
                    results_by_ending.append("female")
                elif last_char in male_endings and last_char not in ['а', 'я']:
                    results_by_ending.append("male")
        
        # Приоритет: ТОЛЬКО список имен (без окончаний!)
        # ВАЖНО: Женские имена имеют приоритет над мужскими
        # Если есть хотя бы одно женское имя - пол = female (независимо от фамилии)
        has_female_name = False
        has_male_name = False
        
        for word in words_to_check:
            if word in female_names:
                has_female_name = True
            elif word in male_names:
                has_male_name = True
        
        # Приоритет: женские имена > мужские имена
        if has_female_name:
            return "female"  # Если есть женское имя - всегда female, даже если фамилия мужского рода
        elif has_male_name:
            return "male"  # Только если нет женских имен, но есть мужское
        
        # Если имя не найдено в списке - возвращаем None
        # Пол будет определен вручную в кабинете
        return None
    
    def is_local_customer(self, city: Optional[str], phone: Optional[str] = None) -> bool:
        """
        Определение, является ли клиент местным (крымским)
        
        Args:
            city: Город клиента
            phone: Номер телефона (опционально, для проверки префикса)
        
        Returns:
            True если клиент местный, False если приезжий
        """
        # Проверка по городу
        if city:
            city_lower = city.lower().strip()
            for crimean_city in self.CRIMEAN_CITIES:
                if crimean_city.lower() in city_lower:
                    return True
        
        # Проверка по префиксу телефона (7978, 7979 - крымские коды)
        if phone:
            phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
            if phone_clean.startswith("7978") or phone_clean.startswith("7979"):
                return True
        
        return False
    
    def is_brand_in_history(self, purchase_history: List[Dict[str, Any]], brand: str) -> bool:
        """
        Проверка наличия бренда в истории покупок
        
        Args:
            purchase_history: Список покупок
            brand: Название бренда для проверки
        
        Returns:
            True если бренд есть в истории
        """
        if not purchase_history or not brand:
            return False
        
        brand_lower = brand.lower().strip()
        for purchase in purchase_history:
            purchase_brand = purchase.get("brand", "")
            if purchase_brand and purchase_brand.lower().strip() == brand_lower:
                return True
        
        return False
    
    def format_bonus_value(self, bonus_balance: int) -> str:
        """
        Преобразование бонусов в ценность (не цифры)
        
        Args:
            bonus_balance: Баланс бонусов в копейках
        
        Returns:
            Текстовое описание ценности бонусов
        """
        if bonus_balance <= 0:
            return ""
        
        # Примерные пороги для разных формулировок
        if bonus_balance >= 1000000:  # >= 10000 рублей
            return "У вас накоплена значительная сумма, которой можно полностью оплатить украшение"
        elif bonus_balance >= 500000:  # >= 5000 рублей
            return "У вас накоплена сумма, которой можно частично оплатить украшение"
        elif bonus_balance >= 100000:  # >= 1000 рублей
            return "У вас накоплена сумма, которой можно дополнить покупку"
        else:
            return "У вас накоплены бонусы, которые можно использовать при следующей покупке"
    
    async def get_store_name(self, store_id_1c: Optional[str], store_name: Optional[str] = None) -> Optional[str]:
        """
        Получение названия бутика по store_id_1c или использованию переданного названия
        
        Args:
            store_id_1c: ID магазина из 1С
            store_name: Название магазина (если уже известно)
        
        Returns:
            Название бутика или None
        """
        # Если название уже передано, используем его
        if store_name:
            return store_name
        
        # Пытаемся найти по external_id в таблице stores
        if store_id_1c:
            try:
                result = await self.db.execute(
                    select(Store).where(Store.external_id == store_id_1c)
                )
                store = result.scalar_one_or_none()
                if store:
                    return store.name
            except Exception as e:
                logger.warning(f"Error getting store name for {store_id_1c}: {e}")
        
        return None
    
    async def get_store_city(self, store_id_1c: Optional[str]) -> Optional[str]:
        """
        Получение города бутика по store_id_1c из таблицы stores
        
        Args:
            store_id_1c: ID магазина из 1С
        
        Returns:
            Город бутика или None
        """
        if not store_id_1c:
            return None
        
        try:
            result = await self.db.execute(
                select(Store.city).where(Store.external_id == store_id_1c)
            )
            city = result.scalar_one_or_none()
            if city:
                return city
        except Exception as e:
            logger.warning(f"Error getting store city for {store_id_1c}: {e}")
        
        return None
    
    async def get_preferred_store_name(self, user_id: UUID) -> Optional[str]:
        """
        Определение предпочтительного бутика клиента на основе истории покупок
        
        Приоритет:
        1. Бутик последней покупки (если есть)
        2. Бутик с наибольшим количеством покупок
        3. Бутик с наибольшей суммой покупок
        
        Также проверяет поле city из таблицы stores и использует его как fallback.
        
        Args:
            user_id: ID клиента
        
        Returns:
            Название предпочтительного бутика или город из stores.city, или None
        """
        try:
            # Получаем все покупки клиента
            result = await self.db.execute(
                select(PurchaseHistory)
                .where(PurchaseHistory.user_id == user_id)
                .where(PurchaseHistory.store_id_1c.isnot(None))
                .order_by(PurchaseHistory.purchase_date.desc())
            )
            purchases = result.scalars().all()
            
            if not purchases:
                return None
            
            # 1. Приоритет: последняя покупка
            last_purchase = purchases[0]
            if last_purchase.store_id_1c:
                last_store_name = await self.get_store_name(last_purchase.store_id_1c)
                if last_store_name:
                    logger.info(f"Using last purchase store for user {user_id}: {last_store_name}")
                    return last_store_name
                
                # Если не нашли название, пробуем получить город из stores
                store_city = await self.get_store_city(last_purchase.store_id_1c)
                if store_city:
                    logger.info(f"Using city from last purchase store for user {user_id}: {store_city}")
                    return store_city
            
            # 2. Подсчитываем покупки по магазинам
            store_stats = {}  # {store_id_1c: {"count": int, "total": int, "last_date": datetime}}
            
            for purchase in purchases:
                store_id = purchase.store_id_1c
                if not store_id:
                    continue
                
                if store_id not in store_stats:
                    store_stats[store_id] = {
                        "count": 0,
                        "total": 0,
                        "last_date": purchase.purchase_date
                    }
                
                store_stats[store_id]["count"] += 1
                store_stats[store_id]["total"] += purchase.total_amount or 0
                
                # Обновляем дату последней покупки в этом магазине
                if purchase.purchase_date and (
                    not store_stats[store_id]["last_date"] or 
                    purchase.purchase_date > store_stats[store_id]["last_date"]
                ):
                    store_stats[store_id]["last_date"] = purchase.purchase_date
            
            if not store_stats:
                return None
            
            # 3. Находим магазин с наибольшим количеством покупок
            most_frequent_store = max(store_stats.items(), key=lambda x: x[1]["count"])
            most_frequent_store_id = most_frequent_store[0]
            
            # 4. Если есть несколько магазинов с одинаковым количеством, выбираем по сумме
            max_count = most_frequent_store[1]["count"]
            stores_with_max_count = [
                (store_id, stats) 
                for store_id, stats in store_stats.items() 
                if stats["count"] == max_count
            ]
            
            if len(stores_with_max_count) > 1:
                # Выбираем по наибольшей сумме
                preferred_store = max(stores_with_max_count, key=lambda x: x[1]["total"])
                preferred_store_id = preferred_store[0]
            else:
                preferred_store_id = most_frequent_store_id
            
            # Получаем название магазина
            preferred_store_name = await self.get_store_name(preferred_store_id)
            if preferred_store_name:
                logger.info(f"Using preferred store for user {user_id}: {preferred_store_name} (count: {store_stats[preferred_store_id]['count']}, total: {store_stats[preferred_store_id]['total']})")
                return preferred_store_name
            
            # Если не нашли название, пробуем получить город из stores
            store_city = await self.get_store_city(preferred_store_id)
            if store_city:
                logger.info(f"Using city from preferred store for user {user_id}: {store_city}")
                return store_city
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting preferred store for user {user_id}: {e}")
            return None
    
    async def get_last_store_name(self, user_id: UUID) -> Optional[str]:
        """
        Получение названия бутика последней покупки клиента (для обратной совместимости)
        
        Args:
            user_id: ID клиента
        
        Returns:
            Название бутика последней покупки или None
        """
        return await self.get_preferred_store_name(user_id)
    
    async def get_available_store_cities(self) -> List[str]:
        """
        Получение списка городов, где есть активные магазины GLAME
        
        Returns:
            Список уникальных городов с активными магазинами
        """
        try:
            result = await self.db.execute(
                select(distinct(Store.city))
                .where(
                    and_(
                        Store.is_active == True,
                        Store.city.isnot(None),
                        Store.external_id.isnot(None)  # Только магазины с UUID из 1С
                    )
                )
            )
            cities = [row[0] for row in result.all() if row[0]]
            logger.debug(f"Available store cities: {cities}")
            return cities
        except Exception as e:
            logger.warning(f"Error getting available store cities: {e}")
            return []
    
    async def generate_message(
        self,
        client_id: UUID,
        event: Dict[str, Any],
        client_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Генерация персонального сообщения для клиента
        
        Args:
            client_id: ID клиента
            event: Событие (type, brand, store и т.д.)
            client_data: Предзагруженные данные клиента (опционально)
        
        Returns:
            Словарь с segment, message, cta и другой информацией
        """
        try:
            # Получаем данные клиента (если не переданы)
            if not client_data:
                # Импортируем здесь, чтобы избежать циклической зависимости
                from app.services.communication_service import CommunicationService
                service = CommunicationService(self.db)
                client_data = await service.get_client_data(client_id)
            
            if not client_data:
                raise ValueError(f"Client {client_id} not found")
            
            # Проверяем наличие бренда в истории (для brand_arrival)
            event_type = event.get("type", "")
            event_brand = event.get("brand", "")
            
            # Для brand_arrival обязательно проверяем наличие бренда в истории
            if event_type == "brand_arrival" and event_brand:
                if not self.is_brand_in_history(client_data.get("purchase_history", []), event_brand):
                    raise ValueError(f"Brand {event_brand} not found in client purchase history")
            
            # Для других типов событий бренд не обязателен, но если указан - проверяем
            elif event_brand and event_type in ["loyalty_level_up", "holiday_male"]:
                # Для этих событий бренд опционален, но если есть - можно упомянуть
                pass
            
            # Определяем сегмент
            total_spend_365 = client_data.get("total_spend_365", 0)
            purchases_365 = client_data.get("purchases_365", 0)
            days_since_last = client_data.get("days_since_last")
            city = client_data.get("city")
            phone = client_data.get("phone")
            client_name = client_data.get("name", "Клиент")
            
            # Определяем пол клиента: сначала из данных (БД), если нет - по имени
            gender = client_data.get("gender")
            if not gender and client_name:
                # Если пол не указан в данных, определяем по имени
                gender = self.determine_gender(client_name)
            
            is_local = self.is_local_customer(city, phone)
            segment = self.determine_segment(
                total_spend_365,
                purchases_365,
                days_since_last,
                is_local
            )
            
            # Получаем название бутика
            store_name = event.get("store")
            auto_detect = event.get("auto_detect_store", False)
            
            # Получаем город из профиля (поле city из БД)
            city_from_profile = client_data.get("city")
            
            # Получаем список городов, где есть активные магазины GLAME
            store_cities = await self.get_available_store_cities()
            
            if auto_detect or not store_name:
                # Определяем предпочтительный бутик на основе истории покупок и города из БД
                # Приоритет: история покупок (последняя покупка > больше всего покупок > наибольшая сумма) > город из профиля (поле city)
                store_name = await self.get_preferred_store_name(client_id)
                
                # Если не нашли из истории покупок, используем город из профиля
                if not store_name:
                    if city_from_profile:
                        store_name = city_from_profile
                        logger.info(f"Using city from profile (DB field) for user {client_id}: {city_from_profile}")
                
                # Проверяем, соответствует ли город из профиля городу магазина
                if city_from_profile and store_cities:
                    # Нормализуем названия городов для сравнения (без учета регистра)
                    city_from_profile_normalized = city_from_profile.strip().lower()
                    store_cities_normalized = [c.strip().lower() for c in store_cities if c]
                    
                    # Проверяем, есть ли город из профиля в списке городов магазинов
                    city_matches_store = city_from_profile_normalized in store_cities_normalized
                    
                    if not city_matches_store:
                        # Город из профиля не соответствует городу магазина
                        # Устанавливаем специальный флаг для промпта
                        logger.info(f"Client city '{city_from_profile}' does not match store cities {store_cities}, will suggest all stores")
                        store_name = None  # Сбрасываем, чтобы в промпте указать "приходите в любой удобный"
                        client_data["suggest_all_stores"] = True
                        client_data["available_store_cities"] = store_cities
                    else:
                        client_data["suggest_all_stores"] = False
                else:
                    client_data["suggest_all_stores"] = False
            
            # Формируем промпт для LLM
            bonus_value = ""
            bonus_balance = client_data.get("bonus_balance", 0)
            if bonus_balance > 0:
                bonus_value = self.format_bonus_value(bonus_balance)
            
            # Проверяем, нужно ли предлагать все магазины
            suggest_all_stores = client_data.get("suggest_all_stores", False)
            available_store_cities = client_data.get("available_store_cities", [])
            
            # Формируем данные для промпта
            prompt_data = {
                "client": {
                    "name": client_name,
                    "gender": gender,  # Добавляем пол клиента
                    "phone": phone or "",
                    "purchase_history": client_data.get("purchase_history", []),
                    "total_spend_365": total_spend_365 // 100,  # В рублях для промпта
                    "purchases_365": purchases_365,
                    "last_purchase_date": client_data.get("last_purchase_date"),
                    "bonus_balance": bonus_balance // 100,  # В рублях для промпта
                    "is_local": is_local,
                    "city": city or ""
                },
                "event": event,
                "segment": segment,
                "store_name": store_name,
                "bonus_value": bonus_value,
                "suggest_all_stores": suggest_all_stores,
                "available_store_cities": available_store_cities
            }
            
            # Формируем специфичные инструкции для разных типов событий
            event_instructions = ""
            if event_type == "brand_arrival":
                event_instructions = f"Событие: в бутик пришел бренд {event_brand}. Сообщи об этом клиенту, упомянув его предыдущие покупки этого бренда."
            elif event_type == "loyalty_level_up":
                event_instructions = "Событие: клиент достиг нового уровня лояльности. Поздравь его и расскажи о преимуществах нового уровня."
            elif event_type == "bonus_balance":
                event_instructions = f"Событие: у клиента есть накопленные бонусы. Напомни о них, используя формулировку: {bonus_value if bonus_value else 'бонусы можно использовать при покупке'}."
            elif event_type == "no_purchase_180":
                event_instructions = "Событие: клиент давно не делал покупок (более 180 дней). Напиши сообщение о возвращении, мягко пригласи в бутик."
            elif event_type == "holiday_male":
                event_instructions = "Событие: приближается праздник (14.02, 23.02 или 8.03). Предложи идеи для подарков мужчинам."
            else:
                event_instructions = f"Событие: {event_type}. Сформируй соответствующее сообщение."
            
            prompt = f"""Сгенерируй персональное сообщение для клиента GLAME.

Данные клиента:
{json.dumps(prompt_data["client"], ensure_ascii=False, indent=2)}

ВАЖНО:
- Имя клиента: {client_name}
- Пол клиента: {gender or "не определен"}
- Используй ТОЛЬКО имя (без фамилии и отчества) для обращения в начале сообщения
- Примеры: "Татьяна, ..." (для "Кальчева Татьяна"), "Андрей, ..." (для "Корлюков Андрей")

Событие:
{json.dumps(event, ensure_ascii=False, indent=2)}

{event_instructions}

Определенный сегмент: {segment}
Местный клиент: {"да" if is_local else "нет"}
Название бутика: {store_name or "не указано"}
{f"ВАЖНО: Город клиента ({city_from_profile}) не соответствует городам, где есть магазины GLAME ({', '.join(available_store_cities)}). Предложи клиенту прийти в любой удобный магазин GLAME, используя фразу 'приходите в какой удобнее' или 'приходите в любой удобный бутик GLAME'." if suggest_all_stores and available_store_cities else ""}
{("Ценность бонусов: " + bonus_value) if bonus_value else ""}

Следуй всем правилам из системного промпта:
1. Используй тон для сегмента {segment}
2. {f"Предложи прийти в любой удобный магазин GLAME (города: {', '.join(available_store_cities)}), используя фразу 'приходите в какой удобнее' или 'приходите в любой удобный бутик GLAME'" if suggest_all_stores and available_store_cities else ("Укажи бутик " + store_name if store_name and is_local else "Веди на сайт и онлайн-консультацию")}
3. {"Упомяни бренд " + event_brand if event_brand else "Используй информацию о брендах из истории покупок"}
4. {"Используй информацию о бонусах: " + bonus_value if bonus_value else ""}

Верни ТОЛЬКО валидный JSON:
{{
  "segment": "{segment}",
  "message": "текст сообщения",
  "cta": "призыв к действию"
}}"""
            
            # Генерируем ответ через LLM
            response_text = await self.generate_response(
                prompt=prompt,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=500
            )
            
            # Парсим JSON ответ
            try:
                # Извлекаем JSON из ответа (может быть обернут в markdown или текст)
                response_text = response_text.strip()
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()
                
                response_data = json.loads(response_text)
                
                # Формируем полный ответ
                result = {
                    "client_id": str(client_id),
                    "phone": client_data.get("phone"),
                    "name": client_name,
                    "gender": gender,  # Добавляем пол в результат
                    "segment": response_data.get("segment", segment),
                    "reason": event_type,
                    "message": response_data.get("message", ""),
                    "cta": response_data.get("cta", ""),
                }
                
                # Добавляем бренд и магазин если есть
                if event_brand:
                    result["brand"] = event_brand
                if store_name:
                    result["store"] = store_name
                
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {response_text[:200]}")
                raise ValueError(f"LLM returned invalid JSON: {e}")
        
        except Exception as e:
            logger.exception(f"Error generating message for client {client_id}: {e}")
            raise
