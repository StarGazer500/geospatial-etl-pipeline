from concurrent.futures import ThreadPoolExecutor, as_completed



from setup_schemas import project_schema
from etl_util_project_level import Extract_Transform_Load


def run_project_level_etl_pipeline(source_schema, target_schema, source_conn, target_conn):

    try:
        target_conn['sync'].dispose()

        # 'buffalo_schema_draft' loads the same layers as 'buffalo_schema'
        project = project_schema(target_schema)

        # Akwaaba does not have firebreaks
        if project == 'akwaaba_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_plantable_areas,
                # Extract_Transform_Load.load_unplantable_areas,
                # Extract_Transform_Load.load_field_mapped_farms,
                # Extract_Transform_Load.load_intercropped_farms,
                Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                # Extract_Transform_Load.load_protected_areas,
                Extract_Transform_Load.load_culverts,
                Extract_Transform_Load.load_lease_areas_stratum,
            ]

        # Buffalo currently does not have field mapped farms and intercropped farms
        elif project == 'buffalo_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_plantable_areas,
                # Extract_Transform_Load.load_unplantable_areas,
                Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                # Extract_Transform_Load.load_firebreaks,
                # Extract_Transform_Load.load_protected_areas,
                Extract_Transform_Load.load_lease_areas_stratum,

            ]

        # Colobus currently does not have intercropped areas
        elif project == 'colobus_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_plantable_areas,
                # Extract_Transform_Load.load_unplantable_areas,
                # Extract_Transform_Load.load_field_mapped_farms,
                Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                # Extract_Transform_Load.load_firebreaks,
                # Extract_Transform_Load.load_protected_areas,
                # Extract_Transform_Load.load_road_buffers,
                Extract_Transform_Load.load_culverts,
                Extract_Transform_Load.load_lease_areas_stratum,

            ]

        else:
            return

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(fn, source_schema, target_schema, source_conn, target_conn): fn.__name__
                for fn in layers
            }
            for future in as_completed(futures):
                future.result()

    except Exception:
        raise
