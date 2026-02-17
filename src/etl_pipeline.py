import asyncio

from etl_util import Extract_Transform_Load




async def run_etl_pipeline(schema,source_conn,target_conn):
    try:
        # Akwaaba has all the layers
        if schema=='akwaaba_schema':
            await asyncio.gather(
                Extract_Transform_Load.load_leased_areas(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_compartments(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_subcompartments(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_unplantable_areas(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_field_mapped_farms(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_intercropped_farms(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_roads(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_assigned_psps(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_completed_psps(schema=schema,source_conn=source_conn,target_conn=target_conn)
            )

        # Buffalo currently does not have farm mapped farms and intercropped farms
        elif schema =='buffalo_schema':
            await asyncio.gather(
                Extract_Transform_Load.load_leased_areas(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_compartments(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_subcompartments(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_unplantable_areas(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_roads(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_assigned_psps(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_completed_psps(schema=schema,source_conn=source_conn,target_conn=target_conn)
            )

        # Colobus currently does not have intercroppted areas
        elif schema == 'colobus_schema':
            await asyncio.gather(
                Extract_Transform_Load.load_leased_areas(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_compartments(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_subcompartments(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_unplantable_areas(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_field_mapped_farms(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_roads(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_assigned_psps(schema=schema,source_conn=source_conn,target_conn=target_conn),
                Extract_Transform_Load.load_rb_completed_psps(schema=schema,source_conn=source_conn,target_conn=target_conn)
            )
    except Exception:
        raise
