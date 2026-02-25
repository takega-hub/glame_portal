"""
Сервис синхронизации покупателей из 1С
"""
import logging
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.product import Product
from app.models.loyalty_transaction import LoyaltyTransaction
from app.services.onec_customers_service import OneCCustomersService
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.agents.communication_agent import CommunicationAgent

logger = logging.getLogger(__name__)


class CustomerSyncService:
    """Сервис синхронизации покупателей из 1С"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.onec_service = None
        self._communication_agent = None
    
    async def _get_onec_service(self) -> OneCCustomersService:
        """Получение или создание сервиса 1С"""
        if not self.onec_service:
            self.onec_service = OneCCustomersService()
        return self.onec_service
    
    async def sync_discount_cards(
        self,
        limit: int = 1000,
        batch_size: int = 1000,
        load_all: bool = True,
        progress_callback: Optional[Callable[[int, str, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Синхронизация дисконтных карт из 1С
        Создает/обновляет пользователей с phone = КодКартыШтрихкод
        
        Args:
            limit: Максимальное количество карт для загрузки (если load_all=False)
            batch_size: Размер батча для пагинации (по умолчанию 1000)
            load_all: Если True, загружает все карты с пагинацией. Если False, загружает только limit карт
        """
        stats = {
            "created": 0,
            "updated": 0,
            "errors": 0,
            "skipped": 0,
            "total_loaded": 0
        }
        
        try:
            onec_service = await self._get_onec_service()
            
            offset = 0
            total_loaded = 0
            batch_count = 0
            
            if load_all:
                print(f"Загрузка всех дисконтных карт порциями по {batch_size}...")
                logger.info(f"Начало загрузки всех дисконтных карт (batch_size={batch_size})")
            else:
                print(f"Загрузка до {limit} дисконтных карт...")
                logger.info(f"Загрузка дисконтных карт (limit={limit})")
            
            while True:
                try:
                    # Определяем сколько загружать в этом батче
                    current_batch_size = batch_size
                    if not load_all and total_loaded + batch_size > limit:
                        current_batch_size = limit - total_loaded
                        if current_batch_size <= 0:
                            break
                    
                    # Загружаем батч
                    cards = await onec_service.fetch_discount_cards(
                        limit=current_batch_size,
                        offset=offset
                    )
                    
                    if not cards:
                        # Больше нет данных
                        break
                    
                    logger.info(f"Получено {len(cards)} дисконтных карт (offset={offset}, total={total_loaded + len(cards)})")
                    print(f"Загружено {len(cards)} карт (всего: {total_loaded + len(cards)})...")
                    
                    # Обрабатываем карты
                    batch_stats = await self._process_cards_batch(cards)
                    stats["created"] += batch_stats["created"]
                    stats["updated"] += batch_stats["updated"]
                    stats["errors"] += batch_stats["errors"]
                    stats["skipped"] += batch_stats["skipped"]
                    
                    total_loaded += len(cards)
                    offset += len(cards)
                    batch_count += 1

                    if progress_callback:
                        # Прогресс для этапа карточек: 10% - 40%
                        if not load_all and limit > 0:
                            progress = 10 + int((min(total_loaded, limit) / limit) * 30)
                        else:
                            # Для полной загрузки без известного total - увеличиваем по батчам
                            progress = min(40, 10 + batch_count * 2)
                        progress_callback(
                            progress,
                            "Синхронизация дисконтных карт...",
                            f"Загружено {total_loaded} карт (создано {stats['created']}, обновлено {stats['updated']})",
                        )
                    
                    # Если загрузили меньше чем запрашивали, значит это последний батч
                    if len(cards) < current_batch_size:
                        break
                    
                    # Если не загружаем все и достигли лимита
                    if not load_all and total_loaded >= limit:
                        break
                    
                    # Коммитим после каждого батча для безопасности
                    await self.db.commit()
                    
                except Exception as e:
                    logger.error(f"Ошибка при получении батча дисконтных карт (offset={offset}): {e}")
                    print(f"Ошибка при загрузке батча (offset={offset}): {e}")
                    stats["errors"] += 1
                    # Продолжаем со следующим батчем
                    offset += batch_size
                    continue
            
            # Финальный коммит для последнего батча
            await self.db.commit()
            
            stats["total_loaded"] = total_loaded
            logger.info(f"Синхронизация завершена: загружено {total_loaded}, создано {stats['created']}, обновлено {stats['updated']}")
            print(f"\nСинхронизация завершена:")
            print(f"  Всего загружено: {total_loaded}")
            print(f"  Создано: {stats['created']}")
            print(f"  Обновлено: {stats['updated']}")
            print(f"  Пропущено: {stats['skipped']}")
            print(f"  Ошибок: {stats['errors']}")
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации дисконтных карт: {e}")
            print(f"Ошибка синхронизации дисконтных карт: {e}")
            await self.db.rollback()
            stats["errors"] += 1
            raise
        
        return stats
    
    async def _process_cards_batch(self, cards: List[Dict[str, Any]]) -> Dict[str, int]:
        """Обработка батча карт"""
        batch_stats = {
            "created": 0,
            "updated": 0,
            "errors": 0,
            "skipped": 0
        }
        onec_service = await self._get_onec_service()
        customer_cache: Dict[str, Dict[str, Any]] = {}

        for card_data in cards:
            try:
                phone = card_data.get("КодКартыШтрихкод")
                if not phone:
                    batch_stats["skipped"] += 1
                    continue
                
                discount_card_id_1c = card_data.get("Ref_Key")
                customer_id_1c = card_data.get("ВладелецКарты_Key")
                card_code = card_data.get("Code", "")
                description = card_data.get("Description", "")

                customer_data = None
                if customer_id_1c:
                    if customer_id_1c in customer_cache:
                        customer_data = customer_cache[customer_id_1c]
                    else:
                        try:
                            customer_data = await onec_service.fetch_customer_details(customer_id_1c)
                        except Exception as e:
                            logger.warning(
                                "Не удалось получить данные контрагента %s: %s",
                                customer_id_1c,
                                e,
                            )
                            customer_data = None
                        customer_cache[customer_id_1c] = customer_data or {}

                full_name, email, city = self._extract_customer_fields(customer_data, description)
                
                # Логируем извлеченный город
                if city:
                    logger.info(f"Извлечен город для карты {phone}: {city}")

                # Ищем существующего пользователя с приоритетом по карте
                stmt = select(User).where(User.discount_card_id_1c == discount_card_id_1c)
                result = await self.db.execute(stmt)
                existing_user = result.scalar_one_or_none()
                if not existing_user:
                    stmt = select(User).where(User.phone == phone)
                    result = await self.db.execute(stmt)
                    existing_user = result.scalar_one_or_none()
                
                if existing_user:
                    # Обновляем существующего пользователя
                    existing_user.phone = phone
                    existing_user.discount_card_number = phone  # номер карты = телефон
                    existing_user.discount_card_id_1c = discount_card_id_1c
                    existing_user.customer_id_1c = customer_id_1c
                    existing_user.is_customer = True
                    existing_user.synced_at = datetime.utcnow()
                    if not existing_user.role:
                        existing_user.role = "customer"
                    if full_name and not existing_user.full_name:
                        existing_user.full_name = full_name
                    if email and not existing_user.email:
                        existing_user.email = email
                    if city:
                        logger.info(f"Обновляем город для {phone}: {city}")
                        existing_user.city = city
                    batch_stats["updated"] += 1
                else:
                    # Определяем пол для нового пользователя
                    gender = None
                    if full_name:
                        gender = self._determine_gender(full_name)
                        if gender:
                            logger.debug(f"Определен пол для нового клиента {phone}: {gender}")
                    
                    # Создаем нового пользователя
                    new_user = User(
                        phone=phone,
                        discount_card_number=phone,
                        discount_card_id_1c=discount_card_id_1c,
                        customer_id_1c=customer_id_1c,
                        is_customer=True,
                        role="customer",
                        synced_at=datetime.utcnow(),
                        full_name=full_name,
                        email=email,
                        city=city,
                        gender=gender,
                        loyalty_points=0,
                        total_purchases=0,
                        total_spent=0
                    )
                    self.db.add(new_user)
                    batch_stats["created"] += 1
                
            except Exception as e:
                logger.error(f"Ошибка при синхронизации карты {card_data.get('Code')}: {e}")
                batch_stats["errors"] += 1
                continue
        
        return batch_stats

    @staticmethod
    def _extract_customer_fields(
        customer_data: Optional[Dict[str, Any]],
        description: Optional[str],
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Извлекает поля покупателя из данных 1С.
        Возвращает: (full_name, email, city)
        """
        if not customer_data:
            return (description or None), None, None

        name_fields = [
            "Description",
            "Наименование",
            "НаименованиеПолное",
            "ПолноеНаименование",
            "ФИО",
            "Имя",
        ]
        email_fields = [
            "Email",
            "ЭлектроннаяПочта",
            "АдресЭлектроннойПочты",
            "EmailAddress",
        ]

        full_name = None
        for field in name_fields:
            value = customer_data.get(field)
            if value:
                full_name = value
                break

        email = None
        for field in email_fields:
            value = customer_data.get(field)
            if value:
                email = value
                break

        if not full_name:
            full_name = description or None

        # Извлекаем город из адреса
        city = None
        try:
            # Логируем доступные поля для отладки
            logger.debug(f"Поля контрагента для извлечения города: {list(customer_data.keys())[:20]}")
            
            # ПРИОРИТЕТ 1: Поле "ОсновныеСведения" (многострочное, город на 3-й строке)
            основные_сведения = customer_data.get("ОсновныеСведения")
            if основные_сведения:
                logger.debug(f"Найдено поле ОсновныеСведения: {type(основные_сведения)}")
                if isinstance(основные_сведения, str):
                    # Разбиваем на строки и берем третью строку (индекс 2)
                    lines = основные_сведения.strip().split('\n')
                    if len(lines) >= 3:
                        city = lines[2].strip()
                        if city:
                            logger.info(f"Город найден в ОсновныеСведения: {city}")
                elif isinstance(основные_сведения, list) and len(основные_сведения) >= 3:
                    city = str(основные_сведения[2]).strip()
                    if city:
                        logger.info(f"Город найден в ОсновныеСведения (список): {city}")
            
            # ПРИОРИТЕТ 2: Пробуем разные варианты структуры адреса
            if not city:
                address_data = customer_data.get("Состав") or customer_data.get("Адрес") or customer_data.get("Address")
                
                if address_data:
                    # Если это словарь с вложенной структурой
                    if isinstance(address_data, dict):
                        # Пробуем найти АдресРФ
                        address_rf = address_data.get("АдресРФ") or address_data.get("Адрес")
                        if address_rf and isinstance(address_rf, dict):
                            # Берем значение из поля Улица (там хранится город)
                            city = address_rf.get("Улица") or address_rf.get("Город") or address_rf.get("City")
                        # Если нет вложенности, проверяем прямое поле Улица
                        if not city:
                            city = address_data.get("Улица") or address_data.get("Город") or address_data.get("City")
                    # Если это список, берем первый элемент
                    elif isinstance(address_data, list) and len(address_data) > 0:
                        first_item = address_data[0]
                        if isinstance(first_item, dict):
                            address_rf = first_item.get("АдресРФ") or first_item.get("Адрес")
                            if address_rf and isinstance(address_rf, dict):
                                city = address_rf.get("Улица") or address_rf.get("Город") or address_rf.get("City")
                            if not city:
                                city = first_item.get("Улица") or first_item.get("Город") or first_item.get("City")
            
            # ПРИОРИТЕТ 3: Прямые поля для города
            if not city:
                city = customer_data.get("Город") or customer_data.get("City") or customer_data.get("НаселенныйПункт")
            
            # ПРИОРИТЕТ 4: Поиск в контактной информации (КонтактнаяИнформация)
            if not city:
                contact_info = customer_data.get("КонтактнаяИнформация") or customer_data.get("ContactInfo")
                if contact_info:
                    logger.debug(f"Найдена контактная информация: {type(contact_info)}")
                    if isinstance(contact_info, list):
                        for ci in contact_info:
                            if isinstance(ci, dict):
                                # Ищем запись с типом "Адрес"
                                ci_type = ci.get("Тип") or ci.get("Type") or ""
                                if "Адрес" in str(ci_type) or "Address" in str(ci_type):
                                    city = ci.get("Город") or ci.get("City") or ci.get("Представление")
                                    if city:
                                        logger.info(f"Город найден в контактной информации: {city}")
                                        break
                    elif isinstance(contact_info, dict):
                        city = contact_info.get("Город") or contact_info.get("City")
            
            # ПРИОРИТЕТ 5: Поиск города в строке Представление/Комментарий
            if not city:
                представление = customer_data.get("Представление") or customer_data.get("Комментарий") or ""
                if представление and isinstance(представление, str):
                    # Известные города Крыма
                    known_cities = ["Симферополь", "Севастополь", "Ялта", "Евпатория", "Керчь", "Феодосия", "Алушта"]
                    for known_city in known_cities:
                        if known_city.lower() in представление.lower():
                            city = known_city
                            logger.info(f"Город найден в Представление: {city}")
                            break
                            
        except Exception as e:
            logger.warning(f"Ошибка при извлечении города из данных 1С: {e}")

        return full_name, email, city
    
    async def sync_initial_balances(
        self, 
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Синхронизация начального ввода (миграция из старой системы).
        Ищет записи типа Document_ВводНачальныхОстатков без ограничения по дате.
        """
        stats = {
            "created": 0,
            "updated": 0,
            "errors": 0,
            "skipped": 0
        }
        
        try:
            onec_service = await self._get_onec_service()
            
            # Получаем пользователей для синхронизации
            if user_id:
                stmt = select(
                    User.id,
                    User.customer_id_1c,
                    User.discount_card_id_1c,
                ).where(User.id == user_id, User.is_customer == True)
            else:
                stmt = select(
                    User.id,
                    User.customer_id_1c,
                    User.discount_card_id_1c,
                ).where(User.is_customer == True)
            
            result = await self.db.execute(stmt)
            users = result.all()
            
            logger.info(f"Синхронизация начального ввода для {len(users)} покупателей")
            
            for user in users:
                user_id = user.id
                customer_id_1c = user.customer_id_1c
                discount_card_id_1c = user.discount_card_id_1c
                
                if not discount_card_id_1c:
                    stats["skipped"] += 1
                    continue
                
                try:
                    # Получаем ВСЕ продажи по карте без фильтрации по дате
                    purchases = await onec_service.fetch_sales_by_discount_card(
                        discount_card_key=discount_card_id_1c,
                        start_date=None,  # Без фильтрации по дате
                        end_date=None,
                        limit=10000,
                    )
                    
                    # Фильтруем только записи типа Document_ВводНачальныхОстатков
                    migration_purchases = [
                        p for p in purchases 
                        if "ВводНачальныхОстатков" in p.get("Recorder_Type", "")
                    ]
                    
                    if migration_purchases:
                        logger.info(
                            f"Найдено {len(migration_purchases)} записей начального ввода для пользователя {user_id}"
                        )
                    
                    for purchase_data in migration_purchases:
                        try:
                            document_id_1c = purchase_data.get("Recorder")
                            product_id_1c = purchase_data.get("Номенклатура_Key")
                            purchase_date_str = purchase_data.get("Period")
                            
                            if not document_id_1c or not purchase_date_str:
                                continue
                            
                            # Парсим дату
                            try:
                                purchase_date = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
                                if purchase_date.tzinfo is None:
                                    purchase_date = purchase_date.replace(tzinfo=timezone.utc)
                                else:
                                    purchase_date = purchase_date.astimezone(timezone.utc)
                            except Exception:
                                purchase_date = datetime.now(timezone.utc)
                            
                            # Получаем сумму и количество
                            amount = purchase_data.get("Сумма", 0)
                            quantity = purchase_data.get("Количество", 1)
                            amount_kopecks = self._to_kopecks(amount)
                            price_kopecks = amount_kopecks // quantity if quantity > 0 else 0
                            
                            # Проверяем, существует ли уже эта запись
                            # Важно: учитываем NULL значения в document_id_1c и product_id_1c
                            # Сравниваем только по дню, без учета времени
                            conditions = [
                                PurchaseHistory.user_id == user_id,
                                func.date(PurchaseHistory.purchase_date) == purchase_date.date()
                            ]
                            
                            # Добавляем условия для document_id_1c (с учетом NULL)
                            if document_id_1c:
                                conditions.append(PurchaseHistory.document_id_1c == document_id_1c)
                            else:
                                conditions.append(PurchaseHistory.document_id_1c.is_(None))
                            
                            # Добавляем условия для product_id_1c (с учетом NULL)
                            if product_id_1c:
                                conditions.append(PurchaseHistory.product_id_1c == product_id_1c)
                            else:
                                conditions.append(PurchaseHistory.product_id_1c.is_(None))
                            
                            stmt = select(PurchaseHistory).where(and_(*conditions)).order_by(PurchaseHistory.created_at)
                            result = await self.db.execute(stmt)
                            existing_purchases = result.scalars().all()
                            
                            # Если найдено несколько записей, удаляем дубликаты (оставляем самую раннюю)
                            if len(existing_purchases) > 1:
                                logger.warning(
                                    "Найдено %s дубликатов начального ввода для user_id=%s, document_id_1c=%s, product_id_1c=%s, date=%s. Удаляем дубликаты.",
                                    len(existing_purchases), user_id, document_id_1c, product_id_1c, purchase_date
                                )
                                # Оставляем первую (самую раннюю) запись, удаляем остальные
                                for dup in existing_purchases[1:]:
                                    await self.db.delete(dup)
                                    logger.debug(f"Удален дубликат начального ввода: id={dup.id}")
                            
                            existing_purchase = existing_purchases[0] if existing_purchases else None
                            
                            if existing_purchase:
                                # Обновляем существующую запись (исправляем суммы)
                                if existing_purchase.total_amount != amount_kopecks:
                                    logger.info(
                                        f"Обновление суммы начального ввода: {existing_purchase.total_amount} -> {amount_kopecks}"
                                    )
                                    existing_purchase.total_amount = amount_kopecks
                                    existing_purchase.price = price_kopecks
                                    stats["updated"] = stats.get("updated", 0) + 1
                                else:
                                    stats["skipped"] += 1
                                continue
                            
                            # Получаем данные товара
                            product_article = None
                            glame_product_id = None
                            product_name_from_1c = purchase_data.get("Номенклатура_Description")
                            category_from_1c = purchase_data.get("Номенклатура_Категория")
                            brand_from_1c = purchase_data.get("Номенклатура_Бренд")
                            
                            if product_id_1c:
                                try:
                                    product_details = await onec_service.fetch_product_details(product_id_1c)
                                    if product_details:
                                        product_article = product_details.get("article") or product_details.get("code")
                                        if not product_name_from_1c:
                                            product_name_from_1c = product_details.get("name")
                                        if not category_from_1c:
                                            category_from_1c = product_details.get("category")
                                        if not brand_from_1c:
                                            brand_from_1c = product_details.get("brand")
                                        
                                        # Ищем товар в нашем каталоге
                                        if product_article:
                                            stmt = select(Product).where(
                                                or_(
                                                    Product.external_id == product_id_1c,
                                                    Product.article == product_article
                                                )
                                            ).limit(1)
                                            result = await self.db.execute(stmt)
                                            product = result.scalars().first()
                                            if product:
                                                glame_product_id = product.id
                                except Exception as e:
                                    logger.warning(f"Не удалось получить данные товара {product_id_1c}: {e}")
                            
                            # Создаем новую запись покупки с защитой от дубликатов
                            try:
                                new_purchase = PurchaseHistory(
                                    user_id=user_id,
                                    document_id_1c=document_id_1c,
                                    store_id_1c=purchase_data.get("Склад_Key"),
                                    product_id=glame_product_id,
                                    product_id_1c=product_id_1c,
                                    product_article=product_article,
                                    product_name=product_name_from_1c,
                                    purchase_date=purchase_date,
                                    quantity=quantity,
                                    price=price_kopecks,
                                    total_amount=amount_kopecks,
                                    category=category_from_1c,
                                    brand=brand_from_1c,
                                    sync_metadata=purchase_data
                                )
                                self.db.add(new_purchase)
                                # Пытаемся зафлашить, чтобы проверить на дубликаты сразу
                                await self.db.flush()
                                stats["created"] += 1
                            except Exception as e:
                                # Если возникла ошибка уникальности, значит запись уже существует
                                error_str = str(e).lower()
                                if 'unique' in error_str or 'duplicate' in error_str:
                                    await self.db.rollback()
                                    
                                    # Повторно ищем запись
                                    stmt = select(PurchaseHistory).where(and_(*conditions)).order_by(PurchaseHistory.created_at)
                                    result = await self.db.execute(stmt)
                                    existing_purchase = result.scalars().first()
                                    
                                    if existing_purchase:
                                        # Обновляем существующую запись
                                        if existing_purchase.total_amount != amount_kopecks:
                                            existing_purchase.total_amount = amount_kopecks
                                            existing_purchase.price = price_kopecks
                                            stats["updated"] = stats.get("updated", 0) + 1
                                        else:
                                            stats["skipped"] += 1
                                        logger.debug(f"Обновлена существующая запись начального ввода после конфликта: user_id={user_id}, document_id_1c={document_id_1c}")
                                    else:
                                        logger.warning(f"Не удалось создать или обновить запись начального ввода: {e}")
                                        stats["errors"] += 1
                                else:
                                    # Другая ошибка - пробрасываем дальше
                                    raise
                            
                        except Exception as e:
                            logger.error(f"Ошибка при синхронизации покупки начального ввода: {e}")
                            stats["errors"] += 1
                            continue
                    
                    # Пересчитываем метрики пользователя, если были добавлены записи
                    if migration_purchases:
                        await self.calculate_customer_metrics(user_id)
                        await self.update_customer_segment(user_id)
                        logger.debug(f"Пересчитаны метрики и сегмент для пользователя {user_id} после начального ввода")
                    
                except Exception as e:
                    logger.error(f"Ошибка при получении начального ввода для пользователя {user_id}: {e}")
                    stats["errors"] += 1
                    continue
            
            await self.db.commit()
            logger.info(f"Синхронизация начального ввода завершена: {stats}")
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации начального ввода: {e}")
            await self.db.rollback()
            raise
        
        return stats

    async def sync_purchase_history(
        self, 
        user_id: Optional[UUID] = None, 
        days: int = 365
    ) -> Dict[str, Any]:
        """
        Синхронизация истории покупок из 1С
        Из AccumulationRegister_Продажи_RecordType и AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType
        """
        stats = {
            "created": 0,
            "updated": 0,
            "errors": 0
        }
        
        try:
            onec_service = await self._get_onec_service()
            
            # Определяем период
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            # Получаем пользователей для синхронизации (только нужные поля, без ORM объектов)
            if user_id:
                stmt = select(
                    User.id,
                    User.customer_id_1c,
                    User.discount_card_id_1c,
                ).where(User.id == user_id, User.is_customer == True)
            else:
                stmt = select(
                    User.id,
                    User.customer_id_1c,
                    User.discount_card_id_1c,
                ).where(User.is_customer == True)
            
            result = await self.db.execute(stmt)
            users = result.all()
            
            logger.info(f"Синхронизация истории покупок для {len(users)} покупателей")
            
            for user in users:
                # Используем значения из Row, чтобы избежать lazy loading
                user_id = user.id
                customer_id_1c = user.customer_id_1c
                discount_card_id_1c = user.discount_card_id_1c
                
                if not customer_id_1c and not discount_card_id_1c:
                    continue
                
                try:
                    purchases: List[Dict[str, Any]] = []
                    source_name = None
                    
                    # Приоритет: продажи по дисконтной карте (точная привязка)
                    # Используем ТОЛЬКО этот источник, чтобы избежать дубликатов
                    if discount_card_id_1c:
                        try:
                            purchases = await onec_service.fetch_sales_by_discount_card(
                                discount_card_key=discount_card_id_1c,
                                start_date=start_date,
                                end_date=end_date,
                                limit=10000,  # Увеличиваем лимит для получения всех покупок
                            )
                            source_name = "AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType"
                            logger.debug(
                                "Получено %s продаж по карте %s за период %s - %s (источник: %s)",
                                len(purchases),
                                discount_card_id_1c,
                                start_date.date(),
                                end_date.date(),
                                source_name
                            )
                        except Exception as e:
                            logger.warning(
                                "Не удалось получить продажи по карте %s: %s. Используем fallback.",
                                discount_card_id_1c,
                                e,
                            )

                    # Резерв: продажи по контрагенту (только если нет данных по карте)
                    # ВАЖНО: Этот источник может содержать те же данные, что и по карте,
                    # поэтому используем его ТОЛЬКО если по карте ничего не найдено (len(purchases) == 0)
                    # и НЕ используем оба источника одновременно, чтобы избежать дубликатов
                    if len(purchases) == 0 and customer_id_1c:
                        logger.info(
                            "Данные по карте не найдены для пользователя %s. Используем fallback источник по контрагенту.",
                            user_id
                        )
                        purchases = await onec_service.get_customer_purchases(
                            customer_key=customer_id_1c,
                            start_date=start_date,
                            end_date=end_date
                        )
                        source_name = "AccumulationRegister_Продажи_RecordType"
                        logger.debug(
                            "Получено %s продаж по контрагенту %s за период %s - %s (источник: %s)",
                            len(purchases),
                            customer_id_1c,
                            start_date.date(),
                            end_date.date(),
                            source_name
                        )
                    elif len(purchases) > 0 and customer_id_1c:
                        logger.debug(
                            "Найдено %s покупок по карте. Fallback источник по контрагенту НЕ используется для предотвращения дубликатов.",
                            len(purchases)
                        )
                    
                    if not purchases:
                        logger.debug("Покупки не найдены для пользователя %s", user_id)
                        continue
                    
                    # Собираем уникальные ключи для дедупликации в рамках одного источника
                    # Это предотвращает дубликаты, если один источник возвращает одинаковые записи
                    seen_keys = set()
                    
                    for purchase_data in purchases:
                        try:
                            # Проверяем, существует ли уже эта покупка
                            document_id_1c = purchase_data.get("Документ") or purchase_data.get("Recorder")
                            product_id_1c = purchase_data.get("Номенклатура_Key")
                            purchase_date_str = purchase_data.get("Period")
                            
                            if not document_id_1c or not purchase_date_str:
                                continue
                            
                            # Парсим дату и нормализуем к aware UTC
                            try:
                                purchase_date = datetime.fromisoformat(purchase_date_str.replace("Z", "+00:00"))
                                if purchase_date.tzinfo is None:
                                    purchase_date = purchase_date.replace(tzinfo=timezone.utc)
                                else:
                                    purchase_date = purchase_date.astimezone(timezone.utc)
                            except Exception:
                                purchase_date = datetime.now(timezone.utc)
                            
                            # Создаем уникальный ключ для дедупликации в рамках одного источника
                            # Используем комбинацию: document_id_1c + product_id_1c + дата (только день)
                            unique_key = (
                                document_id_1c or '',
                                product_id_1c or '',
                                purchase_date.date()
                            )
                            
                            # Пропускаем дубликаты в рамках одного источника
                            if unique_key in seen_keys:
                                logger.debug(
                                    "Пропущен дубликат в рамках источника %s: document_id_1c=%s, product_id_1c=%s, date=%s",
                                    source_name, document_id_1c, product_id_1c, purchase_date.date()
                                )
                                continue
                            
                            seen_keys.add(unique_key)
                            
                            # Ищем существующую запись
                            # Используем комбинацию полей для уникальности: user_id + document_id_1c + product_id_1c + DATE(purchase_date)
                            # Важно: учитываем NULL значения в document_id_1c и product_id_1c
                            # Сравниваем только по дню, без учета времени
                            conditions = [
                                PurchaseHistory.user_id == user_id,
                                func.date(PurchaseHistory.purchase_date) == purchase_date.date()
                            ]
                            
                            # Добавляем условия для document_id_1c (с учетом NULL)
                            if document_id_1c:
                                conditions.append(PurchaseHistory.document_id_1c == document_id_1c)
                            else:
                                conditions.append(PurchaseHistory.document_id_1c.is_(None))
                            
                            # Добавляем условия для product_id_1c (с учетом NULL)
                            if product_id_1c:
                                conditions.append(PurchaseHistory.product_id_1c == product_id_1c)
                            else:
                                conditions.append(PurchaseHistory.product_id_1c.is_(None))
                            
                            stmt = select(PurchaseHistory).where(and_(*conditions)).order_by(PurchaseHistory.created_at)
                            result = await self.db.execute(stmt)
                            existing_purchases = result.scalars().all()
                            
                            # Если найдено несколько записей, удаляем дубликаты (оставляем самую раннюю)
                            if len(existing_purchases) > 1:
                                logger.warning(
                                    "Найдено %s дубликатов покупки для user_id=%s, document_id_1c=%s, product_id_1c=%s, date=%s. Удаляем дубликаты.",
                                    len(existing_purchases), user_id, document_id_1c, product_id_1c, purchase_date
                                )
                                # Оставляем первую (самую раннюю) запись, удаляем остальные
                                for dup in existing_purchases[1:]:
                                    await self.db.delete(dup)
                                    logger.debug(f"Удален дубликат покупки: id={dup.id}")
                            
                            existing_purchase = existing_purchases[0] if existing_purchases else None
                            
                            # Получаем сумму и количество
                            amount = purchase_data.get("Сумма", 0)
                            quantity = purchase_data.get("Количество", 1)
                            
                            # Конвертируем сумму в копейки (если в рублях)
                            # В 1С суммы обычно в рублях, но могут быть и в копейках
                            amount_kopecks = self._to_kopecks(amount)
                            
                            # Логируем для отладки (только первые несколько записей)
                            if stats["created"] + stats["updated"] < 3:
                                logger.debug(
                                    "Покупка: Сумма из 1С=%s, Конвертировано в копейки=%s, Количество=%s",
                                    amount, amount_kopecks, quantity
                                )
                            
                            price_kopecks = amount_kopecks // quantity if quantity > 0 else 0
                            
                            # Получаем данные товара из 1С и привязываем к нашему каталогу
                            product_id = None
                            product_article = None
                            product_name_from_1c = None
                            category_from_1c = None
                            brand_from_1c = None
                            
                            if product_id_1c:
                                try:
                                    # Получаем данные товара из 1С (название, артикул, бренд, категория)
                                    product_details = await onec_service.fetch_product_details(product_id_1c)
                                    
                                    if product_details:
                                        product_article = product_details.get("article") or product_details.get("code")
                                        product_name_from_1c = product_details.get("name")
                                        category_from_1c = product_details.get("category")
                                        brand_from_1c = product_details.get("brand")
                                    
                                    # Ищем товар в нашей БД по external_id (приоритет 1)
                                    stmt = select(Product).where(Product.external_id == product_id_1c)
                                    result = await self.db.execute(stmt)
                                    product = result.scalars().first()
                                    
                                    # Если не нашли по external_id, ищем по артикулу (приоритет 2)
                                    if not product and product_article:
                                        stmt = select(Product).where(
                                            or_(
                                                Product.article == product_article,
                                                Product.external_code == product_article
                                            )
                                        )
                                        result = await self.db.execute(stmt)
                                        product = result.scalars().first()
                                    
                                    if product:
                                        product_id = product.id
                                        # Обновляем артикул, если его не было
                                        if not product_article and product.article:
                                            product_article = product.article
                                    
                                except Exception as e:
                                    logger.warning(f"Ошибка при получении данных товара {product_id_1c}: {e}")
                                    # Продолжаем без привязки товара
                            
                            if existing_purchase:
                                # Обновляем существующую запись
                                existing_purchase.purchase_date = purchase_date
                                existing_purchase.quantity = quantity
                                existing_purchase.price = price_kopecks
                                existing_purchase.total_amount = amount_kopecks
                                existing_purchase.product_id = product_id
                                if product_article:
                                    existing_purchase.product_article = product_article
                                if product_name_from_1c:
                                    existing_purchase.product_name = product_name_from_1c
                                if category_from_1c:
                                    existing_purchase.category = category_from_1c
                                if brand_from_1c:
                                    existing_purchase.brand = brand_from_1c
                                stats["updated"] += 1
                            else:
                                # Создаем новую запись с защитой от дубликатов
                                # Используем try-except для обработки возможных дубликатов
                                # (если уникальный индекс уже создан в БД)
                                try:
                                    new_purchase = PurchaseHistory(
                                        user_id=user_id,
                                        purchase_date=purchase_date,
                                        document_id_1c=document_id_1c,
                                        store_id_1c=purchase_data.get("Склад_Key"),
                                        product_id=product_id,
                                        product_id_1c=product_id_1c,
                                        product_article=product_article,
                                        product_name=product_name_from_1c,
                                        quantity=quantity,
                                        price=price_kopecks,
                                        total_amount=amount_kopecks,
                                        category=category_from_1c,
                                        brand=brand_from_1c,
                                        sync_metadata=purchase_data
                                    )
                                    self.db.add(new_purchase)
                                    # Пытаемся зафлашить, чтобы проверить на дубликаты сразу
                                    await self.db.flush()
                                    stats["created"] += 1
                                except Exception as e:
                                    # Если возникла ошибка уникальности, значит запись уже существует
                                    # Обновляем существующую запись
                                    error_str = str(e).lower()
                                    if 'unique' in error_str or 'duplicate' in error_str:
                                        await self.db.rollback()
                                        
                                        # Повторно ищем запись (возможно, она была создана в другой транзакции)
                                        stmt = select(PurchaseHistory).where(and_(*conditions)).order_by(PurchaseHistory.created_at)
                                        result = await self.db.execute(stmt)
                                        existing_purchase = result.scalars().first()
                                        
                                        if existing_purchase:
                                            # Обновляем существующую запись
                                            existing_purchase.purchase_date = purchase_date
                                            existing_purchase.quantity = quantity
                                            existing_purchase.price = price_kopecks
                                            existing_purchase.total_amount = amount_kopecks
                                            existing_purchase.product_id = product_id
                                            if product_article:
                                                existing_purchase.product_article = product_article
                                            if product_name_from_1c:
                                                existing_purchase.product_name = product_name_from_1c
                                            if category_from_1c:
                                                existing_purchase.category = category_from_1c
                                            if brand_from_1c:
                                                existing_purchase.brand = brand_from_1c
                                            stats["updated"] += 1
                                            logger.debug(f"Обновлена существующая запись после конфликта: user_id={user_id}, document_id_1c={document_id_1c}")
                                        else:
                                            # Если запись не найдена, логируем ошибку
                                            logger.warning(f"Не удалось создать или обновить запись покупки: {e}")
                                            stats["errors"] += 1
                                    else:
                                        # Другая ошибка - пробрасываем дальше
                                        raise
                        
                        except Exception as e:
                            logger.error(f"Ошибка при обработке покупки: {e}")
                            stats["errors"] += 1
                            continue
                    
                    # После синхронизации покупок пересчитываем метрики
                    if purchases:
                        logger.debug(
                            "Синхронизировано %s покупок для пользователя %s. Пересчет метрик...",
                            len(purchases), user_id
                        )
                    await self.calculate_customer_metrics(user_id)
                    await self.update_customer_segment(user_id)
                    
                except Exception as e:
                    logger.error(f"Ошибка при синхронизации покупок для пользователя {user_id}: {e}")
                    stats["errors"] += 1
                    continue
            
            await self.db.commit()
            logger.info(
                "Синхронизация истории покупок завершена: создано=%s обновлено=%s ошибок=%s",
                stats["created"],
                stats["updated"],
                stats["errors"],
            )
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации истории покупок: {e}")
            await self.db.rollback()
            raise
        
        return stats
    
    async def calculate_customer_metrics(self, user_id: UUID) -> Dict[str, Any]:
        """
        Расчет метрик покупателя:
        - RFM анализ
        - Средний чек, LTV
        - Предпочтения по категориям/брендам
        """
        try:
            # Получаем пользователя с историей покупок
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return {}
            
            # Получаем историю покупок
            stmt = (
                select(PurchaseHistory)
                .options(selectinload(PurchaseHistory.product))
                .where(PurchaseHistory.user_id == user_id)
            )
            result = await self.db.execute(stmt)
            purchases = result.scalars().all()
            
            if not purchases:
                return {}
            
            # Базовые метрики
            total_purchases = len(purchases)
            total_spent = sum(p.total_amount for p in purchases)
            average_check = total_spent // total_purchases if total_purchases > 0 else 0

            # Нормализуем даты покупок к UTC (aware) для корректного сравнения
            normalized_dates = []
            for p in purchases:
                if not p.purchase_date:
                    continue
                dt_value = p.purchase_date
                if dt_value.tzinfo is None:
                    dt_value = dt_value.replace(tzinfo=timezone.utc)
                else:
                    dt_value = dt_value.astimezone(timezone.utc)
                normalized_dates.append(dt_value)

            last_purchase_date = max(normalized_dates) if normalized_dates else None
            
            # Обновляем пользователя
            user.total_purchases = total_purchases
            user.total_spent = total_spent
            user.average_check = average_check
            if last_purchase_date:
                user.last_purchase_date = last_purchase_date
            
            # RFM анализ
            analytics_service = CustomerAnalyticsService(self.db)
            rfm_score = await analytics_service.calculate_rfm_score(user_id, purchases)
            user.rfm_score = rfm_score
            
            # Предпочтения по категориям и брендам
            categories = {}
            brands = {}
            favorite_products = []  # Список ID товаров из каталога
            
            # Порог для упаковки: 5 рублей = 500 копеек
            PACKAGING_THRESHOLD = 500
            
            for purchase in purchases:
                # Пропускаем упаковку (товары дешевле 5₽)
                if purchase.total_amount < PACKAGING_THRESHOLD:
                    continue
                
                # Используем категорию и бренд из товара каталога, если товар привязан
                if purchase.product:
                    # Приоритет: данные из каталога
                    category = purchase.product.category or purchase.category
                    brand = purchase.product.brand or purchase.brand
                    if purchase.product_id:
                        favorite_products.append(str(purchase.product_id))
                else:
                    # Используем данные из покупки
                    category = purchase.category
                    brand = purchase.brand
                
                if category:
                    categories[category] = categories.get(category, 0) + purchase.total_amount
                if brand:
                    brands[brand] = brands.get(brand, 0) + purchase.total_amount
            
            # Сортируем и берем топ-5
            top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            top_brands = sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Уникальные товары (топ-20)
            unique_products = list(set(favorite_products))[:20]
            
            user.purchase_preferences = {
                "favorite_categories": [cat for cat, _ in top_categories],
                "favorite_brands": [brand for brand, _ in top_brands],
                "favorite_products": unique_products,  # ID товаров из каталога
                "category_amounts": {cat: amount for cat, amount in top_categories},
                "brand_amounts": {brand: amount for brand, amount in top_brands}
            }
            
            await self.db.commit()
            
            return {
                "total_purchases": total_purchases,
                "total_spent": total_spent,
                "average_check": average_check,
                "rfm_score": rfm_score,
                "purchase_preferences": user.purchase_preferences
            }
            
        except Exception as e:
            logger.error(f"Ошибка расчета метрик для пользователя {user_id}: {e}")
            await self.db.rollback()
            raise

    async def sync_loyalty_points(self, user_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Синхронизация баланса бонусов из 1С (AccumulationRegister_БонусныеБаллы).
        """
        stats = {
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }

        try:
            onec_service = await self._get_onec_service()

            if user_id:
                stmt = select(
                    User.id,
                    User.customer_id_1c,
                    User.discount_card_id_1c,
                    User.loyalty_points,
                ).where(User.id == user_id, User.is_customer == True)
            else:
                stmt = select(
                    User.id,
                    User.customer_id_1c,
                    User.discount_card_id_1c,
                    User.loyalty_points,
                ).where(User.is_customer == True)

            result = await self.db.execute(stmt)
            users = result.all()

            for user in users:
                # Используем значения из Row, чтобы избежать lazy loading
                user_id = user.id
                customer_id_1c = user.customer_id_1c
                discount_card_id_1c = user.discount_card_id_1c
                current_balance = int(user.loyalty_points or 0)
                
                if not customer_id_1c and not discount_card_id_1c:
                    stats["skipped"] += 1
                    continue

                try:
                    loyalty_info = await onec_service.fetch_loyalty_balance(
                        customer_key=customer_id_1c,
                        discount_card_key=discount_card_id_1c,
                    )
                    if not loyalty_info:
                        stats["skipped"] += 1
                        continue

                    balance = loyalty_info.get("balance")
                    source_id = loyalty_info.get("source_id")
                    if balance is None:
                        stats["skipped"] += 1
                        continue

                    balance = int(balance)

                    if balance == current_balance:
                        stats["skipped"] += 1
                        continue

                    delta = balance - current_balance
                    await self.db.execute(
                        update(User)
                        .where(User.id == user_id)
                        .values(loyalty_points=balance)
                    )

                    transaction = LoyaltyTransaction(
                        user_id=user_id,
                        transaction_type="sync_from_1c",
                        points=delta,
                        balance_after=balance,
                        reason="sync_from_1c",
                        description="Синхронизация баланса из 1С",
                        source="1c",
                        source_id=source_id,
                    )
                    self.db.add(transaction)
                    stats["updated"] += 1
                except Exception as e:
                    logger.error("Ошибка синхронизации бонусов для пользователя %s: %s", user_id, e)
                    stats["errors"] += 1
                    continue

            await self.db.commit()
            logger.info(
                "Синхронизация бонусов завершена: обновлено=%s пропущено=%s ошибок=%s",
                stats["updated"],
                stats["skipped"],
                stats["errors"],
            )
        except Exception as e:
            logger.error(f"Ошибка синхронизации бонусов: {e}")
            await self.db.rollback()
            raise

        return stats

    @staticmethod
    def _to_kopecks(amount: Any) -> int:
        """
        Конвертация суммы в копейки.
        В 1С суммы ВСЕГДА в рублях, поэтому всегда умножаем на 100.
        """
        if amount is None:
            return 0
        try:
            value = float(amount)
        except (TypeError, ValueError):
            return 0
        
        # Если значение 0, возвращаем 0
        if value == 0:
            return 0
        
        # В 1С суммы всегда в рублях - умножаем на 100 для получения копеек
        return int(round(value * 100))
    
    async def update_customer_segment(self, user_id: UUID) -> Optional[str]:
        """
        Обновление сегмента покупателя на основе метрик
        """
        try:
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user or not user.is_customer:
                return None
            
            # Простая логика сегментации (можно улучшить)
            segment = None
            
            if user.total_purchases == 0:
                segment = "New"
            elif user.rfm_score:
                r_score = user.rfm_score.get("r_score", 0)
                f_score = user.rfm_score.get("f_score", 0)
                m_score = user.rfm_score.get("m_score", 0)
                total_score = r_score + f_score + m_score
                
                if total_score >= 12:
                    segment = "VIP"
                elif total_score >= 8:
                    segment = "Active"
                elif total_score >= 5:
                    segment = "Regular"
                else:
                    # Проверяем давность последней покупки
                    if user.last_purchase_date:
                        # Нормализуем даты к UTC aware
                        now_utc = datetime.now(timezone.utc)
                        last_purchase = user.last_purchase_date
                        if last_purchase.tzinfo is None:
                            last_purchase = last_purchase.replace(tzinfo=timezone.utc)
                        else:
                            last_purchase = last_purchase.astimezone(timezone.utc)
                        
                        days_since_last = (now_utc - last_purchase).days
                        if days_since_last > 90:
                            segment = "Sleeping"
                        else:
                            segment = "Regular"
                    else:
                        segment = "Sleeping"
            else:
                # Если нет RFM, используем простые правила
                if user.total_purchases >= 10 and user.total_spent >= 5000000:  # 50,000 руб
                    segment = "VIP"
                elif user.total_purchases >= 5:
                    segment = "Active"
                elif user.total_purchases > 0:
                    segment = "Regular"
                else:
                    segment = "New"
            
            user.customer_segment = segment
            await self.db.commit()
            
            return segment
            
        except Exception as e:
            logger.error(f"Ошибка обновления сегмента для пользователя {user_id}: {e}")
            await self.db.rollback()
            return None
    
    @staticmethod
    def _determine_gender(name: Optional[str]) -> Optional[str]:
        """
        Определение пола клиента по имени (только по явным именам, без окончаний)
        
        Определяет пол ТОЛЬКО если имя явно присутствует в списке популярных имен.
        Не использует определение по окончаниям - это слишком ненадежно.
        Если имя не найдено в списке - возвращает None (пол определяется вручную в кабинете).
        
        Args:
            name: Полное имя клиента (формат: "Фамилия Имя" или "Фамилия Имя Отчество")
        
        Returns:
            "male", "female" или None если не удалось определить
        """
        if not name or not name.strip():
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
        
        # Популярные женские имена (расширенный список)
        female_names = {
            'анна', 'мария', 'елена', 'наталья', 'ольга', 'татьяна', 'ирина', 'екатерина',
            'светлана', 'юлия', 'анастасия', 'дарья', 'марина', 'людмила', 'валентина',
            'галина', 'надежда', 'виктория', 'любовь', 'валерия', 'алина',
            'кристина', 'полина', 'вероника', 'диана', 'майя', 'софия',
            'александра', 'василиса', 'милана', 'милена', 'алиса', 'эмилия', 'эмили',
            'виолетта', 'маргарита', 'елизавета', 'ксения', 'мирослава',
            'злата', 'ярослава', 'арина', 'карина', 'ангелина', 'дугма', 'нисо',
            'эмине', 'яна', 'лариса', 'раиса', 'тамара', 'зоя', 'лидия',
            # Дополнительные женские имена
            'ханум', 'лилия', 'влада', 'валерия', 'валерия', 'валерия'
        }
        
        # Популярные мужские имена (расширенный список)
        male_names = {
            'александр', 'дмитрий', 'максим', 'сергей', 'андрей', 'алексей', 'артем',
            'илья', 'кирилл', 'михаил', 'николай', 'матвей', 'роман', 'павел', 'владимир',
            'денис', 'тимофей', 'иван', 'евгений', 'даниил', 'данил', 'данила', 'арсений',
            'леонид', 'степан', 'владислав', 'игорь', 'семен', 'антон',
            'василий', 'виктор', 'юрий', 'олег', 'валерий', 'александр', 'дмитрий'
        }
        
        # Определяем пол ТОЛЬКО по списку имен (не по окончаниям!)
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
