-- Runs once, on first container start, against POSTGRES_DB.
-- Schema itself is owned by Alembic (docs.md: never create_all()).
-- This file only installs extensions, which a migration cannot reliably do
-- because CREATE EXTENSION needs superuser.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
