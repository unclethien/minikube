-- Phase 1: Add indexed_filename and resolution columns to detection_results table
-- Migration: 002_add_phase1_columns.sql
-- Date: 2025-11-19

-- Add indexed_filename column (generated unique filename)
ALTER TABLE detection_results
ADD COLUMN IF NOT EXISTS indexed_filename VARCHAR(300);

-- Add resolution column (256p, 720p, 1080p)
ALTER TABLE detection_results
ADD COLUMN IF NOT EXISTS resolution VARCHAR(10);

-- Create index on indexed_filename for faster lookups
CREATE INDEX IF NOT EXISTS idx_detection_results_indexed_filename
ON detection_results(indexed_filename);

-- Create index on resolution for filtering
CREATE INDEX IF NOT EXISTS idx_detection_results_resolution
ON detection_results(resolution);

-- Create composite index for resolution + created_at (common query pattern)
CREATE INDEX IF NOT EXISTS idx_detection_results_resolution_created
ON detection_results(resolution, created_at DESC);

-- Update any existing rows with default values (NULL is acceptable)
UPDATE detection_results
SET indexed_filename = COALESCE(indexed_filename, 'legacy_' || id || '.png')
WHERE indexed_filename IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN detection_results.indexed_filename IS 'Generated indexed filename: YYYYMMDD_HHMMSS_<pod>_<index>_<resolution>.png';
COMMENT ON COLUMN detection_results.resolution IS 'Image resolution label: 256p, 720p, or 1080p';
