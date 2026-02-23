import time

import pandas as pd
import geopandas as gpd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError




class DataManagement():

    @staticmethod
    def execute_spatial_query(conn, query, geom_col='geom'):
        """executes query and returns GeoDataFrame"""
        try:
            with conn['sync'].connect() as sync_conn:
                return gpd.read_postgis(query, sync_conn, geom_col=geom_col)
        except Exception as e:
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
        """Creates schema if it does not exist"""
        if schema:
            with conn['sync'].connect() as connection:
                connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
                connection.commit()




    @staticmethod
    def save_spatial_data_to_postgres(conn, data, table_name, schema=None, target_crs=4326, max_retries=2):
        if target_crs is not None:
            data = data.to_crs(target_crs)

        DataManagement.create_target_schema_if_not_exists(conn, schema)

        full_table = f'"{schema}"."{table_name}"' if schema else f'"{table_name}"'

        for attempt in range(1, max_retries + 2):
            try:
                data.to_postgis(
                    name=table_name,
                    con=conn['sync'],
                    schema=schema,
                    if_exists='replace',
                    index=False
                )

                with conn['sync'].connect() as connection:
                    connection.execute(text(f"""
                        ALTER TABLE {full_table}
                        ADD COLUMN id SERIAL PRIMARY KEY;
                    """))
                    connection.commit()

                print(f'Successfully saved {len(data)} records to {schema}.{table_name}')
                return

            except OperationalError as e:
                if 'lock timeout' in str(e).lower() and attempt <= max_retries:
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
