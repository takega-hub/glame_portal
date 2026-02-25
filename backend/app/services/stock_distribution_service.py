"""
Сервис для распределения остатков по складам
Используется, когда в offers.xml нет разбивки по складам
Распределяет остатки пропорционально продажам по складам
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.sales_record import SalesRecord
from app.models.product import Product
from app.models.product_stock import ProductStock

logger = logging.getLogger(__name__)


class StockDistributionService:
    """Сервис для распределения остатков по складам на основе продаж"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def distribute_stocks_by_sales(
        self,
        product_id: str,
        total_quantity: float,
        period_days: int = 90
    ) -> Dict[str, float]:
        """
        Распределяет остатки товара по складам пропорционально продажам
        
        Args:
            product_id: ID товара из 1С (external_id)
            total_quantity: Общее количество остатка
            period_days: Период для анализа продаж (дней назад)
        
        Returns:
            Словарь {store_id: quantity} - распределение остатков по складам
        """
        # Получаем продажи товара по складам за период
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        
        query = select(
            SalesRecord.store_id,
            func.sum(SalesRecord.quantity).label('total_sold')
        ).where(
            and_(
                SalesRecord.product_id == product_id,
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.store_id.isnot(None)
            )
        ).group_by(SalesRecord.store_id)
        
        result = await self.db.execute(query)
        sales_by_store = result.all()
        
        if not sales_by_store:
            # Если нет продаж - распределяем равномерно по всем складам из продаж
            # Или используем склад по умолчанию
            logger.warning(f"Нет продаж для товара {product_id} за последние {period_days} дней")
            return {"default_store": total_quantity}
        
        # Рассчитываем общее количество проданных единиц
        total_sold = sum(float(row[1]) if row[1] else 0.0 for row in sales_by_store)
        
        if total_sold == 0:
            # Если нет продаж - используем склад по умолчанию
            return {"default_store": total_quantity}
        
        # Распределяем остатки пропорционально продажам
        distribution = {}
        remaining_quantity = total_quantity
        
        # Сортируем склады по продажам (от большего к меньшему)
        sorted_stores = sorted(sales_by_store, key=lambda x: float(x[1] or 0), reverse=True)
        
        for i, (store_id, sold_quantity) in enumerate(sorted_stores):
            if store_id is None:
                continue
            
            sold_float = float(sold_quantity or 0)
            
            if i == len(sorted_stores) - 1:
                # Последний склад получает остаток (чтобы избежать округления)
                distribution[store_id] = remaining_quantity
            else:
                # Пропорциональное распределение
                share = sold_float / total_sold
                allocated = total_quantity * share
                distribution[store_id] = allocated
                remaining_quantity -= allocated
        
        return distribution
    
    async def redistribute_all_stocks(
        self,
        period_days: int = 90,
        min_sales_threshold: float = 1.0
    ) -> Dict[str, Any]:
        """
        Перераспределяет все остатки без разбивки по складам
        на основе продаж за период
        
        Args:
            period_days: Период для анализа продаж
            min_sales_threshold: Минимальное количество продаж для учёта склада
        
        Returns:
            Статистика перераспределения
        """
        # Находим все остатки без разбивки по складам (store_id = "default_store")
        query = select(ProductStock).where(
            ProductStock.store_id == "default_store"
        )
        
        result = await self.db.execute(query)
        default_stocks = result.scalars().all()
        
        logger.info(f"Найдено {len(default_stocks)} остатков без разбивки по складам")
        
        redistributed = 0
        skipped = 0
        errors = []
        
        for stock in default_stocks:
            try:
                # Получаем товар
                product_result = await self.db.execute(
                    select(Product).where(Product.id == stock.product_id)
                )
                product = product_result.scalar_one_or_none()
                
                if not product or not product.external_id:
                    skipped += 1
                    continue
                
                # Распределяем остатки
                distribution = await self.distribute_stocks_by_sales(
                    product_id=product.external_id,
                    total_quantity=stock.quantity,
                    period_days=period_days
                )
                
                # Удаляем старый остаток
                await self.db.delete(stock)
                
                # Создаём новые остатки по складам
                for store_id, quantity in distribution.items():
                    if quantity > 0:
                        new_stock = ProductStock(
                            product_id=stock.product_id,
                            store_id=store_id,
                            quantity=quantity,
                            reserved_quantity=0.0,
                            available_quantity=quantity,
                        )
                        self.db.add(new_stock)
                
                redistributed += 1
                
                # Коммитим каждые 50 записей
                if redistributed % 50 == 0:
                    await self.db.commit()
                    
            except Exception as e:
                error_msg = f"Ошибка перераспределения остатка для товара {stock.product_id}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)
                skipped += 1
        
        await self.db.commit()
        
        return {
            "redistributed": redistributed,
            "skipped": skipped,
            "errors": errors[:20],
            "error_count": len(errors)
        }
