import pandas as pd
import geopandas as gpd
from sqlalchemy import text

class DataManagement():

    @staticmethod
    async def execute_spatial_query(conn, query, geom_col='geom'):
        """executes query and returns GeoDataFrame"""
        try:
            async_engine = conn['async']
            async with async_engine.connect() as async_conn:
                return await async_conn.run_sync(
                    lambda sync_conn: gpd.read_postgis(query, sync_conn, geom_col=geom_col)
                )
        except Exception as e:
            print(e)
            raise
            



    @staticmethod
    async def execute_query_non_spatial(conn, query):
        """For non-spatial queries"""
        try:
            async_engine = conn['async']
            async with async_engine.connect() as async_conn:
                return await async_conn.run_sync(
                    lambda sync_conn: pd.read_sql(query, sync_conn)
                )
        except Exception as e:
            print(e)
            raise
            
        


    @staticmethod
    async def create_target_schema_if_not_exists(conn, schema):
        """Creates schema if it does not exist"""
        if schema:
            async_engine = conn['async']
            async with async_engine.connect() as async_conn:
                await async_conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
                await async_conn.commit()




    @staticmethod
    async def save_spatial_data_to_postgres(conn, data, table_name, schema=None, target_crs=4326):
        try:
            # Convert CRS if specified
            if target_crs is not None:
                data = data.to_crs(target_crs)

            # Ensure schema exists
            await DataManagement.create_target_schema_if_not_exists(conn, schema)

            data.to_postgis(
                name=table_name,
                con=conn['sync'],
                schema=schema,
                if_exists='replace',
                index=False
            )
            print(f'Successfully saved {len(data)} records to {schema}.{table_name}')

        except Exception as e:
            print(f'Error occurred with error message: {e}')
            raise



    @staticmethod
    async def save_spatialdata_to_postgres(conn, data, table_name):
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
