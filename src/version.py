"""
Database Schema Backup Script
Reads schemas from source PostGIS database and saves each table as a
GeoParquet (spatial) or Parquet (non-spatial) file under a timestamped
folder in the configured Dropbox location.

Restore example:
    import geopandas as gpd
    gdf = gpd.read_parquet("path/to/schema_20260516_1048/table.parquet")
    gdf.to_postgis("table", engine, schema="schema", if_exists="replace")
"""

import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, inspect, text

load_dotenv()

# -------------------------------------------------
# CONFIGURATION
# -------------------------------------------------

DROPBOX_BACKUP_DIR = os.environ["DROPBOX_BACKUP_DIR"]

SRC_HOST     = os.environ["SOURCE_HOST"]
SRC_PORT     = int(os.environ["SOURCE_PORT"])
SRC_DB       = os.environ["SOURCE_DATABASE_NAME"]
SRC_USER     = os.environ["SOURCE_USERNAME"]
SRC_PASSWORD = os.environ["SOURCE_PASSWORD"]

SOURCE_SCHEMAS = [
    "akwaaba_schema",
    "colobus_schema",
    "buffalo_schema"
]

MAX_CONCURRENT = 4

# -------------------------------------------------
# ENGINE
# -------------------------------------------------

def make_src_engine():
    url = (
        f"postgresql+psycopg2://{SRC_USER}:{SRC_PASSWORD}"
        f"@{SRC_HOST}:{SRC_PORT}/{SRC_DB}"
    )
    return create_engine(url, pool_pre_ping=True, pool_size=MAX_CONCURRENT + 2)

# -------------------------------------------------
# TABLE-LEVEL BACKUP
# -------------------------------------------------

def geometry_columns_for(engine, schema, table):
    query = text("""
        SELECT f_geometry_column
        FROM geometry_columns
        WHERE f_table_schema = :schema
          AND f_table_name   = :table
    """)
    with engine.connect() as conn:
        rows = conn.execute(query, {"schema": schema, "table": table})
        return [r[0] for r in rows]


def safe_filename(table):
    """Table names can contain path-separator characters (e.g. 'Z/M Dropped'),
    which os.path.join would otherwise treat as subdirectories."""
    return re.sub(r'[\\/]', '_', table)


def backup_table(engine, schema, table, out_dir):
    label = f"{schema}.{table}"
    try:
        geom_cols = geometry_columns_for(engine, schema, table)
        file_name = f"{safe_filename(table)}.parquet"

        if geom_cols:
            geom_col = geom_cols[0]
            gdf = gpd.read_postgis(
                f'SELECT * FROM "{schema}"."{table}" WHERE "{geom_col}" IS NOT NULL',
                engine,
                geom_col=geom_col,
            )
            out_path = os.path.join(out_dir, file_name)
            gdf.to_parquet(out_path, index=False)
            print(f"  OK [spatial] {label}  ({len(gdf)} rows -> {file_name})")
        else:
            df = pd.read_sql(f'SELECT * FROM "{schema}"."{table}"', engine)
            out_path = os.path.join(out_dir, file_name)
            df.to_parquet(out_path, index=False)
            print(f"  OK [table]   {label}  ({len(df)} rows -> {file_name})")

        return True

    except Exception as exc:
        print(f"  FAILED: {label} — {exc}")
        return False

# -------------------------------------------------
# SCHEMA-LEVEL BACKUP
# -------------------------------------------------

def backup_schema(engine, schema, date_suffix):
    out_dir = os.path.join(DROPBOX_BACKUP_DIR, f"{schema}_{date_suffix}")
    os.makedirs(out_dir, exist_ok=True)

    print("-" * 60)
    print(f"Backing up: {schema}  ->  {out_dir}")

    inspector = inspect(engine)
    tables = inspector.get_table_names(schema=schema)

    if not tables:
        print(f"  No tables found in '{schema}' — skipping.")
        return True

    print(f"  Tables ({len(tables)}): {', '.join(tables)}")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        futures = {
            pool.submit(backup_table, engine, schema, t, out_dir): t
            for t in tables
        }
        results = [fut.result() for fut in as_completed(futures)]

    success = all(results)
    print(f"  Schema {'SUCCESS' if success else 'PARTIAL FAILURE'}: {schema}")
    return success

# -------------------------------------------------
# MAIN
# -------------------------------------------------

def create_version(description):
    date_suffix = datetime.now().strftime("%Y%m%d_%H%M")

    print("=" * 60)
    print("  SCHEMA BACKUP  ->  GeoParquet")
    print(f"  Date suffix  : {date_suffix}")
    print(f"  Schemas      : {SOURCE_SCHEMAS}")
    print(f"  Destination  : {DROPBOX_BACKUP_DIR}")
    print("=" * 60)

    engine = make_src_engine()

    try:
        results = {}
        for schema in SOURCE_SCHEMAS:
            results[schema] = backup_schema(engine, schema, date_suffix)
    finally:
        engine.dispose()

    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    all_ok = True
    for schema, ok in results.items():
        status = "SUCCESS" if ok else "FAILED "
        print(f"  {status}  {schema}  ->  {schema}_{date_suffix}")
        if not ok:
            all_ok = False
    print("=" * 60)

    changelog_path = os.path.join(DROPBOX_BACKUP_DIR, "CHANGELOG.md")
    try:
        with open(changelog_path, "a", encoding="utf-8") as f:
            f.write(f"## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Schemas : {', '.join(SOURCE_SCHEMAS)}\n")
            f.write(f"Status  : {'SUCCESS' if all_ok else 'PARTIAL FAILURE'}\n")
            f.write("\n")
            f.write(description.strip())
            f.write("\n\n---\n\n")
        print(f"Changelog updated: {changelog_path}")
    except OSError as e:
        print(f"Warning: changelog not updated ({e}) — backup data is safe")


# if __name__ == "__main__":
#     create_version("Description of what changed.")
