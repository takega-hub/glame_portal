import asyncio
import os
from typing import Dict, Any, Optional
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.store import Store
from app.services.onec_customers_service import OneCCustomersService


async def fetch_retail_report_details(onec: OneCCustomersService, recorder_key: str) -> Optional[Dict[str, Any]]:
    """
    Пытаемся получить детали документа 'ОтчетОРозничныхПродажах' по Ref_Key (Recorder).
    Пробуем несколько вариантов путей.
    """
    if not onec.client:
        raise RuntimeError("1С клиент не настроен (ONEC_API_URL/ONEC_API_TOKEN)")
    base = onec.api_url.rstrip("/")
    candidates = [
        f"{base}/Document_ОтчетОРозничныхПродажах",
        f"{base}/StandardODATA/Document_ОтчетОРозничныхПродажах",
    ]
    for url in candidates:
        params = {"$filter": f"Ref_Key eq guid'{recorder_key}'", "$top": 1}
        try:
            resp = await onec.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("value"):
                return data["value"][0]
        except Exception:
            continue
    return None


async def backfill(phone: str):
    async with AsyncSessionLocal() as session:
        onec = OneCCustomersService()
        user = (await session.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
        if not user:
            print("User not found")
            return
        print("User:", user.id, user.full_name)
        stores = (await session.execute(select(Store))).scalars().all()
        stores_by_name = {s.name.lower(): s for s in stores if s.name}
        # Выбираем покупки без привязки к магазину
        ph_rows = (
            await session.execute(
                select(PurchaseHistory).where(
                    PurchaseHistory.user_id == user.id,
                    PurchaseHistory.store_id_1c.is_(None),
                )
            )
        ).scalars().all()
        print("Purchases without store:", len(ph_rows))
        # Группируем по документу
        by_doc: Dict[str, list[PurchaseHistory]] = {}
        for p in ph_rows:
            if not p.document_id_1c:
                continue
            by_doc.setdefault(p.document_id_1c, []).append(p)
        updated = 0
        for doc_id, items in by_doc.items():
            details = await fetch_retail_report_details(onec, doc_id)
            if not details:
                continue
            kkt_desc = (
                details.get("КассаККМ_Description")
                or details.get("ККТ_Description")
                or details.get("Description")
                or ""
            )
            kkt_desc_l = str(kkt_desc).lower()
            # Простейший маппинг: ищем по подстроке имени магазина
            target_store_id = None
            # приоритет: Меганом
            if "меганом" in kkt_desc_l:
                s = next((s for s in stores if s.name and "меганом" in s.name.lower()), None)
                if s:
                    target_store_id = s.external_id
            # общий перебор
            if not target_store_id:
                for s in stores:
                    if s.name and s.external_id and s.name.lower() in kkt_desc_l:
                        target_store_id = s.external_id
                        break
            if target_store_id:
                for p in items:
                    p.store_id_1c = target_store_id
                updated += len(items)
                print(f"Doc {doc_id}: set store_id_1c={target_store_id} for {len(items)} items (KKT: {kkt_desc})")
        if updated:
            await session.commit()
        print("Updated rows:", updated)


if __name__ == "__main__":
    import sys
    phone = sys.argv[1] if len(sys.argv) > 1 else ""
    if not phone:
        print("Usage: python -m devtools.backfill_store_from_retail_report <phone>")
        raise SystemExit(1)
    asyncio.run(backfill(phone))

