import logging
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.onec_user_sync_job import OneCUserSyncJob
from app.models.referral import ReferralProgramMember
from app.services.onec_customers_service import OneCCustomersService
from app.services.onec_outbound_service import OneCOutboundService
from app.services.onec_user_registration_payload import OneCUserRegistrationPayload


logger = logging.getLogger(__name__)
REFERRAL_LINK_PROPERTY_KEY = "b126c95a-72ee-11f1-876b-fa163e4cc04e"


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OneCUserSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue_registration(self, user: User, payload: OneCUserRegistrationPayload) -> Optional[OneCUserSyncJob]:
        if not _env_bool("ONEC_OUTBOUND_SYNC_ENABLED", "false"):
            return None

        job = OneCUserSyncJob(
            user_id=user.id,
            status="pending",
            attempts=0,
            max_attempts=int(os.getenv("ONEC_OUTBOUND_MAX_ATTEMPTS", "8")),
            next_attempt_at=_utcnow(),
            request_payload=payload.to_job_payload(),
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def process_job(self, job_id) -> OneCUserSyncJob:
        result = await self.db.execute(select(OneCUserSyncJob).where(OneCUserSyncJob.id == job_id))
        job = result.scalar_one()

        if job.status == "success":
            return job

        now = _utcnow()
        job.status = "in_progress"
        job.last_attempt_at = now
        job.attempts = int(job.attempts or 0) + 1
        job.last_error = None
        job.response_payload = None
        await self.db.commit()

        try:
            await self._sync_user(job)
            job.status = "success"
            job.next_attempt_at = None
            await self._sync_referral_member_status(job, status="success")
            await self.db.commit()
            await self.db.refresh(job)
            return job
        except Exception as e:
            job.last_error = str(e)[:2000]
            should_retry = job.attempts < int(job.max_attempts or 0)
            if should_retry:
                job.status = "pending"
                job.next_attempt_at = self._calc_next_attempt_at(job.attempts)
            else:
                job.status = "failed"
                job.next_attempt_at = None
            await self._sync_referral_member_status(job, status=job.status, error=job.last_error)
            await self.db.commit()
            await self.db.refresh(job)
            return job

    def _calc_next_attempt_at(self, attempts: int) -> datetime:
        base_seconds = int(os.getenv("ONEC_OUTBOUND_RETRY_BASE_SECONDS", "30"))
        max_seconds = int(os.getenv("ONEC_OUTBOUND_RETRY_MAX_SECONDS", "3600"))
        delay = min(max_seconds, base_seconds * (2 ** max(0, attempts - 1)))
        return _utcnow() + timedelta(seconds=delay)

    async def _sync_user(self, job: OneCUserSyncJob) -> None:
        payload_raw = job.request_payload or {}
        payload = OneCUserRegistrationPayload(**payload_raw)

        user_result = await self.db.execute(select(User).where(User.id == job.user_id))
        user = user_result.scalar_one()

        if (
            payload.source != "referral_partner"
            and getattr(user, "customer_id_1c", None)
            and getattr(user, "discount_card_id_1c", None)
        ):
            job.customer_id_1c = user.customer_id_1c
            job.discount_card_id_1c = user.discount_card_id_1c
            return

        async with OneCOutboundService() as onec:
            customer_id_1c, discount_card_id_1c, onec_debug = await self._ensure_customer_and_card(onec, payload)
            job.response_payload = onec_debug
            job.customer_id_1c = customer_id_1c
            job.discount_card_id_1c = discount_card_id_1c

            user.customer_id_1c = customer_id_1c
            user.discount_card_id_1c = discount_card_id_1c
            user.discount_card_number = payload.phone
            user.is_customer = True
            user.synced_at = _utcnow()
            if not getattr(user, "role", None) or str(getattr(user, "role", "")).strip().lower() in {"user"}:
                user.role = "customer"
            await self._sync_loyalty_balance_from_1c(
                user,
                customer_id_1c=str(customer_id_1c),
                discount_card_id_1c=str(discount_card_id_1c),
            )
            await self.db.commit()

            if not payload.skip_welcome_bonus:
                await self._ensure_welcome_bonus(
                    onec,
                    job_id=str(job.id),
                    discount_card_id=str(discount_card_id_1c),
                    payload=payload,
                )

    async def _sync_loyalty_balance_from_1c(
        self,
        user: User,
        *,
        customer_id_1c: str | None,
        discount_card_id_1c: str | None,
    ) -> None:
        if not customer_id_1c and not discount_card_id_1c:
            return
        try:
            async with OneCCustomersService() as onec:
                loyalty_info = await onec.fetch_loyalty_balance(
                    customer_key=customer_id_1c,
                    discount_card_key=discount_card_id_1c,
                )
        except Exception as error:
            logger.warning("Не удалось синхронизировать баланс бонусов из 1С для %s: %s", user.id, error)
            return

        if not loyalty_info or loyalty_info.get("balance") is None:
            return

        balance = int(loyalty_info.get("balance") or 0)
        current_balance = int(getattr(user, "loyalty_points", 0) or 0)
        if balance == current_balance:
            return

        user.loyalty_points = balance
        self.db.add(
            LoyaltyTransaction(
                user_id=user.id,
                transaction_type="sync_from_1c",
                points=balance - current_balance,
                balance_after=balance,
                reason="sync_from_1c",
                description="Синхронизация баланса из 1С после регистрации партнера",
                source="1c",
                source_id=str(loyalty_info.get("source_id") or discount_card_id_1c or customer_id_1c or ""),
            )
        )

    async def _ensure_customer_and_card(
        self,
        onec: OneCOutboundService,
        payload: OneCUserRegistrationPayload,
    ) -> Tuple[str, str, Dict[str, Any]]:
        debug: Dict[str, Any] = {"steps": []}

        card = await onec.find_discount_card_by_phone(payload.phone)
        existing_card_id = None
        if card:
            debug["steps"].append({"type": "found_card", "ref_key": card.get("Ref_Key")})
            card_id = card.get("Ref_Key")
            customer_id = card.get("ВладелецКарты_Key")
            if card_id and customer_id:
                await self._ensure_customer_phone_contact(onec, customer_id=str(customer_id), phone=payload.phone, debug=debug)
                await self._ensure_customer_group(onec, customer_id=str(customer_id), payload=payload, debug=debug)
                await self._ensure_referral_link_extra(onec, customer_id=str(customer_id), payload=payload, debug=debug)
                return str(customer_id), str(card_id), debug
            if card_id:
                existing_card_id = str(card_id)

        customer_created = False
        customer = await self._find_customer(onec, payload)
        if customer:
            debug["steps"].append({"type": "found_customer", "ref_key": customer.get("Ref_Key")})
            customer_id = customer.get("Ref_Key")
        else:
            customer_payload = self._build_customer_create_payload(payload)
            created = await onec.create_customer(customer_payload)
            debug["steps"].append({"type": "created_customer"})
            customer_created = True
            customer_id = created.get("Ref_Key") or created.get("ref_key")
            if not customer_id:
                raise RuntimeError("1С не вернула Ref_Key созданного контрагента")

        await self._ensure_customer_phone_contact(onec, customer_id=str(customer_id), phone=payload.phone, debug=debug)
        await self._ensure_customer_group(onec, customer_id=str(customer_id), payload=payload, debug=debug)
        await self._ensure_referral_link_extra(onec, customer_id=str(customer_id), payload=payload, debug=debug)

        if existing_card_id:
            await onec.update_discount_card(existing_card_id, {"ВладелецКарты_Key": str(customer_id)})
            debug["steps"].append({"type": "updated_card_owner", "ref_key": existing_card_id})
            return str(customer_id), str(existing_card_id), debug

        card_payload = self._build_card_create_payload(
            payload,
            customer_id=str(customer_id),
            include_loyalty_program=customer_created and bool(payload.loyalty_program_key),
        )
        created_card = await onec.create_discount_card(card_payload)
        debug["steps"].append({"type": "created_card"})
        card_id = created_card.get("Ref_Key") or created_card.get("ref_key")
        if not card_id:
            card_id = created_card.get("Ref_Key") or card_payload.get("Ref_Key")
        if not card_id:
            raise RuntimeError("1С не вернула Ref_Key созданной дисконтной карты")
        return str(customer_id), str(card_id), debug

    async def _ensure_discount_card_loyalty_program(
        self,
        onec: OneCOutboundService,
        *,
        card_id: str,
        payload: OneCUserRegistrationPayload,
        debug: Dict[str, Any],
    ) -> None:
        loyalty_key = self._resolve_loyalty_program_key(payload)
        loyalty_field = self._resolve_loyalty_program_field()
        if not card_id or not loyalty_key or not loyalty_field:
            return
        await onec.update_discount_card(card_id, {loyalty_field: loyalty_key})
        debug["steps"].append(
            {
                "type": "updated_card_loyalty_program",
                "ref_key": card_id,
                "loyalty_program_key": loyalty_key,
                "loyalty_program_field": loyalty_field,
            }
        )

    async def _ensure_customer_phone_contact(
        self,
        onec: OneCOutboundService,
        *,
        customer_id: str,
        phone: str,
        debug: Dict[str, Any],
    ) -> None:
        if not customer_id or not phone:
            return

        customer = await onec.fetch_customer_by_ref_key(customer_id)
        existing_contacts = list((customer or {}).get("КонтактнаяИнформация") or [])
        phone_contact = self._build_phone_contact(customer_id=customer_id, phone=phone)

        replaced = False
        merged_contacts: List[Dict[str, Any]] = []
        for contact in existing_contacts:
            if str(contact.get("Тип") or "").lower() == "телефон" and not replaced:
                merged_contacts.append(phone_contact)
                replaced = True
            else:
                merged_contacts.append(contact)
        if not replaced:
            merged_contacts.insert(0, phone_contact)

        await onec.update_customer(
            customer_id,
            {
                "НомерТелефонаДляПоиска": phone,
                "КонтактнаяИнформация": merged_contacts,
            },
        )
        debug["steps"].append({"type": "updated_customer_phone", "ref_key": customer_id})

    async def _ensure_customer_group(
        self,
        onec: OneCOutboundService,
        *,
        customer_id: str,
        payload: OneCUserRegistrationPayload,
        debug: Dict[str, Any],
    ) -> None:
        group_key = payload.customer_group_key or os.getenv("ONEC_CUSTOMER_GROUP_KEY")
        group_field = os.getenv("ONEC_CUSTOMER_GROUP_FIELD", "Parent_Key")
        if not customer_id or not group_key or not group_field:
            return
        await onec.update_customer(customer_id, {group_field: group_key})
        debug["steps"].append({"type": "updated_customer_group", "ref_key": customer_id, "group_key": group_key})

    async def _ensure_referral_link_extra(
        self,
        onec: OneCOutboundService,
        *,
        customer_id: str,
        payload: OneCUserRegistrationPayload,
        debug: Dict[str, Any],
    ) -> None:
        if payload.source != "referral_partner":
            return
        referral_value = (payload.referral_code or payload.referral_url or "").strip()
        if not referral_value:
            return

        property_key = os.getenv("ONEC_REFERRAL_LINK_PROPERTY_KEY", REFERRAL_LINK_PROPERTY_KEY)
        value = await onec.find_property_value(property_key, referral_value)
        if value:
            value_key = value.get("Ref_Key")
        else:
            created = await onec.create_property_value(property_key, referral_value)
            value_key = created.get("Ref_Key") or created.get("ref_key")
            debug["steps"].append({"type": "created_referral_link_value", "ref_key": value_key})
        if not value_key:
            raise RuntimeError("1С не вернула Ref_Key значения допреквизита реферальной ссылки")

        customer = await onec.fetch_customer_by_ref_key(customer_id)
        existing_extra = list((customer or {}).get("ДополнительныеРеквизиты") or [])
        merged_extra: List[Dict[str, Any]] = []
        replaced = False
        line_number = 1
        for item in existing_extra:
            if item.get("Свойство_Key") == property_key:
                if not replaced:
                    merged_extra.append(
                        self._build_referral_link_extra(
                            customer_id,
                            property_key,
                            str(value_key),
                            referral_value,
                            line_number,
                        )
                    )
                    line_number += 1
                    replaced = True
                continue
            item = dict(item)
            item["LineNumber"] = str(line_number)
            merged_extra.append(item)
            line_number += 1
        if not replaced:
            merged_extra.append(
                self._build_referral_link_extra(
                    customer_id,
                    property_key,
                    str(value_key),
                    referral_value,
                    line_number,
                )
            )

        await onec.update_customer(customer_id, {"ДополнительныеРеквизиты": merged_extra})
        debug["steps"].append({"type": "updated_referral_link_extra", "ref_key": customer_id})

    async def _ensure_welcome_bonus(
        self,
        onec: OneCOutboundService,
        job_id: str,
        discount_card_id: str,
        payload: OneCUserRegistrationPayload,
    ) -> None:
        if not _env_bool("ONEC_WELCOME_BONUS_ENABLED", "true"):
            return

        points = int(payload.welcome_bonus_points or os.getenv("ONEC_WELCOME_BONUS_POINTS", "500"))
        if points <= 0:
            return

        bonus_program_key = os.getenv("ONEC_BONUS_PROGRAM_KEY")
        if not bonus_program_key:
            logger.warning("ONEC_BONUS_PROGRAM_KEY не задан, пропускаю приветственные бонусы")
            return

        comment = (payload.welcome_bonus_comment or f"glame_welcome:{job_id}").strip()
        analytics_key = os.getenv(
            "ONEC_WELCOME_BONUS_ANALYTICS_KEY",
            "e6881e68-cdf4-11f0-85a1-fa163e4cc04e",
        ).strip() or None
        expires_days = int(os.getenv("ONEC_WELCOME_BONUS_EXPIRES_DAYS", "365"))
        expires_at = (_utcnow() + timedelta(days=expires_days)).replace(microsecond=0).isoformat()
        try:
            existing = await onec.find_welcome_bonus_doc(comment)
            if existing:
                doc_ref_key = str(existing.get("Ref_Key") or "")
                if doc_ref_key:
                    await onec.unpost_welcome_bonus_doc(doc_ref_key)
                await onec.update_welcome_bonus_doc(
                    doc_ref_key=doc_ref_key,
                    bonus_program_key=bonus_program_key,
                    card_ref_key=discount_card_id,
                    points=points,
                    comment=comment,
                    analytics_key=analytics_key,
                    expires_at=expires_at,
                )
                if doc_ref_key:
                    await onec.post_welcome_bonus_doc(doc_ref_key)
                return
        except Exception as e:
            logger.warning("Не удалось проверить приветственные бонусы в 1С: %s", e)

        try:
            created = await onec.create_welcome_bonus_doc(
                bonus_program_key=bonus_program_key,
                card_ref_key=discount_card_id,
                points=points,
                comment=comment,
                analytics_key=analytics_key,
                expires_at=expires_at,
            )
            doc_ref_key = str(created.get("Ref_Key") or "")
            if doc_ref_key:
                await onec.post_welcome_bonus_doc(doc_ref_key)
        except Exception as e:
            logger.warning("Не удалось начислить приветственные бонусы в 1С: %s", e)

    async def _find_customer(self, onec: OneCOutboundService, payload: OneCUserRegistrationPayload) -> Optional[Dict[str, Any]]:
        candidates: List[Tuple[str, str]] = []

        if payload.email:
            fields_raw = os.getenv(
                "ONEC_CUSTOMER_EMAIL_FIELDS",
                "АдресЭПДляПоиска",
            )
            for field_name in [x.strip() for x in fields_raw.split(",") if x.strip()]:
                candidates.append((field_name, str(payload.email).lower()))

        if payload.phone:
            fields_raw = os.getenv("ONEC_CUSTOMER_PHONE_FIELDS", "НомерТелефонаДляПоиска")
            for field_name in [x.strip() for x in fields_raw.split(",") if x.strip()]:
                candidates.append((field_name, payload.phone))

        if payload.inn:
            fields_raw = os.getenv("ONEC_CUSTOMER_INN_FIELDS", "ИНН")
            for field_name in [x.strip() for x in fields_raw.split(",") if x.strip()]:
                candidates.append((field_name, payload.inn))

        if not candidates:
            return None
        return await onec.find_customer_by_fields(candidates)

    @staticmethod
    def _build_customer_create_payload(payload: OneCUserRegistrationPayload) -> Dict[str, Any]:
        name_value = payload.full_name or payload.phone
        body: Dict[str, Any] = {
            "Description": name_value,
            "НаименованиеПолное": name_value
        }

        kind_value = os.getenv("ONEC_CUSTOMER_KIND_VALUE", "ФизическоеЛицо")
        kind_fields_raw = os.getenv("ONEC_CUSTOMER_KIND_FIELDS", "ВидКонтрагента,ЮридическоеФизическоеЛицо")
        kind_fields = [x.strip() for x in kind_fields_raw.split(",") if x.strip()]
        for field_name in kind_fields:
            body[field_name] = kind_value

        if payload.email:
            email_value = str(payload.email).lower()
            fields_raw = os.getenv(
                "ONEC_CUSTOMER_EMAIL_FIELDS",
                "АдресЭПДляПоиска",
            )
            email_fields = [x.strip() for x in fields_raw.split(",") if x.strip()]
            if email_fields:
                body[email_fields[0]] = email_value

        if payload.phone:
            fields_raw = os.getenv("ONEC_CUSTOMER_PHONE_FIELDS", "НомерТелефонаДляПоиска")
            phone_fields = [x.strip() for x in fields_raw.split(",") if x.strip()]
            if phone_fields:
                body[phone_fields[0]] = payload.phone

        if payload.inn:
            fields_raw = os.getenv("ONEC_CUSTOMER_INN_FIELDS", "ИНН")
            inn_fields = [x.strip() for x in fields_raw.split(",") if x.strip()]
            if inn_fields:
                body[inn_fields[0]] = payload.inn
                
        if payload.birth_date:
            body["ДатаРождения"] = payload.birth_date.isoformat() + "T00:00:00"

        group_key = payload.customer_group_key or os.getenv("ONEC_CUSTOMER_GROUP_KEY")
        group_field = os.getenv("ONEC_CUSTOMER_GROUP_FIELD", "Parent_Key")
        if group_key and group_field:
            body[group_field] = group_key

        customer_type_field = os.getenv("ONEC_CUSTOMER_TYPE_FIELD", "Покупатель")
        customer_type_value = os.getenv("ONEC_CUSTOMER_TYPE_VALUE", "true")
        if customer_type_field:
            body[customer_type_field] = str(customer_type_value).lower() in ("true", "1", "yes") if customer_type_value.lower() in ("true", "false") else customer_type_value

        return body

    async def _sync_referral_member_status(
        self,
        job: OneCUserSyncJob,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        payload_raw = job.request_payload or {}
        if payload_raw.get("source") != "referral_partner":
            return

        values: Dict[str, Any] = {
            "onec_sync_status": status,
            "onec_last_error": error,
        }
        if job.customer_id_1c:
            values["onec_counterparty_id"] = job.customer_id_1c

        await self.db.execute(
            update(ReferralProgramMember)
            .where(ReferralProgramMember.user_id == job.user_id)
            .values(**values)
        )

    @staticmethod
    def _build_card_create_payload(
        payload: OneCUserRegistrationPayload,
        customer_id: str,
        *,
        include_loyalty_program: bool = False,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "Description": payload.full_name or payload.phone,
            "КодКартыШтрихкод": payload.phone,
            "ВладелецКарты_Key": customer_id,
        }

        kind_key = os.getenv("ONEC_DISCOUNT_CARD_KIND_KEY")
        kind_field = os.getenv("ONEC_DISCOUNT_CARD_KIND_FIELD", "Owner_Key")
        if kind_key:
            body[kind_field] = kind_key

        if include_loyalty_program:
            loyalty_key = OneCUserSyncService._resolve_loyalty_program_key(payload)
            loyalty_field = OneCUserSyncService._resolve_loyalty_program_field()
            if loyalty_key and loyalty_field:
                body[loyalty_field] = loyalty_key

        return body

    @staticmethod
    def _resolve_loyalty_program_key(payload: OneCUserRegistrationPayload) -> str | None:
        return (
            payload.loyalty_program_key
            or os.getenv("ONEC_LOYALTY_PROGRAM_KEY")
            or os.getenv("ONEC_BONUS_PROGRAM_KEY")
            or None
        )

    @staticmethod
    def _resolve_loyalty_program_field() -> str:
        return os.getenv("ONEC_LOYALTY_PROGRAM_FIELD", "БонуснаяПрограмма_Key")

    @staticmethod
    def _build_phone_contact(customer_id: str, phone: str) -> Dict[str, Any]:
        phone_clean = "".join(ch for ch in str(phone or "") if ch.isdigit())
        formatted = f"+{phone_clean}" if phone_clean else str(phone or "")
        phone_kind_key = os.getenv("ONEC_CUSTOMER_PHONE_CONTACT_KIND_KEY", "e8220f38-fdc8-11ef-8c0c-fa163e4cc04e")
        value = {
            "version": 4,
            "value": formatted,
            "type": "Телефон",
            "number": formatted,
        }
        return {
            "Ref_Key": customer_id,
            "LineNumber": "1",
            "Тип": "Телефон",
            "Вид_Key": phone_kind_key,
            "Представление": formatted,
            "ЗначенияПолей": (
                '<КонтактнаяИнформация xmlns="http://www.v8.1c.ru/ssl/contactinfo" '
                'xmlns:xs="http://www.w3.org/2001/XMLSchema" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                f'Представление="{formatted}"><Состав xsi:type="НомерТелефона" '
                f'КодСтраны="" КодГорода="" Номер="{formatted}" Добавочный=""/>'
                "</КонтактнаяИнформация>"
            ),
            "Страна": "",
            "Регион": "",
            "Город": "",
            "АдресЭП": "",
            "ДоменноеИмяСервера": "",
            "НомерТелефона": phone_clean,
            "НомерТелефонаБезКодов": phone_clean,
            "Значение": json.dumps(value, ensure_ascii=False, indent=0),
            "ДействуетС": "0001-01-01T00:00:00",
            "ОбратныйНомерТелефона": phone_clean[::-1],
        }

    @staticmethod
    def _build_referral_link_extra(
        customer_id: str,
        property_key: str,
        value_key: str,
        value_text: str,
        line_number: int,
    ) -> Dict[str, Any]:
        return {
            "Ref_Key": customer_id,
            "LineNumber": str(line_number),
            "Свойство_Key": property_key,
            "Значение": value_key,
            "ТекстоваяСтрока": value_text,
            "Значение_Type": "StandardODATA.Catalog_ЗначенияСвойствОбъектов",
        }
