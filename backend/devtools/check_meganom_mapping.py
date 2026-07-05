import asyncio
from sqlalchemy import select, func
from app.database.connection import AsyncSessionLocal
from app.models.store import Store
from app.models.purchase_history import PurchaseHistory


async def main():
    async with AsyncSessionLocal() as session:
        # 1) Найти магазины с именем, содержащим "Меганом"
        stores_stmt = select(Store.external_id, Store.name, Store.is_active).where(
            Store.name.ilike("%Меганом%")
        )
        stores_res = await session.execute(stores_stmt)
        stores = stores_res.all()
        print("=== Stores matching 'Меганом' ===")
        if not stores:
            print("Нет записей в stores с именем, похожим на 'Меганом'")
        for external_id, name, is_active in stores:
            print(f"- {name} | external_id={external_id} | active={is_active}")
            # 2) Посчитать покупки по этому external_id
            cnt_stmt = select(func.count(PurchaseHistory.id)).where(
                PurchaseHistory.store_id_1c == external_id
            )
            cnt = (await session.execute(cnt_stmt)).scalar() or 0
            print(f"  Покупок с этим store_id_1c: {cnt}")
            # 3) Показать до 5 примеров покупок
            sample_stmt = (
                select(PurchaseHistory.id, PurchaseHistory.purchase_date, PurchaseHistory.total_amount)
                .where(PurchaseHistory.store_id_1c == external_id)
                .order_by(PurchaseHistory.purchase_date.desc())
                .limit(5)
            )
            sample = (await session.execute(sample_stmt)).all()
            for pid, dt, amt in sample:
                print(f"  - purchase {pid} | {dt} | {amt}")

        # 4) Если 'Меганом' не найден в stores, показать любые продажи с указанным магазином,
        #    у которых нет соответствия в stores (диагностика "осиротевших" store_id_1c)
        if not stores:
            orphan_stmt = """
            SELECT ph.store_id_1c, COUNT(*) AS c
            FROM purchase_history ph
            LEFT JOIN stores s ON s.external_id = ph.store_id_1c
            WHERE ph.store_id_1c IS NOT NULL AND s.id IS NULL
            GROUP BY ph.store_id_1c
            ORDER BY c DESC
            LIMIT 20
            """
            res = await session.execute(orphan_stmt)
            rows = res.all()
            print("=== Осиротевшие store_id_1c (нет соответствия в stores) ===")
            if not rows:
                print("Нет осиротевших store_id_1c")
            for sid, cnt in rows:
                print(f"- store_id_1c={sid} | purchases={cnt}")


if __name__ == "__main__":
    asyncio.run(main())

