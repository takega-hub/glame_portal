import os
import sys
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
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
        # Define mappings
        mappings = [
            # Simferopol
            {"city": "Симферополь", "stores": ["Меганом", "Центрум 2"]},
            # Yalta
            {"city": "Ялта", "stores": ["Ялта, Набережная 18"]}
        ]
        
        total_updated = 0
        
        for mapping in mappings:
            city = mapping["city"]
            stores = mapping["stores"]
            
            stmt = update(User).where(
                (User.city == None) | (User.city == ""),
                User.preferred_store_name.in_(stores)
            ).values(city=city)
            
            result = await session.execute(stmt)
            count = result.rowcount
            print(f"Updated {count} users to city '{city}' based on stores {stores}")
            total_updated += count
            
        await session.commit()
        print(f"Total updated: {total_updated}")

if __name__ == "__main__":
    asyncio.run(main())
