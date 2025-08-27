-- Add missing columns to runs table for Phase-1 run persistence

-- Add vendor column
ALTER TABLE runs ADD COLUMN IF NOT EXISTS vendor VARCHAR(50);

-- Add model column  
ALTER TABLE runs ADD COLUMN IF NOT EXISTS model VARCHAR(100);

-- Add grounded_requested column
ALTER TABLE runs ADD COLUMN IF NOT EXISTS grounded_requested BOOLEAN DEFAULT FALSE;

-- Add json_mode column
ALTER TABLE runs ADD COLUMN IF NOT EXISTS json_mode BOOLEAN DEFAULT FALSE;