from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from etl_util_chameleon import Extract_Transform_Load
from update_leased_areas_tracker import update_leased_areas_tracker


# Specify which optional tables are available per schema.
# Allowed values: 'road_buffers', 'water_buffers', 'firebreaks', 'unplantable_areas', 'protected_areas'
SUBCOMP_OPTIONAL_LAYERS = {
    'akwaaba_schema': ['protected_areas', 'unplantable_areas'],
    'buffalo_schema': ['road_buffers','unplantable_areas', 'firebreaks','protected_areas'],
    'colobus_schema': ['road_buffers','protected_areas', 'firebreaks', 'unplantable_areas'],
}


def run_chameleon_etl_pipeline(source_schema,target_schema, source_conn, target_conn):
    try:
        target_conn['sync'].dispose()

        optional_layers = SUBCOMP_OPTIONAL_LAYERS.get(source_schema, [])
        load_all_layer_stratum_on_lease = partial(
            Extract_Transform_Load.load_all_layer_stratum_on_lease,
            optional_layers=optional_layers
        )
        load_all_layer_stratum_on_lease.__name__ = 'load_all_layer_stratum_on_lease'

        # Akwaaba does not have firebreaks
        if target_schema == 'akwaaba_schema':
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
                load_all_layer_stratum_on_lease
            ]

        # Buffalo currently does not have field mapped farms and intercropped farms
        elif target_schema == 'buffalo_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_plantable_areas,
                # Extract_Transform_Load.load_unplantable_areas,
                Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                Extract_Transform_Load.load_firebreaks,
                # Extract_Transform_Load.load_protected_areas,
                load_all_layer_stratum_on_lease

            ]

        # Colobus currently does not have intercropped areas
        elif target_schema == 'colobus_schema':
            layers = [
                Extract_Transform_Load.load_leased_areas,
                Extract_Transform_Load.load_compartments,
                Extract_Transform_Load.load_plantable_areas,
                # Extract_Transform_Load.load_unplantable_areas,
                # Extract_Transform_Load.load_field_mapped_farms,
                Extract_Transform_Load.load_rb_roads,
                # Extract_Transform_Load.load_rb_assigned_psps,
                # Extract_Transform_Load.load_rb_completed_psps,
                Extract_Transform_Load.load_firebreaks,
                # Extract_Transform_Load.load_protected_areas,
                # Extract_Transform_Load.load_road_buffers,
                Extract_Transform_Load.load_culverts,
                load_all_layer_stratum_on_lease

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

        # Rejoins buffalo_schema.leased_areas with lease_tracker_schema on the
        # chameleon target — must run after load_leased_areas has refreshed
        # leased_areas above, not concurrently with it.
        if target_schema == 'buffalo_schema':
            update_leased_areas_tracker()

    except Exception:
        raise


