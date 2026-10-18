"""
Change history for the ETL target layers (SCD Type 2).

The ETL truncates and reloads every target table, so on its own it keeps no
history. After a project's layers are loaded, record_history() compares each
target table with the current versions held in "<schema>_history" and writes a
new version only for features that were added, modified or removed. Any layer
can then be rebuilt as it was on any date and compared between two dates.

Run once (gis_create), via setup_schemas.py:
    create_history_objects(conn, schema)   history schema, tables, functions, views, grants

Run after each project's ETL (gis_update needs only SELECT/INSERT/UPDATE):
    record_history(conn, schema, note='what changed')

Objects in "<schema>_history":
    etl_runs                one row per record_history() call (when, who, note)
    layer_runs              per run and layer: baseline/added/modified/removed/unchanged counts
    <layer>                 every version of every feature; valid_from/valid_to bound
                            when it was current; change_type is
                            baseline | added | modified | removed
    <layer>_as_of(ts)       the layer as it was at ts
    <layer>_diff(t0, t1)    net change between two dates, geometry before/after and
                            gained/lost area (polygons), length change (lines) or
                            distance moved (points)
    <layer>_changes         every change event per run, with the same measures
    <layer>_pending()       what promoting "<schema>_draft" would change in "<schema>":
                            same measures, plus attributes before/after (draft_review.py)

A removed feature keeps an open 'removed' row (its last geometry) so the loss can
be mapped; *_as_of() leaves those out.
"""

from sqlalchemy import text

from setup_schemas import (
    CHAMELEON_TABLES, DRAFT_SUFFIX, SCHEMA_TABLE_SCHEMAS, add_missing_columns, ensure_index, id_column,
)


HISTORY_SCHEMA_SUFFIX = '_history'

# Layers loaded into the chameleon target
TRACKED_TABLES = CHAMELEON_TABLES

# Recomputed from geom on every load — they follow a geometry change and are not
# edits in their own right, so they are stored but not compared.
DERIVED_COLUMNS = {'area_ha', 'area_ha_wgs84', 'area_ha_utm29', 'length_km', 'sph', 'perimeter'}

# Geometries are snapped to this grid (degrees, ~1 cm) before comparing, so
# reprojection float noise and vertex reordering are not reported as edits.
GEOM_GRID = 0.0000001

# History is append-only for the ETL role: no DELETE/TRUNCATE.
HISTORY_GRANTS = {
    'gis_viewer': 'SELECT',
    'gis_update': 'SELECT, INSERT, UPDATE',
}


def history_schema(schema):
    return f'{schema}{HISTORY_SCHEMA_SUFFIX}'


def _tracked_tables(schema, tables=None):
    return {
        table: columns
        for table, columns in SCHEMA_TABLE_SCHEMAS.get(schema, {}).items()
        if table in TRACKED_TABLES and (tables is None or table in tables)
    }


def _key_column(schema, table):
    return id_column(schema, table)


def _attr_columns(schema, table, columns):
    key = _key_column(schema, table)
    return [col for col, _ in columns if col not in ('geom', key) and col not in DERIVED_COLUMNS]


def _geom_kind(columns):
    dtype = dict(columns)['geom'].lower()
    if 'polygon' in dtype:
        return 'polygon'
    if 'line' in dtype:
        return 'line'
    return 'point'


def _col_list(columns, alias=None):
    prefix = f'{alias}.' if alias else ''
    return ', '.join(f'{prefix}"{col}"' for col, _ in columns)


def _geom_hash(alias):
    return f'md5(ST_AsBinary(ST_Normalize(ST_SnapToGrid({alias}."geom", {GEOM_GRID}))))'


def _changed_fields(old, new, attr_cols):
    """text[] naming each field that differs between rows old and new ('geom' for geometry)."""
    checks = [f"CASE WHEN {_geom_hash(old)} IS DISTINCT FROM {_geom_hash(new)} THEN 'geom' END"]
    checks += [
        f"CASE WHEN {old}.\"{col}\" IS DISTINCT FROM {new}.\"{col}\" THEN '{col}' END"
        for col in attr_cols
    ]
    return f"array_remove(ARRAY[{', '.join(checks)}]::text[], NULL)"


# ── Measures added to *_diff and *_changes, per geometry kind ──────────────────
# (name, type, expression); stage 2 may reference geom_before/geom_after,
# stage 3 may also reference stage 2 columns.

_MEASURES = {
    'polygon': (
        [
            ('gained_geom', 'geometry',
             'CASE WHEN geom_after IS NULL THEN NULL WHEN geom_before IS NULL THEN geom_after '
             'ELSE ST_Difference(ST_MakeValid(geom_after), ST_MakeValid(geom_before)) END'),
            ('lost_geom', 'geometry',
             'CASE WHEN geom_before IS NULL THEN NULL WHEN geom_after IS NULL THEN geom_before '
             'ELSE ST_Difference(ST_MakeValid(geom_before), ST_MakeValid(geom_after)) END'),
        ],
        [
            ('area_ha_before', 'double precision', 'ST_Area(geom_before::geography) / 10000'),
            ('area_ha_after',  'double precision', 'ST_Area(geom_after::geography) / 10000'),
            ('area_gained_ha', 'double precision', 'COALESCE(ST_Area(gained_geom::geography), 0) / 10000'),
            ('area_lost_ha',   'double precision', 'COALESCE(ST_Area(lost_geom::geography), 0) / 10000'),
            ('area_net_ha',    'double precision',
             '(COALESCE(ST_Area(geom_after::geography), 0) - COALESCE(ST_Area(geom_before::geography), 0)) / 10000'),
        ],
    ),
    'line': (
        [],
        [
            ('length_km_before', 'double precision', 'ST_Length(geom_before::geography) / 1000'),
            ('length_km_after',  'double precision', 'ST_Length(geom_after::geography) / 1000'),
            ('length_km_net',    'double precision',
             '(COALESCE(ST_Length(geom_after::geography), 0) - COALESCE(ST_Length(geom_before::geography), 0)) / 1000'),
        ],
    ),
    'point': (
        [],
        [
            ('moved_m', 'double precision', 'ST_Distance(geom_before::geography, geom_after::geography)'),
        ],
    ),
}


def _with_measures(base_query, kind):
    """Wraps a query exposing geom_before/geom_after with the measure columns for kind."""
    stage2, stage3 = _MEASURES[kind]
    query = base_query
    for stage, alias in ((stage2, 's2'), (stage3, 's3')):
        if stage:
            exprs = ', '.join(f'{expr} AS {name}' for name, _, expr in stage)
            query = f'SELECT {alias}.*, {exprs} FROM ({query}) {alias}'
    return query


# ── Setup (gis_create) ─────────────────────────────────────────────────────────

def create_history_objects(conn, schema):
    """Creates/updates the history schema for one project. Safe to re-run."""
    hs = history_schema(schema)
    layers = _tracked_tables(schema)
    if not layers:
        print(f'  No tracked tables for {schema} — skipping history')
        return

    with conn['sync'].connect() as c:
        # Postgres checks database-level CREATE before IF NOT EXISTS, so only
        # issue it when missing — the schema may have been created by an admin.
        schema_exists = c.execute(
            text('SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :hs)'), {'hs': hs}
        ).scalar()
        if not schema_exists:
            c.exec_driver_sql(f'CREATE SCHEMA "{hs}"')
        c.exec_driver_sql(f'''
            CREATE TABLE IF NOT EXISTS "{hs}".etl_runs (
                run_id  SERIAL PRIMARY KEY,
                run_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                run_by  VARCHAR NOT NULL DEFAULT current_user,
                note    TEXT
            )
        ''')
        # Filled when the run is a promotion of an approved draft (draft_review.promote)
        add_missing_columns(c, hs, 'etl_runs', [
            ('requested_by', 'VARCHAR'), ('approved_by', 'VARCHAR'), ('promoted_by', 'VARCHAR'), ('review_id', 'INTEGER'),
        ])
        c.exec_driver_sql(f'''
            CREATE TABLE IF NOT EXISTS "{hs}".layer_runs (
                run_id          INTEGER NOT NULL REFERENCES "{hs}".etl_runs (run_id),
                layer_name      VARCHAR NOT NULL,
                n_baseline      INTEGER NOT NULL DEFAULT 0,
                n_added         INTEGER NOT NULL DEFAULT 0,
                n_modified      INTEGER NOT NULL DEFAULT 0,
                n_removed       INTEGER NOT NULL DEFAULT 0,
                n_unchanged     INTEGER NOT NULL DEFAULT 0,
                n_skipped_no_id INTEGER NOT NULL DEFAULT 0,
                skipped_reason  TEXT,
                PRIMARY KEY (run_id, layer_name)
            )
        ''')

        for role, privileges in HISTORY_GRANTS.items():
            c.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{hs}" TO {role}')
            for table in ('etl_runs', 'layer_runs'):
                c.exec_driver_sql(f'GRANT {privileges} ON "{hs}"."{table}" TO {role}')
        c.commit()

        # One commit per layer, with its grants, so the locks taken while recreating a
        # layer's view and functions are held briefly (the dashboard reads these too)
        for table, columns in layers.items():
            _create_layer_history(c, schema, hs, table, columns)
            _create_layer_pending(c, schema, hs, table, columns)
            for role, privileges in HISTORY_GRANTS.items():
                c.exec_driver_sql(f'GRANT {privileges} ON "{hs}"."{table}" TO {role}')
                c.exec_driver_sql(f'GRANT SELECT ON "{hs}"."{table}_changes" TO {role}')
                c.exec_driver_sql(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{hs}" TO {role}')
                c.exec_driver_sql(f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA "{hs}" TO {role}')
            c.commit()
    print(f'  History ready: {hs} ({", ".join(layers)})')


def _create_layer_history(c, schema, hs, table, columns):
    full = f'"{hs}"."{table}"'
    key = _key_column(schema, table)
    kind = _geom_kind(columns)
    attr_cols = _attr_columns(schema, table, columns)
    col_defs = ',\n                '.join(f'"{col}" {dtype}' for col, dtype in columns)

    c.exec_driver_sql(f'''
        CREATE TABLE IF NOT EXISTS {full} (
            hist_id         BIGSERIAL PRIMARY KEY,
            etl_run_id      INTEGER NOT NULL REFERENCES "{hs}".etl_runs (run_id),
            change_type     VARCHAR NOT NULL,
            changed_fields  TEXT[],
            valid_from      TIMESTAMPTZ NOT NULL,
            valid_to        TIMESTAMPTZ,
            {col_defs}
        )
    ''')
    add_missing_columns(c, hs, table, columns)

    # One open version (live or 'removed') per feature
    ensure_index(c, hs, f'{table}_open_key',
                 f'CREATE UNIQUE INDEX "{table}_open_key" ON {full} ("{key}") WHERE valid_to IS NULL')
    ensure_index(c, hs, f'{table}_period_idx', f'CREATE INDEX "{table}_period_idx" ON {full} (valid_from, valid_to)')
    ensure_index(c, hs, f'{table}_key_idx', f'CREATE INDEX "{table}_key_idx" ON {full} ("{key}")')
    ensure_index(c, hs, f'{table}_geom_idx', f'CREATE INDEX "{table}_geom_idx" ON {full} USING GIST (geom)')

    # <layer>_as_of(ts)
    c.exec_driver_sql(f'DROP FUNCTION IF EXISTS "{hs}"."{table}_as_of"(timestamptz) CASCADE')
    c.exec_driver_sql(f'''
        CREATE FUNCTION "{hs}"."{table}_as_of"(at_time timestamptz)
        RETURNS SETOF {full} LANGUAGE sql STABLE AS $$
            SELECT h.* FROM {full} h
            WHERE h.valid_from <= at_time
              AND (h.valid_to IS NULL OR h.valid_to > at_time)
              AND h.change_type <> 'removed'
        $$
    ''')

    # <layer>_diff(t0, t1) — net change; a feature edited and then reverted is not reported
    stage2, stage3 = _MEASURES[kind]
    measure_defs = ''.join(f',\n            {name} {dtype}' for name, dtype, _ in stage2 + stage3)
    diff_base = f'''
        SELECT * FROM (
            SELECT
                COALESCE(a."{key}", b."{key}")::varchar AS feature_id,
                CASE WHEN b.hist_id IS NULL THEN 'added'
                     WHEN a.hist_id IS NULL THEN 'removed'
                     ELSE 'modified' END::varchar AS change_type,
                CASE WHEN a.hist_id IS NOT NULL AND b.hist_id IS NOT NULL
                     THEN {_changed_fields('b', 'a', attr_cols)} END AS changed_fields,
                b.hist_id AS hist_id_before,
                a.hist_id AS hist_id_after,
                b.geom::geometry AS geom_before,
                a.geom::geometry AS geom_after
            FROM "{hs}"."{table}_as_of"(from_time) b
            FULL JOIN "{hs}"."{table}_as_of"(to_time) a ON a."{key}" = b."{key}"
            WHERE a.hist_id IS NULL OR b.hist_id IS NULL OR a.hist_id <> b.hist_id
        ) d
        WHERE d.change_type <> 'modified' OR cardinality(d.changed_fields) > 0
    '''
    c.exec_driver_sql(f'DROP FUNCTION IF EXISTS "{hs}"."{table}_diff"(timestamptz, timestamptz)')
    c.exec_driver_sql(f'''
        CREATE FUNCTION "{hs}"."{table}_diff"(from_time timestamptz, to_time timestamptz)
        RETURNS TABLE (
            feature_id varchar,
            change_type varchar,
            changed_fields text[],
            hist_id_before bigint,
            hist_id_after bigint,
            geom_before geometry,
            geom_after geometry{measure_defs}
        ) LANGUAGE sql STABLE AS $$
            {_with_measures(diff_base, kind)}
        $$
    ''')

    # <layer>_changes — every change event, one row per feature per run
    changes_base = f'''
        SELECT
            r.run_id,
            r.run_at AS changed_at,
            r.run_by,
            r.note,
            n.change_type,
            n.changed_fields,
            n."{key}"::varchar AS feature_id,
            p.hist_id AS hist_id_before,
            CASE WHEN n.change_type = 'removed' THEN NULL ELSE n.hist_id END AS hist_id_after,
            p.geom::geometry AS geom_before,
            CASE WHEN n.change_type = 'removed' THEN NULL ELSE n.geom END::geometry AS geom_after
        FROM {full} n
        JOIN "{hs}".etl_runs r ON r.run_id = n.etl_run_id
        LEFT JOIN {full} p
               ON p."{key}" = n."{key}"
              AND p.valid_to = n.valid_from
              AND p.change_type <> 'removed'
        WHERE n.change_type IN ('added', 'modified', 'removed')
    '''
    c.exec_driver_sql(f'DROP VIEW IF EXISTS "{hs}"."{table}_changes"')
    c.exec_driver_sql(f'CREATE VIEW "{hs}"."{table}_changes" AS {_with_measures(changes_base, kind)}')


def _create_layer_pending(c, schema, hs, table, columns):
    """
    <layer>_pending(): every feature that differs between "<schema>_draft" and the
    final "<schema>", i.e. what promoting the draft would change. Only created
    once the draft table exists (the function body is checked against it).
    """
    draft = schema + DRAFT_SUFFIX
    c.exec_driver_sql(f'DROP FUNCTION IF EXISTS "{hs}"."{table}_pending"()')
    exists = c.execute(text(
        'SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = :s AND table_name = :t)'
    ), {'s': draft, 't': table}).scalar()
    if not exists:
        return

    key = _key_column(schema, table)
    kind = _geom_kind(columns)
    attr_cols = _attr_columns(schema, table, columns)
    stage2, stage3 = _MEASURES[kind]
    measure_defs = ''.join(f',\n            {name} {dtype}' for name, dtype, _ in stage2 + stage3)
    strip ="ARRAY['geom', 'id']"
    base = f'''
        SELECT * FROM (
            SELECT
                COALESCE(n."{key}", o."{key}")::varchar AS feature_id,
                -- Presence is decided by the layer's own key (never null on either side, see the
                -- subqueries), not the serial id: some live tables have an id column with no values.
                CASE WHEN o."{key}" IS NULL THEN 'added'
                     WHEN n."{key}" IS NULL THEN 'removed'
                     ELSE 'modified' END::varchar AS change_type,
                CASE WHEN o."{key}" IS NOT NULL AND n."{key}" IS NOT NULL
                     THEN {_changed_fields('o', 'n', attr_cols)} END AS changed_fields,
                CASE WHEN o."{key}" IS NULL THEN NULL ELSE to_jsonb(o) - {strip} END AS attrs_before,
                CASE WHEN n."{key}" IS NULL THEN NULL ELSE to_jsonb(n) - {strip} END AS attrs_after,
                o.geom::geometry AS geom_before,
                n.geom::geometry AS geom_after
            FROM (SELECT * FROM "{schema}"."{table}" WHERE "{key}" IS NOT NULL) o
            FULL JOIN (SELECT * FROM "{draft}"."{table}" WHERE "{key}" IS NOT NULL) n ON n."{key}" = o."{key}"
        ) d
        WHERE d.change_type <> 'modified' OR cardinality(d.changed_fields) > 0
    '''
    c.exec_driver_sql(f'''
        CREATE FUNCTION "{hs}"."{table}_pending"()
        RETURNS TABLE (
            feature_id varchar,
            change_type varchar,
            changed_fields text[],
            attrs_before jsonb,
            attrs_after jsonb,
            geom_before geometry,
            geom_after geometry{measure_defs}
        ) LANGUAGE sql STABLE AS $$
            {_with_measures(base, kind)}
        $$
    ''')


# ── Recording (ETL role) ───────────────────────────────────────────────────────

def record_history(conn, schema, note=None, tables=None):
    """
    Records what changed in schema's target tables since the last call, as one
    run in "<schema>_history". Call right after the project's ETL has loaded.
    The whole run is one transaction: it lands for every layer or for none.
    tables: optional subset of TRACKED_TABLES. Returns the run_id.
    """
    with conn['sync'].begin() as c:
        return record_run(c, schema, note, tables)


def record_run(c, schema, note=None, tables=None, approved_by=None, promoted_by=None, review_id=None,
               requested_by=None):
    """
    record_history() on an open transaction c, so a promotion can update the final
    tables and record their history atomically. Returns the run_id.
    """
    hs = history_schema(schema)
    layers = _tracked_tables(schema, tables)

    run_id, run_at = c.execute(
        text(f'''INSERT INTO "{hs}".etl_runs (note, requested_by, approved_by, promoted_by, review_id)
                 VALUES (:note, :requested_by, :approved_by, :promoted_by, :review_id) RETURNING run_id, run_at'''),
        {'note': note, 'requested_by': requested_by, 'approved_by': approved_by, 'promoted_by': promoted_by,
         'review_id': review_id},
    ).one()
    print(f'Recording history run {run_id} for {schema}')

    for table, columns in layers.items():
        stats = _record_layer(c, schema, hs, table, columns, run_id, run_at)
        c.execute(text(f'''
            INSERT INTO "{hs}".layer_runs
                (run_id, layer_name, n_baseline, n_added, n_modified, n_removed,
                 n_unchanged, n_skipped_no_id, skipped_reason)
            VALUES
                (:run_id, :layer_name, :n_baseline, :n_added, :n_modified, :n_removed,
                 :n_unchanged, :n_skipped_no_id, :skipped_reason)
        '''), {'run_id': run_id, 'layer_name': table, **stats})

        if stats['skipped_reason']:
            print(f'  {table}: skipped — {stats["skipped_reason"]}')
        else:
            print(
                f'  {table}: baseline {stats["n_baseline"]}, added {stats["n_added"]}, '
                f'modified {stats["n_modified"]}, removed {stats["n_removed"]}, '
                f'unchanged {stats["n_unchanged"]}'
                + (f', {stats["n_skipped_no_id"]} rows without an id ignored' if stats['n_skipped_no_id'] else '')
            )

    return run_id


def _record_layer(c, schema, hs, table, columns, run_id, run_at):
    stats = dict(n_baseline=0, n_added=0, n_modified=0, n_removed=0,
                 n_unchanged=0, n_skipped_no_id=0, skipped_reason=None)
    src = f'"{schema}"."{table}"'
    full = f'"{hs}"."{table}"'
    key = _key_column(schema, table)
    attr_cols = _attr_columns(schema, table, columns)
    cols = _col_list(columns)
    params = {'run_id': run_id, 'run_at': run_at}

    exists = c.execute(text(
        'SELECT EXISTS (SELECT 1 FROM information_schema.tables '
        'WHERE table_schema = :schema AND table_name = :table)'
    ), {'schema': schema, 'table': table}).scalar()
    if not exists:
        stats['skipped_reason'] = 'target table does not exist'
        return stats

    c.execute(text('DROP TABLE IF EXISTS _cur, _open, _mod, _gone'))

    # Duplicate ids are blocked by the target's unique index; DISTINCT ON guards
    # tables where that index could not be created.
    c.execute(text(f'''
        CREATE TEMP TABLE _cur ON COMMIT DROP AS
        SELECT DISTINCT ON ("{key}") {cols} FROM {src}
        WHERE "{key}" IS NOT NULL
        ORDER BY "{key}", id
    '''))
    c.execute(text(f'''
        CREATE TEMP TABLE _open ON COMMIT DROP AS
        SELECT hist_id, {cols} FROM {full}
        WHERE valid_to IS NULL AND change_type <> 'removed'
    '''))

    stats['n_skipped_no_id'] = c.execute(text(f'SELECT count(*) FROM {src} WHERE "{key}" IS NULL')).scalar()
    n_cur = c.execute(text('SELECT count(*) FROM _cur')).scalar()
    n_open = c.execute(text('SELECT count(*) FROM _open')).scalar()

    # An empty target means a failed or partial load, not that every feature was deleted
    if n_cur == 0 and n_open > 0:
        stats['skipped_reason'] = f'target table is empty but {n_open} features are current in history'
        c.execute(text('DROP TABLE _cur, _open'))
        return stats

    is_baseline = not c.execute(text(f'SELECT EXISTS (SELECT 1 FROM {full})')).scalar()

    c.execute(text(f'''
        CREATE TEMP TABLE _mod ON COMMIT DROP AS
        SELECT * FROM (
            SELECT o.hist_id, cur."{key}" AS feature_id,
                   {_changed_fields('o', 'cur', attr_cols)} AS changed_fields
            FROM _cur cur
            JOIN _open o ON o."{key}" = cur."{key}"
        ) m
        WHERE cardinality(m.changed_fields) > 0
    '''))
    c.execute(text(f'''
        CREATE TEMP TABLE _gone ON COMMIT DROP AS
        SELECT o.hist_id FROM _open o
        WHERE NOT EXISTS (SELECT 1 FROM _cur cur WHERE cur."{key}" = o."{key}")
    '''))

    # Close superseded versions first — at most one open row per feature is allowed
    c.execute(text(f'''
        UPDATE {full} SET valid_to = :run_at
        WHERE hist_id IN (SELECT hist_id FROM _mod UNION ALL SELECT hist_id FROM _gone)
    '''), params)
    # Features removed earlier and now back: close their 'removed' row
    c.execute(text(f'''
        UPDATE {full} SET valid_to = :run_at
        WHERE valid_to IS NULL AND change_type = 'removed'
          AND "{key}" IN (SELECT "{key}" FROM _cur)
    '''), params)

    stats['n_modified'] = c.execute(text(f'''
        INSERT INTO {full} (etl_run_id, change_type, changed_fields, valid_from, {cols})
        SELECT :run_id, 'modified', m.changed_fields, :run_at, {_col_list(columns, 'cur')}
        FROM _cur cur JOIN _mod m ON m.feature_id = cur."{key}"
    '''), params).rowcount

    n_new = c.execute(text(f'''
        INSERT INTO {full} (etl_run_id, change_type, valid_from, {cols})
        SELECT :run_id, :change_type, :run_at, {_col_list(columns, 'cur')}
        FROM _cur cur
        WHERE NOT EXISTS (SELECT 1 FROM _open o WHERE o."{key}" = cur."{key}")
    '''), {**params, 'change_type': 'baseline' if is_baseline else 'added'}).rowcount
    stats['n_baseline' if is_baseline else 'n_added'] = n_new

    # Keep the last geometry and attributes of removed features so the loss can be mapped
    stats['n_removed'] = c.execute(text(f'''
        INSERT INTO {full} (etl_run_id, change_type, valid_from, {cols})
        SELECT :run_id, 'removed', :run_at, {_col_list(columns, 'h')}
        FROM {full} h JOIN _gone g ON g.hist_id = h.hist_id
    '''), params).rowcount

    stats['n_unchanged'] = n_cur - n_new - stats['n_modified']
    c.execute(text('DROP TABLE _cur, _open, _mod, _gone'))
    return stats
