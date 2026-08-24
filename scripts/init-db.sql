-- Database initialization script for Globexa CRM
-- Creates the test database and extensions

-- Create test database if not exists
SELECT 'CREATE DATABASE globexa_crm_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'globexa_crm_test')\gexec

-- Connect to test database
\c globexa_crm_test;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for fuzzy search (useful for lead search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable pgvector for embeddings (AI Lead Miner)
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE globexa_crm_test TO postgres;
GRANT ALL ON SCHEMA public TO postgres;