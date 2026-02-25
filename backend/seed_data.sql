-- SQL скрипт для заполнения тестовыми данными
-- Запуск: Get-Content backend\seed_data.sql | docker exec -i glame_postgres psql -U glame_user -d glame_db

-- Вставляем товары
INSERT INTO products (id, name, brand, price, category, images, tags, description) VALUES
(gen_random_uuid(), 'Колье Antura', 'Antura', 890000, 'necklace', '[]'::jsonb, '["романтичный", "вечерний", "элегантный"]'::jsonb, 'Изысканное колье от Antura для особых случаев'),
(gen_random_uuid(), 'Серьги Uno de 50', 'Uno de 50', 720000, 'earrings', '[]'::jsonb, '["повседневный", "стильный", "уникальный"]'::jsonb, 'Яркие серьги в стиле Uno de 50'),
(gen_random_uuid(), 'Браслет GLAME', 'GLAME', 450000, 'bracelet', '[]'::jsonb, '["минималистичный", "повседневный"]'::jsonb, 'Элегантный браслет для ежедневного ношения')
ON CONFLICT DO NOTHING;

-- Получаем ID товаров для создания образов
DO $$
DECLARE
    product1_id UUID;
    product2_id UUID;
    product3_id UUID;
BEGIN
    SELECT id INTO product1_id FROM products WHERE name = 'Колье Antura' LIMIT 1;
    SELECT id INTO product2_id FROM products WHERE name = 'Серьги Uno de 50' LIMIT 1;
    SELECT id INTO product3_id FROM products WHERE name = 'Браслет GLAME' LIMIT 1;
    
    -- Вставляем образы
    INSERT INTO looks (id, name, product_ids, style, mood, description, image_url) VALUES
    (gen_random_uuid(), 'Романтичный вечер', jsonb_build_array(product1_id::text, product2_id::text), 'романтичный', 'нежный вечер', 'Идеальный образ для романтического свидания', NULL),
    (gen_random_uuid(), 'Повседневный стиль', jsonb_build_array(product3_id::text), 'повседневный', 'уверенный день', 'Стильный образ для ежедневного ношения', NULL)
    ON CONFLICT DO NOTHING;
END $$;
