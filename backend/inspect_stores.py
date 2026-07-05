import os
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func, distinct
from dotenv import load_dotenv

sys.path.append(os.getcwd())
from app.models.user import User

load_dotenv()

async def main():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found")
        return

    if "postgresql://" in database_url and "postgresql+" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://")
    
    engine = create_async_engine(database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:
        # Get unique preferred_store_name for users where city is NULL or empty string
        stmt = select(User.preferred_store_name, func.count(User.id)).where(
            (User.city == None) | (User.city == "")
        ).group_by(User.preferred_store_name).order_by(func.count(User.id).desc())
        
        result = await session.execute(stmt)
        stores = result.all()
        
        print("Unique preferred_store_name for users without city:")
        for store_name, count in stores:
            print(f"'{store_name}': {count} users")

if __name__ == "__main__":
    asyncio.run(main())
