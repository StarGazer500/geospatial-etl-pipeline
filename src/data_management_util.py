import time

import pandas as pd
import geopandas as gpd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, IntegrityError




class DataManagement():

    # Set once before running setup_schemas.py: {'gis_viewer': 'SELECT', 'gis_update': 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE'}
    grant_roles: dict = {}

    @staticmethod
    def execute_spatial_query(conn, query, geom_col='geom'):
        """executes query and returns GeoDataFrame"""
        with conn['sync'].connect() as sync_conn:
            try:
                return gpd.read_postgis(query, sync_conn, geom_col=geom_col)
            except Exception as e:
                sync_conn.rollback()
                print(e)
                raise




    @staticmethod
    def execute_query_non_spatial(conn, query):
        """For non-spatial queries"""
        try:
            with conn['sync'].connect() as sync_conn:
                return pd.read_sql(query, sync_conn)
        except Exception as e:
            print(e)
            raise




    @staticmethod
    def create_target_schema_if_not_exists(conn, schema):
        """Creates schema if it does not exist and ensures PostGIS extension is enabled"""
        with conn['sync'].connect() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            if schema:
                try:
                    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
                    connection.commit()
                except IntegrityError:
                    connection.rollback()
            else:
                connection.commit()




    @staticmethod
    def _coerce_dtypes(data, conn, table_name, schema):
        """Coerce DataFrame columns to match the target PostgreSQL table's column types."""
        schema_filter = f"AND table_schema = '{schema}'" if schema else ""
        with conn['sync'].connect() as c:
            rows = c.execute(text(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = '{table_name}' {schema_filter}
                ORDER BY ordinal_position
            """)).fetchall()
        col_types = {row[0]: row[1].lower() for row in rows}

        for col in data.columns:
            pg_type = col_types.get(col)
            if not pg_type:
                continue
            try:
                if pg_type in ('integer', 'bigint', 'smallint'):
                    data[col] = pd.to_numeric(data[col], errors='coerce').round().astype('Int64')
                elif pg_type == 'date':
                    series = data[col]
                    if pd.api.types.is_float_dtype(series) or pd.api.types.is_integer_dtype(series):
                        # Year-only numeric values (e.g. 2026.0 stored as double precision)
                        data[col] = series.apply(
                            lambda x: pd.Timestamp(year=int(x), month=1, day=1) if pd.notna(x) else pd.NaT
                        )
                    else:
                        data[col] = pd.to_datetime(series, errors='coerce')
                elif pg_type in ('numeric', 'double precision', 'real'):
                    data[col] = pd.to_numeric(data[col], errors='coerce')
            except Exception as ex:
                print(f'  Warning: could not coerce column "{col}" to {pg_type}: {ex}')
        return data

    @staticmethod
    def save_spatial_data_to_postgres(conn, data, table_name, schema=None, target_crs=4326, max_retries=2):
        if target_crs is not None:
            data = data.to_crs(target_crs)

        # Target geometry columns are 2D: drop Z (e.g. from GPS/KML imports) instead of
        # failing the load with "Geometry has Z dimension but column does not"
        has_z = data.geometry.has_z
        if has_z.any():
            data = data.set_geometry(data.geometry.force_2d())
            print(f'{schema}.{table_name}: dropped Z from {int(has_z.sum())} of {len(data)} geometries')

        full_table = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'
        schema_filter = f"table_schema = '{schema}' AND " if schema else ""

        for attempt in range(1, max_retries + 2):
            try:
                with conn['sync'].connect() as check_conn:
                    result = check_conn.execute(text(f"""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE {schema_filter}table_name = '{table_name}'
                        )
                    """))
                    table_exists = result.scalar()

                if not table_exists:
                    print(f'{full_table} does not exist — run setup_schemas.py first')
                    return

                data = DataManagement._coerce_dtypes(data, conn, table_name, schema)

                with conn['sync'].connect() as trunc_conn:
                    trunc_conn.execute(text("SET LOCAL lock_timeout = '120s'"))
                    trunc_conn.execute(text(f'TRUNCATE TABLE {full_table}'))
                    trunc_conn.commit()

                data.to_postgis(
                    name=table_name,
                    con=conn['sync'],
                    schema=schema,
                    if_exists='append',
                    index=False,
                )

                print(f'Successfully saved {len(data)} records to {schema}.{table_name}')
                return

            except OperationalError as e:
                if 'lock timeout' in str(e).lower() and attempt <= max_retries:
                    conn['sync'].dispose()
                    print(f'Lock timeout on {full_table}, retrying in 5s (attempt {attempt}/{max_retries})...')
                    time.sleep(5)
                else:
                    print(f'Error occurred with error message: {e}')
                    raise



    @staticmethod
    def save_non_spatial_data_to_postgres(conn, data, table_name):
        try:
            data.to_sql(
                name=table_name,
                con=conn['sync'],
                if_exists='replace',
                index=False
            )
        except Exception as e:
            print(f'Error occurred with error message: {e}')
            raise



def read_test_data(path, project_name):
    data = gpd.read_file(path)
    project_data = data[data['project'] == project_name]
    dropped_project_column = project_data.loc[:, project_data.columns != 'project']
    return dropped_project_column
