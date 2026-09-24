#!/usr/bin/env python3
"""Update CRM call results with purchases made within the attribution window."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from app.database.connection import AsyncSessionLocal
from app.services.crm_interaction_attribution_service import CrmInteractionAttributionService


async def update_attribution(window_days: int, apply: bool) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await CrmInteractionAttributionService(db).update_purchase_conversions(
            window_days=window_days,
            commit=False,
        )
        if apply:
            await db.commit()
        else:
            await db.rollback()
    return {**result, "applied": apply}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update CRM interaction conversion results.")
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(update_attribution(window_days=args.window_days, apply=args.apply))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
