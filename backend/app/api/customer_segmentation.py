
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from urllib.parse import quote
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.database.connection import get_db
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import sqlalchemy
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.store import Store
import uuid
from datetime import datetime
import logging
import pandas as pd
import io

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем обработчик для вывода в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Создаем форматтер
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Добавляем обработчик к логгеру
logger.addHandler(console_handler)

router = APIRouter(tags=["Customer Segmentation"])

class FilterCondition(BaseModel):
    field: str
    operator: str
    value: Any

class FilterGroup(BaseModel):
    logic: str = Field(..., description="Logic for the group: AND or OR")
    filters: List[Dict[str, Any]]

class SegmentRules(BaseModel):
    logic: str = Field(default="AND", description="Root logic for the segment: AND or OR")
    filters: List[Dict[str, Any]] = Field(default_factory=list)

class SegmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rules: SegmentRules

class SegmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rules: Optional[SegmentRules] = None

class SegmentOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    rules: SegmentRules
    customer_count: int
    is_auto_generated: bool
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        orm_mode = True


def _normalize_to_segment_rules(rules: Dict[str, Any] | None, is_auto_generated: bool = False) -> SegmentRules:
    try:
        if isinstance(rules, dict) and ("filters" in rules or "logic" in rules):
            logic = str(rules.get("logic", "AND") or "AND").upper()
            filters = rules.get("filters") or []
            if not isinstance(filters, list):
                filters = []
            return SegmentRules(logic=logic, filters=filters)
        if isinstance(rules, dict) and is_auto_generated:
            filters: List[Dict[str, Any]] = []
            try:
                mp = int(rules.get("min_purchases", 0) or 0)
                if mp > 0:
                    filters.append({"field": "total_purchases", "operator": ">=", "value": mp})
            except Exception:
                pass
            try:
                mt = int(rules.get("min_total", 0) or rules.get("min_total_spent", 0) or 0)
                if mt > 0:
                    filters.append({"field": "total_spent", "operator": ">=", "value": mt * 100})
            except Exception:
                pass
            try:
                rd = int(rules.get("max_recency_days", 0) or 0)
                if rd > 0:
                    filters.append({"field": "last_purchase_date", "operator": "within_last_days", "value": rd})
            except Exception:
                pass
            try:
                rfm = int(rules.get("rfm_min_score", 0) or 0)
                if rfm > 0:
                    filters.append({"field": "rfm_score_sum", "operator": ">=", "value": rfm})
            except Exception:
                pass
            return SegmentRules(logic="AND", filters=filters)
    except Exception:
        pass
    return SegmentRules(logic="AND", filters=[])

def _build_select_for_rules(rules: Dict[str, Any]):
    """
    Build a SQLAlchemy SELECT statement (async-compatible) for User IDs
    based on the provided rules. Returns (stmt, needs_join).
    """
    stmt = select(User.id).distinct()
    where_clause, needs_join = _build_where_clause(rules, return_needs_join=True)
    if needs_join:
        stmt = stmt.join(PurchaseHistory, User.id == PurchaseHistory.user_id)
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    return stmt, needs_join


async def materialize_segment_members(
    db: AsyncSession,
    segment_id: uuid.UUID,
    rules: Dict[str, Any],
    assigned_by: str = "ai",
    confidence_score: Optional[float] = None,
) -> int:
    """Перезаписывает фактический список покупателей сегмента по его правилам."""
    base_stmt, _ = _build_select_for_rules(rules or {})
    ids_result = await db.execute(base_stmt)
    user_ids = list(dict.fromkeys(ids_result.scalars().all()))

    await db.execute(delete(UserSegment).where(UserSegment.segment_id == segment_id))
    for user_id in user_ids:
        db.add(
            UserSegment(
                user_id=user_id,
                segment_id=segment_id,
                assigned_by=assigned_by,
                confidence_score=confidence_score,
            )
        )
    return len(user_ids)

def _build_where_clause(rules: Dict[str, Any], return_needs_join=False):
    """
    Recursively builds a SQLAlchemy WHERE clause from the rules dictionary.
    
    Args:
        rules: The rules dictionary.
        return_needs_join: If True, returns a tuple (where_clause, needs_join).
    
    Returns:
        A SQLAlchemy WHERE clause, or a tuple (where_clause, needs_join) if return_needs_join is True.
    """
    logic = rules.get("logic", "AND").upper()
    filters = rules.get("filters", [])

    if not filters:
        return (None, False) if return_needs_join else None

    clauses = []
    connectors = []
    needs_join = False
    for f in filters:
        if "logic" in f:
            # Nested group
            nested_clause, nested_needs_join = _build_where_clause(f, return_needs_join=True)
            if nested_clause is not None:
                clauses.append(nested_clause)
                connectors.append(str(f.get("connector") or logic).upper())
                if nested_needs_join:
                    needs_join = True
        else:
            # Simple filter condition
            field = f.get("field")
            operator = f.get("operator")
            value = f.get("value")

            if not all([field, operator, value is not None]):
                continue

            clause, field_needs_join = _build_single_condition(field, operator, value)
            if clause is not None:
                clauses.append(clause)
                connectors.append(str(f.get("connector") or logic).upper())
                if field_needs_join:
                    needs_join = True

    if not clauses:
        return (None, needs_join) if return_needs_join else None

    has_row_connectors = any(
        str(f.get("connector") or "").upper() in {"AND", "OR"}
        for f in filters
        if isinstance(f, dict)
    )
    if has_row_connectors:
        # Row connectors in the UI mean "this row is combined with the previous row".
        # For common rules like:
        #   city = Simferopol AND brand = UNO OR brand = Kalliope OR brand = Antura
        # the expected business meaning is:
        #   city = Simferopol AND (brand = UNO OR brand = Kalliope OR brand = Antura)
        # not the left-associative SQL form:
        #   (city = Simferopol AND brand = UNO) OR brand = Kalliope OR brand = Antura
        #
        # So we group consecutive OR-runs and then combine those groups by the root
        # logic. Symmetrically, for root OR we group consecutive AND-runs.
        group_connector = "OR" if logic == "AND" else "AND"
        groups = []
        i = 0
        while i < len(clauses):
            if i + 1 < len(clauses) and connectors[i + 1] == group_connector:
                run = [clauses[i]]
                i += 1
                while i < len(clauses) and connectors[i] == group_connector:
                    run.append(clauses[i])
                    i += 1
                groups.append(sqlalchemy.or_(*run) if group_connector == "OR" else sqlalchemy.and_(*run))
            else:
                groups.append(clauses[i])
                i += 1
        final_clause = sqlalchemy.and_(*groups) if logic == "AND" else sqlalchemy.or_(*groups)
    else:
        final_clause = sqlalchemy.and_(*clauses) if logic == "AND" else sqlalchemy.or_(*clauses)
    return (final_clause, needs_join) if return_needs_join else final_clause

def _build_single_condition(field: str, operator: str, value: Any):
    """
    Builds a single condition for a field.
    
    Returns:
        A tuple (clause, needs_join) where clause is the SQLAlchemy condition and needs_join
        indicates if a JOIN with PurchaseHistory is required.
    """
    # Virtual fields: preferred_store / preferred_store_external_id / preferred_store_name
    # Фильтрация по «предпочитаемому магазину» (хранится в users.preferred_store_name / external_id)
    if field == "preferred_store":
        # Smart detection: if value looks like UUID, use external_id, otherwise use name
        is_uuid = False
        if isinstance(value, str):
            v = value.strip()
            if len(v) >= 32 and v.count("-") >= 4:
                is_uuid = True
        elif isinstance(value, (list, tuple)) and value:
            # Check first element to guess type
            v = str(value[0]).strip()
            if len(v) >= 32 and v.count("-") >= 4:
                is_uuid = True
        
        column = User.preferred_store_external_id if is_uuid else User.preferred_store_name
        
        if operator in {"in", "not_in"} and not isinstance(value, (list, tuple)):
            value = [v.strip() for v in str(value).split(",") if v.strip()]
        
        # If filtering by name and operator is equals, use ILIKE for flexibility
        if not is_uuid and operator == "equals" and isinstance(value, str):
             operator = "ilike" 
            
    elif field == "preferred_store_name":
        column = User.preferred_store_name
        if operator in {"in", "not_in"} and not isinstance(value, (list, tuple)):
            value = [v.strip() for v in str(value).split(",") if v.strip()]
        # Use ILIKE for flexibility
        if operator == "equals" and isinstance(value, str):
             operator = "ilike" 
            
    elif field == "preferred_store_external_id":
        column = User.preferred_store_external_id
        if operator in {"in", "not_in"} and not isinstance(value, (list, tuple)):
            value = [v.strip() for v in str(value).split(",") if v.strip()]

    elif field == "secondary_store":
        column = User.secondary_store_name
        if operator in {"in", "not_in"} and not isinstance(value, (list, tuple)):
            value = [v.strip() for v in str(value).split(",") if v.strip()]
        # Use ILIKE for flexibility
        if operator == "equals" and isinstance(value, str):
             operator = "ilike"

    elif field == "exclude_segment":
        # Expecting a list of segment IDs or segment names.
        # The UI stores IDs, but older rules could contain typed names.
        if isinstance(value, str) and ',' in value:
             raw_values = [v.strip() for v in value.split(',') if v.strip()]
        else:
             raw_values = value if isinstance(value, (list, tuple, set)) else [value]

        segment_ids = []
        segment_names = []
        for v in raw_values:
            v_str = str(v).strip()
            if not v_str:
                continue
            try:
                segment_ids.append(uuid.UUID(v_str))
            except (ValueError, TypeError):
                segment_names.append(v_str)
        
        if not segment_ids and not segment_names:
            return None, False

        segment_clause = None
        if segment_ids:
            segment_clause = UserSegment.segment_id.in_(segment_ids)
        if segment_names:
            names_subq = select(CustomerSegment.id).where(CustomerSegment.name.in_(segment_names))
            name_clause = UserSegment.segment_id.in_(names_subq)
            segment_clause = sqlalchemy.or_(segment_clause, name_clause) if segment_clause is not None else name_clause

        if segment_clause is None:
            return None, False

        subq = select(UserSegment.user_id).where(segment_clause)
        
        # Exclude these users
        return (~User.id.in_(subq)), False

    # Special condition: "only_store" (Exclusive Store)
    elif field == "only_store":
        from sqlalchemy import select as _sel, func, or_, and_
        # Resolve target IDs/Names
        raw_values = value if isinstance(value, (list, tuple, set)) else [value]
        raw_values = [v for v in raw_values if v is not None and str(v).strip()]
        if not raw_values:
            return None, False
            
        ids: list[str] = []
        names: list[str] = []
        for v in raw_values:
            vv = str(v).strip()
            # Basic UUID check or just treat as ID if it looks like one
            if len(vv) >= 32 and vv.count("-") >= 4:
                ids.append(vv)
            else:
                names.append(vv)
        
        target_ids_clause = None
        if ids:
            target_ids_clause = PurchaseHistory.store_id_1c.in_(ids)
            
        if names:
            try:
                from app.models.store import Store
                # Find IDs for these names
                name_q = _sel(Store.external_id).where(or_(*[Store.name.ilike(f"%{n}%") for n in names]))
                if target_ids_clause is not None:
                    target_ids_clause = or_(target_ids_clause, PurchaseHistory.store_id_1c.in_(name_q))
                else:
                    target_ids_clause = PurchaseHistory.store_id_1c.in_(name_q)
            except Exception:
                pass
                
        if target_ids_clause is None:
            return None, False

        # 1. Users who bought at target store(s)
        # We need distinct user_ids who satisfy the store condition
        stmt_target = _sel(PurchaseHistory.user_id).where(target_ids_clause).distinct()
        
        # 2. Users who have exactly 1 distinct store in their history
        stmt_exclusive = (
            _sel(PurchaseHistory.user_id)
            .group_by(PurchaseHistory.user_id)
            .having(func.count(func.distinct(PurchaseHistory.store_id_1c)) == 1)
        )
        
        # Combine: User must be in BOTH sets
        # (Bought at target) AND (Bought at only 1 store)
        return and_(User.id.in_(stmt_target), User.id.in_(stmt_exclusive)), False

    elif field == "within_last_days":
        # ...
        pass

    elif field == "rfm_score_sum":
        from sqlalchemy import cast, Integer
        try:
            # Postgres specific: accessing JSONB fields as text and casting to int
            # COALESCE logic is handled by the fact that if any is null, the sum might be null, 
            # so we should probably handle that if needed, but for now simple sum
            r = cast(User.rfm_score['r_score'].astext, Integer)
            f = cast(User.rfm_score['f_score'].astext, Integer)
            m = cast(User.rfm_score['m_score'].astext, Integer)
            return ((r + f + m) >= value), False
        except Exception:
            return None, False

    # Define which fields require a JOIN with PurchaseHistory
    purchase_history_fields = {
        'purchase_date', 'store_id_1c', 'product_id', 'product_id_1c', 
        'product_article', 'product_name', 'quantity', 'price', 
        'total_amount', 'category', 'brand'
    }
    
    needs_join = field in purchase_history_fields
    target_table = PurchaseHistory if needs_join else User
    
    # Only set column from target_table if it wasn't already set (e.g. for virtual fields)
    if 'column' not in locals():
        column = getattr(target_table, field, None)
    
    # Специальное условие: фильтр по магазину последней покупки
    if field in ("last_store_id_1c", "last_store_name"):
        from sqlalchemy import exists, and_, select as _sel, func, or_
        from sqlalchemy.orm import aliased
        # Ожидаем строку или список строк
        raw_values = value if isinstance(value, (list, tuple, set)) else [value]
        raw_values = [v for v in raw_values if v is not None and str(v).strip()]
        if not raw_values:
            return None, False
        # Разрешаем ввод названий: сопоставляем со Store.name -> external_id
        ids: list[str] = []
        names: list[str] = []
        for v in raw_values:
            vv = str(v).strip()
            # If field is specifically last_store_name, treat as name even if it looks like ID (unlikely but possible)
            # Otherwise auto-detect
            if field == "last_store_name":
                 names.append(vv)
            elif len(vv) >= 32 and vv.count("-") >= 4:
                ids.append(vv)
            else:
                names.append(vv)
        if names:
            try:
                from app.models.store import Store
                name_rows = await_db_lookup = False  # placeholder for static analyzers
            except Exception:
                pass
        # Для надёжности строим подзапрос max(...) явно с FROM purchase_history
        ph_max = aliased(PurchaseHistory)
        ph_last = aliased(PurchaseHistory)
        max_date_subq = (
            _sel(func.max(ph_max.purchase_date))
            .select_from(ph_max)
            .where(ph_max.user_id == User.id)
            .correlate(User)
        ).scalar_subquery()
        # Коррелированный EXISTS на «последний чек»
        # purchase_history.store_id_1c IN (:ids) OR, если переданы названия, IN (выбранные по имени IDs)
        store_filter = None
        if ids:
            store_filter = ph_last.store_id_1c.in_(ids)
        # Если пришли названия — сделаем сопоставление Name->IDs за один запрос
        if names:
            try:
                from app.models.store import Store
                name_q = _sel(Store.external_id).where(or_(*[Store.name.ilike(f"%{n}%") for n in names]))
                store_filter = or_(store_filter if store_filter is not None else False, ph_last.store_id_1c.in_(name_q))
            except Exception:
                # Если не удалось сопоставить — оставим как есть (не применяем название)
                pass
        if store_filter is None:
            return None, False
        clause = exists(
            _sel(1)
            .select_from(ph_last)
            .where(
                and_(
                    ph_last.user_id == User.id,
                    ph_last.purchase_date == max_date_subq,
                    store_filter,
                )
            )
            .correlate(User)
        )
        return clause, False
    
    if column is None:
        # Field not found
        return None, needs_join

    # Special handling for Gender: map "F"/"M" to "female"/"male"
    if field == "gender" and operator in ("equals", "in"):
        if operator == "equals" and isinstance(value, str):
            v_upper = value.upper().strip()
            if v_upper == "F":
                value = "female"
            elif v_upper == "M":
                value = "male"
        elif operator == "in" and isinstance(value, (list, tuple)):
            new_values = []
            for v in value:
                s = str(v).upper().strip()
                if s == "F":
                    new_values.append("female")
                elif s == "M":
                    new_values.append("male")
                else:
                    new_values.append(v)
            value = new_values

    # Normalize value types for specific columns/operators
    try:
        from sqlalchemy import DateTime
        is_datetime_column = hasattr(column, "type") and isinstance(getattr(column, "type", None), DateTime.__class__) or getattr(column, "type", None).__class__.__name__ == "DateTime"
    except Exception:
        is_datetime_column = False

    # Try to coerce date strings like 'YYYY-MM-DD' into datetime for comparisons
    if isinstance(value, str) and is_datetime_column and operator in {">=", "<=", ">", "<"}:
        try:
            # Handle SQL-like intervals from AI agents (e.g. "NOW() - INTERVAL '6 months'")
            v_upper = value.upper()
            if "NOW" in v_upper and "INTERVAL" in v_upper:
                import re
                from datetime import datetime, timedelta
                # Extract number and unit
                m = re.search(r"INTERVAL\s+'?(\d+)\s*(months?|days?|years?|weeks?)'?", value, re.IGNORECASE)
                if m:
                    num = int(m.group(1))
                    unit = m.group(2).lower()
                    now = datetime.utcnow()
                    
                    if "month" in unit:
                        dt = now - timedelta(days=num * 30)
                    elif "year" in unit:
                        dt = now - timedelta(days=num * 365)
                    elif "week" in unit:
                        dt = now - timedelta(weeks=num)
                    else:
                        dt = now - timedelta(days=num)
                    
                    # Replace value with calculated datetime
                    value = dt
            
            # Standard ISO format handling
            elif len(value) >= 10:
                from datetime import datetime, timezone
                # Handle dates without time
                if len(value) == 10:
                    parsed = datetime.fromisoformat(value)
                else:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                value = parsed
        except Exception:
            # Leave as-is; the DB may reject and the caller will see a 400
            pass

    # Numeric handling: coerce string numbers to actual numbers
    try:
        from sqlalchemy import Integer, Float, Numeric, BigInteger, SmallInteger
        col_type = getattr(column, "type", None)
        is_numeric = False
        if col_type is not None:
             is_numeric = isinstance(col_type, (Integer, Float, Numeric, BigInteger, SmallInteger)) or \
                          col_type.__class__.__name__ in ('Integer', 'Float', 'Numeric', 'BigInteger', 'SmallInteger')
        
        if is_numeric and isinstance(value, str):
             # Simple check if it looks like a number
             v_clean = value.strip()
             if v_clean.replace('.', '', 1).isdigit():
                 try:
                     if '.' in v_clean:
                         value = float(v_clean)
                     else:
                         value = int(v_clean)
                 except:
                     pass
    except Exception:
        pass

    # Normalize list-based operators
    if operator in {"in", "not_in"} and not isinstance(value, (list, tuple)):
        value = [v.strip() for v in str(value).split(",") if v.strip()]

    # Convert monetary fields from Rubles to Kopecks
    if field in {'total_spent', 'average_check', 'price', 'total_amount'}:
        def to_kopecks(v):
            try:
                return int(float(v) * 100)
            except (ValueError, TypeError):
                return v

        if isinstance(value, (list, tuple)):
            value = [to_kopecks(v) for v in value]
        else:
            value = to_kopecks(value)

    # Build the condition based on the operator
    if operator == "equals":
        return (column == value), needs_join
    elif operator == ">=":
        return (column >= value), needs_join
    elif operator == "<=":
        return (column <= value), needs_join
    elif operator == ">":
        return (column > value), needs_join
    elif operator == "<":
        return (column < value), needs_join
    elif operator == "contains":
        if isinstance(value, str):
            return (column.ilike(f"%{value}%")), needs_join
        return (column.contains(value)), needs_join
    elif operator == "ilike":
        # Case-insensitive partial match
        return (column.ilike(f"%{value}%")), needs_join
    elif operator == "in":
        return (column.in_(value)), needs_join
    elif operator == "not_in":
        return (~column.in_(value)), needs_join
    elif operator == "within_last_days":
        # Special operator for date fields
        if field in ['last_purchase_date', 'purchase_date']:
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=value)
            return (column >= cutoff_date), needs_join
        else:
            return None, needs_join
    else:
        # Unknown operator
        return None, needs_join

    if not clauses:
        return None

    if logic == "AND":
        return sqlalchemy.and_(*clauses)
    else:
        return sqlalchemy.or_(*clauses)

@router.get("/available-fields", response_model=Dict[str, List[Dict[str, str]]])
async def get_available_fields():
    """
    Returns a list of available fields for segmentation.
    """
    user_fields = [
        {"name": "persona", "type": "string", "label": "Персона"},
        {"name": "id", "type": "string", "label": "ID покупателя"},
        {"name": "city", "type": "string", "label": "Город"},
        {"name": "gender", "type": "string", "label": "Пол"},
        {"name": "preferred_store", "type": "string", "label": "Предпочитаемый магазин (по истории)"},
        {"name": "preferred_store_name", "type": "string", "label": "Предпочитаемый магазин (Название)"},
        {"name": "preferred_store_external_id", "type": "string", "label": "Предпочитаемый магазин (ID)"},
        {"name": "secondary_store", "type": "string", "label": "Второй предпочитаемый магазин"},
        {"name": "only_store", "type": "string", "label": "Только этот магазин (эксклюзивно)"},
        {"name": "exclude_segment", "type": "string", "label": "Исключить покупателей из сегмента"},
        {"name": "loyalty_points", "type": "number", "label": "Баллы лояльности"},
        {"name": "total_purchases", "type": "number", "label": "Общее количество покупок"},
        {"name": "total_spent", "type": "number", "label": "Общая сумма покупок"},
        {"name": "average_check", "type": "number", "label": "Средний чек"},
        {"name": "last_purchase_date", "type": "date", "label": "Дата последней покупки"},
    ]

    purchase_history_fields = [
        {"name": "purchase_date", "type": "date", "label": "Дата покупки"},
        {"name": "store_id_1c", "type": "string", "label": "ID магазина"},
        {"name": "last_store_id_1c", "type": "string", "label": "Последний магазин (ID)"},
        {"name": "last_store_name", "type": "string", "label": "Последний магазин (Название)"},
        {"name": "product_name", "type": "string", "label": "Название товара"},
        {"name": "product_article", "type": "string", "label": "Артикул товара"},
        {"name": "product_id_1c", "type": "string", "label": "ID товара 1С"},
        {"name": "category", "type": "string", "label": "Категория товара"},
        {"name": "brand", "type": "string", "label": "Бренд товара"},
        {"name": "price", "type": "number", "label": "Цена товара"},
        {"name": "total_amount", "type": "number", "label": "Сумма покупки"},
    ]

    return {
        "user": user_fields,
        "purchase_history": purchase_history_fields
    }

@router.post("/segments", response_model=SegmentOut)
async def create_segment(segment_in: SegmentCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new customer segment.
    """
    logger.info(f"Creating new segment: {segment_in.name}")
    
    # Check if a segment with the same name already exists
    existing_stmt = select(CustomerSegment).where(CustomerSegment.name == segment_in.name)
    existing_result = await db.execute(existing_stmt)
    existing_segment = existing_result.scalar_one_or_none()
    if existing_segment:
        logger.warning(f"Segment creation failed: segment with name '{segment_in.name}' already exists")
        raise HTTPException(status_code=400, detail="Segment with this name already exists")

    # Calculate customer count for the new segment
    try:
        base_stmt, _ = _build_select_for_rules(segment_in.rules.dict())
        subq = base_stmt.subquery()
        count_result = await db.execute(select(func.count()).select_from(subq))
        customer_count = int(count_result.scalar() or 0)
        logger.info(f"Calculated customer count for new segment '{segment_in.name}': {customer_count}")
    except Exception as e:
        logger.error(f"Error calculating segment count for '{segment_in.name}': {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error calculating segment count: {str(e)}")

    # Create the new segment
    new_segment = CustomerSegment(
        id=uuid.uuid4(),
        name=segment_in.name,
        description=segment_in.description,
        rules=segment_in.rules.dict(),
        customer_count=customer_count,
        is_auto_generated=False,  # This is a manually created segment
        is_active=True
    )
    
    db.add(new_segment)
    await db.flush()
    customer_count = await materialize_segment_members(db, new_segment.id, new_segment.rules, assigned_by="manual")
    new_segment.customer_count = customer_count
    await db.commit()
    await db.refresh(new_segment)
    
    logger.info(f"Successfully created segment '{segment_in.name}' with ID {new_segment.id}")

    return SegmentOut(
        id=str(new_segment.id),
        name=new_segment.name,
        description=new_segment.description,
        rules=_normalize_to_segment_rules(new_segment.rules, bool(getattr(new_segment, "is_auto_generated", False))),
        customer_count=new_segment.customer_count,
        is_auto_generated=new_segment.is_auto_generated,
        created_at=new_segment.created_at.isoformat(),
        updated_at=new_segment.updated_at.isoformat() if new_segment.updated_at else None
    )

@router.get("/segments", response_model=List[SegmentOut])
async def get_segments(db: AsyncSession = Depends(get_db)):
    """
    Get all customer segments.
    """
    result = await db.execute(select(CustomerSegment))
    segments = result.scalars().all()
    
    return [
        SegmentOut(
            id=str(segment.id),
            name=segment.name,
            description=segment.description,
            rules=_normalize_to_segment_rules(segment.rules, bool(getattr(segment, "is_auto_generated", False))),
            customer_count=segment.customer_count,
            is_auto_generated=segment.is_auto_generated,
            created_at=segment.created_at.isoformat(),
            updated_at=segment.updated_at.isoformat() if segment.updated_at else None
        )
        for segment in segments
    ]

@router.get("/segments/{segment_id}", response_model=SegmentOut)
async def get_segment(segment_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a single customer segment by ID.
    """
    try:
        segment_uuid = uuid.UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid segment ID format")

    result = await db.execute(select(CustomerSegment).where(CustomerSegment.id == segment_uuid))
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    return SegmentOut(
        id=str(segment.id),
        name=segment.name,
        description=segment.description,
        rules=_normalize_to_segment_rules(segment.rules, bool(getattr(segment, "is_auto_generated", False))),
        customer_count=segment.customer_count,
        is_auto_generated=segment.is_auto_generated,
        created_at=segment.created_at.isoformat(),
        updated_at=segment.updated_at.isoformat() if segment.updated_at else None
    )

@router.put("/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(segment_id: str, segment_in: SegmentUpdate, db: AsyncSession = Depends(get_db)):
    """
    Update an existing customer segment.
    """
    logger.info(f"Updating segment {segment_id} with data: {segment_in.dict()}")
    try:
        segment_uuid = uuid.UUID(segment_id)
    except ValueError:
        logger.warning(f"Invalid segment ID format: {segment_id}")
        raise HTTPException(status_code=400, detail="Invalid segment ID format")

    result = await db.execute(select(CustomerSegment).where(CustomerSegment.id == segment_uuid))
    segment = result.scalar_one_or_none()
    if not segment:
        logger.warning(f"Segment not found: {segment_id}")
        raise HTTPException(status_code=404, detail="Segment not found")

    # Update fields if provided
    if segment_in.name is not None:
        # Check if another segment with the new name already exists
        existing_stmt = select(CustomerSegment).where(
            CustomerSegment.name == segment_in.name,
            CustomerSegment.id != segment_uuid
        )
        existing_segment = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing_segment:
            logger.warning(f"Another segment with name '{segment_in.name}' already exists")
            raise HTTPException(status_code=400, detail="Another segment with this name already exists")
        segment.name = segment_in.name

    if segment_in.description is not None:
        segment.description = segment_in.description

    if segment_in.rules is not None:
        segment.rules = segment_in.rules.dict()
        # Recalculate customer count if rules are updated
        try:
            base_stmt, _ = _build_select_for_rules(segment_in.rules.dict())
            subq = base_stmt.subquery()
            count_result = await db.execute(select(func.count()).select_from(subq))
            segment.customer_count = int(count_result.scalar() or 0)
            logger.info(f"Recalculated segment count: {segment.customer_count} customers")
        except Exception as e:
            logger.error(f"Error calculating segment count during update: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Error calculating segment count: {str(e)}")

    segment.updated_at = datetime.utcnow()
    if segment.rules:
        segment.customer_count = await materialize_segment_members(
            db,
            segment.id,
            segment.rules,
            assigned_by="manual" if not segment.is_auto_generated else "ai",
        )
    await db.commit()
    await db.refresh(segment)

    logger.info(f"Successfully updated segment {segment_id}")
    return SegmentOut(
        id=str(segment.id),
        name=segment.name,
        description=segment.description,
        rules=_normalize_to_segment_rules(segment.rules, bool(getattr(segment, "is_auto_generated", False))),
        customer_count=segment.customer_count,
        is_auto_generated=segment.is_auto_generated,
        created_at=segment.created_at.isoformat(),
        updated_at=segment.updated_at.isoformat() if segment.updated_at else None
    )

@router.delete("/segments/{segment_id}", status_code=204)
async def delete_segment(segment_id: str, db: AsyncSession = Depends(get_db)):
    """
    Delete a customer segment.
    """
    logger.info(f"Deleting segment {segment_id}")
    try:
        segment_uuid = uuid.UUID(segment_id)
    except ValueError:
        logger.warning(f"Invalid segment ID format: {segment_id}")
        raise HTTPException(status_code=400, detail="Invalid segment ID format")

    result = await db.execute(select(CustomerSegment).where(CustomerSegment.id == segment_uuid))
    segment = result.scalar_one_or_none()
    if not segment:
        logger.warning(f"Segment not found: {segment_id}")
        raise HTTPException(status_code=404, detail="Segment not found")

    try:
        await db.execute(delete(UserSegment).where(UserSegment.segment_id == segment_uuid))
        await db.execute(delete(CustomerSegment).where(CustomerSegment.id == segment_uuid))
        await db.commit()
    except sqlalchemy.exc.IntegrityError as e:
        await db.rollback()
        logger.error(f"Integrity error while deleting segment {segment_id}: {e}")
        raise HTTPException(
            status_code=400,
            detail="Не удалось удалить сегмент, так как он используется в связанных сущностях (кампынии, отчеты и т.п.).",
        )
    except Exception as e:
        await db.rollback()
        logger.exception(f"Unexpected error while deleting segment {segment_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера при удалении сегмента")

    logger.info(f"Successfully deleted segment {segment_id}")

@router.post("/segments/calculate-count", response_model=Dict[str, int])
async def calculate_segment_count(rules: SegmentRules, db: AsyncSession = Depends(get_db)):
    """
    Calculates the number of customers in a segment based on the provided rules.
    """
    logger.info(f"Calculating segment count for rules: {rules.dict()}")
    try:
        base_stmt, _ = _build_select_for_rules(rules.dict())
        subq = base_stmt.subquery()
        result = await db.execute(select(func.count()).select_from(subq))
        count = int(result.scalar() or 0)
        logger.info(f"Segment count calculated: {count} customers")
        return {"count": count}
    except Exception as e:
        logger.error(f"Error calculating segment count: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error calculating segment count: {str(e)}")

@router.post("/segments/{segment_id}/export", response_model=Dict[str, str])
async def export_segment(segment_id: str, format: str = "csv", db: AsyncSession = Depends(get_db)):
    """
    Export customers from a segment in the specified format (csv or excel).
    """
    try:
        segment_uuid = uuid.UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid segment ID format")

    result = await db.execute(select(CustomerSegment).where(CustomerSegment.id == segment_uuid))
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    if format not in ["csv", "excel"]:
        raise HTTPException(status_code=400, detail="Unsupported export format. Use 'csv' or 'excel'.")

    # Get customers in the segment
    try:
        base_stmt, _ = _build_select_for_rules(segment.rules)
        ids_result = await db.execute(base_stmt)
        customer_ids = [str(uid) for uid in ids_result.scalars().unique().all()]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error getting customers from segment: {str(e)}")

    # Get customer details
    if customer_ids:
        users_result = await db.execute(select(User).where(User.id.in_(customer_ids)))
        customers = users_result.scalars().all()
    else:
        customers = []

    # Prepare data for export
    export_data = []
    for customer in customers:
        export_data.append({
            "ID": str(customer.id),
            "Имя": customer.full_name,
            "Email": customer.email,
            "Телефон": customer.phone,
            "Город": customer.city,
            "Дата рождения": customer.birth_date.isoformat() if getattr(customer, "birth_date", None) else None,
            "Пол": customer.gender,
            "Баллы лояльности": customer.loyalty_points,
            "Количество покупок": customer.total_purchases,
            "Общая сумма покупок": customer.total_spent,
            "Средний чек": customer.average_check,
            "Дата последней покупки": customer.last_purchase_date.isoformat() if customer.last_purchase_date else None,
            "Сегмент": customer.customer_segment
        })

    # Convert to pandas DataFrame
    df = pd.DataFrame(export_data)
    
    # Create file-like object
    output = io.BytesIO()
    
    if format == "csv":
        df.to_csv(output, index=False, encoding='utf-8-sig')
        media_type = "text/csv"
        filename = f"{segment.name}_customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    else:  # excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Customers')
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{segment.name}_customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Seek to beginning of file
    output.seek(0)
    
    # Return file response
    # Build robust Content-Disposition header:
    # - ASCII-only 'filename' fallback to satisfy latin-1 header encoding
    # - RFC 5987 'filename*' with UTF-8 and percent-encoding for correct name in modern browsers
    try:
        import re
        # ASCII-safe fallback
        base_ascii = re.sub(r'[^A-Za-z0-9_.-]+', '_', filename)
        if not base_ascii:
            base_ascii = 'export.csv' if format == 'csv' else 'export.xlsx'
        encoded_filename = quote(filename)
        content_disposition = f"attachment; filename=\"{base_ascii}\"; filename*=UTF-8''{encoded_filename}"
    except Exception:
        # Fallback to minimal safe header
        base_ascii = 'export.csv' if format == 'csv' else 'export.xlsx'
        content_disposition = f"attachment; filename=\"{base_ascii}\""
    return StreamingResponse(
        io.BytesIO(output.getvalue()),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition}
    )


@router.get("/segments/{segment_id}/users", response_model=Dict[str, Any])
async def get_segment_users(segment_id: str, limit: int = 200, db: AsyncSession = Depends(get_db)):
    """
    Возвращает список пользователей, входящих в сегмент, для предпросмотра.
    """
    try:
        segment_uuid = uuid.UUID(segment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid segment ID format")

    result = await db.execute(select(CustomerSegment).where(CustomerSegment.id == segment_uuid))
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    lim = max(1, min(int(limit or 200), 1000))
    rules = segment.rules if isinstance(segment.rules, dict) else {}
    is_auto = getattr(segment, "is_auto_generated", False)
    
    try:
        normalized_model = _normalize_to_segment_rules(rules, is_auto)
        normalized_dict = normalized_model.dict()
        
        # If filters are empty, we might return all users. 
        # For auto-generated segments, empty filters usually means "no criteria met" -> return empty list?
        # But for manual segments, empty filters means "all users".
        # Let's stick to returning what the rules dictate.
        base_stmt, _ = _build_select_for_rules(normalized_dict)
        subq = base_stmt.subquery()
        users_stmt = (
            select(User)
            .where(User.id.in_(select(subq.c.id)), User.is_customer == True)
            .order_by(User.last_purchase_date.desc().nullslast(), User.total_purchases.desc(), User.total_spent.desc())
            .limit(lim)
        )
        users_result = await db.execute(users_stmt)
        users = users_result.scalars().all()

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error loading segment users: {str(e)}")

    payload = [
        {
            "id": str(u.id),
            "full_name": u.full_name,
            "phone": u.phone,
            "city": u.city,
            "birth_date": u.birth_date.isoformat() if getattr(u, "birth_date", None) else None,
            "preferred_store": u.preferred_store_name,
            "gender": u.gender,
            "total_purchases": u.total_purchases,
            "total_spent": u.total_spent,
            "last_purchase_date": u.last_purchase_date.isoformat() if u.last_purchase_date else None,
        }
        for u in users
    ]
    return {"users": payload, "count": len(payload)}
