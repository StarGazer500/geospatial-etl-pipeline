"""
Run once with gis_create credentials to create table structures and grants.
Edit SCHEMA_TABLE_SCHEMAS below to adjust column names and types before running.
The ETL pipeline (update mode) will then TRUNCATE + INSERT into these tables.
"""
import os
import re
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
    ('recipe',              'CHARACTER VARYING'),
    ('operational_year',    'INTEGER'),
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

_CULVERTS = [
    ('road_id',          'CHARACTER VARYING'),
    ('culvert_id',          'CHARACTER VARYING'),
    ('geom',                'geometry(Point, 4326)'),
    ('culvert_type',        'CHARACTER VARYING'),
    ('legacy_culvert_id',   'CHARACTER VARYING'),
    ('pipe_diameter_mm',    'INTEGER'),
    ('pipe_length_m',       'DOUBLE PRECISION'),
    ('no_of_pipes',         'INTEGER'),
    ('pipe_type',           'CHARACTER VARYING'),
    ('headwalls',           'CHARACTER VARYING'),
    ('status',               'CHARACTER VARYING'),
    ('build_year',           'INTEGER'),
    ('date_maintained',      'DATE'),
    ('compartment_id',       'CHARACTER VARYING'),
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
    ('recipe',                          'CHARACTER VARYING'),
    ('operational_year',                'INTEGER'),
    ('initial_recipe',                  'CHARACTER VARYING'),
    ('initial_plant_start_date',        'DATE'),
    ('comments',                        'CHARACTER VARYING'),
]

# rb_roads: akwaaba/colobus have no road_type; buffalo schemas have road_type
_RB_ROADS_BASE = [
    ('road_id',                 'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiLineString, 4326)'),
    ('road_class',              'CHARACTER VARYING'),
    ('condition',               'CHARACTER VARYING'),
    ('road_treatment_status',   'CHARACTER VARYING'),
    ('length_km',               'DOUBLE PRECISION'),
    ('area',                    'CHARACTER VARYING'),
    ('compartment_id',          'CHARACTER VARYING'),
    ('status',                  'CHARACTER VARYING'),
    ('build_year',              'INTEGER'),
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
    ('area',                    'CHARACTER VARYING'),
    ('compartment_id',          'CHARACTER VARYING'),
    ('status',                  'CHARACTER VARYING'),
    ('build_year',              'INTEGER'),
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
    ('phase',                   'INTEGER'),

]

_LEASED_AREAS_BUFFALO_VERSIONED = [   # buffalo_schema
    ('lease_id',                'CHARACTER VARYING'),
    ('parcel_id',               'CHARACTER VARYING'),
    ('legacy_lease_id',         'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiPolygon, 4326)'),
    ('geom_status',             'CHARACTER VARYING'),
    ('lease_status',            'CHARACTER VARYING'),
    ('year_leased',             'INTEGER'),
    ('area_ha_wgs84',           'DOUBLE PRECISION'),
    ('area_ha_utm29',           'DOUBLE PRECISION'),
    ('link_to_lease_document',  'CHARACTER VARYING'),
    ('date_registered',         'DATE'),
    ('comments',            'CHARACTER VARYING'),
]

_LEASED_AREAS_BASE = [                # colobus_schema
    ('lease_id',                'CHARACTER VARYING'),
    ('geom',                    'geometry(MultiPolygon, 4326)'),
    ('geom_status',             'CHARACTER VARYING'),
    ('lease_status',            'CHARACTER VARYING'),
    ('year_leased',             'INTEGER'),
    ('area_ha',                 'DOUBLE PRECISION'),
    ('link_to_lease_document',  'CHARACTER VARYING'),
    ('date_registered',         'DATE'),
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
        'culverts':             _CULVERTS,
    },

    'buffalo_schema': {
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
        'culverts':             _CULVERTS,
    },
}


# ── Natural id column per table — the layer's own id, not the SERIAL "id" ──────
# Enforced UNIQUE so the same road/culvert/compartment/etc. can't be inserted twice.

TABLE_ID_COLUMNS = {
    'leased_areas':         'lease_id',
    'compartments':         'compartment_id',
    'subcompartments':      'subcompartment_id',
    'unplantable_areas':    'unplantable_id',
    'rb_roads':             'road_id',
    'firebreaks':           'firebreak_id',
    'protected_areas':      'protected_area_id',
    'road_buffers':         'road_buffer_id',
    'lease_areas_stratum':  'lease_stratum_id',
    'culverts':             'culvert_id',
}

# Per-(schema, table) overrides where the natural id differs from the default
# above. buffalo_schema's leased_areas groups by parcel_id, not lease_id —
# one lease can span multiple parcels, so parcel_id is the unique field for now.
TABLE_ID_COLUMN_OVERRIDES = {
    ('buffalo_schema', 'leased_areas'): 'parcel_id',
}

# Draft (staging) schemas: the ETL loads "<schema>_draft"; approved drafts are
# promoted to "<schema>" by draft_review.promote(). Created by an admin, owned by gis_create.
DRAFT_SUFFIX = '_draft'

# Layers on each target database
CHAMELEON_TABLES = {'rb_roads', 'leased_areas', 'subcompartments', 'lease_areas_stratum', 'compartments', 'firebreaks', 'culverts'}
PROJECT_LEVEL_TABLES = {'rb_roads', 'leased_areas', 'subcompartments', 'lease_areas_stratum', 'compartments', 'culverts'}


def project_schema(schema):
    """The final schema a schema belongs to: 'buffalo_schema_draft' -> 'buffalo_schema'."""
    return schema.removesuffix(DRAFT_SUFFIX)


def id_column(schema, table):
    """The layer's natural id column; drafts use the same id as their final schema."""
    return TABLE_ID_COLUMN_OVERRIDES.get((project_schema(schema), table), TABLE_ID_COLUMNS.get(table))


# ── Core functions ─────────────────────────────────────────────────────────────

# Postgres takes an exclusive lock on the table for ALTER TABLE … ADD COLUMN IF NOT EXISTS
# and CREATE INDEX IF NOT EXISTS even when nothing needs creating, which blocks (or
# deadlocks with) anyone reading the table. So check first and only run what is missing.

def add_missing_columns(connection, schema, table, columns):
    """Adds the (name, type) columns the table doesn't have yet; returns the names added."""
    existing = {row[0] for row in connection.execute(text(
        'SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :t'
    ), {'s': schema, 't': table})}
    added = []
    for col, dtype in columns:
        if col not in existing:
            connection.exec_driver_sql(f'ALTER TABLE "{schema}"."{table}" ADD COLUMN "{col}" {dtype}')
            added.append(col)
    return added


def ensure_index(connection, schema, index_name, ddl):
    """Runs the CREATE INDEX statement ddl only if the index doesn't exist yet."""
    exists = connection.execute(text(
        'SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = :s AND indexname = :i)'
    ), {'s': schema, 'i': index_name}).scalar()
    if not exists:
        connection.exec_driver_sql(ddl)

def create_tables_for_schema(conn, schema, table_schemas=None):
    if table_schemas is None:
        table_schemas = SCHEMA_TABLE_SCHEMAS.get(schema, {})
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

            add_missing_columns(connection, schema, table_name, columns)
            for col, dtype in columns:
                # Alter type if it changed (skip geometry — requires special casting)
                if 'geometry' not in dtype.lower() and col in existing:
                    target = dtype.lower().split('(')[0].strip()
                    if existing[col] != target:
                        connection.execute(text(
                            f'ALTER TABLE {full_table} ALTER COLUMN "{col}" TYPE {dtype} USING "{col}"::{dtype}'
                        ))
                        print(f'    Altered {col}: {existing[col]} -> {dtype}')

            # Discover every sequence backing a column default on this table —
            # not just the expected "{table}_id_seq". Manually recreated/imported
            # tables can have leftover id columns tied to oddly-named sequences
            # (e.g. "colobus_stratum_merged_id_0_seq") that still need granting,
            # or none at all if there's no SERIAL-backed column.
            defaults = connection.execute(text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table "
                "AND column_default LIKE 'nextval(%'"
            ), {'schema': schema, 'table': table_name}).scalars().all()
            sequence_names = sorted({
                match.group(1)
                for default in defaults
                for match in [re.search(r"nextval\('(?:[\w\"]+\.)?\"?([\w]+)\"?'", default)]
                if match
            })

            for role, privileges in GRANT_ROLES.items():
                connection.execute(text(f'GRANT {privileges} ON {full_table} TO {role}'))
                for seq in sequence_names:
                    connection.execute(text(
                        f'GRANT USAGE, SELECT ON SEQUENCE "{schema}"."{seq}" TO {role}'
                    ))
            if not sequence_names:
                print(f'    No sequence-backed columns on {table_name} — skipped sequence grants')
            else:
                print(f'    Granted on sequences: {", ".join(sequence_names)}')
            connection.commit()
        print(f'  Ready: {full_table}')

        # Enforce uniqueness on the layer's natural id (e.g. culvert_id, road_id) —
        # run in its own connection so a table with pre-existing duplicate ids
        # can't abort the create/alter/grant work above or the tables after it.
        key = id_column(schema, table_name)
        if key and any(col == key for col, _ in columns):
            index_name = f'{table_name}_{key}_key'
            with conn['sync'].connect() as connection:
                try:
                    ensure_index(connection, schema, index_name,
                                 f'CREATE UNIQUE INDEX "{index_name}" ON {full_table} ("{key}")')
                    connection.commit()
                    print(f'    Unique index ensured on {key}')
                except Exception as e:
                    connection.rollback()
                    print(f'    Could not enforce uniqueness on {key} (existing duplicates?): {e}')


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Create/update tables, drafts and history. Safe to re-run.',
        epilog='Examples:  setup_schemas.py                         (everything)\n'
               '           setup_schemas.py akwaaba                 (one project, all parts)\n'
               '           setup_schemas.py akwaaba --only history   (one project, history functions only)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('projects', nargs='*', choices=[s.removesuffix('_schema') for s in SCHEMA_TABLE_SCHEMAS],
                        help='projects to set up (default: all)')
    parser.add_argument('--only', nargs='+', choices=['live', 'draft', 'history'], default=['live', 'draft', 'history'],
                        help='parts to set up (default: all). live = live tables on both databases; '
                             'draft = draft tables and review lock; history = history tables and comparison functions')
    args = parser.parse_args()
    schemas = {s: t for s, t in SCHEMA_TABLE_SCHEMAS.items()
               if not args.projects or s.removesuffix('_schema') in args.projects}
    print(f'Setting up {", ".join(schemas)}: {", ".join(args.only)}')

    chameleon_conn = DatabaseConnection.connect_to_target_postgis_database(
        host=os.getenv('CHAMELEON_TARGET_HOST'),
        database_name=os.getenv('CHAMELEON_TARGET_DATABASE_NAME'),
        port=os.getenv('CHAMELEON_TARGET_PORT'),
        username=os.getenv('GIS_CREATE_USERNAME'),
        password=os.getenv('GIS_CREATE_PASSWORD'),
    )

    if 'live' in args.only:
        project_conn = DatabaseConnection.connect_to_target_postgis_database(
            host=os.getenv('PROJECT_LEVEL_TARGET_HOST'),
            database_name=os.getenv('PROJECT_LEVEL_TARGET_DATABASE_NAME'),
            port=os.getenv('PROJECT_LEVEL_TARGET_PORT'),
            username=os.getenv('GIS_CREATE_USERNAME'),
            password=os.getenv('GIS_CREATE_PASSWORD'),
        )
        for schema, table_schemas in schemas.items():
            print(f'\n=== {schema} ===')
            chameleon_tables = {t: c for t, c in table_schemas.items() if t in CHAMELEON_TABLES}
            project_tables   = {t: c for t, c in table_schemas.items() if t in PROJECT_LEVEL_TABLES}
            create_tables_for_schema(chameleon_conn, schema, chameleon_tables)
            create_tables_for_schema(project_conn,   schema, project_tables)

    # Draft schemas (chameleon target only) — same tables as the final schema.
    # The schemas themselves are created by an admin (see RUNBOOK.md); skipped until they exist.
    if 'draft' in args.only:
        from draft_review import create_review_objects, schema_exists
        for schema, table_schemas in schemas.items():
            draft = schema + DRAFT_SUFFIX
            print(f'\n=== {draft} ===')
            if not schema_exists(chameleon_conn, draft):
                print(f'  {draft} does not exist yet — ask an admin to create it (RUNBOOK.md, step 1). Skipped.')
                continue
            create_tables_for_schema(chameleon_conn, draft, {t: c for t, c in table_schemas.items() if t in CHAMELEON_TABLES})
            create_review_objects(chameleon_conn, schema)

    # Change history lives on the chameleon target only, in "<schema>_history".
    # After the drafts: the history's <layer>_pending() functions read them.
    if 'history' in args.only:
        from change_history import create_history_objects
        for schema in schemas:
            print(f'\n=== {schema}_history ===')
            create_history_objects(chameleon_conn, schema)

    print('\nSchema setup complete.')
