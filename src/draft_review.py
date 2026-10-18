"""
Draft → review → approval → promotion of a project's layers.

The ETL loads each project into "<schema>_draft" (same tables as the final
"<schema>"). Nothing reaches the final schema until the draft is reviewed and
promoted:

    submit_for_review(conn, 'buffalo_schema', submitted_by='Martin', requested_by='…', note='…')
        Locks the draft (a trigger rejects any change to it while under review),
        fingerprints its contents and records what promotion would change.
        The approval PDF is then built in the dashboard (Pending approval).

    promote(chameleon_conn, project_conn, 'buffalo_schema', approved_by='…', promoted_by='Martin', note='…')
        Checks the draft still matches the fingerprint, then in ONE transaction
        replaces every final layer with the draft's rows, records the change
        history (with who approved it) and closes the review. Then copies the
        approved layers to the project-level database and refreshes the Buffalo
        leased-areas tracker.

    withdraw_review(conn, 'buffalo_schema', reason='…')
        Unlocks the draft without promoting, e.g. to fix something and push again.

Run once (gis_create), via setup_schemas.py:
    create_review_objects(conn, schema)   review tables, lock trigger, grants on "<schema>_draft"
"""

import geopandas as gpd
from sqlalchemy import text

from change_history import history_schema, record_run
from data_management_util import DataManagement
from setup_schemas import (
    CHAMELEON_TABLES, DRAFT_SUFFIX, PROJECT_LEVEL_TABLES, SCHEMA_TABLE_SCHEMAS, add_missing_columns, ensure_index, id_column,
)

DRAFT_GRANTS = {
    'gis_viewer': 'SELECT',
    'gis_update': 'SELECT, INSERT, UPDATE',
}
CHANGE_TYPES = ('added', 'modified', 'removed')
NET_MEASURE = {'polygon': ('area_net_ha', 'ha'), 'line': ('length_km_net', 'km')}


def draft_schema(schema):
    return f'{schema}{DRAFT_SUFFIX}'


def schema_exists(conn, schema):
    with conn['sync'].connect() as c:
        return c.execute(text('SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :s)'), {'s': schema}).scalar()


def _layers(schema):
    """{table: columns} promoted for schema: its chameleon layers."""
    return {t: cols for t, cols in SCHEMA_TABLE_SCHEMAS[schema].items() if t in CHAMELEON_TABLES}


def _kind(columns):
    dtype = dict(columns)['geom'].lower()
    return 'polygon' if 'polygon' in dtype else 'line' if 'line' in dtype else 'point'


# ── Setup (gis_create) ─────────────────────────────────────────────────────────

def create_review_objects(conn, schema):
    """Review log, the review lock on every draft layer, and grants. Safe to re-run."""
    ds = draft_schema(schema)
    with conn['sync'].connect() as c:
        c.exec_driver_sql(f'''
            CREATE TABLE IF NOT EXISTS "{ds}".reviews (
                review_id       SERIAL PRIMARY KEY,
                status          VARCHAR NOT NULL DEFAULT 'in_review',   -- in_review | approved | withdrawn
                submitted_by    VARCHAR NOT NULL,
                submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
                note            TEXT,
                fingerprint     VARCHAR NOT NULL,
                decided_at      TIMESTAMPTZ,
                approved_by     VARCHAR,
                promoted_by     VARCHAR,
                history_run_id  INTEGER,
                withdraw_reason TEXT
            )
        ''')
        # Who asked for the update (added after the table was first created)
        add_missing_columns(c, ds, 'reviews', [('requested_by', 'VARCHAR')])
        # At most one review open at a time
        ensure_index(c, ds, 'reviews_one_open',
                     f'CREATE UNIQUE INDEX reviews_one_open ON "{ds}".reviews (status) WHERE status = \'in_review\'')
        c.exec_driver_sql(f'''
            CREATE TABLE IF NOT EXISTS "{ds}".review_layers (
                review_id   INTEGER NOT NULL REFERENCES "{ds}".reviews (review_id),
                layer_name  VARCHAR NOT NULL,
                n_added     INTEGER NOT NULL,
                n_modified  INTEGER NOT NULL,
                n_removed   INTEGER NOT NULL,
                n_unchanged INTEGER NOT NULL,
                net_change  DOUBLE PRECISION,
                net_unit    VARCHAR,
                fingerprint VARCHAR NOT NULL,
                PRIMARY KEY (review_id, layer_name)
            )
        ''')

        # The lock: any write to a draft layer fails while a review is open. Enforced
        # by the database, so it holds for the ETL, QGIS and plain SQL alike; only the
        # table owner (gis_create) could disable it.
        c.exec_driver_sql(f'''
            CREATE OR REPLACE FUNCTION "{ds}".review_lock() RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE r RECORD;
            BEGIN
                SELECT review_id, submitted_by, submitted_at INTO r
                FROM "{ds}".reviews WHERE status = 'in_review';
                IF FOUND THEN
                    -- message built by concatenation: percent placeholders would be read by the driver
                    RAISE EXCEPTION USING MESSAGE =
                        '{ds} is locked: review ' || r.review_id || ' (submitted by ' || r.submitted_by
                        || ' on ' || to_char(r.submitted_at, 'DD Mon YYYY HH24:MI')
                        || ') is awaiting approval. Promote it, or withdraw the review to change the draft.';
                END IF;
                RETURN NULL;
            END $$
        ''')
        for table in _layers(schema):
            exists = c.execute(text(
                'SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = :s AND table_name = :t)'
            ), {'s': ds, 't': table}).scalar()
            if not exists:
                continue
            c.exec_driver_sql(f'DROP TRIGGER IF EXISTS review_lock ON "{ds}"."{table}"')
            c.exec_driver_sql(f'''
                CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON "{ds}"."{table}"
                FOR EACH STATEMENT EXECUTE FUNCTION "{ds}".review_lock()
            ''')

        for role, privileges in DRAFT_GRANTS.items():
            c.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{ds}" TO {role}')
            c.exec_driver_sql(f'GRANT {privileges} ON "{ds}".reviews, "{ds}".review_layers TO {role}')
            c.exec_driver_sql(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "{ds}" TO {role}')
        c.commit()
    print(f'  Review lock ready on {ds}')


# ── Fingerprint ────────────────────────────────────────────────────────────────

def _layer_fingerprint(c, ds, table, columns):
    """
    md5 of the layer's content (every column except the serial id, rows in a fixed
    order). Identical data gives the same fingerprint however often it is re-pushed.
    """
    cols = ', '.join(
        f'ST_AsBinary("{col}")' if col == 'geom' else f'"{col}"' for col, _ in columns
    )
    return c.execute(text(f'''
        SELECT md5(COALESCE(string_agg(h, '' ORDER BY h), ''))
        FROM (SELECT md5(ROW({cols})::text) AS h FROM "{ds}"."{table}") t
    ''')).scalar()


def _fingerprint(layer_prints):
    import hashlib
    joined = ';'.join(f'{t}:{p}' for t, p in sorted(layer_prints.items()))
    return hashlib.md5(joined.encode()).hexdigest()


# ── Review ─────────────────────────────────────────────────────────────────────

def _open_review(c, ds, lock=False):
    return c.execute(text(
        f'SELECT * FROM "{ds}".reviews WHERE status = \'in_review\'' + (' FOR UPDATE' if lock else '')
    )).mappings().first()


def review_status(conn, schema):
    """The open review of schema's draft (dict), or None."""
    with conn['sync'].connect() as c:
        review = _open_review(c, draft_schema(schema))
        return dict(review) if review else None


def submit_for_review(conn, schema, submitted_by, requested_by, note=None):
    """
    Locks "<schema>_draft" for review and records what promoting it would change.
    Refuses (and leaves the draft unlocked) when a draft layer is empty while its
    final layer is not, or has features without an id — promoting either would
    lose or corrupt data. requested_by: who asked for the update. Returns the
    review_id, or None if there is nothing to promote.
    """
    if not (requested_by or '').strip():
        raise ValueError('requested_by is required: the person who asked for this update.')
    ds, hs = draft_schema(schema), history_schema(schema)
    with conn['sync'].begin() as c:
        existing = _open_review(c, ds)
        if existing:
            raise RuntimeError(
                f'{ds} is already under review (review {existing["review_id"]}, submitted by '
                f'{existing["submitted_by"]}). Promote it or withdraw it first.'
            )

        problems, stats, prints = [], {}, {}
        for table, columns in _layers(schema).items():
            key = id_column(schema, table)
            n_draft, n_no_id = c.execute(text(
                f'SELECT count(*), count(*) FILTER (WHERE "{key}" IS NULL) FROM "{ds}"."{table}"'
            )).one()
            n_final = c.execute(text(f'SELECT count(*) FROM "{schema}"."{table}"')).scalar()
            if n_draft == 0 and n_final > 0:
                problems.append(f'{table}: the draft is empty but the final layer has {n_final} features '
                                f'(did the push for this layer fail?)')
            if n_no_id:
                problems.append(f'{table}: {n_no_id} draft feature(s) have no {key} — fix them locally and push again')

            kind = _kind(columns)
            net_col, unit = NET_MEASURE.get(kind, (None, None))
            sums = f', sum({net_col})' if net_col else ', NULL'
            rows = c.execute(text(
                f'SELECT change_type, count(*){sums} FROM "{hs}"."{table}_pending"() GROUP BY change_type'
            )).fetchall()
            counts = {ct: 0 for ct in CHANGE_TYPES}
            net = 0.0
            for ct, n, s in rows:
                counts[ct] = n
                net += s or 0
            changed = sum(counts.values())
            stats[table] = dict(
                n_added=counts['added'], n_modified=counts['modified'], n_removed=counts['removed'],
                n_unchanged=n_draft - n_no_id - counts['added'] - counts['modified'],
                net_change=net if net_col else None, net_unit=unit,
            )
            prints[table] = _layer_fingerprint(c, ds, table, columns)

        if problems:
            raise RuntimeError(f'{ds} cannot be submitted for review:\n  ' + '\n  '.join(problems))

        total = sum(s['n_added'] + s['n_modified'] + s['n_removed'] for s in stats.values())
        if total == 0:
            print(f'{ds} matches {schema}: nothing to review. The draft is not locked.')
            return None

        fingerprint = _fingerprint(prints)
        review_id = c.execute(text(f'''
            INSERT INTO "{ds}".reviews (submitted_by, requested_by, note, fingerprint)
            VALUES (:by, :requested_by, :note, :fp) RETURNING review_id
        '''), {'by': submitted_by, 'requested_by': requested_by, 'note': note, 'fp': fingerprint}).scalar()
        for table, s in stats.items():
            c.execute(text(f'''
                INSERT INTO "{ds}".review_layers
                    (review_id, layer_name, n_added, n_modified, n_removed, n_unchanged, net_change, net_unit, fingerprint)
                VALUES (:rid, :layer, :n_added, :n_modified, :n_removed, :n_unchanged, :net_change, :net_unit, :fp)
            '''), {'rid': review_id, 'layer': table, 'fp': prints[table], **s})

    print(f'Review {review_id} opened for {ds} by {submitted_by} (requested by {requested_by}) — the draft is now locked.')
    print(f'  Fingerprint {fingerprint[:12]}')
    for table, s in stats.items():
        if s['n_added'] + s['n_modified'] + s['n_removed']:
            net = f', net {s["net_change"]:+,.2f} {s["net_unit"]}' if s['net_change'] is not None else ''
            print(f'  {table}: added {s["n_added"]}, modified {s["n_modified"]}, removed {s["n_removed"]}{net}')
    print('Next: dashboard > Pending approval > build the approval PDF and send it for approval.')
    return review_id


def withdraw_review(conn, schema, reason=None):
    """Closes the open review without promoting; the draft can be changed again."""
    ds = draft_schema(schema)
    with conn['sync'].begin() as c:
        review = _open_review(c, ds, lock=True)
        if not review:
            print(f'{ds} has no open review.')
            return None
        c.execute(text(f'''
            UPDATE "{ds}".reviews SET status = 'withdrawn', decided_at = now(), withdraw_reason = :reason
            WHERE review_id = :rid
        '''), {'reason': reason, 'rid': review['review_id']})
    print(f'Review {review["review_id"]} withdrawn — {ds} is unlocked.')
    return review['review_id']


# ── Promotion ──────────────────────────────────────────────────────────────────

def promote(chameleon_conn, project_conn, schema, approved_by, promoted_by, note=None):
    """
    Moves the approved draft to the final schema. approved_by: who gave the
    approval, one name or a list of names; promoted_by: who is running this.
    Returns the history run_id.
    """
    if isinstance(approved_by, (list, tuple)):
        approved_by = ', '.join(dict.fromkeys(a.strip() for a in approved_by if a and a.strip()))
    if not (approved_by or '').strip():
        raise ValueError('approved_by is required: the name of the person who approved the changes.')
    if not (promoted_by or '').strip():
        raise ValueError('promoted_by is required: your name.')

    ds = draft_schema(schema)
    layers = _layers(schema)

    with chameleon_conn['sync'].begin() as c:
        review = _open_review(c, ds, lock=True)
        if not review:
            raise RuntimeError(f'{ds} has no open review. Run submit_for_review first and get it approved.')

        prints = {table: _layer_fingerprint(c, ds, table, columns) for table, columns in layers.items()}
        if _fingerprint(prints) != review['fingerprint']:
            raise RuntimeError(
                f'{ds} no longer matches review {review["review_id"]} (fingerprint changed) — nothing was promoted. '
                'Withdraw the review, then push and submit again.'
            )

        print(f'Promoting {ds} to {schema} (review {review["review_id"]}, approved by {approved_by})')
        # DELETE rather than TRUNCATE: readers keep seeing the old layers until COMMIT
        for table, columns in layers.items():
            cols = ', '.join(f'"{col}"' for col, _ in columns)
            c.execute(text(f'DELETE FROM "{schema}"."{table}"'))
            n = c.execute(text(f'INSERT INTO "{schema}"."{table}" ({cols}) SELECT {cols} FROM "{ds}"."{table}"')).rowcount
            print(f'  {table}: {n} features')

        run_note = note or review['note']
        run_id = record_run(c, schema, note=run_note, approved_by=approved_by, promoted_by=promoted_by,
                            review_id=review['review_id'], requested_by=review.get('requested_by'))
        c.execute(text(f'''
            UPDATE "{ds}".reviews
            SET status = 'approved', decided_at = now(), approved_by = :approved_by,
                promoted_by = :promoted_by, history_run_id = :run_id
            WHERE review_id = :rid
        '''), {'approved_by': approved_by, 'promoted_by': promoted_by, 'run_id': run_id, 'rid': review['review_id']})
    print(f'{schema} updated and recorded as history run {run_id}. {ds} is unlocked.')

    copy_to_project_level(chameleon_conn, project_conn, schema)

    if schema == 'buffalo_schema':
        from update_leased_areas_tracker import update_leased_areas_tracker
        update_leased_areas_tracker()
    return run_id


def copy_to_project_level(chameleon_conn, project_conn, schema):
    """
    Copies the final (approved) layers of schema from the chameleon target to the
    project-level database. Called by promote(); can be rerun on its own if it failed.
    """
    for table, columns in SCHEMA_TABLE_SCHEMAS[schema].items():
        if table not in PROJECT_LEVEL_TABLES:
            continue
        cols = ', '.join(f'"{col}"' for col, _ in columns)
        with chameleon_conn['sync'].connect() as c:
            data = gpd.read_postgis(text(f'SELECT {cols} FROM "{schema}"."{table}"'), c, geom_col='geom')
        if data.empty:
            print(f'  project level {table}: final layer is empty — skipped')
            continue
        DataManagement.save_spatial_data_to_postgres(conn=project_conn, data=data, table_name=table, schema=schema)
    print(f'Project-level {schema} updated from the approved layers.')
