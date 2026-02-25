"""
Скрипт для импорта исходных данных в БД
"""
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.look import Look
from app.database.connection import SessionLocal


def seed_products(db: Session):
    """Импорт товаров"""
    # Примеры товаров GLAME
    products_data = [
        {
            "name": "Колье Antura",
            "brand": "Antura",
            "price": 890000,  # в копейках
            "category": "necklace",
            "tags": ["романтичный", "вечерний", "элегантный"],
            "description": "Изысканное колье от Antura для особых случаев",
            "images": []
        },
        {
            "name": "Серьги Uno de 50",
            "brand": "Uno de 50",
            "price": 720000,
            "category": "earrings",
            "tags": ["повседневный", "стильный", "уникальный"],
            "description": "Яркие серьги в стиле Uno de 50",
            "images": []
        },
        {
            "name": "Браслет GLAME",
            "brand": "GLAME",
            "price": 450000,
            "category": "bracelet",
            "tags": ["минималистичный", "повседневный"],
            "description": "Элегантный браслет для ежедневного ношения",
            "images": []
        }
    ]
    
    for product_data in products_data:
        existing = db.query(Product).filter(Product.name == product_data["name"]).first()
        if not existing:
            product = Product(**product_data)
            db.add(product)
    
    db.commit()
    print("Products seeded successfully")


def seed_looks(db: Session):
    """Импорт образов"""
    # Получаем товары для создания образов
    products = db.query(Product).all()
    if not products:
        print("No products found. Please seed products first.")
        return
    
    looks_data = [
        {
            "name": "Романтичный вечер",
            "product_ids": [str(products[0].id), str(products[1].id)] if len(products) >= 2 else [],
            "style": "романтичный",
            "mood": "нежный вечер",
            "description": "Идеальный образ для романтического свидания",
            "image_url": None
        },
        {
            "name": "Повседневный стиль",
            "product_ids": [str(products[2].id)] if len(products) >= 3 else [],
            "style": "повседневный",
            "mood": "уверенный день",
            "description": "Стильный образ для ежедневного ношения",
            "image_url": None
        }
    ]
    
    for look_data in looks_data:
        existing = db.query(Look).filter(Look.name == look_data["name"]).first()
        if not existing:
            look = Look(**look_data)
            db.add(look)
    
    db.commit()
    print("Looks seeded successfully")


def run_seeds():
    """Запуск всех seeds"""
    db = SessionLocal()
    try:
        seed_products(db)
        seed_looks(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_seeds()
