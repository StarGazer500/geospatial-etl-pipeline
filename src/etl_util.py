from datetime import datetime
import pandas as pd
import geopandas as gpd

from data_management_util import DataManagement, read_test_data
from validation_util import Validation
from savepoints_util import SavePoints


class Extract_Transform_Load:


    def load_leased_areas(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_leased_areas_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} leased_areas  already loaded')
            return

        try:
            query = None
            if schema == 'akwaaba_schema':
                query = f"""
                SELECT
                  lease_id,
                  ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                  MAX(geom_status) as geom_status,
                  MAX(lease_status) as lease_status,
                  MIN(year_leased) as year_leased,
                  SUM(area_ha) as area_ha,
                  MAX(link_to_lease_document) as link_to_lease_document
                FROM {schema}.leased_areas
                GROUP BY lease_id;
                """
            else:
                query = f"""
                SELECT
                  lease_id,
                  geom,
                  geom_status,
                  lease_status,
                  year_leased,
                  area_ha,
                  link_to_lease_document
                FROM {schema}.leased_areas
                """

            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='leased_areas',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_leased_areas_{datetime.now().date()}", True)

            print(f'{schema} leased Areas Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_leased_areas_{datetime.now().date()}", False)

            print(e)

            raise



    def load_compartments(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_compartments_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} compartments  already loaded')
            return

        try:
            query = None
            if schema == "akwaaba_schema":
                query = f"""
                SELECT
                  compartment_id,
                  ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                  MAX(lease_id) as lease_id,
                  SUM(area_ha) as area_ha,
                  MAX(n_psp_target) as n_psp_target,
                  MIN(year_created) as year_created
                FROM {schema}.compartments
                GROUP BY compartment_id;
                """
            else:
                query = f"""
                SELECT
                  lease_id,
                  compartment_id,
                  geom,
                  area_ha,
                  n_psp_target,
                  year_created
                FROM {schema}.compartments
                """

            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='compartments',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_compartments_{datetime.now().date()}", True)

            print(f'{schema} compartments Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_compartments_{datetime.now().date()}", False)

            print(e)

            raise



    def load_subcompartments(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} subcompartments  already loaded')
            return

        try:
            query = None

            if schema == 'buffalo_schema':
                query = f"""
                SELECT
                  subcompartment_id,
                  ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                  SUM(area_ha) as area_ha,
                  MAX(compartment_id) AS compartment_id,
                  MAX(treatment_type) AS treatment_type,
                  MAX(planting_status) AS planting_status,
                  MIN(year_planted) AS year_planted,
                  MAX(planting_type) AS planting_type,
                  MIN(lp_start_date) AS lp_start_date,
                  MIN(plant_start_date) AS plant_start_date
                FROM {schema}.subcompartments
                GROUP BY subcompartment_id;
                """
            else:
                query = f"""
                SELECT
                  subcompartment_id,
                  geom,
                  area_ha,
                  compartment_id,
                  treatment_type,
                  planting_status,
                  year_planted,
                  planting_type,
                  lp_start_date,
                  plant_start_date
                FROM {schema}.subcompartments
                """

            source_data = None
            # if schema == 'akwaaba_schema' or schema == 'buffalo_schema':

            source_test_data = read_test_data(r"C:\Users\LENOVO\Downloads\test_subcomps_akw_buf_new.gpkg", schema.split('_')[0])
            source_db_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_db_data.empty or source_test_data.empty:
                return "source db data and test db data mismatch"

            geom_col = source_db_data.geometry.name
            if source_test_data.geometry.name != geom_col:
                source_test_data = source_test_data.rename_geometry(geom_col)

            if source_test_data.crs != source_db_data.crs:
                source_test_data = source_test_data.to_crs(source_db_data.crs)

            source_data = gpd.GeoDataFrame(
                pd.concat([source_db_data, source_test_data], ignore_index=True),
                crs=source_db_data.crs,
                geometry=geom_col
            )

            # else:
            #     source_data = DataManagement.execute_spatial_query(
            #         conn=source_conn,
            #         query=query,
            #     )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='subcompartments',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}", True)

            print(f'{schema} Subcompartments Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}", False)

            print(e)

            raise



    def load_unplantable_areas(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_unplantable_areas_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} unplantable_areas  already loaded')
            return

        try:
            query = f"""
            SELECT
              compartment_id,
              unplantable_id,
              geom,
              area_ha,
              damage_type
            FROM {schema}.unplantable_areas
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='unplantable_areas',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_unplantable_areas_{datetime.now().date()}", True)

            print(f'{schema} Unplantable Areas Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_unplantable_areas_{datetime.now().date()}", False)

            print(e)

            raise



    def load_field_mapped_farms(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_field_mapped_farms_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} field_mapped_farms  already loaded')
            return

        try:
            query = f"""
            SELECT
              compartment_id,
              farm_id,
              geom,
              area_ha,
              date_mapped,
              mapped_by
            FROM {schema}.field_mapped_farms
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='field_mapped_farms',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_field_mapped_farms_{datetime.now().date()}", True)

            print(f'{schema} Field Mapped Farms Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_field_mapped_farms_{datetime.now().date()}", False)

            print(e)

            raise



    def load_intercropped_farms(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_intercropped_farms_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} intercropped_farms  already loaded')
            return

        try:
            query = f"""
            SELECT
              farm_id,
              geom,
              farmer_photo_link,
              farmer_contact,
              farmer_next_of_kin,
              signed_intercrop_agmt_links,
              signed_intercrop_agmt_startdate,
              signed_intercrop_agmt_expirydate,
              signed_intercrop_agmt_area_ha
            FROM {schema}.intercropped_farms
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='intercropped_farms',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_intercropped_farms_{datetime.now().date()}", True)

            print(f'{schema} Intercropped Farms Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_intercropped_farms_{datetime.now().date()}", False)

            print(e)

            raise



    def load_rb_roads(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_rb_roads_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} rb_roads  already loaded')
            return

        try:
            query = f"""
            SELECT
              road_class,
              condition,
              road_id,
              geom,
              road_treatment_status,
              length_km,
              date_created
            FROM {schema}.rb_roads
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='rb_roads',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_rb_roads_{datetime.now().date()}", True)

            print(f'{schema} Roads Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_rb_roads_{datetime.now().date()}", False)

            print(e)

            raise



    def load_rb_assigned_psps(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_assigned_psps_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} assigned_psps  already loaded')
            return

        try:
            query = f"""
            SELECT
              psp_id,
              compartment_id,
              geom,
              date_created,
              generated_by
            FROM {schema}.assigned_psps
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='assigned_psps',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_assigned_psps_{datetime.now().date()}", True)

            print(f'{schema} Assigned Psps Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_assigned_psps_{datetime.now().date()}", False)

            print(e)

            raise



    def load_rb_completed_psps(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_completed_psps_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} completed_psps  already loaded')
            return

        try:
            query = f"""
            SELECT
              psp_id,
              compartment_id,
              geom,
              date_completed,
              psp_cardinal_location
            FROM {schema}.completed_psps
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='completed_psps',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_completed_psps_{datetime.now().date()}", True)

            print(f'{schema} Completed Psps Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_completed_psps_{datetime.now().date()}", False)

            print(e)

            raise
