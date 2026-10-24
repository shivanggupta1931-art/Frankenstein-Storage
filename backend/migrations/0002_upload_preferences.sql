-- Schema migration 0002_upload_preferences.sql

-- Add storage_mode column to files table if not present
ALTER TABLE files ADD COLUMN storage_mode TEXT NOT NULL DEFAULT 'chunked_parity';

-- Table to store user upload preferences
CREATE TABLE IF NOT EXISTS upload_preferences (
    user_id TEXT PRIMARY KEY,
    preferred_mode TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
