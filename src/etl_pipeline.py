from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from etl_util import Extract_Transform_Load


# Specify which optional tables are available per schema.
# Allowed values: 'road_buffers', 'water_buffers', 'firebreaks', 'unplantable_areas', 'protected_areas'
SUBCOMP_OPTIONAL_LAYERS = {
    'akwaaba_schema': ['protected_areas', 'unplantable_areas'],
    'buffalo_schema': ['unplantable_areas', 'firebreaks'],
    'colobus_schema': ['road_buffers', 'water_buffers', 'firebreaks', 'unplantable_areas'],
}


def run_etl_pipeline(schema, source_conn, target_conn):
    try:
        optional_layers = SUBCOMP_OPTIONAL_LAYERS.get(schema, [])
        load_subcompartments = partial(
            Extract_Transform_Load.load_subcompartments,
            optional_layers=optional_layers
        )
        load_subcompartments.__name__ = 'load_subcompartments'

        # Akwaaba does not have firebreaks
        if schema == 'akwaaba_schema':
            layers = [
                # Extract_Transform_Load.load_leased_areas,
                # Extract_Transform_Load.load_compartments,
                load_subcompartments,
                # Extract_Transform_Load.load_field_mapped_farms,
                # Extract_Transform_Load.load_intercropped_farms,
                # Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                # Extract_Transform_Load.load_firebreaks
            ]

        # Buffalo currently does not have field mapped farms and intercropped farms
        elif schema == 'buffalo_schema':
            layers = [
                # Extract_Transform_Load.load_leased_areas,
                # Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_subcompartments,
                
                # Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                # Extract_Transform_Load.load_firebreaks
            ]

        # Colobus currently does not have intercropped areas
        elif schema == 'colobus_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                load_subcompartments,
                Extract_Transform_Load.load_field_mapped_farms,
                Extract_Transform_Load.load_rb_roads,
                Extract_Transform_Load.load_rb_assigned_psps,
                Extract_Transform_Load.load_rb_completed_psps,
                Extract_Transform_Load.load_firebreaks
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
