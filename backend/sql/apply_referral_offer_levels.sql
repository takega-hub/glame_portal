ALTER TABLE referral_program_members
    ALTER COLUMN program_level SET DEFAULT 'stylish_start',
    ALTER COLUMN points_rate_percent SET DEFAULT 3,
    ALTER COLUMN cash_rate_percent SET DEFAULT 3;

UPDATE referral_program_members
SET
    program_level = 'stylish_start',
    points_rate_percent = 3,
    cash_rate_percent = 3,
    updated_at = NOW()
WHERE program_level IN ('starter', 'cash_eligible')
   OR points_rate_percent = 5
   OR cash_rate_percent = 5;

