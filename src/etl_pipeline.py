from concurrent.futures import ThreadPoolExecutor, as_completed

from etl_util import Extract_Transform_Load


def run_etl_pipeline(schema, source_conn, target_conn):
    try:
        # Akwaaba has all the layers
        if schema == 'akwaaba_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_subcompartments,
                Extract_Transform_Load.load_unplantable_areas,
                Extract_Transform_Load.load_field_mapped_farms,
                Extract_Transform_Load.load_intercropped_farms,
                Extract_Transform_Load.load_rb_roads,
                Extract_Transform_Load.load_rb_assigned_psps,
                Extract_Transform_Load.load_rb_completed_psps,
            ]

        # Buffalo currently does not have field mapped farms and intercropped farms
        elif schema == 'buffalo_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_subcompartments,
                Extract_Transform_Load.load_unplantable_areas,
                Extract_Transform_Load.load_rb_roads,
                Extract_Transform_Load.load_rb_assigned_psps,
                Extract_Transform_Load.load_rb_completed_psps,
            ]

        # Colobus currently does not have intercropped areas
        elif schema == 'colobus_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_subcompartments,
                Extract_Transform_Load.load_unplantable_areas,
                Extract_Transform_Load.load_field_mapped_farms,
                Extract_Transform_Load.load_rb_roads,
                Extract_Transform_Load.load_rb_assigned_psps,
                Extract_Transform_Load.load_rb_completed_psps,
            ]

        else:
            return

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(fn, schema, source_conn, target_conn): fn.__name__
                for fn in layers
            }
            for future in as_completed(futures):
                future.result()

    except Exception:
        raise
