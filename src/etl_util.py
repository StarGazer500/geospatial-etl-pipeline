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
                  ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
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
                  ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
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


    def load_plantable_areas(schema, source_conn, target_conn):

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
                  geom,
                  ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
                  compartment_id,
                  treatment_type,
                  planting_status,
                  year_planted,
                  planting_type,
                  lp_start_date,
                  plant_start_date
                FROM (
                  SELECT
                    subcompartment_id,
                    ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                    MAX(compartment_id) AS compartment_id,
                    MAX(treatment_type) AS treatment_type,
                    MAX(planting_status) AS planting_status,
                    MIN(year_planted) AS year_planted,
                    MAX(planting_type) AS planting_type,
                    MIN(lp_start_date) AS lp_start_date,
                    MIN(plant_start_date) AS plant_start_date
                  FROM {schema}.subcompartments
                  GROUP BY subcompartment_id
                ) sub;
                """
            else:
                query = f"""
                SELECT
                  subcompartment_id,
                  geom,
                  ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
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

            source_test_data = read_test_data(r"C:\Users\LENOVO\Downloads\test_subcomps_akw_buf_new3.gpkg", schema.split('_')[0])
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




    def load_subcompartments_stratum_on_lease(schema, source_conn, target_conn, optional_layers=None):
        """
        optional_layers: list of source table names to merge in addition to subcompartments.
        Allowed values: 'road_buffers', 'firebreaks', 'unplantable_areas', 'protected_areas'.
        Only the tables listed here will be queried.
        """
        if optional_layers is None:
            optional_layers = []

        is_loaded = SavePoints.get_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} subcompartments  already loaded')
            return

        UNIFIED_COLS = [
            'subcompartment_id', 'category', 'subcategory', 'treatment',
            'planting_type', 'year_planted', 'plant_start_date', 'lp_start_date',
            'area_ha', 'sph', 'compartment_id', 'source_layer', 'geom'
        ]

        try:
            frames = []

            # --- Subcompartments (plantable) ---
            if schema == 'buffalo_schema':
                subcomp_query = f"""
                SELECT
                  subcompartment_id,
                  ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                  ROUND(CAST(ST_Area(ST_Transform(ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)), 4326)::geography) / 10000.0 AS NUMERIC), 3) AS area_ha,
                  MAX(compartment_id) AS compartment_id,
                  MAX(treatment_type) AS treatment_type,
                  MAX(sph) AS sph,
                  MAX(planting_status) AS planting_status,
                  MIN(year_planted) AS year_planted,
                  MAX(planting_type) AS planting_type,
                  MIN(lp_start_date) AS lp_start_date,
                  MIN(plant_start_date) AS plant_start_date
                FROM {schema}.subcompartments
                GROUP BY subcompartment_id;
                """
            else:
                subcomp_query = f"""
                SELECT
                  subcompartment_id,
                  geom,
                  ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
                  compartment_id,
                  treatment_type,
                  planting_status,
                  year_planted,
                  planting_type,
                  sph,
                  lp_start_date,
                  plant_start_date
                FROM {schema}.subcompartments
                """

            source_test_data = read_test_data(r"C:\Users\LENOVO\Downloads\test_subcomps_akw_buf_new3.gpkg", schema.split('_')[0])
            source_db_data = DataManagement.execute_spatial_query(conn=source_conn, query=subcomp_query)

            if not source_db_data.empty and not source_test_data.empty:
                geom_col = source_db_data.geometry.name
                if source_test_data.geometry.name != geom_col:
                    source_test_data = source_test_data.rename_geometry(geom_col)
                if source_test_data.crs != source_db_data.crs:
                    source_test_data = source_test_data.to_crs(source_db_data.crs)
                subcomps = gpd.GeoDataFrame(
                    pd.concat([source_db_data, source_test_data], ignore_index=True),
                    crs=source_db_data.crs,
                    geometry=geom_col
                )
            elif not source_db_data.empty:
                subcomps = source_db_data
            else:
                subcomps = gpd.GeoDataFrame()

            if not subcomps.empty:
                subcomps['category'] = 'plantable'
                subcomps['subcategory'] = subcomps['planting_status'].apply(
                    lambda x: 'planted' if str(x).lower() == 'planted' else 'planned_planting'
                )
                subcomps = subcomps.rename(columns={'treatment_type': 'treatment', subcomps.geometry.name: 'geom'})
                subcomps = gpd.GeoDataFrame(subcomps, geometry='geom', crs=subcomps.crs)
                subcomps['source_layer'] = 'subcompartments'
                frames.append(subcomps[UNIFIED_COLS])

            # --- Road Buffers (unplantable) ---
            if 'road_buffers' in optional_layers:
                print(f'{schema} loading road_buffers...')
                try:
                    road_buffer_query = f"""
                    SELECT
                      road_buffer_id,
                      ROUND(CAST(ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0 AS NUMERIC), 3) AS area_ha,
                      geom
                    FROM {schema}.road_buffers
                    """
                    road_buffers = DataManagement.execute_spatial_query(conn=source_conn, query=road_buffer_query)
                    if not road_buffers.empty:
                        road_buffers = road_buffers.rename(columns={'road_buffer_id': 'subcompartment_id', road_buffers.geometry.name: 'geom'})
                        road_buffers = gpd.GeoDataFrame(road_buffers, geometry='geom', crs=road_buffers.crs)
                        road_buffers['category'] = 'unplantable'
                        road_buffers['subcategory'] = 'road_buffer'
                        road_buffers['treatment'] = None
                        road_buffers['planting_type'] = None
                        road_buffers['year_planted'] = None
                        road_buffers['plant_start_date'] = None
                        road_buffers['lp_start_date'] = None
                        road_buffers['sph'] = None
                        road_buffers['compartment_id'] = None
                        road_buffers['source_layer'] = 'road_buffers'
                        frames.append(road_buffers[UNIFIED_COLS])
                        print(f'{schema} road_buffers: {len(road_buffers)} records')
                    else:
                        print(f'{schema} road_buffers: 0 records found')
                except Exception as e:
                    print(f'{schema} road_buffers skipped: {e}')

           

            # --- Firebreaks (unplantable) ---
            if 'firebreaks' in optional_layers:
                print(f'{schema} loading firebreaks...')
                try:
                    firebreak_query = f"""
                    SELECT
                      firebreak_id,
                      ROUND(CAST(ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0 AS NUMERIC), 3) AS area_ha,
                      geom
                    FROM {schema}.firebreaks
                    """
                    firebreaks = DataManagement.execute_spatial_query(conn=source_conn, query=firebreak_query)
                    if not firebreaks.empty:
                        firebreaks = firebreaks.rename(columns={'firebreak_id': 'subcompartment_id', firebreaks.geometry.name: 'geom'})
                        firebreaks = gpd.GeoDataFrame(firebreaks, geometry='geom', crs=firebreaks.crs)
                        firebreaks['category'] = 'unplantable'
                        firebreaks['subcategory'] = 'firebreak'
                        firebreaks['treatment'] = None
                        firebreaks['planting_type'] = None
                        firebreaks['year_planted'] = None
                        firebreaks['plant_start_date'] = None
                        firebreaks['lp_start_date'] = None
                        firebreaks['sph'] = None
                        firebreaks['compartment_id'] = None
                        firebreaks['source_layer'] = 'firebreaks'
                        frames.append(firebreaks[UNIFIED_COLS])
                        print(f'{schema} firebreaks: {len(firebreaks)} records')
                    else:
                        print(f'{schema} firebreaks: 0 records found')
                except Exception as e:
                    print(f'{schema} firebreaks skipped: {e}')

            # --- Unplantable Areas (unplantable, subcategory from damage_type) ---
            if 'unplantable_areas' in optional_layers:
                print(f'{schema} loading unplantable_areas...')
                try:
                    unplantable_query = f"""
                    SELECT
                      unplantable_id,
                      compartment_id,
                      ROUND(CAST(ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0 AS NUMERIC), 3) AS area_ha,
                      damage_type,
                      geom
                    FROM {schema}.unplantable_areas
                    """
                    unplantables = DataManagement.execute_spatial_query(conn=source_conn, query=unplantable_query)
                    if not unplantables.empty:
                        unplantables = unplantables.rename(columns={
                            'unplantable_id': 'subcompartment_id',
                            'damage_type': 'subcategory',
                            unplantables.geometry.name: 'geom'
                        })
                        unplantables = gpd.GeoDataFrame(unplantables, geometry='geom', crs=unplantables.crs)
                        unplantables['category'] = 'unplantable'
                        unplantables['treatment'] = None
                        unplantables['planting_type'] = None
                        unplantables['year_planted'] = None
                        unplantables['plant_start_date'] = None
                        unplantables['lp_start_date'] = None
                        unplantables['sph'] = None
                        unplantables['source_layer'] = 'unplantable_areas'
                        frames.append(unplantables[UNIFIED_COLS])
                        print(f'{schema} unplantable_areas: {len(unplantables)} records')
                    else:
                        print(f'{schema} unplantable_areas: 0 records found')
                except Exception as e:
                    print(f'{schema} unplantable_areas skipped: {e}')

            # --- Protected Areas (plantable) ---
            if 'protected_areas' in optional_layers:
                print(f'{schema} loading protected_areas...')
                try:
                    protected_query = f"""
                    SELECT
                      protected_area_id,
                      ROUND(CAST(ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0 AS NUMERIC), 3) AS area_ha,
                      geom
                    FROM {schema}.protected_areas
                    """
                    protected = DataManagement.execute_spatial_query(conn=source_conn, query=protected_query)
                    if not protected.empty:
                        protected = protected.rename(columns={'protected_area_id': 'subcompartment_id', protected.geometry.name: 'geom'})
                        protected = gpd.GeoDataFrame(protected, geometry='geom', crs=protected.crs)
                        protected['category'] = 'plantable'
                        protected['subcategory'] = 'protection'
                        protected['treatment'] = None
                        protected['planting_type'] = None
                        protected['year_planted'] = None
                        protected['plant_start_date'] = None
                        protected['lp_start_date'] = None
                        protected['sph'] = None
                        protected['compartment_id'] = None
                        protected['source_layer'] = 'protected_areas'
                        frames.append(protected[UNIFIED_COLS])
                        print(f'{schema} protected_areas: {len(protected)} records')
                    else:
                        print(f'{schema} protected_areas: 0 records found')
                except Exception as e:
                    print(f'{schema} protected_areas skipped: {e}')

            if not frames:
                print(f'No data found for {schema} subcompartments')
                return

            layer_summary = ', '.join(f"{f['source_layer'].iloc[0]}({len(f)})" for f in frames)
            print(f'{schema} merging layers: {layer_summary}')

            ref_crs = frames[0].crs
            aligned = []
            for f in frames:
                if f.crs != ref_crs:
                    f = f.to_crs(ref_crs)
                aligned.append(f)

            source_data = gpd.GeoDataFrame(
                pd.concat(aligned, ignore_index=True),
                crs=ref_crs,
                geometry='geom'
            )

            source_data = Validation.validate_and_fix_geometries(source_data)

            # Derive compartment_id for all rows via largest-overlap spatial join with compartments
            try:
                comp_query = f"SELECT compartment_id, geom FROM {schema}.compartments"
                compartments = DataManagement.execute_spatial_query(conn=source_conn, query=comp_query)

                if not compartments.empty:
                    if compartments.crs != source_data.crs:
                        compartments = compartments.to_crs(source_data.crs)

                    source_data = source_data.reset_index(drop=True)
                    all_gdf = gpd.GeoDataFrame(
                        {'_orig_idx': source_data.index},
                        geometry=source_data['geom'].values,
                        crs=source_data.crs
                    )
                    comp_gdf = gpd.GeoDataFrame(
                        compartments[['compartment_id']],
                        geometry=compartments['geom'].values,
                        crs=compartments.crs
                    )

                    overlay_result = gpd.overlay(all_gdf, comp_gdf, how='intersection', keep_geom_type=False)
                    overlay_result['_area'] = overlay_result.geometry.area

                    best = (
                        overlay_result.sort_values('_area', ascending=False)
                        .drop_duplicates(subset=['_orig_idx'])
                        .set_index('_orig_idx')['compartment_id']
                    )

                    source_data['compartment_id'] = source_data.index.map(best)
            except Exception:
                pass

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='subcompartment_stratum_on_lease',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}", True)

            print(f'{schema} Subcompartments Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}", False)

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
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
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


    def load_firebreaks(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_firebreaks_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} firebreaks  already loaded')
            return

        try:
            query = f"""
            SELECT
              firebreak_id,
              lease_id,
              CAST(perimeter AS DOUBLE PRECISION) AS perimeter,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
              geom
            FROM {schema}.firebreaks
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
                table_name='firebreaks',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_firebreaks_{datetime.now().date()}", True)

            print(f'{schema} Firebreaks Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_firebreaks_{datetime.now().date()}", False)

            print(e)

            raise


    def load_protected_areas(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_protected_areas_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} protected_areas  already loaded')
            return

        try:
            query = f"""
            SELECT
              protected_area_id,
              landcover,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
              geom
            FROM {schema}.protected_areas
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
                table_name='protected_areas',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_protected_areas_{datetime.now().date()}", True)

            print(f'{schema} Protected_areas Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_protected_areas_{datetime.now().date()}", False)

            print(e)

            raise

    def load_road_buffers(schema, source_conn, target_conn):

        is_loaded = SavePoints.get_layer_progress(f"{schema}_road_buffers_{datetime.now().date()}")
        if is_loaded:
            print(f'{schema} road_buffers  already loaded')
            return

        try:
            query = f"""
            SELECT
              road_buffer_id,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 3) as area_ha,
              geom
            FROM {schema}.road_buffers
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
                table_name='road_buffers',
                schema=schema
            )

            SavePoints.save_layer_progress(f"{schema}_road_buffers_{datetime.now().date()}", True)

            print(f'{schema} Road_buffers Loaded Successfully')

        except Exception as e:

            SavePoints.save_layer_progress(f"{schema}_road_buffers_{datetime.now().date()}", False)

            print(e)

            raise


    