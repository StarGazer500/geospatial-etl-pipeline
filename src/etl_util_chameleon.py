import pandas as pd
import geopandas as gpd
from shapely import snap
from shapely.geometry import MultiPolygon as _MP

from data_management_util import DataManagement, read_test_data
from validation_util import Validation


def _to_multipolygon(g):
    if g is None:
        return None
    if g.geom_type == 'MultiPolygon':
        return g
    if g.geom_type == 'Polygon':
        return _MP([g])
    if 'Collection' in g.geom_type:
        polys = [p for p in g.geoms if p.geom_type == 'Polygon']
        polys += [p for mp in g.geoms if mp.geom_type == 'MultiPolygon' for p in mp.geoms]
        return _MP(polys) if polys else None
    return None


class Extract_Transform_Load:

    def load_leased_areas(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_leased_areas_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} leased_areas  already loaded')
        #     return

        try:
            query = None
            if source_schema == 'buffalo_schema':
                query = f"""
                    SELECT parcel_id,lease_id,legacy_lease_id, geom, geom_status, lease_status, year_leased,
                           ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) AS area_ha_wgs84,
                           ROUND((ST_Area(geom) / 10000)::numeric, 2) AS area_ha_utm29,
                           link_to_lease_document, date_registered,comments
                    FROM (
                        SELECT
                            parcel_id,
                            MAX(lease_id) AS lease_id,
                            MAX(legacy_lease_id) AS legacy_lease_id,
                            ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) AS geom,
                            MAX(geom_status) AS geom_status,
                            MAX(lease_status) AS lease_status,
                            MIN(CASE WHEN year_leased::TEXT ~ '^\\d+$' THEN year_leased::TEXT::INTEGER END) AS year_leased,
                            MAX(link_to_lease_document) AS link_to_lease_document,
                            MIN(date_registered) AS date_registered,
                            MAX(comments) AS comments
                        FROM {source_schema}.leased_areas
                        GROUP BY parcel_id
                    ) sub;
                """
            else:
                if source_schema=='akwaaba_schema':
                     query = f"""
                        SELECT lease_id, geom, geom_status, lease_status, year_leased,year_requested,agreement_type,phase,
                            ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) AS area_ha,
                            link_to_lease_document
                        FROM (
                            SELECT
                                lease_id,
                                ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) AS geom,
                                MAX(geom_status) AS geom_status,
                                MAX(lease_status) AS lease_status,
                                MAX(agreement_type) AS agreement_type,
                                MAX(CASE WHEN phase::TEXT ~ '^\\d+$' THEN phase::TEXT::INTEGER END) AS phase,
                                MIN(CASE WHEN year_leased::TEXT ~ '^\\d+$' THEN year_leased::TEXT::INTEGER END) AS year_leased,
                                MIN(CASE WHEN year_requested::TEXT ~ '^\\d+$' THEN year_requested::TEXT::INTEGER END) AS year_requested,
                                MAX(link_to_lease_document) AS link_to_lease_document
                            FROM {source_schema}.leased_areas
                            GROUP BY lease_id
                        ) sub;
                    """
                else:
                    query = f"""
                        SELECT lease_id, geom, geom_status, lease_status, year_leased,
                            ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) AS area_ha,
                            link_to_lease_document
                        FROM (
                            SELECT
                                lease_id,
                                ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) AS geom,
                                MAX(geom_status) AS geom_status,
                                MAX(lease_status) AS lease_status,
                                MIN(CASE WHEN year_leased::TEXT ~ '^\\d+$' THEN year_leased::TEXT::INTEGER END) AS year_leased,
                                MAX(link_to_lease_document) AS link_to_lease_document
                            FROM {source_schema}.leased_areas
                            GROUP BY lease_id
                        ) sub;
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
                schema=target_schema,
            )

            # SavePoints.save_layer_progress(f"{schema}_leased_areas_{datetime.now().date()}", True)

            print(f'{source_schema} leased Areas into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_leased_areas_{datetime.now().date()}", False)

            print(e)

            raise



    def load_compartments(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_compartments_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} compartments  already loaded')
        #     return

        try:
            query = None
            # if schema == "akwaaba_schema":
            query = f"""
                SELECT compartment_id, geom, lease_id,
                       ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) AS area_ha,
                       n_psp_target, year_created
                FROM (
                    SELECT
                        compartment_id,
                        ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) AS geom,
                        MAX(lease_id) AS lease_id,
                        MAX(n_psp_target) AS n_psp_target,
                        MIN(CASE WHEN year_created::TEXT ~ '^\\d+$' THEN year_created::TEXT::INTEGER END) AS year_created
                    FROM {source_schema}.compartments
                    GROUP BY compartment_id
                ) sub;
                """
            # else:
            #     query = f"""
            #     SELECT
            #       lease_id,
            #       compartment_id,
            #       geom,
            #       ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
            #       n_psp_target,
            #       year_created
            #     FROM {schema}.compartments
            #     """

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
                schema=target_schema,
            )

            # SavePoints.save_layer_progress(f"{schema}_compartments_{datetime.now().date()}", True)

            print(f'{source_schema} compartments into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_compartments_{datetime.now().date()}", False)

            print(e)

            raise


    def load_plantable_areas(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} subcompartments  already loaded')
        #     return

        try:
            query = None

            # if schema == 'buffalo_schema':
            query = f"""
                SELECT
                  subcompartment_id,
                  geom,
                  ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
                  compartment_id,
                  treatment_type,
                  planting_status,
                  year_planted,
                  planting_type,
                  lp_start_date,
                  plant_start_date,
                  sph
                FROM (
                  SELECT
                    subcompartment_id,
                    ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                    MAX(compartment_id) AS compartment_id,
                    MAX(treatment_type) AS treatment_type,
                    MAX(planting_status) AS planting_status,
                    MIN(CASE WHEN year_planted::TEXT ~ '^\\d+$' THEN year_planted::TEXT::INTEGER END) AS year_planted,
                    MAX(planting_type) AS planting_type,
                    MIN(lp_start_date) AS lp_start_date,
                    MIN(plant_start_date) AS plant_start_date,
                    MAX(sph) AS sph
                  FROM {source_schema}.subcompartments
                  GROUP BY subcompartment_id
                ) sub;
                """
            # else:
            #     query = f"""
            #     SELECT
            #       subcompartment_id,
            #       geom,
            #       ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
            #       compartment_id,
            #       treatment_type,
            #       planting_status,
            #       year_planted,
            #       planting_type,
            #       lp_start_date,
            #       plant_start_date,
            #       sph
            #     FROM {schema}.subcompartments
            #     """

            # Test data merge disabled — the gpkg rows collided with live db rows
            # (e.g. 'test1'/'test2' existed in both), and it never had rows for
            # every schema (no 'colobus' project), which left schemas without a
            # match permanently unrefreshed since the early-return skipped the
            # truncate entirely. Querying the source db alone instead.
            # source_test_data = read_test_data(r"C:\Users\LENOVO\Downloads\test_subcomps_akw_buf_new3.gpkg", source_schema.split('_')[0])
            source_db_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            # if source_db_data.empty or source_test_data.empty:
            #     print(f'{source_schema} subcompartments: source db data and test data mismatch')
            #     return
            #
            # geom_col = source_db_data.geometry.name
            # if source_test_data.geometry.name != geom_col:
            #     source_test_data = source_test_data.rename_geometry(geom_col)
            #
            # if source_test_data.crs != source_db_data.crs:
            #     source_test_data = source_test_data.to_crs(source_db_data.crs)
            #
            # from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
            # for df in (source_db_data, source_test_data):
            #     df[geom_col] = df[geom_col].apply(
            #         lambda g: ShapelyMultiPolygon([g]) if g is not None and g.geom_type == 'Polygon' else g
            #     )
            #
            # source_data = gpd.GeoDataFrame(
            #     pd.concat([source_db_data, source_test_data], ignore_index=True),
            #     crs=source_db_data.crs,
            #     geometry=geom_col
            # )
            source_data = source_db_data

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='subcompartments',
                schema=target_schema,
            )

            # SavePoints.save_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}", True)

            print(f'{source_schema} plantable_Areas into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_subcompartments_{datetime.now().date()}", False)

            print(e)

            raise


    def load_unplantable_areas(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_unplantable_areas_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} unplantable_areas  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              compartment_id,
              unplantable_id,
              geom,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
              damage_type
            FROM {source_schema}.unplantable_areas
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_unplantable_areas_{datetime.now().date()}", True)

            print(f'{source_schema} unplantable_Areas into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_unplantable_areas_{datetime.now().date()}", False)

            print(e)

            raise




    def load_all_layer_stratum_on_lease(source_schema,target_schema, source_conn, target_conn, optional_layers=None):
        """
        optional_layers: list of source table names to merge in addition to subcompartments.
        Allowed values: 'road_buffers', 'firebreaks', 'unplantable_areas', 'protected_areas'.
        Only the tables listed here will be queried.
        """
        if optional_layers is None:
            optional_layers = []

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_lease_layer_stratum_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} lease_layer_stratum already loaded')
        #     return

        UNIFIED_COLS = [
            'lease_stratum_id', 'category', 'subcategory', 'treatment',
            'planting_type', 'year_planted', 'plant_start_date', 'lp_start_date',
            'area_ha', 'sph', 'compartment_id', 'source_layer', 'silviculture_operation_status', 'recipe', 'geom'
        ]

        try:
            frames = []

            # --- Subcompartments (plantable) ---
            # if schema == 'buffalo_schema':
            subcomp_query = f"""
                SELECT
                  subcompartment_id,
                  ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)) as geom,
                  ROUND((ST_Area(ST_Transform(ST_Multi(ST_CollectionExtract(ST_Union(geom), 3)), 4326)::geography) / 10000.0)::numeric, 2) AS area_ha,
                  MAX(compartment_id) AS compartment_id,
                  MAX(treatment_type) AS treatment_type,
                  MAX(sph) AS sph,
                  MAX(planting_status) AS planting_status,
                  MIN(CASE WHEN year_planted::TEXT ~ '^\\d+$' THEN year_planted::TEXT::INTEGER END) AS year_planted,
                  MAX(planting_type) AS planting_type,
                  MIN(lp_start_date) AS lp_start_date,
                  MIN(plant_start_date) AS plant_start_date
                FROM {source_schema}.subcompartments
                GROUP BY subcompartment_id;
                """
            # else:
            #     subcomp_query = f"""
            #     SELECT
            #       subcompartment_id,
            #       geom,
            #       ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
            #       compartment_id,
            #       treatment_type,
            #       planting_status,
            #       year_planted,
            #       planting_type,
            #       sph,
            #       lp_start_date,
            #       plant_start_date
            #     FROM {schema}.subcompartments
                # """

            subcomps = DataManagement.execute_spatial_query(conn=source_conn, query=subcomp_query)

            if not subcomps.empty:
                subcomps['category'] = 'plantable'
                subcomps['subcategory'] = subcomps['planting_status'].apply(
                    lambda x: 'planted' if str(x).lower() == 'planted'
                    else 'planted but protected' if str(x).lower() == 'planted but protected'
                    else 'planned_planting'
                )
                subcomps = subcomps.rename(columns={'subcompartment_id': 'lease_stratum_id', 'treatment_type': 'treatment', subcomps.geometry.name: 'geom'})
                subcomps = gpd.GeoDataFrame(subcomps, geometry='geom', crs=subcomps.crs)
                subcomps['source_layer'] = 'subcompartments'
                subcomps['silviculture_operation_status'] = subcomps['subcategory'].apply(
                    lambda x: 'inactive' if x == 'planted but protected' else 'active'
                )
                subcomps['recipe'] = None
                frames.append(subcomps[UNIFIED_COLS])

            # --- Road Buffers (unplantable) ---
            if 'road_buffers' in optional_layers:
                print(f'{source_schema} loading road_buffers...')
                try:
                    road_buffer_query = f"""
                    SELECT
                      road_buffer_id,
                      ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0)::numeric, 2) AS area_ha,
                      geom
                    FROM {source_schema}.road_buffers
                    """
                    road_buffers = DataManagement.execute_spatial_query(conn=source_conn, query=road_buffer_query)
                    if not road_buffers.empty:
                        road_buffers = road_buffers.rename(columns={'road_buffer_id': 'lease_stratum_id', road_buffers.geometry.name: 'geom'})
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
                        road_buffers['silviculture_operation_status'] = 'inactive'
                        road_buffers['recipe'] = None
                        frames.append(road_buffers[UNIFIED_COLS])
                        print(f'{source_schema} road_buffers: {len(road_buffers)} records')
                    else:
                        print(f'{source_schema} road_buffers: 0 records found')
                except Exception as e:
                    print(f'{source_schema} road_buffers skipped: {e}')

           

            # --- Firebreaks (unplantable) ---
            if 'firebreaks' in optional_layers:
                print(f'{source_schema} loading firebreaks...')
                try:
                    firebreak_query = f"""
                    SELECT
                      firebreak_id,
                      ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0)::numeric, 2) AS area_ha,
                      geom
                    FROM {source_schema}.firebreaks
                    """
                    firebreaks = DataManagement.execute_spatial_query(conn=source_conn, query=firebreak_query)
                    if not firebreaks.empty:
                        firebreaks = firebreaks.rename(columns={'firebreak_id': 'lease_stratum_id', firebreaks.geometry.name: 'geom'})
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
                        firebreaks['silviculture_operation_status'] = 'inactive'
                        firebreaks['recipe'] = None
                        frames.append(firebreaks[UNIFIED_COLS])
                        print(f'{source_schema} firebreaks: {len(firebreaks)} records')
                    else:
                        print(f'{source_schema} firebreaks: 0 records found')
                except Exception as e:
                    print(f'{source_schema} firebreaks skipped: {e}')

            # --- Unplantable Areas (unplantable, subcategory from damage_type) ---
            if 'unplantable_areas' in optional_layers:
                print(f'{source_schema} loading unplantable_areas...')
                try:
                    unplantable_query = f"""
                    SELECT
                      unplantable_id,
                      compartment_id,
                      ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0)::numeric, 2) AS area_ha,
                      damage_type,
                      geom
                    FROM {source_schema}.unplantable_areas
                    """
                    unplantables = DataManagement.execute_spatial_query(conn=source_conn, query=unplantable_query)
                    if not unplantables.empty:
                        unplantables = unplantables.rename(columns={
                            'unplantable_id': 'lease_stratum_id',
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
                        unplantables['silviculture_operation_status'] = 'inactive'
                        unplantables['recipe'] = None
                        frames.append(unplantables[UNIFIED_COLS])
                        print(f'{source_schema} unplantable_areas: {len(unplantables)} records')
                    else:
                        print(f'{source_schema} unplantable_areas: 0 records found')
                except Exception as e:
                    print(f'{source_schema} unplantable_areas skipped: {e}')

            # --- Protected Areas (plantable) ---
            if 'protected_areas' in optional_layers:
                print(f'{source_schema} loading protected_areas...')
                try:
                    protected_query = f"""
                    SELECT
                      protected_area_id,
                      ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000.0)::numeric, 2) AS area_ha,
                      geom
                    FROM {source_schema}.protected_areas
                    """
                    protected = DataManagement.execute_spatial_query(conn=source_conn, query=protected_query)
                    if not protected.empty:
                        protected = protected.rename(columns={'protected_area_id': 'lease_stratum_id', protected.geometry.name: 'geom'})
                        protected = gpd.GeoDataFrame(protected, geometry='geom', crs=protected.crs)
                        protected['category'] = 'plantable'
                        protected['subcategory'] = protected['area_ha'].apply(
                            lambda x: 'Other areas' if x > 5 else 'protection'
                        )
                        protected['treatment'] = None
                        protected['planting_type'] = None
                        protected['year_planted'] = None
                        protected['plant_start_date'] = None
                        protected['lp_start_date'] = None
                        protected['sph'] = None
                        protected['compartment_id'] = None
                        protected['source_layer'] = 'protected_areas'
                        protected['silviculture_operation_status'] = 'inactive'
                        protected['recipe'] = None
                        frames.append(protected[UNIFIED_COLS])
                        print(f'{source_schema} protected_areas: {len(protected)} records')
                    else:
                        print(f'{source_schema} protected_areas: 0 records found')
                except Exception as e:
                    print(f'{source_schema} protected_areas skipped: {e}')

            if not frames:
                print(f'No data found for {source_schema} subcompartments')
                return

            layer_summary = ', '.join(f"{f['source_layer'].iloc[0]}({len(f)})" for f in frames)
            print(f'{source_schema} merging layers: {layer_summary}')

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
                comp_query = f"SELECT compartment_id, geom FROM {source_schema}.compartments"
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

      
            # source_data = Validation.validate_and_fix_geometries(source_data)

            # Original unsnapped save — uncomment to roll back
            # DataManagement.save_spatial_data_to_postgres(
            #     conn=target_conn,
            #     data=source_data,
            #     table_name='lease_areas_stratum',
            #     schema=schema
            # )

            try:
                


                layer_union = source_data['geom'].union_all()
                snapped = source_data.copy()
                snapped['geom'] = source_data['geom'].apply(
                    lambda g: _to_multipolygon(snap(g, layer_union, tolerance=0.000002))
                )
                snapped = gpd.GeoDataFrame(snapped, geometry='geom', crs=source_data.crs)
                snapped = snapped[snapped['geom'].notna()].copy()
                snapped = Validation.validate_and_fix_geometries(snapped)
                snapped['geom'] = snapped['geom'].apply(_to_multipolygon)
                snapped = snapped[snapped['geom'].notna()].copy()
                DataManagement.save_spatial_data_to_postgres(
                    conn=target_conn,
                    data=snapped,
                    table_name='lease_areas_stratum',
                    schema=target_schema,
    
                    )
                print(f'{target_schema} Lease Layer Stratum Snapped Loaded Successfully')
            except Exception as snap_err:
                print(f'{target_schema} snapping skipped: {snap_err}')
                return


            # SavePoints.save_layer_progress(f"{target_schema}_lease_layer_stratum_{datetime.now().date()}", True)

            print(f'{target_schema} Lease Layer Stratum Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_lease_layer_stratum_{datetime.now().date()}", False)

            print(e)

            raise





    def load_field_mapped_farms(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_field_mapped_farms_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} field_mapped_farms  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              compartment_id,
              farm_id,
              geom,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
              date_mapped,
              mapped_by
            FROM {source_schema}.field_mapped_farms
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_field_mapped_farms_{datetime.now().date()}", True)

            print(f'{source_schema} Field Mapped Farms into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_field_mapped_farms_{datetime.now().date()}", False)

            print(e)

            raise



    def load_intercropped_farms(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_intercropped_farms_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} intercropped_farms  already loaded')
        #     return

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
            FROM {source_schema}.intercropped_farms
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_intercropped_farms_{datetime.now().date()}", True)

            print(f'{source_schema} Intercropped Farms into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_intercropped_farms_{datetime.now().date()}", False)

            print(e)

            raise



    def load_rb_roads(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_rb_roads_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} rb_roads  already loaded')
        #     return

        try:
            
            # only buffalo has road_type
            if "buffalo" in target_schema:
                query = f"""
                    SELECT
                    road_class,
                    road_type,
                    condition,
                    road_id,
                    geom,
                    road_treatment_status,
                    ROUND((ST_Length(ST_Transform(geom, 4326)::geography) / 1000)::numeric, 2) AS length_km,
                    date_created,
                    compartment_id,
                    status,
                    build_year,
                    area
                    FROM {source_schema}.rb_roads
                    """
            else:
                query = f"""
                    SELECT
                    road_class,
                    condition,
                    road_id,
                    geom,
                    road_treatment_status,
                    ROUND((ST_Length(ST_Transform(geom, 4326)::geography) / 1000)::numeric, 2) AS length_km,
                    date_created,
                    compartment_id,
                    status,
                    build_year,
                    area
                    FROM {source_schema}.rb_roads
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_rb_roads_{datetime.now().date()}", True)

            # print(f'{schema} Roads Loaded Successfully')
            print(f'{source_schema} Rb Roads Loaded into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_rb_roads_{datetime.now().date()}", False)

            print(e)

            raise



    def load_rb_assigned_psps(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_assigned_psps_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} assigned_psps  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              psp_id,
              compartment_id,
              geom,
              date_created,
              generated_by
            FROM {source_schema}.assigned_psps
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_assigned_psps_{datetime.now().date()}", True)

            print(f'{source_schema} Assigned psps into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_assigned_psps_{datetime.now().date()}", False)

            print(e)

            raise



    def load_rb_completed_psps(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_completed_psps_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} completed_psps  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              psp_id,
              compartment_id,
              geom,
              date_completed,
              psp_cardinal_location
            FROM {source_schema}.completed_psps
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_completed_psps_{datetime.now().date()}", True)

            print(f'{source_schema} Completed psps into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_completed_psps_{datetime.now().date()}", False)

            print(e)

            raise


    def load_firebreaks(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_firebreaks_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} firebreaks  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              firebreak_id,
              lease_id,
              CAST(perimeter AS DOUBLE PRECISION) AS perimeter,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
              geom
            FROM {source_schema}.firebreaks
            """
            source_data = DataManagement.execute_spatial_query(
                conn=source_conn,
                query=query,
            )

            if source_data.empty:
                print("No data found")
                return

            source_data = Validation.validate_and_fix_geometries(source_data)
            source_data['geom'] = source_data['geom'].apply(_to_multipolygon)
            source_data = source_data[source_data['geom'].notna()].copy()

            DataManagement.save_spatial_data_to_postgres(
                conn=target_conn,
                data=source_data,
                table_name='firebreaks',
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_firebreaks_{datetime.now().date()}", True)

            print(f'{source_schema} Firebreaks psps into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_firebreaks_{datetime.now().date()}", False)

            print(e)

            raise


    def load_protected_areas(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_protected_areas_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} protected_areas  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              protected_area_id,
              landcover,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
              geom
            FROM {source_schema}.protected_areas
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_protected_areas_{datetime.now().date()}", True)

            print(f'{source_schema} Protected areas into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_protected_areas_{datetime.now().date()}", False)

            print(e)

            raise


    def load_road_buffers(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_road_buffers_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} road_buffers  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              road_buffer_id,
              ROUND((ST_Area(ST_Transform(geom, 4326)::geography) / 10000)::numeric, 2) as area_ha,
              geom
            FROM {source_schema}.road_buffers
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
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_road_buffers_{datetime.now().date()}", True)

            print(f'{source_schema} road buffers into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_road_buffers_{datetime.now().date()}", False)

            print(e)

            raise


    def load_culverts(source_schema,target_schema, source_conn, target_conn):

        # is_loaded = SavePoints.get_layer_progress(f"{schema}_culverts_{datetime.now().date()}")
        # if is_loaded:
        #     print(f'{schema} culverts  already loaded')
        #     return

        try:
            query = f"""
            SELECT
              road_id,
              culvert_id,
              culvert_type,
              legacy_culvert_id,
              pipe_diameter_mm,
              pipe_length_m,
              no_of_pipes,
              pipe_type,
              headwalls,
              status,
              build_year,
              date_maintained,
              compartment_id,
              geom
            FROM {source_schema}.culverts
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
                table_name='culverts',
                schema=target_schema
            )

            # SavePoints.save_layer_progress(f"{schema}_culverts_{datetime.now().date()}", True)

            print(f'{source_schema} Culverts into {target_schema} Loaded Successfully')

        except Exception as e:

            # SavePoints.save_layer_progress(f"{schema}_culverts_{datetime.now().date()}", False)

            print(e)

            raise




