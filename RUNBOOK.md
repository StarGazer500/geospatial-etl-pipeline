# Runbook: updating the live GIS layers

How layer changes get from the local database to the live (final) schemas, with
a review and approval step in between. Everything is versioned: every change that
reaches the live layers is recorded in `<schema>_history` together with who approved it.

```
local DB ──push──▶ <schema>_draft ──submit──▶ (locked, approval PDF) ──promote──▶ <schema> ──▶ history
```

| Schema                                 | What it is                                                  | Who writes to it                                 |
| -------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------ |
| `<schema>` (e.g. `buffalo_schema`) | The live layers everyone uses                               | Only`promote()`, after approval                |
| `<schema>_draft`                     | The proposed next version                                   | The ETL push (step 1); locked while under review |
| `<schema>_history`                   | Every version of every feature, plus the run and review log | Only`promote()`                                |

Projects: `akwaaba_schema`, `buffalo_schema`, `colobus_schema`. Tracked layers:
leased areas, compartments, subcompartments, lease area stratum, roads, firebreaks,
culverts (each project has the ones it uses).

---

## 1. One-time setup

### 1.1 An admin creates the draft schemas

Run on the **chameleon target database** (`CLEANED_POSTGIS_CLOUD_DATABASE`) as an
admin account (e.g. `rb_admin`), not as `gis_create`:

```sql
GRANT gis_create TO CURRENT_USER;

CREATE SCHEMA akwaaba_schema_draft AUTHORIZATION gis_create;
CREATE SCHEMA buffalo_schema_draft AUTHORIZATION gis_create;
CREATE SCHEMA colobus_schema_draft AUTHORIZATION gis_create;

REVOKE gis_create FROM CURRENT_USER;
```

They must be owned by `gis_create`: the setup script creates their tables, the
review lock and the grants.

### 1.2 Run the schema setup

From `etl_pipeline/src`, with the `GIS_CREATE_*` login in `.env`:

```
..\etl_env\Scripts\python.exe setup_schemas.py
```

It creates the draft tables (same columns as the live ones), the review lock on
every draft layer, the pending-changes functions and the new history columns.
It is safe to re-run, e.g. after adding a column. A draft schema that does not
exist yet is skipped with a message.

To re-run only what you need, name the project(s) and/or the part(s):

```
..\etl_env\Scripts\python.exe setup_schemas.py akwaaba                   # one project, everything
..\etl_env\Scripts\python.exe setup_schemas.py akwaaba --only history    # one project, history + comparison functions
..\etl_env\Scripts\python.exe setup_schemas.py --only draft history      # all projects, two parts
```

Parts: `live` (live tables on both databases, the slowest), `draft` (draft tables and
review lock), `history` (history tables and the comparison functions behind Pending
approval).

### 1.3 Add your name to `.env`

Used as *submitted by* / *promoted by*:

```
OPERATOR_NAME=Martin Aborgeh
```

---

## How to run the steps

Every step is a separate command, run from `etl_pipeline/src`, so nothing can run by
accident. The notebook no longer runs these steps, so "Run All" is safe.

```
cd C:\Users\LENOVO\Desktop\etl_pipeline\src
..\etl_env\Scripts\python.exe layers.py status
```

| Command                                          | Step                           |
| ------------------------------------------------ | ------------------------------ |
| `layers.py status`                             | Which drafts are under review  |
| `layers.py push buffalo`                       | 1 · local → draft            |
| `layers.py submit buffalo --requested-by "…" --note "…"` | 2 · lock the draft for review |
| `layers.py promote buffalo --approved-by "…" "…"` | 4 · approved draft → live (one or more approvers) |
| `layers.py withdraw buffalo --reason "…"`     | unlock without promoting       |

Several projects at once: `push buffalo colobus`. `submit`, `promote` and `withdraw`
show what they are about to do and ask you to **type the project name(s)** to confirm.
Anything else cancels. `--by "Name"` overrides `OPERATOR_NAME`.

---

## 2. Every update

All edits are made in the **local database**. Changes from colleagues come in as a
GeoPackage and are applied locally first. Nobody edits the remote layers directly.

### Step 1 · Push to the draft

```
..\etl_env\Scripts\python.exe layers.py push buffalo
```

Loads your local layers into `<schema>_draft`. Nothing live changes. Push as many
times as you need. If the draft is under review, the push stops straight away and
nothing is pushed.

**Check it:** dashboard → **View: Pending approval**. You see exactly what promoting
the draft would change: map (added / gained in blue, removed / lost in red, modified
outlines in yellow), counts and area per layer, and a before/after table per feature.
If something is wrong, fix it locally and push again.

### Step 2 · Submit for review

```
..\etl_env\Scripts\python.exe layers.py submit buffalo --requested-by "Name of who asked for it" --note "Kanneh parcels 123, 129 and 130 added"
```

`--requested-by` is required: the person who asked for this update. It and the note are
shown on the approval PDF and saved with the history. Type `buffalo` when asked.

This **locks the draft**: the database rejects any change to it (ETL, QGIS or SQL)
until the review is promoted or withdrawn. It also records a fingerprint of the
draft's contents.

Submission is refused, and the draft stays unlocked, if:

- a draft layer is empty while its live layer is not (a failed push), or
- a draft feature has no id (`compartment_id`, `parcel_id` for Buffalo leased areas, …).

If there are no differences from the live layers, nothing is locked.

### Step 3 · Approval PDF

Dashboard → **View: Pending approval** → sidebar **Approval PDF** → *Build report* →
*Download PDF*. Send it to the approver.

The PDF shows the review number and fingerprint on every page, who requested the
update, a summary by layer with each layer's total before and after approval, a map and
feature list per changed layer, and a sign-off table with one row per approver (name,
role, signature, date). Set the number of rows in *Approver sign-off lines* (default 3).
A PDF built before
submitting is marked **NOT SUBMITTED FOR REVIEW**. Don't use that one for approval.

### Step 4 · Promote after approval

```
..\etl_env\Scripts\python.exe layers.py promote buffalo --approved-by "Approver 1" "Approver 2"
```

Name every approver who signed: one or more names. They are stored together, e.g.
`Approver 1, Approver 2`.

It first shows the review (number, who submitted it, note, fingerprint, changes per
layer) and asks you to type `buffalo`. `--note "…"` replaces the submit note in the history.

In order:

1. Checks the draft still matches the reviewed fingerprint. If not, nothing is promoted.
2. In **one transaction**: replaces every live layer of the project with the draft,
   records history (with requester, approvers, promoter and review number) and closes the review.
   Anyone viewing the live layers sees the old version until the commit, then the new
   one. If anything fails, nothing changes and the review stays open.
3. Copies the approved layers to the project-level database.
4. Buffalo only: refreshes `buffalo_schema.leased_areas_tracker`.
5. Writes the GeoParquet backup (`create_version`).

**Check it:** dashboard → **View: Change history** → *Latest run*. The Run log tab
shows the run with *Requested by*, *Approved by* and *Promoted by*. Pending approval is now empty for
that project.

---

## 3. If the approver asks for changes

```
..\etl_env\Scripts\python.exe layers.py withdraw buffalo --reason "Approver asked to fix the C4 boundary"
```

This unlocks the draft. Fix locally, then push (step 1), submit (step 2) and send the
new PDF. The withdrawn review stays in the review log.

`layers.py status` shows which projects are under review.

---

## 4. Messages you may see

| Message                                                       | Meaning                                                  | What to do                                                                                                                                |
| ------------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `Draft under review for: …. Nothing was pushed.`           | You pushed a draft under review                          | Promote it, or withdraw it first                                                                                                          |
| `… is locked: review N … is awaiting approval`            | Something tried to edit a draft under review (QGIS, SQL) | Promote it, or withdraw it first                                                                                                          |
| `Not confirmed — nothing was done.`                        | The name typed at the prompt didn't match                | Run the command again                                                                                                                     |
| `… is already under review`                                | Submitted twice                                          | Promote or withdraw the open review                                                                                                       |
| `cannot be submitted for review: … the draft is empty`     | A layer's push failed or loaded nothing                  | Check the push output, push again                                                                                                         |
| `cannot be submitted for review: … have no compartment_id` | Features without an id in the local data                 | Give them ids locally, push again                                                                                                         |
| `nothing to review. The draft is not locked.`               | Draft equals live                                        | Nothing to do                                                                                                                             |
| `No open review for: …`                                    | Promote without a review                                 | Do steps 2 and 3                                                                                                                          |
| `no longer matches review N (fingerprint changed)`          | The draft changed after submitting                       | Withdraw, push, submit again                                                                                                              |
| `--approved-by is required`                                 | No approver given                                        | Add `--approved-by "Name"` (several names allowed)                                                                                       |
| `the following arguments are required: --requested-by`      | Submit without a requester                               | Add `--requested-by "Name"`                                                                                                              |
| `column "requested_by" … does not exist`                    | The database wasn't updated after this feature was added | Run `setup_schemas.py` again (gis_create)                                                                                                |
| Project-level copy failed after a successful promote          | Live chameleon layers and history are already updated    | In the notebook, after the connection cells:`copy_to_project_level(chameleon_target_conn, project_level_target_conn, 'buffalo_schema')` |

---

## 5. Rules

- **Never load the ETL straight into the live schemas**, e.g. by calling the pipeline
  with `TARGET_SCHEMA_NAMES` from the notebook. It bypasses review and the history won't
  show an approval. Use `layers.py`.
- **Don't edit `<schema>_draft` in QGIS.** The local database is the only source. A
  draft edit is overwritten by the next push.
- **One review per project at a time.** Projects are independent: Buffalo can be under
  review while Colobus is pushed.
- History is append-only. `gis_update` can't delete it. Only an admin can reset it.

---

## 6. Dashboard

Separate project: `Desktop/layer_change_dashboard` (read-only, `gis_viewer` login).

```
cd C:\Users\LENOVO\Desktop\layer_change_dashboard
.venv\Scripts\streamlit.exe run app.py
```

- **View: Change history**: what changed in the live layers over any period (map,
  statistics, per-feature history, run log, period PDF report).
- **View: Pending approval**: what promoting each draft would change, the review
  status, the review log and the approval PDF.

See its README for setup (`.env` with the read-only login).
