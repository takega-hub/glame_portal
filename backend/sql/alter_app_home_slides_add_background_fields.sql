ALTER TABLE app_home_slides
  ADD COLUMN IF NOT EXISTS background_mode VARCHAR(16) NOT NULL DEFAULT 'image',
  ADD COLUMN IF NOT EXISTS background_color_hex VARCHAR(7),
  ADD COLUMN IF NOT EXISTS background_color_ral VARCHAR(32);

UPDATE app_home_slides
SET background_mode = 'image'
WHERE background_mode IS NULL OR background_mode = '';
