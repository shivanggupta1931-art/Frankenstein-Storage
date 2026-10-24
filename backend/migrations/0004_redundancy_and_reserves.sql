-- Schema migration 0004_redundancy_and_reserves.sql
-- Adds protection_status and unprotected_reason columns to files table

ALTER TABLE files ADD COLUMN protection_status TEXT DEFAULT NULL;
ALTER TABLE files ADD COLUMN unprotected_reason TEXT DEFAULT NULL;
