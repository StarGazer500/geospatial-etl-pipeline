"""
One step at a time: push → submit → promote. Each command does exactly one step,
so nothing runs by accident (unlike "Run All" in the notebook).

From etl_pipeline/src, with the ETL environment:

    ..\\etl_env\\Scripts\\python.exe layers.py status
    ..\\etl_env\\Scripts\\python.exe layers.py push buffalo
    ..\\etl_env\\Scripts\\python.exe layers.py submit buffalo --requested-by "Name" --note "Kanneh parcels 123, 129, 130 added"
    ..\\etl_env\\Scripts\\python.exe layers.py promote buffalo --approved-by "Approver 1" "Approver 2"
    ..\\etl_env\\Scripts\\python.exe layers.py withdraw buffalo --reason "Approver asked to fix C4"

Several projects at once: `push buffalo colobus`. Projects: akwaaba, buffalo, colobus.
Your name (for --by) defaults to OPERATOR_NAME in .env.
submit and promote show what they are about to do and ask you to type the
project name(s) to confirm. See RUNBOOK.md for what each step does.
"""

import argparse
import os
import sys
import traceback
import warnings
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
warnings.filterwarnings('ignore', 'GeoSeries.notna', UserWarning)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from sqlalchemy import text  # noqa: E402

from connection_util import DatabaseConnection  # noqa: E402
from draft_review import draft_schema, review_status  # noqa: E402

PROJECTS = {'akwaaba': 'akwaaba_schema', 'buffalo': 'buffalo_schema', 'colobus': 'colobus_schema'}


# ── Connections (same settings as the notebook) ────────────────────────────────

def _target(prefix):
    conn = DatabaseConnection.connect_to_target_postgis_database(
        os.getenv(f'{prefix}_HOST'), os.getenv(f'{prefix}_DATABASE_NAME'), os.getenv(f'{prefix}_PORT'),
        os.getenv('GIS_UPDATE_USERNAME'), os.getenv('GIS_UPDATE_PASSWORD'),
    )
    if conn is None:
        sys.exit(f'Could not connect to the {prefix.lower()} database — check .env and the network/proxy.')
    return conn


def _source():
    conn = DatabaseConnection.connect_to_source_postgis_database(
        os.getenv('SOURCE_HOST'), os.getenv('SOURCE_DATABASE_NAME'), os.getenv('SOURCE_PORT'),
        os.getenv('SOURCE_USERNAME'), os.getenv('SOURCE_PASSWORD'),
    )
    if conn is None:
        sys.exit('Could not connect to the local (source) database — check .env.')
    return conn


# ── Helpers ────────────────────────────────────────────────────────────────────

def _confirm(projects, action):
    """Asks the user to type the project name(s); exits if they don't match."""
    expected = ' '.join(projects)
    print(f'\nTo {action}, type: {expected}')
    try:
        answer = input('> ').strip()
    except (EOFError, KeyboardInterrupt):
        answer = ''
    if answer != expected:
        sys.exit('Not confirmed — nothing was done.')


def _operator(args):
    name = (args.by or os.getenv('OPERATOR_NAME') or '').strip()
    if not name:
        sys.exit('Your name is needed: pass --by "Your Name" or set OPERATOR_NAME in .env.')
    return name


def _review_layers(conn, schema, review_id):
    with conn['sync'].connect() as c:
        return c.execute(text(f'''
            SELECT layer_name, n_added, n_modified, n_removed, net_change, net_unit
            FROM "{draft_schema(schema)}".review_layers
            WHERE review_id = :rid AND n_added + n_modified + n_removed > 0
            ORDER BY layer_name
        '''), {'rid': review_id}).fetchall()


def _print_review(conn, project, schema, review):
    print(f'\n{project}: review {review["review_id"]}, submitted by {review["submitted_by"]} '
          f'on {review["submitted_at"]:%d %b %Y %H:%M} UTC')
    if review.get('requested_by'):
        print(f'  Requested by: {review["requested_by"]}')
    if review['note']:
        print(f'  Note: {review["note"]}')
    print(f'  Fingerprint: {review["fingerprint"][:12]}')
    for layer, a, m, r, net, unit in _review_layers(conn, schema, review['review_id']):
        net_text = f', net {net:+,.2f} {unit}' if net is not None else ''
        print(f'  {layer}: added {a}, modified {m}, removed {r}{net_text}')


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_status(args):
    chameleon = _target('CHAMELEON_TARGET')
    for project, schema in PROJECTS.items():
        try:
            review = review_status(chameleon, schema)
        except Exception:
            print(f'{project}: no draft schema yet (RUNBOOK.md, step 1)')
            continue
        if review:
            _print_review(chameleon, project, schema, review)
            print('  Status: LOCKED, awaiting approval → promote or withdraw')
        else:
            print(f'{project}: draft open (not under review) → push / submit')


def cmd_push(args):
    from etl_pipeline_chameleon import run_chameleon_etl_pipeline
    source, chameleon = _source(), _target('CHAMELEON_TARGET')
    # Fail fast with one clear message (the database lock would also stop it, but
    # only after every loader has run and printed its own error)
    locked = [p for p in args.projects if review_status(chameleon, PROJECTS[p])]
    if locked:
        sys.exit(f'Draft under review for: {", ".join(locked)}. Nothing was pushed. '
                 'Promote the review or withdraw it first (layers.py status).')
    failed = []
    for project in args.projects:
        schema = PROJECTS[project]
        print(f'\n=== push {project}: local {schema} → {draft_schema(schema)} ===')
        try:
            run_chameleon_etl_pipeline(schema, draft_schema(schema), source, chameleon)
            print(f'{project}: pushed. Check it in the dashboard (View: Pending approval).')
        except Exception as e:
            failed.append(project)
            print(f'{project}: push FAILED — {e}')
            traceback.print_exc()
    if failed:
        sys.exit(f'\nPush failed for: {", ".join(failed)}')


def cmd_submit(args):
    from draft_review import submit_for_review
    by = _operator(args)
    chameleon = _target('CHAMELEON_TARGET')
    requested_by = args.requested_by.strip()
    if not requested_by:
        sys.exit('--requested-by is required: the person who asked for this update.')
    print(f'Submitting {", ".join(args.projects)} for review, by {by}, requested by {requested_by}.')
    print(f'Note: {args.note}')
    print('The draft(s) will be LOCKED until promoted or withdrawn.')
    _confirm(args.projects, 'submit')
    failed = []
    for project in args.projects:
        print(f'\n=== submit {project} ===')
        try:
            submit_for_review(chameleon, PROJECTS[project], submitted_by=by, requested_by=requested_by, note=args.note)
        except Exception as e:
            failed.append(project)
            print(f'{project}: NOT submitted — {e}')
    if failed:
        sys.exit(f'\nNot submitted: {", ".join(failed)}')


def cmd_promote(args):
    from draft_review import promote
    from version import create_version
    by = _operator(args)
    # One or more approvers: --approved-by "Simon" "Jenni"
    approvers = [a.strip() for a in args.approved_by if a.strip()]
    if not approvers:
        sys.exit('--approved-by is required: the name(s) of the person/people who approved the changes.')
    approved_by = ', '.join(dict.fromkeys(approvers))

    chameleon, project_level = _target('CHAMELEON_TARGET'), _target('PROJECT_LEVEL_TARGET')
    print(f'About to make these drafts LIVE (approved by {approved_by}, promoted by {by}):')
    missing = []
    for project in args.projects:
        review = review_status(chameleon, PROJECTS[project])
        if review:
            _print_review(chameleon, project, PROJECTS[project], review)
        else:
            missing.append(project)
    if missing:
        sys.exit(f'\nNo open review for: {", ".join(missing)}. Submit first (layers.py submit ...).')
    _confirm(args.projects, 'promote these changes to the live layers')

    promoted, failed = [], []
    for project in args.projects:
        print(f'\n=== promote {project} ===')
        try:
            promote(chameleon, project_level, PROJECTS[project],
                    approved_by=approved_by, promoted_by=by, note=args.note)
            promoted.append(project)
        except Exception as e:
            failed.append(project)
            print(f'{project}: NOT promoted — {e}')
            traceback.print_exc()

    if promoted:
        print('\n=== backup ===')
        create_version(f'Promoted {", ".join(promoted)} (approved by {approved_by}, by {by}): {args.note or ""}')
    if failed:
        sys.exit(f'\nNot promoted: {", ".join(failed)}')


def cmd_withdraw(args):
    from draft_review import withdraw_review
    chameleon = _target('CHAMELEON_TARGET')
    for project in args.projects:
        review = review_status(chameleon, PROJECTS[project])
        if review:
            _print_review(chameleon, project, PROJECTS[project], review)
    _confirm(args.projects, 'withdraw (unlock without promoting)')
    for project in args.projects:
        withdraw_review(chameleon, PROJECTS[project], reason=args.reason)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='layers.py', description='Push → submit → promote, one step at a time. See RUNBOOK.md.')
    sub = parser.add_subparsers(dest='command', required=True)

    def projects_arg(p):
        p.add_argument('projects', nargs='+', choices=list(PROJECTS), help='one or more projects')

    sub.add_parser('status', help='which drafts are under review')

    p = sub.add_parser('push', help='STEP 1: load the local layers into the draft')
    projects_arg(p)

    p = sub.add_parser('submit', help='STEP 2: lock the draft for review')
    projects_arg(p)
    p.add_argument('--requested-by', required=True, help='who asked for this update')
    p.add_argument('--note', required=True, help='what changed, shown on the approval PDF')
    p.add_argument('--by', help='your name (default: OPERATOR_NAME in .env)')

    p = sub.add_parser('promote', help='STEP 3: make the approved draft live')
    projects_arg(p)
    p.add_argument('--approved-by', required=True, nargs='+', metavar='NAME',
                   help='who approved the changes; several approvers: --approved-by "Simon" "Jenni"')
    p.add_argument('--by', help='your name (default: OPERATOR_NAME in .env)')
    p.add_argument('--note', help='history note (default: the note given at submit)')

    p = sub.add_parser('withdraw', help='unlock a draft without promoting it')
    projects_arg(p)
    p.add_argument('--reason', required=True, help='why, e.g. what the approver asked to change')

    # Commands copied from chats/documents can carry invisible characters (non-breaking or
    # zero-width spaces) that arrive as extra blank arguments: drop them, and trim the rest
    invisible = ' ​‌‍⁠﻿'
    argv = [a.strip().strip(invisible).strip() for a in sys.argv[1:]]
    args = parser.parse_args([a for a in argv if a])
    # Keep the order given, without duplicates
    if hasattr(args, 'projects'):
        args.projects = list(dict.fromkeys(args.projects))
    {'status': cmd_status, 'push': cmd_push, 'submit': cmd_submit,
     'promote': cmd_promote, 'withdraw': cmd_withdraw}[args.command](args)


if __name__ == '__main__':
    main()
