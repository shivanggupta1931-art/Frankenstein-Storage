-- Schema migration 0003_cloud_providers.sql
-- Adds provider_type and config columns to drives table for Google Drive and cloud storage support

ALTER TABLE drives ADD COLUMN provider_type TEXT NOT NULL DEFAULT 'local';
ALTER TABLE drives ADD COLUMN config TEXT DEFAULT NULL;
