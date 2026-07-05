import asyncio
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).limit(10))
        users = result.scalars().all()
        for u in users:
            print(f"ID: {u.id}, Phone: {u.phone}, Is_Customer: {u.is_customer}")

if __name__ == "__main__":
    asyncio.run(main())
