-- Creates the draft (staging) schemas, owned by gis_create.
-- Run ONCE on the chameleon target database (CLEANED_POSTGIS_CLOUD_DATABASE)
-- as an admin account (e.g. rb_admin) — not as gis_create.
-- Safe to re-run: existing schemas are left as they are.
-- Afterwards run src/setup_schemas.py (gis_create) to create the tables and the review lock.

BEGIN;

-- An admin that isn't a full superuser can only create a schema owned by gis_create
-- while it is a member of gis_create (otherwise: "must be able to SET ROLE gis_create").
GRANT gis_create TO CURRENT_USER;

CREATE SCHEMA IF NOT EXISTS akwaaba_schema_draft AUTHORIZATION gis_create;
CREATE SCHEMA IF NOT EXISTS buffalo_schema_draft AUTHORIZATION gis_create;
CREATE SCHEMA IF NOT EXISTS colobus_schema_draft AUTHORIZATION gis_create;

-- Membership was only needed for the step above
REVOKE gis_create FROM CURRENT_USER;

COMMIT;

-- Check: three rows, each owned by gis_create
SELECT nspname AS schema, pg_get_userbyid(nspowner) AS owner
FROM pg_namespace
WHERE nspname LIKE '%\_schema\_draft'
ORDER BY 1;
