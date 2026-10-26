"""
update_leased_areas_tracker.py
-------------------------------
Refreshes buffalo_schema.leased_areas_tracker on the chameleon target database
by joining buffalo_schema.leased_areas, on parcel_id, with the stage, community,
chiefdom, district and family from a fresh Rainforest Builder export (the system
of record). lease_tracker_schema.current_stage / land_tenure, no longer updated,
only fill values the export lacks.

Safe to rerun: truncates the table and reinserts from the current join every time.

Usage:
    python update_leased_areas_tracker.py
"""

import json
import os

import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from download_leased_areas import GPKG_LAYER, get_leased_areas_gpkg

load_dotenv()

HOST     = os.getenv('CHAMELEON_TARGET_HOST')
DB       = os.getenv('CHAMELEON_TARGET_DATABASE_NAME')
PORT     = os.getenv('CHAMELEON_TARGET_PORT')
USER     = os.getenv('GIS_CREATE_USERNAME')
PASSWORD = os.getenv('GIS_CREATE_PASSWORD')

CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS buffalo_schema.leased_areas_tracker (
        id SERIAL PRIMARY KEY,
        lease_id CHARACTER VARYING,
        parcel_id CHARACTER VARYING,
        legacy_lease_id CHARACTER VARYING,
        geom geometry(MultiPolygon, 4326),
        geom_status CHARACTER VARYING,
        lease_status CHARACTER VARYING,
        year_leased INTEGER,
        area_ha_wgs84 DOUBLE PRECISION,
        area_ha_utm29 DOUBLE PRECISION,
        link_to_lease_document CHARACTER VARYING,
        date_registered DATE,
        comments CHARACTER VARYING,
        current_stage CHARACTER VARYING,
        community CHARACTER VARYING,
        chiefdom CHARACTER VARYING,
        district CHARACTER VARYING,
        family CHARACTER VARYING
    )
"""

INSERT_SQL = """
    INSERT INTO buffalo_schema.leased_areas_tracker (
        lease_id, parcel_id, legacy_lease_id, geom, geom_status, lease_status, year_leased,
        area_ha_wgs84, area_ha_utm29, link_to_lease_document, date_registered, comments,
        current_stage, community, chiefdom, district, family
    )
    SELECT
        la.lease_id, la.parcel_id, la.legacy_lease_id, la.geom, la.geom_status, la.lease_status, la.year_leased,
        la.area_ha_wgs84, la.area_ha_utm29, la.link_to_lease_document, la.date_registered, la.comments,
        COALESCE(ex.current_stage, cs.current_stage), COALESCE(ex.community, lt.community),
        COALESCE(ex.chiefdom, lt.chiefdom), COALESCE(ex.district, lt.district), COALESCE(ex.family, lt.family)
    FROM buffalo_schema.leased_areas la
    LEFT JOIN jsonb_to_recordset(CAST(:export AS jsonb)) AS ex(
        parcel_id TEXT, current_stage TEXT, community TEXT, chiefdom TEXT, district TEXT, family TEXT
    ) ON la.parcel_id = ex.parcel_id
    LEFT JOIN lease_tracker_schema.current_stage cs ON la.parcel_id = cs.parcel_id
    LEFT JOIN lease_tracker_schema.land_tenure lt ON la.parcel_id = lt.parcel_id
"""

GRANT_SQL = [
    'GRANT SELECT ON buffalo_schema.leased_areas_tracker TO gis_viewer',
    'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON buffalo_schema.leased_areas_tracker TO gis_update',
    'GRANT USAGE, SELECT ON SEQUENCE buffalo_schema.leased_areas_tracker_id_seq TO gis_viewer',
    'GRANT USAGE, SELECT ON SEQUENCE buffalo_schema.leased_areas_tracker_id_seq TO gis_update',
]


EXPORT_COLUMNS = ['parcel_id', 'current_stage', 'community', 'chiefdom', 'district', 'family']


def _export_attributes():
    """The tracker attributes of every parcel in a fresh Rainforest Builder export, as JSON."""
    data = gpd.read_file(get_leased_areas_gpkg(), layer=GPKG_LAYER, ignore_geometry=True)
    data = data[EXPORT_COLUMNS].astype(object).where(data[EXPORT_COLUMNS].notna(), None)
    return json.dumps(data.to_dict('records'))


def update_leased_areas_tracker():
    export = _export_attributes()  # before opening the connection: the download takes a while
    engine = create_engine(
        URL.create(
            drivername='postgresql+psycopg2',
            username=USER,
            password=PASSWORD,
            host=HOST,
            port=int(PORT),
            database=DB,
        ),
        pool_pre_ping=True,
    )

    try:
        with engine.connect() as conn:
            conn.execute(text(CREATE_SQL))
            conn.commit()

            conn.execute(text('TRUNCATE TABLE buffalo_schema.leased_areas_tracker'))
            result = conn.execute(text(INSERT_SQL), {'export': export})
            conn.commit()
            print(f'buffalo_schema.leased_areas_tracker refreshed: {result.rowcount} rows')

            for grant in GRANT_SQL:
                conn.execute(text(grant))
            conn.commit()
    finally:
        engine.dispose()


if __name__ == '__main__':
    update_leased_areas_tracker()
