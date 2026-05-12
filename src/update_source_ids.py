"""
update_source_ids.py
--------------------
Updates ID fields in the SOURCE database for the four layers listed below.
Each ID is derived from the compartment_id of the compartment that overlaps
the feature most (largest-area intersection), prefixed with the layer initials:

  unplantable_areas  → UA-{compartment_id}-{n}   (e.g. UA-UWA-B34-1)
  protected_areas    → PA-{compartment_id}-{n}
  road_buffers       → RB-{compartment_id}-{n}
  firebreaks         → FB-{compartment_id}-{n}

Only the specified id field is touched — no other columns are modified.
Tables that do not exist in a schema are silently skipped.

Usage:
    python update_source_ids.py
"""

import os
import psycopg2
import geopandas as gpd
from collections import defaultdict
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Source database connection
# ---------------------------------------------------------------------------
HOST     = os.getenv('SOURCE_HOST',          'localhost')
DB       = os.getenv('SOURCE_DATABASE_NAME', 'POSTGIS_DATABASE')
PORT     = os.getenv('SOURCE_PORT',          '5433')
USER     = os.getenv('SOURCE_USERNAME',      'postgres')
PASSWORD = os.getenv('SOURCE_PASSWORD',      '0549martin')

PSYCOPG2_DSN    = f"host={HOST} dbname={DB} port={PORT} user={USER} password={PASSWORD}"
SQLALCHEMY_URL  = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB}"

# ---------------------------------------------------------------------------
# Layer configuration
# ---------------------------------------------------------------------------
LAYER_CONFIG = {
    'unplantable_areas': {'id_field': 'unplantable_id',   'prefix': 'UA'},
    'protected_areas':   {'id_field': 'protected_area_id', 'prefix': 'PA'},
    'road_buffers':      {'id_field': 'road_buffer_id',   'prefix': 'RB'},
    'firebreaks':        {'id_field': 'firebreak_id',     'prefix': 'FB'},
}

SCHEMA_LAYERS = {
    'akwaaba_schema': ['protected_areas', 'unplantable_areas'],
    'buffalo_schema': ['unplantable_areas', 'firebreaks', 'protected_areas'],
    'colobus_schema': ['road_buffers', 'protected_areas', 'firebreaks', 'unplantable_areas'],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def table_exists(engine, schema, table):
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_schema = :s AND table_name = :t"
                ")"
            ),
            {'s': schema, 't': table}
        )
        return result.scalar()


def load_compartments(engine, schema):
    query = f"SELECT compartment_id, geom FROM {schema}.compartments"
    gdf = gpd.read_postgis(query, engine, geom_col='geom')
    return gdf.set_geometry('geom')


def load_layer(engine, schema, table):
    """Load the layer returning ctid (as text) and geom only."""
    query = f"SELECT ctid::text AS ctid, geom FROM {schema}.{table}"
    gdf = gpd.read_postgis(query, engine, geom_col='geom')
    return gdf.set_geometry('geom')


def assign_compartment_ids(layer_gdf, comp_gdf):
    """
    For each feature in layer_gdf assign the compartment_id of the compartment
    with the largest intersection area.  Falls back to 'NOCOMP' when no
    intersection exists.
    """
    layer_gdf = layer_gdf.reset_index(drop=True).copy()
    layer_gdf['_idx'] = layer_gdf.index

    if comp_gdf.crs != layer_gdf.crs:
        comp_gdf = comp_gdf.to_crs(layer_gdf.crs)

    left  = gpd.GeoDataFrame({'_idx': layer_gdf['_idx']},
                              geometry=layer_gdf.geometry.values,
                              crs=layer_gdf.crs)
    right = gpd.GeoDataFrame({'compartment_id': comp_gdf['compartment_id']},
                              geometry=comp_gdf.geometry.values,
                              crs=comp_gdf.crs)

    # Project to a metric CRS for accurate area comparison
    projected_crs = left.estimate_utm_crs()
    left  = left.to_crs(projected_crs)
    right = right.to_crs(projected_crs)

    overlay = gpd.overlay(left, right, how='intersection', keep_geom_type=False)
    overlay['_area'] = overlay.geometry.area

    best = (
        overlay.sort_values('_area', ascending=False)
               .drop_duplicates(subset=['_idx'])
               .set_index('_idx')['compartment_id']
    )

    layer_gdf['compartment_id'] = layer_gdf['_idx'].map(best).fillna('NOCOMP')
    return layer_gdf


def generate_new_ids(layer_gdf, prefix):
    """
    Assign {prefix}-{compartment_id}-{n} where n resets to 1 for each
    compartment.  The counter is per-compartment so IDs are unique globally
    when prefixes differ across layers.
    """
    counters = defaultdict(int)
    new_ids  = []
    for _, row in layer_gdf.iterrows():
        comp = row['compartment_id']
        counters[comp] += 1
        new_ids.append(f"{prefix}-{comp}-{counters[comp]}")
    layer_gdf = layer_gdf.copy()
    layer_gdf['new_id'] = new_ids
    return layer_gdf


def update_id_field(dsn, schema, table, id_field, ctid_to_id):
    """Execute UPDATE ... SET id_field = %s WHERE ctid = %s::tid for each row."""
    conn = psycopg2.connect(dsn)
    cur  = conn.cursor()
    updated = 0
    try:
        for ctid, new_id in ctid_to_id.items():
            cur.execute(
                f'UPDATE "{schema}"."{table}" SET "{id_field}" = %s WHERE ctid = %s::tid',
                (new_id, ctid)
            )
            updated += cur.rowcount
        conn.commit()
        print(f"    Updated {updated} row(s)  →  {schema}.{table}.{id_field}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_layer(engine, schema, table):
    config   = LAYER_CONFIG[table]
    id_field = config['id_field']
    prefix   = config['prefix']

    print(f"  [{table}] Loading {schema}.{table} …")
    layer_gdf = load_layer(engine, schema, table)
    if layer_gdf.empty:
        print(f"    No features found — skipped.")
        return

    print(f"    {len(layer_gdf)} features.  Loading compartments …")
    comp_gdf = load_compartments(engine, schema)
    if comp_gdf.empty:
        print(f"    No compartments found — cannot assign IDs, skipped.")
        return

    print(f"    Intersecting with {len(comp_gdf)} compartments …")
    layer_gdf = assign_compartment_ids(layer_gdf, comp_gdf)

    nocomp = (layer_gdf['compartment_id'] == 'NOCOMP').sum()
    if nocomp:
        print(f"    Warning: {nocomp} feature(s) did not intersect any compartment (tagged NOCOMP).")

    layer_gdf = generate_new_ids(layer_gdf, prefix)
    ctid_to_id = dict(zip(layer_gdf['ctid'], layer_gdf['new_id']))

    update_id_field(PSYCOPG2_DSN, schema, table, id_field, ctid_to_id)


def main():
    engine = create_engine(SQLALCHEMY_URL,
                           pool_size=2, max_overflow=0,
                           pool_pre_ping=True)

    for schema, tables in SCHEMA_LAYERS.items():
        print(f"\n{'='*55}")
        print(f"Schema: {schema}")
        print(f"{'='*55}")

        for table in tables:
            if table not in LAYER_CONFIG:
                continue
            if not table_exists(engine, schema, table):
                print(f"  [{table}] Table does not exist in {schema} — skipped.")
                continue
            try:
                process_layer(engine, schema, table)
            except Exception as exc:
                print(f"  ERROR on {schema}.{table}: {exc}")

    engine.dispose()
    print("\nAll done.")


if __name__ == '__main__':
    main()
