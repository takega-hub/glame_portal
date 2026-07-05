import re
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.purchase_history import PurchaseHistory
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category


_ARTICLE_FROM_NAME_RE = re.compile(r",\s*(\d{5,})\s*$")


def _extract_article_from_name(product_name: Optional[str]) -> Optional[str]:
    if not product_name:
        return None
    m = _ARTICLE_FROM_NAME_RE.search(str(product_name).strip())
    if not m:
        return None
    return m.group(1)

def _normalize_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    s = str(name).replace("\u00a0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" \t\r\n\"'“”„«»")
    return s or None


class SalesProductLinkService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_product_external_id(self, product_article: Optional[str], product_name: Optional[str]) -> Optional[str]:
        article = (product_article or "").strip() or _extract_article_from_name(product_name)
        if article:
            res = await self.db.execute(select(Product.external_id).where(Product.article == article).limit(1))
            row = res.first()
            if row:
                ext_id = row[0]
                return str(ext_id) if ext_id else None

        norm_name = _normalize_name(product_name)
        if not norm_name:
            return None

        stmt = (
            select(Product.external_id)
            .where(func.lower(func.btrim(Product.name)) == func.lower(func.btrim(norm_name)))
            .limit(2)
        )
        res2 = await self.db.execute(stmt)
        rows = res2.fetchall()
        if len(rows) != 1:
            return None
        ext_id = rows[0][0]
        return str(ext_id) if ext_id else None

    async def backfill_missing_product_links(
        self,
        sync_batch_id: Optional[str] = None,
        limit: int = 200000,
    ) -> int:
        params = {"batch": sync_batch_id, "limit": int(limit)}
        where_batch = "and sr.sync_batch_id = :batch" if sync_batch_id else ""

        sql = f"""
        with target as (
          select sr.id
          from sales_records sr
          where (sr.product_id is null or sr.product_id = '')
            and (
              (sr.product_article is not null and sr.product_article <> '')
              or (sr.product_name is not null and btrim(sr.product_name) <> '')
              or (sr.product_name is not null and sr.product_name ~ ',\\s*\\d{{5,}}\\s*$')
            )
            {where_batch}
          order by sr.sale_date desc
          limit :limit
        ),
        article_map as (
          select p.article, max(p.external_id) as external_id
          from products p
          where p.external_id is not null and p.article is not null and p.article <> ''
          group by p.article
          having count(*) = 1
        ),
        name_map as (
          select lower(btrim(p.name)) as name_key, max(p.external_id) as external_id
          from products p
          where p.external_id is not null and p.name is not null and btrim(p.name) <> ''
          group by lower(btrim(p.name))
          having count(*) = 1
        ),
        resolved as (
          select
            sr.id,
            coalesce(
              am.external_id,
              nm.external_id
            ) as external_id,
            coalesce(
              nullif(sr.product_article, ''),
              substring(sr.product_name from ',\\s*(\\d{{5,}})\\s*$')
            ) as resolved_article
          from sales_records sr
          left join article_map am on am.article = coalesce(
            nullif(sr.product_article, ''),
            substring(sr.product_name from ',\\s*(\\d{{5,}})\\s*$')
          )
          left join name_map nm on nm.name_key = lower(btrim(sr.product_name))
          where sr.id in (select id from target)
        ),
        upd as (
          update sales_records sr
          set
            product_article = coalesce(
              nullif(sr.product_article, ''),
              r.resolved_article
            ),
            product_id = r.external_id,
            product_name = coalesce(sr.product_name, p.name),
            product_category = coalesce(sr.product_category, p.category),
            product_brand = coalesce(sr.product_brand, p.brand),
            updated_at = now()
          from resolved r
          join products p on p.external_id = r.external_id
          where sr.id = r.id and r.external_id is not null
          returning sr.id
        )
        select count(*) from upd;
        """

        result = await self.db.execute(text(sql), params)
        (count,) = result.one()
        await self.db.commit()
        return int(count or 0)

    async def backfill_missing_purchase_product_links(
        self,
        user_id: Optional[str] = None,
        limit: int = 200000,
    ) -> int:
        params = {"user_id": str(user_id) if user_id else None, "limit": int(limit)}
        where_user = "and ph.user_id = cast(:user_id as uuid)" if user_id else ""

        update_set = """
            product_id = coalesce(ph.product_id, p.id),
            product_id_1c = coalesce(ph.product_id_1c, p.external_id),
            product_article = coalesce(nullif(ph.product_article, ''), p.article, p.external_code),
            product_name = coalesce(nullif(ph.product_name, ''), p.name),
            category = coalesce(ph.category, p.category),
            brand = coalesce(ph.brand, p.brand),
            sync_metadata = (
              coalesce(ph.sync_metadata::jsonb, '{}'::jsonb) || jsonb_build_object(
                'resolved_from_catalog', true,
                'resolved_product_external_id', p.external_id,
                'resolved_barcode', p.barcode
              )
            )::json
        """

        base_target_where = f"""
          where (
              ph.product_id is null
              or ph.product_name is null
              or btrim(ph.product_name) = ''
              or ph.product_article is null
              or btrim(ph.product_article) = ''
              or ph.category is null
              or ph.brand is null
            )
            {{extra_condition}}
            {where_user}
          order by ph.purchase_date desc
          limit :limit
        """

        statements = [
            f"""
            with target as (
              select
                ph.id,
                ph.product_id_1c,
                nullif(ph.sync_metadata->>'Характеристика_Key', '00000000-0000-0000-0000-000000000000') as characteristic_key
              from purchase_history ph
              {base_target_where.format(extra_condition="and ph.product_id_1c is not null and nullif(ph.sync_metadata->>'Характеристика_Key', '00000000-0000-0000-0000-000000000000') is not null")}
            ),
            upd as (
              update purchase_history ph
              set {update_set}
              from target t
              join products p on p.external_id = t.product_id_1c || '#' || t.characteristic_key
              where ph.id = t.id
              returning ph.id
            )
            select count(*) from upd;
            """,
            f"""
            with target as (
              select ph.id, ph.product_id_1c
              from purchase_history ph
              {base_target_where.format(extra_condition="and ph.product_id_1c is not null")}
            ),
            upd as (
              update purchase_history ph
              set {update_set}
              from target t
              join products p on p.external_id = t.product_id_1c
              where ph.id = t.id
              returning ph.id
            )
            select count(*) from upd;
            """,
            f"""
            with target as (
              select ph.id, ph.product_article
              from purchase_history ph
              {base_target_where.format(extra_condition="and nullif(ph.product_article, '') is not null")}
            ),
            article_map as (
              select p.article, min(p.id::text)::uuid as id
              from products p
              where p.article is not null and p.article <> ''
              group by p.article
              having count(*) = 1
            ),
            upd as (
              update purchase_history ph
              set {update_set}
              from target t
              join article_map am on am.article = t.product_article
              join products p on p.id = am.id
              where ph.id = t.id
              returning ph.id
            )
            select count(*) from upd;
            """,
            f"""
            with target as (
              select ph.id, ph.product_article
              from purchase_history ph
              {base_target_where.format(extra_condition="and nullif(ph.product_article, '') is not null")}
            ),
            code_map as (
              select p.external_code, min(p.id::text)::uuid as id
              from products p
              where p.external_code is not null and p.external_code <> ''
              group by p.external_code
              having count(*) = 1
            ),
            upd as (
              update purchase_history ph
              set {update_set}
              from target t
              join code_map cm on cm.external_code = t.product_article
              join products p on p.id = cm.id
              where ph.id = t.id
              returning ph.id
            )
            select count(*) from upd;
            """,
            f"""
            with target as (
              select ph.id, ph.sync_metadata->>'resolved_barcode' as barcode
              from purchase_history ph
              {base_target_where.format(extra_condition="and nullif(ph.sync_metadata->>'resolved_barcode', '') is not null")}
            ),
            barcode_map as (
              select p.barcode, min(p.id::text)::uuid as id
              from products p
              where p.barcode is not null and p.barcode <> ''
              group by p.barcode
              having count(*) = 1
            ),
            upd as (
              update purchase_history ph
              set {update_set}
              from target t
              join barcode_map bm on bm.barcode = t.barcode
              join products p on p.id = bm.id
              where ph.id = t.id
              returning ph.id
            )
            select count(*) from upd;
            """,
        ]

        total = 0
        for sql in statements:
            result = await self.db.execute(text(sql), params)
            (count,) = result.one()
            total += int(count or 0)
            await self.db.commit()

        return total

    async def normalize_purchase_product_fields(
        self,
        user_id: Optional[str] = None,
        limit: int = 200000,
    ) -> int:
        stmt = (
            select(PurchaseHistory, Product.category, Product.brand)
            .outerjoin(Product, PurchaseHistory.product_id == Product.id)
            .order_by(PurchaseHistory.purchase_date.desc())
            .limit(int(limit))
        )
        if user_id:
            stmt = stmt.where(PurchaseHistory.user_id == str(user_id))

        result = await self.db.execute(stmt)
        updated = 0

        for purchase, product_category, product_brand in result.all():
            name = purchase.product_name
            category = derive_purchase_category(name, product_category or purchase.category)
            brand = derive_purchase_brand(name, product_brand or purchase.brand, product_category or purchase.category)

            if category != purchase.category or brand != purchase.brand:
                purchase.category = category
                purchase.brand = brand
                updated += 1

        if updated:
            await self.db.commit()
        return updated

    async def backfill_missing_purchase_product_links_slow(
        self,
        user_id: Optional[str] = None,
        limit: int = 200000,
    ) -> int:
        params = {"user_id": str(user_id) if user_id else None, "limit": int(limit)}
        where_user = "and ph.user_id = cast(:user_id as uuid)" if user_id else ""

        sql = f"""
        with target as (
          select ph.id
          from purchase_history ph
          where (
              ph.product_id is null
              or ph.product_name is null
              or btrim(ph.product_name) = ''
              or ph.product_article is null
              or btrim(ph.product_article) = ''
              or ph.category is null
              or ph.brand is null
            )
            and (
              ph.product_id_1c is not null
              or ph.product_article is not null
              or ph.sync_metadata::jsonb ? 'resolved_barcode'
            )
            {where_user}
          order by ph.purchase_date desc
          limit :limit
        ),
        resolved as (
          select
            ph.id as purchase_id,
            p.id as product_uuid,
            p.external_id,
            p.name,
            p.article,
            p.external_code,
            p.category,
            p.brand,
            p.barcode
          from purchase_history ph
          join target t on t.id = ph.id
          left join lateral (
            select p.*
            from products p
            where
              (
                ph.product_id_1c is not null
                and nullif(ph.sync_metadata->>'Характеристика_Key', '00000000-0000-0000-0000-000000000000') is not null
                and p.external_id = ph.product_id_1c || '#' || nullif(ph.sync_metadata->>'Характеристика_Key', '00000000-0000-0000-0000-000000000000')
              )
              or (ph.product_id_1c is not null and p.external_id = ph.product_id_1c)
              or (
                nullif(ph.product_article, '') is not null
                and (p.article = ph.product_article or p.external_code = ph.product_article)
              )
              or (
                nullif(ph.sync_metadata->>'resolved_barcode', '') is not null
                and p.barcode = ph.sync_metadata->>'resolved_barcode'
              )
            order by
              case
                when ph.product_id_1c is not null
                  and nullif(ph.sync_metadata->>'Характеристика_Key', '00000000-0000-0000-0000-000000000000') is not null
                  and p.external_id = ph.product_id_1c || '#' || nullif(ph.sync_metadata->>'Характеристика_Key', '00000000-0000-0000-0000-000000000000') then 1
                when ph.product_id_1c is not null and p.external_id = ph.product_id_1c then 2
                when nullif(ph.product_article, '') is not null and p.article = ph.product_article then 3
                when nullif(ph.product_article, '') is not null and p.external_code = ph.product_article then 4
                when nullif(ph.sync_metadata->>'resolved_barcode', '') is not null and p.barcode = ph.sync_metadata->>'resolved_barcode' then 5
                else 99
              end,
              p.updated_at desc nulls last,
              p.created_at desc nulls last
            limit 1
          ) p on true
          where p.id is not null
        ),
        upd as (
          update purchase_history ph
          set
            product_id = coalesce(ph.product_id, r.product_uuid),
            product_id_1c = coalesce(ph.product_id_1c, r.external_id),
            product_article = coalesce(nullif(ph.product_article, ''), r.article, r.external_code),
            product_name = coalesce(nullif(ph.product_name, ''), r.name),
            category = coalesce(ph.category, r.category),
            brand = coalesce(ph.brand, r.brand),
            sync_metadata = (
              coalesce(ph.sync_metadata::jsonb, '{{}}'::jsonb) || jsonb_build_object(
              'resolved_from_catalog', true,
              'resolved_product_external_id', r.external_id,
              'resolved_barcode', r.barcode
              )
            )::json
          from resolved r
          where ph.id = r.purchase_id
          returning ph.id
        )
        select count(*) from upd;
        """

        result = await self.db.execute(text(sql), params)
        (count,) = result.one()
        await self.db.commit()
        return int(count or 0)
