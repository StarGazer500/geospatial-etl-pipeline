"""
Run once with gis_create credentials to create table structures and grants.
Edit SCHEMA_TABLE_SCHEMAS below to adjust column names and types before running.
The ETL pipeline (update mode) will then TRUNCATE + INSERT into these tables.
"""
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(__file__))

from connection_util import DatabaseConnection

load_dotenv()

# ── Roles to grant access after table creation ────────────────────────────────

GRANT_ROLES = {
    'gis_viewer': 'SELECT',
    'gis_update': 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE',
}

# ── Per-schema table definitions ──────────────────────────────────────────────
# Each table: list of (column_name, postgresql_type)
# 'id' SERIAL PRIMARY KEY is added automatically — do not include it.

_COMPARTMENTS = [
    ('compartment_id',  'CHARACTER VARYING'),
    ('geom',            'geometry(MultiPolygon, 4326)'),
    ('lease_id',        'CHARACTER VARYING'),
    ('area_ha',         'DOUBLE PRECISION'),
    ('n_psp_target',    'INTEGER'),
    ('year_created',    'INTEGER'),
]

_SUBCOMPARTMENTS = [
    ('subcompartment_id',   'CHARACTER VARYING'),
    ('geom',                'geometry(MultiPolygon, 4326)'),
    ('area_ha',             'DOUBLE PRECISION'),
    ('compartment_id',      'CHARACTER VARYING'),
    ('treatment_type',      'CHARACTER VARYING'),
    ('planting_status',     'CHARACTER VARYING'),
    ('year_planted',        'INTEGER'),
    ('planting_type',       'CHARACTER VARYING'),
    ('lp_start_date',       'DATE'),
    ('plant_start_date',    'DATE'),
    ('sph',                 'INTEGER'),
]

_UNPLANTABLE_AREAS = [
    ('unplantable_id',  'CHARACTER VARYING'),
    ('compartment_id',  'CHARACTER VARYING'),
    ('geom',            'geometry(MultiPolygon, 4326)'),
    ('area_ha',         'DOUBLE PRECISION'),
    ('damage_type',     'CHARACTER VARYING'),
]

_FIREBREAKS = [
    ('firebreak_id',    'CHARACTER VARYING'),
    ('lease_id',        'CHARACTER VARYING'),
    ('geom',            'geometry(MultiPolygon, 4326)'),
    ('area_ha',         'DOUBLE PRECISION'),
    ('perimeter',       'DOUBLE PRECISION'),
]

_PROTECTED_AREAS = [
    ('protected_area_id',   'CHARACTER VARYING'),
    ('geom',                'geometry(MultiPolygon, 4326)'),
    ('area_ha',             'DOUBLE PRECISION'),
    ('landcover',           'CHARACTER VARYING'),
]

_ROAD_BUFFERS = [
    ('road_buffer_id',  'CHARACTER VARYING'),
    ('geom',            'geometry(MultiPolygon, 4326)'),
    ('area_ha',         'DOUBLE PRECISION'),
]

_LEASE_AREAS_STRATUM = [
    ('lease_stratum_id',                'CHARACTER VARYING'),
    ('geom',                            'geometry(MultiPolygon, 4326)'),
    ('category',                        'CHARACTER VARYING'),
    ('subcategory',                     'CHARACTER VARYING'),
    ('treatment',                       'CHARACTER VARYING'),
    ('planting_type',                   'CHARACTER VARYING'),
    ('year_planted',                    'INTEGER'),
    ('plant_start_date',                'DATE'),
    ('lp_start_date',                   'DATE'),
    ('area_ha',                         'DOUBLE PRECISION'),
    ('sph',                             'INTEGER'),
    ('compartment_id',                  'CHARACTER VARYING'),
    ('source_layer',                    'CHARACTER VARYING'),
    ('silviculture_operation_status',   'CHARACTER VARYING'),
]

# rb_roads: akwaaba/colobus have no road_type; buffalo schemas have road_type
_RB_ROADS_BASE = [
    ('road_id',                 'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiLineString, 4326)'),
    ('road_class',              'CHARACTER VARYING'),
    ('condition',               'CHARACTER VARYING'),
    ('road_treatment_status',   'CHARACTER VARYING'),
    ('length_km',               'DOUBLE PRECISION'),
    ('date_created',            'DATE'),
]

_RB_ROADS_BUFFALO = [
    ('road_id',                 'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiLineString, 4326)'),
    ('road_class',              'CHARACTER VARYING'),
    ('road_type',               'CHARACTER VARYING'),
    ('condition',               'CHARACTER VARYING'),
    ('road_treatment_status',   'CHARACTER VARYING'),
    ('length_km',               'DOUBLE PRECISION'),
    ('date_created',            'DATE'),
]

# leased_areas differs per schema
_LEASED_AREAS_AKWAABA = [
    ('lease_id',                'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiPolygon, 4326)'),
    ('geom_status',             'CHARACTER VARYING'),
    ('lease_status',            'CHARACTER VARYING'),
    ('year_leased',             'INTEGER'),
    ('year_requested',          'INTEGER'),
    ('agreement_type',          'CHARACTER VARYING'),
    ('area_ha',                 'DOUBLE PRECISION'),
    ('link_to_lease_document',  'CHARACTER VARYING'),
]

_LEASED_AREAS_BUFFALO_VERSIONED = [   # baseline / operational
    ('lease_id',                'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiPolygon, 4326)'),
    ('geom_status',             'CHARACTER VARYING'),
    ('lease_status',            'CHARACTER VARYING'),
    ('year_leased',             'INTEGER'),
    ('area_ha',                 'DOUBLE PRECISION'),
    ('link_to_lease_document',  'CHARACTER VARYING'),
    ('date_registered',         'DATE'),
]

_LEASED_AREAS_BASE = [                # buffalo_schema, colobus_schema
    ('lease_id',                'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiPolygon, 4326)'),
    ('geom_status',             'CHARACTER VARYING'),
    ('lease_status',            'CHARACTER VARYING'),
    ('year_leased',             'INTEGER'),
    ('area_ha',                 'DOUBLE PRECISION'),
    ('link_to_lease_document',  'CHARACTER VARYING'),
]


SCHEMA_TABLE_SCHEMAS = {

    'akwaaba_schema': {
        'leased_areas':         _LEASED_AREAS_AKWAABA,
        'compartments':         _COMPARTMENTS,
        'subcompartments':      _SUBCOMPARTMENTS,
        'unplantable_areas':    _UNPLANTABLE_AREAS,
        'rb_roads':             _RB_ROADS_BASE,
        'protected_areas':      _PROTECTED_AREAS,
        'lease_areas_stratum':  _LEASE_AREAS_STRATUM,
    },

    'buffalo_schema': {
        'leased_areas':         _LEASED_AREAS_BASE,
        'compartments':         _COMPARTMENTS,
        'subcompartments':      _SUBCOMPARTMENTS,
        'unplantable_areas':    _UNPLANTABLE_AREAS,
        'rb_roads':             _RB_ROADS_BUFFALO,
        'firebreaks':           _FIREBREAKS,
        'protected_areas':      _PROTECTED_AREAS,
        'lease_areas_stratum':  _LEASE_AREAS_STRATUM,
    },

    'buffalo_schema_baseline': {
        'leased_areas':         _LEASED_AREAS_BUFFALO_VERSIONED,
        'compartments':         _COMPARTMENTS,
        'subcompartments':      _SUBCOMPARTMENTS,
        'unplantable_areas':    _UNPLANTABLE_AREAS,
        'rb_roads':             _RB_ROADS_BUFFALO,
        'firebreaks':           _FIREBREAKS,
        'protected_areas':      _PROTECTED_AREAS,
        'lease_areas_stratum':  _LEASE_AREAS_STRATUM,
    },

    'buffalo_schema_operational': {
        'leased_areas':         _LEASED_AREAS_BUFFALO_VERSIONED,
        'compartments':         _COMPARTMENTS,
        'subcompartments':      _SUBCOMPARTMENTS,
        'unplantable_areas':    _UNPLANTABLE_AREAS,
        'rb_roads':             _RB_ROADS_BUFFALO,
        'firebreaks':           _FIREBREAKS,
        'protected_areas':      _PROTECTED_AREAS,
        'lease_areas_stratum':  _LEASE_AREAS_STRATUM,
    },

    'colobus_schema': {
        'leased_areas':         _LEASED_AREAS_BASE,
        'compartments':         _COMPARTMENTS,
        'subcompartments':      _SUBCOMPARTMENTS,
        'unplantable_areas':    _UNPLANTABLE_AREAS,
        'rb_roads':             _RB_ROADS_BASE,
        'firebreaks':           _FIREBREAKS,
        'protected_areas':      _PROTECTED_AREAS,
        'road_buffers':         _ROAD_BUFFERS,
        'lease_areas_stratum':  _LEASE_AREAS_STRATUM,
    },
}


# ── Core functions ─────────────────────────────────────────────────────────────

def create_tables_for_schema(conn, schema):
    table_schemas = SCHEMA_TABLE_SCHEMAS.get(schema)
    if not table_schemas:
        print(f'  No schema definition found for {schema} — skipping')
        return

    for table_name, columns in table_schemas.items():
        col_defs = ',\n    '.join(f'"{col}" {dtype}' for col, dtype in columns)
        full_table = f'"{schema}"."{table_name}"'

        with conn['sync'].connect() as connection:
            # Create table with all columns on first run
            connection.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    id SERIAL PRIMARY KEY,
                    {col_defs}
                )
            """))

            # Fetch existing column types for this table
            existing = {
                row[0]: row[1].lower()
                for row in connection.execute(text(f"""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = '{schema}' AND table_name = '{table_name}'
                """)).fetchall()
            }

            for col, dtype in columns:
                # Add column if missing
                connection.execute(text(
                    f'ALTER TABLE {full_table} ADD COLUMN IF NOT EXISTS "{col}" {dtype}'
                ))
                # Alter type if it changed (skip geometry — requires special casting)
                if 'geometry' not in dtype.lower() and col in existing:
                    target = dtype.lower().split('(')[0].strip()
                    if existing[col] != target:
                        connection.execute(text(
                            f'ALTER TABLE {full_table} ALTER COLUMN "{col}" TYPE {dtype} USING "{col}"::{dtype}'
                        ))
                        print(f'    Altered {col}: {existing[col]} → {dtype}')

            for role, privileges in GRANT_ROLES.items():
                connection.execute(text(f'GRANT {privileges} ON {full_table} TO {role}'))
                connection.execute(text(
                    f'GRANT USAGE, SELECT ON SEQUENCE "{schema}"."{table_name}_id_seq" TO {role}'
                ))
            connection.commit()
        print(f'  Ready: {full_table}')


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    chameleon_conn = DatabaseConnection.connect_to_target_postgis_database(
        host=os.getenv('CHAMELEON_TARGET_HOST'),
        database_name=os.getenv('CHAMELEON_TARGET_DATABASE_NAME'),
        port=os.getenv('CHAMELEON_TARGET_PORT'),
        username=os.getenv('GIS_CREATE_USERNAME'),
        password=os.getenv('GIS_CREATE_PASSWORD'),
    )

    project_conn = DatabaseConnection.connect_to_target_postgis_database(
        host=os.getenv('PROJECT_LEVEL_TARGET_HOST'),
        database_name=os.getenv('PROJECT_LEVEL_TARGET_DATABASE_NAME'),
        port=os.getenv('PROJECT_LEVEL_TARGET_PORT'),
        username=os.getenv('GIS_CREATE_USERNAME'),
        password=os.getenv('GIS_CREATE_PASSWORD'),
    )

    for schema in SCHEMA_TABLE_SCHEMAS:
        print(f'\n=== {schema} ===')
        create_tables_for_schema(chameleon_conn, schema)
        create_tables_for_schema(project_conn, schema)

    print('\nSchema setup complete.')
