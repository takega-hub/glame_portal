from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


@dataclass(frozen=True)
class ReceiptBundleMatch:
    rule: dict[str, Any]
    direction: str
    matched_key: str
    counterpart_key: str
    counterpart_article: str | None
    counterpart_name: str | None
    counterpart_category: str | None
    counterpart_product: Product | None = None


class ReceiptBundleService:
    """Read-only access to offline receipt bundle analytics."""

    def __init__(
        self,
        db: AsyncSession,
        analysis_dir: Path | None = None,
    ) -> None:
        self.db = db
        backend_dir = Path(__file__).resolve().parents[2]
        self.analysis_dir = analysis_dir or backend_dir / "data" / "receipt_bundle_analysis"

    def latest_report_path(self) -> Path | None:
        if not self.analysis_dir.exists():
            return None
        candidates = sorted(
            self.analysis_dir.glob("receipt_bundles_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def load_latest_report(self) -> dict[str, Any] | None:
        path = self.latest_report_path()
        if not path:
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        payload["_report_path"] = str(path)
        return payload

    @staticmethod
    def product_keys(product: Product) -> set[str]:
        data = getattr(product, "__dict__", {})
        keys: set[str] = set()
        article = data.get("article")
        external_id = data.get("external_id")
        external_code = data.get("external_code")
        name = data.get("name")
        if article:
            keys.add(f"article:{str(article).strip().lower()}")
        if external_id:
            keys.add(f"1c:{str(external_id).strip().lower()}")
        if external_code:
            keys.add(f"article:{str(external_code).strip().lower()}")
        if name:
            keys.add(f"name:{str(name).strip().lower()}")
        return {key for key in keys if key.split(":", 1)[1]}

    async def recommendations_for_product(
        self,
        product: Product,
        limit: int = 6,
        min_score: float = 0.0,
        require_catalog_match: bool = False,
    ) -> tuple[dict[str, Any] | None, list[ReceiptBundleMatch]]:
        report = self.load_latest_report()
        if not report:
            return None, []

        source_keys = self.product_keys(product)
        if not source_keys:
            return report, []

        matches: list[ReceiptBundleMatch] = []
        for rule in report.get("product_pairs") or []:
            left_key = str(rule.get("left_key") or "")
            right_key = str(rule.get("right_key") or "")
            score = float(rule.get("score") or 0.0)
            if score < min_score:
                continue

            if left_key in source_keys:
                matches.append(
                    ReceiptBundleMatch(
                        rule=rule,
                        direction="left_to_right",
                        matched_key=left_key,
                        counterpart_key=right_key,
                        counterpart_article=rule.get("right_article"),
                        counterpart_name=rule.get("right_name"),
                        counterpart_category=rule.get("right_category"),
                    )
                )
            elif right_key in source_keys:
                matches.append(
                    ReceiptBundleMatch(
                        rule=rule,
                        direction="right_to_left",
                        matched_key=right_key,
                        counterpart_key=left_key,
                        counterpart_article=rule.get("left_article"),
                        counterpart_name=rule.get("left_name"),
                        counterpart_category=rule.get("left_category"),
                    )
                )

        matches.sort(
            key=lambda item: (
                float(item.rule.get("score") or 0.0),
                int(item.rule.get("pair_receipts") or 0),
                float(item.rule.get("lift") or 0.0),
            ),
            reverse=True,
        )
        matches = matches[: max(limit * 3, limit)]

        products_by_key = await self._load_counterpart_products(matches)
        enriched: list[ReceiptBundleMatch] = []
        for match in matches:
            product_match = products_by_key.get(match.counterpart_key)
            if require_catalog_match and not product_match:
                continue
            enriched.append(
                ReceiptBundleMatch(
                    rule=match.rule,
                    direction=match.direction,
                    matched_key=match.matched_key,
                    counterpart_key=match.counterpart_key,
                    counterpart_article=match.counterpart_article,
                    counterpart_name=match.counterpart_name,
                    counterpart_category=match.counterpart_category,
                    counterpart_product=product_match,
                )
            )
            if len(enriched) >= limit:
                break

        return report, enriched

    async def _load_counterpart_products(
        self,
        matches: list[ReceiptBundleMatch],
    ) -> dict[str, Product]:
        article_values: set[str] = set()
        onec_values: set[str] = set()
        name_values: set[str] = set()

        for match in matches:
            key = match.counterpart_key
            if key.startswith("article:"):
                article_values.add(key.split(":", 1)[1])
            elif key.startswith("1c:"):
                onec_values.add(key.split(":", 1)[1])
            elif key.startswith("name:"):
                name_values.add(key.split(":", 1)[1])

        conditions = []
        if article_values:
            conditions.append(func.lower(Product.article).in_(article_values))
            conditions.append(func.lower(Product.external_code).in_(article_values))
        if onec_values:
            conditions.append(func.lower(Product.external_id).in_(onec_values))
        if name_values:
            conditions.append(func.lower(Product.name).in_(name_values))

        if not conditions:
            return {}

        result = await self.db.execute(
            select(Product).where(Product.is_active == True, or_(*conditions))
        )
        products = list(result.scalars().all())

        products_by_key: dict[str, Product] = {}
        for product in products:
            for key in self.product_keys(product):
                products_by_key.setdefault(key, product)
        return products_by_key
