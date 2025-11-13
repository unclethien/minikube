-- Migration: Create detection_results table
-- Run this on PostgreSQL database

CREATE TABLE IF NOT EXISTS detection_results (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255),
    detection_count INTEGER,
    detections JSONB,  -- Store detection data as JSONB for efficient querying
    annotated_image BYTEA,  -- Store annotated image as binary data
    image_width INTEGER,
    image_height INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on created_at for faster queries
CREATE INDEX IF NOT EXISTS idx_detection_results_created_at ON detection_results(created_at DESC);

-- Create index on filename for searches
CREATE INDEX IF NOT EXISTS idx_detection_results_filename ON detection_results(filename);

-- Create index on detection_count for analytics
CREATE INDEX IF NOT EXISTS idx_detection_results_count ON detection_results(detection_count);
