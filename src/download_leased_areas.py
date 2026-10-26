"""
download_leased_areas.py
------------------------
Buffalo leased areas are no longer maintained in the local (source) database.
The system of record is Rainforest Builder (ESG → Land Leasing). This module
downloads its "Export as GPKG" file and reads it for load_leased_areas. Each
download is also copied to the local database as buffalo_schema.leased_areas_tracker,
and merged into the local buffalo_schema.leased_areas (see MERGE_SQL).

Credentials come from .env: RB_EMAIL, RB_PASSWORD, and SOURCE_* for the local database.
Set RB_LEASED_AREAS_GPKG to a path to load an already-downloaded file instead.

Usage:
    python download_leased_areas.py            # downloads exports/leased_areas_<timestamp>.gpkg
    python download_leased_areas.py --headed   # show the browser (debug selectors)
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import geopandas as gpd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

load_dotenv()

BASE_URL    = 'https://app.rainforestbuilder.com'
LOGIN_URL   = f'{BASE_URL}/login'
EXPORT_DIR  = Path(__file__).resolve().parent.parent / 'exports'
GPKG_LAYER  = 'leased_areas_tracker'
LOCAL_SCHEMA = 'buffalo_schema'
LOCAL_TABLE  = 'leased_areas_tracker'

# Brings the local buffalo_schema.leased_areas (UTM 29N) in line with the export just
# saved to leased_areas_tracker, matching on parcel_id. The columns the export has are
# overwritten (the website is the system of record); the ones it lacks —
# link_to_lease_document, comments, year_requested, agreement_type, phase — are kept.
# Parcels new on the website are inserted.
MERGE_SQL = [
    """
    UPDATE buffalo_schema.leased_areas la SET
        lease_id        = t.lease_id,
        legacy_lease_id = t.legacy_lease_id,
        geom_status     = t.geom_status,
        lease_status    = t.lease_status,
        year_leased     = t.year_leased::INTEGER,
        date_registered = t.date_registered::DATE,
        geom            = ST_Multi(ST_Transform(t.geom, 32629)),
        area_ha         = t.area_ha_utm29
    FROM buffalo_schema.leased_areas_tracker t
    WHERE la.parcel_id = t.parcel_id
    """,
    """
    INSERT INTO buffalo_schema.leased_areas (
        id, lease_id, parcel_id, legacy_lease_id, geom_status, lease_status,
        year_leased, date_registered, geom, area_ha
    )
    SELECT
        (SELECT COALESCE(MAX(id), 0) FROM buffalo_schema.leased_areas) + ROW_NUMBER() OVER (ORDER BY t.parcel_id),
        t.lease_id, t.parcel_id, t.legacy_lease_id, t.geom_status, t.lease_status,
        t.year_leased::INTEGER, t.date_registered::DATE, ST_Multi(ST_Transform(t.geom, 32629)), t.area_ha_utm29
    FROM buffalo_schema.leased_areas_tracker t
    WHERE NOT EXISTS (SELECT 1 FROM buffalo_schema.leased_areas la WHERE la.parcel_id = t.parcel_id)
    """,
]
# The project the export must come from — the site exports whichever project is selected
PROJECT_NAME = 'Buffalo'

# Columns of buffalo_schema.leased_areas the export provides. It has no
# link_to_lease_document or comments; those load as NULL.
REQUIRED_COLUMNS = [
    'lease_id', 'parcel_id', 'legacy_lease_id', 'geom_status', 'lease_status', 'year_leased',
    'area_ha_wgs84', 'area_ha_utm29', 'date_registered',
]


def download_leased_areas_gpkg(out_dir=EXPORT_DIR, headless=True, timeout_ms=120_000):
    """Logs in to Rainforest Builder and saves the Land Leasing GeoPackage export. Returns its path."""
    # Playwright's sync API refuses to run inside an asyncio loop (Jupyter): use a worker thread
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_download, out_dir, headless, timeout_ms).result()


def _download(out_dir, headless, timeout_ms):
    email, password = os.getenv('RB_EMAIL'), os.getenv('RB_PASSWORD')
    if not email or not password:
        raise RuntimeError('Set RB_EMAIL and RB_PASSWORD in .env to download Buffalo leased areas')

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'leased_areas_{datetime.now():%Y-%m-%d_%H%M%S}.gpkg'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            # posthog-js treats the HeadlessChrome user agent as a bot and never loads feature
            # flags, so the ESG module stays hidden: present as the same browser, minus "Headless"
            user_agent = browser.new_page().evaluate('navigator.userAgent').replace('HeadlessChrome', 'Chrome')
            ctx = browser.new_context(accept_downloads=True, user_agent=user_agent)
            page = ctx.new_page()
            page.set_default_timeout(timeout_ms)

            # Go to /login directly: other pages only redirect there after the app loads
            page.goto(LOGIN_URL)
            page.locator('#email').fill(email)
            page.locator('#password').fill(password)
            page.get_by_role('button', name='Login', exact=True).click()
            page.wait_for_url(lambda url: '/login' not in url)

            # Login opens the account's default project; the export is per project
            project_menu = page.locator('button[aria-haspopup="menu"]').first
            if project_menu.inner_text().strip() != PROJECT_NAME:
                project_menu.click()
                page.locator('[role=menuitem][aria-haspopup="menu"]').first.click()
                page.get_by_role('menuitem', name=PROJECT_NAME, exact=True).click()
                page.wait_for_function(
                    "name => document.querySelector('button[aria-haspopup=\"menu\"]')?.innerText.trim() === name",
                    arg=PROJECT_NAME,
                )

            # The ESG module is behind a per-project feature flag: /esg/land-leasing is a 404
            # until the flags load, so navigate through the sidebar link once it shows
            page.locator('a[href="/esg/land-leasing"]').click()
            page.get_by_text('Parcel ID', exact=True).wait_for()
            if project_menu.inner_text().strip() != PROJECT_NAME:
                raise RuntimeError(f'Rainforest Builder is not on the {PROJECT_NAME} project — nothing downloaded')

            # Opens a "Download lease data" dialog; the export covers the current filters,
            # which a fresh login leaves empty (all parcels)
            page.get_by_role('button', name='Export as GPKG').click()
            with page.expect_download(timeout=timeout_ms) as dl_info:
                page.get_by_role('dialog').get_by_role('button', name='Download', exact=True).click()
            download = dl_info.value
            if download.failure():
                raise RuntimeError(f'GPKG export failed: {download.failure()}')
            download.save_as(target)
        finally:
            browser.close()

    read_leased_areas_gpkg(target)  # fail now on a bad export, not halfway through the ETL
    # Only now that the new export is good: a failed download keeps the previous one
    for old in out_dir.glob('leased_areas_*.gpkg'):
        if old != target:
            try:
                old.unlink()
            except PermissionError:  # open elsewhere (e.g. QGIS): removed on a later run
                print(f'Could not delete {old.name} (in use), leaving it')
    print(f'Downloaded Buffalo leased areas: {target}')
    save_leased_areas_locally(target)
    return target


def save_leased_areas_locally(path):
    """
    Replaces buffalo_schema.leased_areas_tracker in the local database with the
    export (all columns), then merges it into the local buffalo_schema.leased_areas.
    A local copy is a convenience, so a failure only warns: it never stops the ETL.
    """
    data = gpd.read_file(path, layer=GPKG_LAYER).rename_geometry('geom')
    # Like the push to the remote: parcels not yet surveyed (no geometry) are left out
    data = data[data['geom'].notna()]
    engine = create_engine(URL.create(
        drivername='postgresql+psycopg2',
        username=os.getenv('SOURCE_USERNAME'),
        password=os.getenv('SOURCE_PASSWORD'),
        host=os.getenv('SOURCE_HOST'),
        port=int(os.getenv('SOURCE_PORT')),
        database=os.getenv('SOURCE_DATABASE_NAME'),
    ))
    try:
        # One transaction: QGIS keeps seeing the previous data until both tables are updated
        with engine.begin() as conn:
            if inspect(conn).has_table(LOCAL_TABLE, schema=LOCAL_SCHEMA):
                # Truncate rather than replace, keeping the table's grants and dependent views
                conn.execute(text(f'TRUNCATE TABLE "{LOCAL_SCHEMA}"."{LOCAL_TABLE}"'))
            data.to_postgis(LOCAL_TABLE, conn, schema=LOCAL_SCHEMA, if_exists='append', index=False)
            updated, inserted = (conn.execute(text(sql)).rowcount for sql in MERGE_SQL)
        print(f'Saved {len(data)} parcels to local {LOCAL_SCHEMA}.{LOCAL_TABLE}; '
              f'local {LOCAL_SCHEMA}.leased_areas: {updated} updated, {inserted} added')
    except Exception as e:
        print(f'Warning: could not save leased areas to the local database: {e}')
    finally:
        engine.dispose()


def get_leased_areas_gpkg():
    """
    The GeoPackage to load: RB_LEASED_AREAS_GPKG if set, else a fresh download —
    leases can change several times a day, so an earlier download is never reused.
    """
    override = os.getenv('RB_LEASED_AREAS_GPKG')
    if override:
        return Path(override)
    return download_leased_areas_gpkg()


def read_leased_areas_gpkg(path):
    """Reads the export as buffalo_schema.leased_areas rows (one per parcel_id), validating it first."""
    data = gpd.read_file(path, layer=GPKG_LAYER)

    missing = [c for c in REQUIRED_COLUMNS if c not in data.columns]
    if missing:
        raise ValueError(f'{path}: export is missing columns {missing} — has the Rainforest Builder export changed?')
    if data.empty:
        raise ValueError(f'{path}: export has no features')
    if data['parcel_id'].isna().any():
        raise ValueError(f'{path}: {int(data["parcel_id"].isna().sum())} features have no parcel_id')
    dupes = data.loc[data['parcel_id'].duplicated(), 'parcel_id'].unique().tolist()
    if dupes:
        raise ValueError(f'{path}: duplicate parcel_id {dupes}')
    if data.crs is None or data.crs.to_epsg() != 4326:
        data = data.to_crs(4326) if data.crs is not None else data.set_crs(4326)

    data = data.rename_geometry('geom')[REQUIRED_COLUMNS + ['geom']]
    data['link_to_lease_document'] = None
    data['comments'] = None
    return data


if __name__ == '__main__':
    download_leased_areas_gpkg(headless='--headed' not in sys.argv)
