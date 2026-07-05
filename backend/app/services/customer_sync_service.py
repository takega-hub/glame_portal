"""
Сервис синхронизации покупателей из 1С
"""
import logging
from typing import Optional, List, Dict, Any, Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
import os
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.product import Product
from app.models.store import Store
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.referral import ReferralAttribution, ReferralProgramMember
from app.services.onec_customers_service import OneCCustomersService
from app.services.onec_outbound_service import OneCOutboundService
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.services.loyalty_service import LoyaltyService
from app.services.sales_product_link_service import SalesProductLinkService
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category
from app.services.sales_record_filters import is_analytics_eligible_product
from app.services.referral_service import ReferralService, REFERRED_CLIENT_WELCOME_BONUS_POINTS
from app.agents.communication_agent import CommunicationAgent
from app.services.user_deletion_service import UserDeletionService

logger = logging.getLogger(__name__)


class CustomerSyncService:
    """Сервис синхронизации покупателей из 1С"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.onec_service = None
        self._communication_agent = None
    
    async def _get_onec_service(self) -> OneCCustomersService:
        """Получение или создание сервиса 1С"""
        if self.onec_service and (
            not getattr(self.onec_service, "client", None)
            or getattr(self.onec_service.client, "is_closed", False)
        ):
            self.onec_service = None
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
            "birth_dates_updated": 0,
            "errors": 0,
            "skipped": 0,
            "total_loaded": 0
        }
        
        try:
            onec_service = await self._get_onec_service()
            
            offset = 0
            total_loaded = 0
            batch_count = 0
            phones_from_onec: set[str] = set()
            
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

                    if load_all:
                        for card_data in cards:
                            phone_raw = card_data.get("КодКартыШтрихкод")
                            phone_norm = self._normalize_phone(phone_raw)
                            if phone_norm:
                                phones_from_onec.add(phone_norm)
                    
                    # Обрабатываем карты
                    batch_stats = await self._process_cards_batch(cards)
                    stats["created"] += batch_stats["created"]
                    stats["updated"] += batch_stats["updated"]
                    stats["birth_dates_updated"] += batch_stats["birth_dates_updated"]
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
            
            await self._delete_missing_customers_if_enabled(load_all=load_all, stats=stats, phones_from_onec=phones_from_onec)

            stats["total_loaded"] = total_loaded
            logger.info(f"Синхронизация завершена: загружено {total_loaded}, создано {stats['created']}, обновлено {stats['updated']}")
            print(f"\nСинхронизация завершена:")
            print(f"  Всего загружено: {total_loaded}")
            print(f"  Создано: {stats['created']}")
            print(f"  Обновлено: {stats['updated']}")
            print(f"  Дат рождения обновлено: {stats['birth_dates_updated']}")
            print(f"  Пропущено: {stats['skipped']}")
            print(f"  Ошибок: {stats['errors']}")
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации дисконтных карт: {e}")
            print(f"Ошибка синхронизации дисконтных карт: {e}")
            await self.db.rollback()
            stats["errors"] += 1
            raise
        
        return stats

    async def sync_referrals_by_code(
        self,
        referral_code: str,
        batch_size: int = 500,
        max_cards: int = 20000,
    ) -> Dict[str, Any]:
        """
        Ручная синхронизация покупателей из 1С по одному реферальному коду.
        Ищет код в email/контактных данных контрагента, затем использует общий
        пайплайн обработки карт, чтобы не расходилась логика начислений.
        """
        target_code = (referral_code or "").strip().upper()
        stats: Dict[str, Any] = {
            "created": 0,
            "updated": 0,
            "birth_dates_updated": 0,
            "errors": 0,
            "skipped": 0,
            "total_loaded": 0,
            "customers_loaded": 0,
            "matched": 0,
        }
        if not target_code:
            return stats

        onec_service = await self._get_onec_service()
        offset = 0
        loaded = 0
        customer_cache: Dict[str, Dict[str, Any]] = {}

        try:
            targeted_customers = await onec_service.fetch_customers_by_referral_code(target_code, limit=max_cards)
            if targeted_customers:
                for customer_data in targeted_customers:
                    _, _, found_code, _, _ = self._extract_customer_fields(customer_data, customer_data.get("Description"))
                    if (found_code or "").strip().upper() != target_code:
                        continue
                    phone = self._extract_customer_phone(customer_data)
                    card_data = await onec_service.find_discount_card_by_phone(phone) if phone else None
                    if card_data:
                        batch_stats = await self._process_cards_batch([card_data])
                    else:
                        batch_stats = await self._process_referral_customer_without_card(customer_data)
                    stats["created"] += batch_stats["created"]
                    stats["updated"] += batch_stats["updated"]
                    stats["birth_dates_updated"] += batch_stats["birth_dates_updated"]
                    stats["errors"] += batch_stats["errors"]
                    stats["skipped"] += batch_stats["skipped"]
                    stats["matched"] += 1
                stats["customers_loaded"] = len(targeted_customers)
                await self.db.commit()
                return stats

            while loaded < max_cards:
                current_batch_size = min(batch_size, max_cards - loaded)
                if current_batch_size <= 0:
                    break
                cards = await onec_service.fetch_discount_cards(limit=current_batch_size, offset=offset)
                if not cards:
                    break

                matched_cards: List[Dict[str, Any]] = []
                for card_data in cards:
                    customer_id_1c = card_data.get("ВладелецКарты_Key")
                    description = card_data.get("Description", "")
                    customer_data = None
                    if customer_id_1c:
                        if customer_id_1c not in customer_cache:
                            try:
                                customer_cache[customer_id_1c] = await onec_service.fetch_customer_details(customer_id_1c) or {}
                            except Exception as e:
                                logger.warning("Не удалось получить данные контрагента %s: %s", customer_id_1c, e)
                                customer_cache[customer_id_1c] = {}
                        customer_data = customer_cache.get(customer_id_1c) or None

                    _, _, found_code, _, _ = self._extract_customer_fields(customer_data, description)
                    if (found_code or "").strip().upper() == target_code:
                        matched_cards.append(card_data)

                if matched_cards:
                    batch_stats = await self._process_cards_batch(matched_cards)
                    stats["created"] += batch_stats["created"]
                    stats["updated"] += batch_stats["updated"]
                    stats["birth_dates_updated"] += batch_stats["birth_dates_updated"]
                    stats["errors"] += batch_stats["errors"]
                    stats["skipped"] += batch_stats["skipped"]
                    stats["matched"] += len(matched_cards)
                    await self.db.commit()

                loaded += len(cards)
                offset += len(cards)
                stats["total_loaded"] = loaded
                if len(cards) < current_batch_size:
                    break

            customer_offset = 0
            customers_loaded = 0
            seen_customer_ids: set[str] = set()
            while customers_loaded < max_cards:
                current_batch_size = min(batch_size, max_cards - customers_loaded)
                if current_batch_size <= 0:
                    break
                customers = await onec_service.fetch_customers(limit=current_batch_size, offset=customer_offset)
                if not customers:
                    break
                for customer_data in customers:
                    customer_id_1c = str(customer_data.get("Ref_Key") or "")
                    if customer_id_1c and customer_id_1c in seen_customer_ids:
                        continue
                    _, _, found_code, _, _ = self._extract_customer_fields(customer_data, customer_data.get("Description"))
                    if (found_code or "").strip().upper() != target_code:
                        continue
                    if customer_id_1c:
                        seen_customer_ids.add(customer_id_1c)
                    customer_stats = await self._process_referral_customer_without_card(customer_data)
                    stats["created"] += customer_stats["created"]
                    stats["updated"] += customer_stats["updated"]
                    stats["birth_dates_updated"] += customer_stats["birth_dates_updated"]
                    stats["errors"] += customer_stats["errors"]
                    stats["skipped"] += customer_stats["skipped"]
                    stats["matched"] += customer_stats["matched"]
                customers_loaded += len(customers)
                customer_offset += len(customers)
                stats["customers_loaded"] = customers_loaded
                if len(customers) < current_batch_size:
                    break

            await self.db.commit()
        except Exception:
            await self.db.rollback()
            stats["errors"] += 1
            raise
        finally:
            if onec_service:
                await onec_service.close()

        return stats

    async def _process_referral_customer_without_card(self, customer_data: Dict[str, Any]) -> Dict[str, int]:
        stats = {"created": 0, "updated": 0, "birth_dates_updated": 0, "errors": 0, "skipped": 0, "matched": 0}
        try:
            customer_id_1c = str(customer_data.get("Ref_Key") or "")
            phone = self._extract_customer_phone(customer_data)
            full_name, email, referral_code, city, birth_date = self._extract_customer_fields(
                customer_data,
                customer_data.get("Description"),
            )
            if not phone:
                stats["skipped"] += 1
                return stats

            existing_user = None
            if customer_id_1c:
                existing_user = (
                    await self.db.execute(select(User).where(User.customer_id_1c == customer_id_1c))
                ).scalar_one_or_none()
            if not existing_user:
                existing_user = (
                    await self.db.execute(select(User).where(User.phone == phone))
                ).scalar_one_or_none()

            if existing_user:
                existing_user.phone = phone
                existing_user.customer_id_1c = customer_id_1c or existing_user.customer_id_1c
                existing_user.is_customer = True
                existing_user.synced_at = datetime.utcnow()
                if not existing_user.role:
                    existing_user.role = "customer"
                if full_name and not existing_user.full_name:
                    existing_user.full_name = full_name
                if email and not existing_user.email:
                    existing_user.email = email
                if city:
                    existing_user.city = city
                if birth_date and existing_user.birth_date != birth_date:
                    existing_user.birth_date = birth_date
                    stats["birth_dates_updated"] += 1
                if referral_code:
                    await self._ensure_referral_from_onec_email(existing_user, referral_code)
                stats["updated"] += 1
            else:
                new_user = User(
                    phone=phone,
                    customer_id_1c=customer_id_1c or None,
                    is_customer=True,
                    role="customer",
                    synced_at=datetime.utcnow(),
                    full_name=full_name,
                    email=email,
                    city=city,
                    birth_date=birth_date,
                    gender=self._determine_gender(full_name) if full_name else None,
                    loyalty_points=0,
                    total_purchases=0,
                    total_spent=0,
                )
                self.db.add(new_user)
                await self.db.flush()
                if referral_code:
                    await self._ensure_referral_from_onec_email(new_user, referral_code)
                if birth_date:
                    stats["birth_dates_updated"] += 1
                stats["created"] += 1
            stats["matched"] += 1
        except Exception as e:
            logger.error("Ошибка при синхронизации контрагента по рефкоду %s: %s", customer_data.get("Ref_Key"), e)
            stats["errors"] += 1
        return stats

    @staticmethod
    def _extract_customer_phone(customer_data: Optional[Dict[str, Any]]) -> str:
        if not customer_data:
            return ""
        direct_fields = [
            "НомерТелефонаДляПоиска",
            "Телефон",
            "Phone",
            "ОсновнойТелефон",
            "МобильныйТелефон",
        ]
        for field in direct_fields:
            normalized = CustomerSyncService._normalize_phone(customer_data.get(field))
            if normalized:
                return normalized

        contact_info = customer_data.get("КонтактнаяИнформация") or customer_data.get("ContactInfo")
        contact_items = contact_info if isinstance(contact_info, list) else [contact_info] if contact_info else []
        for contact in contact_items:
            if not isinstance(contact, dict):
                continue
            contact_type = str(contact.get("Тип") or contact.get("Type") or "").lower()
            if contact_type and "тел" not in contact_type and "phone" not in contact_type:
                continue
            candidates = [
                contact.get("НомерТелефона"),
                contact.get("НомерТелефонаБезКодов"),
                contact.get("Представление"),
                contact.get("Presentation"),
                contact.get("Значение"),
                contact.get("Value"),
            ]
            for candidate in candidates:
                normalized = CustomerSyncService._normalize_phone(candidate)
                if normalized:
                    return normalized
        return ""

    @staticmethod
    def _normalize_phone(phone: Optional[str]) -> str:
        if not phone:
            return ""
        digits = re.sub(r"\D", "", str(phone))
        if len(digits) == 11 and digits.startswith("8"):
            return "7" + digits[1:]
        if len(digits) == 10:
            return "7" + digits
        return digits

    async def _delete_missing_customers_if_enabled(self, load_all: bool, stats: Dict[str, Any], phones_from_onec: set[str]) -> None:
        enabled = os.getenv("CUSTOMER_SYNC_DELETE_MISSING", "false").strip().lower() in ("1", "true", "yes")
        require_no_errors = os.getenv("CUSTOMER_SYNC_DELETE_MISSING_REQUIRE_NO_ERRORS", "true").strip().lower() in ("1", "true", "yes")
        if not enabled:
            return
        if not load_all:
            return
        if require_no_errors and int(stats.get("errors", 0) or 0) > 0:
            logger.warning("Удаление отсутствующих клиентов пропущено из-за ошибок синхронизации (errors=%s)", stats.get("errors"))
            return
        if not phones_from_onec:
            logger.warning("Удаление отсутствующих клиентов пропущено: список телефонов из 1С пуст")
            return

        stmt = select(User).where(User.is_customer == True).where(User.phone.isnot(None))
        result = await self.db.execute(stmt)
        users = result.scalars().all()

        deletion = UserDeletionService(self.db)
        deleted = 0
        for user in users:
            phone_norm = self._normalize_phone(getattr(user, "phone", None))
            if not phone_norm:
                continue
            if phone_norm not in phones_from_onec:
                try:
                    await deletion.delete_user_by_id(user.id)
                    deleted += 1
                except Exception as e:
                    logger.error("Не удалось удалить пользователя %s (%s): %s", user.id, phone_norm, e)

        if deleted:
            logger.info("Удалено пользователей, отсутствующих в 1С: %s", deleted)
    
    async def _process_cards_batch(self, cards: List[Dict[str, Any]]) -> Dict[str, int]:
        """Обработка батча карт"""
        batch_stats = {
            "created": 0,
            "updated": 0,
            "birth_dates_updated": 0,
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

                full_name, email, referral_code, city, birth_date = self._extract_customer_fields(customer_data, description)
                
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
                    if birth_date and existing_user.birth_date != birth_date:
                        existing_user.birth_date = birth_date
                        batch_stats["birth_dates_updated"] += 1
                    if referral_code:
                        await self._ensure_referral_from_onec_email(existing_user, referral_code)
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
                        birth_date=birth_date,
                        gender=gender,
                        loyalty_points=0,
                        total_purchases=0,
                        total_spent=0
                    )
                    self.db.add(new_user)
                    await self.db.flush()
                    if referral_code:
                        await self._ensure_referral_from_onec_email(new_user, referral_code)
                    if birth_date:
                        batch_stats["birth_dates_updated"] += 1
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
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[date]]:
        """
        Извлекает поля покупателя из данных 1С.
        Возвращает: (full_name, email, referral_code, city, birth_date)
        """
        if not customer_data:
            _, referral_code = CustomerSyncService._split_email_or_referral_code(description)
            return (description or None), None, referral_code, None, None

        name_fields = [
            "ФИО",
            "НаименованиеПолное",
            "ПолноеНаименование",
            "Description",
            "Наименование",
            "Имя",
        ]
        email_fields = [
            "АдресЭПДляПоиска",
            "Email",
            "ЭлектроннаяПочта",
            "АдресЭлектроннойПочты",
            "EmailAddress",
        ]
        birth_date_fields = [
            "ДатаРождения",
            "Дата_Рождения",
            "BirthDate",
            "Birthday",
        ]

        full_name = None
        for field in name_fields:
            value = customer_data.get(field)
            if value:
                full_name = value
                break

        email = None
        referral_code = None
        for field in email_fields:
            value = customer_data.get(field)
            if value:
                email, referral_code = CustomerSyncService._split_email_or_referral_code(value)
                break

        contact_info = customer_data.get("КонтактнаяИнформация") or customer_data.get("ContactInfo")
        if not email and not referral_code and contact_info:
            contact_items = contact_info if isinstance(contact_info, list) else [contact_info]
            for contact in contact_items:
                if not isinstance(contact, dict):
                    continue
                contact_type = str(contact.get("Тип") or contact.get("Type") or "").lower()
                if "почт" not in contact_type and "email" not in contact_type and "адресэп" not in contact_type:
                    continue
                value = (
                    contact.get("АдресЭП")
                    or contact.get("Email")
                    or contact.get("Значение")
                    or contact.get("Представление")
                    or contact.get("Presentation")
                )
                email, referral_code = CustomerSyncService._split_email_or_referral_code(value)
                if email or referral_code:
                    break

        if not referral_code:
            referral_source_fields = [
                "АдресЭПДляПоиска",
                "Комментарий",
                "Comment",
                "Comments",
                "Description",
                "Наименование",
                "НаименованиеПолное",
                "ПолноеНаименование",
            ]
            for field in referral_source_fields:
                _, referral_code = CustomerSyncService._split_email_or_referral_code(customer_data.get(field))
                if referral_code:
                    break
        if not referral_code and description:
            _, referral_code = CustomerSyncService._split_email_or_referral_code(description)

        if not full_name:
            full_name = description or None

        birth_date = None
        for field in birth_date_fields:
            birth_date = CustomerSyncService._parse_birth_date(customer_data.get(field))
            if birth_date:
                break

        # Извлекаем город из адреса
        city = None
        try:
            # Логируем доступные поля для отладки
            logger.debug(f"Поля контрагента для извлечения города: {list(customer_data.keys())[:20]}")

            # ПРИОРИТЕТ 1: Прямые поля для города
            city = customer_data.get("Город") or customer_data.get("City") or customer_data.get("НаселенныйПункт")

            # ПРИОРИТЕТ 2: Пробуем разные варианты структуры адреса
            if not city:
                address_data = customer_data.get("Состав") or customer_data.get("Адрес") or customer_data.get("Address")

                if address_data:
                    # Если это словарь с вложенной структурой
                    if isinstance(address_data, dict):
                        # Пробуем найти АдресРФ
                        address_rf = address_data.get("АдресРФ") or address_data.get("Адрес")
                        if address_rf and isinstance(address_rf, dict):
                            # Ищем явные поля города
                            city = (
                                address_rf.get("Город")
                                or address_rf.get("City")
                                or address_rf.get("НаселенныйПункт")
                            )
                        # Если нет вложенности, проверяем прямые поля города
                        if not city:
                            city = (
                                address_data.get("Город")
                                or address_data.get("City")
                                or address_data.get("НаселенныйПункт")
                            )
                    # Если это список, берем первый элемент
                    elif isinstance(address_data, list) and len(address_data) > 0:
                        first_item = address_data[0]
                        if isinstance(first_item, dict):
                            address_rf = first_item.get("АдресРФ") or first_item.get("Адрес")
                            if address_rf and isinstance(address_rf, dict):
                                city = (
                                    address_rf.get("Город")
                                    or address_rf.get("City")
                                    or address_rf.get("НаселенныйПункт")
                                )
                            if not city:
                                city = (
                                    first_item.get("Город")
                                    or first_item.get("City")
                                    or first_item.get("НаселенныйПункт")
                                )

            # ПРИОРИТЕТ 3: Поиск в контактной информации (КонтактнаяИнформация)
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
                                    # Берем только явные поля города
                                    city = ci.get("Город") or ci.get("City")
                                    if not city:
                                        # Пытаемся извлечь город из представления адреса через шаблон
                                        presentation = ci.get("Представление") or ci.get("Presentation")
                                        if isinstance(presentation, str):
                                            # Ищем подстроки вида 'г. <Название>' или 'город <Название>'
                                            import re
                                            m = re.search(r"(?:г\.?|город)\s+([А-ЯЁA-Z][а-яёa-z\- ]+)", presentation)
                                            if m:
                                                city_candidate = m.group(1).strip()
                                                if city_candidate:
                                                    city = city_candidate
                                    if city:
                                        logger.info(f"Город найден в контактной информации: {city}")
                                        break
                    elif isinstance(contact_info, dict):
                        city = contact_info.get("Город") or contact_info.get("City")

            # ПРИОРИТЕТ 4: Поиск города в строке Представление/Комментарий
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

        return full_name, email, referral_code, city, birth_date

    @staticmethod
    def _split_email_or_referral_code(value: Any) -> tuple[Optional[str], Optional[str]]:
        raw = str(value or "").strip()
        if not raw:
            return None, None
        if "@" in raw:
            local, _, domain = raw.partition("@")
            domain_norm = domain.strip().lower()
            local_norm = local.strip().upper().removeprefix("REF:").removeprefix("REF=").strip()
            if domain_norm in {"ref.glame", "ref.glamejewelry.ru", "partner.glamejewelry.ru"}:
                match = re.fullmatch(r"([A-ZА-Я0-9]{5,32})(?:[+._-].*)?", local_norm)
                if match:
                    return None, match.group(1)
            return raw.lower(), None
        candidate = raw.upper().removeprefix("REF:").removeprefix("REF=").strip()
        if re.fullmatch(r"[A-ZА-Я0-9]{5,32}", candidate):
            return None, candidate
        return None, None

    async def _ensure_referral_from_onec_email(self, user: User, referral_code: str) -> None:
        code_value = (referral_code or "").strip().upper()
        if not code_value or not getattr(user, "id", None):
            return

        service = ReferralService(self.db)
        code = await service.validate_code(code_value)
        if code is None:
            logger.warning("Реферальный код из поля почты 1С не найден: %s", code_value)
            return

        member = (
            await self.db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == code.member_id))
        ).scalar_one_or_none()
        if member is None or member.status != "active" or member.user_id == user.id:
            return

        existing = (
            await self.db.execute(
                select(ReferralAttribution).where(
                    ReferralAttribution.referee_user_id == user.id,
                    ReferralAttribution.status.in_(["pending", "active"]),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            attribution = ReferralAttribution(
                referrer_member_id=member.id,
                referral_code_id=code.id,
                referee_user_id=user.id,
                status="pending",
                source="onec_rmk_email",
                meta={"field": "email", "raw_referral_code": code_value},
            )
            code.usage_count = int(code.usage_count or 0) + 1
            self.db.add(attribution)
        elif existing.referrer_member_id != member.id:
            logger.warning("Покупатель %s уже привязан к другому партнеру", user.id)
            return

        source_id = f"referral_welcome:{user.id}:{code.code}"
        existing_bonus = (
            await self.db.execute(select(LoyaltyTransaction).where(LoyaltyTransaction.source_id == source_id))
        ).scalar_one_or_none()
        if existing_bonus is None:
            await LoyaltyService(self.db).earn_points(
                user_id=user.id,
                points=REFERRED_CLIENT_WELCOME_BONUS_POINTS,
                reason="referral_welcome",
                metadata={"description": "Бонус за регистрацию по реферальному коду", "referral_code": code.code},
                source="platform",
                source_id=source_id,
            )
        await self._ensure_referral_welcome_bonus_in_1c(user, code.code, source_id)

    async def _ensure_referral_welcome_bonus_in_1c(self, user: User, referral_code: str, source_id: str) -> None:
        discount_card_id = getattr(user, "discount_card_id_1c", None)
        if not discount_card_id:
            return
        bonus_program_key = os.getenv("ONEC_BONUS_PROGRAM_KEY")
        if not bonus_program_key:
            return
        analytics_key = os.getenv(
            "ONEC_WELCOME_BONUS_ANALYTICS_KEY",
            "e6881e68-cdf4-11f0-85a1-fa163e4cc04e",
        ).strip() or None
        expires_days = int(os.getenv("ONEC_WELCOME_BONUS_EXPIRES_DAYS", "365"))
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_days)).replace(microsecond=0).isoformat()
        try:
            async with OneCOutboundService() as onec:
                existing_doc = await onec.find_welcome_bonus_doc(source_id)
                if existing_doc:
                    doc_ref = str(existing_doc.get("Ref_Key") or "")
                    if doc_ref:
                        await onec.unpost_welcome_bonus_doc(doc_ref)
                        await onec.update_welcome_bonus_doc(
                            doc_ref_key=doc_ref,
                            bonus_program_key=bonus_program_key,
                            card_ref_key=str(discount_card_id),
                            points=REFERRED_CLIENT_WELCOME_BONUS_POINTS,
                            comment=source_id,
                            analytics_key=analytics_key,
                            expires_at=expires_at,
                        )
                        await onec.post_welcome_bonus_doc(doc_ref)
                    return
                created = await onec.create_welcome_bonus_doc(
                    bonus_program_key=bonus_program_key,
                    card_ref_key=str(discount_card_id),
                    points=REFERRED_CLIENT_WELCOME_BONUS_POINTS,
                    comment=source_id,
                    analytics_key=analytics_key,
                    expires_at=expires_at,
                )
                doc_ref = str(created.get("Ref_Key") or "")
                if doc_ref:
                    await onec.post_welcome_bonus_doc(doc_ref)
        except Exception as e:
            logger.warning(
                "Не удалось начислить реферальные приветственные бонусы в 1С для %s (%s): %s",
                getattr(user, "phone", None),
                referral_code,
                e,
            )

    @staticmethod
    def _parse_birth_date(value: Any) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, datetime):
            parsed = value.date()
        elif isinstance(value, date):
            parsed = value
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    parsed = date.fromisoformat(raw[:10])
                except ValueError:
                    logger.warning("Не удалось разобрать дату рождения из 1С: %s", value)
                    return None
        else:
            return None

        if parsed.year <= 1900:
            return None
        return parsed
    
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
                                    await ReferralService(self.db).ensure_commission_for_purchase(
                                        referee_user_id=user_id,
                                        purchase=existing_purchase,
                                    )
                                    stats["updated"] = stats.get("updated", 0) + 1
                                else:
                                    stats["skipped"] += 1
                                continue
                            
                            # Получаем данные товара
                            product_article = None
                            product_barcode = None
                            glame_product_id = None
                            product_name_from_1c = purchase_data.get("Номенклатура_Description")
                            category_from_1c = purchase_data.get("Номенклатура_Категория")
                            brand_from_1c = purchase_data.get("Номенклатура_Бренд")
                            
                            if product_id_1c:
                                try:
                                    product_details = await onec_service.fetch_product_details(product_id_1c)
                                    if product_details:
                                        product_article = product_details.get("article") or product_details.get("code")
                                        product_barcode = product_details.get("barcode")
                                        if not product_name_from_1c:
                                            product_name_from_1c = product_details.get("name")
                                        if not category_from_1c:
                                            category_from_1c = product_details.get("category")
                                        if not brand_from_1c:
                                            brand_from_1c = product_details.get("brand")
                                        
                                        # Ищем товар в нашем каталоге
                                        if product_article or product_barcode:
                                            product_conditions = [Product.external_id == product_id_1c]
                                            if product_article:
                                                product_conditions.extend([
                                                    Product.article == product_article,
                                                    Product.external_code == product_article,
                                                ])
                                            if product_barcode:
                                                product_conditions.append(Product.barcode == product_barcode)
                                            stmt = select(Product).where(
                                                or_(*product_conditions)
                                            ).limit(1)
                                            result = await self.db.execute(stmt)
                                            product = result.scalars().first()
                                            if product:
                                                glame_product_id = product.id
                                except Exception as e:
                                    logger.warning(f"Не удалось получить данные товара {product_id_1c}: {e}")

                            raw_category_from_1c = category_from_1c
                            category_from_1c = derive_purchase_category(product_name_from_1c, raw_category_from_1c)
                            brand_from_1c = derive_purchase_brand(product_name_from_1c, brand_from_1c, raw_category_from_1c)
                            
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
                                await ReferralService(self.db).ensure_commission_for_purchase(
                                    referee_user_id=user_id,
                                    purchase=new_purchase,
                                )
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
                                            await ReferralService(self.db).ensure_commission_for_purchase(
                                                referee_user_id=user_id,
                                                purchase=existing_purchase,
                                            )
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
        days: int = 365,
        prefer_discount_card: bool = False,
    ) -> Dict[str, Any]:
        """
        Синхронизация истории покупок из 1С
        Из AccumulationRegister_Продажи_RecordType и AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType
        """
        stats = {
            "created": 0,
            "updated": 0,
            "errors": 0,
            "linked_products": 0,
        }
        target_user_id = user_id
        
        try:
            onec_service = await self._get_onec_service()
            product_cache: Dict[str, Dict[str, Any]] = {}
            
            # Определяем период
            # 1С хранит Period без таймзоны и может отдавать локальное время магазина.
            # Небольшой запас вперед не теряет сегодняшние продажи, которые в UTC
            # выглядят как будущие.
            end_date = datetime.now(timezone.utc) + timedelta(days=1)
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

                    if prefer_discount_card and customer_id_1c:
                        try:
                            purchases = await onec_service.get_customer_purchases(
                                customer_key=customer_id_1c,
                                start_date=start_date,
                                end_date=end_date,
                                limit=10000,
                            )
                            source_name = "AccumulationRegister_Продажи_RecordType by Контрагент_Key"
                            logger.debug(
                                "Получено %s продаж по контрагенту %s за период %s - %s",
                                len(purchases),
                                customer_id_1c,
                                start_date.date(),
                                end_date.date(),
                            )
                        except Exception as e:
                            logger.error(
                                "Не удалось получить продажи по контрагенту %s: %s",
                                customer_id_1c,
                                e,
                            )
                            purchases = []

                    if not purchases and prefer_discount_card and discount_card_id_1c and not customer_id_1c:
                        try:
                            purchases = await onec_service.fetch_sales_by_discount_card(
                                discount_card_key=discount_card_id_1c,
                                start_date=start_date,
                                end_date=end_date,
                                limit=10000,
                            )
                            source_name = "AccumulationRegister_Продажи by ДисконтнаяКарта_Key"
                            logger.debug(
                                "Получено %s продаж по карте %s за период %s - %s",
                                len(purchases),
                                discount_card_id_1c,
                                start_date.date(),
                                end_date.date(),
                            )
                        except Exception as e:
                            logger.error(
                                "Не удалось получить продажи по карте %s: %s",
                                discount_card_id_1c,
                                e,
                            )
                            purchases = []
                    
                    # Используем AccumulationRegister_Продажи с фильтрацией по Контрагент_Key
                    # Это работает без ошибки AUTOORDER в 1С Fresh
                    if not purchases and customer_id_1c and not prefer_discount_card:
                        try:
                            purchases = await onec_service.get_customer_purchases(
                                customer_key=customer_id_1c,
                                start_date=start_date,
                                end_date=end_date,
                                limit=10000,
                            )
                            source_name = "AccumulationRegister_Продажи_RecordType"
                            
                            # Фильтрация "ночных" отчетов (дубликатов из налоговых отчетов)
                            # Пользователи жалуются на дубликаты с временем около 00:00 и без магазина
                            # Обычно это Document_ОтчетОРозничныхПродажах
                            filtered_purchases = []
                            filtered_count = 0
                            
                            for p in purchases:
                                try:
                                    # Проверяем тип документа
                                    recorder_type = str(p.get("Recorder_Type", "") or "")
                                    is_report = "ОтчетОРозничныхПродажах" in recorder_type
                                    
                                    # Проверяем наличие склада
                                    store_key = p.get("Склад_Key")
                                    
                                    # Проверяем время (ночное время 20:00 - 05:00 UTC)
                                    is_night = False
                                    date_str = p.get("Period")
                                    if date_str:
                                        try:
                                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                                            h = dt.hour
                                            # 20:00-05:00 UTC = 23:00-08:00 MSK
                                            if h >= 20 or h <= 5:
                                                is_night = True
                                        except Exception:
                                            pass
                                    
                                    # Условие фильтрации: Отчет + (Нет склада ИЛИ Ночь)
                                    if is_report and (not store_key or is_night):
                                        filtered_count += 1
                                        continue
                                        
                                    filtered_purchases.append(p)
                                except Exception:
                                    filtered_purchases.append(p)
                            
                            if filtered_count > 0:
                                logger.info(
                                    "Отфильтровано %s вероятных дубликатов (ночные отчеты)",
                                    filtered_count
                                )
                                purchases = filtered_purchases

                            logger.debug(
                                "Получено %s продаж для контрагента %s за период %s - %s (источник: %s)",
                                len(purchases),
                                customer_id_1c,
                                start_date.date(),
                                end_date.date(),
                                source_name
                            )
                        except Exception as e:
                            logger.error(
                                "Не удалось получить продажи для контрагента %s: %s",
                                customer_id_1c,
                                e,
                            )
                            purchases = []

                    if not purchases and discount_card_id_1c and not (prefer_discount_card and customer_id_1c):
                        try:
                            purchases = await onec_service.fetch_sales_by_discount_card(
                                discount_card_key=discount_card_id_1c,
                                start_date=start_date,
                                end_date=end_date,
                                limit=10000,
                            )
                            source_name = "AccumulationRegister_Продажи by ДисконтнаяКарта_Key"
                            logger.debug(
                                "Получено %s продаж по карте %s за период %s - %s",
                                len(purchases),
                                discount_card_id_1c,
                                start_date.date(),
                                end_date.date(),
                            )
                        except Exception as e:
                            logger.error(
                                "Не удалось получить продажи по карте %s: %s",
                                discount_card_id_1c,
                                e,
                            )
                            purchases = []
                    
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
                            product_barcode = None
                            product_name_from_1c = None
                            category_from_1c = None
                            brand_from_1c = None
                            
                            if product_id_1c:
                                try:
                                    # Получаем данные товара из 1С (название, артикул, бренд, категория)
                                    product_details = product_cache.get(product_id_1c)
                                    if not product_details:
                                        product_details = await onec_service.fetch_product_details(product_id_1c)
                                        if product_details:
                                            product_cache[product_id_1c] = product_details
                                    
                                    if product_details:
                                        product_article = product_details.get("article") or product_details.get("code")
                                        product_barcode = product_details.get("barcode")
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

                                    if not product and product_barcode:
                                        stmt = select(Product).where(Product.barcode == product_barcode)
                                        result = await self.db.execute(stmt)
                                        product = result.scalars().first()
                                    
                                    if product:
                                        product_id = product.id
                                        # Обновляем артикул, если его не было
                                        if not product_article and product.article:
                                            product_article = product.article
                                        product_name_from_1c = product.name or product_name_from_1c
                                        category_from_1c = product.category or category_from_1c
                                        brand_from_1c = product.brand or brand_from_1c
                                    
                                except Exception as e:
                                    logger.warning(f"Ошибка при получении данных товара {product_id_1c}: {e}")
                                    # Продолжаем без привязки товара

                            raw_category_from_1c = category_from_1c
                            category_from_1c = derive_purchase_category(product_name_from_1c, raw_category_from_1c)
                            brand_from_1c = derive_purchase_brand(product_name_from_1c, brand_from_1c, raw_category_from_1c)
                            
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
                                await ReferralService(self.db).ensure_commission_for_purchase(
                                    referee_user_id=user_id,
                                    purchase=existing_purchase,
                                )
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
                                    await ReferralService(self.db).ensure_commission_for_purchase(
                                        referee_user_id=user_id,
                                        purchase=new_purchase,
                                    )
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
                                            await ReferralService(self.db).ensure_commission_for_purchase(
                                                referee_user_id=user_id,
                                                purchase=existing_purchase,
                                            )
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
            linked_count = await self.backfill_purchase_product_links(user_id=target_user_id)
            stats["linked_products"] = linked_count
            logger.info(
                "Синхронизация истории покупок завершена: создано=%s обновлено=%s связаны_товары=%s ошибок=%s",
                stats["created"],
                stats["updated"],
                stats["linked_products"],
                stats["errors"],
            )
            
        except Exception as e:
            logger.error(f"Ошибка синхронизации истории покупок: {e}")
            await self.db.rollback()
            raise
        
        return stats

    async def backfill_purchase_product_links(
        self,
        user_id: Optional[UUID] = None,
        limit: int = 200000,
    ) -> int:
        """Досопоставление purchase_history с каталогом products."""
        linker = SalesProductLinkService(self.db)
        return await linker.backfill_missing_purchase_product_links(
            user_id=str(user_id) if user_id else None,
            limit=limit,
        )
    
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

            PACKAGING_THRESHOLD = 500
            store_ids = {p.store_id_1c for p in purchases if p.store_id_1c}
            valid_store_ids: set = set()
            if store_ids:
                stores_stmt = select(Store.external_id).where(Store.external_id.in_(list(store_ids)))
                stores_rs = await self.db.execute(stores_stmt)
                valid_store_ids = {row[0] for row in stores_rs.fetchall() if row and row[0]}

            def _is_transfer(ph: PurchaseHistory) -> bool:
                try:
                    name = (ph.product_name or "").lower()
                    if "перенос" in name:
                        return True
                    meta = ph.sync_metadata or {}
                    rt = str(meta.get("Recorder_Type", "")).lower()
                    if "вводначальныхостатков" in rt or "перенос" in rt:
                        return True
                except Exception:
                    pass
                return False

            def _dedup_key(p: PurchaseHistory):
                doc = p.document_id_1c or ""
                prod = p.product_id_1c or (p.product_article or "")
                ts = p.purchase_date.isoformat() if p.purchase_date else ""
                amt = p.total_amount or 0
                return (doc, prod, ts, amt)

            filtered = [
                p for p in purchases
                if is_analytics_eligible_product(
                    product_name=p.product_name,
                    product_category=p.category,
                    product_article=p.product_article,
                    product_id=p.product_id_1c or p.product_id,
                    total_amount_kopecks=p.total_amount or 0,
                )
            ]
            dedup_map: Dict[Any, PurchaseHistory] = {}
            for p in filtered:
                key = _dedup_key(p)
                cur = dedup_map.get(key)
                prefer_new = False
                if cur is None:
                    prefer_new = True
                else:
                    if (not getattr(cur, "store_id_1c", None)) and getattr(p, "store_id_1c", None):
                        prefer_new = True
                if prefer_new:
                    dedup_map[key] = p

            deduped: List[PurchaseHistory] = []
            for p in dedup_map.values():
                has_valid_store = bool(p.store_id_1c and (p.store_id_1c in valid_store_ids))
                if has_valid_store or _is_transfer(p):
                    deduped.append(p)

            total_purchases = len(deduped)
            total_spent = sum((p.total_amount or 0) for p in deduped)
            average_check = total_spent // total_purchases if total_purchases > 0 else 0

            # Нормализуем даты покупок к UTC (aware) для корректного сравнения
            normalized_dates = []
            for p in deduped:
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
            
            # Обновляем предпочитаемый магазин и город (без коммита, он будет ниже)
            await analytics_service.refresh_preferred_store_by_count(user_id, commit=False)
            
            # Предпочтения по категориям и брендам
            categories = {}
            brands = {}
            favorite_products = []  # Список ID товаров из каталога
            
            # Порог для упаковки: 5 рублей = 500 копеек
            PACKAGING_THRESHOLD = 500
            
            for purchase in purchases:
                if not is_analytics_eligible_product(
                    product_name=purchase.product_name,
                    product_category=purchase.category,
                    product_article=purchase.product_article,
                    product_id=purchase.product_id_1c or purchase.product_id,
                    total_amount_kopecks=purchase.total_amount or 0,
                ):
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
            'ханум', 'лилия', 'влада', 'варвара', 'ева', 'ульяна', 'кира', 'вера',
            'евгения', 'олеся', 'альбина', 'нелли', 'рената', 'элина', 'эльвира',
            'айгуль', 'гульнара', 'зульфия', 'лейла', 'фатима', 'камилла',
            'дана', 'амина', 'зарина', 'сабина', 'роза', 'алла', 'инна', 'оксана',
            'жанна', 'анжела', 'снежана', 'лада', 'нинель', 'нонна', 'эвелина',
            'илона', 'диляра', 'дина', 'наталия', 'эльмира', 'аделина', 'асия', 'лия',
            'сафия', 'николь', 'эмилия', 'стефания', 'агата', 'аврора', 'милла',
            'юлианна', 'аида', 'мева', 'анжелика', 'сандра'
        }
        
        # Популярные мужские имена (расширенный список)
        male_names = {
            'александр', 'дмитрий', 'максим', 'сергей', 'андрей', 'алексей', 'артем',
            'илья', 'кирилл', 'михаил', 'николай', 'матвей', 'роман', 'павел', 'владимир',
            'денис', 'тимофей', 'иван', 'евгений', 'даниил', 'данил', 'данила', 'арсений',
            'леонид', 'степан', 'владислав', 'игорь', 'семен', 'антон',
            'василий', 'виктор', 'юрий', 'олег', 'валерий', 'григорий', 'анатолий',
            'вячеслав', 'георгий', 'егор', 'константин', 'лев', 'марк', 'никита',
            'петр', 'станислав', 'федор', 'эдуард', 'ярослав', 'артур', 'тимур',
            'руслан', 'марат', 'дамир', 'ильдар', 'рамиль', 'альберт', 'роберт',
            'герман', 'глеб', 'давид', 'платон', 'савелий', 'богдан', 'мирон',
            'захар', 'макар', 'елисей', 'гордей', 'демид', 'артемий', 'святослав',
            'всеволод', 'борислав', 'вадим', 'валентин', 'виталий', 'геннадий', 'борис'
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
