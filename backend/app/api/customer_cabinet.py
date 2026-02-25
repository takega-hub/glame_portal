"""
API личного кабинета покупателя
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from app.database.connection import get_db
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.saved_look import SavedLook
from app.models.look import Look
from app.api.auth import get_current_user
from app.services.loyalty_service import LoyaltyService

router = APIRouter()


class CustomerProfileResponse(BaseModel):
    id: str
    phone: Optional[str]
    email: Optional[str]
    full_name: Optional[str]
    discount_card_number: Optional[str]
    loyalty_points: int
    customer_segment: Optional[str]
    total_purchases: int
    total_spent: float
    average_check: Optional[float]
    last_purchase_date: Optional[str]
    purchase_preferences: Optional[dict]

    class Config:
        from_attributes = True


class PurchaseHistoryItem(BaseModel):
    id: str
    purchase_date: str
    product_name: Optional[str]
    quantity: int
    total_amount: float
    category: Optional[str]
    brand: Optional[str]

    class Config:
        from_attributes = True


class PurchaseStatsResponse(BaseModel):
    total_purchases: int
    total_spent: float
    average_check: float
    favorite_categories: List[str]
    favorite_brands: List[str]


class SavedLookResponse(BaseModel):
    id: str
    look_id: str
    look_name: str
    save_type: str
    notes: Optional[str]
    is_purchased: bool
    created_at: str

    class Config:
        from_attributes = True


@router.get("/profile", response_model=CustomerProfileResponse)
async def get_customer_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Профиль покупателя"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    return CustomerProfileResponse(
        id=str(current_user.id),
        phone=current_user.phone,
        email=current_user.email,
        full_name=current_user.full_name,
        discount_card_number=current_user.discount_card_number,
        loyalty_points=current_user.loyalty_points or 0,
        customer_segment=current_user.customer_segment,
        total_purchases=current_user.total_purchases,
        total_spent=(current_user.total_spent or 0) / 100,
        average_check=(current_user.average_check / 100) if current_user.average_check else None,
        last_purchase_date=current_user.last_purchase_date.isoformat() if current_user.last_purchase_date else None,
        purchase_preferences=current_user.purchase_preferences
    )


@router.put("/profile")
async def update_customer_profile(
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление профиля покупателя"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    if full_name is not None:
        current_user.full_name = full_name
    if email is not None:
        current_user.email = email
    
    await db.commit()
    
    return {"success": True, "message": "Профиль обновлен"}


@router.get("/purchase-history", response_model=List[PurchaseHistoryItem])
async def get_purchase_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """История покупок"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == current_user.id)
    
    # Фильтр по дате
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            stmt = stmt.where(PurchaseHistory.purchase_date >= from_dt)
        except:
            pass
    
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            stmt = stmt.where(PurchaseHistory.purchase_date <= to_dt)
        except:
            pass
    
    stmt = stmt.order_by(desc(PurchaseHistory.purchase_date)).limit(limit).offset(offset)
    
    result = await db.execute(stmt)
    purchases = result.scalars().all()
    
    return [
        PurchaseHistoryItem(
            id=str(p.id),
            purchase_date=p.purchase_date.isoformat(),
            product_name=p.product_name,
            quantity=p.quantity,
            total_amount=p.total_amount / 100,
            category=p.category,
            brand=p.brand
        )
        for p in purchases
    ]


@router.get("/purchase-stats", response_model=PurchaseStatsResponse)
async def get_purchase_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Статистика покупок"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    preferences = current_user.purchase_preferences or {}
    
    return PurchaseStatsResponse(
        total_purchases=current_user.total_purchases,
        total_spent=(current_user.total_spent or 0) / 100,
        average_check=(current_user.average_check / 100) if current_user.average_check else 0,
        favorite_categories=preferences.get("favorite_categories", []),
        favorite_brands=preferences.get("favorite_brands", [])
    )


@router.get("/loyalty")
async def get_loyalty_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Программа лояльности"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    loyalty_service = LoyaltyService(db)
    balance = await loyalty_service.get_loyalty_balance(current_user.id)
    transactions = await loyalty_service.get_loyalty_transactions(current_user.id, limit=50)
    program_info = loyalty_service.get_loyalty_program_info()
    
    return {
        "balance": balance,
        "transactions": [
            {
                "id": str(t.id),
                "type": t.transaction_type,
                "points": t.points,
                "balance_after": t.balance_after,
                "reason": t.reason,
                "description": t.description,
                "created_at": t.created_at.isoformat()
            }
            for t in transactions
        ],
        "program_info": program_info
    }


@router.get("/saved-looks", response_model=List[SavedLookResponse])
async def get_saved_looks(
    save_type: Optional[str] = Query(None, description="favorite или generated"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Сохраненные образы"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    stmt = (
        select(SavedLook, Look)
        .join(Look, SavedLook.look_id == Look.id)
        .where(SavedLook.user_id == current_user.id)
    )
    
    if save_type:
        stmt = stmt.where(SavedLook.save_type == save_type)
    
    stmt = stmt.order_by(desc(SavedLook.created_at))
    
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        SavedLookResponse(
            id=str(saved_look.id),
            look_id=str(saved_look.look_id),
            look_name=look.name,
            save_type=saved_look.save_type,
            notes=saved_look.notes,
            is_purchased=saved_look.is_purchased,
            created_at=saved_look.created_at.isoformat()
        )
        for saved_look, look in rows
    ]


@router.post("/saved-looks")
async def save_look(
    look_id: str,
    save_type: str,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Сохранить образ"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    if save_type not in ["favorite", "generated"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="save_type должен быть 'favorite' или 'generated'"
        )
    
    # Проверяем существование образа
    try:
        look_uuid = UUID(look_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат look_id"
        )
    
    stmt = select(Look).where(Look.id == look_uuid)
    result = await db.execute(stmt)
    look = result.scalar_one_or_none()
    
    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Образ не найден"
        )
    
    # Проверяем, не сохранен ли уже
    stmt = select(SavedLook).where(
        and_(
            SavedLook.user_id == current_user.id,
            SavedLook.look_id == look_uuid
        )
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Образ уже сохранен"
        )
    
    # Создаем сохраненный образ
    saved_look = SavedLook(
        user_id=current_user.id,
        look_id=look_uuid,
        save_type=save_type,
        notes=notes
    )
    
    db.add(saved_look)
    await db.commit()
    
    return {"success": True, "message": "Образ сохранен", "id": str(saved_look.id)}


@router.delete("/saved-looks/{saved_look_id}")
async def delete_saved_look(
    saved_look_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить сохраненный образ"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    try:
        saved_look_uuid = UUID(saved_look_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат saved_look_id"
        )
    
    stmt = select(SavedLook).where(
        and_(
            SavedLook.id == saved_look_uuid,
            SavedLook.user_id == current_user.id
        )
    )
    result = await db.execute(stmt)
    saved_look = result.scalar_one_or_none()
    
    if not saved_look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сохраненный образ не найден"
        )
    
    await db.delete(saved_look)
    await db.commit()
    
    return {"success": True, "message": "Образ удален"}
